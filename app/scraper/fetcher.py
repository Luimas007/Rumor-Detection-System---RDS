"""
HTTP fetching layer.

Strategy (fastest to most capable):
  1. httpx — fast connection-pooled requests with realistic browser headers
  2. Scrapling Fetcher — stealth TLS fingerprinting for sites that block httpx
  3. trafilatura.fetch_url — own downloader as final fallback

Returns raw HTML string + the method that succeeded, so callers can log it.
"""
from __future__ import annotations

import warnings
from typing import Optional

import httpx

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Suppress noisy SSL warnings on sites with self-signed certs
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT":             "1",
    "Connection":      "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# HTTP status codes that mean we should try Scrapling instead of httpx
_BLOCKED_CODES = {403, 406, 429, 503, 520, 521, 522, 523, 524}


def fetch_html(url: str, timeout: int = 12) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch raw HTML for *url*.

    Returns
    -------
    (html: str | None, method: str | None)
        method is 'httpx' | 'scrapling' | 'trafilatura' | None on total failure.
    """
    # ── Method 1: httpx ───────────────────────────────────────────────────────
    html, method = _httpx_fetch(url, timeout)
    if html:
        return html, method

    # ── Method 2: Scrapling Fetcher ───────────────────────────────────────────
    html = _scrapling_fetch(url, timeout + 5)
    if html:
        return html, "scrapling"

    # ── Method 3: trafilatura built-in downloader ─────────────────────────────
    html = _trafilatura_fetch(url)
    if html:
        return html, "trafilatura"

    logger.warning("All fetch methods failed for: {}", url)
    return None, None


def _httpx_fetch(url: str, timeout: int) -> tuple[Optional[str], Optional[str]]:
    """Try httpx; return (None, None) on any failure."""
    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=float(timeout), write=5.0, pool=2.0),
            headers=_BROWSER_HEADERS,
            follow_redirects=True,
            verify=True,
        ) as client:
            r = client.get(url)

        if r.status_code == 200:
            return r.text, "httpx"

        if r.status_code in _BLOCKED_CODES:
            logger.debug("httpx blocked ({}) for {} — trying Scrapling", r.status_code, url)
            return None, None

        logger.debug("httpx got {} for {}", r.status_code, url)
        return None, None

    except httpx.SSLError:
        # Retry once without SSL verification
        try:
            with httpx.Client(
                timeout=httpx.Timeout(connect=5.0, read=float(timeout), write=5.0, pool=2.0),
                headers=_BROWSER_HEADERS,
                follow_redirects=True,
                verify=False,
            ) as client:
                r = client.get(url)
            if r.status_code == 200:
                return r.text, "httpx"
        except Exception as e:
            logger.debug("httpx SSL retry failed for {}: {}", url, e)

    except httpx.TimeoutException:
        logger.debug("httpx timeout for {}", url)
    except Exception as e:
        logger.debug("httpx error for {}: {}", url, e)

    return None, None


def _scrapling_fetch(url: str, timeout: int) -> Optional[str]:
    """Scrapling Fetcher — stealth HTTP with TLS fingerprint spoofing."""
    try:
        from scrapling.fetchers import Fetcher

        page = Fetcher.get(url, stealthy_headers=True, timeout=timeout)

        # Scrapling returns an Adaptor wrapping the parsed HTML.
        # Try the most common attribute names for the raw HTML string.
        for attr in ("html", "html_content", "body", "content"):
            val = getattr(page, attr, None)
            if val:
                s = str(val)
                if len(s) > 200:
                    return s

        # Last resort: serialise root element via .get()
        try:
            s = page.get()
            if s and len(s) > 200:
                return s
        except Exception:
            pass

    except Exception as e:
        logger.debug("Scrapling error for {}: {}", url, e)

    return None


def _trafilatura_fetch(url: str) -> Optional[str]:
    try:
        import trafilatura
        return trafilatura.fetch_url(url)
    except Exception as e:
        logger.debug("trafilatura fetch error for {}: {}", url, e)
        return None
