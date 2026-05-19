"""
Text cleaning and quality assessment — pure Python, zero ML.

Responsibilities:
  - Normalise whitespace and Unicode
  - Strip residual HTML and web noise
  - Detect language (langdetect, lightweight)
  - Assess content quality (word count, repetition)
  - Normalise date strings to ISO-8601
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)

# ── compiled patterns ──────────────────────────────────────────────────────────
_HTML_TAG      = re.compile(r"<[^>]+>")
_WHITESPACE    = re.compile(r"\s+")
_URL_PATTERN   = re.compile(r"https?://\S+|www\.\S+")
_REPEAT_PUNCT  = re.compile(r"([.!?,;:]){2,}")
_ENCODING_MAP  = {
    "‘": "'",  "’": "'",  "“": '"',  "”": '"',
    "–": "-",  "—": "-",  " ": " ",  "…": "...",
    "&amp;": "&",   "&lt;":  "<",   "&gt;":  ">",   "&quot;": '"',
    "&apos;": "'",  "&#39;": "'",
}
_WEB_NOISE = re.compile(
    r"(?:subscribe now|sign up|newsletter|enable javascript|"
    r"cookie policy|accept cookies|terms of service|privacy policy|"
    r"advertisement|click here|share this|follow us on|"
    r"related articles?|you may also like|more from|trending now)",
    re.IGNORECASE,
)

# ── language detection ─────────────────────────────────────────────────────────
try:
    from langdetect import detect as _ld_detect, LangDetectException
    _LANG_OK = True
except ImportError:
    _LANG_OK = False
    logger.warning("langdetect not installed — language detection disabled")


def detect_language(text: str) -> str:
    if not _LANG_OK or not text:
        return "unknown"
    try:
        return _ld_detect(text[:800])
    except Exception:
        return "unknown"


# ── core cleaning utilities ────────────────────────────────────────────────────

def fix_encoding(text: str) -> str:
    for bad, good in _ENCODING_MAP.items():
        text = text.replace(bad, good)
    return text


def strip_html(text: str) -> str:
    return _HTML_TAG.sub(" ", text)


def normalise_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def normalise_whitespace(text: str) -> str:
    return _WHITESPACE.sub(" ", text).strip()


def remove_web_noise(text: str) -> str:
    """Drop sentences that look like navigation/cookie/ad copy."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    clean = [s for s in sentences if not _WEB_NOISE.search(s) and len(s) > 15]
    return " ".join(clean)


def clean_text(raw: str, strip_urls: bool = True, remove_noise: bool = True) -> Optional[str]:
    """Full cleaning pipeline for extracted article text."""
    if not raw:
        return None

    text = normalise_unicode(raw)
    text = fix_encoding(text)
    text = strip_html(text)

    if strip_urls:
        text = _URL_PATTERN.sub("", text)

    text = _REPEAT_PUNCT.sub(r"\1", text)
    text = normalise_whitespace(text)

    if remove_noise:
        text = remove_web_noise(text)

    return text if len(text) > 30 else None


# ── quality assessment ─────────────────────────────────────────────────────────

def word_count(text: str) -> int:
    return len(text.split()) if text else 0


def _repetition_ratio(text: str) -> float:
    """Fraction of repeated sentences (0 = all unique, 1 = all identical)."""
    sents = [s.strip() for s in text.split(".") if len(s.strip()) > 10]
    if len(sents) < 3:
        return 0.0
    return 1.0 - len(set(sents)) / len(sents)


def is_quality_content(text: str, min_words: int = 50) -> bool:
    if not text or word_count(text) < min_words:
        return False
    if _repetition_ratio(text) > 0.6:
        logger.debug("Dropping high-repetition content ({:.0%} duplicate sentences)", _repetition_ratio(text))
        return False
    return True


# ── date normalisation ─────────────────────────────────────────────────────────

def normalise_date(raw_date: str) -> str:
    """
    Convert any common date string to ISO-8601 UTC (YYYY-MM-DDTHH:MM:SSZ).
    Returns the original string unchanged on parse failure.
    """
    if not raw_date:
        return ""

    # Already ISO-8601-ish
    if re.match(r"\d{4}-\d{2}-\d{2}", raw_date):
        return raw_date

    # RFC 2822 (RSS feeds)
    try:
        dt = parsedate_to_datetime(raw_date)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    # Unix timestamp (Reddit)
    try:
        ts = float(raw_date)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, OSError):
        pass

    return raw_date
