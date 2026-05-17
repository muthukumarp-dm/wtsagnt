"""Verify pydantic models reject malformed JSON and accept correct payloads."""
import pytest
from pydantic import ValidationError

from src.schemas import Intent, SlideDeck, MCQList, Reckoner, TeachingTips, Worksheet


_VALID_INTENT = {
    "subject": "Science",
    "grade": "7",
    "topic": "Photosynthesis",
    "duration_min": 30,
    "n_slides": 10,
    "n_mcqs": 5,
    "ppt_prompt": "Build a grade 7 deck on photosynthesis...",
    "mcq_prompt": "Write 5 MCQs on photosynthesis for grade 7...",
    "reckoner_prompt": "Write a one-page reckoner on photosynthesis...",
    "teaching_tips_prompt": "Write 3-5 teacher coaching tips for this lesson...",
    "worksheet_prompt": "Write a one-page student worksheet for this lesson...",
}


def test_intent_accepts_valid_payload():
    intent = Intent.model_validate(_VALID_INTENT)
    assert intent.n_slides == 10
    assert intent.n_mcqs == 5
    assert intent.teaching_tips_prompt.startswith("Write")


def test_intent_rejects_missing_field():
    with pytest.raises(ValidationError):
        Intent.model_validate({"subject": "Science"})


def test_intent_accepts_optional_teacher_name():
    intent = Intent.model_validate({**_VALID_INTENT, "teacher_name": "Ms. Priya"})
    assert intent.teacher_name == "Ms. Priya"


def test_intent_teacher_name_defaults_to_none():
    intent = Intent.model_validate(_VALID_INTENT)
    assert intent.teacher_name is None


def test_intent_requires_teaching_tips_prompt():
    payload = {k: v for k, v in _VALID_INTENT.items() if k != "teaching_tips_prompt"}
    with pytest.raises(ValidationError):
        Intent.model_validate(payload)


def test_intent_requires_worksheet_prompt():
    payload = {k: v for k, v in _VALID_INTENT.items() if k != "worksheet_prompt"}
    with pytest.raises(ValidationError):
        Intent.model_validate(payload)


def test_worksheet_schema_accepts_mixed_activities():
    ws = Worksheet.model_validate({
        "title": "Photosynthesis worksheet",
        "instructions": "Answer all questions.",
        "activities": [
            {"kind": "fill_blank", "prompt": "Plants need ___ to make food.",
             "answer_hint": "sunlight"},
            {"kind": "question", "prompt": "Where does photosynthesis happen?",
             "answer_hint": "chloroplasts"},
            {"kind": "match",
             "prompt": "Match the inputs to where they come from.",
             "left_items": ["Sunlight", "Water", "CO2"],
             "right_items": ["The air", "Roots", "The sun"],
             "answer_hint": "A=3, B=2, C=1"},
        ],
    })
    assert len(ws.activities) == 3
    assert ws.activities[2].kind == "match"
    assert ws.activities[2].left_items == ["Sunlight", "Water", "CO2"]


def test_worksheet_rejects_bad_kind():
    with pytest.raises(ValidationError):
        Worksheet.model_validate({
            "title": "x", "instructions": "y",
            "activities": [{"kind": "essay", "prompt": "Write something"}],
        })


def test_teaching_tips_schema_accepts_tips():
    tips = TeachingTips.model_validate({
        "tips": [
            {"heading": "Misconception", "body": "Students often think X..."},
            {"heading": "Hook", "body": "Open with a leaf-in-water demo..."},
            {"heading": "Pacing", "body": "Spend 10 min on inputs..."},
        ],
    })
    assert len(tips.tips) == 3
    assert tips.tips[0].heading == "Misconception"


def test_slide_deck_accepts_layouts():
    deck = SlideDeck.model_validate({
        "slides": [
            {"layout": "title", "title": "Photosynthesis", "subtitle": "Grade 7"},
            {"layout": "bullets", "title": "Process", "bullets": ["Sunlight", "Water"]},
            {"layout": "two_column", "title": "In vs Out",
             "left_column": "Inputs: CO2, H2O", "right_column": "Outputs: O2, glucose"},
        ],
    })
    assert len(deck.slides) == 3


def test_mcq_list_requires_four_options():
    with pytest.raises(ValidationError):
        MCQList.model_validate({
            "mcqs": [{"question": "Q", "options": ["A", "B"], "answer": "A", "explanation": "..."}],
        })


def test_reckoner_accepts_structured_plan():
    r = Reckoner.model_validate({
        "title": "Photosynthesis — grade 7 lesson plan",
        "one_line_summary": "Plants use sunlight, water, and CO2 to make food.",
        "materials": ["Whiteboard markers", "Printed worksheet"],
        "timeline": [
            {"minutes": "0-5 min", "activity": "Show leaf-in-water demo"},
            {"minutes": "5-15 min", "activity": "Introduce inputs and outputs"},
        ],
        "key_concepts": ["Sunlight is the energy source", "Chlorophyll captures light"],
        "common_misconceptions": ["Plants 'eat' soil — they don't"],
        "board_work": ["Draw inputs→leaf→outputs diagram"],
        "formative_check": "Ask: what two outputs does photosynthesis make?",
    })
    assert r.timeline[0].minutes == "0-5 min"
    assert "Whiteboard markers" in r.materials


def test_reckoner_requires_structured_fields():
    """Old shape ({title, sections: [...]}) must be rejected — the renderer
    now relies on the structured fields."""
    with pytest.raises(ValidationError):
        Reckoner.model_validate({
            "title": "x",
            "sections": [{"heading": "h", "body": "b"}],
        })
