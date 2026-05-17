# wtsagnt — Onboarding & Handover

**Audience:** new contributors joining the project after the Monday 2026-05-18 demo. Read this top-to-bottom before touching code.

**Owners:** Senthil (product owner, architecture authority) · Muthukumar (lead developer, repo gatekeeper)

---

## TL;DR — what wtsagnt is

A WhatsApp-driven AI assistant for teachers. Teacher sends a request (text today, voice later) → multi-agent pipeline produces lesson materials (`.pptx` deck + MCQs + 1-page reckoner) → bot asks for approval over WhatsApp → on approve, distributes to Google Classroom + email.

The Monday 2026-05-18 demo shipped a stripped slice: WhatsApp text in → `.pptx` + `.pdf` out → summary-first approval flow over WhatsApp, deployed at `https://wtsagnt-monday-production.up.railway.app`. That slice is the **proof of architecture**, not the final product.

Read the source-of-truth diagram before doing anything else: [`workflows/teacher-assistant-voice-whatsapp.mmd`](workflows/teacher-assistant-voice-whatsapp.mmd) (+ `.png`).

---

## Reading order (1.5–2 hours, do not skip)

1. **[`/CLAUDE.md`](../CLAUDE.md)** — locked stack + decision invariants. The "do not re-litigate without Senthil" list lives here.
2. **[`workflows/teacher-assistant-voice-whatsapp.mmd`](workflows/teacher-assistant-voice-whatsapp.mmd)** — the full target system, voice → WhatsApp → approval → Classroom/email.
3. **[`superpowers/specs/2026-05-17-monday-whatsapp-slice-design.md`](superpowers/specs/2026-05-17-monday-whatsapp-slice-design.md)** — the Monday demo design: architecture, data flow, CLAUDE.md compliance table, definition of done. This is what was actually built.
4. **[`superpowers/plans/2026-05-17-monday-whatsapp-slice.md`](superpowers/plans/2026-05-17-monday-whatsapp-slice.md)** — the 16-task implementation plan. Skim this; you don't need to re-implement, but it shows the TDD shape.
5. **[`prototype/README.md`](../prototype/README.md)** — setup, run, deploy, troubleshoot for the existing code.
6. **[`prototype/NOTES-2026-05-17.md`](../prototype/NOTES-2026-05-17.md)** — what's been verified working, what's pending.

After reading: clone the repo, get the local tests passing (Section "Day-1 environment setup" below), then look at the track-specific section for your assigned area.

---

## Day-1 environment setup

```bash
# 1. Clone
git clone https://github.com/muthukumarp-dm/wtsagnt.git
cd wtsagnt/prototype

# 2. Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Install deps
uv sync

# 4. Get your own credentials (do NOT share keys with other trainees)
#    - OpenAI key from platform.openai.com (or Anthropic key — ask Senthil which to use for your dev work)
#    - Your own Supabase project at app.supabase.com (free tier is fine)
#    - Twilio account at twilio.com (free trial credit is enough)
#    - Apply the migration on your Supabase project:
#      Dashboard → SQL editor → paste prototype/supabase/migrations/0001_monday_demo.sql → Run

# 5. Copy and populate .env
cp .env.example .env
# Edit .env with your values

# 6. Run the test suite
uv run pytest -v
# Expected: ~57 passed, smoke tests skip without their respective credentials

# 7. (Optional) Reproduce the live demo locally with ngrok + your Twilio sandbox
#    See prototype/README.md "Run the demo locally"
```

**If anything in steps 1–6 fails:** open a GitHub issue with the exact command, output, and your OS. Don't burn a day debugging your environment.

---

## The architecture — where we are vs. where we're going

### Where we are today (Monday demo)

```
WhatsApp (Twilio sandbox)
    │ POST
    ▼
FastAPI on Railway
    │ verify sig → dedupe → branch on state
    ▼
asyncio in-process pipeline
    │ 1. revision merger (conditional)
    │ 2. intent agent (OpenAI gpt-4o)
    │ 3/4/5. PPT + MCQ + reckoner (parallel gather)
    │ 6/7. render pptx/pdf
    │ 8. upload Supabase Storage + signed URLs
    │ 9. send summary via Twilio
    ▼
state machine: generating → awaiting_approval → approved → delivered
```

