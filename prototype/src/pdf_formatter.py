"""Render reckoner JSON into a .pdf file using reportlab.

The renderer owns all typography and layout. The LLM only supplies headings and
body text. A subject-aware palette colors the title and section headings so the
PDF reads as intentional, not a default-themed Helvetica wall.
"""
from __future__ import annotations
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
)
from reportlab.lib import colors as rl_colors

from src.theme import Palette, palette_for_subject


def _rl_color(rgb: tuple[int, int, int]) -> Color:
    r, g, b = rgb
    return Color(r / 255, g / 255, b / 255)


def _themed_styles(palette: Palette):
    """Return a styles object with Title/Heading2 recolored from the palette."""
    styles = getSampleStyleSheet()
    primary = _rl_color(palette.primary)
    styles["Title"].textColor = primary
    styles["Heading2"].textColor = primary
    return styles


def _bullet_list(items: list[str], style) -> list:
    """Render a simple bullet list as a sequence of Paragraphs. Reportlab's
    ListFlowable is finicky with styles; manual bullets render predictably."""
    return [Paragraph(f"• {item}", style) for item in items]


def _timeline_table(timeline: list[dict], palette: Palette) -> Table:
    """Two-column table: minutes (palette-tinted) | activity. Visually distinct
    from a wall of bullets — the timeline is the spine of the lesson."""
    data = [[row.get("minutes", ""), row.get("activity", "")] for row in timeline]
    table = Table(data, colWidths=[3.5 * cm, 12.5 * cm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), _rl_color(palette.primary)),
        ("BACKGROUND", (0, 0), (0, -1), _rl_color(_lighten(palette.accent))),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, rl_colors.lightgrey),
    ]))
    return table


def _lighten(rgb: tuple[int, int, int], mix: float = 0.7) -> tuple[int, int, int]:
    """Mix an RGB toward white. mix=0 → original, mix=1 → white."""
    r, g, b = rgb
    return (
        int(r + (255 - r) * mix),
        int(g + (255 - g) * mix),
        int(b + (255 - b) * mix),
    )


def _build_story(
    reckoner: dict,
    *,
    teacher_name: str | None = None,
    teaching_tips: list[dict] | None = None,
    subject: str | None = None,
) -> list:
    """Build the list of reportlab flowables for the reckoner.

    The reckoner is a structured lesson-delivery plan: summary, materials,
    timeline, key concepts, common misconceptions, board work, formative
    check. Teaching tips, if supplied, are rendered as a page-break-separated
    appendix labelled "For the teacher" so a teacher can hand the first page
    to students and keep the second page."""
    palette = palette_for_subject(subject)
    styles = _themed_styles(palette)
    story: list = []

    title = reckoner.get("title")
    if title:
        story.append(Paragraph(title, styles["Title"]))
        if teacher_name:
            story.append(Paragraph(f"Prepared by {teacher_name}", styles["Italic"]))
        story.append(Spacer(1, 0.3 * cm))

    one_line = reckoner.get("one_line_summary")
    if one_line:
        story.append(Paragraph(one_line, styles["Italic"]))
        story.append(Spacer(1, 0.3 * cm))

    materials = reckoner.get("materials") or []
    if materials:
        story.append(Paragraph("Materials", styles["Heading2"]))
        story.extend(_bullet_list(materials, styles["BodyText"]))
        story.append(Spacer(1, 0.25 * cm))

    timeline = reckoner.get("timeline") or []
    if timeline:
        story.append(Paragraph("Lesson timeline", styles["Heading2"]))
        story.append(_timeline_table(timeline, palette))
        story.append(Spacer(1, 0.25 * cm))

    key_concepts = reckoner.get("key_concepts") or []
    if key_concepts:
        story.append(Paragraph("Key concepts", styles["Heading2"]))
        story.extend(_bullet_list(key_concepts, styles["BodyText"]))
        story.append(Spacer(1, 0.25 * cm))

    misconceptions = reckoner.get("common_misconceptions") or []
    if misconceptions:
        story.append(Paragraph("Common misconceptions", styles["Heading2"]))
        story.extend(_bullet_list(misconceptions, styles["BodyText"]))
        story.append(Spacer(1, 0.25 * cm))

    board_work = reckoner.get("board_work") or []
    if board_work:
        story.append(Paragraph("Board work", styles["Heading2"]))
        story.extend(_bullet_list(board_work, styles["BodyText"]))
        story.append(Spacer(1, 0.25 * cm))

    formative = reckoner.get("formative_check")
    if formative:
        story.append(Paragraph("Formative check", styles["Heading2"]))
        story.append(Paragraph(formative, styles["BodyText"]))
        story.append(Spacer(1, 0.25 * cm))

    if teaching_tips:
        story.append(PageBreak())
        story.append(Paragraph("For the teacher", styles["Title"]))
        story.append(Spacer(1, 0.4 * cm))
        for tip in teaching_tips:
            story.append(Paragraph(tip["heading"], styles["Heading2"]))
            story.append(Paragraph(tip["body"], styles["BodyText"]))
            story.append(Spacer(1, 0.3 * cm))

    return story


def render_pdf(
    reckoner: dict,
    output_path: str,
    *,
    teacher_name: str | None = None,
    teaching_tips: list[dict] | None = None,
    subject: str | None = None,
) -> None:
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    doc.build(_build_story(
        reckoner,
        teacher_name=teacher_name,
        teaching_tips=teaching_tips,
        subject=subject,
    ))
