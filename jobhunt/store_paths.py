"""Filesystem path resolution, URL sanitization, and atomic replace helpers for Store."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import time
import urllib.parse
from pathlib import Path

logger = logging.getLogger(__name__)

_WRITABLE_DIR_CACHE: set[Path] = set()


def sanitize_job_url(
    url: str | None,
    ats: str = "",
    job_id: str = "",
    company: str = "",
    title: str = "",
) -> str:
    """Ensure every job has a valid, working HTTP/HTTPS apply URL."""
    clean = (url or "").strip()
    if clean and clean != "#":
        if clean.startswith(("http://", "https://")):
            return clean
        if "." in clean and not clean.startswith(("/", "#", "javascript:")):
            return f"https://{clean}"

    effective_id = job_id or ""
    if ":" in effective_id:
        parts = effective_id.split(":", 2)
        ats_name = (ats or parts[0]).lower()
        slug = parts[1] if len(parts) > 1 else ""
        raw_id = parts[2] if len(parts) > 2 else ""

        if ats_name == "greenhouse" and slug and raw_id:
            return f"https://boards.greenhouse.io/{slug}/jobs/{raw_id}"
        elif ats_name == "lever" and slug and raw_id:
            return f"https://jobs.lever.co/{slug}/{raw_id}"
        elif ats_name == "ashby" and slug and raw_id:
            return f"https://jobs.ashbyhq.com/{slug}/{raw_id}"
        elif ats_name == "workable" and slug and raw_id:
            return f"https://apply.workable.com/{slug}/j/{raw_id}/"
        elif ats_name == "smartrecruiters" and slug and raw_id:
            return f"https://jobs.smartrecruiters.com/{slug}/{raw_id}"
        elif ats_name == "bamboohr" and slug and raw_id:
            return f"https://{slug}.bamboohr.com/careers/{raw_id}"
        elif ats_name == "recruitee" and slug and raw_id:
            return f"https://{slug}.recruitee.com/o/{raw_id}"
        elif ats_name in ("breezy", "breezyhr") and slug and raw_id:
            return f"https://{slug}.breezy.hr/p/{raw_id}"
        elif ats_name == "pinpoint" and slug and raw_id:
            return f"https://{slug}.pinpoint.work/en/postings/{raw_id}"

    query = f"{company} {title}".strip()
    if not query:
        query = "software engineering"
    full_query = f"{query} jobs apply"
    return f"https://www.google.com/search?q={urllib.parse.quote_plus(full_query)}"


def get_writable_path(path: str | Path) -> Path:
    """Resolve a path that is writable in read-only environments (like Vercel serverless)."""
    target = Path(path)
    is_vercel = os.environ.get("VERCEL") == "1"

    if is_vercel:
        tmp_dir = Path(tempfile.gettempdir()) / "jobhunt"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir / target.name

    parent = target.parent if target.parent != Path(".") else Path.cwd()

    if parent in _WRITABLE_DIR_CACHE:
        return target

    parent_writable = True
    try:
        parent.mkdir(parents=True, exist_ok=True)
        test_file = parent / ".writable_test"
        test_file.touch()
        test_file.unlink()
        parent_writable = True
    except (PermissionError, OSError):
        parent_writable = False

    if parent_writable:
        _WRITABLE_DIR_CACHE.add(parent)
        return target
    else:
        tmp_dir = Path(tempfile.gettempdir()) / "jobhunt"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        return tmp_dir / target.name


def get_user_profile_path(path: str | Path, user_email: str | None) -> Path:
    """Return a profile cache path isolated to one authenticated user."""
    target = Path(path)
    if not user_email:
        return get_writable_path(target)
    user_hash = hashlib.md5(user_email.strip().lower().encode("utf-8")).hexdigest()[:12]
    scoped_name = f"{target.stem}_{user_hash}{target.suffix}"
    return get_writable_path(target.with_name(scoped_name))


def _atomic_replace(src: Path, dst: Path, retries: int = 4, delay: float = 0.05) -> None:
    """Safely replace dst with src, retrying transient Windows file locks."""
    for attempt in range(retries):
        try:
            os.replace(src, dst)
            return
        except OSError:
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                try:
                    dst.write_bytes(src.read_bytes())
                    src.unlink(missing_ok=True)
                except Exception:
                    os.replace(src, dst)
