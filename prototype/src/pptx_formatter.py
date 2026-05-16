"""Render slide JSON + MCQ JSON into a .pptx file using python-pptx.

The renderer owns ALL layout primitives. Callers (the LLM upstream) only pick
a layout name and supply content — they do not control fonts, sizes, or positions.
"""
from __future__ import annotations
from pptx import Presentation


def render_pptx(slides: list[dict], mcqs: list[dict], output_path: str) -> None:
    prs = Presentation()

    for spec in slides:
        layout = spec.get("layout", "bullets")
        if layout == "title":
            _add_title_slide(prs, spec)
        elif layout == "two_column":
            _add_two_column_slide(prs, spec)
        elif layout == "image_text":
            _add_image_text_slide(prs, spec)
        else:
            _add_bullet_slide(prs, spec)

    for mcq in mcqs:
        _add_mcq_slide(prs, mcq)

    prs.save(output_path)


def _add_title_slide(prs: Presentation, spec: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = spec.get("title", "")
    if len(slide.placeholders) > 1 and spec.get("subtitle"):
        slide.placeholders[1].text = spec["subtitle"]


def _add_bullet_slide(prs: Presentation, spec: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = spec.get("title", "")
    body = slide.placeholders[1].text_frame
    bullets = spec.get("bullets") or []
    if not bullets:
        body.text = spec.get("body", "") or ""
        return
    body.text = bullets[0]
    for bullet in bullets[1:]:
        p = body.add_paragraph()
        p.text = bullet


def _add_two_column_slide(prs: Presentation, spec: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[3])
    slide.shapes.title.text = spec.get("title", "")
    left = slide.placeholders[1].text_frame
    right = slide.placeholders[2].text_frame
    left.text = spec.get("left_column", "") or ""
    right.text = spec.get("right_column", "") or ""


def _add_image_text_slide(prs: Presentation, spec: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = spec.get("title", "")
    body = slide.placeholders[1].text_frame
    body.text = spec.get("body", "") or ""


def _add_mcq_slide(prs: Presentation, mcq: dict) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = mcq["question"]
    body = slide.placeholders[1].text_frame
    options = mcq["options"]
    body.text = f"A. {options[0]}"
    for i, label in enumerate(["B", "C", "D"], start=1):
        p = body.add_paragraph()
        p.text = f"{label}. {options[i]}"
    p = body.add_paragraph()
    p.text = f"Answer: {mcq['answer']} — {mcq.get('explanation', '')}"
