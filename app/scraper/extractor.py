"""
Content extraction layer — wraps trafilatura.

Extracts the main article body, title, author, and date from raw HTML.
Falls back to the RSS snippet when extraction yields nothing usable.
"""
from __future__ import annotations

from typing import Optional

import trafilatura
from trafilatura.settings import use_config as _use_config

from app.utils.logger import get_logger

logger = get_logger(__name__)

# Tune trafilatura: no comments, no tables, favour article body
_TRAF_CFG = _use_config()
_TRAF_CFG.set("DEFAULT", "EXTRACTION_TIMEOUT", "8")
_TRAF_CFG.set("DEFAULT", "MIN_EXTRACTED_SIZE",  "200")
_TRAF_CFG.set("DEFAULT", "MIN_OUTPUT_SIZE",      "200")

_TRAF_EXTRACT_KWARGS = dict(
    include_comments=False,
    include_tables=False,
    no_fallback=False,
    favor_precision=False,
    favor_recall=True,          # get more text rather than less
    config=_TRAF_CFG,
)


def extract_content(html: str, url: str = "") -> dict:
    """
    Extract structured content from raw HTML.

    Returns a dict with keys:
        content (str)   — main article body (may be empty)
        title   (str)
        author  (str)
        date    (str)   — raw date string from trafilatura
    """
    result = {"content": "", "title": "", "author": "", "date": ""}

    if not html:
        return result

    try:
        # Full structured extraction
        traf = trafilatura.extract(
            html,
            url=url or None,
            output_format="python",     # returns dict
            with_metadata=True,
            **_TRAF_EXTRACT_KWARGS,
        )

        if isinstance(traf, dict):
            result["content"] = traf.get("text") or ""
            result["title"]   = traf.get("title") or ""
            result["author"]  = traf.get("author") or ""
            result["date"]    = traf.get("date") or ""
            return result

        # Fallback: plain text extraction
        text = trafilatura.extract(html, **_TRAF_EXTRACT_KWARGS)
        if text:
            result["content"] = text

    except Exception as e:
        logger.debug("trafilatura extraction error for {}: {}", url, e)

    return result
