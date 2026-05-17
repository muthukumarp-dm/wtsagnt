# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: wtsagnt (production-bound)

AI workflow + WhatsApp approval platform. Teachers send voice notes; the system generates teaching materials (PPT with embedded MCQs + a reference PDF) and pushes approved outputs to LMS/email. **Built for real production, not a throwaway.**

- **Owner:** Senthil (technical, will review prototypes and architecture decisions)
- **Developer:** Muthukumar

## Current state (2026-05-17 late evening)

**Monday WhatsApp slice — code complete, deployed to Railway, pending Twilio phone-join only.**

All 16 plan tasks implemented + 3 bonus E2E smoke tests against real cloud services. All 58 tests pass. Three real generated lesson decks + reckoners are in `prototype/outputs/` for hand inspection (happy path local, revision branch local, real-Supabase-Storage roundtrip).

**Deployed service:** `https://wtsagnt-monday-production.up.railway.app`
- Project: `wtsagnt-monday` (id `2f96e94c-5e3c-49b6-bfde-0322c1d0fde8`) in workspace `muthukumarp-dm's Projects`
- Service: `wtsagnt-monday` (id `a72d80f5-517b-41a9-b9c1-0456dff2689f`), production env
- Builder: railpack with `prototype/Procfile`
- `/health` returns 200 OK; `/webhooks/whatsapp` returns 401 for unsigned requests (signature verification working)

