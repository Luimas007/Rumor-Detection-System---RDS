"""Scraping pipeline: fetch article HTML → extract clean text."""
from __future__ import annotations

import time
from typing import Optional

import trafilatura
from trafilatura.settings import use_config as trafilatura_use_config

from app.models.schemas import RawArticle
from app.utils.logger import get_logger
from app.utils.text_cleaner import clean_article_text, count_words

logger = get_logger(__name__)

# Tune trafilatura: faster, no comments/tables, favour main content
_TRAF_CFG = trafilatura_use_config()
_TRAF_CFG.set("DEFAULT", "EXTRACTION_TIMEOUT", "10")


def _fetch_html_scrapling(url: str, timeout: int = 20) -> Optional[str]:
    """Attempt to fetch raw HTML using Scrapling's stealthy HTTP fetcher."""
    try:
        from scrapling.fetchers import Fetcher

        page = Fetcher.get(url, stealthy_headers=True, timeout=timeout)

        # Scrapling Adaptor: try known attributes for raw HTML
        for attr in ("html", "html_content", "body", "content"):
            val = getattr(page, attr, None)
            if val:
                html = str(val)
                if len(html) > 200:
                    return html

        # Fallback: serialise the root element
        try:
            html = page.get()
            if html and len(html) > 200:
                return html
        except Exception:
            pass

    except Exception as exc:
        logger.debug("Scrapling fetch failed for {}: {}", url, exc)

    return None


def _fetch_html_trafilatura(url: str) -> Optional[str]:
    """Fallback fetcher using trafilatura's built-in HTTP client."""
    try:
        downloaded = trafilatura.fetch_url(url)
        return downloaded
    except Exception as exc:
        logger.debug("trafilatura fetch failed for {}: {}", url, exc)
        return None


def fetch_article_content(article: RawArticle, timeout: int = 20,
                          min_length: int = 200) -> Optional[str]:
    """
    Fetch and extract clean article text.

    Strategy:
    1. Try Scrapling (stealth headers, better fingerprinting)
    2. Fall back to trafilatura's own downloader
    3. Fall back to the RSS snippet if it's long enough
    """
    url = article.url
    logger.debug("Fetching content: {}", url)

    html = _fetch_html_scrapling(url, timeout) or _fetch_html_trafilatura(url)

    if html:
        content = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
            config=_TRAF_CFG,
        )
        if content and len(content) >= min_length:
            return content

    # RSS snippet as last resort
    snippet = article.snippet
    if snippet and len(snippet) >= min_length:
        logger.debug("Using RSS snippet for: {}", url)
        return snippet

    logger.warning("Could not extract content for: {}", url)
    return None


def build_analyzed_base(raw: RawArticle, content: str,
                         min_word_count: int = 40) -> Optional[dict]:
    """
    Clean content and return a base dict ready for NLP processing.
    Returns None if content doesn't pass quality checks.
    """
    cleaned = clean_article_text(content)
    if not cleaned:
        return None

    wc = count_words(cleaned)
    if wc < min_word_count:
        logger.debug("Article too short ({} words), skipping: {}", wc, raw.url)
        return None

    return {
        "url": raw.url,
        "title": raw.title,
        "source": raw.source,
        "published": raw.published,
        "clean_content": cleaned,
        "word_count": wc,
    }


def scrape_article(raw: RawArticle, timeout: int = 20,
                   retry: int = 1, delay: float = 1.5) -> Optional[dict]:
    """Full fetch → extract → clean pipeline for a single article."""
    for attempt in range(retry + 1):
        content = fetch_article_content(raw, timeout=timeout)
        if content:
            return build_analyzed_base(raw, content)
        if attempt < retry:
            logger.debug("Retry {}/{} for: {}", attempt + 1, retry, raw.url)
            time.sleep(delay)

    return None
