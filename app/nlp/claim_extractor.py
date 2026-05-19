"""Key claim extraction using NER + heuristic sentence scoring."""
from __future__ import annotations

import re
from typing import Optional

from app.utils.logger import get_logger
from app.utils.text_cleaner import split_into_sentences, truncate_to_chars

logger = get_logger(__name__)

# Verbs that signal a factual claim or statement
_CLAIM_VERBS = re.compile(
    r"\b(?:says?|said|claims?|claimed|reports?|reported|confirms?|confirmed|"
    r"reveals?|revealed|shows?|showed|finds?|found|alleges?|alleged|states?|"
    r"stated|announces?|announced|warns?|warned|denies?|denied|acknowledges?|"
    r"acknowledged|estimates?|estimated|projects?|projected|argues?|argued|"
    r"suggests?|suggested|indicates?|indicated|proves?|proved|demonstrates?|"
    r"demonstrated|concludes?|concluded|discovered|discovers?)\b",
    re.IGNORECASE,
)

# Patterns for numbers and statistics
_STAT_RE = re.compile(r"\b\d+(?:[,.\s]\d+)*\s*(?:%|percent|million|billion|"
                      r"thousand|hundred|trillion)?\b")

# Entity indicators (simple heuristic: title-cased multi-word sequences)
_ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b")

_DEFAULT_NER_MODEL = "dslim/bert-base-NER"


class ClaimExtractor:
    def __init__(self, ner_model: str = _DEFAULT_NER_MODEL,
                 max_claims: int = 6, min_claim_len: int = 30,
                 max_input_chars: int = 4000) -> None:
        self.ner_model = ner_model
        self.max_claims = max_claims
        self.min_claim_len = min_claim_len
        self.max_input_chars = max_input_chars
        self._ner_pipe = None

    def _load_ner(self) -> None:
        if self._ner_pipe is not None:
            return
        try:
            from transformers import pipeline
            logger.info("Loading NER model: {}", self.ner_model)
            self._ner_pipe = pipeline(
                "ner",
                model=self.ner_model,
                aggregation_strategy="simple",
                device=-1,
            )
            logger.info("NER model loaded")
        except Exception as exc:
            logger.warning("NER model unavailable ({}), using heuristics only", exc)
            self._ner_pipe = "unavailable"

    def _ner_entities(self, text: str) -> set[str]:
        """Return the set of recognised entity strings from NER."""
        if self._ner_pipe == "unavailable":
            return set()
        try:
            results = self._ner_pipe(text[:512])  # NER models have token limits
            return {r["word"] for r in results if r.get("score", 0) > 0.85}
        except Exception as exc:
            logger.debug("NER inference error: {}", exc)
            return set()

    def _score_sentence(self, sentence: str, entities: set[str]) -> float:
        """Heuristic claim score: 0.0–1.0."""
        score = 0.0

        # Reward factual/claim verbs
        if _CLAIM_VERBS.search(sentence):
            score += 0.40

        # Reward presence of statistics/numbers
        stats = _STAT_RE.findall(sentence)
        if stats:
            score += min(0.30, len(stats) * 0.10)

        # Reward named entities (heuristic)
        title_entities = _ENTITY_RE.findall(sentence)
        if title_entities:
            score += min(0.20, len(title_entities) * 0.07)

        # Reward NER entities
        matched_ner = sum(1 for e in entities if e.lower() in sentence.lower())
        if matched_ner:
            score += min(0.20, matched_ner * 0.07)

        # Penalise very short or very long sentences
        wc = len(sentence.split())
        if wc < 8 or wc > 60:
            score -= 0.20

        return max(0.0, round(score, 4))

    def extract(self, text: str) -> list[str]:
        self._load_ner()
        if not text:
            return []

        truncated = truncate_to_chars(text, self.max_input_chars)
        sentences = split_into_sentences(truncated)

        if not sentences:
            return []

        entities = self._ner_entities(truncated[:512])

        scored = [
            (s, self._score_sentence(s, entities))
            for s in sentences
            if len(s) >= self.min_claim_len
        ]
        scored.sort(key=lambda x: x[1], reverse=True)

        # Deduplicate by content similarity (simple substring check)
        claims: list[str] = []
        for sentence, score in scored:
            if score < 0.15:
                continue
            if any(sentence[:40] in c or c[:40] in sentence for c in claims):
                continue
            claims.append(sentence)
            if len(claims) >= self.max_claims:
                break

        return claims
