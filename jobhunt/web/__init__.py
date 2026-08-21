"""Job Hunter Web Application Factory and Flask Engine."""
from __future__ import annotations

import logging
from typing import Optional
from pathlib import Path

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from .routes import views_bp, jobs_bp, profile_bp, pipeline_bp
from .state import (
    ROOT,
    get_project_root,
    get_current_user_context,
    get_user_pipeline_state,
    set_user_pipeline_state,
    get_store_version,
    _USER_PIPELINE_STATES,
    _PIPELINE_LOCK,
)

logger = logging.getLogger(__name__)


def handle_exception(e: Exception):
    """Global exception handler converting unhandled exceptions into structured JSON responses."""
    if isinstance(e, HTTPException):
        return jsonify({
            "status": "error",
            "message": e.description or str(e)
        }), e.code
    import traceback
    logger.error("Unhandled Exception in Flask app:\n%s", traceback.format_exc())
    return jsonify({
        "status": "error",
        "message": f"Internal Error: {str(e)}"
    }), 500


def add_cache_headers(response):
    """Add standard security headers and ensure dynamic API responses are fresh and never cached improperly."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.path.startswith("/api/") and not request.path.endswith(".py"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def create_app(
    template_folder: Optional[str | Path] = None,
    static_folder: Optional[str | Path] = None,
) -> Flask:
    """Create and configure an instance of the Job Hunter Flask application."""
    root_dir = get_project_root()
    tmpl = str(template_folder or (root_dir / "templates"))
    stat = str(static_folder or (root_dir / "static"))

    app = Flask(
        "jobhunt.web",
        root_path=str(root_dir),
        template_folder=tmpl,
        static_folder=stat,
    )

    # Register global hooks & error handlers
    app.after_request(add_cache_headers)
    app.errorhandler(Exception)(handle_exception)

    # Register modular Blueprints
    app.register_blueprint(views_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(pipeline_bp)

    return app


__all__ = [
    "create_app",
    "handle_exception",
    "add_cache_headers",
    "get_project_root",
    "get_current_user_context",
    "get_user_pipeline_state",
    "set_user_pipeline_state",
    "get_store_version",
    "_USER_PIPELINE_STATES",
    "_PIPELINE_LOCK",
    "ROOT",
]
