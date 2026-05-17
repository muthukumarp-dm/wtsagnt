"""TDD for the FastAPI webhook. Pipeline, adapters, settings, and supabase
are mocked via the dependency-override pattern."""
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from src.server import (
    app,
    get_pipeline,
    get_whatsapp_adapter,
    get_supabase,
    get_settings_dep,
)


@pytest.fixture
def client():
    # Fake settings — provides public_base_url for URL reconstruction
    fake_settings = SimpleNamespace(
        public_base_url="https://example.test",
        twilio_whatsapp_from="whatsapp:+14155238886",
    )

    fake_whatsapp = MagicMock()
    fake_whatsapp.verify_signature = MagicMock(return_value=True)
    fake_whatsapp.send_text = AsyncMock()

    fake_pipeline = MagicMock()
    fake_pipeline.generate = AsyncMock()
    fake_pipeline.handle_reply = AsyncMock()

    # Fake supabase with chained mock that supports:
    #   - latest_project_for_phone (select chain) → default empty (no project)
    #   - create_project (insert chain) → returns new row
    #   - insert_inbound_message (insert chain) → succeeds by default
    fake_supabase = MagicMock()
    builder = MagicMock()
    for m in ("insert", "select", "update", "eq", "order", "limit"):
        setattr(builder, m, MagicMock(return_value=builder))
    builder.execute = MagicMock(return_value=MagicMock(data=[]))
    fake_supabase.table = MagicMock(return_value=builder)

    app.dependency_overrides[get_settings_dep] = lambda: fake_settings
    app.dependency_overrides[get_pipeline] = lambda: fake_pipeline
    app.dependency_overrides[get_whatsapp_adapter] = lambda: fake_whatsapp
    app.dependency_overrides[get_supabase] = lambda: fake_supabase

    client = TestClient(app, base_url="https://example.test")
    client.fake_pipeline = fake_pipeline
    client.fake_whatsapp = fake_whatsapp
    client.fake_supabase = fake_supabase
    client.fake_builder = builder

    yield client
    app.dependency_overrides.clear()


def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_projects_endpoint_returns_history(client):
    """GET /projects?phone=... returns the projects list."""
    client.fake_builder.execute.return_value = MagicMock(data=[
        {"id": "p-1", "phone": "whatsapp:+919999999999",
         "state": "delivered", "summary": "Made: 30-min Science lesson…",
         "pptx_url": "https://x.test/a.pptx", "pdf_url": "https://x.test/a.pdf",
         "revision_count": 0, "error_reason": None,
         "created_at": "2026-05-17T10:00:00Z", "updated_at": "2026-05-17T10:02:00Z"},
        {"id": "p-2", "phone": "whatsapp:+919999999999",
         "state": "awaiting_approval", "summary": "Made: 45-min Math lesson…",
         "pptx_url": "https://x.test/b.pptx", "pdf_url": "https://x.test/b.pdf",
         "revision_count": 1, "error_reason": None,
         "created_at": "2026-05-17T09:00:00Z", "updated_at": "2026-05-17T09:01:30Z"},
    ])
    r = client.get("/projects?phone=whatsapp%3A%2B919999999999")
    assert r.status_code == 200
    body = r.json()
    assert "projects" in body
    assert len(body["projects"]) == 2
    assert body["projects"][0]["id"] == "p-1"
    assert body["projects"][0]["state"] == "delivered"
    assert body["projects"][1]["revision_count"] == 1


def test_projects_endpoint_rejects_missing_phone(client):
    r = client.get("/projects")
    assert r.status_code == 422  # FastAPI validates required query params


def test_projects_endpoint_rejects_bad_limit(client):
    r = client.get("/projects?phone=x&limit=0")
    assert r.status_code == 400
    r2 = client.get("/projects?phone=x&limit=999")
    assert r2.status_code == 400


def test_webhook_bad_signature_returns_401(client):
    client.fake_whatsapp.verify_signature = MagicMock(return_value=False)
    form = {
        "AccountSid": "AC_fake", "MessageSid": "SM_bad",
        "From": "whatsapp:+919999999999", "To": "whatsapp:+14155238886",
        "Body": "hi",
    }
    r = client.post("/webhooks/whatsapp", data=form,
                    headers={"X-Twilio-Signature": "obviously-wrong"})
    assert r.status_code == 401


def test_webhook_new_request_creates_project_and_acks(client):
    # latest_project_for_phone returns empty → new request path
    # First execute call (SELECT for latest_project_for_phone) → []
    # Second execute call (INSERT create_project) → row
    # Third execute call (INSERT inbound message) → row (success)
    client.fake_builder.execute.side_effect = [
        MagicMock(data=[]),  # latest_project_for_phone: no project
        MagicMock(data=[{"id": "p-new", "phone": "whatsapp:+919999999999",
                         "state": "generating"}]),  # create_project
        MagicMock(data=[{"id": "m-1"}]),  # insert_inbound_message
    ]
    form = {
        "AccountSid": "AC_fake", "MessageSid": "SM_new1",
        "From": "whatsapp:+919999999999", "To": "whatsapp:+14155238886",
        "Body": "30-min lesson grade 7 photosynthesis",
    }
    r = client.post("/webhooks/whatsapp", data=form,
                    headers={"X-Twilio-Signature": "ok"})
    assert r.status_code == 200
    assert "<Response>" in r.text and "<Message>" in r.text
    assert "Got it" in r.text
    client.fake_pipeline.generate.assert_called()


def test_webhook_duplicate_message_returns_empty_twiml(client):
    # latest_project_for_phone → empty (route to new request)
    # create_project → row
    # insert_inbound_message → APIError (23505 unique violation) → returns False
    client.fake_builder.execute.side_effect = [
        MagicMock(data=[]),
        MagicMock(data=[{"id": "p-new", "phone": "whatsapp:+919999999999",
                         "state": "generating"}]),
        APIError({"code": "23505", "message": "dup"}),
    ]
    form = {
        "AccountSid": "AC_fake", "MessageSid": "SM_dup",
        "From": "whatsapp:+919999999999", "To": "whatsapp:+14155238886",
        "Body": "hi",
    }
    r = client.post("/webhooks/whatsapp", data=form,
                    headers={"X-Twilio-Signature": "ok"})
    assert r.status_code == 200
    assert "<Message>" not in r.text
    client.fake_pipeline.generate.assert_not_called()


def test_webhook_reply_routes_to_handle_reply(client):
    # latest_project_for_phone → existing project in awaiting_approval
    client.fake_builder.execute.side_effect = [
        MagicMock(data=[{"id": "p-existing", "phone": "whatsapp:+919999999999",
                         "state": "awaiting_approval"}]),
        MagicMock(data=[{"id": "m-1"}]),  # insert_inbound_message
    ]
    form = {
        "AccountSid": "AC_fake", "MessageSid": "SM_reply",
        "From": "whatsapp:+919999999999", "To": "whatsapp:+14155238886",
        "Body": "APPROVE",
    }
    r = client.post("/webhooks/whatsapp", data=form,
                    headers={"X-Twilio-Signature": "ok"})
    assert r.status_code == 200
    client.fake_pipeline.handle_reply.assert_called()
    client.fake_pipeline.generate.assert_not_called()
