"""Flask API routes."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.models.schemas import JobStatus
from app.scraper.engine import create_job, get_job, list_jobs
from app.utils.logger import get_logger

logger = get_logger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

_VALID_SOURCES = {"google_news", "bing_news", "reddit"}


@api_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "RDS Scraper API"})


@api_bp.route("/search", methods=["POST"])
def search():
    """Start a new search job.

    Request body (JSON):
      query        str   required
      sources      list  optional, default: all enabled
      max_articles int   optional, default: 30, max: 60
    """
    data = request.get_json(silent=True) or {}

    query = (data.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    if len(query) > 500:
        return jsonify({"error": "query too long (max 500 chars)"}), 400

    raw_sources = data.get("sources") or list(_VALID_SOURCES)
    if isinstance(raw_sources, str):
        raw_sources = [raw_sources]
    sources = [s for s in raw_sources if s in _VALID_SOURCES]
    if not sources:
        sources = list(_VALID_SOURCES)

    try:
        max_articles = int(data.get("max_articles", 30))
        max_articles = max(5, min(max_articles, 60))
    except (ValueError, TypeError):
        max_articles = 30

    job = create_job(query=query, sources=sources, max_articles=max_articles)
    logger.info("New search job {} | query={!r}", job.id[:8], query)

    return jsonify({
        "job_id": job.id,
        "query": job.query,
        "sources": job.sources,
        "max_articles": job.max_articles,
        "status": job.status.value,
        "message": "Job created and queued.",
    }), 202


@api_bp.route("/job/<job_id>", methods=["GET"])
def job_status(job_id: str):
    """Poll job status and results."""
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "job not found"}), 404

    include_articles = job.status == JobStatus.COMPLETED
    return jsonify(job.to_dict(include_articles=include_articles))


@api_bp.route("/jobs", methods=["GET"])
def jobs_list():
    """List recent jobs (latest 20)."""
    jobs = list_jobs(limit=20)
    return jsonify([j.to_dict(include_articles=False) for j in jobs])


@api_bp.route("/analyze", methods=["POST"])
def analyze_text():
    """Analyze a raw text snippet on demand (no scraping).

    Request body:
      text  str  required
    """
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()

    if not text:
        return jsonify({"error": "text is required"}), 400
    if len(text) > 20_000:
        return jsonify({"error": "text too long (max 20 000 chars)"}), 400

    try:
        from app.nlp.processor import NLPProcessor
        nlp = NLPProcessor()
        base = {"url": "", "title": "", "source": "direct", "published": "",
                "clean_content": text, "word_count": len(text.split())}
        article = nlp.process(base)
        return jsonify({
            "summary": article.summary,
            "key_claims": article.key_claims,
            "themes": article.themes,
            "main_theme": article.main_theme,
            "sentiment": article.sentiment,
            "sentiment_score": article.sentiment_score,
            "reliability_score": article.reliability_score,
        })
    except Exception as exc:
        logger.exception("Analyze endpoint error: {}", exc)
        return jsonify({"error": "Analysis failed", "detail": str(exc)}), 500


@api_bp.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@api_bp.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"error": "Method not allowed"}), 405


@api_bp.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error"}), 500
