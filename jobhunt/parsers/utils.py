"""Text processing, compensation extraction, and SSRF security utilities for ATS parsers."""

from __future__ import annotations

import html
import ipaddress
import re
from typing import Any
from urllib.parse import urlparse

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


def strip_html(raw: str | Any | None) -> str:
    """Strip HTML tags and normalize whitespace in job descriptions."""
    if not raw:
        return ""
    if not isinstance(raw, str):
        raw = str(raw)
    text = html.unescape(raw)
    text = re.sub(r"<\s*(br|/p|/div|/li|/h[1-6])\s*/?>", "\n", text, flags=re.I)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = _WS.sub(" ", text)
    text = _NL.sub("\n\n", text)
    return text.strip()


_SALARY_PATTERNS = [
    re.compile(r"(\b\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?\s*(?:LPA|lpa|Lakh|lakhs|Lac|lacs)\b)", re.I),
    re.compile(
        r"(₹\s*[\d,]+(?:\s*(?:k|K))?(?:\s*-\s*₹?\s*[\d,]+(?:\s*(?:k|K))?)?(?:\s*\/\s*(?:mo|month|yr|year|annum))?)",
        re.I,
    ),
    re.compile(
        r"([€$]\s*[\d,]+(?:\s*[kK])?(?:\s*-\s*[€$]?\s*[\d,]+(?:\s*[kK])?)?(?:\s*\/\s*(?:yr|year|hr|hour))?)",
        re.I,
    ),
    re.compile(r"(\b\d{2,3}k\s*-\s*\d{2,3}k\b)", re.I),
]


def extract_salary_hint(title: str = "", description: str = "") -> str | None:
    """Extract salary or compensation string from job title or description preview."""
    for text in (title, description[:600] if description else ""):
        if not text:
            continue
        for pat in _SALARY_PATTERNS:
            m = pat.search(text)
            if m:
                return m.group(1).strip()
    return None


_VALID_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


def is_valid_slug(slug: str | None) -> bool:
    """Validate ATS board slug to prevent path traversal, host injection, and SSRF."""
    if not slug or not isinstance(slug, str):
        return False
    clean = slug.strip()
    if not clean or ".." in clean:
        return False
    return bool(_VALID_SLUG_RE.match(clean))


def is_safe_url(url: str) -> bool:
    """Validate external URLs to prevent SSRF against private/loopback/link-local networks."""
    if not url or not isinstance(url, str):
        return False
    try:
        p = urlparse(url.strip())
        if p.scheme.lower() not in ("http", "https"):
            return False
        if p.username is not None or p.password is not None:
            return False
        hostname = p.hostname
        if not hostname:
            return False
        # Block localhost aliases
        lower_host = hostname.lower().rstrip(".")
        if lower_host in ("localhost", "127.0.0.1", "::1", "0.0.0.0", "metadata.google.internal"):
            return False
        # If it is an IP address, check against private and reserved CIDRs (including IPv4-mapped IPv6)
        try:
            ip = ipaddress.ip_address(lower_host)
            ip_v4 = getattr(ip, "ipv4_mapped", None)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
            if ip_v4 and (ip_v4.is_private or ip_v4.is_loopback or ip_v4.is_link_local or ip_v4.is_reserved or ip_v4.is_multicast):
                return False
        except ValueError:
            # Domain name: verify it doesn't end with local domain patterns
            if lower_host.endswith((".local", ".localhost", ".internal", ".arpa")):
                return False
        return True
    except Exception:
        return False
