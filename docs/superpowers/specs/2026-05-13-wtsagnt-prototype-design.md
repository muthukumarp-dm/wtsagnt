# wtsagnt Prototype — Design Spec

**Date:** 2026-05-13
**Owner:** Senthil (technical, will watch the demo today)
**Developer:** Muthukumar
**Status:** Approved during brainstorm 2026-05-13, ready for implementation planning

## Purpose

Prove that the multi-agent architecture in Senthil's workflow diagram is viable. The prototype is the artifact Senthil watches to decide whether real development on the full stack should proceed.

The thing being de-risked is **"the agent network handles real teacher requests."** Output quality and end-user UX are explicitly *not* being de-risked today.

## Demo surface

LangFlow canvas only — no wrapping frontend.

Senthil watches the developer:
1. Open the LangFlow canvas (8 nodes visible, sensible layout, descriptive names)
2. Paste a sample teacher transcript into the Input node
3. Click Run
4. Watch nodes light up as the graph executes (~2 minutes end to end)
5. Open the two output files (`.pptx` and `.pdf`) and confirm they look like something a teacher would actually use

The canvas itself is the artifact. If Senthil asks "but is this real?" the answer is "yes, you just saw four Claude calls and two Python renderers fire."

## Agent graph (8 nodes)

```
[Input: transcript text]
      ↓
[Intent + Prompt Engineering]   ← 1 Claude call: parse the transcript and emit 3 downstream prompts
      ↓
      ├─→ [PPT Content Gen]     ── Claude → slide JSON
      ├─→ [MCQ Generator]       ── Claude → MCQ list with answers
      └─→ [Reckoner Content Gen] ── Claude → 1-page reference content
                ↓                       ↓                       ↓
           [Format to PPT]   ←─── MCQs merged in ───       [Format to PDF]
           (python-pptx)                                    (reportlab)
                ↓                                               ↓
                └─────────────→ [Output: 2 files] ←─────────────┘
                                  (.pptx + .pdf)
```

## Data flow

1. **Input** → raw transcript string.
2. **Intent + Prompt Engineering** → single Claude call returns JSON: `{subject, grade, topic, duration_min, n_slides, n_mcqs, ppt_prompt, mcq_prompt, reckoner_prompt}`.
3. **Three parallel Claude calls** consume the three expanded prompts:
   - `ppt_prompt` → slide list `[{layout, title, bullets|two_col|image_text_content}, ...]`
   - `mcq_prompt` → MCQ list `[{question, options:[A,B,C,D], answer, explanation}, ...]`
   - `reckoner_prompt` → reckoner sections `[{heading, body}, ...]`
4. **Format to PPT** consumes slide list + MCQ list; MCQs become the last N slides of the deck. Writes `.pptx` via `python-pptx`. Renderer owns layout primitives — the LLM only picks a `layout` enum per slide.
5. **Format to PDF** consumes reckoner sections, writes `.pdf` via `reportlab`.
6. **Output** writes both files to `./outputs/<UTC-timestamp>/` and returns the paths.

## Sample transcript (for the demo)

> "Hi, I need to prepare for tomorrow's class. It's a 30-minute lesson for grade 7 on photosynthesis. Cover the basic process, what goes in and what comes out, where in the plant it happens, and why it matters. Give me a one-page summary sheet I can hand to students, and 5 multiple choice questions for a quick quiz at the end. Make the slides visually varied, not just bullet walls."

Why this transcript: realistic teacher voice-note shape; exercises all four extractable fields (subject / grade / duration / output mix); India-flavored grade level; produces enough output to fill a believable deck.

## Tech stack — prototype subset

- **LangFlow** (local install) — the canvas + runtime
- **LangChain** — LLM client wrappers used by LangFlow's nodes
- **Anthropic Claude** `claude-sonnet-4-6` for all four LLM nodes
- **`python-pptx`** for `.pptx` rendering
- **`reportlab`** for `.pdf` rendering
- **Python 3.11+**

Local only. No deploy, no DB, no auth, no public endpoints.

## Out of scope (stubbed today, real later)

Deferred to the post-prototype build on the full locked stack:

- Speech-to-text (today: paste transcript as text)
- WhatsApp ingress/egress (Twilio dev → Gupshup prod)
- Google Drive upload / Google Classroom / Email distribution
- Approval flow + "Changes Required" rework loop
- TanStack frontend (Start + Router + Query) + Vercel AI SDK
- N8n outer workflow engine
- Supabase (Auth + Postgres + Storage)
- Railway hosting
- Multi-tenancy, RLS, signed-URL machinery
- Cost tracking, daily caps

## Error handling

Prototype-grade only:

- JSON-parse failures from Claude → LangFlow's built-in single retry on the LLM node, then fail loud
- Anthropic API errors → bubble up; demo is supervised, you'll see them on the canvas
- No DLQ, no persistent retry, no observability beyond LangFlow's run UI

## Verification (definition of done)

The prototype is done when **all six** of these are true:

1. LangFlow canvas opens locally with all 8 nodes visible and wired per the graph above
2. Pasting the sample transcript and clicking Run completes in ≤2 minutes
3. Both `lesson.pptx` and `reckoner.pdf` are written to `./outputs/<timestamp>/`
4. `lesson.pptx` opens in Keynote with **no** "needs repair" warning, has ~10 content slides + 5 MCQ slides
5. `reckoner.pdf` opens in Preview, is 1–2 pages, looks handout-grade (real headings, readable typography, not a wall of unstyled text)
6. Senthil agrees the architecture is worth building out

## What this prototype proves (and doesn't)

**Proves:** the multi-agent shape from the diagram works end-to-end with real LLM calls, real file outputs, and a real visual canvas Senthil can point at and modify.

**Does NOT prove:** voice-note quality, WhatsApp ingress/egress reliability, multi-tenant RLS, scale, cost-per-project, rework loop ergonomics, LMS distribution, approval-via-chat parsing, India-region latency. All those are post-prototype concerns.

## Decisions locked during brainstorm (do not re-litigate without Senthil)

- **Full target stack:** TanStack (Start + Router + Query) + Vercel AI SDK · LangChain + LangFlow · N8n (outer workflow / loops / branches) · Supabase · Railway · Anthropic Claude
- **LangGraph dropped** — N8n owns workflow topology, LangChain runs inside each agent step
- **Python worker from the old plan dropped** — orchestration via LangFlow/N8n instead
- **Google Drive (not Supabase Storage)** is the real-development storage target (per diagram), though prototype writes locally
- **WhatsApp = Gupshup for production, Twilio sandbox for dev**
- **BMAD (`aj-geddes/claude-code-bmad-skills`)** is the spec-driven-development tool for the broader business-context exploration *after* the prototype lands — not installed today
- **`tasks/plan.md` is obsolete** — it described a Next.js + Python-worker MVP that the diagram supersedes. It will be rewritten or archived after prototype lands.

## Next steps after this spec

1. `writing-plans` — produce the implementation plan for the prototype
2. Build the prototype (today)
3. Demo to Senthil
4. If approved: update CLAUDE.md, archive `tasks/plan.md`, install BMAD, run SDD on the broader business context, then begin real development on the full locked stack
