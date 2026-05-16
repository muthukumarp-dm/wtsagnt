# wtsagnt Monday WhatsApp Slice — Design Spec

**Date:** 2026-05-17
**Owner:** Senthil (technical, will watch the Monday 2026-05-18 demo)
**Developer:** Muthukumar
**Status:** Draft for user review

## Purpose

Demonstrate the wtsagnt multi-agent architecture **end-to-end over WhatsApp** on a single use case. A teacher sends a WhatsApp text message describing what they need; the agent network generates a `.pptx` lesson deck (with embedded MCQ slides) and a `.pdf` ready-reckoner; the bot replies on WhatsApp with a summary for approval; on `APPROVE` the bot delivers signed download links for both files.

This is the **WhatsApp-end-to-end demo** Senthil asked for on Monday. It supersedes the earlier LangFlow-only prototype as the demo path. The LangFlow canvas remains in `docs/superpowers/specs/2026-05-13-wtsagnt-prototype-design.md` as a parked artifact; we do not put it on the Monday critical path.

## Demo surface

A real WhatsApp conversation from a real phone:

1. Teacher → Twilio sandbox: *"30-min lesson for grade 7 on photosynthesis. Cover the process, inputs, outputs, where in the plant. 5 MCQs."*
2. Bot replies within 3 seconds: *"Got it. Generating your lesson…"*
3. Bot replies in ≤ 120 seconds with a summary: *"Made a 30-min grade-7 lesson on photosynthesis: 10 slides + 5 MCQs + 1-page reckoner. Reply APPROVE to receive files, or tell me what to change."*
4. Teacher replies: `APPROVE`
5. Bot replies with two messages (or one with both links) containing signed URLs to `lesson.pptx` and `reckoner.pdf`
6. Teacher opens both on phone and confirms they look like materials a real teacher would use

A revision branch is also demonstrated:

7. Instead of `APPROVE`, teacher replies *"Make it for grade 8 instead, and add a section on cellular respiration"*
8. Bot replies: *"Updating with your changes…"*
9. ~ 90 seconds later a new summary arrives
10. Teacher approves and receives the revised files

## Pre-flight blockers (P0)

These cannot be parallelized with development. They must be done — or owned by a specific person with a specific deadline — **before any code is written**:

1. **Twilio sandbox phone join.** Twilio's WhatsApp sandbox requires each participating phone to text `join <sandbox-code>` to the sandbox number **once**. If neither Muthukumar's nor Senthil's phone is joined by Saturday evening, the Monday demo cannot run regardless of code quality. **Owner: Muthukumar. Action: join both phones today.**
2. **Anthropic API key** present in `prototype/.env` as `ANTHROPIC_API_KEY`.
3. **Twilio credentials** in `prototype/.env`: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM` (the `whatsapp:+1415...` sandbox number).
4. **Supabase secret key** in `prototype/.env` as `SUPABASE_SECRET_KEY` (new-format `sb_secret_...` or legacy `service_role` JWT).
5. **Supabase database password** (set when the project was created) — for `supabase link --project-ref elczksydirrjuqapcpgq` and `supabase db push`.
6. **Railway project provisioned** at deploy time via Railway MCP.

A Sunday-night dry-run + 30-second screen recording of the happy path is required (see "Demo day plan"). It costs five minutes and saves you on Anthropic 503, Twilio sandbox hiccups, or Railway cold-start during the live demo.

## Out of scope

Deferred to post-Monday hardening / Phase 2:

- Voice notes & speech-to-text (Whisper / Deepgram / Sarvam — picked later)
- Google Drive / Microsoft OneDrive / Google Classroom uploads
- Email distribution to students
- Multi-tenant Supabase RLS (Monday demo is single-phone)
- LangFlow canvas as the demo surface
- Native WhatsApp media attachments (we send signed links, sidesteps Twilio's 5 MB cap)
- Per-day LLM cost cap *enforcement* (cost is *tracked* on every call)
- Languages other than English (Indian-English is fine; Tamil/Hindi later)
- Gupshup production WhatsApp adapter (Twilio sandbox for Monday)

## Architecture

```
WhatsApp (Twilio sandbox)
      │
      │ POST /webhooks/whatsapp
      ▼
