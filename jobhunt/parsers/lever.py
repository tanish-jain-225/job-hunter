"""Lever ATS parser."""

from __future__ import annotations

import time
from typing import Any
from .models import Job
from .registry import register_ats
from .utils import strip_html, extract_salary_hint


@register_ats("lever", "https://api.lever.co/v0/postings/{slug}?mode=json")
def parse_lever(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    jobs_list = body if isinstance(body, list) else (body.get("data") or [] if isinstance(body, dict) else [])
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
        try:
            cats = j.get("categories") or {}
            chunks = [j.get("descriptionPlain") or strip_html(j.get("description"))]
            for lst in j.get("lists") or []:
                if isinstance(lst, dict):
                    chunks.append(str(lst.get("text") or ""))
                    chunks.append(strip_html(lst.get("content")))
            chunks.append(j.get("additionalPlain") or strip_html(j.get("additional")))
            ts = j.get("createdAt")
            posted = None
            if isinstance(ts, (int, float)):
                try:
                    if ts > 0:
                        posted = time.strftime("%Y-%m-%d", time.gmtime(ts / 1000))
                except (ValueError, OSError, OverflowError):
                    posted = None
            jid = j.get("id")
            raw_url = j.get("hostedUrl") or j.get("applyUrl")
            url = (
                raw_url
                if raw_url and str(raw_url).startswith(("http://", "https://"))
                else f"https://jobs.lever.co/{slug}/{jid}"
            )
            loc_val = cats.get("location") if isinstance(cats, dict) else str(cats or "")
            title = (j.get("text") or "").strip()
            desc = "\n\n".join(c for c in chunks if c).strip()
            salary = extract_salary_hint(title, desc)
            out.append(
                Job(
                    job_id=f"lever:{slug}:{jid}",
                    ats="lever",
                    company=company,
                    title=title,
                    location=str(loc_val or "").strip(),
                    url=url,
                    description=desc,
                    posted_at=posted,
                    salary=salary,
                )
            )
        except Exception:
            continue
    return out
