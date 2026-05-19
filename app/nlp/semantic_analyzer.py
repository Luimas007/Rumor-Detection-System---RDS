"""Semantic analysis: sentence embeddings and sentiment classification."""
from __future__ import annotations

from typing import Optional

from app.utils.logger import get_logger
from app.utils.text_cleaner import truncate_to_chars

logger = get_logger(__name__)

_DEFAULT_EMBEDDER = "sentence-transformers/all-MiniLM-L6-v2"
_DEFAULT_SENTIMENT = "distilbert-base-uncased-finetuned-sst-2-english"

_LABEL_MAP = {
    "POSITIVE": "positive",
    "NEGATIVE": "negative",
    "NEUTRAL": "neutral",
    "LABEL_0": "negative",
    "LABEL_1": "positive",
}


class SemanticAnalyzer:
    def __init__(self,
                 embedder_model: str = _DEFAULT_EMBEDDER,
                 sentiment_model: str = _DEFAULT_SENTIMENT,
                 max_input_chars: int = 2000) -> None:
        self.embedder_model = embedder_model
        self.sentiment_model = sentiment_model
        self.max_input_chars = max_input_chars
        self._embedder = None
        self._sentiment_pipe = None

    # ─── Lazy loaders ────────────────────────────────────────────────────────

    def _load_embedder(self) -> None:
        if self._embedder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading sentence embedder: {}", self.embedder_model)
            self._embedder = SentenceTransformer(self.embedder_model)
            logger.info("Embedder loaded")
        except Exception as exc:
            logger.error("Failed to load embedder: {}", exc)
            self._embedder = "unavailable"

    def _load_sentiment(self) -> None:
        if self._sentiment_pipe is not None:
            return
        try:
            from transformers import pipeline
            logger.info("Loading sentiment model: {}", self.sentiment_model)
            self._sentiment_pipe = pipeline(
                "sentiment-analysis",
                model=self.sentiment_model,
                device=-1,
                truncation=True,
                max_length=512,
            )
            logger.info("Sentiment model loaded")
        except Exception as exc:
            logger.error("Failed to load sentiment model: {}", exc)
            self._sentiment_pipe = "unavailable"

    # ─── Public methods ───────────────────────────────────────────────────────

    def embed(self, text: str) -> Optional[list[float]]:
        """Return a 384-dim embedding vector (all-MiniLM-L6-v2)."""
        self._load_embedder()
        if self._embedder == "unavailable" or not text:
            return None
        try:
            snippet = truncate_to_chars(text, self.max_input_chars)
            vec = self._embedder.encode(snippet, show_progress_bar=False)
            return vec.tolist()
        except Exception as exc:
            logger.warning("Embedding error: {}", exc)
            return None

    def sentiment(self, text: str) -> tuple[str, float]:
        """
        Returns (label, score).
        label ∈ {'positive', 'negative', 'neutral'}
        score ∈ [0, 1]
        """
        self._load_sentiment()
        if self._sentiment_pipe == "unavailable" or not text:
            return "neutral", 0.5
        try:
            snippet = truncate_to_chars(text, 512 * 4)  # ~512 tokens
            result = self._sentiment_pipe(snippet)[0]
            raw_label = result.get("label", "NEUTRAL").upper()
            label = _LABEL_MAP.get(raw_label, "neutral")
            score = float(result.get("score", 0.5))
            return label, round(score, 4)
        except Exception as exc:
            logger.warning("Sentiment inference error: {}", exc)
            return "neutral", 0.5