FastAPI on Railway
      │
      │ 1. Verify X-Twilio-Signature                      → bad sig: 401, no writes
      │ 2. Dedupe by MessageSid (partial UNIQUE inbound)  → dup: empty TwiML, no work
      │ 3. Persist inbound message row
      │ 4. Match phone to latest project; decide route
      │ 5. Return TwiML inline ack ("Got it…" or          ← inline, no extra API call
      │    "Updating with your changes…") in the response
      │ 6. Schedule asyncio background task; return
      ▼
Background pipeline (asyncio task in-process)
      │
      ├── route = new_request    (no project OR latest state ∈ {approved, delivered, error})
      │   │
      │   └── generation pipeline (creates new projects row)
      │       │
      │       ├── 0. Skipped on first run (revision_count == 0)
      │       ├── 1. Intent + Prompt Engineering   (Claude Sonnet 4.6)
      │       ├── 2. PPT Content                   (Claude Sonnet 4.6)  ┐
      │       ├── 3. MCQ Generation                (Claude Sonnet 4.6)  ├─ parallel
      │       ├── 4. Reckoner Content              (Claude Sonnet 4.6)  ┘
      │       ├── 5. pptx_formatter.render_pptx → bytes
      │       ├── 6. pdf_formatter.render_pdf → bytes
      │       ├── 7. Upload to Supabase Storage; mint signed URLs
      │       └── 8. CAS UPDATE state=awaiting_approval; send summary via Twilio
      │
      └── route = reply_to_pending  (latest state == awaiting_approval)
          │
          └── reply parser
              │
              ├── regex (APPROVE/YES/OK/👍/✅/SEND/GO) → approved
              ├── body > 30 chars and no approval token → changes_requested
              └── ambiguous → Claude Haiku 4.5 classification
                   │
                   ├── APPROVED → CAS UPDATE awaiting_approval → approved.
                   │              Send 2 messages with file URLs.
                   │              CAS UPDATE approved → delivered.
                   │              (If CAS row count = 0 anywhere: another handler won, exit.)
                   │
                   ├── CHANGES  → CAS UPDATE awaiting_approval → generating
                   │              (also: append to current_request, bump revision_count).
                   │              If CAS row count = 0: exit. Else run revision merger
                   │              (Claude Sonnet 4.6) → coherent brief → restart pipeline.
                   │
                   └── UNCLEAR  → reply asking for clarification; no state change
```

## Components

### Persistence — Supabase Postgres

Three tables. RLS is **OFF** for Monday (single-phone demo). See "Compliance" section.

**`projects`** — one row per generation request
| column | type | notes |
|---|---|---|
| `id` | uuid pk | |
| `phone` | text | teacher's WhatsApp address (`whatsapp:+91...`) |
| `original_request` | text | the first inbound transcript-as-text |
| `current_request` | text | original + accumulated revision notes |
| `state` | text | `generating \| awaiting_approval \| approved \| delivered \| error` |
| `summary` | text | the summary that was sent for approval |
| `pptx_url` | text | signed Supabase Storage URL (7-day TTL) |
| `pdf_url` | text | signed Supabase Storage URL (7-day TTL) |
| `revision_count` | int default 0 | bumps each "changes requested" loop |
| `error_reason` | text nullable | populated on state=error |
| `created_at`, `updated_at` | timestamptz | |

**`messages`** — every inbound and outbound WhatsApp message
| column | type | notes |
|---|---|---|
| `id` | uuid pk | |
| `project_id` | uuid fk projects.id nullable | nullable for unmatched inbound |
| `direction` | text | `inbound \| outbound` |
| `provider_sid` | text | Twilio MessageSid. **Partial UNIQUE index** on `(provider_sid) WHERE direction='inbound'` — enforces idempotency on the webhook hot path without colliding with outbound SIDs returned by Twilio's send API. |
| `from_phone`, `to_phone`, `body` | text | |
| `created_at` | timestamptz | |

**`generations`** — every Claude API call (for cost tracking + debugging)
| column | type | notes |
|---|---|---|
| `id` | uuid pk | |
| `project_id` | uuid fk projects.id | |
| `step` | text | `intent \| ppt_content \| mcq \| reckoner \| reply_parse` |
| `model` | text | `claude-sonnet-4-6` or `claude-haiku-4-5` |
| `input_tokens`, `output_tokens` | int | from Anthropic response |
| `cost_cents` | int | computed from token counts × model rate |
| `created_at` | timestamptz | |

**Storage bucket:** `lesson-files`. Private. Paths: `<project_id>/lesson.pptx`, `<project_id>/reckoner.pdf`. Signed URLs minted on upload with 7-day TTL.

**Concurrency control — state CAS.** Every state-changing UPDATE includes the expected current state in its WHERE clause:

```sql
-- accept approval (idempotent under concurrent webhook hits)
UPDATE projects SET state = 'approved', updated_at = now()
 WHERE id = $1 AND state = 'awaiting_approval';

