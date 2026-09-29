"""Workable ATS parser."""

from __future__ import annotations

from typing import Any
from .models import Job
from .registry import register_ats
from .utils import strip_html, extract_salary_hint


@register_ats("workable", "https://apply.workable.com/api/v1/widget/accounts/{slug}")
def parse_workable(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    jobs_list = (
        (body.get("results") or body.get("jobs") or [])
        if isinstance(body, dict)
        else (body if isinstance(body, list) else [])
    )
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
        try:
            loc = j.get("location") or {}
            loc_str = (
                loc.get("city") or loc.get("country") or j.get("location_str") or ""
                if isinstance(loc, dict)
                else str(loc or "")
            )
            shortcode = j.get("shortcode") or j.get("id")
            raw_url = j.get("url") or j.get("application_url")
            url = (
                raw_url
                if raw_url and str(raw_url).startswith(("http://", "https://"))
                else f"https://apply.workable.com/{slug}/j/{shortcode}/"
            )
            title = (j.get("title") or "").strip()
            desc = strip_html(j.get("description"))
            salary = extract_salary_hint(title, desc)
            out.append(
                Job(
                    job_id=f"workable:{slug}:{shortcode}",
                    ats="workable",
                    company=company,
                    title=title,
                    location=str(loc_str).strip(),
                    url=url,
                    description=desc,
                    posted_at=j.get("published") or j.get("created_at") or j.get("published_on"),
                    salary=salary,
                )
            )
        except Exception:
            continue
    return out
