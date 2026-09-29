"""BambooHR ATS parser."""

from __future__ import annotations

from typing import Any
from .models import Job
from .registry import register_ats
from .utils import strip_html, extract_salary_hint


@register_ats("bamboohr", "https://{slug}.bamboohr.com/careers/list")
def parse_bamboohr(slug: str, company: str, body: Any) -> list[Job]:
    out: list[Job] = []
    jobs_list = (
        (body.get("result") or body.get("jobs") or [])
        if isinstance(body, dict)
        else (body if isinstance(body, list) else [])
    )
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
        try:
            jid = j.get("id") or j.get("jobOpeningId")
            loc = j.get("location") or {}
            if isinstance(loc, dict):
                loc_parts = [loc.get("city"), loc.get("state")]
                loc_str = ", ".join(p for p in loc_parts if p) or "Remote/Unspecified"
            else:
                loc_str = str(loc or "Remote/Unspecified")
            url = f"https://{slug}.bamboohr.com/careers/{jid}"
            title = (j.get("jobOpeningName") or j.get("title") or "").strip()
            desc = strip_html(j.get("description") or j.get("jobDescription"))
            salary = extract_salary_hint(title, desc)
            out.append(
                Job(
                    job_id=f"bamboohr:{slug}:{jid}",
                    ats="bamboohr",
                    company=company,
                    title=title,
                    location=str(loc_str).strip(),
                    url=url,
                    description=desc,
                    posted_at=j.get("datePosted") or j.get("postedDate"),
                    salary=salary,
                )
            )
        except Exception:
            continue
    return out
