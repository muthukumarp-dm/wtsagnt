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

    prs = Presentation(str(out))
    assert len(prs.slides) == len(slides) + len(mcqs)
    assert prs.slides[0].shapes.title.text == "Photosynthesis"
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
