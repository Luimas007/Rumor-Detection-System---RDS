"""Job engine: manages search jobs, scraping, and NLP orchestration."""
from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

import yaml

from app.models.schemas import (
    AnalyzedArticle, JobStatus, RawArticle, SearchJob,
)
from app.scraper.pipeline import scrape_article
from app.scraper.sources import BingNewsSource, GoogleNewsSource, RedditSource
from app.utils.logger import get_logger

logger = get_logger(__name__)

# In-memory job store; swap for Redis in production
_job_store: dict[str, SearchJob] = {}
_store_lock = threading.Lock()


def _load_source_config(source_name: str) -> dict:
    try:
        with open("config/sources.yaml", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data.get("sources", {}).get(source_name, {})
    except Exception:
        return {}


def _load_scraper_config() -> dict:
    try:
        with open("config/config.yaml", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data.get("scraper", {})
    except Exception:
        return {}


# Source registry — add new sources here
_SOURCE_CLASSES = {
    "google_news": GoogleNewsSource,
    "bing_news": BingNewsSource,
    "reddit": RedditSource,
}


def _build_sources(requested: list[str]) -> list:
    sources = []
    for name in requested:
        cls = _SOURCE_CLASSES.get(name)
        if cls is None:
            logger.warning("Unknown source: {}", name)
            continue
        cfg = _load_source_config(name)
        if cfg.get("enabled", True):
            sources.append(cls(cfg))
    return sources


def _deduplicate(articles: list[AnalyzedArticle],
                 threshold: float = 0.88) -> tuple[list[AnalyzedArticle], int]:
    """Remove near-duplicate articles using cosine similarity of embeddings."""
    if not articles:
        return articles, 0

    import numpy as np
    from sklearn.metrics.pairwise import cosine_similarity

    # Articles without embeddings skip deduplication
    with_emb = [a for a in articles if a.embedding]
    without_emb = [a for a in articles if not a.embedding]

    if not with_emb:
        # Fallback: deduplicate by URL
        seen_urls: set[str] = set()
        unique = []
        for a in articles:
            if a.url not in seen_urls:
                unique.append(a)
                seen_urls.add(a.url)
        removed = len(articles) - len(unique)
        return unique, removed

    matrix = np.array([a.embedding for a in with_emb])
    sim = cosine_similarity(matrix)
    keep = set(range(len(with_emb)))

    for i in range(len(with_emb)):
        if i not in keep:
            continue
        for j in range(i + 1, len(with_emb)):
            if j in keep and sim[i][j] >= threshold:
                keep.discard(j)

    unique = [with_emb[i] for i in sorted(keep)] + without_emb
    removed = len(with_emb) - len(keep)
    logger.info("Deduplication removed {} duplicate articles", removed)
    return unique, removed


def _run_job(job_id: str) -> None:
    """Execute a search job end-to-end in a background thread."""
    with _store_lock:
        job = _job_store.get(job_id)
    if job is None:
        return

    cfg = _load_scraper_config()
    timeout = cfg.get("request_timeout", 25)
    retry = cfg.get("retry_attempts", 2)
    delay = cfg.get("retry_delay", 1.5)
    workers = cfg.get("concurrent_requests", 5)
    dedup_threshold = cfg.get("dedup_similarity_threshold", 0.88)

    def _update(msg: str, status: Optional[JobStatus] = None) -> None:
        with _store_lock:
            job.progress_message = msg
            if status:
                job.status = status
        logger.info("[job={}] {}", job_id[:8], msg)

    try:
        _update("Collecting articles from sources...", JobStatus.RUNNING)

        # --- Phase 1: Collect raw articles from all sources ---
        sources = _build_sources(job.sources)
        raw_articles: list[RawArticle] = []
        seen_urls: set[str] = set()

        for source in sources:
            for raw in source._safe_search(job.query):
                if raw.url not in seen_urls:
                    raw_articles.append(raw)
                    seen_urls.add(raw.url)
                if len(raw_articles) >= job.max_articles * 2:
                    break

        job.stats.total_found = len(raw_articles)
        _update(f"Found {len(raw_articles)} articles. Fetching content...")

        # --- Phase 2: Scrape article content concurrently ---
        scraped_bases: list[dict] = []
        failed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(scrape_article, raw, timeout, retry, delay): raw
                for raw in raw_articles[:job.max_articles * 2]
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    scraped_bases.append(result)
                    job.stats.fetched = len(scraped_bases)
                else:
                    failed += 1

        job.stats.failed = failed
        _update(f"Scraped {len(scraped_bases)} articles. Running NLP analysis...")

        # --- Phase 3: NLP analysis ---
        from app.nlp.processor import NLPProcessor
        nlp = NLPProcessor()

        analyzed: list[AnalyzedArticle] = []
        for i, base in enumerate(scraped_bases[: job.max_articles]):
            try:
                article = nlp.process(base)
                analyzed.append(article)
                job.stats.analyzed = len(analyzed)
                if (i + 1) % 5 == 0:
                    _update(f"Analysed {i + 1}/{min(len(scraped_bases), job.max_articles)} articles...")
            except Exception as exc:
                logger.error("NLP failed for {}: {}", base.get("url"), exc)

        # --- Phase 4: Deduplicate ---
        _update("Removing duplicates...")
        unique, removed = _deduplicate(analyzed, threshold=dedup_threshold)
        job.stats.duplicates_removed = removed

        # Sort: most recent first (articles with no date go last)
        unique.sort(key=lambda a: a.published or "", reverse=True)

        with _store_lock:
            job.articles = unique
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow().isoformat()
            job.progress_message = (
                f"Done — {len(unique)} unique articles analysed."
            )

        logger.info(
            "[job={}] Completed: {} articles, {} duplicates removed",
            job_id[:8], len(unique), removed,
        )

    except Exception as exc:
        logger.exception("[job={}] Unhandled error: {}", job_id[:8], exc)
        with _store_lock:
            job.status = JobStatus.FAILED
            job.error = str(exc)
            job.progress_message = "Job failed."
            job.completed_at = datetime.utcnow().isoformat()


# ─── Public API ───────────────────────────────────────────────────────────────

def create_job(query: str, sources: Optional[list[str]] = None,
               max_articles: int = 30) -> SearchJob:
    default_sources = list(_SOURCE_CLASSES.keys())
    job = SearchJob(
        query=query,
        sources=sources or default_sources,
        max_articles=max_articles,
    )
    with _store_lock:
        _job_store[job.id] = job

    thread = threading.Thread(target=_run_job, args=(job.id,), daemon=True)
    thread.start()
    logger.info("Job {} started for query: {!r}", job.id[:8], query)
    return job


def get_job(job_id: str) -> Optional[SearchJob]:
    with _store_lock:
        return _job_store.get(job_id)


def list_jobs(limit: int = 20) -> list[SearchJob]:
    with _store_lock:
        jobs = list(_job_store.values())
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs[:limit]