-- accept revision request
UPDATE projects
   SET state = 'generating',
       current_request = current_request || E'\n\nRevision ' || (revision_count + 1)::text || ': ' || $2,
       revision_count = revision_count + 1,
       updated_at = now()
 WHERE id = $1 AND state = 'awaiting_approval';
```

If `rowcount == 0`, another handler already advanced the state and this handler exits with no side effects (no duplicate generation, no duplicate delivery). This handles the teacher double-tapping APPROVE, a revision arriving while we're still generating, and any other inbound-race scenario. No advisory locks required.

**Route decision uses the *latest* project for a phone, not the first awaiting_approval found.** If the latest project's state is in `{approved, delivered, error}`, the inbound message is treated as a brand-new request and a new `projects` row is created. This is intentional: an errored project does not silently swallow the teacher's next message.

### Code layout — `prototype/src/`

```
prototype/src/
├── schemas.py             # REUSED from existing prototype plan: Intent, Slide, SlideDeck,
│                          # MCQ, MCQList, ReckonerSection, Reckoner (pydantic v2)
├── prompts.py             # REUSED: INTENT_AND_PROMPT_ENGINEERING, PPT_CONTENT_GENERATION,
│                          # MCQ_GENERATION, RECKONER_GENERATION (string constants)
├── pptx_formatter.py      # REUSED: render_pptx(slides, mcqs, output_path)
├── pdf_formatter.py       # REUSED: render_pdf(reckoner, output_path)
├── settings.py            # NEW: pydantic-settings; loads .env into typed Settings
├── pipeline.py            # NEW: generate(project_id), handle_reply(project_id, body),
│                          # merge_revisions(coherent_brief) — pre-step before intent agent
│                          # when revision_count > 0 (skipped on first run)
├── whatsapp_adapter.py    # NEW: WhatsAppAdapter Protocol + TwilioAdapter impl
├── storage_adapter.py     # NEW: StorageAdapter Protocol + SupabaseStorageAdapter impl
├── reply_parser.py        # NEW: parse(body) → 'approved' | 'changes_requested' | 'unclear'
├── state.py               # NEW: Postgres CRUD via supabase-py; project state machine
└── server.py              # NEW: FastAPI app, POST /webhooks/whatsapp
```

**Migrations:** `prototype/supabase/migrations/0001_monday_demo.sql` creates the three tables and the storage bucket.

**Tests:** `prototype/tests/`
- Reused: `test_pptx_formatter.py`, `test_pdf_formatter.py`, `test_schemas.py`, `test_smoke_anthropic.py`
- New: `test_reply_parser.py`, `test_twilio_signature.py`, `test_pipeline.py` (with mocked adapters), `test_smoke_twilio.py`, `test_smoke_supabase.py`

### Adapter contracts

```python
# whatsapp_adapter.py
class WhatsAppAdapter(Protocol):
    def verify_signature(self, raw_body: bytes, signature: str, url: str) -> bool: ...
    async def send_text(self, to: str, body: str) -> SendResult: ...