**Supabase project:** `elczksydirrjuqapcpgq` (in user's personal Supabase org, NOT the decisionminds org the MCP is connected to). Tables + `lesson-files` bucket exist; migration `0001_monday_demo.sql` applied via dashboard SQL editor.

- **Active spec:** `docs/superpowers/specs/2026-05-17-monday-whatsapp-slice-design.md`
- **Active plan:** `docs/superpowers/plans/2026-05-17-monday-whatsapp-slice.md`
- **Onboarding for new trainees:** `docs/HANDOVER.md` — reading order + Day-1 setup + per-track work assignments (A: TanStack frontend / B: n8n + LangFlow / C: backend integrations + hardening) + decision authority + workflow practices
- **Tomorrow checklist:** `prototype/NOTES-2026-05-17.md` — what's verified working + what you still need to do
- **Setup + run + deploy docs:** `prototype/README.md`
- **Parked artifacts** (LangFlow-only prototype, *not* on the Monday path; modules reused as parts donor): `docs/superpowers/specs/2026-05-13-wtsagnt-prototype-design.md` + `docs/superpowers/plans/2026-05-13-wtsagnt-prototype.md`. Tasks 2–5 of that plan (schemas, prompts, pptx, pdf) are imported verbatim by the Monday plan.
- **Workflow diagram (source of truth):** `docs/workflows/teacher-assistant-voice-whatsapp.mmd` (+ `.png`) — Senthil's full real-development target; Monday builds the stripped no-voice no-Drive no-Classroom subset.
- **`tasks/plan.md` is OBSOLETE.** Pre-pivot MVP plan, do not implement from it.

### What's still pending for Monday (user-only actions)

1. ~~Apply the Supabase migration~~ ✅ done
2. Rotate the leaked OpenAI key + update **both** `prototype/.env` AND Railway env var
3. Join Twilio sandbox from demo phone (text the `join <code>` SMS)
4. ~~Set `PUBLIC_BASE_URL`~~ ✅ done on Railway
5. Point Twilio sandbox webhook at `https://wtsagnt-monday-production.up.railway.app/webhooks/whatsapp`
6. ~~Railway deploy~~ ✅ done — service `wtsagnt-monday` live, `/health` 200 OK
7. Sunday-evening dry-run + 30s screen recording

Full step-by-step in `prototype/NOTES-2026-05-17.md`.

### Temporary LLM-provider deviation (Monday only)

The Monday demo ships **OpenAI `gpt-4o` + `gpt-4o-mini`** instead of the CLAUDE.md-locked `claude-sonnet-4-6` + `claude-haiku-4-5`. Reason: Anthropic key was not provisioned in time. **Planned revert post-Monday.** The pipeline's two LLM helpers (`call_llm_json`, `call_llm_text`) are the only swap-back touchpoints — ~10 minutes of work. Senthil to confirm at the demo. See spec's "CLAUDE.md compliance check" table.

## Locked stack (for real development, not prototype)

Decided during the 2026-05-13 brainstorm. Do not re-litigate without Senthil.

- **Frontend:** TanStack (Start + Router + Query) + Vercel AI SDK (UI side, all TypeScript)
- **Workflow / orchestration:** N8n (outer envelope — graph topology, branches, "Changes Required" rework loop, cross-system glue)
- **Agent runtime:** LangChain + LangFlow (per-agent LLM reasoning, visual canvas for prototyping). **LangGraph dropped** — N8n owns the graph instead.
- **LLM:** Anthropic Claude — `claude-sonnet-4-6` for content generation, `claude-haiku-4-5` only for cheap classification (e.g., ambiguous reply parsing)
- **DB + Auth + Storage:** Supabase
- **File storage target (produced documents):** Google Drive (per the workflow diagram); Supabase Storage as fallback
- **Hosting:** Railway. Cloudflare deferred — add only later as CDN/WAF if a real need shows up.
- **WhatsApp:** `WhatsAppAdapter` interface. Twilio sandbox for dev, Gupshup for production.
- **Speech-to-text:** TBD when voice ingress is built (Whisper / AssemblyAI / Deepgram / Sarvam are the candidates — Sarvam relevant for Indian languages).

The previous plan's Next.js + Python-worker + Supabase-Storage-only + linear-pipeline architecture is **dropped**.

## Workflow scope is intentionally not locked

The voice-WhatsApp diagram is **one** example workflow, not the whole product. The broader business surface — what other teacher/student workflows wtsagnt covers — is **deferred to SDD**. Use BMAD (`https://github.com/aj-geddes/claude-code-bmad-skills`) for that exploration when the time comes. **BMAD is not installed today**; install it at the start of the SDD phase, after the prototype demo.

## How we work on this codebase (Claude Code patterns)

### Agent Teams — for parallel collaborative work

For tasks that benefit from genuine parallel exploration — research with multiple angles, code review with several lenses (security / performance / tests), multi-module feature work where each teammate owns different files, debugging with competing hypotheses — use Claude Code's **Agent Teams**:

📘 https://code.claude.com/docs/en/agent-teams

Agent Teams is experimental and disabled by default. To enable, add to `settings.json`:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

- Requires Claude Code **v2.1.32+** (check with `claude --version`)
- Start with **3–5 teammates** for most workflows
- Use teams when teammates need to talk to each other and challenge each other's findings
- Higher token cost than a single session — use deliberately, not for routine work

### Subagents vs teams

- **Subagents** (`Agent` tool): focused workers that report results back to the main session. Use for delegated lookups, narrow reviews, and single-purpose research. Lower token cost.
- **Agent Teams**: independent Claude Code instances that share a task list and message each other directly. Use for genuine collaborative parallel work.

When unsure, default to subagents and escalate to a team only if the work genuinely needs cross-talk.

### Skills

The agent-skills set (`spec`, `plan`, `build`, `review`, `test`, `ship`, etc.) maps to development phases. Run the right skill at the right phase. For the broader business-context exploration (post-prototype), use BMAD instead of `spec` directly.

## Decision invariants (carry forward into real development)

These were decided in the earlier MVP plan and survive the redirect — they apply when real development starts on the new stack:

- **Supabase RLS is ON for every table**, scoped to `auth.uid()` (directly or via join). Every feature ships with a positive + negative isolation test. Run `get_advisors` via the Supabase MCP after every migration.
- **Signed URLs are never stored** — regenerate on demand. WhatsApp/email links go through a redirect endpoint that re-signs storage URLs on each access so links don't expire from the recipient's perspective.
- **Webhook idempotency** via a unique `provider_sid` constraint on inbound message rows. Always verify provider signatures before any DB write; bad signature → 401, no write.
- **Reply parsing order**: regex/keyword first → Haiku fallback only when ambiguous → if still ambiguous, surface as "manual decision needed," do not auto-decide. Never put a model on the hot path of a yes/no.
- **LLM cost cap**: track per-call cost in a `generations`-style table; enforce `MAX_DAILY_COST_CENTS` before enqueueing new generation work.
- **Renderer owns layout primitives.** The LLM picks a `layout` enum per slide and supplies content — it does not control layout details. Same rule for PDF rendering.

## Build / test / lint commands

No code has landed yet — the commands below are what the prototype plan installs. Update this section once the prototype is built so future sessions don't have to re-discover them.

**Prototype (per `docs/superpowers/plans/2026-05-13-wtsagnt-prototype.md`):** Python 3.11+, `uv` for deps. All commands run from `prototype/`.

- Install deps: `uv sync`
- Run all tests: `uv run pytest -v`
- Run a single test: `uv run pytest tests/test_pptx_formatter.py::test_render_pptx_creates_valid_file -v`
- Anthropic smoke test only: `uv run pytest tests/test_smoke_anthropic.py -v`
- Start the LangFlow canvas (loads custom components from `langflow_components/`):
  ```bash
  LANGFLOW_COMPONENTS_PATH=./langflow_components \
  ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2) \
  uv run langflow run --host 127.0.0.1 --port 7860
  ```
- Outputs land in `prototype/outputs/<UTC-timestamp>/` (gitignored).

Real-development commands (TanStack build, Python service runners, N8n compose-up, Supabase migrations) land as those pieces are built.
