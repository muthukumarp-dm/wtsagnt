# Implementation Plan: `wtsagnt` — AI Workflow & WhatsApp Approval Platform (MVP Phase 1)

> Approved on 2026-05-13. Mirror of `/Users/newuser/.claude/plans/we-are-going-to-binary-hejlsberg.md`.
> Companion checklist: `tasks/todo.md`.

## Context

`wtsagnt` is a greenfield project (empty repo at `/Users/newuser/Projects/Personal/wtsagnt`). The vision is an AI-powered workflow platform where a user submits a natural-language prompt and the system researches, generates educational/business content, produces PPT/PDF/DOCX files, uploads them to cloud storage, and requests approval over WhatsApp — eventually publishing to LMS systems.

This plan covers **only the user's stated MVP Phase 1**: prompt input → AI-generated PPT/PDF/DOCX → cloud storage upload → WhatsApp approval. The user's listed Phase 2/3 items (rework loop, LMS integrations, dashboard, multi-agent orchestration, analytics, voice, video, grading, etc.) are explicitly **out of scope**, even though some appeared in the vision's end-to-end diagram. We are honoring the user's own scope split, not the most expansive reading of the doc.

The plan is sliced **vertically**: each task delivers an end-to-end observable behavior, so the system stays demoable after every slice and we discover integration risk early instead of at the end.

## Decisions (with rationale)

