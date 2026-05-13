# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: wtsagnt (production-bound)

AI workflow + WhatsApp approval platform. Teachers send voice notes; the system generates teaching materials (PPT with embedded MCQs + a reference PDF) and pushes approved outputs to LMS/email. **Built for real production, not a throwaway.**

- **Owner:** Senthil (technical, will review prototypes and architecture decisions)
- **Developer:** Muthukumar

## Current state (2026-05-13)

Greenfield repo. Today's immediate work: build a quality prototype that demonstrates the multi-agent architecture on a LangFlow canvas. After Senthil approves the prototype, real development begins on the full locked stack.

- **Prototype spec:** `docs/superpowers/specs/2026-05-13-wtsagnt-prototype-design.md` — read this before doing any prototype work.
- **`tasks/plan.md` is OBSOLETE.** It described a Next.js + Python-worker MVP that has been superseded by Senthil's multi-agent voice-WhatsApp workflow diagram and a stack change. Do not implement from it. It will be archived or rewritten after the prototype lands.

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

Not yet defined. Today's prototype runs LangFlow locally — install LangFlow, open the canvas, run the flow. Real-development commands (TanStack build, Python service runners, N8n compose-up, Supabase migrations) land as those pieces are built. **Update this section as commands are added** so future sessions don't have to discover them.
