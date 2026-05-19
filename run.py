"""Entry point for the RDS Flask application."""
import sys
import os

# Ensure the project root is on the path so `app` is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows asyncio compatibility (needed by some Scrapling internals)
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import yaml
from app import create_app

if __name__ == "__main__":
    try:
        with open("config/config.yaml", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh).get("flask", {})
    except FileNotFoundError:
        cfg = {}

    app = create_app()
    app.run(
        host=cfg.get("host", "0.0.0.0"),
        port=int(cfg.get("port", 5000)),
        debug=cfg.get("debug", True),
        threaded=cfg.get("threaded", True),
        use_reloader=False,  # prevents double-initialisation of NLP models
    )