**Why this shape:** fastest path to "Senthil sees it work end-to-end on Monday." Everything is in one Python process, no orchestration tool, no UI. Adapter pattern for WhatsApp + Storage so we can swap providers without rewriting business logic.

### Where we're going (locked stack — production target)

```
┌─────────────────────────────────────────────────────────────────┐
│  TanStack Frontend (Start + Router + Query + Vercel AI SDK)     │
│  • Connector setup (Drive, Classroom, Email)                    │
│  • Project history + approval dashboard                          │
│  • Account settings + RLS-scoped teacher view                   │
└────────────────┬────────────────────────────────────────────────┘
                 │ Supabase Auth / direct Supabase queries
                 │ + n8n webhooks for actions
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  n8n (outer workflow envelope)                                   │
│  • Graph topology + branches + the "Changes Required" rework loop│
│  • Cross-system glue (Drive upload, Classroom post, Email send) │
│  • Calls LangFlow canvases for agent steps                      │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  LangFlow canvases (per-agent reasoning, LangChain inside)       │
│  • Intent + Prompt Engineering agent                             │
│  • PPT / MCQ / Reckoner content agents                          │
│  • Revision merger                                               │
│  • Reply parser (tier-2 fallback)                                │
│  • LLM: Anthropic Claude (sonnet-4-6 + haiku-4-5)               │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
Supabase (Postgres + Storage + Auth, RLS-on)  →  Google Drive (per-teacher folders)
                 │
                 ▼
WhatsApp (Gupshup for prod, Twilio for dev)  →  Google Classroom + Email
```

**The Monday slice modules survive the transition:**
- `src/schemas.py`, `src/prompts.py`, `src/pptx_formatter.py`, `src/pdf_formatter.py` — keep verbatim, they're called by LangFlow canvases instead of inline
- `src/whatsapp_adapter.py` — add `GupshupAdapter` next to `TwilioAdapter`, callers don't change
- `src/storage_adapter.py` — add `GoogleDriveAdapter`, callers don't change
- `src/reply_parser.py` — keep verbatim, called from n8n or pipeline

**What gets replaced:**
- `src/pipeline.py` orchestration → moves into n8n nodes calling LangFlow canvases
- `src/server.py` webhook → either stays as a thin webhook that triggers n8n, or n8n receives webhooks directly

---

## Trainee track assignments

Three parallel work streams. Each trainee owns one track end-to-end.

### Track A — Frontend (TanStack)

**Trainee A owns:** UI for teachers and admins to interact with the system outside of WhatsApp.

**Stack:** TanStack Start (full-stack framework) + TanStack Router + TanStack Query + Vercel AI SDK (for any in-app chat/streaming UI). TypeScript. Supabase JS client for data + auth.

**What to build (priority order):**

1. **Auth + scaffold** — Supabase Auth (email/password + magic link), TanStack Start project initialized, deployed to Railway alongside the backend
2. **Project history page** — list a teacher's past projects from the `projects` table (RLS-scoped to their `auth.uid()`), show status badges, link to files
3. **Approval inbox** — for each `awaiting_approval` project, show the summary + buttons to APPROVE / Request Changes (the latter opens a textarea, posts to a backend endpoint that drives the revision branch)
4. **Connector setup** — pages to connect Google Drive, Google Classroom, email — OAuth flows, store tokens encrypted in Supabase
5. **Account settings** — name, default grade level, default duration, signature for handouts

**Key non-obvious decisions you'll face:**
- How to handle long-running pipeline jobs (poll vs. Supabase Realtime — recommend Realtime subscriptions on `projects.state`)
- Where the OAuth callback for Drive/Classroom lands (your TanStack route, then a server function stores the token)
- How approvals from the frontend integrate with approvals from WhatsApp (same `projects` row, both paths write to it)

**Don't do alone:**
- Token encryption — coordinate with Track C (backend) for the encryption key management
- RLS policy design — coordinate with Track C; the policies need to match the queries your UI makes

### Track B — Workflow orchestration (n8n + LangFlow)

**Trainee B owns:** moving the in-process Python pipeline into n8n + LangFlow so the workflow is visual, branches are explicit, and the "Changes Required" rework loop is a first-class graph edge.

