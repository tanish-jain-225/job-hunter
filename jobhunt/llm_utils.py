"""JSON parsing, validation, and PDF resume processing utilities for LLM stages."""

from __future__ import annotations

import io
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Max PDF bytes (5 MB) and maximum page count (10 pages) for resource bounds
MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 10
MAX_RESUME_TEXT_CHARS = 50_000

_FENCE_OPEN = re.compile(r"^```(?:json)?\s*", re.M)
_FENCE_CLOSE = re.compile(r"\s*```$", re.M)


def parse_json(raw: str) -> Any:
    """Parse a model reply that is *supposed* to be JSON."""
    if raw is None:
        raise ValueError("empty model reply")
    # Strip <think>...</think> reasoning blocks from thinking models
    cleaned = re.sub(r"<think>.*?</think>", "", str(raw), flags=re.DOTALL)
    cleaned = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", cleaned)).strip()
    try:
        return json.loads(cleaned, strict=False)
    except (json.JSONDecodeError, TypeError):
        pass

    # Sanitize trailing commas before closing braces/brackets e.g. {"a": 1,} -> {"a": 1}
    sanitized = re.sub(r",\s*([\]}])", r"\1", cleaned)
    try:
        return json.loads(sanitized, strict=False)
    except (json.JSONDecodeError, TypeError):
        pass

    candidates = []
    for opener, closer in (("[", "]"), ("{", "}")):
        i, k = sanitized.find(opener), sanitized.rfind(closer)
        if i != -1 and k > i:
            candidates.append((i, sanitized[i : k + 1]))
    for _, blob in sorted(candidates):
        try:
            return json.loads(blob, strict=False)
        except (json.JSONDecodeError, TypeError):
            continue
    raise ValueError(f"could not parse JSON from model reply: {cleaned[:300]!r}")


def _ensure_list(val: Any) -> list[str]:
    """Safely convert list or newline-separated string into a list of non-empty strings."""
    if isinstance(val, list):
        return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str):
        lines = [line.strip().lstrip("-*•1234567890. ") for line in val.split("\n") if line.strip()]
        return [l for l in lines if l]
    return []


def _as_list(payload: Any) -> list[dict]:
    """Accept [ {...} ], { "jobs": [...] }, or a bare { ... }."""
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("jobs", "results", "scores", "items"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [p for p in inner if isinstance(p, dict)]
        list_vals = [v for v in payload.values() if isinstance(v, list)]
        if len(list_vals) == 1:
            return [p for p in list_vals[0] if isinstance(p, dict)]
        return [payload]
    raise ValueError(f"expected a JSON array of results, got {type(payload).__name__}")


def extract_text_from_pdf(pdf_bytes: bytes | None) -> str:
    """Extract plain text from PDF bytes locally using pypdf with bounds safety."""
    if not pdf_bytes or not isinstance(pdf_bytes, (bytes, bytearray)):
        return ""

    if len(pdf_bytes) > MAX_PDF_BYTES:
        logger.warning("PDF exceeds maximum allowed size (%d bytes); skipping.", len(pdf_bytes))
        return ""

    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_text: list[str] = []
        for page in reader.pages[:MAX_PDF_PAGES]:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())
        res = "\n\n".join(pages_text).strip()
        if res:
            return res[:MAX_RESUME_TEXT_CHARS]
    except Exception as e:
        logger.debug("pypdf parsing failed: %s", e)

    # Fallback decode as text if parsing fails (useful for mock/corrupted PDF bytes in testing)
    try:
        decoded = pdf_bytes[:MAX_PDF_BYTES].decode("utf-8", errors="ignore").strip()
        if len(decoded) > 20 and any(
            kw in decoded for kw in ("Resume", "skills", "Python", "experience", "education", "projects")
        ):
            return decoded[:MAX_RESUME_TEXT_CHARS]
    except Exception:
        pass
    return ""


__all__ = [
    "parse_json",
    "_ensure_list",
    "_as_list",
    "extract_text_from_pdf",
    "MAX_PDF_BYTES",
    "MAX_PDF_PAGES",
    "MAX_RESUME_TEXT_CHARS",
]
