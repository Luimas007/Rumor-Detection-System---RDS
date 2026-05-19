"""Basic scraper tests (no network required for most)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.models.schemas import RawArticle, SearchJob, JobStatus
from app.scraper.pipeline import build_analyzed_base
from app.utils.text_cleaner import (
    clean_article_text, strip_html, normalize_whitespace,
    split_into_sentences, count_words,
)


# ─── Text cleaner ─────────────────────────────────────────────────────────────

def test_strip_html():
    assert strip_html("<p>Hello <b>World</b></p>") == " Hello  World  "

def test_normalize_whitespace():
    assert normalize_whitespace("foo   bar\n\nbaz") == "foo bar baz"

def test_clean_article_text_basic():
    raw = "<p>The government <b>confirmed</b> plans worth $5 billion.</p>"
    result = clean_article_text(raw)
    assert result is not None
    assert "government" in result
    assert "<" not in result

def test_clean_article_text_returns_none_for_empty():
    assert clean_article_text("") is None
    assert clean_article_text("   ") is None

def test_split_into_sentences():
    text = "The sun rises. It sets in the west. Every day this happens."
    sents = split_into_sentences(text)
    assert len(sents) >= 2

def test_count_words():
    assert count_words("Hello world foo") == 3


# ─── Schema ───────────────────────────────────────────────────────────────────

def test_raw_article_to_dict():
    a = RawArticle(url="https://example.com", title="Test", source="Test News")
    d = a.to_dict()
    assert d["url"] == "https://example.com"
    assert d["title"] == "Test"

def test_search_job_defaults():
    job = SearchJob(query="test query")
    assert job.status == JobStatus.PENDING
    assert job.query == "test query"
    assert isinstance(job.id, str) and len(job.id) == 36

def test_search_job_serialisation():
    job = SearchJob(query="climate change", sources=["google_news"])
    d = job.to_dict()
    assert d["query"] == "climate change"
    assert d["status"] == "pending"
    assert "articles" in d


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def test_build_analyzed_base_valid():
    raw = RawArticle(url="https://example.com", title="Big News", source="NewsX")
    content = "Scientists discovered a new planet orbiting a distant star. " * 10
    result = build_analyzed_base(raw, content)
    assert result is not None
    assert result["url"] == "https://example.com"
    assert result["word_count"] > 0

def test_build_analyzed_base_too_short():
    raw = RawArticle(url="https://example.com", title="X", source="Y")
    result = build_analyzed_base(raw, "Short.", min_word_count=40)
    assert result is None


# ─── Source config (no network) ───────────────────────────────────────────────

def test_google_news_source_init():
    from app.scraper.sources.google_news import GoogleNewsSource
    src = GoogleNewsSource({"max_results": 5, "enabled": True})
    assert src.name == "google_news"
    assert src.max_results == 5

def test_reddit_source_init():
    from app.scraper.sources.reddit import RedditSource
    src = RedditSource({"max_results": 8, "enabled": False})
    assert not src.enabled
