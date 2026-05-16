"""Three-tier reply parser. Compliance with CLAUDE.md invariant:
regex first → Haiku only on ambiguity → never auto-decide ambiguous replies."""
from __future__ import annotations
import enum
import re
from typing import Awaitable, Callable


class ReplyOutcome(str, enum.Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    UNCLEAR = "unclear"


_APPROVAL_RE = re.compile(
    r"^\s*(approve|approved|yes|ok|okay|👍|✅|send|share|go|done|"
    r"all good|looks good)\s*[.!]?\s*$",
    re.IGNORECASE,
)

_CHANGES_MIN_LEN = 30  # chars; longer than this with no approval keyword → revision


async def parse_reply(
    body: str,
    *,
    classify: Callable[[str], Awaitable[str]],
) -> ReplyOutcome:
    """Classify a teacher's WhatsApp reply.

    `classify` is the Haiku tier-2 callback: takes the reply text, returns
    one of 'APPROVED' | 'CHANGES' | 'UNCLEAR'. Only called when tier 1 fails.
    """
    body = body.strip()
    if _APPROVAL_RE.match(body):
        return ReplyOutcome.APPROVED
    if len(body) >= _CHANGES_MIN_LEN:
        return ReplyOutcome.CHANGES_REQUESTED
    # Ambiguous: short reply without an approval keyword.
    raw = (await classify(body)).strip().upper()
    if raw == "APPROVED":
        return ReplyOutcome.APPROVED
    if raw == "CHANGES":
        return ReplyOutcome.CHANGES_REQUESTED
    return ReplyOutcome.UNCLEAR
