"""Centralized registry for ATS board parsers."""

from __future__ import annotations

import warnings
from typing import Callable
from .models import ParserFunc

REGISTERED_ATS: dict[str, tuple[str, ParserFunc]] = {}


def register_ats(name: str, url_template: str) -> Callable[[ParserFunc], ParserFunc]:
    """Decorator to register an ATS board parser."""

    def decorator(func: ParserFunc) -> ParserFunc:
        lower = name.lower()
        if lower in REGISTERED_ATS:
            existing_fn = REGISTERED_ATS[lower][1]
            if existing_fn is not func:
                warnings.warn(
                    f"ATS '{lower}' already registered by {existing_fn.__name__!r}; "
                    f"overwriting with {func.__name__!r}. "
                    f"Use an intentional alias if this is expected.",
                    stacklevel=2,
                )
        REGISTERED_ATS[lower] = (url_template, func)
        return func

    return decorator
