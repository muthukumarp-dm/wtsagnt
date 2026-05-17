"""Render reckoner JSON into a .pdf file using reportlab.

The renderer owns all typography and layout. The LLM only supplies headings and body text.
"""
from __future__ import annotations
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak


def _build_story(
    reckoner: dict,
    *,
    teacher_name: str | None = None,
    teaching_tips: list[dict] | None = None,
) -> list:
    """Build the list of reportlab flowables for the reckoner. Split out so
    tests can introspect the rendered content without reading the compressed
    PDF stream.

    The reckoner sections are student-facing. Teaching tips, if supplied, are
    rendered as a page-break-separated appendix labelled "For the teacher" so
    a teacher can hand the first page to students and keep the second page."""
    styles = getSampleStyleSheet()
    story: list = []

    title = reckoner.get("title")
    if title:
        story.append(Paragraph(title, styles["Title"]))
        if teacher_name:
            story.append(Paragraph(f"Prepared by {teacher_name}", styles["Italic"]))
        story.append(Spacer(1, 0.4 * cm))

    for section in reckoner.get("sections", []):
        story.append(Paragraph(section["heading"], styles["Heading2"]))
        story.append(Paragraph(section["body"], styles["BodyText"]))
        story.append(Spacer(1, 0.3 * cm))

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
        reckoner, teacher_name=teacher_name, teaching_tips=teaching_tips,
    ))
