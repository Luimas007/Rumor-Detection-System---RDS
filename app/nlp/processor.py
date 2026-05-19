"""NLP orchestrator — loads config and ties all NLP modules together."""
from __future__ import annotations

from typing import Any

import yaml

from app.models.schemas import AnalyzedArticle, Sentiment
from app.nlp.claim_extractor import ClaimExtractor
from app.nlp.content_filter import ContentFilter
from app.nlp.semantic_analyzer import SemanticAnalyzer
from app.nlp.summarizer import Summarizer
from app.nlp.topic_detector import TopicDetector
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _load_nlp_config() -> dict:
    try:
        with open("config/config.yaml", encoding="utf-8") as fh:
            return yaml.safe_load(fh).get("nlp", {})
    except Exception:
        return {}


class NLPProcessor:
    """
    Singleton-style NLP processor.  All models are lazy-loaded on first use.
    One instance is typically shared across a scraping job.
    """

    _instance: "NLPProcessor | None" = None

    def __new__(cls) -> "NLPProcessor":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    def _init_components(self) -> None:
        if self._initialised:
            return
        cfg = _load_nlp_config()

        self.filter = ContentFilter(
            min_words=cfg.get("max_claims", 40),
        )
        self.summarizer = Summarizer(
            model_name=cfg.get("summarizer_model", "sshleifer/distilbart-cnn-12-6"),
            max_length=cfg.get("summarizer_max_length", 160),
            min_length=cfg.get("summarizer_min_length", 50),
            max_input_chars=cfg.get("max_input_chars", 4000),
        )
        self.claim_extractor = ClaimExtractor(
            ner_model=cfg.get("ner_model", "dslim/bert-base-NER"),
            max_claims=cfg.get("max_claims", 6),
            min_claim_len=cfg.get("min_claim_length", 30),
            max_input_chars=cfg.get("max_input_chars", 4000),
        )
        self.topic_detector = TopicDetector(
            model_name=cfg.get("classifier_model", "cross-encoder/nli-deberta-v3-small"),
            topics=cfg.get("topics"),
            threshold=cfg.get("classifier_threshold", 0.30),
            max_input_chars=1000,
        )
        self.semantic_analyzer = SemanticAnalyzer(
            embedder_model=cfg.get("embedder_model", "sentence-transformers/all-MiniLM-L6-v2"),
            sentiment_model=cfg.get("sentiment_model",
                                    "distilbert-base-uncased-finetuned-sst-2-english"),
            max_input_chars=cfg.get("max_input_chars", 4000),
        )
        self._initialised = True

    def process(self, base: dict[str, Any]) -> AnalyzedArticle:
        """
        Run the full NLP pipeline on a scraped article base dict.

        base keys: url, title, source, published, clean_content, word_count
        """
        self._init_components()

        text = base.get("clean_content", "")
        title = base.get("title", "")

        # Quality filter
        ok, quality = self.filter.score(text), 0.5
        passes, quality = self.filter.score(text), 0.5
        passes_filter = self.filter.passes(text)

        if not passes_filter:
            logger.debug("Article failed content filter: {}", base.get("url"))

        # Run all NLP even if quality is low — RDS downstream decides what to use
        quality = self.filter.score(text)

        summary = self.summarizer.summarize(text) if text else title
        claims = self.claim_extractor.extract(text) if text else []
        themes, main_theme = self.topic_detector.detect(f"{title}. {text}")
        sentiment_label, sentiment_score = self.semantic_analyzer.sentiment(text)
        embedding = self.semantic_analyzer.embed(text)

        # Composite reliability score (heuristic baseline for RDS)
        base_quality = self.filter.score(text)
        has_claims = min(1.0, len(claims) / 3)
        has_themes = 1.0 if themes else 0.5
        reliability = round((base_quality * 0.5 + has_claims * 0.3 + has_themes * 0.2), 4)

        return AnalyzedArticle(
            url=base.get("url", ""),
            title=title,
            source=base.get("source", ""),
            published=base.get("published", ""),
            clean_content=text,
            word_count=base.get("word_count", len(text.split())),
            language="en",
            summary=summary,
            key_claims=claims,
            themes=themes,
            main_theme=main_theme,
            sentiment=sentiment_label,
            sentiment_score=sentiment_score,
            reliability_score=reliability,
            embedding=embedding,
        )
