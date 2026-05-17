"""Render a Worksheet JSON into a printable student-facing PDF.

This is a separate artifact from the reckoner: the reckoner is for the
teacher (lesson plan + pedagogy), the worksheet is for the student (questions
to attempt). The teacher hands one to themselves, photocopies the other.
"""
from __future__ import annotations
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.lib import colors as rl_colors

from src.fonts import pdf_font_for_language
from src.theme import Palette, palette_for_subject


def _rl_color(rgb: tuple[int, int, int]):
    from reportlab.lib.colors import Color
    r, g, b = rgb
    return Color(r / 255, g / 255, b / 255)


def _themed_styles(palette: Palette, language: str | None = None):
    styles = getSampleStyleSheet()
    styles["Title"].textColor = _rl_color(palette.primary)
    styles["Heading2"].textColor = _rl_color(palette.primary)
    font_name = pdf_font_for_language(language)
    if font_name:
        for style_name in ("Title", "Heading2", "BodyText", "Italic", "Normal"):
            styles[style_name].fontName = font_name
    return styles


def _build_story(
    worksheet: dict, *, subject: str | None = None, language: str | None = None,
) -> list:
    palette = palette_for_subject(subject)
    styles = _themed_styles(palette, language=language)
    body = styles["BodyText"]
    story: list = []

    title = worksheet.get("title", "Worksheet")
    instructions = worksheet.get("instructions") or ""

    story.append(Paragraph(title, styles["Title"]))
    # Name + Date strip — leave blanks for the student to fill in
    story.append(Paragraph(
        "Name: ________________________   Date: ____________   Score: _____ / _____",
        styles["BodyText"],
    ))
    story.append(Spacer(1, 0.3 * cm))
    if instructions:
        story.append(Paragraph(f"<i>{instructions}</i>", styles["BodyText"]))
        story.append(Spacer(1, 0.3 * cm))

    for i, activity in enumerate(worksheet.get("activities", []), start=1):
        kind = activity.get("kind", "question")
        prompt = activity.get("prompt", "")
        story.append(Paragraph(f"<b>{i}.</b> {prompt}", body))

        if kind == "match":
            left = activity.get("left_items") or []
            right = activity.get("right_items") or []
            # Render side-by-side columns for students to draw lines between
            rows = []
            for j in range(max(len(left), len(right))):
                lv = left[j] if j < len(left) else ""
                rv = right[j] if j < len(right) else ""
                rows.append([f"{chr(ord('A') + j)}. {lv}", f"{j + 1}. {rv}"])
            if rows:
                tbl = Table(rows, colWidths=[8 * cm, 8 * cm])
                tbl.setStyle(TableStyle([
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]))
                story.append(tbl)
        elif kind == "fill_blank":
            # The prompt itself contains "___" — render as-is, plus a small
            # answer line below for additional working if needed
            story.append(Spacer(1, 0.2 * cm))
        else:
            # question — render 2 blank lines for the student's answer
            story.append(Paragraph("________________________________________________________", body))
            story.append(Paragraph("________________________________________________________", body))

        story.append(Spacer(1, 0.35 * cm))

    return story


def render_worksheet_pdf(
    worksheet: dict,
    output_path: str,
    *,
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
    doc.build(_build_story(worksheet, subject=subject, language=language))
