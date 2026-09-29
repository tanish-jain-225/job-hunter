"""Ashby ATS parser."""

from __future__ import annotations

from typing import Any
from .models import Job
from .registry import register_ats
from .utils import strip_html, extract_salary_hint


@register_ats("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
def parse_ashby(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    jobs_list = (
        (body.get("jobPostings") or body.get("jobs") or [])
        if isinstance(body, dict)
        else (body if isinstance(body, list) else [])
    )
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
        try:
            if j.get("isListed") is False:
                continue
            comp = j.get("compensation") or {}
            salary = None
            if isinstance(comp, dict):
                summary = comp.get("compensationTierSummary") or comp.get("summaryComponents")
                if isinstance(summary, str):
                    salary = summary
            jid = j.get("id")
            raw_url = j.get("jobUrl") or j.get("applyUrl")
            url = (
                raw_url
                if raw_url and str(raw_url).startswith(("http://", "https://"))
                else f"https://jobs.ashbyhq.com/{slug}/{jid}"
            )
            loc_val = j.get("location")
            if isinstance(loc_val, dict):
                loc_val = loc_val.get("name") or loc_val.get("location") or ""
            title = (j.get("title") or "").strip()
            desc = (j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")) or "").strip()
            salary = salary or extract_salary_hint(title, desc)
            out.append(
                Job(
                    job_id=f"ashby:{slug}:{jid}",
                    ats="ashby",
                    company=company,
                    title=title,
                    location=str(loc_val or "").strip(),
                    url=url,
                    description=desc,
                    posted_at=j.get("publishedAt") or j.get("publishedDate"),
                    salary=salary,
                )
            )
        except Exception:
            continue
    return out
