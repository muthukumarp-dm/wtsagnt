# wtsagnt MVP Phase 1 — Todo

Full plan with acceptance criteria, verification steps, schema, and risks: [`tasks/plan.md`](./plan.md)

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done · `[!]` blocked

---

## Day-1 parallel kickoff (start before any slice — they unblock later work)

- [ ] **Submit WhatsApp approval template to Meta** (1–3 day approval, blocks 5a only). Template = project title + three short links + "Reply YES to approve, NO to reject."
- [ ] **Confirm Drive vs Supabase Storage** with user. Plan assumes Supabase Storage for MVP; flag now so slice 4 doesn't redo work.
- [ ] **Provision Supabase project + Railway project** (env scaffolding only — no code yet)

---

## Phase 1 — Foundation

- [ ] **1a · Scaffold + healthchecks** *(Medium · no deps)*
  - Next.js App Router in `apps/web/`, Python FastAPI in `apps/worker/`
  - Monorepo with shared `railway.toml`, `package.json`, `pyproject.toml`, `.gitignore`, `README.md`
  - Acceptance: `apps/web/` builds + serves `/`; `apps/worker/` serves `/healthz` returning `{"status":"ok"}`; both deploy to Railway with public 200s

- [ ] **1b · Supabase schema + Auth** *(Medium · depends 1a)*
  - Apply `supabase/migrations/0001_init.sql` (projects, generations, documents, approvers, approvals, inbound_messages, jobs + enums)
  - RLS ON every table; policies scoped to `owner_user_id = auth.uid()`
  - `@supabase/ssr` magic-link auth in Next.js
  - Acceptance: `list_tables` shows all tables; `get_advisors` clean on RLS; sign-in works; user A cannot read user B's rows

### ▶ Checkpoint: Foundation ready
- [ ] Both services deployed and healthy
- [ ] Schema applied, RLS verified
- [ ] User can sign in
- [ ] **Confirm with user before Phase 2**

---

## Phase 2 — Prompt → status visible

- [ ] **2 · Prompt submission** *(Small · depends 1b)*
  - `POST /api/projects` validates → inserts `projects` row (`status='researching'`) + `jobs` row (`kind='outline'`) atomically
  - Redirects to project detail page
  - Acceptance: non-empty prompt creates 1 project + 1 job; empty/whitespace → 400; cross-user reads blocked

- [ ] **2.5 · Status view** *(Small · depends 2)*
  - `(app)/page.tsx` lists my projects (newest first)
  - Project detail page polls every 2s while status is non-terminal
  - Document links: signed URLs generated server-side per request, never stored
  - Acceptance: only my projects visible; status badge updates ≤2s after DB change; document links download correct files

---

## Phase 3 — AI + documents

- [ ] **3 · AI content generation (outline)** *(Medium · depends 1b, 2)*
  - Worker polls `kind='outline'` jobs, leases with `lease_expires_at = now()+5min`
  - Calls Claude (`claude-sonnet-4-6`) via `LLMAdapter`, expects JSON per fixed slide schema (`layout ∈ {title, bullets, two_column, image_text}`)
  - Writes `generations` row with `outline_json`, model, tokens, `cost_cents`
  - Transitions to `status='generating'` and enqueues `kind='documents'`
  - Acceptance: outline_json non-empty with correct slide count; bad LLM output retries up to max_attempts then `status='failed'`; expired-lease pickup works; cost logged

- [ ] **4 · Document generation + storage upload** *(Medium · depends 3)*
  - `python-pptx` / `reportlab` / `python-docx` renderers in `apps/worker/generators/`
  - Renderer owns layout primitives; LLM only picks `layout` per slide
  - Upload to Supabase Storage at `projects/<id>/v<n>/<format>`
  - Insert 3 `documents` rows with `bytes`, `checksum_sha256`, `generation_id`
  - Transition to `awaiting_approval`, enqueue `kind='notify'`
  - Acceptance: 3 documents rows with non-zero bytes; files open clean in Keynote/Preview/Word; re-run is idempotent

### ▶ Checkpoint: Documents reachable
- [ ] End-to-end ≤2 min: prompt → 3 downloadable files
- [ ] Files open without corruption warnings
- [ ] Cost visible in `generations`
- [ ] **Confirm with user before WhatsApp slices**

---

## Phase 4 — WhatsApp approval

> **Hard blocker** for 5a: approved WhatsApp template (from Day-1 kickoff)

- [ ] **5a · WhatsApp outbound** *(Medium · depends 4 + approved template)*
  - `WhatsAppAdapter` interface; `TwilioAdapter` (dev) and `GupshupAdapter` (prod) implementations
  - Send template message with three `/r/:doc_id` redirect links (NOT raw signed URLs)
  - `/r/:doc_id` re-signs storage URL on each access
  - Insert `approvals` row with `template_message_sid`
  - Acceptance: message arrives ≤30s with 3 clickable links; links still work 24h later; provider failure retries

- [ ] **5b · WhatsApp inbound webhook** *(Medium · depends 5a)*
  - `POST /api/webhooks/whatsapp` verifies provider signature (Twilio HMAC / Gupshup shared secret)
  - Insert `inbound_messages` keyed by `provider_sid` unique constraint (dedupe replays)
  - Parse via `reply_parser.py`: regex first → Haiku fallback → ambiguous flag
  - Update `approvals.status` + `projects.status` + `final_decision_at`
  - Acceptance: "YES" → approved ≤10s; replay is no-op; bad signature → 401; unmatched phone → 200 + null match; ambiguous body surfaces on status view

### ▶ Checkpoint: MVP complete
- [ ] Happy path: prompt → docs → WhatsApp → approve → flipped
- [ ] Reject path: prompt → docs → WhatsApp → reject → flipped (NO rework — Phase 2)
- [ ] Webhook idempotency proven via replay
- [ ] Cross-user RLS isolation proven
- [ ] Cost per 20-slide deck within budget
- [ ] Ready for demo + Phase 2 planning

---

## Out of scope (do NOT build in this plan)

Rework loop · LMS integrations · Multi-tenant dashboard · Roles · Audit log UI · CrewAI / Langflow / n8n · Google Drive adapter · Voice / video / narration / grading · Analytics · Quiz / assignment generation · Multi-level approvals · SLA tracking

See `tasks/plan.md` for the full Phase 2/3 backlog.
