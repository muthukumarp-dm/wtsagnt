"""Pydantic models for the agent outputs."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class Intent(BaseModel):
    subject: str
    grade: str
    topic: str
    duration_min: int
    n_slides: int = Field(ge=1, le=40)
    n_mcqs: int = Field(ge=1, le=20)
    ppt_prompt: str
    mcq_prompt: str
    reckoner_prompt: str
    teaching_tips_prompt: str
    worksheet_prompt: str
    # Optional: teacher's display name extracted from the request (e.g.,
    # "I'm Ms. Priya" → "Ms. Priya"). Renderers add "Prepared by …" when set.
    teacher_name: str | None = None


class Slide(BaseModel):
    layout: Literal["title", "bullets", "two_column", "image_text"]
    title: str
    subtitle: str | None = None
    bullets: list[str] | None = None
    left_column: str | None = None
    right_column: str | None = None
    body: str | None = None


class SlideDeck(BaseModel):
    slides: list[Slide]


class MCQ(BaseModel):
    question: str
    options: list[str]
    answer: Literal["A", "B", "C", "D"]
    explanation: str

    @field_validator("options")
    @classmethod
    def four_options(cls, v: list[str]) -> list[str]:
        if len(v) != 4:
            raise ValueError("MCQ must have exactly 4 options")
        return v


class MCQList(BaseModel):
    mcqs: list[MCQ]


class TimelineStep(BaseModel):
    """One row of the lesson timeline. `minutes` is a free-form range
    like '0-5 min' so the teacher can read it as a clock segment."""
    minutes: str
    activity: str


class Reckoner(BaseModel):
    """Structured teaching plan delivered to the teacher as a PDF.

    Replaces the old generic "title + sections" wall with sections explicitly
    aimed at lesson delivery: a 1-line summary, materials checklist, time-boxed
    timeline, key concepts, common student misconceptions, board work, and a
    formative check — content that's actually useful for teaching, not facts
    that can be Googled."""
    title: str
    one_line_summary: str
    materials: list[str]
    timeline: list[TimelineStep]
    key_concepts: list[str]
    common_misconceptions: list[str]
    board_work: list[str]
    formative_check: str


class TeachingTip(BaseModel):
    heading: str
    body: str


class TeachingTips(BaseModel):
    tips: list[TeachingTip]


class WorksheetActivity(BaseModel):
    """One activity on the printable student worksheet.

    - 'question': open-ended, render with blank lines for the answer
    - 'fill_blank': prompt contains '___' (or similar) placeholders the
      student fills in
    - 'match': pair up left_items with right_items (LLM puts the answers
      in answer_hint)
    """
    kind: Literal["question", "fill_blank", "match"]
    prompt: str
    left_items: list[str] | None = None
    right_items: list[str] | None = None
    answer_hint: str | None = None


class Worksheet(BaseModel):
    title: str
    instructions: str
    activities: list[WorksheetActivity]
