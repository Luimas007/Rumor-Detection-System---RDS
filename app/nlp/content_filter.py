"""Content quality filter — runs before heavy NLP to skip junk articles."""
from __future__ import annotations

from app.utils.logger import get_logger
from app.utils.text_cleaner import count_words

logger = get_logger(__name__)

try:
    from langdetect import detect, LangDetectException
    _LANGDETECT_OK = True
except ImportError:
    _LANGDETECT_OK = False
    logger.warning("langdetect not installed — language filtering disabled")


def detect_language(text: str) -> str:
    if not _LANGDETECT_OK or not text:
        return "unknown"
    try:
        return detect(text[:1000])
    except Exception:
        return "unknown"


def is_english(text: str) -> bool:
    lang = detect_language(text)
    return lang in ("en", "unknown")


def _repetition_ratio(text: str) -> float:
    """Fraction of repeated sentences — high = boilerplate/spam."""
    sentences = [s.strip() for s in text.split(".") if len(s.strip()) > 10]
    if len(sentences) < 3:
        return 0.0
    unique = len(set(sentences))
    return 1.0 - (unique / len(sentences))


def quality_score(text: str, min_words: int = 40) -> tuple[bool, float]:
    """
    Returns (passes: bool, score: float 0-1).
    score is used as a base for reliability_score downstream.
    """
    if not text:
        return False, 0.0

    wc = count_words(text)
    if wc < min_words:
        return False, 0.0

    # Score components
    length_score = min(1.0, wc / 500)            # saturates at 500 words
    rep_penalty = _repetition_ratio(text)         # 0=unique, 1=all duplicate
    lang_ok = is_english(text)

    if not lang_ok:
        return False, 0.0

    score = length_score * (1.0 - rep_penalty * 0.5)
    return True, round(max(0.0, min(1.0, score)), 4)


class ContentFilter:
    def __init__(self, min_words: int = 40):
        self.min_words = min_words

    def passes(self, text: str) -> bool:
        ok, _ = quality_score(text, self.min_words)
        return ok

    def score(self, text: str) -> float:
        _, s = quality_score(text, self.min_words)
        return s
