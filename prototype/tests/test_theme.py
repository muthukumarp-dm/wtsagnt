"""Subject → palette lookup."""
from src.theme import palette_for_subject


def test_palette_science_keywords_route_to_science():
    for subj in ["Science", "Biology", "Chemistry", "physics", "STEM lab"]:
        assert palette_for_subject(subj).name == "science"


def test_palette_math_keywords_route_to_math():
    for subj in ["Mathematics", "Algebra 1", "Geometry", "Trigonometry"]:
        assert palette_for_subject(subj).name == "math"


def test_palette_history_keywords_route_to_history():
    assert palette_for_subject("History").name == "history"
    assert palette_for_subject("Social studies").name == "history"
    assert palette_for_subject("Civics").name == "history"


def test_palette_english_includes_indian_languages():
    assert palette_for_subject("English literature").name == "english"
    assert palette_for_subject("Tamil").name == "english"
    assert palette_for_subject("Hindi grammar").name == "english"


def test_palette_unknown_subject_falls_back_to_default():
    assert palette_for_subject("Underwater basket weaving").name == "default"
    assert palette_for_subject("").name == "default"
    assert palette_for_subject(None).name == "default"


def test_palette_returns_rgb_tuples():
    p = palette_for_subject("Science")
    assert len(p.primary) == 3
    assert all(0 <= c <= 255 for c in p.primary)
    assert all(0 <= c <= 255 for c in p.accent)
