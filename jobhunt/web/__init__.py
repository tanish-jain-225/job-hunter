"""Job Hunter Web Application Factory and Flask Engine."""

from __future__ import annotations

import logging
import os
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

# Detect production environment once at module load
_IS_PROD = os.environ.get("VERCEL") == "1" or os.environ.get("FLASK_ENV") == "production"


def handle_exception(e: Exception):
    """Global exception handler converting unhandled exceptions into structured JSON responses.

    In production: returns a generic message to the client — never raw exception strings
    or stack traces, which can leak internal implementation details and credentials.
    Full details are always logged server-side regardless of environment.
    """
    if isinstance(e, HTTPException):
        return jsonify({"status": "error", "message": e.description or str(e)}), e.code
    import traceback

    logger.error("Unhandled Exception in Flask app:\n%s", traceback.format_exc())
    # In production: generic message. In development: include the error for easier debugging.
    client_msg = "An internal error occurred. Please try again later." if _IS_PROD else f"Internal Error: {str(e)}"
    return jsonify({"status": "error", "message": client_msg}), 500


def add_cache_headers(response):
    """Add security headers and ensure dynamic API responses are never improperly cached."""
    # Standard security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Content-Security-Policy: restricts resource origins to prevent XSS/injection attacks
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdn.supabase.co; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' https://*.supabase.co https://api.github.com https://api.groq.com "
        "https://generativelanguage.googleapis.com; "
        "frame-ancestors 'none';"
    )

    # Permissions-Policy: disable browser features not needed by this app
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"

    # API cache-busting: ensure JSON responses are always fresh
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

    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24).hex()
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    is_prod = os.environ.get("VERCEL") == "1" or os.environ.get("FLASK_ENV") == "production"
    app.config["SESSION_COOKIE_SECURE"] = is_prod
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # Support reverse proxy headers (Vercel edge proxies) for accurate remote IP rate limiting
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    except Exception:
        pass

    # Rate limiting — gracefully degrades if flask-limiter is not installed.
    # Protects free-tier LLM quota from runaway clients or accidental loops.
    try:
        from flask_limiter import Limiter, RateLimitExceeded
        from flask_limiter.util import get_remote_address

        limiter = Limiter(
            key_func=get_remote_address,
            app=app,
            default_limits=["500 per hour"],
            storage_uri="memory://",
        )
        # Expose the limiter so blueprint routes can apply tighter per-endpoint limits
        app.extensions["limiter"] = limiter
        logger.debug("flask-limiter enabled (default: 500 req/hour per IP)")

        @app.errorhandler(RateLimitExceeded)
        def handle_rate_limit_exceeded(e):
            return jsonify({"status": "error", "message": "Rate limit exceeded. Please wait before retrying."}), 429
    except ImportError:
        logger.debug("flask-limiter not installed — rate limiting disabled. Install with: pip install flask-limiter")

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
