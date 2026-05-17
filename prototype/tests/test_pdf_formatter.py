"""TDD: PDF formatter renders reckoner JSON into a valid one-page .pdf."""
from pathlib import Path

from reportlab.platypus import Paragraph

from src.pdf_formatter import render_pdf, _build_story


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

    with open(out, "rb") as f:
        header = f.read(4)
    assert header == b"%PDF", f"not a valid PDF (header was {header!r})"


def test_render_pdf_handles_missing_title(tmp_path: Path):
    reckoner = {"sections": [{"heading": "Only section", "body": "Only body."}]}
    out = tmp_path / "no_title.pdf"
    render_pdf(reckoner, str(out))
    assert out.exists()


def _story_texts(story: list) -> list[str]:
    return [f.text for f in story if isinstance(f, Paragraph)]


def test_build_story_includes_teacher_byline():
    reckoner = {
        "title": "Photosynthesis reckoner",
        "sections": [{"heading": "What", "body": "It's a process."}],
    }
    texts = _story_texts(_build_story(reckoner, teacher_name="Ms. Priya"))
    assert "Prepared by Ms. Priya" in texts


def test_build_story_omits_byline_when_no_teacher_name():
    reckoner = {
        "title": "Photosynthesis reckoner",
        "sections": [{"heading": "What", "body": "It's a process."}],
    }
    texts = _story_texts(_build_story(reckoner))
    assert not any("Prepared by" in t for t in texts)


def test_build_story_omits_byline_when_no_title():
    """Byline is anchored to the title — no title, no byline."""
    reckoner = {"sections": [{"heading": "Only", "body": "Only body."}]}
    texts = _story_texts(_build_story(reckoner, teacher_name="Ms. Priya"))
    assert not any("Prepared by" in t for t in texts)


def test_render_pdf_with_teacher_name_still_produces_valid_pdf(tmp_path: Path):
    """End-to-end: render_pdf with teacher_name produces a valid PDF file."""
    reckoner = {
        "title": "Photosynthesis reckoner",
        "sections": [{"heading": "What", "body": "It's a process."}],
    }
    out = tmp_path / "branded.pdf"
    render_pdf(reckoner, str(out), teacher_name="Ms. Priya")
    assert out.exists()
    with open(out, "rb") as f:
        assert f.read(4) == b"%PDF"
