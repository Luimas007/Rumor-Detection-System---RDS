"""DuckDuckGo News source via the duckduckgo_search library."""
from __future__ import annotations

from typing import Iterator

from app.models.schemas import RawResult
from app.utils.logger import get_logger
from .base import BaseSource

logger = get_logger(__name__)


class DuckDuckGoSource(BaseSource):
    name        = "DuckDuckGo News"
    source_type = "duckduckgo"

    def search(self, query: str) -> Iterator[RawResult]:
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            logger.error("[duckduckgo] duckduckgo_search not installed. Run: pip install duckduckgo-search")
            return

        # timelimit: 'd'=day, 'w'=week, 'm'=month, 'y'=year
        timelimit = self.config.get("timelimit", "m")

        with DDGS() as ddgs:
            results = list(ddgs.news(
                query,
                max_results=self.max_results,
                timelimit=timelimit,
            ))

        for item in results:
            url   = (item.get("url")   or "").strip()
            title = (item.get("title") or "").strip()
            if not url or not title:
                continue

            yield RawResult(
                url=url, title=title,
                source=item.get("source", self.name),
                source_type=self.source_type,
                snippet=item.get("body", ""),
                published=item.get("date", ""),
            )
