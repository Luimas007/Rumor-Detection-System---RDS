from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


@dataclass
class RawArticle:
    """Article as returned by a scraper source, before NLP processing."""
    url: str
    title: str
    source: str
    snippet: str = ""
    published: str = ""
    raw_html: str = ""
    raw_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "source": self.source,
            "snippet": self.snippet,
            "published": self.published,
        }


@dataclass
class AnalyzedArticle:
    """Fully processed article with NLP annotations."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    url: str = ""
    title: str = ""
    source: str = ""
    published: str = ""
    clean_content: str = ""
    word_count: int = 0
    language: str = "en"

    # NLP outputs
    summary: str = ""
    key_claims: list[str] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    main_theme: str = ""
    sentiment: str = Sentiment.NEUTRAL
    sentiment_score: float = 0.0
    reliability_score: float = 0.5  # 0.0-1.0, used by downstream RDS modules

    # Embedding stored separately (not serialised to JSON by default)
    embedding: Optional[list[float]] = field(default=None, repr=False)

    scraped_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self, include_embedding: bool = False) -> dict[str, Any]:
        d = {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "source": self.source,
            "published": self.published,
            "clean_content": self.clean_content,
            "word_count": self.word_count,
            "language": self.language,
            "summary": self.summary,
            "key_claims": self.key_claims,
            "themes": self.themes,
            "main_theme": self.main_theme,
            "sentiment": self.sentiment,
            "sentiment_score": round(self.sentiment_score, 4),
            "reliability_score": round(self.reliability_score, 4),
            "scraped_at": self.scraped_at,
        }
        if include_embedding and self.embedding:
            d["embedding"] = self.embedding
        return d


@dataclass
class JobStats:
    total_found: int = 0
    fetched: int = 0
    analyzed: int = 0
    duplicates_removed: int = 0
    failed: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "total_found": self.total_found,
            "fetched": self.fetched,
            "analyzed": self.analyzed,
            "duplicates_removed": self.duplicates_removed,
            "failed": self.failed,
        }


@dataclass
class SearchJob:
    query: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.PENDING
    sources: list[str] = field(default_factory=list)
    max_articles: int = 30
    articles: list[AnalyzedArticle] = field(default_factory=list)
    stats: JobStats = field(default_factory=JobStats)
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    progress_message: str = "Initialising..."

    def to_dict(self, include_articles: bool = True) -> dict[str, Any]:
        d = {
            "id": self.id,
            "query": self.query,
            "status": self.status.value,
            "sources": self.sources,
            "max_articles": self.max_articles,
            "stats": self.stats.to_dict(),
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "progress_message": self.progress_message,
        }
        if include_articles:
            d["articles"] = [a.to_dict() for a in self.articles]
        return d
