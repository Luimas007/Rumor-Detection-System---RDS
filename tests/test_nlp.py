"""NLP module tests — model-free paths only (no downloads required)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from app.nlp.content_filter import quality_score, detect_language
from app.nlp.claim_extractor import ClaimExtractor, _CLAIM_VERBS, _STAT_RE
from app.nlp.topic_detector import _keyword_fallback
from app.nlp.summarizer import _extractive_fallback
from app.utils.text_cleaner import truncate_to_chars, split_into_sentences


# ─── Content filter ───────────────────────────────────────────────────────────

def test_quality_score_empty():
    ok, score = quality_score("")
    assert not ok and score == 0.0

def test_quality_score_too_short():
    ok, _ = quality_score("short text")
    assert not ok

def test_quality_score_valid():
    text = ("The government announced a new policy on climate change. " * 12)
    ok, score = quality_score(text)
    assert ok
    assert 0 < score <= 1.0


# ─── Claim extractor (heuristic path) ────────────────────────────────────────

def test_claim_verbs_regex():
    assert _CLAIM_VERBS.search("The minister said the plan is ready")
    assert _CLAIM_VERBS.search("Scientists confirmed the discovery")
    assert not _CLAIM_VERBS.search("The sky is blue today")

def test_stat_regex():
    assert _STAT_RE.search("costs $3.5 billion")
    assert _STAT_RE.search("increased by 42%")

def test_claim_extractor_no_model():
    extractor = ClaimExtractor(max_claims=3)
    extractor._ner_pipe = "unavailable"  # skip model load
    text = (
        "The president said inflation reached 8 percent last month. "
        "Researchers confirmed the vaccine is 95 percent effective. "
        "The company announced revenue of $12 billion for Q3. "
        "The weather is nice outside today. It was sunny."
    )
    claims = extractor.extract(text)
    assert isinstance(claims, list)
    assert len(claims) <= 3


# ─── Topic detector (keyword fallback) ───────────────────────────────────────

def test_keyword_fallback_politics():
    themes, main = _keyword_fallback(
        "The president and congress voted on the new election policy.",
        ["politics", "sports", "technology"],
    )
    assert "politics" in themes or main == "politics"

def test_keyword_fallback_technology():
    themes, main = _keyword_fallback(
        "AI software and digital algorithms are transforming the internet.",
        ["politics", "technology", "health"],
    )
    assert "technology" in themes or main == "technology"


# ─── Summarizer (extractive fallback) ────────────────────────────────────────

def test_extractive_fallback():
    text = (
        "The economy grew by 3 percent. Inflation is falling. "
        "Experts say recovery is on track. Markets rallied on the news."
    )
    summary = _extractive_fallback(text, n_sentences=2)
    assert len(summary) > 10
    assert "economy" in summary or "Inflation" in summary


# ─── Utility: truncate_to_chars ───────────────────────────────────────────────

def test_truncate_exact():
    text = "a" * 100
    assert len(truncate_to_chars(text, 50)) <= 50

def test_truncate_sentence_boundary():
    text = "Hello world. This is a test. More text here."
    result = truncate_to_chars(text, 25)
    assert result.endswith(".")

def test_truncate_no_op():
    text = "Short text."
    assert truncate_to_chars(text, 1000) == text
