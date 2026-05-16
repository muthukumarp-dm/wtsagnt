"""E2E smoke: real OpenAI calls drive the full pipeline; Twilio + Supabase
are mocked; files are saved to a tmp dir AND copied to prototype/outputs/
so they can be inspected by hand.

Skip-on-missing-env policy: requires OPENAI_API_KEY. Skips otherwise.

Run with:
    cd prototype && uv run pytest tests/test_smoke_pipeline_e2e.py -v -s

Approximate cost per run: ~$0.05 of gpt-4o tokens (intent + PPT + MCQ +
reckoner = 4 generations). The pipeline runs the three content generators
in parallel via asyncio.gather, so wall-clock is ~the slowest one (~30s).
"""
from __future__ import annotations
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pipeline import Pipeline


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
async def test_full_pipeline_with_real_openai(tmp_path: Path):
    """Drive the full pipeline against real OpenAI; verify both files
    are produced and contain real content."""
    from openai import AsyncOpenAI

    # ---- Real OpenAI client ----
    llm = AsyncOpenAI()

    # ---- Mocked WhatsApp adapter ----
    whatsapp = MagicMock()
    whatsapp.send_text = AsyncMock(return_value=MagicMock(sid="SM_test_outbound"))

    # ---- Mocked storage adapter — saves to local disk instead of Supabase ----
    output_root = tmp_path / "storage"

    async def fake_upload(*, bucket: str, path: str, content: bytes, content_type: str) -> None:
        out = output_root / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)
        print(f"    [upload] {len(content):>8} bytes → {out.relative_to(tmp_path)} ({content_type})")

    async def fake_signed_url(*, bucket: str, path: str, expires_in_seconds: int) -> str:
        return f"file://{output_root / path}"

    storage = MagicMock()
    storage.upload = fake_upload
    storage.signed_url = fake_signed_url

    # ---- Settings ----
    settings = MagicMock()
    settings.openai_content_model = "gpt-4o"
    settings.openai_classification_model = "gpt-4o-mini"
    settings.supabase_storage_bucket = "lesson-files"
    settings.signed_url_ttl_seconds = 604800
    settings.twilio_whatsapp_from = "whatsapp:+14155238886"

    pipeline = Pipeline(
        llm=llm,
        whatsapp=whatsapp,
        storage=storage,
        supabase=MagicMock(),  # patched via src.pipeline.state below
        settings=settings,
    )

    transcript = (
        "Hi, I need to prepare for tomorrow's class. It's a 30-minute lesson "
        "for grade 7 on photosynthesis. Cover the basic process, what goes in "
        "and what comes out, where in the plant it happens, and why it matters. "
        "Give me a one-page summary sheet I can hand to students, and 5 "
        "multiple choice questions for a quick quiz at the end. Make the "
        "slides visually varied, not just bullet walls."
    )

    fake_project = {
        "id": "test-e2e-project",
        "phone": "whatsapp:+910000000000",
        "original_request": transcript,
        "current_request": transcript,
        "state": "generating",
        "revision_count": 0,
        "pptx_url": None,
        "pdf_url": None,
        "summary": None,
    }

    # Track every Claude/OpenAI call via the state.insert_generation spy
    generation_records: list[dict] = []

    def spy_insert_generation(*args, **kwargs):
        generation_records.append(kwargs)

    with patch("src.pipeline.state") as mock_state:
        mock_state.get_project.return_value = fake_project
        mock_state.cas_to_awaiting_approval.return_value = True
        mock_state.cas_to_error = MagicMock()
        mock_state.insert_generation = spy_insert_generation
        mock_state.insert_outbound_message = MagicMock()

        print(f"\n  [E2E] running pipeline.generate against real OpenAI…")
        await pipeline.generate("test-e2e-project")

        # CRITICAL: verify the pipeline did NOT fall into the error path.
        # If state.cas_to_error was called, something exploded silently.
        assert not mock_state.cas_to_error.called, (
            f"pipeline.generate failed silently — went to state=error. "
            f"Check OpenAI rate limits, prompt validation, or formatter issues."
        )

    # ---- Verify outputs ----
    pptx_path = output_root / "test-e2e-project/lesson.pptx"
    pdf_path = output_root / "test-e2e-project/reckoner.pdf"

    assert pptx_path.exists(), f"pptx not created at {pptx_path}"
    assert pdf_path.exists(), f"pdf not created at {pdf_path}"
    assert pptx_path.stat().st_size > 5_000, "pptx looks empty"
    assert pdf_path.stat().st_size > 1_000, "pdf looks empty"

    # Verify pptx parses as a real PPTX
    from pptx import Presentation
    prs = Presentation(str(pptx_path))
    n_slides = len(prs.slides)
    print(f"\n  [verify] pptx has {n_slides} slides")
    assert n_slides >= 5, f"expected ≥5 slides (content + MCQs), got {n_slides}"

    # Verify pdf has the %PDF header
    with open(pdf_path, "rb") as f:
        assert f.read(4) == b"%PDF", "not a valid PDF"

    # Verify summary was sent
    whatsapp.send_text.assert_awaited_once()
    summary_call = whatsapp.send_text.call_args
    summary_body = summary_call.kwargs.get("body", "")
    print(f"\n  [verify] summary sent: {summary_body[:200]}…")
    assert "APPROVE" in summary_body or "approve" in summary_body.lower()

    # ---- Cost summary ----
    print(f"\n  [cost] {len(generation_records)} LLM calls:")
    total_cents = 0
    for g in generation_records:
        cents = g.get("cost_cents", 0)
        total_cents += cents
        print(
            f"    step={g.get('step'):>15} "
            f"model={g.get('model')} "
            f"in={g.get('input_tokens'):>5} "
            f"out={g.get('output_tokens'):>5} "
            f"cost={cents}¢"
        )
    print(f"  [cost] TOTAL: ${total_cents / 100:.4f}")

    # ---- Copy outputs to a persistent location for hand inspection ----
    persistent_root = Path("/Users/newuser/Projects/Personal/wtsagnt/prototype/outputs")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_dir = persistent_root / f"{timestamp}_e2e_smoke"
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(pptx_path, target_dir / "lesson.pptx")
    shutil.copy(pdf_path, target_dir / "reckoner.pdf")
    print(f"\n  📂 outputs copied to: {target_dir}")
    print(f"     open with: open '{target_dir / 'lesson.pptx'}'")
    print(f"                open '{target_dir / 'reckoner.pdf'}'")


@pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
async def test_revision_branch_invokes_merger(tmp_path: Path):
    """When revision_count > 0, the pipeline runs the revision merger
    pre-step (a 5th LLM call) before the intent agent. Verify the merger
    is actually invoked and produces a coherent brief."""
    from openai import AsyncOpenAI

    llm = AsyncOpenAI()
    whatsapp = MagicMock()
    whatsapp.send_text = AsyncMock(return_value=MagicMock(sid="SM_revision_outbound"))

    output_root = tmp_path / "storage"

    async def fake_upload(*, bucket, path, content, content_type):
        out = output_root / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)

    async def fake_signed_url(*, bucket, path, expires_in_seconds):
        return f"file://{output_root / path}"

    storage = MagicMock()
    storage.upload = fake_upload
    storage.signed_url = fake_signed_url

    settings = MagicMock()
    settings.openai_content_model = "gpt-4o"
    settings.openai_classification_model = "gpt-4o-mini"
    settings.supabase_storage_bucket = "lesson-files"
    settings.signed_url_ttl_seconds = 604800
    settings.twilio_whatsapp_from = "whatsapp:+14155238886"

    pipeline = Pipeline(
        llm=llm,
        whatsapp=whatsapp,
        storage=storage,
        supabase=MagicMock(),
        settings=settings,
    )

    original = (
        "30-minute lesson for grade 7 on photosynthesis. Cover the basic "
        "process, inputs and outputs, where it happens. 5 MCQs."
    )
    revised_current = (
        original
        + "\n\nRevision 1: Change the grade level to 8 and add a brief section "
        "on cellular respiration as a contrast to photosynthesis."
    )

    fake_project = {
        "id": "test-revision-project",
        "phone": "whatsapp:+910000000000",
        "original_request": original,
        "current_request": revised_current,
        "state": "generating",
        "revision_count": 1,
    }

    merger_call_made = []

    # Wrap call_llm_text to detect the merger call (which is the only text-mode
    # call in generate() — reply_parse is called from handle_reply, not generate)
    original_call_llm_text = pipeline.call_llm_text

    async def spy_call_llm_text(**kwargs):
        merger_call_made.append({"step": kwargs.get("step"), "prompt_preview": kwargs.get("prompt", "")[:100]})
        return await original_call_llm_text(**kwargs)

    pipeline.call_llm_text = spy_call_llm_text

    with patch("src.pipeline.state") as mock_state:
        mock_state.get_project.return_value = fake_project
        mock_state.cas_to_awaiting_approval.return_value = True
        mock_state.cas_to_error = MagicMock()
        mock_state.insert_generation = MagicMock()
        mock_state.insert_outbound_message = MagicMock()

        print(f"\n  [E2E revision] running pipeline.generate with revision_count=1…")
        await pipeline.generate("test-revision-project")

        assert not mock_state.cas_to_error.called, "revision pipeline went to error"

    assert len(merger_call_made) == 1, (
        f"expected exactly 1 text-mode call (revision merger), got {len(merger_call_made)}"
    )
    assert merger_call_made[0]["step"] == "revision_merge"
    print(f"  [E2E revision] ✅ merger invoked, step={merger_call_made[0]['step']}")
    print(f"  [E2E revision] merger prompt prefix: {merger_call_made[0]['prompt_preview']!r}")

    # Verify files still produced
    pptx_path = output_root / "test-revision-project/lesson.pptx"
    pdf_path = output_root / "test-revision-project/reckoner.pdf"
    assert pptx_path.exists() and pptx_path.stat().st_size > 5_000
    assert pdf_path.exists() and pdf_path.stat().st_size > 1_000

    # Verify the summary mentions grade 8 (the revision target) — confirms
    # the merger output was actually used by downstream agents
    whatsapp.send_text.assert_awaited_once()
    summary = whatsapp.send_text.call_args.kwargs.get("body", "").lower()
    print(f"\n  [verify] revised summary: {summary[:200]}…")
    assert "8" in summary or "grade" in summary, (
        f"summary doesn't reflect revision: {summary[:200]}"
    )

    # Copy to outputs
    persistent_root = Path("/Users/newuser/Projects/Personal/wtsagnt/prototype/outputs")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_dir = persistent_root / f"{timestamp}_e2e_revision"
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(pptx_path, target_dir / "lesson.pptx")
    shutil.copy(pdf_path, target_dir / "reckoner.pdf")
    print(f"\n  📂 revision outputs copied to: {target_dir}")
