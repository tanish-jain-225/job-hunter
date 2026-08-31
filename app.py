"""Flask Web Dashboard for Job Hunter (job-hunter).

Public Multi-Tenant AI Career Intelligence Engine WSGI Entrypoint.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobhunt.cli import _load_env

_load_env()

from jobhunt.web import (
    create_app,
    handle_exception,
    add_cache_headers,
    get_project_root as _get_project_root,
    get_current_user_context as _get_current_user_context,
    get_user_pipeline_state as _get_user_pipeline_state,
    set_user_pipeline_state as _set_user_pipeline_state,
    get_store_version as _get_store_version,
    _USER_PIPELINE_STATES,
    _PIPELINE_LOCK,
)

# Instantiate the global application instance
app = create_app()

__all__ = [
    "app",
    "create_app",
    "handle_exception",
    "add_cache_headers",
    "_get_project_root",
    "_get_current_user_context",
    "_get_user_pipeline_state",
    "_set_user_pipeline_state",
    "_get_store_version",
    "_USER_PIPELINE_STATES",
    "_PIPELINE_LOCK",
    "ROOT",
]

if __name__ == "__main__":
    import os

    print("=" * 60)
    print(" [*] Job Hunter Web Dashboard (Public Multi-Tenant Ready)")
    print(" Server running at: http://localhost:5000")
    print("=" * 60)
    is_debug = os.environ.get("FLASK_DEBUG", "0") == "1" or os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=5000, debug=is_debug)
