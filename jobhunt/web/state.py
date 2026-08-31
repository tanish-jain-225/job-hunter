"""State management, context resolution, and project root utilities for Job Hunter Web."""

from __future__ import annotations

import hashlib
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

from flask import g

from ..auth import extract_bearer_token
from ..store import Store

logger = logging.getLogger(__name__)


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


_USER_PIPELINE_STATES: dict[str, dict] = {}
_PIPELINE_LOCK = threading.Lock()
_MAX_PIPELINE_STATES = 500


def _prune_pipeline_states_locked() -> None:
    """Evict oldest idle pipeline states when capacity exceeds limits."""
    if len(_USER_PIPELINE_STATES) > _MAX_PIPELINE_STATES:
        # Filter non-running states first for eviction
        idle_keys = [k for k, v in _USER_PIPELINE_STATES.items() if not v.get("running") and k != "anonymous"]
        excess = len(_USER_PIPELINE_STATES) - _MAX_PIPELINE_STATES
        for k in idle_keys[:excess]:
            _USER_PIPELINE_STATES.pop(k, None)


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


def get_store_version(st: Store) -> str:
    """Generate a deterministic fast hash/version token representing current store state."""
    try:
        items = [
            f"{jid}:{d.get('applied', False)}:{d.get('score', '')}:{d.get('first_seen', '')}"
            for jid, d in sorted(st.data.items())
        ]
        content = f"{len(st.data)}|" + "|".join(items)
        return hashlib.md5(content.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return str(int(time.time()))
