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

_THINK_BLOCKS = re.compile(
    r"<(?:think|thought|thinking)>.*?</(?:think|thought|thinking)>",
    flags=re.DOTALL | re.IGNORECASE,
)
_FENCE_OPEN = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*", re.M)
_FENCE_CLOSE = re.compile(r"\s*```\s*$", re.M)


def strip_json_comments(text: str) -> str:
    """Safely strip single-line // and multi-line /* */ comments outside JSON string literals."""
    out: list[str] = []
    in_str = False
    esc = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
        else:
            if c == '"':
                in_str = True
                out.append(c)
                i += 1
            elif c == "/" and i + 1 < n and text[i + 1] == "/":
                i += 2
                while i < n and text[i] != "\n":
                    i += 1
            elif c == "/" and i + 1 < n and text[i + 1] == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
            else:
                out.append(c)
                i += 1
    return "".join(out)


def repair_truncated_json(text: str) -> Any | None:
    """Attempt to recover complete items from a truncated JSON list or object."""
    trimmed = text.strip()
    if not trimmed:
        return None

    # If it starts with [ but doesn't end with ]
    if trimmed.startswith("[") and not trimmed.endswith("]"):
        last_brace = trimmed.rfind("}")
        if last_brace != -1:
            candidate = trimmed[: last_brace + 1].strip()
            candidate = re.sub(r",\s*$", "", candidate) + "]"
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                pass

    # If it starts with { but doesn't end with }
    if trimmed.startswith("{") and not trimmed.endswith("}"):
        last_comma = trimmed.rfind(",")
        if last_comma != -1:
            candidate = trimmed[:last_comma].strip() + "}"
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                pass
        for close_attempt in ['"}', '"]}', '}', ']']:
            try:
                return json.loads(trimmed + close_attempt, strict=False)
            except Exception:
                continue

    return None


def parse_json(raw: str) -> Any:
    """Parse a model reply that is *supposed* to be JSON with maximum resilience."""
    if raw is None:
        raise ValueError("empty model reply")
    raw_str = str(raw).strip()
    if not raw_str:
        raise ValueError("empty model reply")

    # Strip <think>...</think> reasoning blocks from thinking models
    cleaned = _THINK_BLOCKS.sub("", raw_str)
    # If an opening thought tag was cut off mid-thought without closing tag, strip up to first [ or {
    if re.search(r"<(?:think|thought|thinking)>", cleaned, re.IGNORECASE):
        first_bracket = min(
            (pos for pos in (cleaned.find("["), cleaned.find("{")) if pos != -1),
            default=-1,
        )
        if first_bracket != -1:
            cleaned = cleaned[first_bracket:]

    cleaned = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", cleaned)).strip()

    # Fast path: direct valid JSON
    try:
        return json.loads(cleaned, strict=False)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strip single-line & multi-line comments and sanitize trailing commas e.g. {"a": 1,} -> {"a": 1}
    comment_stripped = strip_json_comments(cleaned)
    sanitized = re.sub(r",\s*([\]}])", r"\1", comment_stripped).strip()
    try:
        return json.loads(sanitized, strict=False)
    except (json.JSONDecodeError, TypeError):
        pass

    # If the reply was an array cut off mid-output (starts with [ but missing closing ]),
    # prioritize repairing the array so we return a list rather than an isolated inner dict.
    if sanitized.startswith("[") and not sanitized.endswith("]"):
        repaired = repair_truncated_json(sanitized)
        if repaired is not None:
            return repaired

    # Extract bracketed / braced candidate substrings
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

    # Try converting Python literals outside quotes (True -> true, False -> false, None -> null)
    py_literal_fixed = re.sub(r"\bTrue\b", "true", sanitized)
    py_literal_fixed = re.sub(r"\bFalse\b", "false", py_literal_fixed)
    py_literal_fixed = re.sub(r"\bNone\b", "null", py_literal_fixed)
    try:
        return json.loads(py_literal_fixed, strict=False)
    except (json.JSONDecodeError, TypeError):
        pass

    # Safe fallback for Python dict/list literals with single quotes
    if (sanitized.startswith("{") and sanitized.endswith("}")) or (sanitized.startswith("[") and sanitized.endswith("]")):
        import ast

        try:
            val = ast.literal_eval(sanitized)
            if isinstance(val, (dict, list)):
                return val
        except Exception:
            pass

    # Attempt truncated JSON recovery for models cut off by max output token ceilings
    repaired = repair_truncated_json(sanitized)
    if repaired is not None:
        return repaired

    raise ValueError(f"could not parse JSON from model reply: {cleaned[:300]!r}")


def _ensure_list(val: Any) -> list[str]:
    """Safely convert list or newline-separated string into a list of non-empty strings."""
    if isinstance(val, (list, tuple, set)):
        result = []
        for x in val:
            if isinstance(x, dict):
                v = x.get("text") or x.get("name") or x.get("skill") or x.get("value") or (next(iter(x.values())) if x else "")
                if str(v).strip():
                    result.append(str(v).strip())
            elif str(x).strip():
                result.append(str(x).strip())
        return result
    if isinstance(val, dict):
        return _ensure_list(list(val.values()))
    if isinstance(val, str):
        lines = [line.strip().lstrip("-*•1234567890. ") for line in val.split("\n") if line.strip()]
        if len(lines) == 1 and "," in lines[0] and not lines[0].startswith("http"):
            parts = [p.strip().lstrip("-*•1234567890. ") for p in lines[0].split(",") if p.strip()]
            if len(parts) > 1:
                return parts
        return [l for l in lines if l]
    return []


def _as_list(payload: Any) -> list[dict]:
    """Accept [ {...} ], { "jobs": [...] }, or a bare { ... }."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("jobs", "results", "scores", "items", "data", "candidates", "matches", "evaluations", "output"):
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
    "strip_json_comments",
    "repair_truncated_json",
    "_ensure_list",
    "_as_list",
    "extract_text_from_pdf",
    "MAX_PDF_BYTES",
    "MAX_PDF_PAGES",
    "MAX_RESUME_TEXT_CHARS",
]
