"""Greenhouse ATS parser."""

from __future__ import annotations

from typing import Any
from .models import Job
from .registry import register_ats
from .utils import strip_html, extract_salary_hint


@register_ats("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
def parse_greenhouse(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    jobs_list = (body.get("jobs") or []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
        try:
            loc = j.get("location") or {}
            loc_name = loc.get("name") if isinstance(loc, dict) else str(loc or "")
            jid = j.get("id")
            raw_url = j.get("absolute_url")
            url = (
                raw_url
                if raw_url and str(raw_url).startswith(("http://", "https://"))
                else f"https://boards.greenhouse.io/{slug}/jobs/{jid}"
            )
            title = (j.get("title") or "").strip()
            desc = strip_html(j.get("content"))
            salary = extract_salary_hint(title, desc)
            out.append(
                Job(
                    job_id=f"greenhouse:{slug}:{jid}",
                    ats="greenhouse",
                    company=company,
                    title=title,
                    location=str(loc_name or "").strip(),
                    url=url,
                    description=desc,
                    posted_at=j.get("updated_at") or j.get("first_published"),
                    salary=salary,
                )
            )
        except Exception:
            continue
    return out
