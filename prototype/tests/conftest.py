"""Shared pytest fixtures: env loading, deterministic UUIDs, mocked adapters."""
from __future__ import annotations
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture
def fake_project_id() -> str:
    return str(uuid.UUID(int=0x1234))


@pytest.fixture
def mock_whatsapp_adapter() -> MagicMock:
    m = MagicMock()
    m.verify_signature = MagicMock(return_value=True)
    m.send_text = AsyncMock(return_value=MagicMock(sid="SM_outbound_test"))
    return m


@pytest.fixture
def mock_storage_adapter() -> MagicMock:
    m = MagicMock()
    m.upload = AsyncMock(return_value=None)
    m.signed_url = AsyncMock(return_value="https://example.test/signed-url")
    return m


@pytest.fixture
def mock_supabase() -> MagicMock:
    """Minimal supabase-py table-builder mock. Override per-test as needed."""
    client = MagicMock()
    builder = MagicMock()
    builder.insert = MagicMock(return_value=builder)
    builder.select = MagicMock(return_value=builder)
    builder.update = MagicMock(return_value=builder)
    builder.eq = MagicMock(return_value=builder)
    builder.order = MagicMock(return_value=builder)
    builder.limit = MagicMock(return_value=builder)
    builder.execute = MagicMock(return_value=MagicMock(data=[]))
    client.table = MagicMock(return_value=builder)
    return client
