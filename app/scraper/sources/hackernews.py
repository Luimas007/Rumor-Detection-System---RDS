"""Hacker News source via Algolia search API — returns stories with external URLs."""
from __future__ import annotations

import urllib.parse
from typing import Iterator

import httpx

from app.models.schemas import RawResult
from app.utils.logger import get_logger
from .base import BaseSource

logger = get_logger(__name__)

_ALGOLIA_URL = (
    "https://hn.algolia.com/api/v1/search"
    "?query={query}&tags=story&hitsPerPage={limit}&attributesToHighlight=none"
)


class HackerNewsSource(BaseSource):
    name        = "Hacker News"
    source_type = "hackernews"

    def search(self, query: str) -> Iterator[RawResult]:
        url = _ALGOLIA_URL.format(
            query=urllib.parse.quote_plus(query),
            limit=min(self.max_results * 2, 30),
        )

        with httpx.Client(timeout=10, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            hits = r.json().get("hits", [])

        count = 0
        for hit in hits:
            if count >= self.max_results:
                break

            title   = (hit.get("title") or "").strip()
            ext_url = (hit.get("url")   or "").strip()

            # Skip self-posts (no external URL to scrape)
            if not ext_url:
                hn_id = hit.get("objectID")
                if hn_id:
                    # Use the HN discussion page as the article source
                    ext_url = f"https://news.ycombinator.com/item?id={hn_id}"
                else:
                    continue

            if not title:
                continue

            yield RawResult(
                url=ext_url, title=title,
                source=self.name, source_type=self.source_type,
                snippet="",
                published=hit.get("created_at", ""),
                author=hit.get("author", ""),
            )
            count += 1
