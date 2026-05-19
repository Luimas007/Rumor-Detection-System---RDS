"""
Scraper job engine.

3-phase pipeline (all phases logged separately for easy debugging):

  Phase 1 — SOURCE SEARCH   : all sources run concurrently → list[RawResult]
  Phase 2 — CONTENT FETCH   : all URLs fetched concurrently → list[Article]
  Phase 3 — PREPROCESS      : clean, language-filter, content-dedup → final list

Job state is held in a plain dict (_job_store) guarded by a threading.Lock.
Swap for Redis/DB without changing the public API (create_job / get_job / list_jobs).
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

import yaml

from app.models.schemas import Article, FetchMode, JobStatus, RawResult, ScraperStats, SearchJob
from app.preprocessor.cleaner import (
    clean_text, detect_language, is_quality_content, normalise_date, word_count,
)
from app.preprocessor.deduplicator import dedup_by_content, dedup_by_url
from app.scraper.extractor import extract_content
from app.scraper.fetcher import fetch_html
from app.scraper.sources import SOURCE_REGISTRY
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── in-memory job store ────────────────────────────────────────────────────────
_job_store: dict[str, SearchJob] = {}
_store_lock = threading.Lock()


# ── config helpers ─────────────────────────────────────────────────────────────

def _cfg() -> dict:
    try:
        with open("config/config.yaml", encoding="utf-8") as fh:
            return yaml.safe_load(fh).get("scraper", {})
    except Exception:
        return {}


def _source_cfg(source_type: str) -> dict:
    try:
        with open("config/sources.yaml", encoding="utf-8") as fh:
            return yaml.safe_load(fh).get("sources", {}).get(source_type, {})
    except Exception:
        return {}


# ── Phase helpers ──────────────────────────────────────────────────────────────

def _phase1_collect(query: str, source_types: list[str]) -> tuple[list[RawResult], dict[str, int]]:
    """Run all sources concurrently and return deduplicated RawResults + per-source counts."""
    sources = []
    for st in source_types:
        cls = SOURCE_REGISTRY.get(st)
        if cls is None:
            logger.warning("Unknown source type: {}", st)
            continue
        sources.append(cls(_source_cfg(st)))

    raw_all: list[RawResult] = []
    source_counts: dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=len(sources) or 1, thread_name_prefix="src") as pool:
        futures = {pool.submit(src.safe_search, query): src for src in sources}
        for future in as_completed(futures):
            src     = futures[future]
            results = future.result()  # safe_search never raises
            source_counts[src.source_type] = len(results)
            raw_all.extend(results)

    # URL dedup before we do any HTTP fetching
    unique = dedup_by_url(raw_all, url_attr="url")
    logger.info("Phase 1 done — {} raw URLs → {} unique", len(raw_all), len(unique))
    return unique, source_counts


def _build_article(raw: RawResult, html: Optional[str],
                   fetch_method: Optional[str], min_words: int) -> Article:
    """Convert a RawResult + fetched HTML into a fully preprocessed Article."""
    article = Article(
        url=raw.url, title=raw.title,
        source=raw.source, source_type=raw.source_type,
        published=normalise_date(raw.published),
        author=raw.author,
        snippet=raw.snippet,
    )

    if not html:
        # No HTML — use snippet if long enough
        snippet_clean = clean_text(raw.snippet) or ""
        if snippet_clean and word_count(snippet_clean) >= 15:
            article.content    = snippet_clean
            article.word_count = word_count(snippet_clean)
            article.fetch_mode = FetchMode.SNIPPET_ONLY
        else:
            article.fetch_mode = FetchMode.FAILED
        return article

    # Extract main content
    extracted = extract_content(html, url=raw.url)

    # Prefer extracted title over RSS title when it's longer/cleaner
    if extracted["title"] and len(extracted["title"]) > len(raw.title):
        article.title = extracted["title"]
    if extracted["author"] and not article.author:
        article.author = extracted["author"]
    if extracted["date"] and not article.published:
        article.published = normalise_date(extracted["date"])

    content_raw = extracted["content"]
    if not content_raw:
        # Extraction got nothing — fall back to snippet
        snippet_clean = clean_text(raw.snippet) or ""
        article.content    = snippet_clean
        article.word_count = word_count(snippet_clean)
        article.fetch_mode = FetchMode.SNIPPET_ONLY if snippet_clean else FetchMode.FAILED
        return article

    cleaned = clean_text(content_raw)
    if not cleaned or not is_quality_content(cleaned, min_words=min_words):
        # Content didn't pass quality gate — try snippet fallback
        fallback = clean_text(raw.snippet) or ""
        article.content    = fallback
        article.word_count = word_count(fallback)
        article.fetch_mode = FetchMode.SNIPPET_ONLY if fallback else FetchMode.FAILED
        return article

    article.content    = cleaned
    article.word_count = word_count(cleaned)
    article.language   = detect_language(cleaned[:500])
    article.fetch_mode = FetchMode.FULL
    return article


def _fetch_one(raw: RawResult, timeout: int, min_words: int) -> Article:
    """Fetch + extract + clean a single article. Never raises."""
    try:
        html, method = fetch_html(raw.url, timeout=timeout)
        article = _build_article(raw, html, method, min_words)
        logger.debug("[{}] {} → {} words ({})", raw.source_type,
                     raw.url[:60], article.word_count, article.fetch_mode)
        return article
    except Exception as exc:
        logger.error("Unhandled error fetching {}: {}", raw.url, exc)
        return Article(
            url=raw.url, title=raw.title,
            source=raw.source, source_type=raw.source_type,
            published=normalise_date(raw.published),
            snippet=raw.snippet,
            fetch_mode=FetchMode.FAILED,
        )


def _phase2_fetch(raw_results: list[RawResult], stats: ScraperStats,
                  timeout: int, workers: int, min_words: int,
                  update_fn) -> list[Article]:
    """Fetch all articles concurrently and update stats in real time."""
    articles: list[Article] = []
    done = 0

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="fetch") as pool:
        futures = {pool.submit(_fetch_one, raw, timeout, min_words): raw for raw in raw_results}

        for future in as_completed(futures):
            article = future.result()
            articles.append(article)
            done += 1

            # Update live stats
            if article.fetch_mode == FetchMode.FULL:
                stats.fetched_full += 1
            elif article.fetch_mode == FetchMode.SNIPPET_ONLY:
                stats.fetched_snippet += 1
            else:
                stats.fetch_failed += 1

            if done % 5 == 0 or done == len(raw_results):
                update_fn(
                    f"Phase 2/3 — Fetching articles… {done}/{len(raw_results)} "
                    f"({stats.fetched_full} full, {stats.fetched_snippet} snippet, {stats.fetch_failed} failed)"
                )

    logger.info("Phase 2 done — {} full, {} snippet, {} failed",
                stats.fetched_full, stats.fetched_snippet, stats.fetch_failed)
    return articles


def _phase3_preprocess(articles: list[Article], stats: ScraperStats,
                       lang_filter: Optional[str]) -> list[Article]:
    """
    Language filter → content dedup → sort by date.
    Returns final clean list.
    """
    # Optional language filter (default: English only)
    before = len(articles)
    if lang_filter:
        articles = [a for a in articles if a.language in (lang_filter, "unknown", "")]
        dropped  = before - len(articles)
        if dropped:
            logger.info("Phase 3 — language filter dropped {} articles", dropped)

    # Content-level dedup (removes near-identical articles from different sources)
    articles, removed = dedup_by_content(articles, content_attr="content")
    stats.duplicates_removed = removed

    # Sort: newest first; articles without a date go to the end
    articles.sort(key=lambda a: a.published or "", reverse=True)

    stats.final_count = len(articles)
    logger.info("Phase 3 done — {} articles after dedup", len(articles))
    return articles


# ── Main job runner ────────────────────────────────────────────────────────────

def _run_job(job_id: str) -> None:
    with _store_lock:
        job = _job_store.get(job_id)
    if job is None:
        return

    cfg        = _cfg()
    timeout    = cfg.get("request_timeout", 12)
    workers    = cfg.get("concurrent_requests", 20)
    min_words  = cfg.get("min_content_words", 50)
    lang       = cfg.get("language_filter", "en")  # set to "" to disable

    def _update(msg: str, status: Optional[JobStatus] = None) -> None:
        with _store_lock:
            job.progress_message = msg
            if status:
                job.status = status
        logger.info("[job={}] {}", job_id[:8], msg)

    t0 = time.time()
    try:
        _update("Phase 1/3 — Searching sources…", JobStatus.RUNNING)

        # ── Phase 1 ────────────────────────────────────────────────────────────
        raw_results, source_counts = _phase1_collect(job.query, job.sources)
        job.stats.source_counts = source_counts
        job.stats.total_urls    = sum(source_counts.values())
        job.stats.unique_urls   = len(raw_results)

        if not raw_results:
            with _store_lock:
                job.status           = JobStatus.COMPLETED
                job.completed_at     = datetime.utcnow().isoformat()
                job.progress_message = "No results found for this query."
                job.stats.elapsed_seconds = round(time.time() - t0, 2)
            return

        # Cap at 2× max so Phase 3 dedup has room to trim
        budget = min(len(raw_results), job.max_articles * 2)
        raw_results = raw_results[:budget]
        _update(f"Phase 2/3 — Fetching {len(raw_results)} articles…")

        # ── Phase 2 ────────────────────────────────────────────────────────────
        articles = _phase2_fetch(
            raw_results, job.stats, timeout, workers, min_words, _update,
        )

        _update("Phase 3/3 — Cleaning and deduplicating…")

        # ── Phase 3 ────────────────────────────────────────────────────────────
        articles = _phase3_preprocess(articles, job.stats, lang)

        # Trim to user's requested limit
        articles = articles[: job.max_articles]
        job.stats.elapsed_seconds = round(time.time() - t0, 2)

        with _store_lock:
            job.articles         = articles
            job.status           = JobStatus.COMPLETED
            job.completed_at     = datetime.utcnow().isoformat()
            job.progress_message = (
                f"Done — {len(articles)} articles in {job.stats.elapsed_seconds}s "
                f"({job.stats.fetched_full} full, {job.stats.fetched_snippet} snippet)"
            )

        logger.info(
            "[job={}] Completed in {:.1f}s — {} articles ({} full, {} snippet, {} failed, {} deduped)",
            job_id[:8], job.stats.elapsed_seconds, len(articles),
            job.stats.fetched_full, job.stats.fetched_snippet,
            job.stats.fetch_failed, job.stats.duplicates_removed,
        )

    except Exception as exc:
        logger.exception("[job={}] Unhandled error: {}", job_id[:8], exc)
        with _store_lock:
            job.status           = JobStatus.FAILED
            job.error            = str(exc)
            job.completed_at     = datetime.utcnow().isoformat()
            job.progress_message = "Job failed — see logs for details."
            job.stats.elapsed_seconds = round(time.time() - t0, 2)


# ── Public API ─────────────────────────────────────────────────────────────────

def create_job(query: str, sources: Optional[list[str]] = None,
               max_articles: int = 30) -> SearchJob:
    all_sources = list(SOURCE_REGISTRY.keys())
    job = SearchJob(
        query=query,
        sources=sources or all_sources,
        max_articles=max_articles,
    )
    with _store_lock:
        _job_store[job.id] = job

    t = threading.Thread(target=_run_job, args=(job.id,), daemon=True, name=f"job-{job.id[:8]}")
    t.start()
    logger.info("Job {} started — query={!r}, sources={}", job.id[:8], query, job.sources)
    return job


def get_job(job_id: str) -> Optional[SearchJob]:
    with _store_lock:
        return _job_store.get(job_id)


def list_jobs(limit: int = 20) -> list[SearchJob]:
    with _store_lock:
        jobs = sorted(_job_store.values(), key=lambda j: j.created_at, reverse=True)
    return jobs[:limit]
