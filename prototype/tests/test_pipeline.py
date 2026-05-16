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
    return {"title": "Photosynthesis", "sections": [
        {"heading": "What", "body": "Process plants use to make food."},
    ]}


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
    assert pipeline.call_llm_json.await_count == 4


async def test_generate_with_revisions_calls_merger_first(pipeline, fake_project_id):
    """When revision_count > 0, the revision merger runs as step 0."""
    pipeline.call_llm_text = AsyncMock(return_value="A coherent merged brief.")
    pipeline.call_llm_json = AsyncMock(side_effect=[
        _fake_intent_response(),
        _fake_slides_response(),
        _fake_mcqs_response(),
        _fake_reckoner_response(),
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
    assert pipeline.call_llm_json.await_count == 4


async def test_generate_cas_loss_skips_send(pipeline, fake_project_id):
    """If CAS to awaiting_approval returns False, we don't send the summary."""
    pipeline.call_llm_json = AsyncMock(side_effect=[
        _fake_intent_response(),
        _fake_slides_response(),
        _fake_mcqs_response(),
        _fake_reckoner_response(),
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


async def test_handle_reply_approved_sends_two_files(pipeline, fake_project_id):
    awaiting_row = {
        "id": fake_project_id, "phone": "whatsapp:+91999...",
        "state": "awaiting_approval",
        "pptx_url": "https://x.test/pptx",
        "pdf_url": "https://x.test/pdf",
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
