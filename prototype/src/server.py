"""FastAPI service — POST /webhooks/whatsapp.

The webhook returns TwiML inline for the ack (no separate Twilio API call),
schedules background work via asyncio.create_task, and verifies Twilio's
X-Twilio-Signature before any DB write. State transitions are CAS so
concurrent webhook hits don't race (see src.state)."""
from __future__ import annotations
import asyncio
from functools import lru_cache

from openai import AsyncOpenAI
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from supabase import create_client

from src import state
from src.pipeline import Pipeline
from src.settings import Settings, get_settings
from src.storage_adapter import SupabaseStorageAdapter
from src.whatsapp_adapter import TwilioAdapter, WhatsAppAdapter


app = FastAPI(title="wtsagnt Monday WhatsApp slice")


@lru_cache(maxsize=1)
def _whatsapp_adapter() -> TwilioAdapter:
    s = get_settings()
    return TwilioAdapter(
        account_sid=s.twilio_account_sid,
        auth_token=s.twilio_auth_token,
        whatsapp_from=s.twilio_whatsapp_from,
    )


@lru_cache(maxsize=1)
def _supabase_client():
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_secret_key)


@lru_cache(maxsize=1)
def _llm_client() -> AsyncOpenAI:
    """LLM client — OpenAI for Monday, AsyncAnthropic on planned revert."""
    s = get_settings()
    return AsyncOpenAI(api_key=s.openai_api_key)


@lru_cache(maxsize=1)
def _pipeline() -> Pipeline:
    s = get_settings()
    return Pipeline(
        llm=_llm_client(),
        whatsapp=_whatsapp_adapter(),
        storage=SupabaseStorageAdapter(client=_supabase_client()),
        supabase=_supabase_client(),
        settings=s,
    )


def get_settings_dep() -> Settings:
    return get_settings()


def get_whatsapp_adapter() -> WhatsAppAdapter:
    return _whatsapp_adapter()


def get_supabase():
    return _supabase_client()


def get_pipeline() -> Pipeline:
    return _pipeline()


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _twiml(message: str = "") -> Response:
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        + (f"<Message>{message}</Message>" if message else "")
        + "</Response>"
    )
    return Response(content=body, media_type="application/xml")


@app.post("/webhooks/whatsapp")
async def whatsapp_webhook(
    request: Request,
    x_twilio_signature: str = Header(default=""),
    settings: Settings = Depends(get_settings_dep),
    whatsapp: WhatsAppAdapter = Depends(get_whatsapp_adapter),
    supabase=Depends(get_supabase),
    pipeline: Pipeline = Depends(get_pipeline),
) -> Response:
    form_data = await request.form()
    form = {k: form_data[k] for k in form_data}

    # Signature verification — reconstruct the URL as Twilio sees it
    public_url = f"{settings.public_base_url.rstrip('/')}{request.url.path}"
    if not whatsapp.verify_signature(url=public_url, signature=x_twilio_signature, form=form):
        raise HTTPException(status_code=401, detail="bad twilio signature")

    provider_sid = form.get("MessageSid", "")
    from_phone = form.get("From", "")
    to_phone = form.get("To", "")
    body = (form.get("Body") or "").strip()
    if not (provider_sid and from_phone and body):
        return _twiml()

    latest = state.latest_project_for_phone(supabase, from_phone)

    if latest is None or latest["state"] in ("approved", "delivered", "error"):
        project = state.create_project(supabase, from_phone, body)
        ok = state.insert_inbound_message(
            supabase, project_id=project["id"], provider_sid=provider_sid,
            from_phone=from_phone, to_phone=to_phone, body=body,
        )
        if not ok:
            return _twiml()
        asyncio.create_task(pipeline.generate(project["id"]))
        return _twiml("Got it. Generating your lesson…")

    if latest["state"] == "generating":
        state.insert_inbound_message(
            supabase, project_id=latest["id"], provider_sid=provider_sid,
            from_phone=from_phone, to_phone=to_phone, body=body,
        )
        return _twiml("Still working on your previous request — one moment.")

    # latest["state"] == "awaiting_approval"
    ok = state.insert_inbound_message(
        supabase, project_id=latest["id"], provider_sid=provider_sid,
        from_phone=from_phone, to_phone=to_phone, body=body,
    )
    if not ok:
        return _twiml()
    asyncio.create_task(pipeline.handle_reply(latest["id"], body))
    return _twiml()
