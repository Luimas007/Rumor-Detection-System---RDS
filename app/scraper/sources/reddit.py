from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Iterator

import httpx

from app.models.schemas import RawResult
from app.utils.logger import get_logger
from .base import BaseSource

logger = get_logger(__name__)

_SEARCH_URL = (
    "https://www.reddit.com/search.json"
    "?q={query}&sort=relevance&type=link&t=month&limit={limit}"
)
_HEADERS = {"User-Agent": "RDS/2.0 (web scraper; non-commercial research)"}


def _unix_to_iso(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


class RedditSource(BaseSource):
    name        = "Reddit"
    source_type = "reddit"

    def search(self, query: str) -> Iterator[RawResult]:
        url = _SEARCH_URL.format(
            query=urllib.parse.quote_plus(query),
            limit=min(self.max_results * 2, 25),
        )

        with httpx.Client(timeout=12, headers=_HEADERS, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            posts = r.json().get("data", {}).get("children", [])

        count = 0
        for post in posts:
            if count >= self.max_results:
                break

            p     = post.get("data", {})
            title = (p.get("title") or "").strip()
            link  = (p.get("url")   or "").strip()
            if not title or not link:
                continue

            # Skip deleted self-posts — no content to scrape
            selftext = p.get("selftext", "")
            if p.get("is_self") and selftext in ("", "[removed]", "[deleted]"):
                continue

            subreddit = p.get("subreddit", "reddit")
            snippet   = selftext[:400] if selftext not in ("", "[removed]", "[deleted]") else ""
            published = _unix_to_iso(p.get("created_utc", 0))

            yield RawResult(
                url=link, title=title,
                source=f"Reddit / r/{subreddit}", source_type=self.source_type,
                snippet=snippet, published=published,
                author=p.get("author", ""),
            )
            count += 1
