"""Subject-aware color palettes.

The renderer picks a palette from the lesson's subject and applies it to the
title text, the accent shape on the title slide, and the section-heading
colors in the PDF. Same content engine, different visual identity per subject
— so the artifact doesn't read as a default-themed generic AI deck.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    """An RGB triplet for primary (titles, accents) and a softer accent for
    bullet markers / underlines. Values are 0..255 ints."""
    name: str
    primary: tuple[int, int, int]
    accent: tuple[int, int, int]


# Buckets are intentionally broad — we match keywords, not exact subject names.
# Defaults to "default" if no keyword fires.
_PALETTES: dict[str, Palette] = {
    "science": Palette("science", primary=(15, 118, 110), accent=(110, 231, 183)),  # teal / mint
    "math": Palette("math", primary=(30, 64, 175), accent=(147, 197, 253)),         # indigo / sky
    "history": Palette("history", primary=(146, 64, 14), accent=(252, 211, 77)),    # sepia / amber
    "english": Palette("english", primary=(136, 19, 55), accent=(244, 114, 182)),   # mulberry / pink
    "geography": Palette("geography", primary=(22, 101, 52), accent=(190, 242, 100)),  # forest / lime
    "default": Palette("default", primary=(30, 41, 59), accent=(148, 163, 184)),    # slate
}


# Keyword → bucket. Lowercased subject is scanned for the first hit.
_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("science", "biology", "chemistry", "physics", "stem"), "science"),
    (("math", "algebra", "geometry", "arithmetic", "calculus", "trig"), "math"),
    (("history", "civics", "social"), "history"),
    (("english", "language", "literature", "grammar", "tamil", "hindi"), "english"),
    (("geography", "geo", "environment"), "geography"),
]


def palette_for_subject(subject: str | None) -> Palette:
    """Return the palette for a subject string. Falls back to the slate
    'default' palette when nothing matches."""
    if not subject:
        return _PALETTES["default"]
    s = subject.lower()
    for keywords, bucket in _KEYWORDS:
        if any(k in s for k in keywords):
            return _PALETTES[bucket]
    return _PALETTES["default"]
