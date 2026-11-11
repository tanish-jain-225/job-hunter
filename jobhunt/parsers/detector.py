"""Automatic ATS platform and company slug detection from URL."""

from __future__ import annotations

from urllib.parse import urlparse

from .utils import is_valid_slug


def _host_matches(hostname: str, domain: str) -> bool:
    """Strictly match exact domain or subdomain without allowing lookalike substring attacks."""
    return hostname == domain or hostname.endswith(f".{domain}")


def _result(ats: str, slug: str) -> dict[str, str] | None:
    if not is_valid_slug(slug):
        return None
    clean_slug = slug.strip()
    return {"ats": ats, "slug": clean_slug, "name": clean_slug.replace("-", " ").replace("_", " ").title()}


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
    if parsed.username is not None or parsed.password is not None:
        return None
    hostname = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path.strip("/")
    path_segments = [p for p in path.split("/") if p]

    # 1. Greenhouse
    if _host_matches(hostname, "greenhouse.io"):
        slug = ""
        if path_segments:
            if path_segments[0] == "v1" and len(path_segments) >= 3 and path_segments[1] == "boards":
                slug = path_segments[2]
            elif path_segments[0] in ("boards", "job-boards") and len(path_segments) >= 2:
                slug = path_segments[1]
            else:
                slug = path_segments[0]
        return _result("greenhouse", slug)

    # 2. Lever
    if _host_matches(hostname, "lever.co"):
        slug = ""
        if path_segments:
            if path_segments[0] == "v0" and len(path_segments) >= 3 and path_segments[1] == "postings":
                slug = path_segments[2]
            else:
                slug = path_segments[0]
        return _result("lever", slug)

    # 3. Ashby
    if _host_matches(hostname, "ashbyhq.com"):
        slug = ""
        if path_segments:
            if path_segments[0] == "posting-api" and len(path_segments) >= 3 and path_segments[1] == "job-board":
                slug = path_segments[2]
            else:
                slug = path_segments[0]
        return _result("ashby", slug)

    # 4. Workable
    if _host_matches(hostname, "workable.com"):
        slug = ""
        if hostname == "apply.workable.com" and path_segments:
            slug = path_segments[0]
        else:
            subdomain = hostname.split(".")[0]
            if subdomain and subdomain not in ("apply", "www"):
                slug = subdomain
        return _result("workable", slug)

    # 5. SmartRecruiters
    if _host_matches(hostname, "smartrecruiters.com"):
        slug = ""
        if path_segments:
            if path_segments[0] == "v1" and len(path_segments) >= 3 and path_segments[1] == "companies":
                slug = path_segments[2]
            else:
                slug = path_segments[0]
        return _result("smartrecruiters", slug)

    # 6. BambooHR
    if _host_matches(hostname, "bamboohr.com"):
        slug = hostname.split(".")[0]
        if slug and slug != "www":
            return _result("bamboohr", slug)

    # 7. Recruitee
    if _host_matches(hostname, "recruitee.com"):
        slug = ""
        if hostname == "careers.recruitee.com" and path_segments:
            slug = path_segments[0]
        else:
            subdomain = hostname.split(".")[0]
            if subdomain and subdomain not in ("careers", "www"):
                slug = subdomain
        return _result("recruitee", slug)

    # 8. Breezy HR
    if _host_matches(hostname, "breezy.hr"):
        slug = hostname.split(".")[0]
        if slug and slug != "www":
            return _result("breezy", slug)

    # 9. Pinpoint
    if _host_matches(hostname, "pinpoint.work") or _host_matches(hostname, "pinpointhq.com"):
        slug = hostname.split(".")[0]
        if slug and slug != "www":
            return _result("pinpoint", slug)

    return None
