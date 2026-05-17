"""Orchestration pipeline — revision merger + generate + handle_reply.

Adapters are dependency-injected so tests can mock them. The pipeline owns
the business logic; adapters own I/O.

LLM provider: OpenAI (gpt-4o + gpt-4o-mini) for the Monday demo. Swap-back
to Anthropic Claude is localized to the two `call_llm_*` helpers below —
change the SDK import, the .create() call shape, and the cost-rate constants.
"""
from __future__ import annotations
import asyncio
import json
import os
import tempfile

from pydantic import ValidationError

from src import state
from src.prompts import (
    INTENT_AND_PROMPT_ENGINEERING,
    PPT_CONTENT_GENERATION,
    MCQ_GENERATION,
    RECKONER_GENERATION,
    TEACHING_TIPS_GENERATION,
    WORKSHEET_GENERATION,
    REVISION_MERGER,
    REPLY_PARSER_HAIKU,
)
from src.reply_parser import parse_reply, ReplyOutcome
from src.schemas import Intent, SlideDeck, MCQList, Reckoner, TeachingTips, Worksheet
from src.pptx_formatter import render_pptx
from src.pdf_formatter import render_pdf
from src.worksheet_formatter import render_worksheet_pdf


def _cost_cents(model: str, input_tokens: int, output_tokens: int) -> int:
    """Per-1M-token rates × tokens, in cents. Approximate; providers publish
    exact rates per model."""
    rates = {
        # OpenAI (current Monday stack)
        "gpt-4o": (2.50, 10.0),
        "gpt-4o-2024-08-06": (2.50, 10.0),
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4-turbo": (10.0, 30.0),
        # Anthropic (planned revert)
        "claude-sonnet-4-6": (3.0, 15.0),
        "claude-sonnet-4-5": (3.0, 15.0),
        "claude-haiku-4-5": (0.25, 1.25),
    }
    in_per_m, out_per_m = rates.get(model, (3.0, 15.0))
    dollars = (input_tokens / 1_000_000) * in_per_m + (output_tokens / 1_000_000) * out_per_m
    return int(round(dollars * 100))


