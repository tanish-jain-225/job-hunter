"""Views, static asset serving, health checks, and authentication configuration routes."""

from __future__ import annotations

import os
import time

from flask import Blueprint, g, jsonify, render_template, request, send_file

from ...auth import get_supabase_config, require_auth
from ..state import ROOT

views_bp = Blueprint("views", __name__)


@views_bp.route("/")
@views_bp.route("/api/index.py")
def index():
    """Render main Light Mode dashboard with digest & job tracker."""
    return render_template("index.html")


@views_bp.route("/api/health")
def api_health():
    """Service health check endpoint for monitoring, Vercel status, and uptime verification."""
    import requests

    is_vercel = os.environ.get("VERCEL") == "1"
    supabase_cfg = get_supabase_config()
    auth_backend_ready = bool(supabase_cfg.get("supabase_url") and supabase_cfg.get("supabase_anon_key"))
    production_misconfigured = is_vercel and not auth_backend_ready

    memory_configured = bool(
        supabase_cfg.get("supabase_url")
        and (supabase_cfg.get("supabase_anon_key") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    )

    db_status = "unconfigured"
    if memory_configured:
        db_status = "connected"
        if request.args.get("deep") == "1":
            try:
                probe_url = f"{supabase_cfg['supabase_url']}/rest/v1/"
                resp = requests.get(
                    probe_url,
                    headers={"apikey": supabase_cfg.get("supabase_anon_key") or ""},
                    timeout=1.5,
                )
                if resp.status_code not in (200, 401, 403, 404):
                    db_status = "unreachable"
            except Exception:
                db_status = "unreachable"

    return jsonify(
        {
            "status": "misconfigured" if production_misconfigured else "healthy",
            "service": "job-hunter",
            "version": "1.0.0",
            "environment": "vercel" if is_vercel else "local",
            "auth_required": supabase_cfg.get("auth_required", False),
            "memory_connected": memory_configured,
            "database_status": db_status,
            "llm_default_model": "gemini-3.5-flash",
            "timestamp": time.time(),
            "utc_time": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
        }
    ), 503 if production_misconfigured else 200


@views_bp.route("/logo.png")
def serve_logo():
    """Serve brand logo PNG."""
    logo_path = (ROOT / "static" / "assets" / "logo.png").resolve()
    if logo_path.is_file():
        return send_file(str(logo_path), mimetype="image/png")
    return "", 204


@views_bp.route("/favicon.ico")
def serve_favicon():
    """Serve brand favicon (.ico preferred, falling back to logo.png)."""
    fav_path = (ROOT / "static" / "assets" / "favicon.ico").resolve()
    if fav_path.is_file():
        return send_file(str(fav_path), mimetype="image/x-icon")
    logo_path = (ROOT / "static" / "assets" / "logo.png").resolve()
    if logo_path.is_file():
        return send_file(str(logo_path), mimetype="image/png")
    return "", 204


@views_bp.route("/api/auth/config")
def api_auth_config():
    """Return public Supabase configuration for client authentication initialization."""
    cfg = get_supabase_config()
    production_misconfigured = os.environ.get("VERCEL") == "1" and not (
        cfg["supabase_url"] and cfg["supabase_anon_key"]
    )
    if production_misconfigured:
        return jsonify(
            {
                "status": "error",
                "code": "AUTH_BACKEND_MISCONFIGURED",
                "message": "Authentication is temporarily unavailable. Please try again later.",
            }
        ), 503
    return jsonify(
        {
            "status": "success",
            "auth_required": cfg["auth_required"],
            "supabase_url": cfg["supabase_url"],
            "supabase_anon_key": cfg["supabase_anon_key"],
        }
    )


@views_bp.route("/api/auth/user")
@require_auth
def api_auth_user():
    """Return currently authenticated user details from session context."""
    return jsonify({"status": "success", "user": getattr(g, "user", None)})
