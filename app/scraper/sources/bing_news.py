from __future__ import annotations

import urllib.parse
from typing import Iterator

import feedparser

from app.models.schemas import RawResult
from app.utils.logger import get_logger
from .base import BaseSource

logger = get_logger(__name__)

_RSS_URL = "https://www.bing.com/news/search?q={query}&format=RSS"


class BingNewsSource(BaseSource):
    name        = "Bing News"
    source_type = "bing_news"

    def search(self, query: str) -> Iterator[RawResult]:
        url  = _RSS_URL.format(query=urllib.parse.quote_plus(query))
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            logger.warning("[bing_news] feedparser bozo: {}", feed.bozo_exception)
            return

        count = 0
        for entry in feed.entries:
            if count >= self.max_results:
                break

            title = (entry.get("title") or "").strip()
            link  = (entry.get("link")  or "").strip()
            if not title or not link:
                continue

            # Bing RSS puts the publisher in entry.provider
            source_label = self.name
            provider = getattr(entry, "provider", None)
            if provider:
                source_label = provider.get("name", self.name)

            yield RawResult(
                url=link, title=title,
                source=source_label, source_type=self.source_type,
                snippet=entry.get("summary", ""),
                published=entry.get("published", ""),
            )
            count += 1
