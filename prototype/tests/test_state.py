"""TDD for state machine + CAS operations against supabase-py."""
from unittest.mock import MagicMock

import pytest

from src.state import (
    create_project,
    latest_project_for_phone,
    list_projects_for_phone,
    insert_inbound_message,
    insert_outbound_message,
    cas_to_generating_for_revision,
    cas_to_awaiting_approval,
    cas_to_approved,
    cas_to_delivered,
    cas_to_error,
)


def _builder_returning(data):
    b = MagicMock()
    b.insert = MagicMock(return_value=b)
    b.select = MagicMock(return_value=b)
    b.update = MagicMock(return_value=b)
    b.eq = MagicMock(return_value=b)
    b.order = MagicMock(return_value=b)
    b.limit = MagicMock(return_value=b)
    b.execute = MagicMock(return_value=MagicMock(data=data))
    return b


def test_create_project_returns_row(mock_supabase):
    mock_supabase.table.return_value = _builder_returning(
        [{"id": "p-1", "phone": "whatsapp:+91...", "state": "generating",
          "original_request": "x", "current_request": "x", "revision_count": 0}]
    )
    p = create_project(mock_supabase, "whatsapp:+91...", "x")
    assert p["id"] == "p-1"
    assert p["state"] == "generating"


def test_list_projects_for_phone_returns_ordered_rows(mock_supabase):
    rows = [
        {"id": "p-3", "created_at": "2026-05-17T10:00:00Z", "state": "delivered"},
        {"id": "p-2", "created_at": "2026-05-17T09:00:00Z", "state": "approved"},
        {"id": "p-1", "created_at": "2026-05-17T08:00:00Z", "state": "delivered"},
    ]
    mock_supabase.table.return_value = _builder_returning(rows)
    out = list_projects_for_phone(mock_supabase, "whatsapp:+91...", limit=20)
    assert len(out) == 3
    assert out[0]["id"] == "p-3"


def test_list_projects_for_phone_empty(mock_supabase):
    mock_supabase.table.return_value = _builder_returning([])
    assert list_projects_for_phone(mock_supabase, "whatsapp:+91...") == []


def test_latest_project_for_phone_returns_none_when_empty(mock_supabase):
    mock_supabase.table.return_value = _builder_returning([])
    p = latest_project_for_phone(mock_supabase, "whatsapp:+91...")
    assert p is None


def test_insert_inbound_message_dedupes_on_unique_conflict(mock_supabase):
    # Simulate supabase-py raising on UNIQUE conflict (the partial index)
    from postgrest.exceptions import APIError
    b = _builder_returning([])
    b.execute = MagicMock(side_effect=APIError({"code": "23505", "message": "dup"}))
    mock_supabase.table.return_value = b

    ok = insert_inbound_message(
        mock_supabase, project_id=None, provider_sid="SMdup",
        from_phone="whatsapp:+91...", to_phone="whatsapp:+1415...", body="hi",
    )
    assert ok is False  # dedupe path


def test_insert_inbound_message_succeeds_on_new(mock_supabase):
    mock_supabase.table.return_value = _builder_returning(
        [{"id": "m-1", "provider_sid": "SMnew"}]
    )
    ok = insert_inbound_message(
        mock_supabase, project_id=None, provider_sid="SMnew",
        from_phone="whatsapp:+91...", to_phone="whatsapp:+1415...", body="hi",
    )
    assert ok is True


def test_cas_to_approved_succeeds_when_state_matches(mock_supabase):
    mock_supabase.table.return_value = _builder_returning([{"id": "p-1", "state": "approved"}])
    won = cas_to_approved(mock_supabase, "p-1")
    assert won is True


def test_cas_to_approved_loses_race(mock_supabase):
    mock_supabase.table.return_value = _builder_returning([])  # no rows updated
    won = cas_to_approved(mock_supabase, "p-1")
    assert won is False


def test_cas_to_generating_for_revision_appends_request(mock_supabase):
    # We rely on the SQL appending via Postgres expression; here we just
    # check the function returns True/False based on rows-affected.
    mock_supabase.table.return_value = _builder_returning([{"id": "p-1", "state": "awaiting_approval"}])
    won = cas_to_generating_for_revision(mock_supabase, "p-1", "make it grade 8")
    assert won is True
