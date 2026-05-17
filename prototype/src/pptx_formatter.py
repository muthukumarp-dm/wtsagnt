"""Render slide JSON + MCQ JSON into a .pptx file using python-pptx.

The renderer owns ALL layout primitives. Callers (the LLM upstream) only pick
a layout name and supply content — they do not control fonts, sizes, or positions.
A subject-aware color palette is applied to title text and accent shapes so the
artifact reads as intentional rather than default-themed.
"""
from __future__ import annotations
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Emu, Pt

from src.theme import Palette, palette_for_subject


def render_pptx(
    slides: list[dict],
    mcqs: list[dict],
    output_path: str,
    *,
    teacher_name: str | None = None,
    subject: str | None = None,
) -> None:
    prs = Presentation()
    palette = palette_for_subject(subject)

    title_slide_done = False
    for spec in slides:
        layout = spec.get("layout", "bullets")
        if layout == "title":
            _add_title_slide(
                prs, spec, palette,
                teacher_name=teacher_name if not title_slide_done else None,
            )
            title_slide_done = True
        elif layout == "two_column":
            _add_two_column_slide(prs, spec, palette)
        elif layout == "image_text":
            _add_image_text_slide(prs, spec, palette)
        else:
            _add_bullet_slide(prs, spec, palette)

    for mcq in mcqs:
        _add_mcq_slide(prs, mcq, palette)

    prs.save(output_path)


def _rgb(palette_color: tuple[int, int, int]) -> RGBColor:
    return RGBColor(*palette_color)


def _color_title(slide, palette: Palette) -> None:
    """Recolor the title placeholder text to the palette's primary color."""
    title = slide.shapes.title
    if title is None:
        return
    for para in title.text_frame.paragraphs:
        for run in para.runs:
            run.font.color.rgb = _rgb(palette.primary)


def _add_accent_bar(slide, palette: Palette) -> None:
    """Draw a thin accent rectangle along the left edge of the slide. Visual
    differentiation against generic default-themed decks."""
    from pptx.enum.shapes import MSO_SHAPE
    width = Emu(120000)   # ~0.13 in
    height = slide.part.package.presentation_part.presentation.slide_height
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(palette.accent)
    shape.line.fill.background()


def _add_title_slide(
    prs: Presentation, spec: dict, palette: Palette,
    *, teacher_name: str | None = None,
) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = spec.get("title", "")
    subtitle_lines: list[str] = []
    if spec.get("subtitle"):
        subtitle_lines.append(spec["subtitle"])
    if teacher_name:
        subtitle_lines.append(f"Prepared by {teacher_name}")
    if subtitle_lines and len(slide.placeholders) > 1:
        slide.placeholders[1].text = "\n".join(subtitle_lines)
    _color_title(slide, palette)
    _add_accent_bar(slide, palette)


def _add_bullet_slide(prs: Presentation, spec: dict, palette: Palette) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = spec.get("title", "")
    body = slide.placeholders[1].text_frame
    bullets = spec.get("bullets") or []
    if not bullets:
        body.text = spec.get("body", "") or ""
    else:
        body.text = bullets[0]
        for bullet in bullets[1:]:
            p = body.add_paragraph()
            p.text = bullet
    _color_title(slide, palette)


def _add_two_column_slide(prs: Presentation, spec: dict, palette: Palette) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[3])
    slide.shapes.title.text = spec.get("title", "")
    left = slide.placeholders[1].text_frame
    right = slide.placeholders[2].text_frame
    left.text = spec.get("left_column", "") or ""
    right.text = spec.get("right_column", "") or ""
    _color_title(slide, palette)


def _add_image_text_slide(prs: Presentation, spec: dict, palette: Palette) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = spec.get("title", "")
    body = slide.placeholders[1].text_frame
    body.text = spec.get("body", "") or ""
    _color_title(slide, palette)


def _add_mcq_slide(prs: Presentation, mcq: dict, palette: Palette) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = mcq["question"]
    body = slide.placeholders[1].text_frame
    options = mcq["options"]
    body.text = f"A. {options[0]}"
    for i, label in enumerate(["B", "C", "D"], start=1):
        p = body.add_paragraph()
        p.text = f"{label}. {options[i]}"
    # Answer line in the accent color so it visually separates from options
    p = body.add_paragraph()
    p.text = f"Answer: {mcq['answer']} — {mcq.get('explanation', '')}"
    for run in p.runs:
        run.font.color.rgb = _rgb(palette.primary)
        run.font.size = Pt(14)
    _color_title(slide, palette)
