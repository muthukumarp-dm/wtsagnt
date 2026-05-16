"""Verify TwilioAdapter.verify_signature against Twilio's documented behavior.

Twilio computes HMAC-SHA1 over (URL + concatenated sorted form pairs),
base64-encoded. We use twilio's own RequestValidator to compute a known-good
signature, then assert our adapter accepts it and rejects tampered ones."""
import os

import pytest
from twilio.request_validator import RequestValidator

from src.whatsapp_adapter import TwilioAdapter


AUTH_TOKEN = "12345"  # test-only; doesn't need to match a real account
URL = "https://example.test/webhooks/whatsapp"
PARAMS = {
    "AccountSid": "AC_fake",
    "From": "whatsapp:+919876543210",
    "To": "whatsapp:+14155238886",
    "Body": "30-min lesson grade 7 photosynthesis",
    "MessageSid": "SM_test_inbound",
}


def _real_signature(token: str, url: str, params: dict) -> str:
    return RequestValidator(token).compute_signature(url, params)


def test_verify_signature_accepts_valid():
    adapter = TwilioAdapter(account_sid="AC_fake", auth_token=AUTH_TOKEN,
                            whatsapp_from="whatsapp:+14155238886")
    sig = _real_signature(AUTH_TOKEN, URL, PARAMS)
    assert adapter.verify_signature(url=URL, signature=sig, form=PARAMS) is True


def test_verify_signature_rejects_tampered_body():
    adapter = TwilioAdapter(account_sid="AC_fake", auth_token=AUTH_TOKEN,
                            whatsapp_from="whatsapp:+14155238886")
    sig = _real_signature(AUTH_TOKEN, URL, PARAMS)
    tampered = {**PARAMS, "Body": "totally different body"}
    assert adapter.verify_signature(url=URL, signature=sig, form=tampered) is False


def test_verify_signature_rejects_wrong_token():
    wrong_token_adapter = TwilioAdapter(account_sid="AC_fake",
                                        auth_token="WRONG", whatsapp_from="whatsapp:+1...")
    sig = _real_signature(AUTH_TOKEN, URL, PARAMS)
    assert wrong_token_adapter.verify_signature(url=URL, signature=sig, form=PARAMS) is False


def test_verify_signature_rejects_missing_signature():
    adapter = TwilioAdapter(account_sid="AC_fake", auth_token=AUTH_TOKEN,
                            whatsapp_from="whatsapp:+1...")
    assert adapter.verify_signature(url=URL, signature="", form=PARAMS) is False
