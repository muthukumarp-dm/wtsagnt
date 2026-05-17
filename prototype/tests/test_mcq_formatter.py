"""TDD: standalone MCQ-quiz PDF renderer."""
from pathlib import Path

from reportlab.platypus import Paragraph, PageBreak

from src.mcq_formatter import render_mcq_pdf, _build_story


def _story_texts(story: list) -> list[str]:
    return [f.text for f in story if isinstance(f, Paragraph)]


_MCQS = [
    {"question": "What gas do plants take in?",
     "options": ["O2", "CO2", "N2", "H2"],
     "answer": "B",
     "explanation": "Plants absorb CO2 for photosynthesis."},
    {"question": "Where does photosynthesis happen?",
     "options": ["Roots", "Stem", "Chloroplasts", "Mitochondria"],
     "answer": "C",
     "explanation": "Chloroplasts contain chlorophyll."},
]


def test_render_mcq_pdf_creates_valid_file(tmp_path: Path):
    out = tmp_path / "quiz.pdf"
    render_mcq_pdf(_MCQS, str(out), title="Photosynthesis quiz")
    assert out.exists()
    with open(out, "rb") as f:
        assert f.read(4) == b"%PDF"


def test_build_story_renders_each_question_with_four_options():
    texts = _story_texts(_build_story(_MCQS, title="Quiz"))
    assert any("1. What gas do plants take in?" in t for t in texts)
    # Option labels rendered with the actual option text
    for label, opt in zip(["A", "B", "C", "D"], _MCQS[0]["options"]):
        assert any(f"{label}. {opt}" in t for t in texts)


def test_build_story_inserts_page_break_before_answer_key():
    story = _build_story(_MCQS, title="Quiz")
    pb_idx = next(i for i, f in enumerate(story) if isinstance(f, PageBreak))
    after = _story_texts(story[pb_idx:])
    assert "Answer key" in after
    # Answer-key entries contain the correct answer letter
    assert any("1." in t and "B" in t for t in after)


def test_build_story_renders_name_score_strip():
    texts = _story_texts(_build_story(_MCQS, title="Quiz"))
    assert any("Name:" in t and "Score:" in t for t in texts)


def test_build_story_subject_palette_colors_title():
    from src.theme import palette_for_subject
    story = _build_story(_MCQS, title="Photosynthesis quiz", subject="Science")
    expected = palette_for_subject("Science").primary
    title = next(f for f in story if isinstance(f, Paragraph) and f.text == "Photosynthesis quiz")
    c = title.style.textColor
    assert (round(c.red * 255), round(c.green * 255), round(c.blue * 255)) == expected


def test_render_mcq_pdf_with_subject(tmp_path: Path):
    out = tmp_path / "themed.pdf"
    render_mcq_pdf(_MCQS, str(out), title="Quiz", subject="Mathematics")
    assert out.exists()