| Decision | Choice | Why |
|---|---|---|
| Web framework | Next.js (App Router) | User listed it; pairs cleanly with Supabase Auth via `@supabase/ssr`. |
| Worker language | Python (FastAPI for HTTP, plain `asyncio` worker for jobs) | The document-generation libs the user named (`python-pptx`, `reportlab`, `python-docx`) are Python. Don't bridge them. |
| DB + Auth + File storage | **Supabase** (Postgres + Auth + Storage) | User has Supabase MCP enabled. One vendor replaces Postgres + Clerk/Auth0 + (initial) Drive. Cuts MVP infra count. |
| LLM | Anthropic Claude (`claude-sonnet-4-6` for content; `claude-haiku-4-5` only as ambiguity fallback) | User is in Claude Code; Claude API skill loaded. |
| Approve/reject parsing | Regex/keyword first; Haiku only on ambiguity | Deterministic, testable, cheap. Don't put a model on the hot path of a yes/no decision. |
| Workflow orchestration | App code (linear pipeline with explicit Postgres state transitions). **Defer n8n/Langflow/CrewAI.** | One linear chain, one branch. An orchestration framework here is pure overhead. Re-evaluate after MVP ships. |
| Storage | Supabase Storage with a `StorageAdapter` interface. **Defer Google Drive adapter** to Phase 2. | Drive OAuth + folder-per-workspace + token refresh is its own project. Adapter pattern keeps the door open. ⚠ See "Open assumption to flag" below. |
| WhatsApp | `WhatsAppAdapter` interface. **Dev**: Twilio sandbox. **Production target**: Gupshup. | Twilio sandbox requires every approver to text a join code — unworkable for real users. Gupshup is the right India production pick (user's vision references Tamil-speaking students). Adapter lets us flip provider without rewrites. |
| Hosting | Railway | Railway plugin enabled in user's environment. |

### Open assumption to flag

The vision document mentions "Google Drive" repeatedly. We are **assuming** Drive is *aspirational*, not a hard MVP requirement, and shipping MVP with Supabase Storage signed URLs. If Drive is mandatory for MVP (e.g. the org already lives in Google Workspace and links must land in someone's My Drive), the slice 4 acceptance criteria need to change. **Flag this to the user before starting slice 4.**

## Architecture (one paragraph)

A Next.js app on Railway handles auth (Supabase Auth) and presents the prompt-submit form + a minimal status view. Submitting a prompt creates a `projects` row and a `jobs` row in Supabase Postgres. A Python worker process (also on Railway) polls `jobs` and runs a linear pipeline: `research/outline (Claude) → generate documents (python-pptx / reportlab / python-docx) → upload to Supabase Storage → record documents → send WhatsApp approval via adapter`. A public Next.js API route at `/api/webhooks/whatsapp` receives inbound replies, verifies the provider signature, deduplicates by provider message SID, parses approve/reject, and updates the `approvals` row. Row-Level Security on every table scopes data to `auth.uid()`. Everything is observable from the status view.

```
┌──────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Next.js │────▶│ Supabase        │◀────│ Python worker    │
│ (Railway)│     │ Postgres+Auth+  │     │ (Railway)        │
└──────────┘     │ Storage         │     │  - pipeline.py   │
      ▲          └─────────────────┘     │  - adapters/     │
      │                  ▲                └────────┬─────────┘
      │ webhook          │                         │
┌─────┴────────┐         │             ┌───────────▼─────────┐
│ WhatsApp     │─────────┴─────────────│ Anthropic Claude    │
│ (Twilio dev / │                       │ Storage upload      │
│  Gupshup prod)│                       └─────────────────────┘
└───────────────┘
```

## Schema (Supabase / Postgres)

All tables have RLS enabled and a policy scoping to `owner_user_id = auth.uid()` (or join through `projects` for child tables). All timestamps are `timestamptz default now()`. All `id` columns are `uuid default gen_random_uuid() primary key`.

```sql
create type project_status as enum (
  'draft','researching','generating','awaiting_approval',
  'approved','rejected','failed'
);

create type job_kind as enum ('outline','documents','notify');
create type job_status as enum ('queued','running','done','failed');

create table projects (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users(id),
  prompt text not null,
  prompt_hash text not null,            -- for dedupe
  status project_status not null default 'draft',
  final_decision_at timestamptz,
  created_at timestamptz default now()
);

create table generations (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  outline_json jsonb not null,
  model text not null,
  prompt_tokens int,
  completion_tokens int,
  cost_cents int,
  created_at timestamptz default now()
);

create table documents (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  generation_id uuid not null references generations(id),
  format text not null check (format in ('pptx','pdf','docx')),
  storage_path text not null,           -- "projects/<id>/v1/deck.pptx"
  bytes bigint not null,
  checksum_sha256 text not null,
  version int not null default 1,
  created_at timestamptz default now()
);
-- signed_url is NOT stored; regenerate on demand.

create table approvers (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null references auth.users(id),
  display_name text not null,
  phone_e164 text not null,             -- "+91..."
  verified_at timestamptz,
  unique (owner_user_id, phone_e164)
);

create table approvals (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  approver_id uuid not null references approvers(id),
  template_message_sid text,            -- outbound provider id
  status text not null default 'pending'
    check (status in ('pending','approved','rejected')),
  feedback text,
  requested_at timestamptz default now(),
  decided_at timestamptz
);

create table inbound_messages (
  id uuid primary key default gen_random_uuid(),
  provider text not null,               -- 'twilio' | 'gupshup'
  provider_sid text not null unique,    -- idempotency key
  from_phone text not null,
  body text not null,
  received_at timestamptz default now(),
  processed_at timestamptz,
  matched_approval_id uuid references approvals(id)
);

create table jobs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references projects(id) on delete cascade,
  kind job_kind not null,
  status job_status not null default 'queued',
  attempt int not null default 0,
  max_attempts int not null default 3,
  lease_expires_at timestamptz,         -- crash recovery
  last_error text,
  idempotency_key text not null unique,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
```

## Critical files (to be created)

- `supabase/migrations/0001_init.sql` — schema above + RLS policies
- `apps/web/` — Next.js App Router app
  - `apps/web/app/(app)/page.tsx` — prompt-submit form + project list
  - `apps/web/app/api/projects/route.ts` — `POST` creates project + job
  - `apps/web/app/api/webhooks/whatsapp/route.ts` — inbound webhook
  - `apps/web/lib/supabase/server.ts`, `apps/web/lib/supabase/client.ts`
- `apps/worker/` — Python worker
  - `apps/worker/main.py` — poll loop, job leasing
  - `apps/worker/pipeline.py` — research → generate → upload → notify
  - `apps/worker/generators/{pptx,pdf,docx}.py`
  - `apps/worker/adapters/storage.py` — `StorageAdapter` interface + `SupabaseStorageAdapter`
  - `apps/worker/adapters/whatsapp.py` — `WhatsAppAdapter` interface + `TwilioAdapter`, `GupshupAdapter`
  - `apps/worker/adapters/llm.py` — `LLMAdapter` interface + `AnthropicAdapter`
  - `apps/worker/reply_parser.py` — regex first, Haiku fallback
- `railway.toml` (web + worker services), `pyproject.toml`, `package.json`
- `README.md` — env vars, local dev, deploy

## Task List

### Phase 1: Foundation

#### Task 1a — Scaffold + healthchecks

**Description:** Set up monorepo with `apps/web` (Next.js App Router) and `apps/worker` (Python + FastAPI for `/healthz`). Both deploy to Railway from the same repo with separate services. No business logic.

**Acceptance criteria:**
- [ ] `apps/web/` builds and serves at `/` with a placeholder page
- [ ] `apps/worker/` runs and serves `GET /healthz` → `{"status":"ok"}`
- [ ] Both services deploy to Railway and the public URL of each returns 200

**Verification:**
- [ ] `cd apps/web && npm run build` succeeds
- [ ] `cd apps/worker && uvicorn main:app --port 8000` then `curl :8000/healthz` returns 200
- [ ] `curl https://<railway-web-url>/` returns 200
- [ ] `curl https://<railway-worker-url>/healthz` returns 200

**Dependencies:** None.

**Files touched:** `apps/web/*` (scaffold), `apps/worker/*` (scaffold), `package.json`, `pyproject.toml`, `railway.toml`, `.gitignore`, `README.md`.

**Scope:** Medium.

---

#### Task 1b — Supabase project, schema, auth wired to Next.js

**Description:** Provision Supabase project. Apply migration `0001_init.sql` with all tables + RLS. Wire Supabase Auth into Next.js using `@supabase/ssr` (email magic link is enough for MVP). User can sign in and the session is visible server-side.

**Acceptance criteria:**
- [ ] Migration applies cleanly (no errors)
- [ ] RLS is `ON` on every table and at least one positive + one negative test query confirms isolation
- [ ] User can sign in with magic link; `(app)/page.tsx` shows the user's email
- [ ] Anonymous visitor to `(app)/` is redirected to sign-in

**Verification:**
- [ ] `supabase` MCP `list_tables` shows all expected tables
- [ ] `supabase` MCP `get_advisors` returns no security errors on RLS
- [ ] Manual: log in as user A in one browser, confirm cannot see user B's projects (insert a stub row via SQL first)

**Dependencies:** 1a.

**Files touched:** `supabase/migrations/0001_init.sql`, `apps/web/lib/supabase/{server,client}.ts`, `apps/web/middleware.ts`, `apps/web/app/(auth)/login/page.tsx`, `apps/web/app/(app)/page.tsx`.

**Scope:** Medium.

---

### Checkpoint: Foundation ready
- [ ] Both services deployed and healthy on Railway
- [ ] Supabase schema applied with RLS verified
- [ ] User can sign in
- [ ] Confirm with user before proceeding to Phase 2

### Phase 2: Prompt → status visible

#### Task 2 — Prompt submission

**Description:** Authenticated user submits a prompt via a form on `(app)/`. `POST /api/projects` validates, inserts a `projects` row (`status='researching'`) and a `jobs` row (`kind='outline'`) atomically in a transaction, returns the project id. Redirect to a project detail page that polls for status.

**Acceptance criteria:**
- [ ] Submitting a non-empty prompt creates exactly one `projects` row and one `jobs` row owned by the current user
- [ ] User B cannot read user A's project rows (RLS proven)
- [ ] Empty/whitespace prompt returns a 400
- [ ] The project detail page shows `status='researching'` immediately after submit

**Verification:**
- [ ] Manual: submit "Create a 5-slide intro to SQL" → row appears in `projects` table via Supabase MCP `execute_sql`
- [ ] Manual: in incognito as user B, fetch user A's project id → 404 or 403
- [ ] Unit test: prompt validation rejects empty input

**Dependencies:** 1b.

**Files touched:** `apps/web/app/api/projects/route.ts`, `apps/web/app/(app)/page.tsx`, `apps/web/app/(app)/projects/[id]/page.tsx`, `apps/web/lib/validations.ts`.

**Scope:** Small.

---

#### Task 2.5 — Status view

**Description:** `(app)/page.tsx` lists the signed-in user's projects (newest first) with status and links to detail. Project detail page polls every 2s while `status` is non-terminal. Once `documents` rows exist, the detail page renders downloadable links (signed URLs generated on the fly server-side, never stored).

**Acceptance criteria:**
- [ ] List shows only the current user's projects (RLS confirmed)
- [ ] Status badge updates within 2s of a DB-side status change
- [ ] When documents exist, three signed-URL links are rendered (pptx/pdf/docx)
- [ ] Clicking a link downloads the file

**Verification:**
- [ ] Manual: insert a project row + 3 document rows via SQL → reload → see links and downloads work
- [ ] Manual: change project status via SQL while page is open → badge updates within 2s

**Dependencies:** 2.

**Files touched:** `apps/web/app/(app)/page.tsx`, `apps/web/app/(app)/projects/[id]/page.tsx`, `apps/web/app/api/projects/[id]/route.ts`, `apps/web/app/api/documents/[id]/url/route.ts`.

**Scope:** Small.

---

### Phase 3: AI + documents

#### Task 3 — AI content generation (outline)

**Description:** Worker `main.py` polls `jobs` where `kind='outline' and status='queued'`, leases (sets `lease_expires_at = now()+5min`), calls Claude through `LLMAdapter` with a structured prompt that returns JSON conforming to a fixed slide schema (title, then N slides each with `layout ∈ {title,bullets,two_column,image_text}` + content). Writes `generations` row with `outline_json`, model, tokens, cost. Transitions project `status → 'generating'` and enqueues `kind='documents'` job.

**Acceptance criteria:**
- [ ] Successful run: `generations` row exists with non-empty `outline_json`; `projects.status='generating'`; new `kind='documents'` job is queued
- [ ] LLM response that fails schema validation → retry up to `max_attempts`; final failure → `projects.status='failed'`, `jobs.last_error` populated
- [ ] Worker crash mid-job: another worker can pick up after `lease_expires_at` passes (test by manually expiring the lease)
- [ ] Cost is logged in `generations.cost_cents`

**Verification:**
- [ ] Manual: submit prompt → within 30s, `outline_json` is present, slide count matches request
- [ ] Test: feed deliberately invalid JSON response (via mock adapter) → status flips to `failed` after retries

**Dependencies:** 1b, 2.

**Files touched:** `apps/worker/main.py`, `apps/worker/pipeline.py`, `apps/worker/adapters/llm.py`, `apps/worker/schemas.py`.

**Scope:** Medium.

---

#### Task 4 — Document generation + storage upload

**Description:** Worker picks up `kind='documents'` job. Renders three files from `outline_json` using fixed slide templates (LLM picks `layout` per slide; renderer owns visuals — LLM never controls layout primitives):
- `.pptx` via `python-pptx`
- `.pdf` via `reportlab`
- `.docx` via `python-docx`

Each file is uploaded to Supabase Storage at `projects/<project_id>/v<version>/<format>`. A `documents` row is inserted with `bytes`, `checksum_sha256`, `generation_id`. Project status → `awaiting_approval` and enqueues `kind='notify'` job.

**Acceptance criteria:**
- [ ] Three `documents` rows exist after the job, one per format, each with `bytes > 0` and a valid sha256
- [ ] The three files in Supabase Storage open without corruption warnings in Keynote/Preview/Word
- [ ] Re-running the job is idempotent: re-run replaces files at the same `storage_path` and updates `documents` rows (does not duplicate)
- [ ] Project `status='awaiting_approval'` at the end

**Verification:**
- [ ] Manual: submit prompt, wait for status `awaiting_approval`, download all three files, open each. PPTX renders with no "repair" prompt.
- [ ] Manual: re-trigger documents job via SQL → no duplicate `documents` rows; files updated

**Dependencies:** 3.

**Files touched:** `apps/worker/generators/pptx.py`, `apps/worker/generators/pdf.py`, `apps/worker/generators/docx.py`, `apps/worker/adapters/storage.py`, `apps/worker/pipeline.py`.

**Scope:** Medium.

---

### Checkpoint: Documents reachable
- [ ] End-to-end: prompt submitted → three files downloadable from status view in under 2 minutes
- [ ] Files open in their native apps without corruption
- [ ] Cost tracked in `generations`
- [ ] Confirm with user before WhatsApp slices

### Phase 4: WhatsApp approval (outbound + inbound split)

> **Prerequisite (start on day 1, runs in parallel with everything else):** Submit the WhatsApp approval-message template to the chosen provider for Meta approval. Approval takes 1–3 business days and is a hard blocker for slice 5a. Template content: project title + three short links + "Reply YES to approve, NO to reject."

#### Task 5a — WhatsApp outbound

**Description:** Worker picks up `kind='notify'` job. Resolves a designated approver (for MVP, the project owner's first registered approver — `approvers` row created via a simple settings page or seeded SQL). Sends the approval template message via `WhatsAppAdapter` with three short signed-URL **redirect endpoints** (not raw signed URLs — see risk below). Inserts `approvals` row with `template_message_sid`, status `pending`.

A short redirect endpoint `/r/:doc_id` server-side re-signs the storage URL on access (so the link in WhatsApp never expires; the signed URL it redirects to is freshly minted each click). Owner-scoped via RLS.

**Acceptance criteria:**
- [ ] Approver's WhatsApp receives a templated message with three clickable links within 30s of `status='awaiting_approval'`
- [ ] `approvals.template_message_sid` is recorded
- [ ] Clicking any link in WhatsApp downloads the correct file
- [ ] Links still work 24 hours later (redirect endpoint re-signs)
- [ ] Provider failure → job retries up to `max_attempts`; final failure → `status='failed'`

**Verification:**
- [ ] Manual: submit a prompt with self as approver → WhatsApp message arrives, all three links download correct files
- [ ] Manual: wait 24h, click links again, confirm still working

**Dependencies:** 4, approved WhatsApp template.

**Files touched:** `apps/worker/adapters/whatsapp.py`, `apps/worker/pipeline.py`, `apps/web/app/r/[doc_id]/route.ts`, `apps/web/app/(app)/settings/approvers/page.tsx`.

**Scope:** Medium.

---

#### Task 5b — WhatsApp inbound webhook

**Description:** `POST /api/webhooks/whatsapp` accepts provider callbacks. Verifies the provider signature (Twilio: `X-Twilio-Signature` HMAC; Gupshup: shared secret). Inserts an `inbound_messages` row keyed by `provider_sid` (unique constraint dedupes replays). Looks up the matching `pending` approval by `from_phone` → `approvers.phone_e164` → most recent `pending` approval for that owner. Parses body via `reply_parser.py`:
1. Regex/keyword match first (`yes|approve|ok|👍|✅` → approved; `no|reject|rework|❌` → rejected)
2. If ambiguous, call Haiku for classification with a 1-token-budget structured response
3. If still ambiguous, record but do not decide; surface to status view as "ambiguous reply"

On match: update `approvals.status` and `decided_at`, update `projects.status` and `final_decision_at`, mark `inbound_messages.processed_at`.

**Acceptance criteria:**
- [ ] Replying "YES" within 10s sets `approvals.status='approved'`, `projects.status='approved'`, and `inbound_messages` row has `matched_approval_id` set
- [ ] Replaying the same webhook payload does NOT create a duplicate `inbound_messages` row and does NOT re-decide the approval
- [ ] Bad signature → 401, no DB write
- [ ] Unmatched `from_phone` → `inbound_messages` recorded with `matched_approval_id=null`, 200 returned to provider (no retry storm)
- [ ] Ambiguous body → status view shows "ambiguous reply, manual decision needed"

**Verification:**
- [ ] Manual: full E2E run — submit prompt, receive WhatsApp, reply YES, confirm `projects.status='approved'` in DB and on status view
- [ ] Manual: replay the captured webhook payload via `curl` → second call is a no-op
- [ ] Manual: send a webhook with a bad signature → 401
- [ ] Manual: reply "maybe later" → status view shows ambiguous

**Dependencies:** 5a.

**Files touched:** `apps/web/app/api/webhooks/whatsapp/route.ts`, `apps/worker/reply_parser.py` (shared lib — extract reply parser into a shared package or duplicate; for MVP, duplicate is fine), `apps/web/lib/whatsapp/signature.ts`.

**Scope:** Medium.

---

### Checkpoint: MVP complete
- [ ] End-to-end happy path: prompt → docs → WhatsApp → approve → status flips
- [ ] End-to-end reject path: prompt → docs → WhatsApp → reject → status flips to `rejected` (no rework — that's Phase 2)
- [ ] Webhook idempotency confirmed (replay does not double-process)
- [ ] RLS: cross-user isolation confirmed
- [ ] Cost per project (sum of `generations.cost_cents`) is visible and within expected budget for a 20-slide deck
- [ ] Ready for user demo + Phase 2 planning

## Parallelization

- 5a and 5b cannot start until the WhatsApp template is approved by Meta — submit on **day 1** of slice 1a so the 1–3 day approval runs in parallel with all other work.
- The three document generators (pptx/pdf/docx) inside slice 4 can be built in parallel by separate agents/sessions once the outline schema is locked.
- Slices 1a and the WhatsApp template submission are independent and should start the same day.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| WhatsApp template approval takes 1–3 days | Blocks 5a entirely | Submit template on day 1 of slice 1a in parallel |
| Twilio sandbox requires recipients to opt in via join code | Unusable for real approvers | Use sandbox only for dev demos; ship production with Gupshup. `WhatsAppAdapter` interface keeps the swap cheap |
| LLM-only PPTX output looks like a wall of text | Demo-killer | Fixed slide templates owned by the renderer; LLM picks `layout` per slide but never controls layout primitives |
| Signed URL expiry vs WhatsApp message permanence | Approver clicks dead link days later | All WhatsApp links go through `/r/:doc_id` redirect that re-signs on access |
| Webhook replay / Twilio retry storm | Double-decision, duplicate state changes | `inbound_messages.provider_sid` unique constraint + dedupe before applying |
| Worker crash mid-job | Orphaned project stuck in `running` | `jobs.lease_expires_at` — expired leases are reclaimable by other workers |
| Approver identity spoofing | A user could request approval to anyone's phone | `approvers` table is owner-scoped and verified (out-of-band verification deferred to Phase 2; for MVP require explicit registration via settings page) |
| LLM cost runaway | Bill shock | `generations.cost_cents` per call; daily-cap env var that the worker checks before queueing outline jobs (`MAX_DAILY_COST_CENTS`) |
| RLS misconfigured | Cross-tenant data leak | Supabase MCP `get_advisors` run after every migration; one positive + one negative isolation test in 1b acceptance |
| Single-LLM-provider outage | MVP down | Accept for MVP, document in README. `LLMAdapter` interface exists so a Gemini/OpenAI fallback can be added without rewrites |
| Drive turns out to be a hard MVP requirement | Slice 4 rework | Flag the assumption to user before slice 4 begins (see Decisions section) |

## Out of scope (Phase 2 candidates, do NOT build now)

- Rework loop on rejection (user listed as Phase 2)
- LMS integrations (Moodle, Google Classroom, Canvas, Blackboard, TalentLMS)
- Multi-tenant dashboard, roles, audit log UI
- Multi-agent orchestration (CrewAI/Langflow)
- n8n workflow engine
- Google Drive storage adapter
- Voice input, AI video, AI narration, AI grading
- Analytics, personalization, attendance, parent notifications
- Quiz generation, assignment grading
- Multi-level approvals, escalations, SLA tracking

## Verification: end-to-end test plan

After all slices land, this is the demo script to prove MVP works:

1. **Login**: open the web app, sign in with magic link as User A
2. **Register approver**: settings → add approver with my own E.164 WhatsApp number, mark verified
3. **Submit prompt**: `Create a 10-slide intro to Python for high school students with two exercises at the end`
4. **Observe pipeline**: status view shows `researching → generating → awaiting_approval` within ~90s
5. **Check files**: status view shows three download links; download .pptx, .pdf, .docx; each opens cleanly in Keynote/Preview/Word
6. **Check WhatsApp**: approval template message arrived with three links; clicking each downloads the right file
7. **Approve**: reply `YES` on WhatsApp
8. **Confirm**: status view flips to `approved` within 10s; DB has `approvals.status='approved'`, `projects.final_decision_at` set
9. **Replay attack**: re-send the captured Twilio/Gupshup webhook payload via `curl` — `inbound_messages` count unchanged, no duplicate state change
10. **Cross-user isolation**: sign in as User B in incognito; cannot see User A's project on `(app)/`; direct `GET /api/projects/<A_project_id>` returns 404/403
11. **Reject path** (separate run): same flow but reply `NO add more examples` — status flips to `rejected`, feedback stored, no rework triggered (Phase 2)

Use Chrome DevTools MCP to capture console errors and network failures during the run. Use Supabase MCP `get_logs` and `get_advisors` to confirm no DB errors or RLS warnings.

## Environment / Secrets needed (single source of truth)

- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `ANTHROPIC_API_KEY`
- `WHATSAPP_PROVIDER=twilio|gupshup`
- Twilio: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- Gupshup: `GUPSHUP_API_KEY`, `GUPSHUP_APP_NAME`, `GUPSHUP_SOURCE_NUMBER`
- `WHATSAPP_TEMPLATE_NAME` (approved template name)
- `MAX_DAILY_COST_CENTS` (LLM safety cap)
- `WEB_PUBLIC_URL` (used by redirect endpoint + WhatsApp link generation)

All secrets live in Railway env, never in code, never in git.
