"""Abstractive summarisation using HuggingFace transformers."""
from __future__ import annotations

from typing import Optional

from app.utils.logger import get_logger
from app.utils.text_cleaner import truncate_to_chars

logger = get_logger(__name__)

_DEFAULT_MODEL = "sshleifer/distilbart-cnn-12-6"


class Summarizer:
    def __init__(self, model_name: str = _DEFAULT_MODEL,
                 max_length: int = 160, min_length: int = 50,
                 max_input_chars: int = 4000) -> None:
        self.model_name = model_name
        self.max_length = max_length
        self.min_length = min_length
        self.max_input_chars = max_input_chars
        self._pipeline = None

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        try:
            from transformers import pipeline
            logger.info("Loading summariser model: {}", self.model_name)
            self._pipeline = pipeline(
                "summarization",
                model=self.model_name,
                device=-1,  # CPU; change to 0 for GPU
            )
            logger.info("Summariser model loaded")
        except Exception as exc:
            logger.error("Failed to load summariser: {}", exc)
            self._pipeline = "unavailable"

    def summarize(self, text: str) -> str:
        self._load()

        if self._pipeline == "unavailable" or not text:
            return _extractive_fallback(text, n_sentences=3)

        truncated = truncate_to_chars(text, self.max_input_chars)
        wc = len(truncated.split())

        # Model requires input longer than max_length
        if wc < self.min_length + 10:
            return truncated

        actual_max = min(self.max_length, max(self.min_length + 10, wc // 3))

        try:
            result = self._pipeline(
                truncated,
                max_length=actual_max,
                min_length=self.min_length,
                do_sample=False,
                truncation=True,
            )
            return result[0]["summary_text"].strip()
        except Exception as exc:
            logger.warning("Summariser inference error: {}", exc)
            return _extractive_fallback(text, n_sentences=3)


def _extractive_fallback(text: str, n_sentences: int = 3) -> str:
    """Return the first N sentences as a simple extractive summary."""
    import re
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return " ".join(sentences[:n_sentences]).strip()
