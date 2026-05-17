"""Bundled font assets + reportlab registration.

Tamil rendering needs a Tamil-script-aware font. Default reportlab Helvetica
and python-pptx Calibri don't include Tamil glyphs, so Tamil text renders as
tofu (☐). We bundle Noto Sans Tamil (Google open source) and register it
with reportlab so PDFs render correctly. PPT side just sets the run's font
name; PowerPoint substitutes from the system font catalog at open time.
"""
from __future__ import annotations
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"

TAMIL_REGULAR_TTF = FONTS_DIR / "NotoSansTamil-Regular.ttf"
TAMIL_BOLD_TTF = FONTS_DIR / "NotoSansTamil-Bold.ttf"

# These are the names the renderers reference downstream.
TAMIL_FONT_NAME = "NotoSansTamil"
TAMIL_FONT_BOLD_NAME = "NotoSansTamil-Bold"


# Per-process registration cache so we don't re-register on every render call.
_TAMIL_REGISTERED = False


def ensure_tamil_registered() -> bool:
    """Idempotent. Returns True iff Tamil rendering is available for reportlab.
    On a missing TTF (e.g., a stripped-down container deploy), returns False
    and the callers fall back to the default font — Tamil glyphs will render
    as tofu, but the PDF still produces."""
    global _TAMIL_REGISTERED
    if _TAMIL_REGISTERED:
        return True
    if not TAMIL_REGULAR_TTF.exists() or not TAMIL_BOLD_TTF.exists():
        return False
    pdfmetrics.registerFont(TTFont(TAMIL_FONT_NAME, str(TAMIL_REGULAR_TTF)))
    pdfmetrics.registerFont(TTFont(TAMIL_FONT_BOLD_NAME, str(TAMIL_BOLD_TTF)))
    pdfmetrics.registerFontFamily(
        TAMIL_FONT_NAME,
        normal=TAMIL_FONT_NAME,
        bold=TAMIL_FONT_BOLD_NAME,
    )
    _TAMIL_REGISTERED = True
    return True


def pptx_font_for_language(language: str | None) -> str | None:
    """Font-family name to set on python-pptx runs.

    Returns None for English (let python-pptx use its slide-master default,
    typically Calibri). Returns a Tamil-capable name for Tamil so the
    OOXML run carries `typeface="Noto Sans Tamil"` — PowerPoint substitutes
    from the system catalog at open time. "Noto Sans Tamil" is widely
    available on modern systems; if absent, Office picks the next Tamil
    font automatically."""
    if (language or "").lower() == "tamil":
        return "Noto Sans Tamil"
    return None


def pdf_font_for_language(language: str | None) -> str | None:
    """Reportlab font name for paragraph styles. Returns None for English
    (default Helvetica). For Tamil, ensures the TTF is registered and
    returns the registered name."""
    if (language or "").lower() == "tamil":
        if ensure_tamil_registered():
            return TAMIL_FONT_NAME
    return None
