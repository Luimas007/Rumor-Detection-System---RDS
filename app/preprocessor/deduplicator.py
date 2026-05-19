"""
Two-stage deduplication — no ML required.

Stage 1 — URL level   : exact URL match (runs before fetching, saves HTTP calls)
Stage 2 — Content level: SHA-256 of first 300 normalised words (runs after fetch)
"""
from __future__ import annotations

import hashlib
import re
from typing import TypeVar

from app.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


# ── URL deduplication ──────────────────────────────────────────────────────────

def _normalise_url(url: str) -> str:
    """Strip trailing slash, fragment, and common tracking params."""
    url = url.split("#")[0].rstrip("/")
    url = re.sub(r"[?&](utm_[^&]+|ref=[^&]+|source=[^&]+|fbclid=[^&]+)", "", url)
    url = re.sub(r"[?&]$", "", url)
    return url.lower()


def dedup_by_url(results: list, url_attr: str = "url") -> list:
    """
    Remove duplicates from a list of objects (or dicts) by their URL.
    Preserves first occurrence, drops subsequent ones.
    """
    seen:   set[str] = set()
    unique: list     = []

    for item in results:
        raw_url = getattr(item, url_attr, None) or (item.get(url_attr) if isinstance(item, dict) else None)
        if not raw_url:
            continue
        norm = _normalise_url(raw_url)
        if norm not in seen:
            seen.add(norm)
            unique.append(item)

    removed = len(results) - len(unique)
    if removed:
        logger.debug("URL dedup: removed {} duplicates ({} → {})", removed, len(results), len(unique))
    return unique


# ── Content deduplication ──────────────────────────────────────────────────────

def _content_fingerprint(text: str) -> str:
    """SHA-256 of the first 300 normalised words."""
    words  = re.findall(r"\b\w+\b", text.lower())
    sample = " ".join(words[:300])
    return hashlib.sha256(sample.encode()).hexdigest()


def dedup_by_content(articles: list, content_attr: str = "content") -> tuple[list, int]:
    """
    Remove articles whose first 300 words produce the same hash.
    Returns (unique_articles, num_removed).
    """
    seen:   set[str] = set()
    unique: list     = []

    for article in articles:
        text = getattr(article, content_attr, "") or ""
        if not text:
            # Articles with no content (snippet-only) are kept; they can't be content-duped
            unique.append(article)
            continue

        fp = _content_fingerprint(text)
        if fp not in seen:
            seen.add(fp)
            unique.append(article)

    removed = len(articles) - len(unique)
    if removed:
        logger.debug("Content dedup: removed {} near-duplicate articles", removed)
    return unique, removed
