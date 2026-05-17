"""TDD for the orchestration pipeline. Adapters and the state module are mocked;
we assert call sequence and state transitions, not supabase chain plumbing.

(supabase chain mocking happens at the state module level — see test_state.py.
Here we patch src.pipeline.state.* directly so this test file is decoupled
from the state module's choice of database client.)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pipeline import Pipeline


def _fake_intent_response():
    return {
        "subject": "Science",
        "grade": "7",
        "topic": "Photosynthesis",
        "duration_min": 30,
        "n_slides": 10,
        "n_mcqs": 5,
        "ppt_prompt": "make a deck",
        "mcq_prompt": "make 5 mcqs",
        "reckoner_prompt": "make a reckoner",
        "teaching_tips_prompt": "make teacher tips",
        "worksheet_prompt": "make a student worksheet",
    }


def _fake_tips_response():
    return {"tips": [
        {"heading": "Hook", "body": "Open with a leaf demo."},
        {"heading": "Misconception", "body": "Students mix photosynthesis with respiration."},
    ]}


def _fake_worksheet_response():
    return {
        "title": "Photosynthesis worksheet",
        "instructions": "Answer all questions.",
        "activities": [
            {"kind": "fill_blank",
             "prompt": "Plants need ___, ___, and ___ to make food.",
             "answer_hint": "sunlight, water, CO2"},
            {"kind": "question",
             "prompt": "Name one place photosynthesis happens.",
             "answer_hint": "chloroplasts"},
        ],
    }


def _fake_slides_response():
    return {"slides": [
        {"layout": "title", "title": "Photosynthesis", "subtitle": "Grade 7"},
        {"layout": "bullets", "title": "Inputs", "bullets": ["Sunlight", "CO2", "H2O"]},
    ]}


def _fake_mcqs_response():
    return {"mcqs": [
        {"question": "What gas?", "options": ["O2", "CO2", "N2", "H2"],
         "answer": "B", "explanation": "Plants absorb CO2."},
    ]}


def _fake_reckoner_response():
    return {
        "title": "Photosynthesis — grade 7",
        "one_line_summary": "Plants use sunlight + water + CO2 to make food.",
        "materials": ["Whiteboard", "Worksheet"],
        "timeline": [
            {"minutes": "0-5 min", "activity": "Warm-up"},
            {"minutes": "5-25 min", "activity": "Teach inputs/outputs"},
            {"minutes": "25-30 min", "activity": "Quick check"},
        ],
        "key_concepts": ["Sunlight is the energy source"],
        "common_misconceptions": ["Plants 'eat' soil — they don't"],
        "board_work": ["Inputs → leaf → outputs diagram"],
        "formative_check": "What two outputs does photosynthesis make?",
    }


@pytest.fixture
def pipeline(mock_whatsapp_adapter, mock_storage_adapter):
    """Build a Pipeline with adapter dependencies mocked. The supabase
    client passed in is a placeholder — tests patch src.pipeline.state.*
    so the pipeline never actually touches it."""
    llm = MagicMock()
    settings = MagicMock()
    settings.openai_content_model = "gpt-4o"
    settings.openai_classification_model = "gpt-4o-mini"
    settings.supabase_storage_bucket = "lesson-files"
    settings.signed_url_ttl_seconds = 604800
    settings.twilio_whatsapp_from = "whatsapp:+14155238886"

    return Pipeline(
        llm=llm,
        whatsapp=mock_whatsapp_adapter,
        storage=mock_storage_adapter,
        supabase=MagicMock(),
        settings=settings,
    )


async def test_generate_first_run_skips_revision_merger(pipeline, fake_project_id):
    """When revision_count == 0, the revision merger is NOT called."""
    pipeline.call_llm_json = AsyncMock(side_effect=[
        _fake_intent_response(),
        _fake_slides_response(),
        _fake_mcqs_response(),
        _fake_reckoner_response(),
        _fake_tips_response(),
        _fake_worksheet_response(),
    ])
    pipeline.call_llm_text = AsyncMock()  # should not be called

    project_row = {
        "id": fake_project_id, "phone": "whatsapp:+91999...",
        "original_request": "x", "current_request": "x",
        "state": "generating", "revision_count": 0,
    }
    with patch("src.pipeline.state") as mock_state:
        mock_state.get_project.return_value = project_row
        mock_state.cas_to_awaiting_approval.return_value = True

        await pipeline.generate(fake_project_id)

    pipeline.call_llm_text.assert_not_called()
    assert pipeline.call_llm_json.await_count == 6


async def test_generate_with_revisions_calls_merger_first(pipeline, fake_project_id):
    """When revision_count > 0, the revision merger runs as step 0."""
    pipeline.call_llm_text = AsyncMock(return_value="A coherent merged brief.")
    pipeline.call_llm_json = AsyncMock(side_effect=[
        _fake_intent_response(),
        _fake_slides_response(),
        _fake_mcqs_response(),
        _fake_reckoner_response(),
        _fake_tips_response(),
        _fake_worksheet_response(),
    ])

    project_row = {
        "id": fake_project_id, "phone": "whatsapp:+91999...",
        "original_request": "x",
        "current_request": "x\n\nRevision 1: grade 8",
        "state": "generating", "revision_count": 1,
    }
    with patch("src.pipeline.state") as mock_state:
        mock_state.get_project.return_value = project_row
        mock_state.cas_to_awaiting_approval.return_value = True

        await pipeline.generate(fake_project_id)

    pipeline.call_llm_text.assert_awaited_once()
    assert pipeline.call_llm_json.await_count == 6


async def test_generate_cas_loss_skips_send(pipeline, fake_project_id):
    """If CAS to awaiting_approval returns False, we don't send the summary."""
    pipeline.call_llm_json = AsyncMock(side_effect=[
        _fake_intent_response(),
        _fake_slides_response(),
        _fake_mcqs_response(),
        _fake_reckoner_response(),
        _fake_tips_response(),
        _fake_worksheet_response(),
    ])

    project_row = {
        "id": fake_project_id, "phone": "whatsapp:+91999...",
        "original_request": "x", "current_request": "x",
        "state": "generating", "revision_count": 0,
    }
    with patch("src.pipeline.state") as mock_state:
        mock_state.get_project.return_value = project_row
        mock_state.cas_to_awaiting_approval.return_value = False  # lost race

        await pipeline.generate(fake_project_id)

    pipeline.whatsapp.send_text.assert_not_called()


