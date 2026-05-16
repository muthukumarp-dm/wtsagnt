"""Verify pydantic models reject malformed JSON and accept correct payloads."""
import pytest
from pydantic import ValidationError

from src.schemas import Intent, SlideDeck, MCQList, Reckoner


def test_intent_accepts_valid_payload():
    intent = Intent.model_validate({
        "subject": "Science",
        "grade": "7",
        "topic": "Photosynthesis",
        "duration_min": 30,
        "n_slides": 10,
        "n_mcqs": 5,
        "ppt_prompt": "Build a grade 7 deck on photosynthesis...",
        "mcq_prompt": "Write 5 MCQs on photosynthesis for grade 7...",
        "reckoner_prompt": "Write a one-page reckoner on photosynthesis...",
    })
    assert intent.n_slides == 10
    assert intent.n_mcqs == 5


def test_intent_rejects_missing_field():
    with pytest.raises(ValidationError):
        Intent.model_validate({"subject": "Science"})


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


def test_reckoner_accepts_sections():
    r = Reckoner.model_validate({
        "title": "Photosynthesis quick reference",
        "sections": [{"heading": "What", "body": "It's a process..."}],
    })
    assert r.sections[0].heading == "What"