def _strip_json_fences(text: str) -> str:
    """Defensive: strip ```json ... ``` wrappers if a model adds them.
    OpenAI's response_format=json_object should make this unnecessary,
    but we keep it as belt-and-suspenders."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        if text.endswith("```"):
            text = text[: -len("```")]
    return text.strip()


class Pipeline:
    def __init__(self, *, llm, whatsapp, storage, supabase, settings) -> None:
        self.llm = llm
        self.whatsapp = whatsapp
        self.storage = storage
        self.supabase = supabase
        self.settings = settings

    # --- LLM call helpers (override in tests via AsyncMock) ---
    # SWAP-BACK NOTE: when reverting to Anthropic Claude, only these two
    # methods need rewriting (replace OpenAI SDK calls + model field lookups
    # + token-usage field names). Method names stay provider-agnostic.

    async def call_llm_json(self, *, project_id: str, step: str, prompt: str) -> dict:
        """Call the content model with JSON mode and parse the response."""
        resp = await self.llm.chat.completions.create(
            model=self.settings.openai_content_model,
            max_tokens=4096,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content or "{}"
        usage = resp.usage
        state.insert_generation(
            self.supabase,
            project_id=project_id,
            step=step,
            model=self.settings.openai_content_model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_cents=_cost_cents(
                self.settings.openai_content_model,
                usage.prompt_tokens,
                usage.completion_tokens,
            ),
        )
        return json.loads(_strip_json_fences(text))

    async def call_llm_text(self, *, project_id: str, step: str, prompt: str,
                             model: str | None = None, max_tokens: int = 2048) -> str:
        """Call the LLM expecting plain text (revision merger, reply parser)."""
        model = model or self.settings.openai_content_model
        resp = await self.llm.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.choices[0].message.content or ""
        usage = resp.usage
        state.insert_generation(
            self.supabase,
            project_id=project_id,
            step=step,
            model=model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_cents=_cost_cents(model, usage.prompt_tokens, usage.completion_tokens),
        )
        return text.strip()

    # --- Generation pipeline ---

    async def generate(self, project_id: str) -> None:
        """Full generation pipeline: revision merger (conditional) → intent →
        3 parallel generators → 2 formatters → upload → CAS to awaiting_approval →
        send summary. CAS losses anywhere → silent exit."""
        try:
            project = state.get_project(self.supabase, project_id)
            if project is None:
                return

            # Step 0: revision merger (only when there are revisions)
            if (project.get("revision_count") or 0) > 0:
                brief = await self.call_llm_text(
                    project_id=project_id,
                    step="revision_merge",
                    prompt=REVISION_MERGER.format(
                        original_request=project["original_request"],
                        revisions_text=project["current_request"],
                    ),
                )
            else:
                brief = project["current_request"]

            # Step 1: intent + prompt engineering
            intent_raw = await self.call_llm_json(
                project_id=project_id,
                step="intent",
                prompt=INTENT_AND_PROMPT_ENGINEERING.format(transcript=brief),
            )
            intent = Intent.model_validate(intent_raw)

            # Steps 2/3/4/5/6: PPT / MCQ / Reckoner / Tips / Worksheet in parallel
            ppt_raw, mcq_raw, reckoner_raw, tips_raw, worksheet_raw = await asyncio.gather(
                self.call_llm_json(
                    project_id=project_id, step="ppt_content",
                    prompt=PPT_CONTENT_GENERATION.format(ppt_prompt=intent.ppt_prompt),
                ),
                self.call_llm_json(
                    project_id=project_id, step="mcq",
                    prompt=MCQ_GENERATION.format(mcq_prompt=intent.mcq_prompt),
                ),
                self.call_llm_json(
                    project_id=project_id, step="reckoner",
                    prompt=RECKONER_GENERATION.format(reckoner_prompt=intent.reckoner_prompt),
                ),
                self.call_llm_json(
                    project_id=project_id, step="teaching_tips",
                    prompt=TEACHING_TIPS_GENERATION.format(
                        teaching_tips_prompt=intent.teaching_tips_prompt,
                    ),
                ),
                self.call_llm_json(
                    project_id=project_id, step="worksheet",
                    prompt=WORKSHEET_GENERATION.format(
                        worksheet_prompt=intent.worksheet_prompt,
                    ),
                ),
            )
            slide_deck = SlideDeck.model_validate(ppt_raw)
            mcq_list = MCQList.model_validate(mcq_raw)
            reckoner = Reckoner.model_validate(reckoner_raw)
            teaching_tips = TeachingTips.model_validate(tips_raw)
            worksheet = Worksheet.model_validate(worksheet_raw)

            # Steps 6/7/8: render the three files
            with tempfile.TemporaryDirectory() as tmp:
                pptx_path = os.path.join(tmp, "lesson.pptx")
                pdf_path = os.path.join(tmp, "reckoner.pdf")
                ws_path = os.path.join(tmp, "worksheet.pdf")
                render_pptx(
                    [s.model_dump(exclude_none=True) for s in slide_deck.slides],
                    [m.model_dump(exclude_none=True) for m in mcq_list.mcqs],
                    pptx_path,
                    teacher_name=intent.teacher_name,
                    subject=intent.subject,
                )
                render_pdf(
                    reckoner.model_dump(exclude_none=True),
                    pdf_path,
                    teacher_name=intent.teacher_name,
                    teaching_tips=[t.model_dump() for t in teaching_tips.tips],
                    subject=intent.subject,
                )
                render_worksheet_pdf(
                    worksheet.model_dump(exclude_none=True),
                    ws_path,
                    subject=intent.subject,
                )

                with open(pptx_path, "rb") as f:
                    pptx_bytes = f.read()
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()
                with open(ws_path, "rb") as f:
                    ws_bytes = f.read()

            # Step 9: upload + sign — three artifacts in parallel
            bucket = self.settings.supabase_storage_bucket
            pptx_obj = f"{project_id}/lesson.pptx"
            pdf_obj = f"{project_id}/reckoner.pdf"
            ws_obj = f"{project_id}/worksheet.pdf"
            await asyncio.gather(
                self.storage.upload(
                    bucket=bucket, path=pptx_obj, content=pptx_bytes,
                    content_type=(
                        "application/vnd.openxmlformats-officedocument."
                        "presentationml.presentation"
                    ),
                ),
                self.storage.upload(
                    bucket=bucket, path=pdf_obj, content=pdf_bytes,
                    content_type="application/pdf",
                ),
                self.storage.upload(
                    bucket=bucket, path=ws_obj, content=ws_bytes,
                    content_type="application/pdf",
                ),
            )
            pptx_url, pdf_url, worksheet_url = await asyncio.gather(
                self.storage.signed_url(
                    bucket=bucket, path=pptx_obj,
                    expires_in_seconds=self.settings.signed_url_ttl_seconds,
                ),
                self.storage.signed_url(
                    bucket=bucket, path=pdf_obj,
                    expires_in_seconds=self.settings.signed_url_ttl_seconds,
                ),
                self.storage.signed_url(
                    bucket=bucket, path=ws_obj,
                    expires_in_seconds=self.settings.signed_url_ttl_seconds,
                ),
            )

            # Step 10: CAS → awaiting_approval; send summary
            summary = (
                f"Made: {intent.duration_min}-min {intent.subject} lesson for grade "
                f"{intent.grade} on {intent.topic} — {intent.n_slides} slides + "
                f"{intent.n_mcqs} MCQs + lesson plan + student worksheet.\n\n"
                "Reply APPROVE to receive the files, or describe what to change."
            )
            won = state.cas_to_awaiting_approval(
                self.supabase, project_id,
                summary=summary, pptx_url=pptx_url, pdf_url=pdf_url,
                worksheet_url=worksheet_url,
            )
            if not won:
                return

            project = state.get_project(self.supabase, project_id)
            if project is not None:
                result = await self.whatsapp.send_text(to=project["phone"], body=summary)
                state.insert_outbound_message(
                    self.supabase, project_id=project_id, provider_sid=result.sid,
                    from_phone=self.settings.twilio_whatsapp_from,
                    to_phone=project["phone"], body=summary,
                )

        except Exception as exc:  # noqa: BLE001 — prototype scope
            state.cas_to_error(
                self.supabase, project_id,
                error_reason=str(exc)[:500],
                expected_states=("generating",),
            )
            project = state.get_project(self.supabase, project_id)
            if project is not None:
                try:
                    await self.whatsapp.send_text(
                        to=project["phone"],
                        body="Something went wrong while generating your lesson — please try again.",
                    )
                except Exception:
                    pass  # don't compound failure during demo

    # --- Reply handling ---

    async def handle_reply(self, project_id: str, body: str) -> None:
        project = state.get_project(self.supabase, project_id)
        if project is None or project["state"] != "awaiting_approval":
            return

        async def haiku_classify(text: str) -> str:
            return await self.call_llm_text(
                project_id=project_id,
                step="reply_parse",
                prompt=REPLY_PARSER_HAIKU.format(body=text),
                model=self.settings.openai_classification_model,
                max_tokens=16,
            )

        outcome = await parse_reply(body, classify=haiku_classify)

        if outcome == ReplyOutcome.APPROVED:
            won = state.cas_to_approved(self.supabase, project_id)
            if not won:
                return
            project = state.get_project(self.supabase, project_id)
            urls = [
                ("Slides", project.get("pptx_url")),
                ("Lesson plan (teacher)", project.get("pdf_url")),
                ("Student worksheet", project.get("worksheet_url")),
            ]
            for label, url in urls:
                if not url:
                    continue
                body = f"{label}: {url}"
                result = await self.whatsapp.send_text(to=project["phone"], body=body)
                state.insert_outbound_message(
                    self.supabase, project_id=project_id, provider_sid=result.sid,
                    from_phone=self.settings.twilio_whatsapp_from,
                    to_phone=project["phone"], body=body,
                )
            state.cas_to_delivered(self.supabase, project_id)

        elif outcome == ReplyOutcome.CHANGES_REQUESTED:
            won = state.cas_to_generating_for_revision(self.supabase, project_id, body)
            if not won:
                return
            result = await self.whatsapp.send_text(
                to=project["phone"], body="Updating with your changes…",
            )
            state.insert_outbound_message(
                self.supabase, project_id=project_id, provider_sid=result.sid,
                from_phone=self.settings.twilio_whatsapp_from,
                to_phone=project["phone"], body="Updating with your changes…",
            )
            await self.generate(project_id)

        else:  # UNCLEAR
            result = await self.whatsapp.send_text(
                to=project["phone"],
                body=("I'm not sure — reply APPROVE to receive the files, "
                      "or describe what you'd like to change."),
            )
            state.insert_outbound_message(
                self.supabase, project_id=project_id, provider_sid=result.sid,
                from_phone=self.settings.twilio_whatsapp_from,
                to_phone=project["phone"], body="(clarification prompt)",
            )
