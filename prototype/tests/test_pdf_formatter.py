"""TDD: PDF formatter renders the structured lesson reckoner."""
from pathlib import Path

from reportlab.platypus import Paragraph, PageBreak, Table

from src.pdf_formatter import render_pdf, _build_story


def _story_texts(story: list) -> list[str]:
    return [f.text for f in story if isinstance(f, Paragraph)]


_RECKONER = {
    "title": "Photosynthesis — grade 7 lesson plan",
    "one_line_summary": "Plants use sunlight, water, and CO2 to make food.",
    "materials": ["Whiteboard markers", "Printed worksheet", "Beaker with water"],
    "timeline": [
        {"minutes": "0-5 min", "activity": "Warm-up: leaf-in-water demo"},
        {"minutes": "5-15 min", "activity": "Introduce inputs/outputs on board"},
        {"minutes": "15-25 min", "activity": "Pair work: label the diagram"},
        {"minutes": "25-30 min", "activity": "Formative check + wrap-up"},
    ],
    "key_concepts": [
        "Sunlight is the energy source",
        "Chlorophyll captures light",
        "Glucose is the food plants make",
    ],
    "common_misconceptions": [
        "Plants 'eat' soil — they don't, they make their food in leaves",
        "Photosynthesis happens everywhere — actually mainly in leaves",
    ],
    "board_work": [
        "Inputs → leaf → outputs diagram",
        "List the three inputs",
        "Highlight chlorophyll as the converter",
    ],
    "formative_check": "Ask: what two outputs does photosynthesis make?",
}


def test_render_pdf_creates_valid_file(tmp_path: Path):
    out = tmp_path / "reckoner.pdf"
    render_pdf(_RECKONER, str(out))
    assert out.exists()
    assert out.stat().st_size > 1_000
    with open(out, "rb") as f:
        assert f.read(4) == b"%PDF"


def test_build_story_renders_each_structured_section():
    story = _build_story(_RECKONER)
    texts = _story_texts(story)
    assert "Materials" in texts
    assert "Lesson timeline" in texts
    assert "Key concepts" in texts
    assert "Common misconceptions" in texts
    assert "Board work" in texts
    assert "Formative check" in texts


def test_build_story_renders_timeline_as_table():
    story = _build_story(_RECKONER)
    tables = [f for f in story if isinstance(f, Table)]
    assert len(tables) == 1, "expected one timeline table in the story"


def test_build_story_includes_one_line_summary():
    story = _build_story(_RECKONER)
    assert _RECKONER["one_line_summary"] in _story_texts(story)


def test_build_story_omits_byline_when_no_teacher_name():
    texts = _story_texts(_build_story(_RECKONER))
    assert not any("Prepared by" in t for t in texts)


def test_build_story_includes_teacher_byline_when_set():
    texts = _story_texts(_build_story(_RECKONER, teacher_name="Ms. Priya"))
    assert "Prepared by Ms. Priya" in texts


def test_build_story_skips_empty_optional_sections():
    """If the LLM hands back an empty list for a section, we skip the heading
    rather than render an empty 'Materials' header."""
    sparse = {**_RECKONER, "materials": [], "board_work": []}
    texts = _story_texts(_build_story(sparse))
    assert "Materials" not in texts
    assert "Board work" not in texts
    assert "Key concepts" in texts  # the populated ones still render


def test_build_story_appends_teaching_tips_after_page_break():
    tips = [
        {"heading": "Misconception",
         "body": "Students often confuse photosynthesis with respiration."},
        {"heading": "Hook", "body": "Open with a leaf-in-water demo."},
    ]
    story = _build_story(_RECKONER, teaching_tips=tips)
    pb_idx = next(i for i, f in enumerate(story) if isinstance(f, PageBreak))
    after = _story_texts(story[pb_idx:])
    assert "For the teacher" in after
    assert "Misconception" in after
    assert "Hook" in after


def test_build_story_omits_tips_appendix_when_no_tips():
    story = _build_story(_RECKONER, teaching_tips=None)
    assert not any(isinstance(f, PageBreak) for f in story)
    assert "For the teacher" not in _story_texts(story)


def test_build_story_subject_palette_colors_title_and_headings():
    from src.theme import palette_for_subject
    story = _build_story(_RECKONER, subject="Science")
    expected = palette_for_subject("Science").primary
    title = next(f for f in story if isinstance(f, Paragraph) and f.text == _RECKONER["title"])
    c = title.style.textColor
    assert (round(c.red * 255), round(c.green * 255), round(c.blue * 255)) == expected


def test_render_pdf_full_render_with_everything(tmp_path: Path):
    tips = [{"heading": "Hook", "body": "Open with a demo."}]
    out = tmp_path / "full.pdf"
    render_pdf(_RECKONER, str(out), teacher_name="Ms. Priya",
               teaching_tips=tips, subject="Science")
    assert out.exists()
    with open(out, "rb") as f:
        assert f.read(4) == b"%PDF"
