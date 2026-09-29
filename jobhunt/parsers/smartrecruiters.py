"""SmartRecruiters ATS parser."""

from __future__ import annotations

from typing import Any
from .models import Job
from .registry import register_ats
from .utils import strip_html, extract_salary_hint


@register_ats("smartrecruiters", "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100")
def parse_smartrecruiters(slug: str, company: str, body: Any) -> list[Job]:
    out: list[Job] = []
    jobs_list: list[Any] = []
    if isinstance(body, dict) and isinstance(body.get("content"), list):
        jobs_list = body["content"]
    elif isinstance(body, list):
        jobs_list = body
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
        try:
            loc = j.get("location") or {}
            loc_str = loc.get("city") or loc.get("country") or "" if isinstance(loc, dict) else str(loc or "")
            jid = j.get("id")
            ad = j.get("jobAd") or {}
            raw_url = (j.get("applyUrl") or ad.get("applyUrl")) if isinstance(ad, dict) else j.get("applyUrl")
            url = (
                raw_url
                if raw_url and str(raw_url).startswith(("http://", "https://"))
                else f"https://jobs.smartrecruiters.com/{slug}/{jid}"
            )
            desc_raw = None
            if isinstance(ad, dict):
                sections = ad.get("sections")
                if isinstance(sections, dict):
                    jd_sec = sections.get("jobDescription")
                    if isinstance(jd_sec, dict):
                        desc_raw = jd_sec.get("text")
            title = (j.get("name") or j.get("title") or "").strip()
            desc = strip_html(desc_raw)
            salary = extract_salary_hint(title, desc)
            out.append(
                Job(
                    job_id=f"smartrecruiters:{slug}:{jid}",
                    ats="smartrecruiters",
                    company=company,
                    title=title,
                    location=str(loc_str).strip(),
                    url=url,
                    description=desc,
                    posted_at=j.get("releasedDate") or j.get("createdOn"),
                    salary=salary,
                )
            )
        except Exception:
            continue
    return out
