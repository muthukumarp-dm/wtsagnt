"""Render MCQs as a printable student quiz PDF, with a teacher answer key
on a separate page.

The PPTX already has MCQ slides for projector-led review; this PDF is the
photocopy-and-hand-out artifact. The answer key on page 2 is for the
teacher to grade or self-check.
"""
from __future__ import annotations
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak,
)

from src.fonts import pdf_font_for_language
from src.theme import Palette, palette_for_subject


def _rl_color(rgb: tuple[int, int, int]) -> Color:
    r, g, b = rgb
    return Color(r / 255, g / 255, b / 255)


def _themed_styles(palette: Palette, language: str | None = None):
    styles = getSampleStyleSheet()
    primary = _rl_color(palette.primary)
    styles["Title"].textColor = primary
    styles["Heading2"].textColor = primary
    font_name = pdf_font_for_language(language)
    if font_name:
        for style_name in ("Title", "Heading2", "BodyText", "Italic", "Normal"):
            styles[style_name].fontName = font_name
    return styles


def _build_story(
    mcqs: list[dict],
    *,
    title: str = "Quiz",
    subject: str | None = None,
    language: str | None = None,
) -> list:
    palette = palette_for_subject(subject)
    styles = _themed_styles(palette, language=language)
    body = styles["BodyText"]
    story: list = [
        Paragraph(title, styles["Title"]),
        Paragraph(
            "Name: ________________________   Date: ____________   Score: _____ / _____",
            body,
        ),
        Spacer(1, 0.3 * cm),
        Paragraph(
            "<i>Circle the best answer for each question.</i>",
            body,
        ),
        Spacer(1, 0.4 * cm),
    ]

    for i, mcq in enumerate(mcqs, start=1):
        story.append(Paragraph(f"<b>{i}. {mcq.get('question', '')}</b>", body))
        options = mcq.get("options") or []
        for label, opt in zip(["A", "B", "C", "D"], options):
            story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;{label}. {opt}", body))
        story.append(Spacer(1, 0.3 * cm))

    # Answer key on its own page so the teacher can fold it off or
    # photocopy only page 1 for students.
    story.append(PageBreak())
    story.append(Paragraph("Answer key", styles["Title"]))
    story.append(Spacer(1, 0.3 * cm))
    for i, mcq in enumerate(mcqs, start=1):
        story.append(Paragraph(
            f"<b>{i}.</b> {mcq.get('answer', '?')} — {mcq.get('explanation', '')}",
            body,
        ))
        story.append(Spacer(1, 0.15 * cm))

    return story


def render_mcq_pdf(
    mcqs: list[dict],
    output_path: str,
    *,
    title: str = "Quiz",
    subject: str | None = None,
    language: str | None = None,
) -> None:
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    doc.build(_build_story(mcqs, title=title, subject=subject, language=language))
