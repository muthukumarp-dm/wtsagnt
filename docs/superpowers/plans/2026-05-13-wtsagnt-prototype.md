# wtsagnt Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a quality LangFlow-based prototype that demonstrates the wtsagnt multi-agent architecture end-to-end: paste a teacher transcript, watch the agent network execute, produce a `.pptx` lesson deck (with MCQs) and a `.pdf` ready-reckoner. Demoable to Senthil today.

**Architecture:** Local-only Python prototype with a LangFlow canvas as the runtime. Reusable Python modules (`pptx_formatter`, `pdf_formatter`) are TDD'd in isolation; LangFlow custom components wrap them as draggable nodes. The canvas has 7 functional nodes (1 transcript input, 4 Claude calls, 2 custom formatters) that mirror the diagram's Input → Intent+Prompt → fan-out to 3 generators → 2 formatters → 2 output files. No deploy, no DB, no auth.

**Tech Stack:** Python 3.11+, [`uv`](https://docs.astral.sh/uv/) for dependency management, `langflow` (visual canvas + runtime), `anthropic` SDK (`claude-sonnet-4-6`), `python-pptx`, `reportlab`, `pydantic` (schemas), `pytest` (formatter tests).

**Spec:** [`docs/superpowers/specs/2026-05-13-wtsagnt-prototype-design.md`](../specs/2026-05-13-wtsagnt-prototype-design.md)

---

## File Structure

All paths relative to `/Users/newuser/Projects/Personal/wtsagnt/`.

```
prototype/
├── pyproject.toml                  # uv project + deps
├── .env.example                    # ANTHROPIC_API_KEY placeholder
├── .gitignore                      # outputs/, .env, __pycache__/, .venv/
├── README.md                       # how to run the demo (written last)
├── samples/
│   └── transcript.txt              # the photosynthesis sample
├── src/
│   ├── __init__.py
│   ├── schemas.py                  # pydantic models (Intent, Slide, MCQ, Reckoner)
│   ├── prompts.py                  # the 4 prompt templates as constants
│   ├── pptx_formatter.py           # render_pptx(slides, mcqs, out_path)
│   └── pdf_formatter.py            # render_pdf(reckoner, out_path)
├── langflow_components/
│   ├── __init__.py
│   ├── pptx_node.py                # LangFlow Custom Component wrapping pptx_formatter
│   └── pdf_node.py                 # LangFlow Custom Component wrapping pdf_formatter
├── flows/
│   └── wtsagnt_prototype.json      # exported LangFlow flow (Task 11)
├── outputs/                        # gitignored; flow writes <timestamp>/lesson.pptx and reckoner.pdf here
└── tests/
    ├── __init__.py
    ├── test_pptx_formatter.py
    └── test_pdf_formatter.py
```

Decomposition rationale: business logic (formatters) lives in `src/` and is plain Python that's testable in pytest. `langflow_components/` is the thin LangFlow adapter layer. `flows/` is the canvas as data. Keeping these split means real-development (which moves orchestration to N8n) only has to throw away `langflow_components/` and `flows/` — the `src/` modules survive.

---

## Task 1: Project skeleton + dependencies + Claude API smoke test

**Files:**
- Create: `prototype/pyproject.toml`
- Create: `prototype/.env.example`
- Create: `prototype/.gitignore`
- Create: `prototype/src/__init__.py`
- Create: `prototype/langflow_components/__init__.py`
- Create: `prototype/tests/__init__.py`
- Create: `prototype/samples/.gitkeep`
- Create: `prototype/flows/.gitkeep`
- Test: `prototype/tests/test_smoke_anthropic.py`

- [ ] **Step 1: Create the project directory layout**

Run:
```bash
mkdir -p /Users/newuser/Projects/Personal/wtsagnt/prototype/{src,langflow_components,flows,samples,tests}
cd /Users/newuser/Projects/Personal/wtsagnt/prototype
touch src/__init__.py langflow_components/__init__.py tests/__init__.py samples/.gitkeep flows/.gitkeep
```

Expected: no errors; directories exist.

- [ ] **Step 2: Write `pyproject.toml`**

Create `prototype/pyproject.toml`:
```toml
[project]
name = "wtsagnt-prototype"
version = "0.1.0"
description = "wtsagnt LangFlow prototype — paste transcript, get .pptx + .pdf"
requires-python = ">=3.11"
dependencies = [
    "langflow>=1.0",
    "anthropic>=0.40",
    "python-pptx>=0.6.23",
    "reportlab>=4.0",
    "pydantic>=2.0",
    "python-dotenv>=1.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

- [ ] **Step 3: Write `.env.example` and `.gitignore`**

Create `prototype/.env.example`:
```
ANTHROPIC_API_KEY=sk-ant-...your-key-here...
LANGFLOW_COMPONENTS_PATH=./langflow_components
```

Create `prototype/.gitignore`:
```
.env
.venv/
__pycache__/
*.pyc
outputs/
.pytest_cache/
.langflow/
```

- [ ] **Step 4: Install dependencies with uv**

Run (from `prototype/`):
```bash
uv sync
```

If `uv` is not installed, install it first:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Expected: `.venv/` created, dependencies installed without errors. Takes 30–90 seconds (langflow is large).

- [ ] **Step 5: Copy your real Anthropic API key into a local `.env`**

Run:
```bash
cp .env.example .env
# Then edit .env and replace the placeholder with the real ANTHROPIC_API_KEY
```

Verify the key is loaded:
```bash
uv run python -c "from dotenv import load_dotenv; load_dotenv(); import os; print('key set:', bool(os.getenv('ANTHROPIC_API_KEY')))"
```
Expected: `key set: True`

- [ ] **Step 6: Write a smoke test that hits the Anthropic API**

Create `prototype/tests/test_smoke_anthropic.py`:
```python
"""Smoke test: confirm ANTHROPIC_API_KEY works and claude-sonnet-4-6 responds."""
import os
import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.mark.skipif(
    not os.getenv("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set",
)
def test_claude_responds():
    from anthropic import Anthropic

    client = Anthropic()
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=64,
        messages=[{"role": "user", "content": "Reply with exactly the word: ready"}],
    )
    text = response.content[0].text.strip().lower()
    assert "ready" in text
```

- [ ] **Step 7: Run the smoke test**

Run:
```bash
uv run pytest tests/test_smoke_anthropic.py -v
```
Expected: PASS. If you get a 401, the key is wrong. If you get model-not-found, your account doesn't have access to `claude-sonnet-4-6` — try `claude-sonnet-4-5` and update later.

- [ ] **Step 8: Initialize git and commit**

Run (from `prototype/`):
```bash
cd /Users/newuser/Projects/Personal/wtsagnt
git init
git add prototype/pyproject.toml prototype/.env.example prototype/.gitignore prototype/src/__init__.py prototype/langflow_components/__init__.py prototype/tests/__init__.py prototype/samples/.gitkeep prototype/flows/.gitkeep prototype/tests/test_smoke_anthropic.py
git commit -m "feat: prototype scaffolding + Claude API smoke test"
```

Expected: commit succeeds. The `.env` file is NOT in the index (gitignored).

---

## Task 2: Sample transcript + Pydantic schemas

**Files:**
- Create: `prototype/samples/transcript.txt`
- Create: `prototype/src/schemas.py`
- Test: `prototype/tests/test_schemas.py`

- [ ] **Step 1: Write the sample transcript**

Create `prototype/samples/transcript.txt`:
```
Hi, I need to prepare for tomorrow's class. It's a 30-minute lesson for grade 7 on photosynthesis. Cover the basic process, what goes in and what comes out, where in the plant it happens, and why it matters. Give me a one-page summary sheet I can hand to students, and 5 multiple choice questions for a quick quiz at the end. Make the slides visually varied, not just bullet walls.
```

- [ ] **Step 2: Write the schemas test**

Create `prototype/tests/test_schemas.py`:
```python
"""Verify pydantic models reject malformed JSON and accept correct payloads."""
import pytest
from pydantic import ValidationError

from src.schemas import Intent, SlideDeck, MCQList, Reckoner


def test_intent_accepts_valid_payload():
    intent = Intent.model_validate({
        "subject": "Science",
        "grade": "7",
        "topic": "Photosynthesis",
        "duration_min": 30,
        "n_slides": 10,
        "n_mcqs": 5,
        "ppt_prompt": "Build a grade 7 deck on photosynthesis...",
        "mcq_prompt": "Write 5 MCQs on photosynthesis for grade 7...",
        "reckoner_prompt": "Write a one-page reckoner on photosynthesis...",
    })
    assert intent.n_slides == 10
    assert intent.n_mcqs == 5


def test_intent_rejects_missing_field():
    with pytest.raises(ValidationError):
        Intent.model_validate({"subject": "Science"})


def test_slide_deck_accepts_layouts():
    deck = SlideDeck.model_validate({
        "slides": [
            {"layout": "title", "title": "Photosynthesis", "subtitle": "Grade 7"},
            {"layout": "bullets", "title": "Process", "bullets": ["Sunlight", "Water"]},
            {"layout": "two_column", "title": "In vs Out",
             "left_column": "Inputs: CO2, H2O", "right_column": "Outputs: O2, glucose"},
        ],
    })
    assert len(deck.slides) == 3


def test_mcq_list_requires_four_options():
    with pytest.raises(ValidationError):
        MCQList.model_validate({
            "mcqs": [{"question": "Q", "options": ["A", "B"], "answer": "A", "explanation": "..."}],
        })


def test_reckoner_accepts_sections():
    r = Reckoner.model_validate({
        "title": "Photosynthesis quick reference",
        "sections": [{"heading": "What", "body": "It's a process..."}],
    })
    assert r.sections[0].heading == "What"
```

- [ ] **Step 3: Run the test to verify it fails**

Run:
```bash
uv run pytest tests/test_schemas.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'src.schemas'`.

- [ ] **Step 4: Write the schemas module**

Create `prototype/src/schemas.py`:
```python
"""Pydantic models for the agent outputs."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class Intent(BaseModel):
    subject: str
    grade: str
    topic: str
    duration_min: int
    n_slides: int = Field(ge=1, le=40)
    n_mcqs: int = Field(ge=1, le=20)
    ppt_prompt: str
    mcq_prompt: str
    reckoner_prompt: str


class Slide(BaseModel):
    layout: Literal["title", "bullets", "two_column", "image_text"]
    title: str
    subtitle: str | None = None
    bullets: list[str] | None = None
    left_column: str | None = None
    right_column: str | None = None
    body: str | None = None


class SlideDeck(BaseModel):
    slides: list[Slide]


class MCQ(BaseModel):
    question: str
    options: list[str]
    answer: Literal["A", "B", "C", "D"]
    explanation: str

    @field_validator("options")
    @classmethod
    def four_options(cls, v: list[str]) -> list[str]:
        if len(v) != 4:
            raise ValueError("MCQ must have exactly 4 options")
        return v


class MCQList(BaseModel):
    mcqs: list[MCQ]


class ReckonerSection(BaseModel):
    heading: str
    body: str


class Reckoner(BaseModel):
    title: str
    sections: list[ReckonerSection]
```

- [ ] **Step 5: Run the test to verify it passes**

Run:
```bash
uv run pytest tests/test_schemas.py -v
```
Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

Run:
```bash
git add prototype/samples/transcript.txt prototype/src/schemas.py prototype/tests/test_schemas.py
git commit -m "feat: sample transcript + pydantic schemas for agent outputs"
```

---

## Task 3: Prompt templates module

**Files:**
- Create: `prototype/src/prompts.py`

(No tests — these are constant strings used by LangFlow nodes. They're verified end-to-end when the canvas runs.)

- [ ] **Step 1: Write the prompts module**

Create `prototype/src/prompts.py`:
```python
"""Prompt templates for the four Claude nodes in the LangFlow canvas.

Each constant is the FULL prompt sent to the model. {placeholders} are filled
in by the LangFlow prompt-template component at runtime.
"""
from __future__ import annotations


INTENT_AND_PROMPT_ENGINEERING = """\
You are a curriculum design assistant. A teacher has sent a transcript
describing what they need for an upcoming class. Your job is to:

1. Extract the structured intent (subject, grade, topic, duration, output counts)
2. Compose three downstream prompts for specialist agents (PPT, MCQ, reckoner)

Input transcript:
\"\"\"
{transcript}
\"\"\"

Respond with ONLY valid JSON matching this schema (no prose, no markdown fences):
{{
  "subject": "...",
  "grade": "...",
  "topic": "...",
  "duration_min": <int>,
  "n_slides": <int recommended content-slide count, excluding MCQ slides>,
  "n_mcqs": <int>,
  "ppt_prompt": "<self-contained prompt for the PPT content generator>",
  "mcq_prompt": "<self-contained prompt for the MCQ generator>",
  "reckoner_prompt": "<self-contained prompt for the reckoner generator>"
}}

The three downstream prompts must be self-contained — the downstream agents do
not see this transcript. Restate the subject, grade, topic, learning objectives,
and any constraints the teacher mentioned (visual variety, slide count, etc.).
"""


PPT_CONTENT_GENERATION = """\
You are an instructional designer building a slide deck for a classroom lesson.

Brief:
\"\"\"
{ppt_prompt}
\"\"\"

Respond with ONLY valid JSON (no prose, no markdown fences) matching this schema:
{{
  "slides": [
    {{
      "layout": "title" | "bullets" | "two_column" | "image_text",
      "title": "...",
      "subtitle": "..." | null,
      "bullets": ["...", "..."] | null,
      "left_column": "..." | null,
      "right_column": "..." | null,
      "body": "..." | null
    }}
  ]
}}

Constraints:
- Start with one "title" slide
- Vary layouts across the deck — do NOT use only "bullets". Mix bullets, two_column, image_text.
- No more than 5 bullets per "bullets" slide
- Use grade-appropriate language
- Aim for the slide count specified in the brief
"""


MCQ_GENERATION = """\
You are an assessment designer building multiple-choice questions for a classroom quiz.

Brief:
\"\"\"
{mcq_prompt}
\"\"\"

Respond with ONLY valid JSON (no prose, no markdown fences) matching this schema:
{{
  "mcqs": [
    {{
      "question": "...",
      "options": ["...", "...", "...", "..."],
      "answer": "A" | "B" | "C" | "D",
      "explanation": "..."
    }}
  ]
}}

Constraints:
- EXACTLY 4 options per question, in A B C D order
- Cover different cognitive levels (recall, understanding, application)
- Distractors must be plausible, not silly
- Questions must be answerable from the lesson content, not require outside knowledge
- One-sentence explanation per MCQ
"""


RECKONER_GENERATION = """\
You are a curriculum writer producing a one-page handout that students can take
home as a quick reference for the lesson.

Brief:
\"\"\"
{reckoner_prompt}
\"\"\"

Respond with ONLY valid JSON (no prose, no markdown fences) matching this schema:
{{
  "title": "...",
  "sections": [
    {{"heading": "...", "body": "..."}}
  ]
}}

Constraints:
- 3 to 6 sections
- Each section body is 1–3 sentences, no longer
- Use grade-appropriate language
- The whole handout should fit on one printed A4 page when rendered
"""
```

- [ ] **Step 2: Sanity-import to catch syntax errors**

Run:
```bash
uv run python -c "from src.prompts import INTENT_AND_PROMPT_ENGINEERING, PPT_CONTENT_GENERATION, MCQ_GENERATION, RECKONER_GENERATION; print('all 4 prompts loaded, total chars:', sum(map(len, [INTENT_AND_PROMPT_ENGINEERING, PPT_CONTENT_GENERATION, MCQ_GENERATION, RECKONER_GENERATION])))"
```
Expected: `all 4 prompts loaded, total chars: <some-number-around-3000>`

- [ ] **Step 3: Commit**

Run:
```bash
git add prototype/src/prompts.py
git commit -m "feat: prompt templates for the four Claude nodes"
```

---

## Task 4: PPT formatter (TDD)

**Files:**
- Test: `prototype/tests/test_pptx_formatter.py`
- Create: `prototype/src/pptx_formatter.py`

- [ ] **Step 1: Write the failing test**

Create `prototype/tests/test_pptx_formatter.py`:
```python
"""TDD: PPT formatter renders slide JSON + MCQ JSON into a valid .pptx file."""
from pathlib import Path

from pptx import Presentation

from src.pptx_formatter import render_pptx


def test_render_pptx_creates_valid_file(tmp_path: Path):
    slides = [
        {"layout": "title", "title": "Photosynthesis", "subtitle": "Grade 7"},
        {"layout": "bullets", "title": "Process",
         "bullets": ["Sunlight", "Water", "CO2"]},
        {"layout": "two_column", "title": "In vs Out",
         "left_column": "Inputs: CO2, H2O", "right_column": "Outputs: O2, glucose"},
        {"layout": "image_text", "title": "Where",
         "body": "It happens in the chloroplasts of plant leaves."},
    ]
    mcqs = [
        {"question": "What gas do plants take in?",
         "options": ["O2", "CO2", "N2", "H2"],
         "answer": "B", "explanation": "Plants absorb CO2 from the air."},
        {"question": "Where does photosynthesis happen?",
         "options": ["Roots", "Stem", "Chloroplasts", "Mitochondria"],
         "answer": "C", "explanation": "Chloroplasts contain chlorophyll."},
    ]
    out = tmp_path / "lesson.pptx"

    render_pptx(slides, mcqs, str(out))

    assert out.exists(), "pptx file was not created"
    assert out.stat().st_size > 5_000, "pptx file looks empty"

    # Open it back and confirm structure
    prs = Presentation(str(out))
    assert len(prs.slides) == len(slides) + len(mcqs)  # 4 content + 2 MCQ
    # First slide is the title
    assert prs.slides[0].shapes.title.text == "Photosynthesis"
    # Last slide is the second MCQ
    assert "photosynthesis happen" in prs.slides[-1].shapes.title.text.lower()


def test_render_pptx_handles_empty_mcqs(tmp_path: Path):
    slides = [{"layout": "title", "title": "Topic", "subtitle": "Sub"}]
    out = tmp_path / "no_mcqs.pptx"
    render_pptx(slides, [], str(out))
    prs = Presentation(str(out))
    assert len(prs.slides) == 1


def test_render_pptx_unknown_layout_falls_back_to_bullets(tmp_path: Path):
    slides = [{"layout": "weird_unknown", "title": "X", "bullets": ["a", "b"]}]
    out = tmp_path / "fallback.pptx"
    render_pptx(slides, [], str(out))
    prs = Presentation(str(out))
    assert len(prs.slides) == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
uv run pytest tests/test_pptx_formatter.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'src.pptx_formatter'`.

- [ ] **Step 3: Implement the formatter**

Create `prototype/src/pptx_formatter.py`:
```python
"""Render slide JSON + MCQ JSON into a .pptx file using python-pptx.

The renderer owns ALL layout primitives. Callers (the LLM upstream) only pick
a layout name and supply content — they do not control fonts, sizes, or positions.
"""
from __future__ import annotations
from pptx import Presentation


def render_pptx(slides: list[dict], mcqs: list[dict], output_path: str) -> None:
    prs = Presentation()

    for spec in slides:
        layout = spec.get("layout", "bullets")
        if layout == "title":
            _add_title_slide(prs, spec)
        elif layout == "two_column":
            _add_two_column_slide(prs, spec)
        elif layout == "image_text":
            _add_image_text_slide(prs, spec)
        else:
            # bullets is the default; unknown layouts fall back here
            _add_bullet_slide(prs, spec)

    for mcq in mcqs:
        _add_mcq_slide(prs, mcq)

    prs.save(output_path)


def _add_title_slide(prs: Presentation, spec: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = spec.get("title", "")
    if len(slide.placeholders) > 1 and spec.get("subtitle"):
        slide.placeholders[1].text = spec["subtitle"]


def _add_bullet_slide(prs: Presentation, spec: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = spec.get("title", "")
    body = slide.placeholders[1].text_frame
    bullets = spec.get("bullets") or []
    if not bullets:
        body.text = spec.get("body", "") or ""
        return
    body.text = bullets[0]
    for bullet in bullets[1:]:
        p = body.add_paragraph()
        p.text = bullet


def _add_two_column_slide(prs: Presentation, spec: dict) -> None:
    # Default template's "Two Content" layout is at index 3
    slide = prs.slides.add_slide(prs.slide_layouts[3])
    slide.shapes.title.text = spec.get("title", "")
    left = slide.placeholders[1].text_frame
    right = slide.placeholders[2].text_frame
    left.text = spec.get("left_column", "") or ""
    right.text = spec.get("right_column", "") or ""


def _add_image_text_slide(prs: Presentation, spec: dict) -> None:
    # No image asset in prototype; render as title + body (Title and Content layout)
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = spec.get("title", "")
    body = slide.placeholders[1].text_frame
    body.text = spec.get("body", "") or ""


def _add_mcq_slide(prs: Presentation, mcq: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = mcq["question"]
    body = slide.placeholders[1].text_frame
    options = mcq["options"]
    body.text = f"A. {options[0]}"
    for i, label in enumerate(["B", "C", "D"], start=1):
        p = body.add_paragraph()
        p.text = f"{label}. {options[i]}"
    p = body.add_paragraph()
    p.text = f"Answer: {mcq['answer']} — {mcq.get('explanation', '')}"
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
uv run pytest tests/test_pptx_formatter.py -v
```
Expected: all 3 tests PASS.

- [ ] **Step 5: Eyeball one rendered file**

Run:
```bash
uv run python -c "
from src.pptx_formatter import render_pptx
render_pptx(
    [
        {'layout': 'title', 'title': 'Photosynthesis', 'subtitle': 'Grade 7'},
        {'layout': 'bullets', 'title': 'Inputs', 'bullets': ['Sunlight', 'Water', 'CO2']},
    ],
    [{'question': 'What gas?', 'options': ['O2','CO2','N2','H2'], 'answer': 'B', 'explanation': 'CO2 is absorbed.'}],
    './outputs/_sanity.pptx',
)
print('wrote ./outputs/_sanity.pptx')
" && mkdir -p outputs && open outputs/_sanity.pptx
```
Expected: Keynote opens the file with NO "needs repair" warning, 3 slides visible (title, bullets, MCQ).

- [ ] **Step 6: Commit**

Run:
```bash
git add prototype/src/pptx_formatter.py prototype/tests/test_pptx_formatter.py
git commit -m "feat: pptx formatter with TDD (title, bullets, two_column, image_text, MCQ layouts)"
```

---

## Task 5: PDF formatter (TDD)

**Files:**
- Test: `prototype/tests/test_pdf_formatter.py`
- Create: `prototype/src/pdf_formatter.py`

- [ ] **Step 1: Write the failing test**

Create `prototype/tests/test_pdf_formatter.py`:
```python
"""TDD: PDF formatter renders reckoner JSON into a valid one-page .pdf."""
from pathlib import Path

from src.pdf_formatter import render_pdf


def test_render_pdf_creates_valid_file(tmp_path: Path):
    reckoner = {
        "title": "Photosynthesis quick reference",
        "sections": [
            {"heading": "What is photosynthesis?",
             "body": "The process plants use to make food from sunlight, water, and CO2."},
            {"heading": "Inputs", "body": "Sunlight, water (H2O), carbon dioxide (CO2)."},
            {"heading": "Outputs", "body": "Glucose (food) and oxygen (O2)."},
            {"heading": "Where it happens", "body": "In the chloroplasts of plant cells."},
        ],
    }
    out = tmp_path / "reckoner.pdf"

    render_pdf(reckoner, str(out))

    assert out.exists(), "pdf file was not created"
    assert out.stat().st_size > 1_000, "pdf file looks empty"

    # PDF files start with "%PDF"
    with open(out, "rb") as f:
        header = f.read(4)
    assert header == b"%PDF", f"not a valid PDF (header was {header!r})"


def test_render_pdf_handles_missing_title(tmp_path: Path):
    reckoner = {"sections": [{"heading": "Only section", "body": "Only body."}]}
    out = tmp_path / "no_title.pdf"
    render_pdf(reckoner, str(out))
    assert out.exists()
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
uv run pytest tests/test_pdf_formatter.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'src.pdf_formatter'`.

- [ ] **Step 3: Implement the formatter**

Create `prototype/src/pdf_formatter.py`:
```python
"""Render reckoner JSON into a .pdf file using reportlab.

The renderer owns all typography and layout. The LLM only supplies headings and body text.
"""
from __future__ import annotations
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer


def render_pdf(reckoner: dict, output_path: str) -> None:
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    story: list = []

    title = reckoner.get("title")
    if title:
        story.append(Paragraph(title, styles["Title"]))
        story.append(Spacer(1, 0.4 * cm))

    for section in reckoner.get("sections", []):
        story.append(Paragraph(section["heading"], styles["Heading2"]))
        story.append(Paragraph(section["body"], styles["BodyText"]))
        story.append(Spacer(1, 0.3 * cm))

    doc.build(story)
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
uv run pytest tests/test_pdf_formatter.py -v
```
Expected: both tests PASS.

- [ ] **Step 5: Eyeball one rendered file**

Run:
```bash
uv run python -c "
from src.pdf_formatter import render_pdf
render_pdf({
    'title': 'Photosynthesis quick reference',
    'sections': [
        {'heading': 'What', 'body': 'Plants make food from sunlight, water, and CO2.'},
        {'heading': 'Where', 'body': 'In the chloroplasts of plant cells.'},
    ],
}, './outputs/_sanity.pdf')
print('wrote ./outputs/_sanity.pdf')
" && open outputs/_sanity.pdf
```
Expected: Preview opens a clean one-page PDF with the title and two sections rendered.

- [ ] **Step 6: Run the full test suite**

Run:
```bash
uv run pytest -v
```
Expected: ALL tests pass (smoke + schemas + pptx + pdf).

- [ ] **Step 7: Commit**

Run:
```bash
git add prototype/src/pdf_formatter.py prototype/tests/test_pdf_formatter.py
git commit -m "feat: pdf formatter with TDD (title + headings + bodies on A4)"
```

---

## Task 6: LangFlow first run + Anthropic node verification

**Files:** none created in this task; this is environment verification.

- [ ] **Step 1: Start LangFlow**

Run (from `prototype/`):
```bash
uv run langflow run --host 127.0.0.1 --port 7860
```
Expected: terminal prints `Welcome to LangFlow` and a URL `http://127.0.0.1:7860`. Leave this running. Open the URL in a browser.

- [ ] **Step 2: Confirm the LangFlow UI loads**

In the browser at `http://127.0.0.1:7860`:
- You should see the LangFlow main page (Flows / Components / etc.)
- Click "+ New Flow" → "Blank Flow"

Expected: an empty canvas opens with a left-hand component palette.

- [ ] **Step 3: Drag an Anthropic node onto the canvas and verify it can call Claude**

- In the component palette search box, type `Anthropic`
- Drag the **Anthropic** model node onto the canvas
- Click the node; fill the fields:
  - **Model:** `claude-sonnet-4-6`
  - **Anthropic API Key:** paste your key (or set via the `ANTHROPIC_API_KEY` env var before starting LangFlow — see Step 1 note below)
  - **Input:** type a literal test prompt: `Reply with the word "ready"`
- Click the **Run** button on the Anthropic node (the play icon)

Expected: the node shows a green success indicator and the output panel shows the model's reply (containing "ready").

> **Note:** If LangFlow doesn't pick up `ANTHROPIC_API_KEY` from your shell, stop it (`Ctrl-C`), then re-run with the env var inline:
> ```bash
> ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2) uv run langflow run --host 127.0.0.1 --port 7860
> ```

- [ ] **Step 4: Delete the test node and save the empty flow**

- Right-click the Anthropic node → Delete
- Click the **Save** button (top right) — name the flow `wtsagnt_prototype`

Expected: the flow appears under your Flows list. No commit needed for the empty canvas yet.

---

## Task 7: PPT custom LangFlow component

**Files:**
- Create: `prototype/langflow_components/pptx_node.py`

- [ ] **Step 1: Write the PPT custom component**

Create `prototype/langflow_components/pptx_node.py`:
```python
"""LangFlow custom component that wraps src.pptx_formatter.render_pptx.

Inputs:
- slides_text: JSON string from upstream PPT-content Claude node (or pasted manually)
- mcqs_text:   JSON string from upstream MCQ Claude node
- output_dir:  base directory; files go to <output_dir>/<UTC-timestamp>/lesson.pptx

Output:
- A Data record containing the absolute path to the written .pptx
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the prototype root is importable so we can pull in src.pptx_formatter
_PROTOTYPE_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROTOTYPE_ROOT not in sys.path:
    sys.path.insert(0, _PROTOTYPE_ROOT)

from langflow.custom import Component
from langflow.io import MessageTextInput, StrInput, Output
from langflow.schema import Data

from src.pptx_formatter import render_pptx


def _coerce_list(payload: str, key: str) -> list[dict]:
    """Parse a JSON string and unwrap to a list. Accepts either:
       - a top-level list:        [{...}, {...}]
       - an object with the key:  {"<key>": [{...}, {...}]}
    """
    data = json.loads(payload)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and key in data and isinstance(data[key], list):
        return data[key]
    raise ValueError(f"Expected a list or an object with '{key}' key, got: {type(data).__name__}")


class PPTXFormatterComponent(Component):
    display_name = "Format to PPTX"
    description = "Render slide JSON + MCQ JSON into a .pptx (lesson + MCQ slides)."
    icon = "file-text"
    name = "PPTXFormatter"

    inputs = [
        MessageTextInput(name="slides_text", display_name="Slides JSON", required=True),
        MessageTextInput(name="mcqs_text", display_name="MCQs JSON", required=True),
        StrInput(name="output_dir", display_name="Output Directory", value="./outputs"),
    ]

    outputs = [
        Output(display_name="File Path", name="file_path", method="render"),
    ]

    def render(self) -> Data:
        slides = _coerce_list(self.slides_text, "slides")
        mcqs = _coerce_list(self.mcqs_text, "mcqs")

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = os.path.join(self.output_dir, ts)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.abspath(os.path.join(out_dir, "lesson.pptx"))

        render_pptx(slides, mcqs, out_path)

        self.status = f"Saved {out_path}"
        return Data(data={"file_path": out_path, "format": "pptx"})
```

- [ ] **Step 2: Make LangFlow load custom components from this directory**

Stop the running LangFlow (`Ctrl-C` in its terminal). Restart with the components path:
```bash
LANGFLOW_COMPONENTS_PATH=./langflow_components \
ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2) \
uv run langflow run --host 127.0.0.1 --port 7860
```
Expected: terminal logs mention loading custom components from `./langflow_components`.

- [ ] **Step 3: Confirm the node appears in the LangFlow palette**

In the browser, open the saved `wtsagnt_prototype` flow. In the component palette, search for `Format to PPTX`.

Expected: the custom node appears under a "Custom" section (or similar) and can be dragged onto the canvas.

> **If the node does not appear:** check the LangFlow logs for an import error in `pptx_node.py`. The most common cause is the `from langflow.custom import Component` import path differing between LangFlow versions. If your version uses `langflow.custom.custom_component`, edit that import accordingly.

- [ ] **Step 4: Commit**

Run:
```bash
git add prototype/langflow_components/pptx_node.py
git commit -m "feat: LangFlow custom component wrapping pptx_formatter"
```

---

## Task 8: PDF custom LangFlow component

**Files:**
- Create: `prototype/langflow_components/pdf_node.py`

- [ ] **Step 1: Write the PDF custom component**

Create `prototype/langflow_components/pdf_node.py`:
```python
"""LangFlow custom component that wraps src.pdf_formatter.render_pdf.

Input:
- reckoner_text: JSON string from upstream Reckoner Claude node

Output:
- A Data record containing the absolute path to the written .pdf
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_PROTOTYPE_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROTOTYPE_ROOT not in sys.path:
    sys.path.insert(0, _PROTOTYPE_ROOT)

from langflow.custom import Component
from langflow.io import MessageTextInput, StrInput, Output
from langflow.schema import Data

from src.pdf_formatter import render_pdf


class PDFFormatterComponent(Component):
    display_name = "Format to PDF"
    description = "Render reckoner JSON into a one-page .pdf handout."
    icon = "file-text"
    name = "PDFFormatter"

    inputs = [
        MessageTextInput(name="reckoner_text", display_name="Reckoner JSON", required=True),
        StrInput(name="output_dir", display_name="Output Directory", value="./outputs"),
    ]

    outputs = [
        Output(display_name="File Path", name="file_path", method="render"),
    ]

    def render(self) -> Data:
        reckoner = json.loads(self.reckoner_text)
        if not isinstance(reckoner, dict):
            raise ValueError(f"Reckoner JSON must be an object, got: {type(reckoner).__name__}")

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = os.path.join(self.output_dir, ts)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.abspath(os.path.join(out_dir, "reckoner.pdf"))

        render_pdf(reckoner, out_path)

        self.status = f"Saved {out_path}"
        return Data(data={"file_path": out_path, "format": "pdf"})
```

- [ ] **Step 2: Reload LangFlow and confirm both nodes are available**

Stop LangFlow (`Ctrl-C`) and restart with the same command as Task 7 Step 2. In the browser, search the palette for `Format to PDF`.

Expected: both `Format to PPTX` and `Format to PDF` are draggable.

- [ ] **Step 3: Commit**

Run:
```bash
git add prototype/langflow_components/pdf_node.py
git commit -m "feat: LangFlow custom component wrapping pdf_formatter"
```

---

## Task 9: Build the LangFlow canvas (7 wired nodes)

**Files:** none created here; the canvas state is saved inside LangFlow's database and exported in Task 11.

This task is UI clicks. Follow them in order. The end state is a canvas matching the diagram in the spec.

- [ ] **Step 1: Open the saved flow and clear it**

In the browser at `http://127.0.0.1:7860`, open the `wtsagnt_prototype` flow. Delete any existing nodes. You should have an empty canvas.

- [ ] **Step 2: Add the Input node (Text Input)**

- In the component palette, search `Text Input` and drag a **Text Input** onto the canvas (top-left of the canvas area).
- Rename it (gear icon → Display Name): `Transcript Input`
- Open `samples/transcript.txt` in your editor, copy the entire transcript, paste it into the node's **Text** field.

- [ ] **Step 3: Add and configure the Intent + Prompt Engineering Anthropic node**

- Search `Prompt` and drag a **Prompt Template** node onto the canvas, to the right of the Text Input.
  - Rename it: `Intent Prompt`
  - **Template** field: paste the contents of `INTENT_AND_PROMPT_ENGINEERING` from `prototype/src/prompts.py` (everything between the triple-quoted strings)
  - The `{transcript}` placeholder will become a wired input.
- Search `Anthropic` and drag an **Anthropic** model node next to the Prompt Template.
  - Rename it: `Intent + Prompt Engineering`
  - **Model:** `claude-sonnet-4-6`
  - **Max Tokens:** `2048`
  - **Temperature:** `0.3`
  - **API Key:** your `ANTHROPIC_API_KEY` (or leave to env)

- Wire: `Transcript Input` (Output: text) → `Intent Prompt` (Input: `transcript`)
- Wire: `Intent Prompt` (Output: prompt text) → `Intent + Prompt Engineering` (Input: input/message)

- [ ] **Step 4: Add the three downstream Anthropic nodes (PPT, MCQ, Reckoner)**

Repeat the Prompt-Template + Anthropic pattern three times, in parallel (place them in a vertical column to the right of the Intent node):

For each of `PPT Content`, `MCQ Generator`, `Reckoner Content`:
- Drag a **Prompt Template** + an **Anthropic** node onto the canvas
- Paste the matching prompt from `prototype/src/prompts.py`:
  - `PPT Content` → `PPT_CONTENT_GENERATION`
  - `MCQ Generator` → `MCQ_GENERATION`
  - `Reckoner Content` → `RECKONER_GENERATION`
- Configure each Anthropic node with `claude-sonnet-4-6`, Max Tokens `3000`, Temperature `0.4`

- [ ] **Step 5: Wire the Intent output into all three downstream prompt templates**

The Intent node outputs a JSON string with `ppt_prompt`, `mcq_prompt`, `reckoner_prompt` fields. The simplest robust wiring (no JSON-parser node needed):

For each of the three downstream Prompt Templates, **change the template variable from `{ppt_prompt}` (or `{mcq_prompt}` / `{reckoner_prompt}`) to `{full_intent_json}`** at the top of the template, and prepend this short directive:

```
You will receive a JSON object below. Use ONLY the value of the `<FIELD>` field
as your brief; ignore other fields.

JSON:
{full_intent_json}

Your task continues below as already described.
```

Replace `<FIELD>` with `ppt_prompt` / `mcq_prompt` / `reckoner_prompt` for each respective node.

Now wire `Intent + Prompt Engineering` (Output: message text) → each of the three downstream Prompt Templates' `full_intent_json` input.

> **Why this kludge:** LangFlow has version-specific JSON-parser nodes that vary in shape. Sending the whole JSON downstream and instructing each model to focus on its field is a few extra tokens per call but works on any LangFlow version. This is acceptable for prototype-grade; in real development on N8n this would be a proper field-extraction step.

- [ ] **Step 6: Add the two formatter nodes and wire them**

- Drag `Format to PPTX` onto the canvas (right side, top)
- Drag `Format to PDF` onto the canvas (right side, bottom)
- Wire:
  - `PPT Content` (Output: message text) → `Format to PPTX` (`slides_text`)
  - `MCQ Generator` (Output: message text) → `Format to PPTX` (`mcqs_text`)
  - `Reckoner Content` (Output: message text) → `Format to PDF` (`reckoner_text`)
- Leave `output_dir` at default `./outputs`

- [ ] **Step 7: Save the flow**

Click **Save** (top right). The canvas should now match the spec: 1 input → 1 intent → 3 fan-out generators → 2 formatters. Plus 3 prompt-template nodes which are part of LangFlow's idiom but conceptually fold into the agent nodes for spec-counting purposes.

- [ ] **Step 8: Visual sanity check — count nodes**

Expected on the canvas:
- 1 Text Input
- 4 Prompt Templates (1 intent + 3 downstream)
- 4 Anthropic LLM nodes (1 intent + 3 downstream)
- 2 Custom formatter nodes

That's 11 boxes drawn. The spec's "8 nodes" maps as: Input (1) + Intent+Prompt (1 conceptual = 1 PT + 1 LLM = 2 drawn) + 3 fan-out generators (3 conceptual = 3 PT + 3 LLM = 6 drawn) + 2 formatters (2) + Output (the formatter outputs themselves) = **8 conceptual / 11 drawn**. Note this in the demo so Senthil doesn't expect exactly 8 boxes.

- [ ] **Step 9: Take a screenshot of the canvas for the demo handoff**

Save it to `prototype/docs/canvas-screenshot.png` (create the dir if needed). This is the artifact Senthil will see before the run.

---

## Task 10: End-to-end run + verification

- [ ] **Step 1: Click Run on the final downstream node (`Format to PDF`)**

LangFlow will execute the whole upstream graph to satisfy this node's inputs, then the PPTX node will execute when its downstream is triggered (or you can click both formatters in sequence).

Expected: all 4 Anthropic nodes light up green (one at a time, then 3 in parallel), then both formatter nodes light up green. Total wall-clock ≤2 minutes (depends on Claude latency).

- [ ] **Step 2: Confirm both output files exist**

Run (in a new terminal, from `prototype/`):
```bash
ls -la outputs/*/
```
Expected: a directory like `outputs/20260513T...Z/` containing both `lesson.pptx` and `reckoner.pdf`, each >5 KB.

- [ ] **Step 3: Open the .pptx in Keynote**

Run:
```bash
open outputs/*/lesson.pptx
```
Expected:
- Keynote opens the file with **NO** "needs repair" warning
- Around 10 content slides + 5 MCQ slides (15 total, ±2)
- Layouts are visually varied (not all bullet walls)
- Each MCQ slide has 4 options A/B/C/D + an "Answer: X" line at the bottom

If the file fails to open or shows "repair" — see Troubleshooting at the end of this plan.

- [ ] **Step 4: Open the .pdf in Preview**

Run:
```bash
open outputs/*/reckoner.pdf
```
Expected:
- Preview opens a 1–2 page document
- A title at the top, 3–6 headed sections below
- Looks handout-grade (real typography, not a wall of unstyled text)

- [ ] **Step 5: If both files look clean, the prototype is functionally done. Commit the canvas state**

Note: the LangFlow canvas state lives in LangFlow's local database, not yet in the repo. Export happens in Task 11. For now:

```bash
cd /Users/newuser/Projects/Personal/wtsagnt
git status
# Should show no unstaged changes (no source files were edited in Tasks 9-10)
```

- [ ] **Step 6: If a file looks broken, debug and re-run**

Common failures:
- **"needs repair" in Keynote:** open the `lesson.pptx` and check the Anthropic PPT Content node's output — the LLM may have returned text that wasn't valid JSON, or used an unsupported layout. Edit the Prompt Template node to add "Respond with ONLY a JSON object, no prose, no markdown fences" if missing. Re-run.
- **Empty PDF / one blank page:** check the Reckoner Anthropic node's output — likely returned an empty `sections` array. Increase Max Tokens or tighten the prompt.
- **An Anthropic node fails with a JSON parse error from the formatter:** the LLM wrapped the JSON in markdown fences (` ```json ... ``` `). Add explicit "no markdown" instruction to the prompt and re-run. Or strip the fences in the formatter's `_coerce_list` — a small one-liner fix.

---

## Task 11: Export flow + write README

**Files:**
- Create: `prototype/flows/wtsagnt_prototype.json`
- Create: `prototype/README.md`

- [ ] **Step 1: Export the LangFlow flow as JSON**

In the LangFlow UI, with the `wtsagnt_prototype` flow open:
- Click the menu (•••) on the flow → **Export**
- Save the file as `prototype/flows/wtsagnt_prototype.json`

Verify:
```bash
ls -la prototype/flows/wtsagnt_prototype.json
```
Expected: a non-empty `.json` file (typically 20–80 KB).

- [ ] **Step 2: Write the README**

Create `prototype/README.md`:
```markdown
# wtsagnt Prototype

Local LangFlow demo: paste a teacher transcript → multi-agent network produces
a `.pptx` lesson deck (with MCQs) and a `.pdf` ready-reckoner.

Spec: [../docs/superpowers/specs/2026-05-13-wtsagnt-prototype-design.md](../docs/superpowers/specs/2026-05-13-wtsagnt-prototype-design.md)
Plan: [../docs/superpowers/plans/2026-05-13-wtsagnt-prototype.md](../docs/superpowers/plans/2026-05-13-wtsagnt-prototype.md)

## One-time setup

1. Install `uv` if you don't have it:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. Install dependencies:
   ```bash
   uv sync
   ```
3. Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`.
4. Confirm the API key works:
   ```bash
   uv run pytest tests/test_smoke_anthropic.py -v
   ```

## Run the tests

```bash
uv run pytest -v
```
All four test files should pass (smoke, schemas, pptx, pdf).

## Run the demo

1. Start LangFlow with the custom components path:
   ```bash
   LANGFLOW_COMPONENTS_PATH=./langflow_components \
   ANTHROPIC_API_KEY=$(grep ANTHROPIC_API_KEY .env | cut -d= -f2) \
   uv run langflow run --host 127.0.0.1 --port 7860
   ```
2. Open `http://127.0.0.1:7860` in a browser.
3. **First time only:** in the UI, import `flows/wtsagnt_prototype.json` (Flows → Import).
4. Open the flow. The Text Input node is pre-filled with the sample transcript;
   replace it with any teacher transcript you want.
5. Click **Run** on the `Format to PDF` node (or trigger each formatter).
6. Wait ~1–2 minutes. Outputs land in `outputs/<UTC-timestamp>/`:
   - `lesson.pptx` (open in Keynote / PowerPoint)
   - `reckoner.pdf` (open in Preview / any PDF viewer)

## What this prototype is — and is NOT

**Is:** a working demonstration that the multi-agent shape from Senthil's
workflow diagram is viable. Real Claude calls, real document outputs.

**Is NOT:** voice ingress, WhatsApp delivery, Google Drive upload, Google
Classroom distribution, rework loop, approval flow, multi-tenant, scale-ready.
All of those land in real development on the locked stack (TanStack + N8n +
LangChain + LangFlow + Supabase + Railway).

## Troubleshooting

- **Custom node doesn't appear in palette:** restart LangFlow with
  `LANGFLOW_COMPONENTS_PATH=./langflow_components` set, and check the LangFlow
  logs for an import error in `pptx_node.py` / `pdf_node.py`. The most likely
  cause is a LangFlow version where `from langflow.custom import Component`
  has moved — see the LangFlow docs for your installed version.
- **PPT opens with "needs repair":** the LLM returned slide JSON with an
  unsupported layout name or markdown-fenced output. See plan Task 10 Step 6.
- **API key not picked up:** export it explicitly in the same shell that
  starts `langflow run`, or pass it inline as shown above.
```

- [ ] **Step 3: Commit the flow export and README**

Run:
```bash
git add prototype/flows/wtsagnt_prototype.json prototype/README.md
git commit -m "docs: README for prototype demo + export LangFlow canvas as JSON"
```

- [ ] **Step 4: Final smoke run from a fresh state**

Verify the README's instructions actually work by re-running the demo end-to-end one more time. This is the "imagine Senthil's about to do it" check.

Run:
```bash
uv run pytest -v
```
Expected: all tests pass.

Then start LangFlow per the README, open the flow, run it, confirm both files appear.

- [ ] **Step 5: Ready for Senthil**

The prototype is demoable. Tell Muthukumar to:
1. Open `http://127.0.0.1:7860` on the demo machine
2. Open the `wtsagnt_prototype` flow
3. Walk Senthil through the canvas left-to-right
4. Hit Run, open both output files
5. Discuss next steps (likely: install BMAD, run SDD on broader business context, then start real development on the locked stack)

---

## Self-Review

**Spec coverage (8-node graph):** Input ✓ (Text Input, Task 9 Step 2), Intent+Prompt Engineering ✓ (PT+Anthropic, Task 9 Step 3), 3 fan-out generators ✓ (Task 9 Step 4–5), 2 formatters ✓ (Task 9 Step 6), 2 output files ✓ (Task 10 Step 2–4). All 8 conceptual nodes covered.

**Spec coverage (data flow):** transcript → Intent JSON with `{subject, grade, topic, duration_min, n_slides, n_mcqs, ppt_prompt, mcq_prompt, reckoner_prompt}` ✓ (schemas.py + prompts.py), 3 parallel Claude calls produce slide/MCQ/reckoner JSON ✓ (Tasks 4 + 5 + canvas Task 9), formatters write to `./outputs/<timestamp>/lesson.pptx` + `reckoner.pdf` ✓ (Tasks 7 + 8).

**Verification gates from spec:**
1. Canvas opens with 8 conceptual nodes wired → Task 9
2. ≤2 min E2E run → Task 10 Step 1
3. Both files at `./outputs/<timestamp>/` → Task 10 Step 2
4. `.pptx` opens clean in Keynote with ~10 + 5 slides → Task 10 Step 3
5. `.pdf` opens clean in Preview, 1–2 pages, handout-grade → Task 10 Step 4
6. Senthil approves → Task 11 Step 5

All 6 verification points covered.

**Out-of-scope items not built:** STT, WhatsApp, Drive, Classroom, email, approval flow, rework loop, TanStack, N8n, Supabase, Railway, multi-tenant — none appear in any task. ✓

**Placeholder scan:** no TBDs, no "implement later," no "add appropriate error handling." Each step has runnable code or runnable commands.

**Type consistency:** `render_pptx(slides, mcqs, output_path)` and `render_pdf(reckoner, output_path)` referenced consistently in source, tests, and the LangFlow custom components. `Intent` schema fields match across `schemas.py`, `prompts.py`, and the canvas wiring.

**Known risk:** LangFlow's exact import paths for `Component`, `MessageTextInput`, `StrInput`, `Output` shift between versions. The plan calls this out in Task 7 Step 3 with a fallback instruction. If a fresh engineer hits import errors, they have explicit guidance to consult the LangFlow docs for their installed version. This is acceptable for prototype-grade and won't sink the day.
