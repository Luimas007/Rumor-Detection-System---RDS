"""Flask application factory — scraper-only build."""
from __future__ import annotations

import yaml
from flask import Flask, render_template
from flask_cors import CORS

from app.api.routes import api_bp
from app.utils.logger import setup_logger


def create_app() -> Flask:
    try:
        with open("config/config.yaml", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh)
    except FileNotFoundError:
        cfg = {}

    log_cfg = cfg.get("logging", {})
    setup_logger(
        level=log_cfg.get("level", "DEBUG"),
        log_file=log_cfg.get("log_file", "logs/rds.log"),
        rotation=log_cfg.get("rotation", "10 MB"),
        retention=log_cfg.get("retention", "7 days"),
    )

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config["SECRET_KEY"]    = "rds-dev-secret-change-me"
    app.config["JSON_SORT_KEYS"] = False

    CORS(app, resources={r"/api/*": {"origins": "*"}})
    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        return render_template("index.html")

    return app