# storage_adapter.py
class StorageAdapter(Protocol):
    async def upload(self, bucket: str, path: str, content: bytes, content_type: str) -> None: ...
    async def signed_url(self, bucket: str, path: str, expires_in_seconds: int) -> str: ...
```

Monday implementations: `TwilioAdapter`, `SupabaseStorageAdapter`. Gupshup, Drive, OneDrive land later behind the same interfaces — no caller changes required.

### LLM strategy

**Temporary LLM-provider deviation (Monday demo only):** The locked stack in CLAUDE.md is Anthropic Claude. For the Monday-week demo, the developer (Muthukumar) opted to use OpenAI because an Anthropic key was not provisioned in time. **Planned revert:** swap back to Claude after the Monday demo, once an Anthropic key is provisioned at decisionminds. The pipeline's two LLM helpers (`call_llm_json` and `call_llm_text`) are the only swap-back touchpoints — ~10 minutes of work when the time comes.

| Pipeline step | Model (Monday) | Planned revert | Reasoning |
|---|---|---|---|
| Revision merger (only when `revision_count > 0`) | `gpt-4o` | `claude-sonnet-4-6` | Pre-step that reconciles `original_request` + all accumulated `Revision N:` blocks into a single coherent brief. The intent agent then sees one clean transcript, not a concatenation it has to interpret. |
| Intent + Prompt Engineering | `gpt-4o` | `claude-sonnet-4-6` | Needs reasoning to decompose teacher's request |
| PPT Content | `gpt-4o` | `claude-sonnet-4-6` | Slide-by-slide content quality matters |
| MCQ Generation | `gpt-4o` | `claude-sonnet-4-6` | Distractor quality matters |
| Reckoner Content | `gpt-4o` | `claude-sonnet-4-6` | Handout text quality matters |
| Reply parsing (tier-2 fallback) | `gpt-4o-mini` | `claude-haiku-4-5` | Cheap classification — CLAUDE.md invariant preserved (regex first, model only on ambiguity) |

All five content calls use OpenAI's native JSON mode (`response_format={"type": "json_object"}`) — more reliable than Claude's prompt-engineered JSON. The `_strip_json_fences` defensive parsing stays in place as belt-and-suspenders.

Prompt-caching: the four content prompt prefixes are stable across calls; OpenAI's automatic prompt caching (enabled on `gpt-4o` for inputs ≥1024 tokens, ~50% discount on cached tokens) applies without code changes.

Prompt-caching enabled on the four content-generation prompt prefixes (the long instruction blocks are stable across calls).

## Data flow (concrete walkthrough)

**Inbound message → generation:**

1. Teacher's phone sends WhatsApp text "30-min lesson grade 7 photosynthesis…" to Twilio sandbox number
2. Twilio POSTs `/webhooks/whatsapp` with form-encoded body and `X-Twilio-Signature` header
3. `server.py` handler:
   - Calls `TwilioAdapter.verify_signature(raw_body, sig, request_url)`. Bad sig → 401, no DB write, no reply.
   - INSERTs into `messages` with `direction='inbound'`, `provider_sid=<MessageSid>`. On partial-UNIQUE conflict → return empty `<Response/>` TwiML, no further work (idempotency).
   - Loads the **latest** project for this `phone` (`order by created_at desc limit 1`). Branches on its state:
     - **No project, or state ∈ {approved, delivered, error}** → INSERT new `projects` row state=`generating`, original_request=body, current_request=body, revision_count=0. Schedule `pipeline.generate(project_id)`. Return TwiML inline ack: `<Response><Message>Got it. Generating your lesson…</Message></Response>`.
     - **state = awaiting_approval** → schedule `pipeline.handle_reply(project_id, body)`. Return empty `<Response/>` — `handle_reply` decides whether to send "Updating…" (revision branch) or stay silent until files are ready.
     - **state = generating** → race with our own in-flight pipeline. Return TwiML inline: `<Response><Message>Still working on the previous request — one moment.</Message></Response>`. Do not schedule new work.
   - The TwiML reply is sent in the HTTP 200 response body — **no separate Twilio API call**. Guarantees the teacher sees the ack in under 1 second, independent of Twilio API latency.
4. `pipeline.generate(project_id)`:
   - Loads project.
   - **If `revision_count > 0`:** calls the revision merger (Sonnet) with `current_request` → coherent brief string. Records `generations` row (step=`revision_merge`). The intent agent will see this single brief, not the raw original+revisions concatenation.
   - **Else:** uses `current_request` as the brief directly.
   - Calls Intent agent with the brief. Validates with `Intent.model_validate`. Inserts `generations` row.
   - Runs PPT/MCQ/Reckoner agents in parallel via `asyncio.gather`. Validates each. Inserts 3 `generations` rows.
   - Calls `pptx_formatter.render_pptx(slides, mcqs, tmp_path)`. Reads tmp file into bytes.
   - Calls `pdf_formatter.render_pdf(reckoner, tmp_path)`. Reads tmp file into bytes.
   - Uploads `lesson.pptx` and `reckoner.pdf` to `lesson-files/<project_id>/`.
   - Mints signed URLs (7-day TTL).
   - **CAS UPDATE:** `state='awaiting_approval', pptx_url=$, pdf_url=$, summary=$` WHERE `state='generating' AND id=$1`. If rowcount=0 → another handler already advanced the state; exit without sending. Else send summary via `TwilioAdapter.send_text`.

**Reply → approval / revision:**

5. Teacher replies "APPROVE". Webhook handler is in the `awaiting_approval` route; schedules `pipeline.handle_reply(project_id, "APPROVE")` and returns empty TwiML.
6. `reply_parser.parse("APPROVE")`:
   - Tier-1 regex matches `^approve\b` (case-insensitive) → returns `approved`.
7. `handle_reply`:
   - On `approved`:
     - **CAS UPDATE:** `state='approved'` WHERE `state='awaiting_approval' AND id=$1`. If rowcount=0 → another handler already moved the state (double-tap, late revision); exit silently.
     - Send two outbound WhatsApp messages (one with `pptx_url`, one with `pdf_url`) via `TwilioAdapter.send_text`.
     - **CAS UPDATE:** `state='delivered'` WHERE `state='approved' AND id=$1`.
   - On `changes_requested`:
     - **CAS UPDATE:** `state='generating'`, append revision to `current_request`, `revision_count += 1`. WHERE `state='awaiting_approval' AND id=$1`. If rowcount=0 → exit.
     - Send "Updating with your changes…" via `TwilioAdapter.send_text` (inside the background task; webhook already returned).
     - Re-invoke `pipeline.generate(project_id)` — the revision merger runs first because `revision_count > 0`.
   - On `unclear`:
     - Send: "I'm not sure — reply APPROVE to receive the files, or describe what you'd like to change." No state change.

## Reply parser — three tiers

Compliance with CLAUDE.md invariant: regex first → Haiku only on ambiguity → never auto-decide ambiguous.

**Tier 1: regex (deterministic, cheap).**
- Approved patterns: `^\s*(approve|approved|yes|ok|okay|👍|✅|send|share|go|done|all good|looks good)\s*[.!]?\s*$`
- Heuristic for `changes_requested`: body length > 30 chars AND no approval pattern anywhere → revision instruction
- Otherwise → fall through to tier 2

**Tier 2: Claude Haiku 4.5 (only when tier 1 is ambiguous).**
```
You will classify a teacher's WhatsApp reply.

