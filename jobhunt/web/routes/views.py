"""Views, static asset serving, health checks, and authentication configuration routes."""
from __future__ import annotations

import os
import time

from flask import Blueprint, g, jsonify, render_template, send_file

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
    is_vercel = os.environ.get("VERCEL") == "1"
    supabase_cfg = get_supabase_config()
    return jsonify({
        "status": "healthy",
        "service": "job-hunter",
        "version": "1.0.0",
        "environment": "vercel" if is_vercel else "local",
        "auth_required": supabase_cfg.get("auth_required", False),
        "memory_connected": bool(supabase_cfg.get("supabase_url") and (supabase_cfg.get("supabase_anon_key") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))),
        "timestamp": time.time(),
        "utc_time": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
    })


@views_bp.route("/logo.png")
@views_bp.route("/favicon.ico")
def serve_logo():
    """Serve brand logo or favicon."""
    logo_path = (ROOT / "logo.png").resolve()
    if logo_path.is_file():
        return send_file(str(logo_path), mimetype="image/png")
    return "", 204


@views_bp.route("/api/auth/config")
def api_auth_config():
    """Return public Supabase configuration for client authentication initialization."""
    cfg = get_supabase_config()
    return jsonify({
        "status": "success",
        "auth_required": cfg["auth_required"],
        "supabase_url": cfg["supabase_url"],
        "supabase_anon_key": cfg["supabase_anon_key"]
    })


@views_bp.route("/api/auth/user")
@require_auth
def api_auth_user():
    """Return currently authenticated user details from session context."""
    return jsonify({
        "status": "success",
        "user": getattr(g, "user", None)
    })
