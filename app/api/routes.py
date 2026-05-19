"""Flask API — scraper-only endpoints (no NLP/rumor analysis)."""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.models.schemas import JobStatus
from app.scraper.engine import create_job, get_job, list_jobs
from app.scraper.sources import SOURCE_REGISTRY
from app.utils.logger import get_logger

logger = get_logger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

_VALID_SOURCES = set(SOURCE_REGISTRY.keys())


# ── Health ─────────────────────────────────────────────────────────────────────

@api_bp.get("/health")
def health():
    return jsonify({"status": "ok", "service": "RDS Scraper", "sources": list(_VALID_SOURCES)})


# ── Search ─────────────────────────────────────────────────────────────────────

@api_bp.post("/search")
def search():
    """
    Start a scrape job.

    Body (JSON):
        query        str   required — search query
        sources      list  optional — subset of source keys; default: all
        max_articles int   optional — 5–100, default 30
    """
    body = request.get_json(silent=True) or {}

    query = (body.get("query") or "").strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    if len(query) > 500:
        return jsonify({"error": "query too long (max 500 chars)"}), 400

    raw_sources = body.get("sources") or list(_VALID_SOURCES)
    if isinstance(raw_sources, str):
        raw_sources = [raw_sources]
    sources = [s for s in raw_sources if s in _VALID_SOURCES]
    if not sources:
        return jsonify({"error": f"No valid sources. Valid: {sorted(_VALID_SOURCES)}"}), 400

    try:
        max_articles = max(5, min(int(body.get("max_articles", 60)), 200))
    except (TypeError, ValueError):
        max_articles = 60

    job = create_job(query=query, sources=sources, max_articles=max_articles)
    logger.info("POST /search — job={} query={!r}", job.id[:8], query)

    return jsonify({
        "job_id":       job.id,
        "query":        job.query,
        "sources":      job.sources,
        "max_articles": job.max_articles,
        "status":       job.status.value,
    }), 202


# ── Job polling ────────────────────────────────────────────────────────────────

@api_bp.get("/job/<job_id>")
def job_status(job_id: str):
    """Poll a job. Returns full articles array only when status == 'completed'."""
    job = get_job(job_id)
    if job is None:
        return jsonify({"error": "job not found"}), 404
    include = job.status == JobStatus.COMPLETED
    return jsonify(job.to_dict(include_articles=include))


@api_bp.get("/jobs")
def jobs_list():
    """List the 20 most recent jobs (no articles included)."""
    return jsonify([j.to_dict(include_articles=False) for j in list_jobs(limit=20)])


# ── Sources meta ───────────────────────────────────────────────────────────────

@api_bp.get("/sources")
def sources_list():
    """Return all registered source keys, names, and categories."""
    import yaml
    try:
        with open("config/sources.yaml", encoding="utf-8") as fh:
            src_cfg = yaml.safe_load(fh).get("sources", {})
    except Exception:
        src_cfg = {}

    from app.scraper.sources import SOURCE_REGISTRY as reg
    return jsonify([
        {
            "key":      k,
            "name":     cls.name,
            "type":     cls.source_type,
            "category": src_cfg.get(k, {}).get("category", "news"),
        }
        for k, cls in reg.items()
    ])


# ── Error handlers ─────────────────────────────────────────────────────────────

@api_bp.errorhandler(404)
def not_found(_):
    return jsonify({"error": "not found"}), 404

@api_bp.errorhandler(405)
def method_not_allowed(_):
    return jsonify({"error": "method not allowed"}), 405

@api_bp.errorhandler(500)
def internal(_):
    return jsonify({"error": "internal server error"}), 500
