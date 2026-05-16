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

    with open(out, "rb") as f:
        header = f.read(4)
    assert header == b"%PDF", f"not a valid PDF (header was {header!r})"


def test_render_pdf_handles_missing_title(tmp_path: Path):
    reckoner = {"sections": [{"heading": "Only section", "body": "Only body."}]}
    out = tmp_path / "no_title.pdf"
    render_pdf(reckoner, str(out))
    assert out.exists()
