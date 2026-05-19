# coding: utf-8
"""Portal RSS aggregator -- fetches major news portals concurrently, scores by query relevance."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterator

import feedparser

from app.models.schemas import RawResult
from app.utils.logger import get_logger
from .base import BaseSource

logger = get_logger(__name__)

_WORD_RE = re.compile(r"\b[a-zA-Z0-9]+\b")

_STOP_WORDS = {
    "the", "and", "or", "in", "of", "a", "an", "to", "is", "are", "was",
    "for", "on", "at", "by", "it", "its", "this", "that", "with", "from",
    "be", "not", "but", "as", "do", "did", "about", "news", "latest",
    "after", "over", "into", "than", "then", "when", "who", "what",
    "how", "all", "has", "have", "had", "will", "would", "could", "should",
}

# Minimum relevance score to accept an article (0.0 -- 1.0).
# 0.3 means at least ~30% keyword coverage; exact phrase match in title always passes.
_MIN_SCORE = 0.3


def _parse_query(query: str) -> tuple[list[str], list[str]]:
    """
    Return (keywords, phrases).
    keywords -- individual significant words from the query
    phrases  -- multi-word sequences to check as exact substrings
    """
    tokens = [w.lower() for w in _WORD_RE.findall(query)]
    keywords = [t for t in tokens if len(t) >= 2 and t not in _STOP_WORDS]

    # Build the full normalised phrase for exact-match shortcut
    full_phrase = " ".join(keywords)
    phrases = [full_phrase] if len(keywords) >= 2 else []

    return keywords, phrases


def _relevance_score(title: str, snippet: str,
                     keywords: list[str], phrases: list[str]) -> float:
    """
    Score how relevant an article is to the query (0.0 -- 1.0).

    Scoring rules:
      - Exact phrase match in title  -> 1.0  (always include)
      - Exact phrase match in body   -> 0.75 (strong match)
      - Per keyword: title hit = 2 pts, body hit = 1 pt
      - Final score = hits / max_possible_hits
    """
    if not keywords:
        return 1.0  # no query keywords -- pass everything

    title_l  = title.lower()
    body_l   = (title + " " + snippet).lower()

    # Fast path: exact multi-word phrase
    for phrase in phrases:
        if phrase in title_l:
            return 1.0
        if phrase in body_l:
            return 0.75

    # Per-keyword word-boundary scoring
    hits = 0
    for kw in keywords:
        pat = r"\b" + re.escape(kw) + r"\b"
        if re.search(pat, title_l):
            hits += 2   # title match is worth double
        elif re.search(pat, body_l):
            hits += 1

    max_hits = len(keywords) * 2  # if every keyword appeared in title
    return hits / max_hits if max_hits else 1.0


def _fetch_one_feed(portal: dict, keywords: list[str], phrases: list[str],
                    max_per_feed: int) -> list[RawResult]:
    """Fetch one RSS feed and return relevance-filtered RawResults."""
    rss_url = portal.get("rss_url", "")
    name    = portal.get("name", "Portal")

    if not rss_url:
        return []

    try:
        feed = feedparser.parse(
            rss_url,
            agent="Mozilla/5.0 (compatible; RDS/1.0; +https://github.com/rds)",
        )
        if feed.bozo and not feed.entries:
            logger.debug("[portals] {} feed error: {}", name, feed.bozo_exception)
            return []

        results: list[RawResult] = []
        for entry in feed.entries:
            if len(results) >= max_per_feed:
                break

            title   = (entry.get("title")   or "").strip()
            link    = (entry.get("link")    or "").strip()
            snippet = (entry.get("summary") or "").strip()

            if not title or not link:
                continue

            score = _relevance_score(title, snippet, keywords, phrases)
            if score < _MIN_SCORE:
                continue

            results.append(RawResult(
                url=link, title=title,
                source=name, source_type="portals",
                snippet=snippet,
                published=entry.get("published", ""),
            ))

        if results:
            logger.debug("[portals] {} -> {} relevant results", name, len(results))
        return results

    except Exception as exc:
        logger.warning("[portals] Error fetching {!r} ({}): {}", name, rss_url[:60], exc)
        return []


class PortalAggregatorSource(BaseSource):
    """
    Aggregates 20+ major news portal RSS feeds concurrently.

    Portal list lives in config/sources.yaml under sources.portals.feeds[].
    Since portal RSS feeds return their latest articles (not query results),
    articles are scored for relevance: exact phrase matches always pass;
    individual keywords are matched at word boundaries and must collectively
    exceed a minimum coverage threshold (_MIN_SCORE = 0.3).
    """

    name        = "News Portals"
    source_type = "portals"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.feeds:        list[dict] = config.get("feeds", [])
        self.max_per_feed: int        = config.get("max_per_feed", 5)
        self.max_workers:  int        = config.get("max_workers", 15)

    def search(self, query: str) -> Iterator[RawResult]:
        active_feeds = [f for f in self.feeds if f.get("enabled", True)]
        if not active_feeds:
            logger.warning("[portals] No feeds enabled in sources.yaml")
            return

        keywords, phrases = _parse_query(query)
        logger.debug(
            "[portals] query={!r}  keywords={}  phrases={}", query, keywords, phrases
        )

        seen_urls: set[str] = set()
        total = 0

        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="rss") as pool:
            futures = {
                pool.submit(_fetch_one_feed, feed, keywords, phrases, self.max_per_feed): feed
                for feed in active_feeds
            }
            for future in as_completed(futures):
                for result in future.result():
                    if total >= self.max_results:
                        return
                    if result.url in seen_urls:
                        continue
                    seen_urls.add(result.url)
                    total += 1
                    yield result
