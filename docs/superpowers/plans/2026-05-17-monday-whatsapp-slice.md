# Monday WhatsApp Slice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a working WhatsApp-end-to-end demo by Monday 2026-05-18: teacher sends a text message to a Twilio WhatsApp sandbox number → multi-agent pipeline generates `.pptx` + `.pdf` → bot replies with a summary → teacher replies APPROVE → bot delivers signed Supabase Storage links. Includes a revision branch (teacher describes changes → regeneration with revision-merger pre-step).

**Architecture:** FastAPI service on Railway, in-process `asyncio` pipeline (no N8n, no LangFlow on the critical path), Supabase Postgres + Storage, OpenAI `gpt-4o` for content + revision merging + `gpt-4o-mini` only as the reply-parser tier-2 fallback. Adapter pattern for WhatsApp (Twilio today, Gupshup later) and Storage (Supabase today, Drive/OneDrive later). State machine with compare-and-swap UPDATEs to prevent webhook races.

**LLM provider note (temporary):** This plan ships OpenAI for the Monday-week demo as a tactical deviation from CLAUDE.md's locked Claude stack. Planned revert to `claude-sonnet-4-6` + `claude-haiku-4-5` post-demo. The pipeline's two LLM helpers (`call_llm_json`, `call_llm_text`) are the only swap-back touchpoints — see spec for rationale.

**Tech Stack:** Python 3.11+, `uv` for deps, FastAPI + Uvicorn, `openai` SDK (>=1.50), `twilio` SDK, `supabase` (supabase-py) SDK, `python-pptx`, `reportlab`, `pydantic` + `pydantic-settings`, `tenacity` (single retry on Twilio send), `pytest` + `pytest-asyncio` + `httpx` (for FastAPI TestClient).

**Spec:** [`docs/superpowers/specs/2026-05-17-monday-whatsapp-slice-design.md`](../specs/2026-05-17-monday-whatsapp-slice-design.md)

**Reuses (and supersedes) the LangFlow-focused tasks from:** [`docs/superpowers/plans/2026-05-13-wtsagnt-prototype.md`](2026-05-13-wtsagnt-prototype.md). Specifically: Tasks 2–5 (schemas, prompts, pptx_formatter, pdf_formatter) are imported verbatim. Tasks 6–11 of that plan (LangFlow canvas) are **not** on Monday's critical path — defer them.

---

## File Structure

All paths relative to `/Users/newuser/Projects/Personal/wtsagnt/`.

```
prototype/
├── pyproject.toml                    # uv project + expanded deps for FastAPI/Twilio/Supabase
├── .env.example                      # placeholders for every secret
├── .env                              # real secrets (gitignored)
├── .gitignore                        # outputs/, .env, .venv/, __pycache__/
├── README.md                         # how to run + deploy
├── samples/
│   └── transcript.txt                # sample teacher request (reused from existing plan)
├── supabase/
│   ├── config.toml                   # already created by `supabase init`
│   └── migrations/
│       └── 0001_monday_demo.sql      # projects + messages + generations + storage bucket
├── src/
│   ├── __init__.py
│   ├── schemas.py                    # REUSED: Intent, Slide, MCQ, Reckoner (pydantic v2)
│   ├── prompts.py                    # REUSED + 2 new: REVISION_MERGER, REPLY_PARSER_HAIKU
│   ├── pptx_formatter.py             # REUSED: render_pptx(slides, mcqs, output_path)
│   ├── pdf_formatter.py              # REUSED: render_pdf(reckoner, output_path)
│   ├── settings.py                   # NEW: pydantic-settings; typed access to .env
│   ├── state.py                      # NEW: project state machine + CAS via supabase-py
│   ├── reply_parser.py               # NEW: 3-tier reply parser (regex → Haiku → unclear)
│   ├── whatsapp_adapter.py           # NEW: WhatsAppAdapter Protocol + TwilioAdapter impl
│   ├── storage_adapter.py            # NEW: StorageAdapter Protocol + SupabaseStorageAdapter impl
│   ├── pipeline.py                   # NEW: revision merger + generate() + handle_reply()
│   └── server.py                     # NEW: FastAPI app, POST /webhooks/whatsapp
├── outputs/                          # gitignored; tmp files written here during runs
├── demo/                             # gitignored; Sunday-night dry-run video lands here
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # NEW: pytest fixtures (mocked adapters, fake supabase)
│   ├── test_smoke_openai.py          # NEW: confirms OPENAI_API_KEY works against gpt-4o
│   ├── test_smoke_twilio.py          # NEW: send a real message (skipped without env)
│   ├── test_smoke_supabase.py        # NEW: upload + signed URL (skipped without env)
│   ├── test_schemas.py               # REUSED
│   ├── test_pptx_formatter.py        # REUSED
│   ├── test_pdf_formatter.py         # REUSED
│   ├── test_reply_parser.py          # NEW
│   ├── test_twilio_signature.py      # NEW
│   ├── test_state.py                 # NEW: CAS semantics
│   ├── test_pipeline.py              # NEW: mocked adapters, sequence assertions
│   └── test_server.py                # NEW: FastAPI TestClient for the webhook
└── railway.toml                      # NEW: Railway build/start config (Task 15)
```

**Decomposition rationale:** business logic (formatters, schemas, prompts, parser) is plain Python and fully testable in pytest with no I/O. The adapters mock cleanly because they implement Protocols. The pipeline tests use mocked adapters to verify orchestration sequence, not the third-party SDKs. The server tests use FastAPI's TestClient and a fake Supabase client. Smoke tests are explicitly opt-in (skipped unless real credentials are set) so the unit suite stays fast.

---

## Pre-flight (do before Task 1)

These cannot be parallelized with code. **Owner: Muthukumar.**

- [ ] **Twilio sandbox phone join.** Twilio dashboard → Messaging → Try it out → WhatsApp. Note the sandbox number and the `join <code>` phrase. **Text that join phrase from the demo phone(s) to the sandbox number** — both Muthukumar's and Senthil's, if possible. Only joined phones can DM the sandbox.
- [ ] **OpenAI key** in hand (`sk-proj-...` or `sk-...`). **Note:** this is a temporary deviation from CLAUDE.md's locked Claude stack — see the plan header. The (rotated, new) key from the earlier chat-paste must replace the leaked one.
- [ ] **Twilio credentials:** Account SID + Auth Token from the Twilio Console.
- [ ] **Supabase secret key:** Project Settings → API → either the new "Secret keys" section (`sb_secret_...`) or the legacy `service_role` JWT (`eyJ...`).
- [ ] **Supabase database password** (set when project was created at app.supabase.com).
- [ ] **Railway account** logged in via `railway login` on the dev machine.

If any of these is missing at Task 7 (migration) or Task 15 (deploy) time, the plan stalls. Resolve them now.

---

## Task 1: Project scaffolding + dependencies + OpenAI API smoke test

**Files:**
- Create: `prototype/pyproject.toml`
- Create: `prototype/.env.example`
- Create: `prototype/.env` (real, gitignored)
- Create: `prototype/.gitignore`
- Create: `prototype/src/__init__.py`
- Create: `prototype/tests/__init__.py`
- Create: `prototype/tests/conftest.py`
- Create: `prototype/samples/.gitkeep`
- Create: `prototype/outputs/.gitkeep`
- Create: `prototype/demo/.gitkeep`
- Test: `prototype/tests/test_smoke_openai.py`

- [ ] **Step 1: Create the directory layout**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt
mkdir -p prototype/{src,tests,samples,outputs,demo,supabase/migrations}
touch prototype/src/__init__.py prototype/tests/__init__.py
touch prototype/samples/.gitkeep prototype/outputs/.gitkeep prototype/demo/.gitkeep
```

Expected: directories exist with empty `__init__.py` files. The `supabase/` dir already exists from the earlier `supabase init` call; the `migrations/` subdir is new.

- [ ] **Step 2: Write `pyproject.toml`**

Create `prototype/pyproject.toml`:

```toml
[project]
name = "wtsagnt-monday"
version = "0.1.0"
description = "wtsagnt Monday WhatsApp slice — text in, multi-agent, files out via signed URL"
requires-python = ">=3.11"
dependencies = [
    "openai>=1.50",
    "twilio>=9.0",
    "supabase>=2.7",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "python-pptx>=0.6.23",
    "reportlab>=4.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "python-dotenv>=1.0",
    "tenacity>=9.0",
    "httpx>=0.27",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "respx>=0.21",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
asyncio_mode = "auto"
```

- [ ] **Step 3: Write `.env.example` and `.gitignore`**

Create `prototype/.env.example`:

```
# OpenAI (temporary deviation from CLAUDE.md's Claude stack; planned revert post-Monday)
OPENAI_API_KEY=sk-proj-...
OPENAI_CONTENT_MODEL=gpt-4o
OPENAI_CLASSIFICATION_MODEL=gpt-4o-mini

# Twilio (sandbox for Monday, production credentials later)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_FROM=whatsapp:+14155238886

# Supabase
SUPABASE_URL=https://elczksydirrjuqapcpgq.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
SUPABASE_STORAGE_BUCKET=lesson-files

# Public webhook base (for signature verification + deploy)
# Locally: ngrok https URL. On Railway: the public service domain.
PUBLIC_BASE_URL=https://example.ngrok.app

# Signed-URL TTL in seconds (default 7 days)
SIGNED_URL_TTL_SECONDS=604800
```

Create `prototype/.gitignore`:

```
.env
.venv/
__pycache__/
*.pyc
outputs/
demo/
.pytest_cache/
*.log
```

- [ ] **Step 4: Install dependencies with uv**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv sync
```

Expected: `.venv/` created, ~70–100 packages installed in 60–120s.

If `uv` is not installed:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

- [ ] **Step 5: Populate `.env`**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
cp .env.example .env
```

Open `prototype/.env` in your editor and paste real values for every key listed in `.env.example`. Save.

Verify:

```bash
uv run python -c "from dotenv import load_dotenv; load_dotenv(); import os; \
print('openai:', bool(os.getenv('OPENAI_API_KEY'))); \
print('twilio:', bool(os.getenv('TWILIO_ACCOUNT_SID'))); \
print('supabase:', bool(os.getenv('SUPABASE_SECRET_KEY')))"
```

Expected: three `True` lines.

- [ ] **Step 6: Write a conftest with shared fixtures**

Create `prototype/tests/conftest.py`:

```python
"""Shared pytest fixtures: env loading, deterministic UUIDs, mocked adapters."""
from __future__ import annotations
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from dotenv import load_dotenv

# Load .env once for any smoke test that opts in.
load_dotenv()


@pytest.fixture
def fake_project_id() -> str:
    return str(uuid.UUID(int=0x1234))


@pytest.fixture
def mock_whatsapp_adapter() -> MagicMock:
    m = MagicMock()
    m.verify_signature = MagicMock(return_value=True)
    m.send_text = AsyncMock(return_value=MagicMock(sid="SM_outbound_test"))
    return m


@pytest.fixture
def mock_storage_adapter() -> MagicMock:
    m = MagicMock()
    m.upload = AsyncMock(return_value=None)
    m.signed_url = AsyncMock(return_value="https://example.test/signed-url")
    return m


@pytest.fixture
def mock_supabase() -> MagicMock:
    """Minimal supabase-py table-builder mock. Override per-test as needed."""
    client = MagicMock()
    builder = MagicMock()
    builder.insert = MagicMock(return_value=builder)
    builder.select = MagicMock(return_value=builder)
    builder.update = MagicMock(return_value=builder)
    builder.eq = MagicMock(return_value=builder)
    builder.order = MagicMock(return_value=builder)
    builder.limit = MagicMock(return_value=builder)
    builder.execute = MagicMock(return_value=MagicMock(data=[]))
    client.table = MagicMock(return_value=builder)
    return client
```

- [ ] **Step 7: Write the OpenAI smoke test**

Create `prototype/tests/test_smoke_openai.py`:

```python
"""Smoke test: confirm OPENAI_API_KEY works and gpt-4o responds."""
import os
import pytest


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
def test_openai_responds():
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=16,
        messages=[{"role": "user", "content": "Reply with exactly the word: ready"}],
    )
    text = response.choices[0].message.content.strip().lower()
    assert "ready" in text
