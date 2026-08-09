"""jobhunt: Personal job-search agent."""
from __future__ import annotations

from . import digest, llm, store
from .fetch import Job, fetch_all, fetch_board
from .prefilter import prefilter
from .store import Store

__version__ = "1.0.0"
__all__ = [
    "Job",
    "Store",
    "digest",
    "fetch_all",
    "fetch_board",
    "llm",
    "prefilter",
    "store",
    "__version__",
]
