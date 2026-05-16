# wtsagnt Prototype — Monday WhatsApp Slice

Local + Railway-deployable demo: teacher sends a WhatsApp text message →
multi-agent pipeline generates `.pptx` lesson deck (with MCQ slides) and a
`.pdf` ready-reckoner → bot replies with a summary → teacher replies
`APPROVE` → bot delivers signed Supabase Storage links to both files.
Revision branch supported: any non-APPROVE reply is treated as revision
instructions and triggers regeneration with a coherent-brief merger step.

**Spec:** [`../docs/superpowers/specs/2026-05-17-monday-whatsapp-slice-design.md`](../docs/superpowers/specs/2026-05-17-monday-whatsapp-slice-design.md)
**Plan:** [`../docs/superpowers/plans/2026-05-17-monday-whatsapp-slice.md`](../docs/superpowers/plans/2026-05-17-monday-whatsapp-slice.md)

## Stack

- Python 3.11+, [`uv`](https://docs.astral.sh/uv/) for deps
- FastAPI + Uvicorn (webhook)
- OpenAI (`gpt-4o` for content, `gpt-4o-mini` for tier-2 reply parsing) —
  **temporary deviation** from CLAUDE.md's Claude stack; planned revert
  post-Monday by editing only `src/pipeline.py`'s two `call_llm_*` helpers
- Twilio sandbox WhatsApp (Gupshup later, behind `WhatsAppAdapter` interface)
- Supabase Postgres + Storage (Google Drive / OneDrive later, behind
  `StorageAdapter` interface)
- `python-pptx` + `reportlab` for file rendering

## One-time setup

1. Install `uv` if you don't have it:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. Install Python deps:
   ```bash
   uv sync
   ```
3. Copy `.env.example` to `.env`, fill in real values for:
   - `OPENAI_API_KEY` (rotated key — don't reuse anything from chat scrollback)
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
     (sandbox number, e.g., `whatsapp:+14155238886`)
   - `SUPABASE_SECRET_KEY` (`sb_secret_...` or legacy service_role JWT)
   - `PUBLIC_BASE_URL` — your ngrok URL locally, Railway domain in prod
4. Apply the database migration (Path A or Path B):

   **Path A (CLI, needs DB password):**
   ```bash
   supabase login                                    # one-time
   supabase link --project-ref elczksydirrjuqapcpgq  # asks for DB password
   supabase db push
   ```

   **Path B (dashboard, no password needed):** open the Supabase SQL editor
   at https://app.supabase.com/project/elczksydirrjuqapcpgq/sql/new, paste
   the contents of `supabase/migrations/0001_monday_demo.sql`, click Run.

5. Join the Twilio sandbox from your phone:
   - Twilio Console → Messaging → Try it out → WhatsApp → Sandbox settings
   - Text the `join <code>` phrase shown there to the sandbox number
   - Until each demo phone is joined, it cannot send/receive from the sandbox

## Verify setup

```bash
uv run pytest -v
```

Expected: **53 passed, 3 skipped**. The 3 skipped are the smoke tests
(`test_smoke_openai.py`, `test_smoke_twilio.py`, `test_smoke_supabase.py`)
which skip automatically when their respective env vars are missing.

To actually run the smoke tests (with real credentials):

```bash
# Once .env is populated:
uv run pytest tests/test_smoke_openai.py -v
uv run pytest tests/test_smoke_supabase.py -v

# For Twilio smoke, set TWILIO_TEST_TO to a joined sandbox phone:
TWILIO_TEST_TO="whatsapp:+91XXXXXXXXXX" uv run pytest tests/test_smoke_twilio.py -v
```

## Run the demo locally

1. Start ngrok in one terminal:
   ```bash
   ngrok http 8000
   ```
   Copy the `https://<random>.ngrok-free.app` URL it prints.
2. Set `PUBLIC_BASE_URL=https://<that-random>.ngrok-free.app` in `.env`.
3. In Twilio Console → Sandbox settings → "WHEN A MESSAGE COMES IN":
   set to `https://<that-random>.ngrok-free.app/webhooks/whatsapp` (POST).
4. Start the server:
   ```bash
   uv run uvicorn src.server:app --host 127.0.0.1 --port 8000 --reload
   ```
5. From your joined sandbox phone, send a WhatsApp message:

   > 30-min lesson for grade 7 on photosynthesis. Cover the process,
   > inputs, outputs, where in the plant. 5 MCQs.

6. Expected:
   - "Got it. Generating your lesson…" arrives within 2 seconds
   - Summary arrives within ~120 seconds
   - Reply `APPROVE` → two messages with file links arrive within 5 seconds
   - Tapping each link downloads the file (signed Supabase Storage URL,
     7-day TTL)

7. To test revision: instead of `APPROVE`, reply with changes (e.g.,
   *"Make it grade 8 and add cellular respiration"*). The bot replies
   "Updating with your changes…" and regenerates.

## Deploy to Railway

1. `railway login` (one-time)
2. From this directory: `railway link` (create or select the project)
3. Set every env var from `.env.example` in the Railway dashboard with
   real values from your local `.env`. **Skip `PUBLIC_BASE_URL` initially.**
4. Deploy: `railway up` (or git push if a GitHub trigger is configured)
5. `railway domain` → note the public URL
6. Set `PUBLIC_BASE_URL` in Railway env vars to that domain → redeploy
7. Re-point Twilio's sandbox webhook to `https://<railway-domain>/webhooks/whatsapp`
8. Send a real message from the sandbox-joined phone → verify the full
   round trip works against Railway (cold start may add 5–10s on the first hit)

## Architecture in one paragraph

A POST hits `/webhooks/whatsapp` → FastAPI verifies the X-Twilio-Signature
(401 if bad) → dedupes inbound messages via the partial UNIQUE index on
`messages.provider_sid WHERE direction='inbound'` → branches on the latest
project's state for this phone (new request / awaiting_approval reply /
generating-in-progress) → returns TwiML inline as the HTTP response (no
separate Twilio API call for the ack) → schedules background work via
`asyncio.create_task`. The pipeline runs revision-merger (conditional) →
intent → 3 parallel content generators → 2 formatters (PPTX, PDF) →
parallel Supabase Storage uploads + signed-URL minting → CAS UPDATE the
project state from `generating` to `awaiting_approval` and sends the
summary via Twilio. Every state transition is compare-and-swap: the UPDATE
includes the expected current state in its WHERE clause, so racing
webhook handlers exit silently on rowcount=0 instead of duplicating work.
Every Claude/OpenAI call writes a `generations` row with input/output
tokens and approximate `cost_cents` for budget tracking.

## File layout

```
prototype/
├── src/
│   ├── schemas.py            # pydantic v2: Intent, SlideDeck, MCQList, Reckoner
│   ├── prompts.py            # 6 prompt templates (4 content + revision merger + reply parser)
│   ├── pptx_formatter.py     # render_pptx(slides, mcqs, output_path)
│   ├── pdf_formatter.py      # render_pdf(reckoner, output_path)
│   ├── settings.py           # pydantic-settings typed env access
│   ├── state.py              # project state machine + CAS operations + dedupe
│   ├── reply_parser.py       # 3-tier: regex → LLM tier-2 → never-auto-decide
│   ├── whatsapp_adapter.py   # WhatsAppAdapter Protocol + TwilioAdapter
│   ├── storage_adapter.py    # StorageAdapter Protocol + SupabaseStorageAdapter
│   ├── pipeline.py           # Pipeline class: revision merger + generate + handle_reply
│   └── server.py             # FastAPI app, /webhooks/whatsapp, /health
├── supabase/
│   ├── config.toml
│   └── migrations/
│       └── 0001_monday_demo.sql
├── tests/                    # 53 tests, 3 skip-on-missing-credentials smoke tests
├── samples/transcript.txt    # the photosynthesis demo prompt
├── pyproject.toml
├── .env.example              # placeholders for every required secret
└── README.md
```

## Troubleshooting

- **Pytest fails with `OPENAI_API_KEY` validation error** when running
  `Settings()` — `.env` has empty values. That's expected during development;
  the smoke tests have `pytest.mark.skipif` so they skip cleanly. If you
  hit this in app code, populate `.env` with real values.
- **Twilio webhook returns 401** — the X-Twilio-Signature check failed.
  Most common cause: `PUBLIC_BASE_URL` in `.env` doesn't exactly match the
  URL Twilio is calling. Verify the ngrok URL hasn't changed (free ngrok
  URLs rotate per session).
- **"needs repair" in Keynote** for the .pptx — the LLM produced a slide
  with an unsupported layout or malformed JSON. Check the most recent
  `generations` row in Supabase for the raw response; the prompt may need
  tightening, or the JSON-mode fallback (`_strip_json_fences`) may need
  to handle a new edge case.
- **Twilio sandbox phone "not joined"** — sandboxes auto-expire after 72h
  of inactivity. Send the `join <code>` SMS again from the demo phone.