```

- [ ] **Step 8: Run the smoke test**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv run pytest tests/test_smoke_openai.py -v
```

Expected: PASS. If 401 → key is wrong. If model-not-found → your account doesn't have access to `gpt-4o`; try `gpt-4o-2024-08-06` or `gpt-4-turbo` in `.env` (`OPENAI_CONTENT_MODEL=gpt-4o-2024-08-06`).

- [ ] **Step 9: Commit**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt
git add prototype/pyproject.toml prototype/.env.example prototype/.gitignore \
        prototype/src/__init__.py prototype/tests/__init__.py prototype/tests/conftest.py \
        prototype/tests/test_smoke_openai.py \
        prototype/samples/.gitkeep prototype/outputs/.gitkeep prototype/demo/.gitkeep
git commit -m "feat(prototype): Monday WhatsApp slice scaffolding + OpenAI smoke"
```

Expected: commit succeeds. `.env` is NOT staged (gitignored).

---

## Task 2: Schemas (reused verbatim from existing prototype plan)

**Files:**
- Create: `prototype/src/schemas.py`
- Test: `prototype/tests/test_schemas.py`

Execute **Task 2 of `docs/superpowers/plans/2026-05-13-wtsagnt-prototype.md`** verbatim. It produces:
- `src/schemas.py` with `Intent`, `Slide`, `SlideDeck`, `MCQ`, `MCQList`, `ReckonerSection`, `Reckoner` (pydantic v2 models)
- `tests/test_schemas.py` with 5 tests (all passing)

After running the existing-plan Task 2:

- [ ] **Step 1: Verify all schema tests pass**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv run pytest tests/test_schemas.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 2: Commit**

```bash
git add prototype/src/schemas.py prototype/tests/test_schemas.py
git commit -m "feat(prototype): pydantic schemas (Intent, SlideDeck, MCQList, Reckoner)"
```

---

## Task 3: Prompt templates (reused 4 + 2 new for revision merger and reply parser)

**Files:**
- Create: `prototype/src/prompts.py`
- Create: `prototype/samples/transcript.txt`

Execute **Task 2 Step 1 and Task 3 of `docs/superpowers/plans/2026-05-13-wtsagnt-prototype.md`** verbatim. They produce:
- `samples/transcript.txt` (the photosynthesis sample)
- `src/prompts.py` with `INTENT_AND_PROMPT_ENGINEERING`, `PPT_CONTENT_GENERATION`, `MCQ_GENERATION`, `RECKONER_GENERATION`

Then **append** two new prompt constants to `prototype/src/prompts.py`:

- [ ] **Step 1: Append `REVISION_MERGER` to `prompts.py`**

Open `prototype/src/prompts.py` and append at the end:

```python


REVISION_MERGER = """\
You are reconciling a teacher's request with revisions they sent later.

ORIGINAL REQUEST:
\"\"\"
{original_request}
\"\"\"

REVISIONS (in order, latest takes precedence on conflicts):
\"\"\"
{revisions_text}
\"\"\"

Produce a SINGLE coherent revised brief that incorporates the revisions into
the original. Resolve conflicts in favor of the latest revision.

Output requirements:
- Plain prose, the way a teacher would write it
- No JSON, no markdown, no preamble like "Here is..."
- The intent agent will consume your output as if it were the teacher's
  original request — make it readable as a standalone instruction
"""


REPLY_PARSER_HAIKU = """\
Classify a teacher's WhatsApp reply.

Context: the teacher received a summary of an auto-generated lesson and was
asked to either approve it (to receive the files) or describe changes they want.

Reply: \"\"\"{body}\"\"\"

Output EXACTLY one word, no punctuation, no explanation:
APPROVED | CHANGES | UNCLEAR

- APPROVED: the reply means yes / send the files
- CHANGES: the reply describes modifications to the lesson
- UNCLEAR: the reply is too short, contradictory, or off-topic to decide
"""
```

- [ ] **Step 2: Sanity-import to catch syntax errors**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv run python -c "from src.prompts import \
    INTENT_AND_PROMPT_ENGINEERING, PPT_CONTENT_GENERATION, MCQ_GENERATION, \
    RECKONER_GENERATION, REVISION_MERGER, REPLY_PARSER_HAIKU; \
print('all 6 prompts loaded, total chars:', sum(map(len, [INTENT_AND_PROMPT_ENGINEERING, PPT_CONTENT_GENERATION, MCQ_GENERATION, RECKONER_GENERATION, REVISION_MERGER, REPLY_PARSER_HAIKU])))"
```

Expected: `all 6 prompts loaded, total chars: <some-number-around-4000>`.

- [ ] **Step 3: Commit**

```bash
git add prototype/src/prompts.py prototype/samples/transcript.txt
git commit -m "feat(prototype): prompts (4 reused + revision merger + reply parser haiku)"
```

---

## Task 4: PPTX formatter (reused verbatim from existing prototype plan)

**Files:**
- Create: `prototype/src/pptx_formatter.py`
- Test: `prototype/tests/test_pptx_formatter.py`

Execute **Task 4 of `docs/superpowers/plans/2026-05-13-wtsagnt-prototype.md`** verbatim (Steps 1–4 only — skip Step 5's "eyeball" since we'll see real output via the pipeline later). It produces:
- `src/pptx_formatter.py` with `render_pptx(slides: list[dict], mcqs: list[dict], output_path: str) -> None`
- `tests/test_pptx_formatter.py` with 3 tests (all passing)

- [ ] **Step 1: Verify formatter tests pass**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv run pytest tests/test_pptx_formatter.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 2: Commit**

```bash
git add prototype/src/pptx_formatter.py prototype/tests/test_pptx_formatter.py
git commit -m "feat(prototype): pptx formatter (TDD, 4 layouts + MCQ slides)"
```

---

## Task 5: PDF formatter (reused verbatim from existing prototype plan)

**Files:**
- Create: `prototype/src/pdf_formatter.py`
- Test: `prototype/tests/test_pdf_formatter.py`

Execute **Task 5 of `docs/superpowers/plans/2026-05-13-wtsagnt-prototype.md`** verbatim (Steps 1–4). It produces:
- `src/pdf_formatter.py` with `render_pdf(reckoner: dict, output_path: str) -> None`
- `tests/test_pdf_formatter.py` with 2 tests (all passing)

- [ ] **Step 1: Verify formatter tests pass**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv run pytest tests/test_pdf_formatter.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 2: Run the full suite so far**

```bash
uv run pytest -v
```

Expected: 11 tests PASS (1 smoke + 5 schemas + 3 pptx + 2 pdf).

- [ ] **Step 3: Commit**

```bash
git add prototype/src/pdf_formatter.py prototype/tests/test_pdf_formatter.py
git commit -m "feat(prototype): pdf formatter (TDD, reckoner with headings on A4)"
```

---

## Task 6: Settings module (`src/settings.py`)

**Files:**
- Create: `prototype/src/settings.py`
- Test: `prototype/tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

Create `prototype/tests/test_settings.py`:

```python
"""Verify Settings loads from environment and exposes typed access."""
import os
from unittest.mock import patch

from src.settings import Settings


