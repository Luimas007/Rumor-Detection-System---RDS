"""Preprocessor tests — no ML, no network required."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.preprocessor.cleaner import (
    clean_text, detect_language, is_quality_content,
    normalise_date, word_count, fix_encoding, strip_html,
    normalise_whitespace, remove_web_noise,
)
from app.preprocessor.deduplicator import _content_fingerprint, _normalise_url


# ── Text utilities ─────────────────────────────────────────────────────────────

def test_strip_html_basic():
    assert strip_html("<div>Hello</div>") == " Hello "

def test_strip_html_nested():
    assert "<" not in strip_html("<p>A <b>bold</b> word.</p>")

def test_normalise_whitespace():
    assert normalise_whitespace("foo   bar\n\nbaz") == "foo bar baz"

def test_fix_encoding_curly_quotes():
    result = fix_encoding("‘Hello’ “World”")
    assert "'" in result and '"' in result

def test_fix_encoding_html_entities():
    assert fix_encoding("&amp;") == "&"
    assert fix_encoding("&lt;")  == "<"

def test_remove_web_noise_drops_subscribe():
    text = "Great article. Subscribe now to get more. Very informative piece."
    cleaned = remove_web_noise(text)
    assert "Subscribe now" not in cleaned

def test_clean_text_full_pipeline():
    raw = "<p>The president &amp; congress <b>agreed</b> on a $5 billion plan.</p>\n\nSubscribe now for more!"
    result = clean_text(raw)
    assert result is not None
    assert "<" not in result
    assert "agreed" in result


# ── Quality check ──────────────────────────────────────────────────────────────

def test_quality_fails_on_empty():
    assert not is_quality_content("")

def test_quality_fails_short():
    assert not is_quality_content("A short sentence.", min_words=50)

def test_quality_passes_long():
    text = (
        "Scientists discovered a new species of deep-sea fish near the Mariana Trench. "
        "The stock market closed higher following positive employment data released today. "
        "Climate researchers published findings on Arctic ice melt acceleration rates. "
        "A new treatment for antibiotic-resistant infections showed promise in clinical trials. "
        "Electric vehicle sales rose sharply in the third quarter across global markets. "
        "Astronomers detected unusual radio signals from a distant galaxy cluster last night. "
        "Health officials warned about rising respiratory illness rates expected this winter. "
        "Engineers unveiled a new bridge design that significantly resists earthquake damage. "
    )
    assert is_quality_content(text, min_words=50)

def test_quality_fails_high_repetition():
    text = ("Same sentence repeated again. " * 20)
    assert not is_quality_content(text, min_words=50)


# ── Date normalisation ─────────────────────────────────────────────────────────

def test_normalise_rfc2822():
    result = normalise_date("Wed, 01 Jan 2025 12:00:00 +0000")
    assert result == "2025-01-01T12:00:00Z"

def test_normalise_iso_passthrough():
    d = "2025-03-15T08:30:00Z"
    assert normalise_date(d) == d

def test_normalise_unix_timestamp():
    result = normalise_date("1700000000")
    assert result.startswith("2023-")

def test_normalise_empty():
    assert normalise_date("") == ""


# ── Deduplicator internals ─────────────────────────────────────────────────────

def test_url_normalise_strips_slash():
    from app.preprocessor.deduplicator import _normalise_url
    assert _normalise_url("https://example.com/") == "https://example.com"

def test_url_normalise_strips_utm():
    from app.preprocessor.deduplicator import _normalise_url
    url = "https://example.com/article?utm_source=twitter&utm_medium=social"
    assert "utm_source" not in _normalise_url(url)

def test_content_fingerprint_consistent():
    text = "This is a sample article about politics and government policy. " * 10
    fp1 = _content_fingerprint(text)
    fp2 = _content_fingerprint(text)
    assert fp1 == fp2

def test_content_fingerprint_differs():
    t1 = "Article about sports and football championships in Europe. " * 10
    t2 = "Article about science and space exploration missions. " * 10
    assert _content_fingerprint(t1) != _content_fingerprint(t2)
