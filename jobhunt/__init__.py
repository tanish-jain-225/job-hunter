"""jobhunt: Personal job-search agent."""
from __future__ import annotations

from .fetch import Job, fetch_all, fetch_board
from .prefilter import prefilter
from .store import Store

__version__ = "1.0.0"
__all__ = ["Job", "fetch_all", "fetch_board", "prefilter", "Store", "__version__"]
