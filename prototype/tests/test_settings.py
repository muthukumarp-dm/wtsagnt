"""Verify Settings loads from environment and exposes typed access."""
import os
from unittest.mock import patch

from src.settings import Settings


def test_settings_loads_required_fields():
    env = {
        "OPENAI_API_KEY": "sk-proj-test",
        "TWILIO_ACCOUNT_SID": "AC_test",
        "TWILIO_AUTH_TOKEN": "tok_test",
        "TWILIO_WHATSAPP_FROM": "whatsapp:+14155238886",
        "SUPABASE_URL": "https://elczksydirrjuqapcpgq.supabase.co",
        "SUPABASE_SECRET_KEY": "sb_secret_test",
        "SUPABASE_STORAGE_BUCKET": "lesson-files",
        "PUBLIC_BASE_URL": "https://example.test",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.openai_api_key == "sk-proj-test"
    assert s.twilio_account_sid == "AC_test"
    assert s.twilio_whatsapp_from == "whatsapp:+14155238886"
    assert s.supabase_url == "https://elczksydirrjuqapcpgq.supabase.co"
    assert s.supabase_storage_bucket == "lesson-files"
    assert s.public_base_url == "https://example.test"


def test_settings_defaults():
    env = {
        "OPENAI_API_KEY": "sk-proj-test",
        "TWILIO_ACCOUNT_SID": "AC_test",
        "TWILIO_AUTH_TOKEN": "tok_test",
        "TWILIO_WHATSAPP_FROM": "whatsapp:+14155238886",
        "SUPABASE_URL": "https://x.supabase.co",
        "SUPABASE_SECRET_KEY": "sb_secret_test",
        "PUBLIC_BASE_URL": "https://example.test",
    }
    with patch.dict(os.environ, env, clear=True):
        s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.openai_content_model == "gpt-4o"
    assert s.openai_classification_model == "gpt-4o-mini"
    assert s.signed_url_ttl_seconds == 604800
    assert s.supabase_storage_bucket == "lesson-files"
