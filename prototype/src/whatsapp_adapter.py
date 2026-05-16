"""WhatsApp adapter — Twilio sandbox implementation for Monday.

Designed to be swapped for a Gupshup adapter post-Monday without touching
callers. Callers depend only on the Protocol below."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from twilio.request_validator import RequestValidator
from twilio.rest import Client as TwilioClient


@dataclass
class SendResult:
    sid: str


@runtime_checkable
class WhatsAppAdapter(Protocol):
    def verify_signature(self, *, url: str, signature: str, form: dict) -> bool: ...
    async def send_text(self, *, to: str, body: str) -> SendResult: ...


class TwilioAdapter:
    """Twilio sandbox WhatsApp adapter. Thread-safe; the underlying TwilioClient
    is HTTP-based and stateless aside from credentials."""

    def __init__(self, *, account_sid: str, auth_token: str, whatsapp_from: str) -> None:
        self._client = TwilioClient(account_sid, auth_token)
        self._validator = RequestValidator(auth_token)
        self._from = whatsapp_from

    def verify_signature(self, *, url: str, signature: str, form: dict) -> bool:
        if not signature:
            return False
        return self._validator.validate(url, form, signature)

    async def send_text(self, *, to: str, body: str) -> SendResult:
        # twilio-python is sync; bounce to a thread so we don't block the loop
        loop = asyncio.get_running_loop()
        msg = await loop.run_in_executor(
            None,
            lambda: self._client.messages.create(from_=self._from, to=to, body=body),
        )
        return SendResult(sid=msg.sid)
