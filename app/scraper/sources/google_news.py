from __future__ import annotations

import urllib.parse
from typing import Iterator

import feedparser

from app.models.schemas import RawArticle
from app.utils.logger import get_logger
from .base import BaseSource

logger = get_logger(__name__)

_RSS_TEMPLATE = (
    "https://news.google.com/rss/search"
    "?q={query}&hl=en-US&gl=US&ceid=US:en"
)


class GoogleNewsSource(BaseSource):
    name = "google_news"

    def search(self, query: str) -> Iterator[RawArticle]:
        url = _RSS_TEMPLATE.format(query=urllib.parse.quote_plus(query))
        logger.info("GoogleNews | fetching RSS for: {!r}", query)

        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            logger.warning("GoogleNews | feedparser bozo error: {}", feed.bozo_exception)
            return

        count = 0
        for entry in feed.entries:
            if count >= self.max_results:
                break

            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published = entry.get("published", "")
            summary = entry.get("summary", "")

            if not title or not link:
                continue

            # Google News links are redirect URLs; the real URL is in the source
            source_name = "Google News"
            if hasattr(entry, "source") and entry.source:
                source_name = entry.source.get("title", "Google News")

            yield RawArticle(
                url=link,
                title=title,
                source=source_name,
                snippet=summary,
                published=published,
            )
            count += 1

        logger.info("GoogleNews | yielded {} articles", count)
