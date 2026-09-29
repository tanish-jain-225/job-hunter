"""Recruitee ATS parser."""

from __future__ import annotations

from typing import Any
from .models import Job
from .registry import register_ats
from .utils import strip_html, extract_salary_hint


@register_ats("recruitee", "https://{slug}.recruitee.com/api/offers/")
def parse_recruitee(slug: str, company: str, body: Any) -> list[Job]:
    out: list[Job] = []
    offers = (body.get("offers") or []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    for j in offers:
        if not isinstance(j, dict):
            continue
        try:
            jid = j.get("id")
            loc_str = (
                j.get("location")
                or j.get("city")
                or j.get("country")
                or ("Remote" if j.get("remote") else "Unspecified")
            )
            raw_url = j.get("careers_url") or j.get("url")
            url = (
                raw_url
                if raw_url and str(raw_url).startswith(("http://", "https://"))
                else f"https://{slug}.recruitee.com/o/{jid}"
            )
            title = (j.get("title") or "").strip()
            desc = strip_html(j.get("description") or j.get("requirements"))
            salary = j.get("salary_range") or j.get("compensation") or extract_salary_hint(title, desc)
            out.append(
                Job(
                    job_id=f"recruitee:{slug}:{jid}",
                    ats="recruitee",
                    company=company,
                    title=title,
                    location=str(loc_str).strip(),
                    url=url,
                    description=desc,
                    posted_at=j.get("created_at") or j.get("published_at"),
                    salary=salary,
                )
            )
        except Exception:
            continue
    return out
