"""Smoke test: real Twilio send to the dev phone. Skipped without env vars."""
import os
import pytest


REQUIRED = ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM",
            "TWILIO_TEST_TO")  # TWILIO_TEST_TO must be a joined sandbox phone


@pytest.mark.skipif(
    any(not os.getenv(k) for k in REQUIRED),
    reason="Twilio env not set (set TWILIO_TEST_TO to a joined sandbox phone)",
)
async def test_twilio_send_real():
    from src.whatsapp_adapter import TwilioAdapter
    adapter = TwilioAdapter(
        account_sid=os.environ["TWILIO_ACCOUNT_SID"],
        auth_token=os.environ["TWILIO_AUTH_TOKEN"],
        whatsapp_from=os.environ["TWILIO_WHATSAPP_FROM"],
    )
    result = await adapter.send_text(
        to=os.environ["TWILIO_TEST_TO"],
        body="wtsagnt smoke test — please ignore",
    )
    assert result.sid.startswith(("SM", "MM"))
