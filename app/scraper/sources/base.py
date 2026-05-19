from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from app.models.schemas import RawArticle
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseSource(ABC):
    """Abstract base class for all news/content sources."""

    name: str = "base"

    def __init__(self, config: dict) -> None:
        self.config = config
        self.max_results: int = config.get("max_results", 10)
        self.enabled: bool = config.get("enabled", True)

    @abstractmethod
    def search(self, query: str) -> Iterator[RawArticle]:
        """Yield RawArticle objects for the given query.

        Must be implemented by every source. Should yield (not return) so that
        the pipeline can start processing results incrementally.
        """

    def _safe_search(self, query: str) -> Iterator[RawArticle]:
        """Wrapper that catches exceptions and logs them without crashing the pipeline."""
        if not self.enabled:
            logger.debug("Source '{}' is disabled — skipping", self.name)
            return
        try:
            yield from self.search(query)
        except Exception as exc:
            logger.error("Source '{}' raised an error for query '{}': {}", self.name, query, exc)
