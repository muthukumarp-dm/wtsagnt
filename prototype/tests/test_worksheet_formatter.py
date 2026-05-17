"""TDD: worksheet PDF renderer."""
from pathlib import Path

from reportlab.platypus import Paragraph, Table

from src.worksheet_formatter import render_worksheet_pdf, _build_story


def _story_texts(story: list) -> list[str]:
    return [f.text for f in story if isinstance(f, Paragraph)]


_WORKSHEET = {
    "title": "Photosynthesis — student worksheet",
    "instructions": "Answer all questions. Show your working.",
    "activities": [
        {"kind": "fill_blank",
         "prompt": "Plants need ___, ___, and ___ to make food.",
         "answer_hint": "sunlight, water, CO2"},
        {"kind": "question",
         "prompt": "Name two places in a leaf where photosynthesis happens.",
         "answer_hint": "chloroplasts in palisade cells; spongy mesophyll"},
        {"kind": "match",
         "prompt": "Match the input to its source.",
         "left_items": ["Sunlight", "Water", "CO2"],
         "right_items": ["From the air", "From the roots", "From the sun"],
         "answer_hint": "A=3, B=2, C=1"},
    ],
}


def test_render_worksheet_pdf_creates_valid_file(tmp_path: Path):
    out = tmp_path / "worksheet.pdf"
    render_worksheet_pdf(_WORKSHEET, str(out))
    assert out.exists()
    with open(out, "rb") as f:
        assert f.read(4) == b"%PDF"


def test_build_story_includes_title_and_instructions():
    texts = _story_texts(_build_story(_WORKSHEET))
    assert _WORKSHEET["title"] in texts
    assert any("Answer all questions" in t for t in texts)


def test_build_story_renders_name_score_strip():
    texts = _story_texts(_build_story(_WORKSHEET))
    assert any("Name:" in t and "Date:" in t and "Score:" in t for t in texts)


def test_build_story_renders_match_activity_as_table():
    tables = [f for f in _build_story(_WORKSHEET) if isinstance(f, Table)]
    assert len(tables) == 1, "match activity should render as one table"


def test_build_story_question_activities_get_answer_lines():
    """Open-ended question activities should produce blank lines for the
    student to write on."""
    story = _build_story({**_WORKSHEET, "activities": [_WORKSHEET["activities"][1]]})
    texts = _story_texts(story)
    underscore_lines = [t for t in texts if "____" in t]
    assert len(underscore_lines) >= 2, "expected at least 2 answer lines"


def test_build_story_subject_palette_colors_title():
    from src.theme import palette_for_subject
    story = _build_story(_WORKSHEET, subject="Science")
    expected = palette_for_subject("Science").primary
    title = next(f for f in story if isinstance(f, Paragraph) and f.text == _WORKSHEET["title"])
    c = title.style.textColor
    assert (round(c.red * 255), round(c.green * 255), round(c.blue * 255)) == expected


def test_render_worksheet_full(tmp_path: Path):
    out = tmp_path / "full_ws.pdf"
    render_worksheet_pdf(_WORKSHEET, str(out), subject="Science")
    assert out.exists()
