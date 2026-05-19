"""Data models for the RDS scraper — no NLP fields."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class JobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class FetchMode(str, Enum):
    FULL         = "full"          # full article body extracted
    SNIPPET_ONLY = "snippet_only"  # only RSS/API snippet available
    FAILED       = "failed"        # fetch or extraction failed


@dataclass
class RawResult:
    """URL + lightweight metadata returned by a source. No HTTP fetch yet."""
    url:         str
    title:       str
    source:      str       # human label, e.g. "Google News"
    source_type: str       # machine key, e.g. "google_news"
    snippet:     str  = ""
    published:   str  = ""
    author:      str  = ""


@dataclass
class Article:
    """Fully fetched, extracted, and cleaned article."""
    id:          str  = field(default_factory=lambda: str(uuid.uuid4()))
    url:         str  = ""
    title:       str  = ""
    source:      str  = ""
    source_type: str  = ""
    published:   str  = ""
    author:      str  = ""
    content:     str  = ""   # full cleaned article body
    snippet:     str  = ""   # short description / fallback
    word_count:  int  = 0
    language:    str  = "en"
    fetch_mode:  str  = FetchMode.FAILED
    scraped_at:  str  = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":          self.id,
            "url":         self.url,
            "title":       self.title,
            "source":      self.source,
            "source_type": self.source_type,
            "published":   self.published,
            "author":      self.author,
            "content":     self.content,
            "snippet":     self.snippet,
            "word_count":  self.word_count,
            "language":    self.language,
            "fetch_mode":  self.fetch_mode,
            "scraped_at":  self.scraped_at,
        }


@dataclass
class ScraperStats:
    """Per-job scraping statistics — useful for debugging and tuning."""
    source_counts:     dict[str, int] = field(default_factory=dict)
    total_urls:        int   = 0
    unique_urls:       int   = 0
    fetched_full:      int   = 0
    fetched_snippet:   int   = 0
    fetch_failed:      int   = 0
    duplicates_removed: int  = 0
    final_count:       int   = 0
    elapsed_seconds:   float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_counts":      self.source_counts,
            "total_urls":         self.total_urls,
            "unique_urls":        self.unique_urls,
            "fetched_full":       self.fetched_full,
            "fetched_snippet":    self.fetched_snippet,
            "fetch_failed":       self.fetch_failed,
            "duplicates_removed": self.duplicates_removed,
            "final_count":        self.final_count,
            "elapsed_seconds":    round(self.elapsed_seconds, 2),
        }


@dataclass
class SearchJob:
    query:            str
    id:               str         = field(default_factory=lambda: str(uuid.uuid4()))
    status:           JobStatus   = JobStatus.PENDING
    sources:          list[str]   = field(default_factory=list)
    max_articles:     int         = 30
    articles:         list[Article] = field(default_factory=list)
    stats:            ScraperStats  = field(default_factory=ScraperStats)
    error:            Optional[str] = None
    created_at:       str         = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at:     Optional[str] = None
    progress_message: str         = "Queued"

    def to_dict(self, include_articles: bool = True) -> dict[str, Any]:
        d = {
            "id":               self.id,
            "query":            self.query,
            "status":           self.status.value,
            "sources":          self.sources,
            "max_articles":     self.max_articles,
            "stats":            self.stats.to_dict(),
            "error":            self.error,
            "created_at":       self.created_at,
            "completed_at":     self.completed_at,
            "progress_message": self.progress_message,
        }
        if include_articles:
            d["articles"] = [a.to_dict() for a in self.articles]
        return d