**Stack:** n8n (self-hosted on Railway or n8n cloud — Senthil's call), LangFlow (local install or cloud), LangChain Python (the LLM client used inside LangFlow custom components), Anthropic Claude SDK.

**What to build (priority order):**

1. **n8n self-hosted on Railway** — get an n8n instance running in the same Railway project, behind auth
2. **Port the Monday pipeline to n8n** — the existing 4-call agent pipeline becomes 4 LangFlow canvases (intent / ppt / mcq / reckoner) wired together inside one n8n workflow
3. **The "Changes Required" branch** — explicit branch in n8n that loops back to the intent agent with revision context. This is the part the current Python code does inline; making it visual is the whole point.
4. **Cross-system nodes** — n8n has native nodes for Google Drive, Classroom, Gmail. Wire those in for the post-approval distribution branch.
5. **Webhook trigger** — n8n receives the Twilio/Gupshup webhook (replaces `src/server.py` for production)
6. **Revert from OpenAI to Anthropic** — when Senthil approves an Anthropic key, swap `OPENAI_API_KEY` for `ANTHROPIC_API_KEY` and update the LangFlow LLM nodes from `gpt-4o` to `claude-sonnet-4-6`. The Python helpers `call_llm_*` in `pipeline.py` are the swap-back template.

**Key non-obvious decisions you'll face:**
- Where state lives: n8n's own DB vs. our Supabase `projects` table. Recommend Supabase as source of truth, n8n nodes write to it (so the frontend + WhatsApp side stay consistent).
- How LangFlow canvases get called from n8n: HTTP request to LangFlow's API (each flow has a flow ID and can be invoked via POST).
- Cost tracking: every LLM call must still write a `generations` row. Either LangFlow custom component does this, or n8n has a "log generation" node after each agent call.

**Don't do alone:**
- The state machine semantics (CAS, partial UNIQUE on inbound messages) — coordinate with Track C, they own the DB layer
- The reply parser tier-2 fallback — keep the existing Python `src/reply_parser.py`, call it from n8n via HTTP

### Track C — Backend integrations + hardening

**Trainee C owns:** everything that's not UI and not visual workflow — provider adapters, security, observability, deployment.

**Stack:** Python 3.11+, the existing `prototype/src/` codebase, Supabase admin, Railway, Google Cloud APIs.

**What to build (priority order):**

1. **`GupshupAdapter`** — new class in `src/whatsapp_adapter.py` implementing the `WhatsAppAdapter` Protocol against Gupshup's HTTP API. Same signature verify / send_text shape as `TwilioAdapter`. Update `.env.example` with `GUPSHUP_*` keys. Switch is a one-line factory change in `src/server.py`.
2. **`GoogleDriveAdapter`** — new class in `src/storage_adapter.py` implementing `StorageAdapter` against Drive's API. OAuth-token-based; the token comes from the per-teacher OAuth flow Track A builds. Files land in a per-teacher folder.
3. **RLS hardening** — flip RLS on for `projects`, `messages`, `generations`. Scope to `auth.uid()` via a `teacher_id` column. Add migration. Add positive + negative isolation tests (a teacher's queries cannot see another teacher's rows).
4. **Cost cap enforcement** — read `MAX_DAILY_COST_CENTS` from settings, sum `generations.cost_cents` for the current day, reject new pipeline runs if over cap.
5. **Signed-URL redirect endpoint** — `/files/<project_id>/<filename>` that re-signs the Storage URL on each request. Replaces the stored-URL pattern in the current Monday slice (matches the CLAUDE.md invariant "Signed URLs are never stored").
6. **STT for voice notes** — Twilio/Gupshup webhook → download audio → send to Deepgram (or Sarvam for Indian languages) → resulting transcript drives the existing pipeline.
7. **Sentry + structured logging** — observability beyond stderr.

**Key non-obvious decisions you'll face:**
- How to handle OAuth token refresh (Drive tokens expire) — recommend a background job per teacher that refreshes tokens 24h before expiry
- Whether `GoogleDriveAdapter` writes to a shared org folder or per-teacher My Drive — Senthil's call; default to per-teacher (matches the diagram)
- Whether to support both Twilio and Gupshup simultaneously (dev vs. prod env) or one at a time

**Don't do alone:**
- Multi-tenant data model decisions — coordinate with Track A on what the frontend expects, and with Track B on what n8n sees
- Anthropic key provisioning — Senthil owns this; you swap configs once he's done

---

## Decision authority + escalation

Three levels — know which you're at before acting.

| Decision type | Who decides | Examples |
|---|---|---|
| **Implementation detail inside your track** | You | Pick `httpx` over `requests`; structure a React component however you like; choose between two equally-valid n8n node arrangements |
| **Cross-track or affecting interfaces** | Track-leads sync, Muthukumar arbitrates | Should the frontend talk to n8n directly or via a backend proxy? What's the shape of the `approvals` table? |
| **Stack / architecture / invariant** | Senthil | Replace n8n with X; drop LangFlow; loosen RLS; use a different LLM provider; remove the approval step |

**The CLAUDE.md "Decision invariants" section lists the unmovable parts.** Read it. If you find yourself wanting to break one, that's a Senthil conversation, not a unilateral choice.

**Escalation channel:** GitHub issue → @ Muthukumar. Don't DM, don't Slack-DM. Issues create a paper trail.

---

## Workflow + practices

- **Branching:** `main` is deployable. Each piece of work lives on a branch named `<initials>/<short-description>` (e.g., `pa/auth-scaffold`). PR into `main` when ready. Squash-merge.
- **PR review:** at least one reviewer (Muthukumar, or another trainee for code-quality-only review). Must pass CI before merge.
- **Tests:** every new module gets unit tests. TDD-style is preferred; see `prototype/tests/test_state.py` and `test_pipeline.py` for the patterns.
- **Commits:** conventional-ish — `feat(area): what changed` / `fix(area): ...` / `docs(area): ...`. Write the **why**, not the **what**.
- **Daily standup:** 10 min, async in a shared channel. What I did, what I'm doing, what I'm blocked on.
- **Weekly architecture review:** 30 min with Senthil + Muthukumar + all trainees. Each trainee shows the working demo of their week's slice.

---

## What's verified working today (for reference)

- All 16 plan tasks implemented + 3 E2E smoke tests against real OpenAI + real Supabase Storage
- All 58 tests pass; smoke tests skip cleanly without their respective credentials
- Deployed at `https://wtsagnt-monday-production.up.railway.app` — `/health` 200, webhook returns 401 for unsigned requests (signature verification working)
- Full WhatsApp round-trip verified live: text in → summary in ~120s → APPROVE → file links
- Total cost so far: ~$0.10 of OpenAI

The Monday slice is **production-deployed** and **demonstrably working**. New work builds on top, doesn't replace from scratch.

---

## What's still pending (mostly user-only, but trainees can advance once onboarded)

From the Monday slice's spec deferrals:

1. RLS on every table (Track C, priority #1 after onboarding)
2. Signed URLs not stored (Track C, the redirect endpoint)
3. Cost cap enforcement (Track C)
4. Voice STT (Track C)
5. Gupshup adapter (Track C)
6. Google Drive / Classroom / email (Track B for n8n nodes, Track C for adapter)
7. n8n outer workflow (Track B's main work)
8. LangFlow canvases (Track B)
9. TanStack frontend (Track A's main work)
10. Anthropic key revert (any track, 10-minute change)

---

## Reference links

- **Live service:** https://wtsagnt-monday-production.up.railway.app
- **GitHub:** https://github.com/muthukumarp-dm/wtsagnt
- **Railway:** railway.com (workspace: `muthukumarp-dm's Projects`, project: `wtsagnt-monday`)
- **Supabase:** app.supabase.com (project ref `elczksydirrjuqapcpgq`)
- **Twilio Console:** console.twilio.com
- **Locked stack docs:**
  - TanStack: https://tanstack.com
  - Vercel AI SDK: https://sdk.vercel.ai
  - n8n: https://docs.n8n.io
  - LangFlow: https://docs.langflow.org
  - LangChain Python: https://python.langchain.com
  - Supabase: https://supabase.com/docs
  - Railway: https://docs.railway.com
  - Anthropic API: https://docs.anthropic.com (for the revert)
  - Gupshup API: https://docs.gupshup.io
