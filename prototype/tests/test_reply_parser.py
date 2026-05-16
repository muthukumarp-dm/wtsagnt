"""TDD for the 3-tier reply parser: regex → Haiku → unclear (no auto-decide)."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.reply_parser import parse_reply, ReplyOutcome


# --- Tier 1: regex hits (no Haiku call) ---

@pytest.mark.parametrize("body", [
    "APPROVE", "approve", "yes", "OK", "ok.", "okay",
    "👍", "✅", "send", "share", "go", "done", "all good", "looks good",
])
async def test_tier1_approval_keywords(body):
    haiku = AsyncMock()
    outcome = await parse_reply(body, classify=haiku)
    assert outcome == ReplyOutcome.APPROVED
    haiku.assert_not_called()


async def test_tier1_long_body_is_changes_requested():
    haiku = AsyncMock()
    outcome = await parse_reply(
        "Please change the topic to cellular respiration and target grade 8 instead",
        classify=haiku,
    )
    assert outcome == ReplyOutcome.CHANGES_REQUESTED
    haiku.assert_not_called()


# --- Tier 2: Haiku fallback ---

async def test_tier2_haiku_returns_approved():
    haiku = AsyncMock(return_value="APPROVED")
    outcome = await parse_reply("sure thing", classify=haiku)
    assert outcome == ReplyOutcome.APPROVED
    haiku.assert_awaited_once()


async def test_tier2_haiku_returns_changes():
    haiku = AsyncMock(return_value="CHANGES")
    outcome = await parse_reply("hmm switch it up", classify=haiku)
    assert outcome == ReplyOutcome.CHANGES_REQUESTED


async def test_tier2_haiku_returns_unclear():
    haiku = AsyncMock(return_value="UNCLEAR")
    outcome = await parse_reply("???", classify=haiku)
    assert outcome == ReplyOutcome.UNCLEAR


async def test_tier3_malformed_haiku_output_is_unclear():
    haiku = AsyncMock(return_value="MAYBE or something else")
    outcome = await parse_reply("idk", classify=haiku)
    assert outcome == ReplyOutcome.UNCLEAR
