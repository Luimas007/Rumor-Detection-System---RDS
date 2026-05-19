# coding: utf-8
"""Scraper tests -- no network, no model downloads required."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.models.schemas import RawResult, Article, SearchJob, JobStatus, FetchMode
from app.preprocessor.cleaner import (
    clean_text, detect_language, is_quality_content, normalise_date, word_count,
)
from app.preprocessor.deduplicator import dedup_by_url, dedup_by_content


# -- Cleaner -------------------------------------------------------------------

def test_clean_text_strips_html():
    result = clean_text(
        "<p>Hello <b>World</b>, welcome to the global news coverage"
        " article about current events happening today.</p>"
    )
    assert result is not None
    assert "<" not in result
    assert "Hello" in result

def test_clean_text_empty_returns_none():
    assert clean_text("") is None
    assert clean_text("   ") is None

def test_clean_text_fixes_encoding():
    raw = "The president &amp; congress discussed a broad range of topics at the annual summit."
    result = clean_text(raw)
    assert result is not None
    assert "congress" in result
    assert "&amp;" not in result

def test_word_count():
    assert word_count("hello world foo bar") == 4
    assert word_count("") == 0

def test_is_quality_content_too_short():
    assert not is_quality_content("Too short.", min_words=50)

def test_is_quality_content_valid():
    text = (
        "The government announced a major new policy on climate change and emissions reduction today. "
        "Scientists from leading universities published research confirming the policy is evidence-based. "
        "Industry groups expressed mixed reactions with some welcoming the regulatory changes proposed. "
        "Environmental activists praised the announcement as an important step forward in decarbonisation. "
        "International observers noted the policy could influence similar legislation in other countries. "
        "Economic analysts forecast modest short-term costs but significant long-term benefits overall. "
        "The opposition party called for further consultation before the bill proceeds to parliament. "
        "Citizens polled in urban areas expressed broad support for tighter emissions standards nationwide. "
    )
    assert is_quality_content(text, min_words=50)

def test_normalise_date_rfc2822():
    raw = "Mon, 15 Jan 2024 10:30:00 +0000"
    result = normalise_date(raw)
    assert result.startswith("2024-01-15")

def test_normalise_date_passthrough():
    raw = "2024-06-01T12:00:00Z"
    assert normalise_date(raw) == raw

def test_normalise_date_empty():
    assert normalise_date("") == ""


# -- Deduplicator --------------------------------------------------------------

def test_dedup_by_url_removes_exact_duplicates():
    results = [
        RawResult(url="https://example.com/", title="A", source="X", source_type="x"),
        RawResult(url="https://example.com",  title="B", source="Y", source_type="y"),
        RawResult(url="https://other.com",    title="C", source="Z", source_type="z"),
    ]
    unique = dedup_by_url(results)
    assert len(unique) == 2

def test_dedup_by_url_strips_tracking_params():
    results = [
        RawResult(url="https://news.com/article?utm_source=twitter", title="A", source="X", source_type="x"),
        RawResult(url="https://news.com/article", title="B", source="Y", source_type="y"),
    ]
    unique = dedup_by_url(results)
    assert len(unique) == 1

def test_dedup_by_content_removes_near_duplicates():
    body = "Scientists confirmed the drug reduces mortality by forty percent. " * 30
    a1 = Article(url="https://a.com", content=body)
    a2 = Article(url="https://b.com", content=body)
    a3 = Article(url="https://c.com", content="Completely different content about sports. " * 30)
    unique, removed = dedup_by_content([a1, a2, a3])
    assert len(unique) == 2
    assert removed == 1

def test_dedup_by_content_keeps_no_content_articles():
    a1 = Article(url="https://a.com", content="")
    a2 = Article(url="https://b.com", content="")
    unique, removed = dedup_by_content([a1, a2])
    assert len(unique) == 2
    assert removed == 0


# -- Schemas -------------------------------------------------------------------

def test_raw_result_fields():
    r = RawResult(url="https://example.com", title="Test", source="NewsX", source_type="google_news")
    assert r.url == "https://example.com"
    assert r.source_type == "google_news"
    assert r.snippet == ""

def test_article_to_dict():
    a = Article(
        url="https://example.com", title="Test Article",
        content="Some article content.", fetch_mode=FetchMode.FULL,
    )
    d = a.to_dict()
    assert d["url"] == "https://example.com"
    assert d["fetch_mode"] == "full"
    assert "content" in d

def test_search_job_defaults():
    job = SearchJob(query="test query")
    assert job.status == JobStatus.PENDING
    assert isinstance(job.id, str) and len(job.id) == 36
    assert job.articles == []

def test_search_job_to_dict():
    job = SearchJob(query="climate change", sources=["google_news", "reddit"])
    d = job.to_dict()
    assert d["query"] == "climate change"
    assert d["status"] == "pending"
    assert "articles" in d
    assert "stats" in d


# -- Sources (no network) ------------------------------------------------------

def test_google_news_source_init():
    from app.scraper.sources.google_news import GoogleNewsSource
    src = GoogleNewsSource({"max_results": 5, "enabled": True})
    assert src.name == "Google News"
    assert src.source_type == "google_news"
    assert src.max_results == 5

def test_source_registry_complete():
    from app.scraper.sources import SOURCE_REGISTRY
    expected = {"google_news", "bing_news", "reddit", "hackernews", "duckduckgo", "portals", "google_web"}
    assert expected == set(SOURCE_REGISTRY.keys())

def test_disabled_source_returns_empty():
    from app.scraper.sources.bing_news import BingNewsSource
    src = BingNewsSource({"enabled": False})
    assert src.safe_search("test") == []

def test_google_web_source_init():
    from app.scraper.sources.google_search import GoogleWebSource
    src = GoogleWebSource({"enabled": True, "max_results": 10, "sleep_interval": 0.5})
    assert src.name == "Google Web"
    assert src.source_type == "google_web"
    assert src.sleep_interval == 0.5

def test_portal_aggregator_init():
    from app.scraper.sources.rss_feed import PortalAggregatorSource
    feeds = [{"name": "Test Portal", "rss_url": "https://example.com/rss", "enabled": True}]
    src = PortalAggregatorSource({"enabled": True, "max_results": 50, "max_per_feed": 5, "feeds": feeds})
    assert src.name == "News Portals"
    assert src.source_type == "portals"
    assert len(src.feeds) == 1
    assert src.max_per_feed == 5

def test_portal_aggregator_disabled_returns_empty():
    from app.scraper.sources.rss_feed import PortalAggregatorSource
    src = PortalAggregatorSource({"enabled": False, "feeds": []})
    assert src.safe_search("test") == []

def test_portal_no_feeds_returns_empty():
    from app.scraper.sources.rss_feed import PortalAggregatorSource
    src = PortalAggregatorSource({"enabled": True, "feeds": []})
    assert src.safe_search("test") == []

def test_portal_relevance_exact_phrase_passes():
    from app.scraper.sources.rss_feed import _relevance_score, _parse_query
    keywords, phrases = _parse_query("climate change")
    score = _relevance_score("Climate change threatens coastal cities", "", keywords, phrases)
    assert score == 1.0

def test_portal_relevance_no_match_fails():
    from app.scraper.sources.rss_feed import _relevance_score, _parse_query
    keywords, phrases = _parse_query("artificial intelligence")
    score = _relevance_score("Local football team wins championship game", "", keywords, phrases)
    assert score < 0.3

def test_portal_relevance_partial_keyword_match():
    from app.scraper.sources.rss_feed import _relevance_score, _parse_query
    keywords, phrases = _parse_query("bitcoin cryptocurrency market")
    # Only "bitcoin" appears in title -- should score enough to pass
    score = _relevance_score("Bitcoin price surges to record high", "", keywords, phrases)
    assert score >= 0.3

def test_portal_relevance_word_boundary():
    from app.scraper.sources.rss_feed import _relevance_score, _parse_query
    keywords, phrases = _parse_query("change")
    # "exchange" should NOT count as a match for "change"
    score = _relevance_score("Stock exchange reports record volume", "", keywords, phrases)
    assert score < 0.3
