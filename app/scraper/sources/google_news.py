from __future__ import annotations

import urllib.parse
from typing import Iterator

import feedparser

from app.models.schemas import RawResult
from app.utils.logger import get_logger
from .base import BaseSource

logger = get_logger(__name__)

_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


class GoogleNewsSource(BaseSource):
    name        = "Google News"
    source_type = "google_news"

    def search(self, query: str) -> Iterator[RawResult]:
        url  = _RSS_URL.format(query=urllib.parse.quote_plus(query))
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            logger.warning("[google_news] feedparser bozo: {}", feed.bozo_exception)
            return

        count = 0
        for entry in feed.entries:
            if count >= self.max_results:
                break

            title = (entry.get("title") or "").strip()
            link  = (entry.get("link")  or "").strip()
            if not title or not link:
                continue

            source_label = self.name
            if getattr(entry, "source", None):
                source_label = entry.source.get("title", self.name)

            yield RawResult(
                url=link, title=title,
                source=source_label, source_type=self.source_type,
                snippet=entry.get("summary", ""),
                published=entry.get("published", ""),
            )
            count += 1
