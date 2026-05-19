# coding: utf-8
"""Google Web Search source -- returns top organic search results via googlesearch-python."""
from __future__ import annotations

from typing import Iterator

from app.models.schemas import RawResult
from app.utils.logger import get_logger
from .base import BaseSource

logger = get_logger(__name__)


class GoogleWebSource(BaseSource):
    """
    Fetches top Google web search results (organic SERP, not Google News).
    Uses googlesearch-python with advanced=True to get title + description.

    Note: Google rate-limits aggressive scrapers. If you get blocked,
    increase sleep_interval in config/sources.yaml (sources.google_web.sleep_interval).
    """

    name        = "Google Web"
    source_type = "google_web"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.sleep_interval: float = float(config.get("sleep_interval", 1.0))
        self.timeout:        int   = int(config.get("timeout", 10))
        self.lang:           str   = config.get("lang", "en")
        self.safe:           str   = config.get("safe", "off")

    def search(self, query: str) -> Iterator[RawResult]:
        try:
            from googlesearch import search as _gsearch
        except ImportError:
            logger.error("[google_web] googlesearch-python not installed. Run: pip install googlesearch-python")
            return

        try:
            results = _gsearch(
                query,
                num_results=self.max_results,
                lang=self.lang,
                advanced=True,           # returns SearchResult(url, title, description)
                sleep_interval=self.sleep_interval,
                timeout=self.timeout,
                safe=self.safe,
            )
        except Exception as exc:
            logger.error("[google_web] Search API error for {!r}: {}", query, exc)
            return

        count = 0
        for r in results:
            if count >= self.max_results:
                break
            url   = getattr(r, "url",         None) or ""
            title = getattr(r, "title",       None) or ""
            desc  = getattr(r, "description", None) or ""

            if not url:
                continue

            # Skip Google's own internal pages
            if "google.com/search" in url or url.startswith("https://www.google.com/"):
                continue

            yield RawResult(
                url=url, title=title,
                source=self.name, source_type=self.source_type,
                snippet=desc,
            )
            count += 1
            logger.debug("[google_web] result {}: {}", count, url[:70])
