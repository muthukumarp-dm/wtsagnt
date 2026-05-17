"""Font registration + language → font helper tests."""
from src.fonts import (
    ensure_tamil_registered,
    pdf_font_for_language,
    pptx_font_for_language,
    TAMIL_FONT_NAME,
    TAMIL_REGULAR_TTF,
    TAMIL_BOLD_TTF,
)


def test_tamil_ttf_files_are_bundled():
    """The repo must ship the Tamil TTFs — without them, PDF Tamil = tofu."""
    assert TAMIL_REGULAR_TTF.exists(), f"missing: {TAMIL_REGULAR_TTF}"
    assert TAMIL_BOLD_TTF.exists(), f"missing: {TAMIL_BOLD_TTF}"
    # Header byte check: TTF starts with 0x00010000 or 'OTTO' or 'true'
    with open(TAMIL_REGULAR_TTF, "rb") as f:
        head = f.read(4)
    assert head in (b"\x00\x01\x00\x00", b"OTTO", b"true"), (
        f"not a TTF: header was {head!r}"
    )


def test_ensure_tamil_registered_is_idempotent():
    assert ensure_tamil_registered() is True
    assert ensure_tamil_registered() is True  # second call must not error
    # The reportlab pdfmetrics module should now know about the font
    from reportlab.pdfbase import pdfmetrics
    assert pdfmetrics.getFont(TAMIL_FONT_NAME) is not None


def test_pdf_font_for_language_tamil():
    assert pdf_font_for_language("tamil") == TAMIL_FONT_NAME
    assert pdf_font_for_language("Tamil") == TAMIL_FONT_NAME  # case-insensitive


def test_pdf_font_for_language_english_is_none():
    assert pdf_font_for_language("english") is None
    assert pdf_font_for_language(None) is None
    assert pdf_font_for_language("") is None


def test_pptx_font_for_language_tamil():
    """PPT carries a font face name; PowerPoint substitutes from the
    system font catalog. Returns the human-readable family name, NOT
    the reportlab-registered short name."""
    assert pptx_font_for_language("tamil") == "Noto Sans Tamil"


def test_pptx_font_for_language_english_is_none():
    assert pptx_font_for_language("english") is None
    assert pptx_font_for_language(None) is None
