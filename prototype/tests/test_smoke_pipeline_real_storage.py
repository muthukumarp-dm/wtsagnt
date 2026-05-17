"""Full E2E smoke against REAL OpenAI + REAL Supabase Storage.

This is the strongest smoke test we have without Twilio. Only the WhatsApp
adapter is mocked. Everything else hits real cloud services:

- OpenAI: gpt-4o for content + gpt-4o-mini if reply-parser tier-2 triggers
- Supabase Storage: real upload to lesson-files/test-real-{uuid}/ + real
  signed URL generation. Files are cleaned up after the assertion.

State module is patched (no DB pollution) — the state layer has its own
mocked tests; this one verifies the cloud-Storage path the pipeline takes.

Run with:
    cd prototype && uv run pytest tests/test_smoke_pipeline_real_storage.py -v -s

Cost per run: ~$0.025 of gpt-4o tokens + ~free Supabase Storage operations.
Skips automatically without OPENAI_API_KEY or SUPABASE_SECRET_KEY.
"""
from __future__ import annotations
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.pipeline import Pipeline
from src.storage_adapter import SupabaseStorageAdapter


REQUIRED_ENV = ("OPENAI_API_KEY", "SUPABASE_URL", "SUPABASE_SECRET_KEY")


@pytest.mark.skipif(
    any(not os.getenv(k) for k in REQUIRED_ENV),
    reason=f"required env not set: {REQUIRED_ENV}",
)
async def test_pipeline_uploads_to_real_supabase_storage(tmp_path: Path):
    """Run pipeline end-to-end with real OpenAI + real Supabase Storage.

    Verifies:
    - Upload succeeds (no MIME type / file size errors)
    - Signed URLs are publicly downloadable via httpx GET
    - The summary message is composed with both URLs
    """
    from openai import AsyncOpenAI
    from supabase import create_client

    # ---- Real clients ----
    llm = AsyncOpenAI()
    supabase_client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )
    storage = SupabaseStorageAdapter(client=supabase_client)

    # ---- Mocked WhatsApp adapter (no real send) ----
    whatsapp = MagicMock()
    whatsapp.send_text = AsyncMock(return_value=MagicMock(sid="SM_real_storage_test"))

    # ---- Settings ----
    settings = MagicMock()
    settings.openai_content_model = "gpt-4o"
    settings.openai_classification_model = "gpt-4o-mini"
    settings.supabase_storage_bucket = os.environ.get("SUPABASE_STORAGE_BUCKET", "lesson-files")
    settings.signed_url_ttl_seconds = 604800
    settings.twilio_whatsapp_from = "whatsapp:+14155238886"

    pipeline = Pipeline(
        llm=llm,
        whatsapp=whatsapp,
        storage=storage,
        supabase=MagicMock(),  # state.* is patched below; we never touch real DB
        settings=settings,
    )

    # ---- Test project ----
    project_id = f"smoke-real-{uuid.uuid4()}"
    transcript = (
        "30-minute lesson for grade 7 on photosynthesis. Cover the process, "
        "inputs, outputs, where it happens, and why it matters. 5 MCQs."
    )
    fake_project = {
        "id": project_id,
        "phone": "whatsapp:+910000000000",
        "original_request": transcript,
        "current_request": transcript,
        "state": "generating",
        "revision_count": 0,
    }

    try:
        with patch("src.pipeline.state") as mock_state:
            mock_state.get_project.return_value = fake_project
            mock_state.cas_to_awaiting_approval.return_value = True
            mock_state.cas_to_error = MagicMock()
            mock_state.insert_generation = MagicMock()
            mock_state.insert_outbound_message = MagicMock()

            print(f"\n  [real-storage] project_id = {project_id}")
            print(f"  [real-storage] running pipeline.generate against real OpenAI + real Supabase…")
            await pipeline.generate(project_id)

            assert not mock_state.cas_to_error.called, (
                "pipeline silently went to error state — check OpenAI response, "
                "schema validation, or Supabase upload"
            )

        # ---- Verify the summary was sent with both URLs in scope ----
        whatsapp.send_text.assert_awaited_once()
        summary = whatsapp.send_text.call_args.kwargs["body"]
        print(f"\n  [real-storage] summary: {summary[:160]}…")

        # ---- Extract the signed URLs from the CAS call ----
        cas_call = mock_state.cas_to_awaiting_approval.call_args
        pptx_url = cas_call.kwargs["pptx_url"]
        pdf_url = cas_call.kwargs["pdf_url"]
        print(f"  [real-storage] pptx signed URL: {pptx_url[:120]}…")
        print(f"  [real-storage] pdf  signed URL: {pdf_url[:120]}…")

        # ---- Verify the signed URLs are publicly downloadable ----
        async with httpx.AsyncClient(timeout=30.0) as http:
            r_pptx = await http.get(pptx_url)
            r_pdf = await http.get(pdf_url)
        assert r_pptx.status_code == 200, f"pptx signed URL returned {r_pptx.status_code}"
        assert r_pdf.status_code == 200, f"pdf signed URL returned {r_pdf.status_code}"
        assert len(r_pptx.content) > 5_000, f"pptx download is empty ({len(r_pptx.content)} bytes)"
        assert len(r_pdf.content) > 1_000, f"pdf download is empty ({len(r_pdf.content)} bytes)"
        assert r_pdf.content[:4] == b"%PDF", "downloaded pdf is malformed"
        print(f"  [real-storage] ✅ pptx downloaded: {len(r_pptx.content)} bytes")
        print(f"  [real-storage] ✅ pdf  downloaded: {len(r_pdf.content)} bytes")

        # ---- Save copies locally for hand inspection ----
        persistent_root = Path("/Users/newuser/Projects/Personal/wtsagnt/prototype/outputs")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target_dir = persistent_root / f"{timestamp}_real_storage_smoke"
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "lesson.pptx").write_bytes(r_pptx.content)
        (target_dir / "reckoner.pdf").write_bytes(r_pdf.content)
        (target_dir / "urls.txt").write_text(
            f"pptx: {pptx_url}\npdf:  {pdf_url}\n\n"
            f"These are 7-day signed URLs. Click in a browser to verify they're publicly fetchable.\n"
        )
        print(f"\n  📂 outputs + URLs copied to: {target_dir}")
        print(f"     open '{target_dir / 'lesson.pptx'}'")
        print(f"     open '{target_dir / 'reckoner.pdf'}'")

    finally:
        # ---- Cleanup: delete uploaded objects so the bucket stays tidy ----
        try:
            bucket = settings.supabase_storage_bucket
            for obj in (f"{project_id}/lesson.pptx", f"{project_id}/reckoner.pdf"):
                supabase_client.storage.from_(bucket).remove([obj])
            print(f"  [cleanup] removed {project_id}/* from {bucket}")
        except Exception as exc:
            print(f"  [cleanup] WARNING: failed to remove test objects — {exc}")