async def test_handle_reply_approved_sends_four_labelled_links(pipeline, fake_project_id):
    awaiting_row = {
        "id": fake_project_id, "phone": "whatsapp:+91999...",
        "state": "awaiting_approval",
        "pptx_url": "https://x.test/pptx",
        "pdf_url": "https://x.test/pdf",
        "worksheet_url": "https://x.test/worksheet",
        "mcq_url": "https://x.test/quiz",
    }
    with patch("src.pipeline.state") as mock_state:
        mock_state.get_project.return_value = awaiting_row
        mock_state.cas_to_approved.return_value = True
        mock_state.cas_to_delivered.return_value = True

        await pipeline.handle_reply(fake_project_id, "APPROVE")

    # 4 messages: Slides + Lesson plan + Student worksheet + Quiz
    assert pipeline.whatsapp.send_text.await_count == 4
    sent_bodies = [c.kwargs["body"] for c in pipeline.whatsapp.send_text.call_args_list]
    assert any("Slides:" in b for b in sent_bodies)
    assert any("Lesson plan" in b for b in sent_bodies)
    assert any("Student worksheet" in b for b in sent_bodies)
    assert any("Quiz" in b for b in sent_bodies)


async def test_handle_reply_approved_skips_missing_optional_urls(pipeline, fake_project_id):
    """If worksheet_url and mcq_url aren't set (project predates D3/D6),
    still deliver the 2 core links cleanly."""
    awaiting_row = {
        "id": fake_project_id, "phone": "whatsapp:+91999...",
        "state": "awaiting_approval",
        "pptx_url": "https://x.test/pptx",
        "pdf_url": "https://x.test/pdf",
        "worksheet_url": None,
        "mcq_url": None,
    }
    with patch("src.pipeline.state") as mock_state:
        mock_state.get_project.return_value = awaiting_row
        mock_state.cas_to_approved.return_value = True
        mock_state.cas_to_delivered.return_value = True

        await pipeline.handle_reply(fake_project_id, "APPROVE")

    assert pipeline.whatsapp.send_text.await_count == 2


async def test_handle_reply_changes_restarts_generation(pipeline, fake_project_id):
    awaiting_row = {
        "id": fake_project_id, "phone": "whatsapp:+91999...",
        "state": "awaiting_approval",
        "current_request": "x", "revision_count": 0,
    }
    pipeline.generate = AsyncMock()

    with patch("src.pipeline.state") as mock_state:
        mock_state.get_project.return_value = awaiting_row
        mock_state.cas_to_generating_for_revision.return_value = True

        await pipeline.handle_reply(
            fake_project_id,
            "Please change to grade 8 and add cellular respiration coverage",
        )

    pipeline.generate.assert_awaited_once_with(fake_project_id)
    pipeline.whatsapp.send_text.assert_awaited()


async def test_handle_reply_unclear_asks_clarification(pipeline, fake_project_id):
    awaiting_row = {
        "id": fake_project_id, "phone": "whatsapp:+91999...",
        "state": "awaiting_approval",
    }
    pipeline.call_llm_text = AsyncMock(return_value="UNCLEAR")

    with patch("src.pipeline.state") as mock_state:
        mock_state.get_project.return_value = awaiting_row

        await pipeline.handle_reply(fake_project_id, "???")

    pipeline.whatsapp.send_text.assert_awaited()
    args, kwargs = pipeline.whatsapp.send_text.call_args
    assert "APPROVE" in kwargs["body"] or "approve" in kwargs["body"].lower()
