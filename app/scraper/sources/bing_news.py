from __future__ import annotations

import urllib.parse
from typing import Iterator

import feedparser

from app.models.schemas import RawArticle
from app.utils.logger import get_logger
from .base import BaseSource

logger = get_logger(__name__)

_RSS_TEMPLATE = "https://www.bing.com/news/search?q={query}&format=RSS"


class BingNewsSource(BaseSource):
    name = "bing_news"

    def search(self, query: str) -> Iterator[RawArticle]:
        url = _RSS_TEMPLATE.format(query=urllib.parse.quote_plus(query))
        logger.info("BingNews | fetching RSS for: {!r}", query)

        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            logger.warning("BingNews | feedparser bozo error: {}", feed.bozo_exception)
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

            # Provider info is in entry.provider for Bing RSS
            source_name = "Bing News"
            if "provider" in entry and entry.provider:
                source_name = entry.provider.get("name", "Bing News")

            yield RawArticle(
                url=link,
                title=title,
                source=source_name,
                snippet=summary,
                published=published,
            )
            count += 1

        logger.info("BingNews | yielded {} articles", count)
