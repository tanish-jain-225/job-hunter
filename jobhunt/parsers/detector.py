"""Automatic ATS platform and company slug detection from URL."""

from __future__ import annotations

from urllib.parse import urlparse


def detect_ats_from_url(url: str) -> dict[str, str] | None:
    """Auto-detect ATS engine and extract slug/name from an arbitrary career board URL.

    Supported engines:
    - Greenhouse: boards.greenhouse.io/{slug}, boards-api.greenhouse.io/v1/boards/{slug}, job-boards.greenhouse.io/{slug}
    - Lever: jobs.lever.co/{slug}, api.lever.co/v0/postings/{slug}
    - Ashby: jobs.ashbyhq.com/{slug}, api.ashbyhq.com/posting-api/job-board/{slug}
    - Workable: apply.workable.com/{slug}, {slug}.workable.com
    - SmartRecruiters: jobs.smartrecruiters.com/{slug}, careers.smartrecruiters.com/{slug}
    - BambooHR: {slug}.bamboohr.com
    - Recruitee: {slug}.recruitee.com, careers.recruitee.com/{slug}
    - Breezy HR: {slug}.breezy.hr
    - Pinpoint: {slug}.pinpoint.work, {slug}.pinpointhq.com
    """
    if not url or not isinstance(url, str):
        return None

    raw = url.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw

    parsed = urlparse(raw)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.strip("/")
    path_segments = [p for p in path.split("/") if p]

    # 1. Greenhouse
    if "greenhouse.io" in hostname:
        slug = ""
        if path_segments:
            if path_segments[0] == "v1" and len(path_segments) >= 3 and path_segments[1] == "boards":
                slug = path_segments[2]
            elif path_segments[0] in ("boards", "job-boards") and len(path_segments) >= 2:
                slug = path_segments[1]
            else:
                slug = path_segments[0]
        if slug:
            return {"ats": "greenhouse", "slug": slug, "name": slug.replace("-", " ").replace("_", " ").title()}

    # 2. Lever
    if "lever.co" in hostname:
        slug = ""
        if path_segments:
            if path_segments[0] == "v0" and len(path_segments) >= 3 and path_segments[1] == "postings":
                slug = path_segments[2]
            else:
                slug = path_segments[0]
        if slug:
            return {"ats": "lever", "slug": slug, "name": slug.replace("-", " ").replace("_", " ").title()}

    # 3. Ashby
    if "ashbyhq.com" in hostname:
        slug = ""
        if path_segments:
            if path_segments[0] == "posting-api" and len(path_segments) >= 3 and path_segments[1] == "job-board":
                slug = path_segments[2]
            else:
                slug = path_segments[0]
        if slug:
            return {"ats": "ashby", "slug": slug, "name": slug.replace("-", " ").replace("_", " ").title()}

    # 4. Workable
    if "workable.com" in hostname:
        slug = ""
        if hostname.startswith("apply.workable.com") and path_segments:
            slug = path_segments[0]
        else:
            subdomain = hostname.split(".")[0]
            if subdomain and subdomain != "apply" and subdomain != "www":
                slug = subdomain
        if slug:
            return {"ats": "workable", "slug": slug, "name": slug.replace("-", " ").replace("_", " ").title()}

    # 5. SmartRecruiters
    if "smartrecruiters.com" in hostname:
        slug = ""
        if path_segments:
            if path_segments[0] == "v1" and len(path_segments) >= 3 and path_segments[1] == "companies":
                slug = path_segments[2]
            else:
                slug = path_segments[0]
        if slug:
            return {"ats": "smartrecruiters", "slug": slug, "name": slug.replace("-", " ").replace("_", " ").title()}

    # 6. BambooHR
    if "bamboohr.com" in hostname:
        slug = hostname.split(".")[0]
        if slug and slug != "www":
            return {"ats": "bamboohr", "slug": slug, "name": slug.replace("-", " ").replace("_", " ").title()}

    # 7. Recruitee
    if "recruitee.com" in hostname:
        slug = ""
        if hostname.startswith("careers.recruitee.com") and path_segments:
            slug = path_segments[0]
        else:
            subdomain = hostname.split(".")[0]
            if subdomain and subdomain != "careers" and subdomain != "www":
                slug = subdomain
        if slug:
            return {"ats": "recruitee", "slug": slug, "name": slug.replace("-", " ").replace("_", " ").title()}

    # 8. Breezy HR
    if "breezy.hr" in hostname:
        slug = hostname.split(".")[0]
        if slug and slug != "www":
            return {"ats": "breezy", "slug": slug, "name": slug.replace("-", " ").replace("_", " ").title()}

    # 9. Pinpoint
    if "pinpoint.work" in hostname or "pinpointhq.com" in hostname:
        slug = hostname.split(".")[0]
        if slug and slug != "www":
            return {"ats": "pinpoint", "slug": slug, "name": slug.replace("-", " ").replace("_", " ").title()}

    return None