def test_settings_loads_required_fields():
    env = {
        "OPENAI_API_KEY": "sk-proj-test",
        "TWILIO_ACCOUNT_SID": "AC_test",
        "TWILIO_AUTH_TOKEN": "tok_test",
        "TWILIO_WHATSAPP_FROM": "whatsapp:+14155238886",
        "SUPABASE_URL": "https://elczksydirrjuqapcpgq.supabase.co",
        "SUPABASE_SECRET_KEY": "sb_secret_test",
        "SUPABASE_STORAGE_BUCKET": "lesson-files",
        "PUBLIC_BASE_URL": "https://example.test",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings()  # type: ignore[call-arg]
    assert s.openai_api_key == "sk-proj-test"
    assert s.twilio_account_sid == "AC_test"
    assert s.twilio_whatsapp_from == "whatsapp:+14155238886"
    assert s.supabase_url == "https://elczksydirrjuqapcpgq.supabase.co"
    assert s.supabase_storage_bucket == "lesson-files"
    assert s.public_base_url == "https://example.test"


def test_settings_defaults():
    env = {
        "OPENAI_API_KEY": "sk-proj-test",
        "TWILIO_ACCOUNT_SID": "AC_test",
        "TWILIO_AUTH_TOKEN": "tok_test",
        "TWILIO_WHATSAPP_FROM": "whatsapp:+14155238886",
        "SUPABASE_URL": "https://x.supabase.co",
        "SUPABASE_SECRET_KEY": "sb_secret_test",
        "PUBLIC_BASE_URL": "https://example.test",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings()  # type: ignore[call-arg]
    assert s.openai_content_model == "gpt-4o"
    assert s.openai_classification_model == "gpt-4o-mini"
    assert s.signed_url_ttl_seconds == 604800
    assert s.supabase_storage_bucket == "lesson-files"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_settings.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.settings'`.

- [ ] **Step 3: Write the settings module**

Create `prototype/src/settings.py`:

```python
"""Typed access to environment variables. Loaded once via pydantic-settings."""
from __future__ import annotations
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str
    openai_content_model: str = "gpt-4o"
    openai_classification_model: str = "gpt-4o-mini"

    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str

    supabase_url: str
    supabase_secret_key: str
    supabase_storage_bucket: str = "lesson-files"

    public_base_url: str
    signed_url_ttl_seconds: int = Field(default=604800)  # 7 days


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_settings.py -v
```

Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add prototype/src/settings.py prototype/tests/test_settings.py
git commit -m "feat(prototype): pydantic-settings Settings module"
```

---

## Task 7: Database migration (`supabase/migrations/0001_monday_demo.sql`)

**Files:**
- Create: `prototype/supabase/migrations/0001_monday_demo.sql`

This task creates the schema. **Two ways to apply it** — pick one based on whether you have the database password:

- **Path A (CLI, requires database password):** `supabase db push`
- **Path B (dashboard, no password needed):** copy the SQL into Supabase dashboard → SQL editor → Run

- [ ] **Step 1: Write the migration SQL**

Create `prototype/supabase/migrations/0001_monday_demo.sql`:

```sql
-- wtsagnt Monday WhatsApp slice — initial schema
-- Spec: docs/superpowers/specs/2026-05-17-monday-whatsapp-slice-design.md
-- RLS is intentionally OFF for the Monday single-phone demo. Hardening
-- pass post-Monday will scope to auth.uid() (or to phone via a sessions table).

create extension if not exists pgcrypto;

-- projects: one row per generation request
create table if not exists public.projects (
    id uuid primary key default gen_random_uuid(),
    phone text not null,
    original_request text not null,
    current_request text not null,
    state text not null default 'generating'
        check (state in ('generating','awaiting_approval','approved','delivered','error')),
    summary text,
    pptx_url text,
    pdf_url text,
    revision_count int not null default 0,
    error_reason text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists projects_phone_created_at_idx
    on public.projects (phone, created_at desc);

-- messages: every inbound and outbound WhatsApp message
create table if not exists public.messages (
    id uuid primary key default gen_random_uuid(),
    project_id uuid references public.projects(id) on delete set null,
    direction text not null check (direction in ('inbound','outbound')),
    provider_sid text,
    from_phone text not null,
    to_phone text not null,
    body text not null,
    created_at timestamptz not null default now()
);

-- partial UNIQUE on inbound provider_sid only — enforces webhook idempotency
-- without colliding with outbound SIDs returned by Twilio's send API
create unique index if not exists messages_inbound_provider_sid_unique
    on public.messages (provider_sid)
    where direction = 'inbound' and provider_sid is not null;

-- generations: every LLM API call (cost tracking + debugging)
create table if not exists public.generations (
    id uuid primary key default gen_random_uuid(),
    project_id uuid references public.projects(id) on delete cascade,
    step text not null check (step in (
        'revision_merge','intent','ppt_content','mcq','reckoner','reply_parse'
    )),
    model text not null,
    input_tokens int not null default 0,
    output_tokens int not null default 0,
    cost_cents int not null default 0,
    created_at timestamptz not null default now()
);

create index if not exists generations_project_id_idx
    on public.generations (project_id, created_at desc);

-- updated_at trigger on projects
create or replace function public.projects_set_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists projects_set_updated_at on public.projects;
create trigger projects_set_updated_at
    before update on public.projects
    for each row execute function public.projects_set_updated_at();

-- Storage bucket: 'lesson-files', private (signed URLs only)
insert into storage.buckets (id, name, public)
values ('lesson-files', 'lesson-files', false)
on conflict (id) do nothing;
```

- [ ] **Step 2: Apply the migration (pick A or B)**

**Path A — CLI:**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
supabase link --project-ref elczksydirrjuqapcpgq
# Enter your database password at the prompt
supabase db push
```

Expected output (path A): `Applying migration 0001_monday_demo.sql... Finished supabase db push.`

**Path B — dashboard:**

Open https://app.supabase.com/project/elczksydirrjuqapcpgq/sql/new → paste the contents of `0001_monday_demo.sql` → Run. You should see "Success. No rows returned." for each statement.

- [ ] **Step 3: Verify the schema is applied**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv run python -c "
from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv()
client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SECRET_KEY'])
for table in ('projects', 'messages', 'generations'):
    r = client.table(table).select('id').limit(1).execute()
    print(table, '→ OK (returned', len(r.data), 'rows)')
buckets = client.storage.list_buckets()
names = [b.name for b in buckets]
print('buckets:', names)
assert 'lesson-files' in names, 'lesson-files bucket missing'
print('all good')
"
```

Expected: three `→ OK` lines, `buckets: [...'lesson-files'...]`, `all good`.

- [ ] **Step 4: Run `get_advisors` to catch any obvious issues**

If you have the Supabase MCP connected to this project, run the `get_advisors` tool. Otherwise: dashboard → Advisors → Security/Performance, look at any RED items. **Expect** an RLS-disabled warning for the three tables — that's intentional for Monday and documented in the spec. Any other red warning needs investigation.

- [ ] **Step 5: Commit**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt
git add prototype/supabase/migrations/0001_monday_demo.sql
git commit -m "feat(prototype): supabase migration — projects/messages/generations + lesson-files bucket"
```

---

## Task 8: State module (`src/state.py`) — TDD with mocked supabase-py

**Files:**
- Create: `prototype/src/state.py`
- Test: `prototype/tests/test_state.py`

- [ ] **Step 1: Write the failing tests**

Create `prototype/tests/test_state.py`:

```python
"""TDD for state machine + CAS operations against supabase-py."""
from unittest.mock import MagicMock

import pytest

from src.state import (
    create_project,
    latest_project_for_phone,
    insert_inbound_message,
    insert_outbound_message,
    cas_to_generating_for_revision,
    cas_to_awaiting_approval,
    cas_to_approved,
    cas_to_delivered,
    cas_to_error,
)


def _builder_returning(data):
    b = MagicMock()
    b.insert = MagicMock(return_value=b)
    b.select = MagicMock(return_value=b)
    b.update = MagicMock(return_value=b)
    b.eq = MagicMock(return_value=b)
    b.order = MagicMock(return_value=b)
    b.limit = MagicMock(return_value=b)
    b.execute = MagicMock(return_value=MagicMock(data=data))
    return b


def test_create_project_returns_row(mock_supabase):
    mock_supabase.table.return_value = _builder_returning(
        [{"id": "p-1", "phone": "whatsapp:+91...", "state": "generating",
          "original_request": "x", "current_request": "x", "revision_count": 0}]
    )
    p = create_project(mock_supabase, "whatsapp:+91...", "x")
    assert p["id"] == "p-1"
    assert p["state"] == "generating"


def test_latest_project_for_phone_returns_none_when_empty(mock_supabase):
    mock_supabase.table.return_value = _builder_returning([])
    p = latest_project_for_phone(mock_supabase, "whatsapp:+91...")
    assert p is None


def test_insert_inbound_message_dedupes_on_unique_conflict(mock_supabase):
    # Simulate supabase-py raising on UNIQUE conflict (the partial index)
    from postgrest.exceptions import APIError
    b = _builder_returning([])
    b.execute = MagicMock(side_effect=APIError({"code": "23505", "message": "dup"}))
    mock_supabase.table.return_value = b

    ok = insert_inbound_message(
        mock_supabase, project_id=None, provider_sid="SMdup",
        from_phone="whatsapp:+91...", to_phone="whatsapp:+1415...", body="hi",
    )
    assert ok is False  # dedupe path


def test_insert_inbound_message_succeeds_on_new(mock_supabase):
    mock_supabase.table.return_value = _builder_returning(
        [{"id": "m-1", "provider_sid": "SMnew"}]
    )
    ok = insert_inbound_message(
        mock_supabase, project_id=None, provider_sid="SMnew",
        from_phone="whatsapp:+91...", to_phone="whatsapp:+1415...", body="hi",
    )
    assert ok is True


def test_cas_to_approved_succeeds_when_state_matches(mock_supabase):
    mock_supabase.table.return_value = _builder_returning([{"id": "p-1", "state": "approved"}])
    won = cas_to_approved(mock_supabase, "p-1")
    assert won is True


def test_cas_to_approved_loses_race(mock_supabase):
    mock_supabase.table.return_value = _builder_returning([])  # no rows updated
    won = cas_to_approved(mock_supabase, "p-1")
    assert won is False


def test_cas_to_generating_for_revision_appends_request(mock_supabase):
    # We rely on the SQL appending via Postgres expression; here we just
    # check the function returns True/False based on rows-affected.
    mock_supabase.table.return_value = _builder_returning([{"id": "p-1", "state": "generating"}])
    won = cas_to_generating_for_revision(mock_supabase, "p-1", "make it grade 8")
    assert won is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_state.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.state'`.

- [ ] **Step 3: Implement the state module**

Create `prototype/src/state.py`:

```python
"""Project state machine + CAS operations against supabase-py.

All state transitions use compare-and-swap: the UPDATE includes the expected
current state in the WHERE clause. If 0 rows return, another handler already
advanced the state; the caller exits silently. This eliminates duplicate
work under webhook races (double-tap APPROVE, race with revision arrival).
"""
from __future__ import annotations
from typing import Any, Optional

from postgrest.exceptions import APIError


def create_project(client, phone: str, body: str) -> dict:
    """Insert a brand-new projects row in state='generating'. Returns the row."""
    r = (
        client.table("projects")
        .insert({
            "phone": phone,
            "original_request": body,
            "current_request": body,
            "state": "generating",
            "revision_count": 0,
        })
        .execute()
    )
    return r.data[0]


def latest_project_for_phone(client, phone: str) -> Optional[dict]:
    """Return the most recent project for this phone, or None."""
    r = (
        client.table("projects")
        .select("*")
        .eq("phone", phone)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return r.data[0] if r.data else None


def get_project(client, project_id: str) -> Optional[dict]:
    r = client.table("projects").select("*").eq("id", project_id).limit(1).execute()
    return r.data[0] if r.data else None


def insert_inbound_message(
    client,
    *,
    project_id: Optional[str],
    provider_sid: str,
    from_phone: str,
    to_phone: str,
    body: str,
) -> bool:
    """Insert an inbound message. Returns False if the partial-UNIQUE index
    rejects it (duplicate webhook). True on successful insert."""
    payload = {
        "project_id": project_id,
        "direction": "inbound",
        "provider_sid": provider_sid,
        "from_phone": from_phone,
        "to_phone": to_phone,
        "body": body,
    }
    try:
        client.table("messages").insert(payload).execute()
        return True
    except APIError as exc:
        # 23505 = unique_violation in Postgres
        if str(getattr(exc, "code", "")) == "23505" or "23505" in str(exc):
            return False
        raise


def insert_outbound_message(
    client,
    *,
    project_id: Optional[str],
    provider_sid: Optional[str],
    from_phone: str,
    to_phone: str,
    body: str,
) -> None:
    client.table("messages").insert({
        "project_id": project_id,
        "direction": "outbound",
        "provider_sid": provider_sid,
        "from_phone": from_phone,
        "to_phone": to_phone,
        "body": body,
    }).execute()


def _cas(client, project_id: str, expected: str, updates: dict[str, Any]) -> bool:
    """Conditional UPDATE. Returns True iff the update affected exactly the
    target row (i.e., the project was in the expected state)."""
    r = (
        client.table("projects")
        .update(updates)
        .eq("id", project_id)
        .eq("state", expected)
        .execute()
    )
    return bool(r.data)


def cas_to_awaiting_approval(
    client, project_id: str, *, summary: str, pptx_url: str, pdf_url: str
) -> bool:
    return _cas(client, project_id, expected="generating", updates={
        "state": "awaiting_approval",
        "summary": summary,
        "pptx_url": pptx_url,
        "pdf_url": pdf_url,
    })


def cas_to_approved(client, project_id: str) -> bool:
    return _cas(client, project_id, expected="awaiting_approval",
                updates={"state": "approved"})


def cas_to_delivered(client, project_id: str) -> bool:
    return _cas(client, project_id, expected="approved",
                updates={"state": "delivered"})


def cas_to_generating_for_revision(client, project_id: str, revision_body: str) -> bool:
    """Append the revision to current_request and bump revision_count, only
    if we're still in awaiting_approval. supabase-py's table-builder doesn't
    expose SQL expressions, so we read-modify-write within a single CAS update."""
    project = get_project(client, project_id)
    if project is None or project["state"] != "awaiting_approval":
        return False
    n = (project.get("revision_count") or 0) + 1
    new_request = (
        (project.get("current_request") or "")
        + f"\n\nRevision {n}: {revision_body}"
    )
    return _cas(client, project_id, expected="awaiting_approval", updates={
        "state": "generating",
        "current_request": new_request,
        "revision_count": n,
    })


def cas_to_error(client, project_id: str, *, error_reason: str,
                 expected_states: tuple[str, ...] = ("generating",)) -> bool:
    """Set state=error from any of expected_states. Returns True on a win."""
    for st in expected_states:
        if _cas(client, project_id, expected=st, updates={
            "state": "error",
            "error_reason": error_reason,
        }):
            return True
    return False


def insert_generation(
    client,
    *,
    project_id: str,
    step: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost_cents: int,
) -> None:
    client.table("generations").insert({
        "project_id": project_id,
        "step": step,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_cents": cost_cents,
    }).execute()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_state.py -v
```

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add prototype/src/state.py prototype/tests/test_state.py
git commit -m "feat(prototype): state module — CAS transitions + dedupe-via-unique-index"
```

---

## Task 9: Reply parser (`src/reply_parser.py`) — TDD

**Files:**
- Create: `prototype/src/reply_parser.py`
- Test: `prototype/tests/test_reply_parser.py`

- [ ] **Step 1: Write the failing tests**

Create `prototype/tests/test_reply_parser.py`:

```python
"""TDD for the 3-tier reply parser: regex → Haiku → unclear (no auto-decide)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.reply_parser import parse_reply, ReplyOutcome


# --- Tier 1: regex hits (no Haiku call) ---

@pytest.mark.parametrize("body", [
    "APPROVE", "approve", "yes", "OK", "ok.", "okay",
    "👍", "✅", "send", "share", "go", "done", "all good", "looks good",
])
async def test_tier1_approval_keywords(body):
    haiku = AsyncMock()
    outcome = await parse_reply(body, classify=haiku)
    assert outcome == ReplyOutcome.APPROVED
    haiku.assert_not_called()


async def test_tier1_long_body_is_changes_requested():
    haiku = AsyncMock()
    outcome = await parse_reply(
        "Please change the topic to cellular respiration and target grade 8 instead",
        classify=haiku,
    )
    assert outcome == ReplyOutcome.CHANGES_REQUESTED
    haiku.assert_not_called()


# --- Tier 2: Haiku fallback ---

async def test_tier2_haiku_returns_approved():
    haiku = AsyncMock(return_value="APPROVED")
    outcome = await parse_reply("sure thing", classify=haiku)
    assert outcome == ReplyOutcome.APPROVED
    haiku.assert_awaited_once()


async def test_tier2_haiku_returns_changes():
    haiku = AsyncMock(return_value="CHANGES")
    outcome = await parse_reply("hmm switch it up", classify=haiku)
    assert outcome == ReplyOutcome.CHANGES_REQUESTED


async def test_tier2_haiku_returns_unclear():
    haiku = AsyncMock(return_value="UNCLEAR")
    outcome = await parse_reply("???", classify=haiku)
    assert outcome == ReplyOutcome.UNCLEAR


async def test_tier3_malformed_haiku_output_is_unclear():
    haiku = AsyncMock(return_value="MAYBE or something else")
    outcome = await parse_reply("idk", classify=haiku)
    assert outcome == ReplyOutcome.UNCLEAR
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_reply_parser.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.reply_parser'`.

- [ ] **Step 3: Implement the parser**

Create `prototype/src/reply_parser.py`:

```python
"""Three-tier reply parser. Compliance with CLAUDE.md invariant:
regex first → Haiku only on ambiguity → never auto-decide ambiguous replies."""
from __future__ import annotations
import enum
import re
from typing import Awaitable, Callable


class ReplyOutcome(str, enum.Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    UNCLEAR = "unclear"


_APPROVAL_RE = re.compile(
    r"^\s*(approve|approved|yes|ok|okay|👍|✅|send|share|go|done|"
    r"all good|looks good)\s*[.!]?\s*$",
    re.IGNORECASE,
)

_CHANGES_MIN_LEN = 30  # chars; longer than this with no approval keyword → revision


async def parse_reply(
    body: str,
    *,
    classify: Callable[[str], Awaitable[str]],
) -> ReplyOutcome:
    """Classify a teacher's WhatsApp reply.

    `classify` is the Haiku tier-2 callback: takes the reply text, returns
    one of 'APPROVED' | 'CHANGES' | 'UNCLEAR'. Only called when tier 1 fails.
    """
    body = body.strip()
    if _APPROVAL_RE.match(body):
        return ReplyOutcome.APPROVED
    if len(body) >= _CHANGES_MIN_LEN:
        return ReplyOutcome.CHANGES_REQUESTED
    # Ambiguous: short reply without an approval keyword.
    raw = (await classify(body)).strip().upper()
    if raw == "APPROVED":
        return ReplyOutcome.APPROVED
    if raw == "CHANGES":
        return ReplyOutcome.CHANGES_REQUESTED
    return ReplyOutcome.UNCLEAR
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_reply_parser.py -v
```

Expected: all parametrize + 5 non-parametrize tests PASS.

- [ ] **Step 5: Commit**

```bash
git add prototype/src/reply_parser.py prototype/tests/test_reply_parser.py
git commit -m "feat(prototype): 3-tier reply parser (regex → Haiku → unclear)"
```

---

## Task 10: WhatsApp adapter (`src/whatsapp_adapter.py`) — TDD

**Files:**
- Create: `prototype/src/whatsapp_adapter.py`
- Test: `prototype/tests/test_twilio_signature.py`
- Test: `prototype/tests/test_smoke_twilio.py`

- [ ] **Step 1: Write the signature-verification test**

Create `prototype/tests/test_twilio_signature.py`:

```python
"""Verify TwilioAdapter.verify_signature against Twilio's documented behavior.

Twilio computes HMAC-SHA1 over (URL + concatenated sorted form pairs),
base64-encoded. We use twilio's own RequestValidator to compute a known-good
signature, then assert our adapter accepts it and rejects tampered ones."""
import os

import pytest
from twilio.request_validator import RequestValidator

from src.whatsapp_adapter import TwilioAdapter


AUTH_TOKEN = "12345"  # test-only; doesn't need to match a real account
URL = "https://example.test/webhooks/whatsapp"
PARAMS = {
    "AccountSid": "AC_fake",
    "From": "whatsapp:+919876543210",
    "To": "whatsapp:+14155238886",
    "Body": "30-min lesson grade 7 photosynthesis",
    "MessageSid": "SM_test_inbound",
}


def _real_signature(token: str, url: str, params: dict) -> str:
    return RequestValidator(token).compute_signature(url, params)


def test_verify_signature_accepts_valid():
    adapter = TwilioAdapter(account_sid="AC_fake", auth_token=AUTH_TOKEN,
                            whatsapp_from="whatsapp:+14155238886")
    sig = _real_signature(AUTH_TOKEN, URL, PARAMS)
    assert adapter.verify_signature(url=URL, signature=sig, form=PARAMS) is True


def test_verify_signature_rejects_tampered_body():
    adapter = TwilioAdapter(account_sid="AC_fake", auth_token=AUTH_TOKEN,
                            whatsapp_from="whatsapp:+14155238886")
    sig = _real_signature(AUTH_TOKEN, URL, PARAMS)
    tampered = {**PARAMS, "Body": "totally different body"}
    assert adapter.verify_signature(url=URL, signature=sig, form=tampered) is False


def test_verify_signature_rejects_wrong_token():
    wrong_token_adapter = TwilioAdapter(account_sid="AC_fake",
                                        auth_token="WRONG", whatsapp_from="whatsapp:+1...")
    sig = _real_signature(AUTH_TOKEN, URL, PARAMS)
    assert wrong_token_adapter.verify_signature(url=URL, signature=sig, form=PARAMS) is False


def test_verify_signature_rejects_missing_signature():
    adapter = TwilioAdapter(account_sid="AC_fake", auth_token=AUTH_TOKEN,
                            whatsapp_from="whatsapp:+1...")
    assert adapter.verify_signature(url=URL, signature="", form=PARAMS) is False
```

Create `prototype/tests/test_smoke_twilio.py`:

```python
"""Smoke test: real Twilio send to the dev phone. Skipped without env vars."""
import os
import pytest


REQUIRED = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM",
            "TWILIO_TEST_TO")  # TWILIO_TEST_TO must be a joined sandbox phone


@pytest.mark.skipif(
    any(not os.getenv(k) for k in REQUIRED),
    reason="Twilio env not set (set TWILIO_TEST_TO to a joined sandbox phone)",
)
async def test_twilio_send_real():
    from src.whatsapp_adapter import TwilioAdapter
    adapter = TwilioAdapter(
        account_sid=os.environ["TWILIO_ACCOUNT_SID"],
        auth_token=os.environ["TWILIO_AUTH_TOKEN"],
        whatsapp_from=os.environ["TWILIO_WHATSAPP_FROM"],
    )
    result = await adapter.send_text(
        to=os.environ["TWILIO_TEST_TO"],
        body="wtsagnt smoke test — please ignore",
    )
    assert result.sid.startswith(("SM", "MM"))
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_twilio_signature.py -v
```

Expected: 4 FAIL with `ModuleNotFoundError: No module named 'src.whatsapp_adapter'`.

- [ ] **Step 3: Implement the adapter**

Create `prototype/src/whatsapp_adapter.py`:

```python
"""WhatsApp adapter — Twilio sandbox implementation for Monday.

Designed to be swapped for a Gupshup adapter post-Monday without touching
callers. Callers depend only on the Protocol below."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from twilio.request_validator import RequestValidator
from twilio.rest import Client as TwilioClient


@dataclass
class SendResult:
    sid: str


@runtime_checkable
class WhatsAppAdapter(Protocol):
    def verify_signature(self, *, url: str, signature: str, form: dict) -> bool: ...
    async def send_text(self, *, to: str, body: str) -> SendResult: ...


class TwilioAdapter:
    """Twilio sandbox WhatsApp adapter. Thread-safe; the underlying TwilioClient
    is HTTP-based and stateless aside from credentials."""

    def __init__(self, *, account_sid: str, auth_token: str, whatsapp_from: str) -> None:
        self._client = TwilioClient(account_sid, auth_token)
        self._validator = RequestValidator(auth_token)
        self._from = whatsapp_from

    def verify_signature(self, *, url: str, signature: str, form: dict) -> bool:
        if not signature:
            return False
        return self._validator.validate(url, form, signature)

    async def send_text(self, *, to: str, body: str) -> SendResult:
        # twilio-python is sync; bounce to a thread so we don't block the loop
        loop = asyncio.get_running_loop()
        msg = await loop.run_in_executor(
            None,
            lambda: self._client.messages.create(from_=self._from, to=to, body=body),
        )
        return SendResult(sid=msg.sid)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_twilio_signature.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: (Optional) Run the real Twilio smoke**

If your `TWILIO_TEST_TO` env var is set to a joined sandbox phone:

```bash
TWILIO_TEST_TO="whatsapp:+91XXXXXXXXXX" uv run pytest tests/test_smoke_twilio.py -v
```

Expected: PASS, and a "wtsagnt smoke test" message arrives on that phone.

- [ ] **Step 6: Commit**

```bash
git add prototype/src/whatsapp_adapter.py \
        prototype/tests/test_twilio_signature.py prototype/tests/test_smoke_twilio.py
git commit -m "feat(prototype): TwilioAdapter — verify_signature + async send_text"
```

---

## Task 11: Supabase Storage adapter (`src/storage_adapter.py`) — TDD

**Files:**
- Create: `prototype/src/storage_adapter.py`
- Test: `prototype/tests/test_smoke_supabase.py`

(No pure unit test for the adapter — its surface is "call the SDK and unwrap"; behavior tests are smoke tests against a real bucket. The unit testing happens at the pipeline layer where this adapter is mocked.)

- [ ] **Step 1: Write the smoke test**

Create `prototype/tests/test_smoke_supabase.py`:

```python
"""Smoke test: upload and signed-URL a small blob to the lesson-files bucket.
Skipped without Supabase env vars."""
import os
import uuid

import httpx
import pytest


REQUIRED = ("SUPABASE_URL", "SUPABASE_SECRET_KEY", "SUPABASE_STORAGE_BUCKET")


@pytest.mark.skipif(
    any(not os.getenv(k) for k in REQUIRED),
    reason="Supabase env not set",
)
async def test_upload_and_signed_url_roundtrip():
    from src.storage_adapter import SupabaseStorageAdapter
    from supabase import create_client

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
    adapter = SupabaseStorageAdapter(client=client)

    bucket = os.environ["SUPABASE_STORAGE_BUCKET"]
    path = f"smoke/{uuid.uuid4()}.txt"
    content = b"wtsagnt storage smoke"

    await adapter.upload(bucket=bucket, path=path, content=content, content_type="text/plain")
    url = await adapter.signed_url(bucket=bucket, path=path, expires_in_seconds=60)

    async with httpx.AsyncClient() as http:
        r = await http.get(url)
    assert r.status_code == 200
    assert r.content == content
```

- [ ] **Step 2: Implement the adapter**

Create `prototype/src/storage_adapter.py`:

```python
"""Storage adapter — Supabase Storage for Monday. Google Drive / OneDrive
implementations land later behind the same Protocol."""
from __future__ import annotations
import asyncio
from typing import Protocol, runtime_checkable


@runtime_checkable
class StorageAdapter(Protocol):
    async def upload(self, *, bucket: str, path: str, content: bytes, content_type: str) -> None: ...
    async def signed_url(self, *, bucket: str, path: str, expires_in_seconds: int) -> str: ...


class SupabaseStorageAdapter:
    """Wraps supabase-py's storage client. The underlying SDK is sync (httpx-based
    internally); we hop to a thread so we don't block the event loop."""

    def __init__(self, *, client) -> None:
        self._client = client

    async def upload(self, *, bucket: str, path: str, content: bytes, content_type: str) -> None:
        def _do() -> None:
            self._client.storage.from_(bucket).upload(
                path=path,
                file=content,
                file_options={"content-type": content_type, "upsert": "true"},
            )
        await asyncio.get_running_loop().run_in_executor(None, _do)

    async def signed_url(self, *, bucket: str, path: str, expires_in_seconds: int) -> str:
        def _do() -> str:
            r = self._client.storage.from_(bucket).create_signed_url(path, expires_in_seconds)
            # supabase-py returns {'signedURL': '...', 'signedUrl': '...'} depending on version
            return r.get("signedURL") or r.get("signedUrl") or r["signed_url"]
        return await asyncio.get_running_loop().run_in_executor(None, _do)
```

- [ ] **Step 3: Run the smoke test**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv run pytest tests/test_smoke_supabase.py -v
```

Expected: PASS. Confirms the upload roundtrips through a signed URL.

- [ ] **Step 4: Commit**

```bash
git add prototype/src/storage_adapter.py prototype/tests/test_smoke_supabase.py
git commit -m "feat(prototype): SupabaseStorageAdapter — async upload + signed URL"
```

---

## Task 12: Pipeline (`src/pipeline.py`) — TDD with mocked adapters

**Files:**
- Create: `prototype/src/pipeline.py`
- Test: `prototype/tests/test_pipeline.py`

This is the largest module. It contains:
- `merge_revisions(coherent brief)` — pre-step (`gpt-4o`) when `revision_count > 0`
- `generate(project_id)` — full generation pipeline
- `handle_reply(project_id, body)` — approve / changes / unclear branching
- A `Pipeline` class that holds all the dependencies (OpenAI client, adapters, supabase client, settings)

**LLM-provider-agnostic naming:** The two LLM call helpers are named `call_llm_json` and `call_llm_text` (not `call_openai_*`). This keeps the swap-back to Anthropic cheap — only the helper bodies need to change.

- [ ] **Step 1: Write the failing tests**

Create `prototype/tests/test_pipeline.py`:

```python
"""TDD for the orchestration pipeline. Adapters and the LLM client are mocked;
we assert call sequence and state transitions."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pipeline import Pipeline


def _fake_intent_response():
    return {
        "subject": "Science",
        "grade": "7",
        "topic": "Photosynthesis",
        "duration_min": 30,
        "n_slides": 10,
        "n_mcqs": 5,
        "ppt_prompt": "make a deck",
        "mcq_prompt": "make 5 mcqs",
        "reckoner_prompt": "make a reckoner",
    }


def _fake_slides_response():
    return {"slides": [
        {"layout": "title", "title": "Photosynthesis", "subtitle": "Grade 7"},
        {"layout": "bullets", "title": "Inputs", "bullets": ["Sunlight", "CO2", "H2O"]},
    ]}


def _fake_mcqs_response():
    return {"mcqs": [
        {"question": "What gas?", "options": ["O2", "CO2", "N2", "H2"],
         "answer": "B", "explanation": "Plants absorb CO2."},
    ]}


def _fake_reckoner_response():
    return {"title": "Photosynthesis", "sections": [
        {"heading": "What", "body": "Process plants use to make food."},
    ]}


@pytest.fixture
def pipeline(mock_whatsapp_adapter, mock_storage_adapter, mock_supabase):
    """Build a Pipeline with all dependencies mocked."""
    llm = MagicMock()
    # Per-test we replace pipeline.call_llm_json / call_llm_text with AsyncMocks
    settings = MagicMock()
    settings.openai_content_model = "gpt-4o"
    settings.openai_classification_model = "gpt-4o-mini"
    settings.supabase_storage_bucket = "lesson-files"
    settings.signed_url_ttl_seconds = 604800
    settings.twilio_whatsapp_from = "whatsapp:+14155238886"

    p = Pipeline(
        llm=llm,
        whatsapp=mock_whatsapp_adapter,
        storage=mock_storage_adapter,
        supabase=mock_supabase,
        settings=settings,
    )
    return p


async def test_generate_first_run_skips_revision_merger(pipeline, fake_project_id):
    """When revision_count == 0, the revision merger is NOT called."""
    pipeline.call_llm_json = AsyncMock(side_effect=[
        _fake_intent_response(),
        _fake_slides_response(),
        _fake_mcqs_response(),
        _fake_reckoner_response(),
    ])
    pipeline.call_llm_text = AsyncMock()  # should not be called
    # Project state: revision_count == 0
    pipeline.supabase.table().select().eq().limit().execute.return_value = MagicMock(
        data=[{"id": fake_project_id, "phone": "whatsapp:+91...",
               "original_request": "x", "current_request": "x",
               "state": "generating", "revision_count": 0}]
    )
    # CAS to awaiting_approval succeeds
    pipeline.supabase.table().update().eq().eq().execute.return_value = MagicMock(
        data=[{"id": fake_project_id}]
    )

    await pipeline.generate(fake_project_id)

    # No text-mode call (the merger would use call_llm_text)
    pipeline.call_llm_text.assert_not_called()
    # Four JSON-mode calls (intent + 3 generators)
    assert pipeline.call_llm_json.await_count == 4


async def test_generate_with_revisions_calls_merger_first(pipeline, fake_project_id):
    """When revision_count > 0, the revision merger runs as step 0."""
    pipeline.call_llm_text = AsyncMock(return_value="A coherent merged brief.")
    pipeline.call_llm_json = AsyncMock(side_effect=[
        _fake_intent_response(),
        _fake_slides_response(),
        _fake_mcqs_response(),
        _fake_reckoner_response(),
    ])
    pipeline.supabase.table().select().eq().limit().execute.return_value = MagicMock(
        data=[{"id": fake_project_id, "phone": "whatsapp:+91...",
               "original_request": "x", "current_request": "x\n\nRevision 1: grade 8",
               "state": "generating", "revision_count": 1}]
    )
    pipeline.supabase.table().update().eq().eq().execute.return_value = MagicMock(
        data=[{"id": fake_project_id}]
    )

    await pipeline.generate(fake_project_id)

    pipeline.call_llm_text.assert_awaited_once()  # the merger
    assert pipeline.call_llm_json.await_count == 4


async def test_generate_cas_loss_skips_send(pipeline, fake_project_id):
    """If CAS to awaiting_approval returns 0 rows, we don't send the summary."""
    pipeline.call_llm_json = AsyncMock(side_effect=[
        _fake_intent_response(),
        _fake_slides_response(),
        _fake_mcqs_response(),
        _fake_reckoner_response(),
    ])
    pipeline.supabase.table().select().eq().limit().execute.return_value = MagicMock(
        data=[{"id": fake_project_id, "phone": "whatsapp:+91...",
               "original_request": "x", "current_request": "x",
               "state": "generating", "revision_count": 0}]
    )
    # CAS returns empty data (lost race)
    pipeline.supabase.table().update().eq().eq().execute.return_value = MagicMock(data=[])

    await pipeline.generate(fake_project_id)

    pipeline.whatsapp.send_text.assert_not_called()


async def test_handle_reply_approved_sends_two_files(pipeline, fake_project_id):
    pipeline.supabase.table().select().eq().limit().execute.return_value = MagicMock(
        data=[{"id": fake_project_id, "phone": "whatsapp:+91...",
               "state": "awaiting_approval",
               "pptx_url": "https://x.test/pptx",
               "pdf_url": "https://x.test/pdf"}]
    )
    pipeline.supabase.table().update().eq().eq().execute.return_value = MagicMock(
        data=[{"id": fake_project_id}]
    )

    await pipeline.handle_reply(fake_project_id, "APPROVE")

    # Two send_text calls — one per file URL
    assert pipeline.whatsapp.send_text.await_count == 2


async def test_handle_reply_changes_restarts_generation(pipeline, fake_project_id):
    # State machine: awaiting_approval → generating (CAS succeeds)
    pipeline.supabase.table().select().eq().limit().execute.return_value = MagicMock(
        data=[{"id": fake_project_id, "phone": "whatsapp:+91...",
               "state": "awaiting_approval",
               "current_request": "x", "revision_count": 0}]
    )
    pipeline.supabase.table().update().eq().eq().execute.return_value = MagicMock(
        data=[{"id": fake_project_id}]
    )
    pipeline.generate = AsyncMock()

    await pipeline.handle_reply(
        fake_project_id,
        "Please change to grade 8 and add cellular respiration coverage",
    )

    pipeline.generate.assert_awaited_once_with(fake_project_id)
    # Acked the revision
    pipeline.whatsapp.send_text.assert_awaited()


async def test_handle_reply_unclear_asks_clarification(pipeline, fake_project_id):
    pipeline.supabase.table().select().eq().limit().execute.return_value = MagicMock(
        data=[{"id": fake_project_id, "phone": "whatsapp:+91...", "state": "awaiting_approval"}]
    )
    # Mock tier-2 LLM to return UNCLEAR
    pipeline.call_llm_text = AsyncMock(return_value="UNCLEAR")

    await pipeline.handle_reply(fake_project_id, "???")

    pipeline.whatsapp.send_text.assert_awaited()
    args, kwargs = pipeline.whatsapp.send_text.call_args
    assert "APPROVE" in kwargs["body"] or "approve" in kwargs["body"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_pipeline.py -v
```

Expected: 6 FAIL with `ModuleNotFoundError: No module named 'src.pipeline'`.

- [ ] **Step 3: Implement the pipeline**

Create `prototype/src/pipeline.py`:

```python
"""Orchestration pipeline — revision merger + generate + handle_reply.

Adapters are dependency-injected so tests can mock them. The pipeline owns
the business logic; adapters own I/O.

LLM provider: OpenAI (gpt-4o + gpt-4o-mini) for the Monday demo. Swap-back
to Anthropic Claude is localized to the two `call_llm_*` helpers below —
change the SDK import, the .create() call shape, and the cost-rate constants."""
from __future__ import annotations
import asyncio
import json
import os
import tempfile
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from src import state
from src.prompts import (
    INTENT_AND_PROMPT_ENGINEERING,
    PPT_CONTENT_GENERATION,
    MCQ_GENERATION,
    RECKONER_GENERATION,
    REVISION_MERGER,
    REPLY_PARSER_HAIKU,
)
from src.reply_parser import parse_reply, ReplyOutcome
from src.schemas import Intent, SlideDeck, MCQList, Reckoner
from src.pptx_formatter import render_pptx
from src.pdf_formatter import render_pdf


def _cost_cents(model: str, input_tokens: int, output_tokens: int) -> int:
    """Rough per-1M-token rates × tokens, in cents.
    OpenAI (Monday): gpt-4o $2.50/$10 in/out, gpt-4o-mini $0.15/$0.60 in/out.
    Anthropic (planned revert): claude-sonnet-4-6 $3/$15, claude-haiku-4-5 $0.25/$1.25.
    Numbers here are approximate and used for budgeting only — providers
    publish exact rates per model."""
    rates = {
        # OpenAI (current)
        "gpt-4o": (2.50, 10.0),
        "gpt-4o-2024-08-06": (2.50, 10.0),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.0, 30.0),
        # Anthropic (planned revert)
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-sonnet-4-5": (3.0, 15.0),
        "claude-haiku-4-5": (0.25, 1.25),
    }
    in_per_m, out_per_m = rates.get(model, (3.0, 15.0))
    dollars = (input_tokens / 1_000_000) * in_per_m + (output_tokens / 1_000_000) * out_per_m
    return int(round(dollars * 100))


def _strip_json_fences(text: str) -> str:
    """Defensive: strip ```json ... ``` wrappers if a model adds them.
    OpenAI's response_format=json_object should make this unnecessary,
    but we keep it as belt-and-suspenders."""
    text = text.strip()
    if text.startswith("```"):
        # Drop the opening fence (with or without language tag) and the closing one.
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text[: -len("```")]
    return text.strip()


class Pipeline:
    def __init__(self, *, llm, whatsapp, storage, supabase, settings) -> None:
        self.llm = llm  # AsyncOpenAI instance (Monday); AsyncAnthropic on revert
        self.whatsapp = whatsapp
        self.storage = storage
        self.supabase = supabase
        self.settings = settings

    # --- LLM call helpers (override in tests via AsyncMock) ---
    # SWAP-BACK NOTE: when reverting to Anthropic Claude, only these two
    # methods need rewriting (replace the OpenAI SDK calls + the model
    # field lookups). Method names stay provider-agnostic.

    async def call_llm_json(self, *, project_id: str, step: str, prompt: str) -> dict:
        """Call the content model with JSON mode and parse the response.
        Records a generations row with token usage + cost."""
        resp = await self.llm.chat.completions.create(
            model=self.settings.openai_content_model,
            max_tokens=4096,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content or "{}"
        usage = resp.usage
        state.insert_generation(
            self.supabase,
            project_id=project_id,
            step=step,
            model=self.settings.openai_content_model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_cents=_cost_cents(
                self.settings.openai_content_model,
                usage.prompt_tokens,
                usage.completion_tokens,
            ),
        )
        return json.loads(_strip_json_fences(text))

    async def call_llm_text(self, *, project_id: str, step: str, prompt: str,
                             model: str | None = None, max_tokens: int = 2048) -> str:
        """Call the LLM expecting plain text (revision merger, reply parser)."""
        model = model or self.settings.openai_content_model
        resp = await self.llm.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        state.insert_generation(
            self.supabase,
            project_id=project_id,
            step=step,
            model=model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_cents=_cost_cents(model, usage.prompt_tokens, usage.completion_tokens),
        )
        return text.strip()

    # --- Generation pipeline ---

    async def generate(self, project_id: str) -> None:
        """Full generation pipeline: revision merger (conditional) → intent →
        3 parallel generators → 2 formatters → upload → CAS to awaiting_approval →
        send summary. CAS losses anywhere → silent exit (another handler won)."""
        try:
            project = state.get_project(self.supabase, project_id)
            if project is None:
                return

            # Step 0: revision merger (only when there are revisions)
            if (project.get("revision_count") or 0) > 0:
                merged = await self.call_llm_text(
                    project_id=project_id,
                    step="revision_merge",
                    prompt=REVISION_MERGER.format(
                        original_request=project["original_request"],
                        revisions_text=project["current_request"],
                    ),
                )
                brief = merged
            else:
                brief = project["current_request"]

            # Step 1: intent + prompt engineering
            intent_raw = await self.call_llm_json(
                project_id=project_id,
                step="intent",
                prompt=INTENT_AND_PROMPT_ENGINEERING.format(transcript=brief),
            )
            intent = Intent.model_validate(intent_raw)

            # Steps 2/3/4: PPT / MCQ / Reckoner in parallel
            ppt_raw, mcq_raw, reckoner_raw = await asyncio.gather(
                self.call_llm_json(
                    project_id=project_id, step="ppt_content",
                    prompt=PPT_CONTENT_GENERATION.format(ppt_prompt=intent.ppt_prompt),
                ),
                self.call_llm_json(
                    project_id=project_id, step="mcq",
                    prompt=MCQ_GENERATION.format(mcq_prompt=intent.mcq_prompt),
                ),
                self.call_llm_json(
                    project_id=project_id, step="reckoner",
                    prompt=RECKONER_GENERATION.format(reckoner_prompt=intent.reckoner_prompt),
                ),
            )
            slide_deck = SlideDeck.model_validate(ppt_raw)
            mcq_list = MCQList.model_validate(mcq_raw)
            reckoner = Reckoner.model_validate(reckoner_raw)

            # Steps 5/6: render files
            with tempfile.TemporaryDirectory() as tmp:
                pptx_path = os.path.join(tmp, "lesson.pptx")
                pdf_path = os.path.join(tmp, "reckoner.pdf")
                render_pptx(
                    [s.model_dump(exclude_none=True) for s in slide_deck.slides],
                    [m.model_dump(exclude_none=True) for m in mcq_list.mcqs],
                    pptx_path,
                )
                render_pdf(reckoner.model_dump(exclude_none=True), pdf_path)

                with open(pptx_path, "rb") as f:
                    pptx_bytes = f.read()
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()

            # Step 7: upload + sign
            bucket = self.settings.supabase_storage_bucket
            pptx_obj = f"{project_id}/lesson.pptx"
            pdf_obj = f"{project_id}/reckoner.pdf"
            await asyncio.gather(
                self.storage.upload(bucket=bucket, path=pptx_obj, content=pptx_bytes,
                                    content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"),
                self.storage.upload(bucket=bucket, path=pdf_obj, content=pdf_bytes,
                                    content_type="application/pdf"),
            )
            pptx_url, pdf_url = await asyncio.gather(
                self.storage.signed_url(bucket=bucket, path=pptx_obj,
                                        expires_in_seconds=self.settings.signed_url_ttl_seconds),
                self.storage.signed_url(bucket=bucket, path=pdf_obj,
                                        expires_in_seconds=self.settings.signed_url_ttl_seconds),
            )

            # Step 8: CAS → awaiting_approval; send summary
            summary = (
                f"Made: {intent.duration_min}-min {intent.subject} lesson for grade "
                f"{intent.grade} on {intent.topic} — {intent.n_slides} slides + "
                f"{intent.n_mcqs} MCQs + 1-page reckoner.\n\n"
                "Reply APPROVE to receive the files, or describe what to change."
            )
            won = state.cas_to_awaiting_approval(
                self.supabase, project_id,
                summary=summary, pptx_url=pptx_url, pdf_url=pdf_url,
            )
            if not won:
                return  # another handler advanced state; do not send

            # Refetch phone to send the summary
            project = state.get_project(self.supabase, project_id)
            if project is not None:
                result = await self.whatsapp.send_text(to=project["phone"], body=summary)
                state.insert_outbound_message(
                    self.supabase, project_id=project_id, provider_sid=result.sid,
                    from_phone=self.settings.twilio_whatsapp_from,
                    to_phone=project["phone"], body=summary,
                )

        except (ValidationError, Exception) as exc:  # noqa: BLE001 — prototype scope
            state.cas_to_error(
                self.supabase, project_id,
                error_reason=str(exc)[:500],
                expected_states=("generating",),
            )
            project = state.get_project(self.supabase, project_id)
            if project is not None:
                try:
                    await self.whatsapp.send_text(
                        to=project["phone"],
                        body="Something went wrong while generating your lesson — please try again.",
                    )
                except Exception:
                    pass  # don't compound failure during demo

    # --- Reply handling ---

    async def handle_reply(self, project_id: str, body: str) -> None:
        project = state.get_project(self.supabase, project_id)
        if project is None or project["state"] != "awaiting_approval":
            return  # nothing actionable

        async def haiku_classify(text: str) -> str:
            return await self.call_llm_text(
                project_id=project_id,
                step="reply_parse",
                prompt=REPLY_PARSER_HAIKU.format(body=text),
                model=self.settings.openai_classification_model,
                max_tokens=16,
            )

        outcome = await parse_reply(body, classify=haiku_classify)

        if outcome == ReplyOutcome.APPROVED:
            won = state.cas_to_approved(self.supabase, project_id)
            if not won:
                return
            # Refresh — we need the URLs
            project = state.get_project(self.supabase, project_id)
            for url in (project["pptx_url"], project["pdf_url"]):
                result = await self.whatsapp.send_text(to=project["phone"], body=url)
                state.insert_outbound_message(
                    self.supabase, project_id=project_id, provider_sid=result.sid,
                    from_phone=self.settings.twilio_whatsapp_from,
                    to_phone=project["phone"], body=url,
                )
            state.cas_to_delivered(self.supabase, project_id)

        elif outcome == ReplyOutcome.CHANGES_REQUESTED:
            won = state.cas_to_generating_for_revision(self.supabase, project_id, body)
            if not won:
                return
            result = await self.whatsapp.send_text(
                to=project["phone"], body="Updating with your changes…",
            )
            state.insert_outbound_message(
                self.supabase, project_id=project_id, provider_sid=result.sid,
                from_phone=self.settings.twilio_whatsapp_from,
                to_phone=project["phone"], body="Updating with your changes…",
            )
            await self.generate(project_id)

        else:  # UNCLEAR
            result = await self.whatsapp.send_text(
                to=project["phone"],
                body=("I'm not sure — reply APPROVE to receive the files, "
                      "or describe what you'd like to change."),
            )
            state.insert_outbound_message(
                self.supabase, project_id=project_id, provider_sid=result.sid,
                from_phone=self.settings.twilio_whatsapp_from,
                to_phone=project["phone"], body="(clarification prompt)",
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_pipeline.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Run the full suite**

```bash
uv run pytest -v --ignore=tests/test_smoke_openai.py \
                 --ignore=tests/test_smoke_twilio.py \
                 --ignore=tests/test_smoke_supabase.py
```

Expected: all non-smoke tests PASS.

- [ ] **Step 6: Commit**

```bash
git add prototype/src/pipeline.py prototype/tests/test_pipeline.py
git commit -m "feat(prototype): pipeline — revision merger + generate + handle_reply (TDD)"
```

---

## Task 13: FastAPI server (`src/server.py`) — TDD with TestClient

**Files:**
- Create: `prototype/src/server.py`
- Test: `prototype/tests/test_server.py`

- [ ] **Step 1: Write the failing tests**

Create `prototype/tests/test_server.py`:

```python
"""TDD for the FastAPI webhook. Pipeline + adapters + supabase are mocked
via the get_* dependency-override pattern."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from src.server import app, get_pipeline, get_whatsapp_adapter, get_supabase
from src.state import insert_inbound_message  # noqa: F401 — imported elsewhere


TWILIO_TOKEN = "test_token"
WEBHOOK_URL = "https://example.test/webhooks/whatsapp"


def _signed_form(form: dict) -> tuple[dict, str]:
    sig = RequestValidator(TWILIO_TOKEN).compute_signature(WEBHOOK_URL, form)
    return form, sig


@pytest.fixture
def client():
    fake_whatsapp = MagicMock()
    fake_whatsapp.verify_signature = MagicMock(return_value=True)
    fake_whatsapp.send_text = AsyncMock()
    fake_pipeline = MagicMock()
    fake_pipeline.generate = AsyncMock()
    fake_pipeline.handle_reply = AsyncMock()
    fake_supabase = MagicMock()
    # Default: no existing project for this phone, no inbound message dup
    fake_supabase.table().select().eq().order().limit().execute.return_value = MagicMock(data=[])
    fake_supabase.table().insert().execute.return_value = MagicMock(
        data=[{"id": "p-new", "phone": "whatsapp:+919999999999",
               "original_request": "x", "current_request": "x",
               "state": "generating", "revision_count": 0}]
    )

    app.dependency_overrides[get_pipeline] = lambda: fake_pipeline
    app.dependency_overrides[get_whatsapp_adapter] = lambda: fake_whatsapp
    app.dependency_overrides[get_supabase] = lambda: fake_supabase

    client = TestClient(app, base_url="https://example.test")
    client.fake_pipeline = fake_pipeline
    client.fake_whatsapp = fake_whatsapp
    client.fake_supabase = fake_supabase
    yield client
    app.dependency_overrides.clear()


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_webhook_bad_signature_returns_401(client):
    client.fake_whatsapp.verify_signature = MagicMock(return_value=False)
    form = {
        "AccountSid": "AC_fake", "MessageSid": "SM_bad",
        "From": "whatsapp:+919999999999", "To": "whatsapp:+14155238886",
        "Body": "hi",
    }
    r = client.post("/webhooks/whatsapp", data=form,
                    headers={"X-Twilio-Signature": "obviously-wrong"})
    assert r.status_code == 401


def test_webhook_new_request_creates_project_and_acks(client):
    form = {
        "AccountSid": "AC_fake", "MessageSid": "SM_new1",
        "From": "whatsapp:+919999999999", "To": "whatsapp:+14155238886",
        "Body": "30-min lesson grade 7 photosynthesis",
    }
    r = client.post("/webhooks/whatsapp", data=form,
                    headers={"X-Twilio-Signature": "ok"})
    assert r.status_code == 200
    body = r.text
    assert "<Response>" in body and "<Message>" in body
    assert "Got it" in body
    # Pipeline.generate was scheduled
    client.fake_pipeline.generate.assert_called()


def test_webhook_duplicate_message_returns_empty_twiml(client):
    # Make the inbound insert raise unique-violation
    from postgrest.exceptions import APIError
    client.fake_supabase.table().insert().execute.side_effect = APIError(
        {"code": "23505", "message": "dup"}
    )
    form = {
        "AccountSid": "AC_fake", "MessageSid": "SM_dup",
        "From": "whatsapp:+919999999999", "To": "whatsapp:+14155238886",
        "Body": "hi",
    }
    r = client.post("/webhooks/whatsapp", data=form,
                    headers={"X-Twilio-Signature": "ok"})
    assert r.status_code == 200
    assert "<Message>" not in r.text  # empty <Response/>
    client.fake_pipeline.generate.assert_not_called()


def test_webhook_reply_routes_to_handle_reply(client):
    # Latest project is in awaiting_approval
    client.fake_supabase.table().select().eq().order().limit().execute.return_value = MagicMock(
        data=[{"id": "p-existing", "phone": "whatsapp:+919999999999",
               "state": "awaiting_approval"}]
    )
    form = {
        "AccountSid": "AC_fake", "MessageSid": "SM_reply",
        "From": "whatsapp:+919999999999", "To": "whatsapp:+14155238886",
        "Body": "APPROVE",
    }
    r = client.post("/webhooks/whatsapp", data=form,
                    headers={"X-Twilio-Signature": "ok"})
    assert r.status_code == 200
    client.fake_pipeline.handle_reply.assert_called()
    client.fake_pipeline.generate.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_server.py -v
```

Expected: 5 FAIL with `ModuleNotFoundError: No module named 'src.server'`.

- [ ] **Step 3: Implement the server**

Create `prototype/src/server.py`:

```python
"""FastAPI service — POST /webhooks/whatsapp.

The webhook returns TwiML inline for the ack, schedules background work via
`asyncio.create_task`, and verifies Twilio's X-Twilio-Signature before any
DB write. State transitions are CAS so concurrent webhook hits don't race."""
from __future__ import annotations
import asyncio
from functools import lru_cache

from openai import AsyncOpenAI
from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, Response
from supabase import create_client

from src import state
from src.pipeline import Pipeline
from src.settings import Settings, get_settings
from src.storage_adapter import SupabaseStorageAdapter
from src.whatsapp_adapter import TwilioAdapter, WhatsAppAdapter


app = FastAPI(title="wtsagnt Monday WhatsApp slice")


@lru_cache(maxsize=1)
def _whatsapp_adapter() -> TwilioAdapter:
    s = get_settings()
    return TwilioAdapter(
        account_sid=s.twilio_account_sid,
        auth_token=s.twilio_auth_token,
        whatsapp_from=s.twilio_whatsapp_from,
    )


@lru_cache(maxsize=1)
def _supabase_client():
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_secret_key)


@lru_cache(maxsize=1)
def _llm_client() -> AsyncOpenAI:
    """LLM client — OpenAI for Monday, AsyncAnthropic on planned revert."""
    s = get_settings()
    return AsyncOpenAI(api_key=s.openai_api_key)


@lru_cache(maxsize=1)
def _pipeline() -> Pipeline:
    s = get_settings()
    return Pipeline(
        llm=_llm_client(),
        whatsapp=_whatsapp_adapter(),
        storage=SupabaseStorageAdapter(client=_supabase_client()),
        supabase=_supabase_client(),
        settings=s,
    )


def get_settings_dep() -> Settings:
    return get_settings()


def get_whatsapp_adapter() -> WhatsAppAdapter:
    return _whatsapp_adapter()


def get_supabase():
    return _supabase_client()


def get_pipeline() -> Pipeline:
    return _pipeline()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _twiml(message: str = "") -> Response:
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        + (f"<Message>{message}</Message>" if message else "")
        + "</Response>"
    )
    return Response(content=body, media_type="application/xml")


@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_twilio_signature: str = Header(default=""),
    settings: Settings = Depends(get_settings_dep),
    whatsapp: WhatsAppAdapter = Depends(get_whatsapp_adapter),
    supabase=Depends(get_supabase),
    pipeline: Pipeline = Depends(get_pipeline),
) -> Response:
    # 1. Parse the form body — Twilio sends application/x-www-form-urlencoded
    form_data = await request.form()
    form = {k: form_data[k] for k in form_data}

    # 2. Signature verification — reconstruct the URL as Twilio sees it
    # When deployed behind a proxy, trust the public base URL from settings
    public_url = f"{settings.public_base_url.rstrip('/')}{request.url.path}"
    if not whatsapp.verify_signature(url=public_url, signature=x_twilio_signature, form=form):
        raise HTTPException(status_code=401, detail="bad twilio signature")

    provider_sid = form.get("MessageSid", "")
    from_phone = form.get("From", "")
    to_phone = form.get("To", "")
    body = (form.get("Body") or "").strip()
    if not (provider_sid and from_phone and body):
        return _twiml()  # malformed, ignore

    # 3. Look up the latest project for this phone
    latest = state.latest_project_for_phone(supabase, from_phone)

    # 4. Branch on state
    if latest is None or latest["state"] in ("approved", "delivered", "error"):
        # New request route
        project = state.create_project(supabase, from_phone, body)
        ok = state.insert_inbound_message(
            supabase, project_id=project["id"], provider_sid=provider_sid,
            from_phone=from_phone, to_phone=to_phone, body=body,
        )
        if not ok:
            return _twiml()  # duplicate, no work
        asyncio.create_task(pipeline.generate(project["id"]))
        return _twiml("Got it. Generating your lesson…")

    if latest["state"] == "generating":
        # Race with our own in-flight pipeline; just ack and don't queue more work
        state.insert_inbound_message(
            supabase, project_id=latest["id"], provider_sid=provider_sid,
            from_phone=from_phone, to_phone=to_phone, body=body,
        )
        return _twiml("Still working on your previous request — one moment.")

    # latest["state"] == "awaiting_approval"
    ok = state.insert_inbound_message(
        supabase, project_id=latest["id"], provider_sid=provider_sid,
        from_phone=from_phone, to_phone=to_phone, body=body,
    )
    if not ok:
        return _twiml()
    asyncio.create_task(pipeline.handle_reply(latest["id"], body))
    return _twiml()  # handle_reply will send a follow-up message asynchronously
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_server.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Boot the server locally and hit /health**

In one terminal:

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv run uvicorn src.server:app --host 127.0.0.1 --port 8000
```

In another:

```bash
curl http://127.0.0.1:8000/health
```

Expected: `{"ok":true}` and the uvicorn log shows a 200.

Stop uvicorn with Ctrl-C.

- [ ] **Step 6: Run the full suite (non-smoke)**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv run pytest -v \
    --ignore=tests/test_smoke_openai.py \
    --ignore=tests/test_smoke_twilio.py \
    --ignore=tests/test_smoke_supabase.py
```

Expected: every non-smoke test PASSES.

- [ ] **Step 7: Commit**

```bash
git add prototype/src/server.py prototype/tests/test_server.py
git commit -m "feat(prototype): FastAPI webhook — signature verify + route + TwiML ack"
```

---

## Task 14: Local end-to-end with ngrok + Twilio sandbox

This is a wiring task — no new code. You verify that a real WhatsApp message from a joined sandbox phone, through ngrok, hits your local server and round-trips.

- [ ] **Step 1: Install ngrok and start a tunnel**

```bash
# If you don't have ngrok yet
brew install ngrok/ngrok/ngrok
ngrok config add-authtoken <your-ngrok-token>  # one-time

# Start the tunnel to port 8000
ngrok http 8000
```

Note the `https://<random>.ngrok-free.app` URL that ngrok prints. Copy it.

- [ ] **Step 2: Update `.env` PUBLIC_BASE_URL**

In `prototype/.env`, set:

```
PUBLIC_BASE_URL=https://<that-random>.ngrok-free.app
```

(The signature validator builds the request URL as `PUBLIC_BASE_URL + /webhooks/whatsapp` — must match exactly what Twilio sees.)

- [ ] **Step 3: Configure the Twilio sandbox webhook**

Twilio Console → Messaging → Try it out → WhatsApp → Sandbox settings. Set:
- **WHEN A MESSAGE COMES IN:** `https://<that-random>.ngrok-free.app/webhooks/whatsapp` (POST)
- Save.

- [ ] **Step 4: Boot the local server**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
uv run uvicorn src.server:app --host 127.0.0.1 --port 8000 --reload
```

- [ ] **Step 5: Send a real WhatsApp message from the joined phone**

From the demo phone (already joined to the sandbox), send to the sandbox number:

> 30-min lesson for grade 7 on photosynthesis. Cover the process, inputs, outputs, where in the plant. 5 MCQs.

Watch the uvicorn logs. Expected:
- Single POST `/webhooks/whatsapp` → 200 in <500ms
- Phone receives "Got it. Generating your lesson…" within 2 seconds
- 60–120 seconds later, a summary message arrives

Then reply `APPROVE`. Expected:
- Two follow-up messages arrive with `.pptx` and `.pdf` links (signed Supabase URLs)
- Tapping each on the phone downloads the file; both open clean

- [ ] **Step 6: Test the revision branch**

Send a new request, wait for summary, then reply (instead of APPROVE):

> Make it for grade 8 instead, and add a section on cellular respiration

Expected:
- "Updating with your changes…" arrives quickly
- 60–120s later a new summary arrives
- APPROVE → new files arrive

- [ ] **Step 7: Inspect the database**

Open Supabase dashboard → Table editor → `projects`, `messages`, `generations`.
- One `projects` row, state should be `delivered` (or `awaiting_approval` if you didn't approve the revision)
- `messages` rows for every inbound and outbound (provider_sid populated)
- `generations` rows: ~4–8 entries with token counts + cost_cents

- [ ] **Step 8: Commit any small tweaks you needed during the smoke**

If you discovered a small bug during the live smoke, fix it, add a regression test, and commit. Don't proceed to Task 15 with anything visibly broken.

---

## Task 15: Railway deployment

**Files:**
- Create: `prototype/railway.toml`

- [ ] **Step 1: Write the Railway config**

Create `prototype/railway.toml`:

```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "uv run uvicorn src.server:app --host 0.0.0.0 --port $PORT"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3

[deploy.healthcheck]
path = "/health"
timeout = 30
```

- [ ] **Step 2: Provision the Railway project**

Use the Railway MCP (or CLI) to:
1. Create a new project named `wtsagnt-monday`
2. Connect this directory (`/Users/newuser/Projects/Personal/wtsagnt/prototype`) as the service source
3. Set the service root to `prototype/` (Nixpacks needs to see `pyproject.toml` at the root of the build context)
4. Set every env var from `prototype/.env.example` in the Railway dashboard with real values — copy from `.env` line-by-line. **Skip `PUBLIC_BASE_URL` for now**; set it after step 4.
5. Deploy

If using the CLI:

```bash
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
railway link    # follow prompts; choose 'wtsagnt-monday'
railway up
```

- [ ] **Step 3: Wait for the build to complete and grab the public URL**

```bash
railway domain   # shows the public URL, e.g., wtsagnt-monday.up.railway.app
```

Expected: `https://wtsagnt-monday-production.up.railway.app` (or similar).

- [ ] **Step 4: Update `PUBLIC_BASE_URL` in Railway**

Back in the Railway dashboard, set `PUBLIC_BASE_URL=https://<that-public-domain>`. Redeploy (Railway auto-redeploys on env change).

- [ ] **Step 5: Smoke-test the deployed `/health`**

```bash
curl https://<that-public-domain>/health
```

Expected: `{"ok":true}`.

- [ ] **Step 6: Re-point the Twilio webhook at Railway**

Twilio Console → Sandbox settings → **WHEN A MESSAGE COMES IN:** `https://<that-public-domain>/webhooks/whatsapp` (POST). Save.

- [ ] **Step 7: Full live round-trip against Railway**

From the joined sandbox phone, send the photosynthesis prompt. Confirm the same flow as Task 14 Steps 5–7 works against the Railway URL (not localhost). Wall-clock timing matters: Railway cold-start can add 5–10s the first time.

- [ ] **Step 8: Commit the Railway config**

```bash
cd /Users/newuser/Projects/Personal/wtsagnt
git add prototype/railway.toml
git commit -m "feat(prototype): Railway deploy config (nixpacks + healthcheck)"
```

---

## Task 16: Sunday dry-run + screen recording

This task is the safety net. Cheap insurance against Monday-morning failure.

- [ ] **Step 1: Full dry-run on the production Railway service**

From the demo phone, run the complete demo as you'd show Senthil:
- New request (photosynthesis grade 7)
- Wait for summary
- Show the Supabase dashboard `projects` row appearing
- Show the `generations` rows appearing per LLM call
- Reply APPROVE → two file links arrive
- Open both files on the phone, show they look real
- Send a second new request that exercises a revision (e.g., "5-min quiz for grade 9 on Newton's laws, 10 MCQs") then reply with a revision instruction
- Show the regeneration flow

Total wall-clock: 5–8 minutes including narration pauses.

- [ ] **Step 2: Record the dry-run**

Screen-record the phone (iOS: built-in Screen Recording; Android: Screen Recorder) for the full happy path. Save the file as `prototype/demo/2026-05-17-dry-run.mp4`.

(The `prototype/demo/` directory is gitignored, so the video stays local.)

- [ ] **Step 3: Stop touching the code**

If the dry-run passes, **stop**. No "one more tweak." Anything else you want to improve goes into a post-Monday issue list.

If the dry-run fails, debug, fix, **re-run the dry-run end-to-end**, re-record. Repeat until the recording is clean.

- [ ] **Step 4: Brief written demo script for Monday**

Create `prototype/demo/script.md` (you can keep it as private notes if you prefer — it's gitignored):

```markdown
# Monday demo script (5 minutes)

1. (30s) Pitch: "Teacher sends WhatsApp, agents make lesson, bot delivers."
2. (45s) Open WhatsApp on phone. Send the photosynthesis prompt.
3. (60-120s while it runs) Walk through:
   - The architecture diagram (`docs/superpowers/specs/2026-05-17-...-design.md`)
   - The Supabase `projects` and `generations` rows appearing in real time
4. (30s) Summary arrives. Read it aloud. Reply APPROVE.
5. (10s) Files arrive. Tap each on the phone, show they open clean.
6. (90s) Demo the revision branch. Send a new request, reply with a change.
7. (30s) Wrap: what's next — RLS, Drive, voice, Gupshup. Hand to Senthil.
```

- [ ] **Step 5: Confirm pre-flight is clean for Monday morning**

Make a quick checklist text file `prototype/demo/morning-checklist.md` (gitignored):

```markdown
- [ ] Railway service `wtsagnt-monday` is healthy (curl /health)
- [ ] Twilio webhook points at Railway public URL (not ngrok)
- [ ] Demo phone(s) still joined to Twilio sandbox (sandboxes auto-expire after 72h of inactivity — send one warm-up message Monday morning)
- [ ] `prototype/.env` has correct values on the dev machine (in case Railway needs a redeploy)
- [ ] OpenAI balance / rate-limit headroom checked
- [ ] Screen recording (`demo/2026-05-17-dry-run.mp4`) exists and plays
- [ ] Browser tab open to Supabase dashboard → `projects` table sorted by created_at desc
```

- [ ] **Step 6: (No commit — `demo/` is gitignored.)**

You can however commit a final tag if you want a checkpoint:

```bash
cd /Users/newuser/Projects/Personal/wtsagnt
git tag -a monday-demo-ready -m "Pre-demo checkpoint: dry-run passed, screen recording saved"
```

---

## Self-Review

**Spec coverage check** — every section of the spec maps to at least one task:

| Spec section | Implementing task(s) |
|---|---|
| Pre-flight blockers (P0) | Pre-flight checklist above Task 1 |
| Demo surface (text→summary→APPROVE→files; revision branch) | Tasks 12–14 |
| Architecture (FastAPI + async pipeline + Twilio + Supabase) | Tasks 10–13 |
| Components → persistence (projects/messages/generations + storage bucket + CAS + partial UNIQUE) | Tasks 7, 8 |
| Code layout (each src/ file) | Tasks 1, 6, 8, 9, 10, 11, 12, 13 |
| Adapter contracts (WhatsAppAdapter, StorageAdapter Protocols) | Tasks 10, 11 |
| LLM strategy (6 prompts incl. revision merger + Haiku reply) | Tasks 3, 12 |
| Data flow walkthrough (TwiML inline, CAS at every state transition, revision merger) | Tasks 12, 13 |
| Reply parser 3 tiers | Task 9 |
| Error handling (CAS to error, single Twilio retry, no DLQ) | Task 12 (pipeline try/except), Task 10 (TwilioAdapter — tenacity retry deferred to a small follow-up) |
| Testing (unit + smoke + manual E2E) | Tasks 2, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 16 |
| Definition of done (1–9) | Task 14 (local) + Task 15 (deployed) + Task 16 (dry-run) |
| CLAUDE.md compliance check | Built into the migration (Task 7) and pipeline (Task 12) per the spec table |
| Demo day plan | Task 16 |

**Identified gap (and fix):** I called out a small follow-up — the spec mentions `tenacity` retry on Twilio send failure. The current `TwilioAdapter.send_text` doesn't wrap with `tenacity`. **Fix:** add this as Step 6.5 inside Task 12 (the only place `send_text` is consumed). Acceptable to defer to a follow-up commit during Task 14 if needed — adding `@retry(stop=stop_after_attempt(2), wait=wait_fixed(1))` from `tenacity` to a small wrapper inside the pipeline.

**Placeholder scan:** No "TBD"/"TODO"/"implement later" in the plan. Every step has runnable code or a runnable command with an expected outcome.

**Type consistency:** Verified — `render_pptx(slides, mcqs, output_path)` and `render_pdf(reckoner, output_path)` signatures match between Tasks 4/5 and the consuming pipeline in Task 12. `WhatsAppAdapter.send_text(to=, body=)` and `StorageAdapter.upload(bucket=, path=, content=, content_type=)` / `signed_url(bucket=, path=, expires_in_seconds=)` are consistent across Tasks 10, 11, 12, 13. `state.cas_to_*(supabase, project_id, ...)` signatures consistent between Tasks 8 and 12.

**Spec deferrals tracked:** RLS off, signed URLs stored on row, cost cap tracked-not-enforced — all match the spec's "CLAUDE.md compliance check" table.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-17-monday-whatsapp-slice.md`.**

Two execution options for handing this off:

**1. Subagent-Driven (recommended for this scope)** — I dispatch a fresh subagent per task using `superpowers:subagent-driven-development`, review the diff between tasks, fast iteration with clean context for each task. Best for the heavy Python tasks (8, 9, 10, 12, 13). The wiring tasks (7, 14, 15, 16) have human-only steps so they stay on the main thread.

**2. Inline Execution** — I execute every task in this session using `superpowers:executing-plans` with checkpoints. Slower context-wise but lets you watch each step land. Better if you want to learn the codebase as it grows.

**Which approach?**
