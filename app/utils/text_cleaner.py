import re
import unicodedata
from typing import Optional

import cleantext


# Compiled patterns for performance
_WHITESPACE_RE = re.compile(r"\s+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
_SPECIAL_CHARS_RE = re.compile(r"[^\w\s.,!?;:()\-'\"—–]")
_REPEATED_PUNCT_RE = re.compile(r"([.!?,;:]){2,}")
_AD_NOISE_RE = re.compile(
    r"(?:subscribe|sign up|newsletter|cookie|advertisement|sponsored|"
    r"click here|read more|share this|follow us|related articles|"
    r"also read|must read|trending now)",
    re.IGNORECASE,
)


def strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub(" ", text)


def normalize_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def remove_urls(text: str) -> str:
    return _URL_RE.sub("", text)


def remove_emails(text: str) -> str:
    return _EMAIL_RE.sub("", text)


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def fix_encoding_artifacts(text: str) -> str:
    replacements = {
        "’": "'", "‘": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", " ": " ", "…": "...",
        "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'",
        "&#39;": "'", "&#8217;": "'",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def remove_noise_phrases(text: str) -> str:
    """Remove common web noise like ad/cookie banners by filtering sentences."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text)]
    clean = [s for s in sentences if not _AD_NOISE_RE.search(s) and len(s) > 15]
    return " ".join(clean)


def clean_article_text(raw: str, remove_urls_flag: bool = True,
                        remove_noise: bool = True) -> Optional[str]:
    """Full cleaning pipeline for scraped article content."""
    if not raw:
        return None

    text = normalize_unicode(raw)
    text = fix_encoding_artifacts(text)
    text = strip_html(text)

    if remove_urls_flag:
        text = remove_urls(text)
        text = remove_emails(text)

    text = _REPEATED_PUNCT_RE.sub(r"\1", text)
    text = normalize_whitespace(text)

    if remove_noise:
        text = remove_noise_phrases(text)

    if len(text) < 50:
        return None

    return text


def truncate_to_chars(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    truncated = text[:max_chars]
    last_period = truncated.rfind(".")
    if last_period > max_chars * 0.7:
        return truncated[: last_period + 1]
    return truncated


def split_into_sentences(text: str) -> list[str]:
    """Naive but fast sentence splitter (no NLTK dependency required at import)."""
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return [s.strip() for s in raw if len(s.strip()) > 10]


def count_words(text: str) -> int:
    return len(text.split())
