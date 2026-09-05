"""State management, context resolution, and project root utilities for Job Hunter Web."""

from __future__ import annotations

import hashlib
import json
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional, Tuple

from flask import g

from ..auth import extract_bearer_token
from ..store import Store
from ..memory import SupabaseMemory

logger = logging.getLogger(__name__)


def sanitize_profile_for_response(profile: Any) -> Any:
    """Remove credentials and other secrets before profile data leaves the server."""
    if isinstance(profile, dict):
        safe = {}
        for key, value in profile.items():
            normalized = str(key).lower().replace("-", "_")
            if any(marker in normalized for marker in ("api_key", "token", "secret", "password")):
                continue
            safe[key] = sanitize_profile_for_response(value)
        return safe
    if isinstance(profile, list):
        return [sanitize_profile_for_response(value) for value in profile]
    return profile


def get_project_root() -> Path:
    """Find and resolve the repository root directory containing templates and static assets."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent,
        Path.cwd(),
    ]
    try:
        import jobhunt

        candidates.append(Path(jobhunt.__file__).resolve().parent.parent)
    except Exception:
        pass

    for candidate in candidates:
        if (candidate / "templates" / "index.html").is_file():
            return candidate

    return candidates[0]


ROOT = get_project_root()


def get_current_user_context() -> Tuple[Optional[str], Optional[str]]:
    """Extract (email, access_token) from active authenticated session.

    Delegates to app module if monkeypatched in testing environments.
    """
    if "app" in sys.modules and hasattr(sys.modules["app"], "_get_current_user_context"):
        app_mod = sys.modules["app"]
        if app_mod._get_current_user_context is not get_current_user_context:
            return app_mod._get_current_user_context()

    user = getattr(g, "user", None) or {}
    email = user.get("email")
    token = extract_bearer_token()
    return email, token


def get_user_profile(cfg: dict, email: Optional[str], token: Optional[str]) -> dict:
    """Load one user's profile from Supabase, then their isolated local cache."""
    memory = SupabaseMemory(token=token)
    if email and email != "developer@local":
        profile = memory.get_user_profile(email, token=token) or {}
        if profile:
            return profile

    if email and email != "developer@local":
        from ..store import get_user_profile_path

        profile_path = get_user_profile_path(cfg.get("profile_file", "profile.json"), email)
        if profile_path.is_file():
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                if isinstance(profile, dict):
                    return profile
            except (OSError, ValueError):
                pass

        # An authenticated user must never receive the generic local profile.
        return {}

    from .. import cli

    return cli._load_profile(cfg, raise_on_error=False) or {}


_USER_PIPELINE_STATES: dict[str, dict] = {}
_USER_LOG_BUFFERS: dict[str, list[str]] = {}
_PIPELINE_LOCK = threading.Lock()
_MAX_PIPELINE_STATES = 500
_MAX_LOGS_PER_USER = 200


def _prune_pipeline_states_locked() -> None:
    """Evict oldest idle pipeline states and log buffers when capacity exceeds limits."""
    if len(_USER_PIPELINE_STATES) > _MAX_PIPELINE_STATES:
        # Filter non-running states first for eviction
        idle_keys = [k for k, v in _USER_PIPELINE_STATES.items() if not v.get("running") and k != "anonymous"]
        excess = len(_USER_PIPELINE_STATES) - _MAX_PIPELINE_STATES
        for k in idle_keys[:excess]:
            _USER_PIPELINE_STATES.pop(k, None)
            _USER_LOG_BUFFERS.pop(k, None)


def get_user_pipeline_state(email: Optional[str]) -> dict:
    """Retrieve thread-safe pipeline execution state for a specific user."""
    key = (email or "anonymous").lower().strip()
    with _PIPELINE_LOCK:
        if key not in _USER_PIPELINE_STATES:
            _USER_PIPELINE_STATES[key] = {
                "running": False,
                "step": "idle",
                "message": "System ready. Click 'Run Job Hunt Now' to start scanning.",
                "last_run": None,
                "exit_code": 0,
            }
        return dict(_USER_PIPELINE_STATES[key])


def set_user_pipeline_state(email: Optional[str], **kwargs) -> dict:
    """Update thread-safe pipeline execution state for a specific user."""
    key = (email or "anonymous").lower().strip()
    with _PIPELINE_LOCK:
        if key not in _USER_PIPELINE_STATES:
            _prune_pipeline_states_locked()
            _USER_PIPELINE_STATES[key] = {
                "running": False,
                "step": "idle",
                "message": "System ready. Click 'Run Job Hunt Now' to start scanning.",
                "last_run": None,
                "exit_code": 0,
            }
        _USER_PIPELINE_STATES[key].update(kwargs)
        return dict(_USER_PIPELINE_STATES[key])


def publish_user_pipeline_log(email: Optional[str], message: str) -> None:
    """Append a real-time log event to user's circular log stream buffer."""
    if not message:
        return
    key = (email or "anonymous").lower().strip()
    with _PIPELINE_LOCK:
        if key not in _USER_LOG_BUFFERS:
            _USER_LOG_BUFFERS[key] = []
        buf = _USER_LOG_BUFFERS[key]
        buf.append(message)
        if len(buf) > _MAX_LOGS_PER_USER:
            _USER_LOG_BUFFERS[key] = buf[-_MAX_LOGS_PER_USER:]


def get_user_pipeline_logs(email: Optional[str]) -> list[str]:
    """Retrieve snapshot of current pipeline logs for user."""
    key = (email or "anonymous").lower().strip()
    with _PIPELINE_LOCK:
        return list(_USER_LOG_BUFFERS.get(key, []))


def clear_user_pipeline_logs(email: Optional[str]) -> None:
    """Clear circular log stream buffer for user."""
    key = (email or "anonymous").lower().strip()
    with _PIPELINE_LOCK:
        _USER_LOG_BUFFERS[key] = []


def get_store_version(st: Store) -> str:
    """Generate a deterministic fast hash/version token representing current store state."""
    try:
        items = [
            f"{jid}:{d.get('applied', False)}:{d.get('application_stage', '')}:{d.get('score', '')}:{d.get('notes', '')}:{d.get('first_seen', '')}"
            for jid, d in sorted(st.data.items())
        ]
        content = f"{len(st.data)}|" + "|".join(items)
        return hashlib.md5(content.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return str(int(time.time()))

