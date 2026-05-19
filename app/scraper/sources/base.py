"""Abstract base class for all scraper sources."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from app.models.schemas import RawResult
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseSource(ABC):
    """
    Every source must implement `search()` and set `name` + `source_type`.

    name        — human label shown in the UI  (e.g. "Hacker News")
    source_type — machine key used in config   (e.g. "hackernews")
    """

    name:        str = "base"
    source_type: str = "base"

    def __init__(self, config: dict) -> None:
        self.config     = config
        self.max_results: int  = config.get("max_results", 10)
        self.enabled:    bool  = config.get("enabled", True)

    @abstractmethod
    def search(self, query: str) -> Iterator[RawResult]:
        """Yield RawResult objects for *query*. Must be a generator."""

    def safe_search(self, query: str) -> list[RawResult]:
        """
        Public entry point — catches all exceptions so one broken source
        never stops the whole pipeline. Returns a list (not a generator)
        so callers get a complete result even if the source is slow.
        """
        if not self.enabled:
            logger.debug("[{}] disabled — skipping", self.source_type)
            return []
        try:
            results = list(self.search(query))
            logger.info("[{}] yielded {} raw results", self.source_type, len(results))
            return results
        except Exception as exc:
            logger.error("[{}] search failed for {!r}: {}", self.source_type, query, exc)
            return []