The teacher was shown a summary of an auto-generated lesson and asked to
either approve it (to receive the files) or describe changes they want.

Reply: """{body}"""

Output EXACTLY one word: APPROVED | CHANGES | UNCLEAR
- APPROVED: reply means yes, send the files
- CHANGES: reply describes modifications to the lesson
- UNCLEAR: reply is too short, contradictory, or off-topic to decide
```

**Tier 3: never auto-decide.** If Haiku returns `UNCLEAR` or any malformed output, the bot asks the teacher to clarify. We do not flip a coin.

## Error handling (prototype-grade, supervised demo)

| Failure | Behavior |
|---|---|
| Bad Twilio signature | 401, no DB write, no reply |
| Duplicate webhook (same MessageSid) | Partial-UNIQUE conflict → return empty `<Response/>` TwiML, no further work |
| Anthropic API error mid-pipeline | **CAS UPDATE** `state='error'`, `error_reason=str(exc)` WHERE `state='generating' AND id=$1`. Send "Something went wrong, please try again" via `TwilioAdapter.send_text`. Log to stderr. No automatic retry for Monday. Teacher's next message starts a fresh project (latest-state route rule). |
| Pydantic validation error on Claude JSON | Same as above. (Post-Monday: single retry with stricter "JSON only, no markdown" reminder.) |
| Supabase Storage upload fails | Same as above. |
| Twilio send fails | Single retry via `tenacity` (1s backoff). Second failure → CAS UPDATE state=`error`. |

No DLQ, no Sentry, no observability beyond stderr logs and the `generations` / `messages` tables. Acceptable because the demo is supervised.

## Testing

**Unit tests (pytest, fast, run in CI later):**
- `test_reply_parser.py` — fixtures: clear approvals (`yes`, `APPROVE`, `👍`), clear changes (long instruction strings), genuinely ambiguous strings (`maybe`, `hmm`, `huh?`). For ambiguous cases, mock the Haiku call.
- `test_twilio_signature.py` — uses Twilio's published test vectors for `validateRequest`.
- `test_pipeline.py` — wires `pipeline.generate` against mocked Anthropic/Storage/Twilio adapters; asserts the 4-call sequence, parallel fan-out shape, state transitions.
- `test_pptx_formatter.py`, `test_pdf_formatter.py`, `test_schemas.py` — reused from existing prototype plan.

**Smoke tests (require real credentials, skipped unless env vars set):**
- `test_smoke_anthropic.py` — confirms the Claude API key works.
- `test_smoke_twilio.py` — sends a single message to the dev phone.
- `test_smoke_supabase.py` — uploads/downloads a 1KB blob, signs a URL.

**End-to-end (manual, on Monday morning before demo):**
- Real text from real phone → full round trip → approve → files received → revision branch tested → second approve → revised files received.

## Definition of done

Monday demo passes if **all** of these are true:

1. Real WhatsApp text from a real phone to the Twilio sandbox triggers the pipeline
2. Bot acknowledgment ("Got it") arrives within 3 seconds
3. Summary arrives within 120 seconds of the original message
4. Replying `APPROVE` yields the two file links within 5 seconds
5. `lesson.pptx` opens clean in Keynote (no "needs repair" warning), has ~10 content slides + N MCQ slides
6. `reckoner.pdf` opens clean in Preview, is 1–2 pages, handout-grade
7. A revision reply triggers regeneration; a new summary arrives ≤ 120 seconds later
8. Service is deployed on Railway (not localhost) and Twilio's sandbox webhook points at the public URL
9. Senthil watches the round trip live and agrees it demonstrates the multi-agent architecture working end-to-end

## CLAUDE.md compliance check

| Invariant | Monday compliance | Notes |
|---|---|---|
| **Supabase RLS on every table** | ❌ Deferred | Single-phone demo, no `auth.uid()` yet. Hardening pass post-Monday will add RLS scoped to `phone` (or to a Supabase auth user once we wire auth). |
| **Signed URLs never stored** | ❌ Deferred | URLs stored on `projects` row with 7-day TTL. Post-Monday: replace stored URLs with a redirect endpoint that re-signs on demand. |
| **Webhook idempotency via unique `provider_sid`** | ✅ Enforced | UNIQUE on `messages.provider_sid`. |
| **Webhook signature verification before any DB write** | ✅ Enforced | `TwilioAdapter.verify_signature` runs first; bad sig → 401 with no DB write. |
| **Reply parsing: regex → cheap-model → never auto-decide** | ✅ Enforced | Three-tier parser; tier-2 model is `gpt-4o-mini` for Monday (`claude-haiku-4-5` planned revert). UNCLEAR replies prompt clarification. |
| **LLM provider: Anthropic Claude** | ⚠️ Temporary deviation | OpenAI (`gpt-4o` + `gpt-4o-mini`) for the Monday-week demo. Planned revert to Claude when an Anthropic key is provisioned at decisionminds. Senthil to confirm at the demo. |
| **LLM cost cap** | ⚠️ Tracked, not enforced | Every Claude call writes a `generations` row with `cost_cents`. Daily-cap enforcement gate added post-Monday. |
| **Renderer owns layout primitives** | ✅ Enforced | LLM picks `layout` enum; formatters own positions, fonts, sizes. Same rule for PDF. |

Three deferrals (RLS, no-stored-URLs, cost-cap enforcement), each with an explicit reason and a post-Monday remediation. No invariant is silently violated.

## Decisions locked

- **Storage for Monday:** Supabase Storage with signed URLs (7-day TTL). Google Drive / OneDrive deferred behind `StorageAdapter`.
- **Outputs:** `.pptx` + `.pdf`. DOCX deferred unless Senthil specifically requests on Monday.
- **Approval flow:** Summary first → APPROVE → files. (Approach A from brainstorming.)
- **Input modality:** WhatsApp text only. Voice / STT deferred.
- **WhatsApp provider:** Twilio sandbox only. Gupshup later.
- **Orchestration:** in-process Python `asyncio` task. No N8n, no LangFlow on the demo path. (LangFlow canvas still exists in the parked prototype, unused for the demo.)
- **Hosting:** Railway (per locked stack).
- **LLM (Monday only):** OpenAI `gpt-4o` for content generation, `gpt-4o-mini` only as the reply-parser tier-2 fallback. **Temporary deviation from the CLAUDE.md-locked Claude stack** — planned revert post-Monday. The pipeline's two LLM helpers are the only swap-back touchpoints.

## Demo day plan

**Sunday evening (2026-05-17):**
1. All Pre-flight blockers cleared (Twilio join, .env credentials populated, Supabase linked, Railway provisioned).
2. Full E2E dry-run from Muthukumar's phone against the deployed Railway service: new request → summary → APPROVE → files delivered → revision branch → second approval. Both files inspected on phone.
3. **Record a 30-second screen-grab of the happy path** (phone screen mirroring + the LangFlow-free architecture diagram from this spec, side-by-side). Saved to `prototype/demo/2026-05-17-dry-run.mp4`. Cheap insurance against Anthropic 503, Twilio sandbox hiccups, or Railway cold-start during the live demo Monday morning.
4. Stop touching the code after the dry-run passes. No "one more tweak."

**Monday morning, 30 min before demo:**
1. Run `uv run pytest -v` against the prototype directory — all green.
2. Send one warm-up message from the demo phone to wake up Railway (cold start kills the "3-second ack" criterion). Confirm ack arrives.
3. Confirm Anthropic balance / rate limit headroom via dashboard.
4. Pull the dry-run video onto the laptop in case live fails.

**During the demo:** narrate left-to-right what's happening on the WhatsApp screen and on the Supabase project rows / `generations` table in a separate browser tab. Senthil should be able to see one row appear per Claude call.

**Open questions to resolve with Senthil on Monday (post-demo discussion):**
1. **Demo phone for ongoing dev** — keep Muthukumar's, or rotate to Senthil's for ownership-handoff?
2. **7-day signed-URL TTL** — acceptable, or shorter?
3. **Post-Monday plan timing** — when do we write the spec for the hardening pass (RLS, Drive migration, cost-cap enforcement, voice STT, Gupshup)? Same week, or after BMAD-driven business-context exploration?

## Next steps after this spec

1. **User reviews this spec.** Make changes inline if requested.
2. **Invoke `superpowers:writing-plans`** to produce the task-by-task implementation plan (~12 tasks, each with files / tests / verification commands, in the same style as `docs/superpowers/plans/2026-05-13-wtsagnt-prototype.md`).
3. **Execute the plan via `superpowers:subagent-driven-development`** with human checkpoints at: webhook live, pipeline produces files locally, deployed to Railway, Twilio webhook pointed at Railway, full E2E smoke from real phone.
