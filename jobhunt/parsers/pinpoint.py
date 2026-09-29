"""Pinpoint ATS parser."""

from __future__ import annotations

from typing import Any
from .models import Job
from .registry import register_ats
from .utils import strip_html, extract_salary_hint


@register_ats("pinpoint", "https://{slug}.pinpoint.work/en/postings.json")
def parse_pinpoint(slug: str, company: str, body: Any) -> list[Job]:
    out: list[Job] = []
    data_list = (
        (body.get("data") or body.get("jobs") or [])
        if isinstance(body, dict)
        else (body if isinstance(body, list) else [])
    )
    for j in data_list:
        if not isinstance(j, dict):
            continue
        try:
            jid = j.get("id")
            loc = j.get("location") or {}
            loc_str = (
                loc.get("city") or loc.get("country") or j.get("location_name")
                if isinstance(loc, dict)
                else str(loc or "")
            )
            if not loc_str:
                loc_str = "Remote" if j.get("workplace_type") == "remote" else "Unspecified"
            raw_url = j.get("url")
            url = (
                raw_url
                if raw_url and str(raw_url).startswith(("http://", "https://"))
                else f"https://{slug}.pinpoint.work/en/postings/{jid}"
            )
            title = (j.get("title") or "").strip()
            desc = strip_html(j.get("description") or j.get("summary") or j.get("body"))
            salary = j.get("salary_range") or j.get("compensation") or extract_salary_hint(title, desc)
            out.append(
                Job(
                    job_id=f"pinpoint:{slug}:{jid}",
                    ats="pinpoint",
                    company=company,
                    title=title,
                    location=str(loc_str).strip(),
                    url=url,
                    description=desc,
                    posted_at=j.get("published_at") or j.get("created_at"),
                    salary=salary,
                )
            )
        except Exception:
            continue
    return out
