from .base import BaseSource
from .google_news import GoogleNewsSource
from .bing_news import BingNewsSource
from .reddit import RedditSource
from .hackernews import HackerNewsSource
from .duckduckgo import DuckDuckGoSource

# Registry: source_type key → class
# Add new sources here only — no other file needs to change.
SOURCE_REGISTRY: dict[str, type[BaseSource]] = {
    "google_news": GoogleNewsSource,
    "bing_news":   BingNewsSource,
    "reddit":      RedditSource,
    "hackernews":  HackerNewsSource,
    "duckduckgo":  DuckDuckGoSource,
}

__all__ = [
    "BaseSource", "SOURCE_REGISTRY",
    "GoogleNewsSource", "BingNewsSource", "RedditSource",
    "HackerNewsSource", "DuckDuckGoSource",
]
