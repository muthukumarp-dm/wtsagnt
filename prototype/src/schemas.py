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


class ReckonerSection(BaseModel):
    heading: str
    body: str


class Reckoner(BaseModel):
    title: str
    sections: list[ReckonerSection]
