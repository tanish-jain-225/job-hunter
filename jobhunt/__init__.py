"""jobhunt: Autonomous AI-Powered Career Intelligence & Job Hunting Agent."""
from __future__ import annotations

from . import digest, llm, memory, providers, store
from .fetch import Job, fetch_all, fetch_board
from .memory import SupabaseMemory
from .multi import run_multi_user_pipeline
from .prefilter import prefilter
from .store import Store
from .web import create_app

__version__ = "1.0.0"
__all__ = [
    "Job",
    "Store",
    "SupabaseMemory",
    "create_app",
    "digest",
    "fetch_all",
    "fetch_board",
    "llm",
    "memory",
    "prefilter",
    "providers",
    "run_multi_user_pipeline",
    "store",
    "__version__",
]
