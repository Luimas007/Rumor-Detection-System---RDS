from __future__ import annotations

import urllib.parse
from typing import Iterator

import httpx

from app.models.schemas import RawArticle
from app.utils.logger import get_logger
from .base import BaseSource

logger = get_logger(__name__)

_SEARCH_URL = (
    "https://www.reddit.com/search.json"
    "?q={query}&sort=relevance&type=link&t=month&limit={limit}"
)
_USER_AGENT = "RDS/1.0 (Rumor Detection System; research; non-commercial)"


class RedditSource(BaseSource):
    name = "reddit"

    def search(self, query: str) -> Iterator[RawArticle]:
        url = _SEARCH_URL.format(
            query=urllib.parse.quote_plus(query),
            limit=min(self.max_results * 2, 25),
        )
        logger.info("Reddit | searching for: {!r}", query)

        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                response = client.get(url, headers={"User-Agent": _USER_AGENT})
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            logger.error("Reddit | request failed: {}", exc)
            return

        posts = data.get("data", {}).get("children", [])
        count = 0

        for post in posts:
            if count >= self.max_results:
                break

            p = post.get("data", {})
            title = p.get("title", "").strip()
            url_post = p.get("url", "").strip()
            subreddit = p.get("subreddit", "reddit")
            selftext = p.get("selftext", "")
            created = p.get("created_utc", "")
            is_self = p.get("is_self", False)
            score = p.get("score", 0)

            if not title or not url_post:
                continue

            # Skip low-quality or deleted posts
            if selftext in ("[removed]", "[deleted]", ""):
                if is_self:
                    continue

            # Prefer external links over self-posts for article content
            snippet = selftext[:500] if selftext and selftext not in ("[removed]", "[deleted]") else ""

            # Convert unix timestamp
            published_str = ""
            if created:
                from datetime import datetime, timezone
                try:
                    dt = datetime.fromtimestamp(float(created), tz=timezone.utc)
                    published_str = dt.strftime("%a, %d %b %Y %H:%M:%S %z")
                except (ValueError, OSError):
                    pass

            yield RawArticle(
                url=url_post,
                title=title,
                source=f"Reddit/r/{subreddit}",
                snippet=snippet,
                published=published_str,
            )
            count += 1

        logger.info("Reddit | yielded {} posts", count)
