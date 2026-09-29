"""Breezy HR ATS parser."""

from __future__ import annotations

from typing import Any
from .models import Job
from .registry import register_ats
from .utils import strip_html, extract_salary_hint


@register_ats("breezy", "https://{slug}.breezy.hr/json")
@register_ats("breezyhr", "https://{slug}.breezy.hr/json")
def parse_breezy(slug: str, company: str, body: Any) -> list[Job]:
    out: list[Job] = []
    positions = (body.get("positions") or []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    for j in positions:
        if not isinstance(j, dict):
            continue
        try:
            jid = j.get("id") or j.get("friendly_id")
            loc = j.get("location") or {}
            loc_name = loc.get("name") if isinstance(loc, dict) else str(loc)
            if isinstance(loc, dict) and loc.get("is_remote"):
                loc_name = f"{loc_name} (Remote)" if loc_name else "Remote"
            raw_url = j.get("url")
            url = (
                raw_url
                if raw_url and str(raw_url).startswith(("http://", "https://"))
                else f"https://{slug}.breezy.hr/p/{jid}"
            )
            title = (j.get("name") or j.get("title") or "").strip()
            desc = strip_html(j.get("description") or j.get("summary"))
            salary = (
                j.get("type", {}).get("name") if isinstance(j.get("type"), dict) else None
            ) or extract_salary_hint(title, desc)
            out.append(
                Job(
                    job_id=f"breezy:{slug}:{jid}",
                    ats="breezy",
                    company=company,
                    title=title,
                    location=str(loc_name or "Remote/Unspecified").strip(),
                    url=url,
                    description=desc,
                    posted_at=j.get("published_date") or j.get("updated_at"),
                    salary=salary,
                )
            )
        except Exception:
            continue
    return out
