"""Zero-shot topic/theme detection."""
from __future__ import annotations

from app.utils.logger import get_logger
from app.utils.text_cleaner import truncate_to_chars

logger = get_logger(__name__)

_DEFAULT_MODEL = "cross-encoder/nli-deberta-v3-small"

_DEFAULT_TOPICS = [
    "politics", "technology", "health", "science", "economy",
    "environment", "sports", "entertainment", "crime",
    "education", "military", "business", "social issues", "international",
]


class TopicDetector:
    def __init__(self, model_name: str = _DEFAULT_MODEL,
                 topics: list[str] | None = None,
                 threshold: float = 0.30,
                 max_input_chars: int = 1000) -> None:
        self.model_name = model_name
        self.topics = topics or _DEFAULT_TOPICS
        self.threshold = threshold
        self.max_input_chars = max_input_chars
        self._pipeline = None

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        try:
            from transformers import pipeline
            logger.info("Loading zero-shot classifier: {}", self.model_name)
            self._pipeline = pipeline(
                "zero-shot-classification",
                model=self.model_name,
                device=-1,
            )
            logger.info("Zero-shot classifier loaded")
        except Exception as exc:
            logger.error("Failed to load topic detector: {}", exc)
            self._pipeline = "unavailable"

    def detect(self, text: str) -> tuple[list[str], str]:
        """
        Returns (themes, main_theme).
        themes: all topics above threshold, sorted by score desc
        main_theme: highest-scoring topic
        """
        self._load()

        if not text:
            return [], ""

        # Use first portion of text for speed (topics usually evident early)
        snippet = truncate_to_chars(text, self.max_input_chars)

        if self._pipeline == "unavailable":
            return _keyword_fallback(snippet, self.topics, self.threshold)

        try:
            result = self._pipeline(
                snippet,
                candidate_labels=self.topics,
                multi_label=True,
            )
            pairs = list(zip(result["labels"], result["scores"]))
            pairs.sort(key=lambda x: x[1], reverse=True)

            themes = [label for label, score in pairs if score >= self.threshold]
            main_theme = pairs[0][0] if pairs else ""
            return themes, main_theme

        except Exception as exc:
            logger.warning("Topic detection inference error: {}", exc)
            return _keyword_fallback(snippet, self.topics, self.threshold)


def _keyword_fallback(text: str, topics: list[str],
                      threshold: float = 0.30) -> tuple[list[str], str]:
    """Simple keyword matching fallback when model is unavailable."""
    lower = text.lower()
    _KEYWORDS: dict[str, list[str]] = {
        "politics": ["government", "president", "senator", "congress", "election", "vote", "policy", "democrat", "republican"],
        "technology": ["ai", "software", "app", "tech", "digital", "cyber", "internet", "data", "algorithm"],
        "health": ["hospital", "disease", "vaccine", "doctor", "patient", "medicine", "health", "covid", "cancer"],
        "science": ["research", "study", "scientists", "experiment", "discovery", "nasa", "biology", "physics"],
        "economy": ["market", "stock", "inflation", "gdp", "economy", "trade", "invest", "bank", "financial"],
        "environment": ["climate", "carbon", "emission", "pollution", "green", "renewable", "forest", "species"],
        "sports": ["game", "match", "team", "player", "championship", "league", "score", "tournament"],
        "entertainment": ["movie", "music", "celebrity", "actor", "award", "film", "show", "concert"],
        "crime": ["police", "arrest", "murder", "court", "judge", "prison", "crime", "fraud", "trial"],
        "education": ["school", "university", "student", "teacher", "education", "college", "degree"],
        "military": ["army", "military", "soldier", "war", "weapons", "missile", "defense", "troops"],
        "business": ["company", "ceo", "startup", "revenue", "profit", "merger", "acquisition"],
        "social issues": ["racism", "protest", "rights", "inequality", "discrimination", "poverty"],
        "international": ["country", "nation", "president", "foreign", "sanctions", "diplomat", "un"],
    }

    scores: dict[str, float] = {}
    for topic in topics:
        keywords = _KEYWORDS.get(topic, [topic])
        matches = sum(1 for kw in keywords if kw in lower)
        scores[topic] = matches / max(len(keywords), 1)

    sorted_topics = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    themes = [t for t, s in sorted_topics if s >= threshold * 0.3]  # lower bar for keyword method
    main_theme = sorted_topics[0][0] if sorted_topics else ""
    return themes[:5], main_theme
