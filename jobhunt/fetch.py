"""Fetch jobs from public ATS APIs. No auth, no scraping, no ToS risk."""
from __future__ import annotations

import html
import re
import threading
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Iterable

import requests

UA = {"User-Agent": "jobhunt/1.0 (personal job search agent)"}
TIMEOUT = 20

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<\s*(br|/p|/div|/li|/h[1-6])\s*/?>", "\n", text, flags=re.I)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    text = _WS.sub(" ", text)
    text = _NL.sub("\n\n", text)
    return text.strip()


@dataclass
class Job:
    job_id: str          # stable global id for dedupe: "<ats>:<slug>:<id>"
    ats: str
    company: str
    title: str
    location: str
    url: str
    description: str
    posted_at: str | None = None
    salary: str | None = None
    # filled in later by the pipeline
    score: float | None = None
    reason: str | None = None
    draft: dict[str, Any] = field(default_factory=dict)

    @property
    def score_100(self) -> int:
        if self.score is None:
            return 0
        return int(round(max(0.0, min(10.0, float(self.score))) * 10))

    @property
    def queue_category(self) -> str:
        s = self.score_100
        if s >= 90:
            return "🔥 Exceptional"
        elif s >= 80:
            return "🟢 Strong Apply"
        elif s >= 70:
            return "🟡 Apply"
        elif s >= 60:
            return "⚪ Consider"
        else:
            return "🔴 Skip"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["score_100"] = self.score_100
        d["queue_category"] = self.queue_category
        return d


# --------------------------------------------------------------------------
# Adapters & ATS Registry. Each takes raw JSON body and returns list[Job].
# Keeping parse separate from HTTP is what makes offline testing possible.
# --------------------------------------------------------------------------

ParserFunc = Callable[[str, str, Any], list[Job]]
REGISTERED_ATS: dict[str, tuple[str, ParserFunc]] = {}


def register_ats(name: str, url_template: str) -> Callable[[ParserFunc], ParserFunc]:
    """Decorator to register a new ATS board parser.

    Emits a warning when the same ATS name is registered by a *different* function —
    this catches accidental overwrites from typos while still allowing intentional
    aliases (e.g., 'breezy' and 'breezyhr' both pointing to the same function).
    """
    def decorator(func: ParserFunc) -> ParserFunc:
        lower = name.lower()
        if lower in REGISTERED_ATS:
            existing_fn = REGISTERED_ATS[lower][1]
            if existing_fn is not func:
                import warnings
                warnings.warn(
                    f"ATS '{lower}' already registered by {existing_fn.__name__!r}; "
                    f"overwriting with {func.__name__!r}. "
                    f"Use an intentional alias if this is expected.",
                    stacklevel=2,
                )
        REGISTERED_ATS[lower] = (url_template, func)
        return func
    return decorator


@register_ats("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
def parse_greenhouse(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    jobs_list = (body.get("jobs") or []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
        loc = j.get("location") or {}
        loc_name = loc.get("name") if isinstance(loc, dict) else str(loc or "")
        jid = j.get("id")
        raw_url = j.get("absolute_url")
        url = raw_url if raw_url and str(raw_url).startswith(("http://", "https://")) else f"https://boards.greenhouse.io/{slug}/jobs/{jid}"
        out.append(Job(
            job_id=f"greenhouse:{slug}:{jid}",
            ats="greenhouse",
            company=company,
            title=(j.get("title") or "").strip(),
            location=str(loc_name or "").strip(),
            url=url,
            description=strip_html(j.get("content")),
            posted_at=j.get("updated_at") or j.get("first_published"),
        ))
    return out


@register_ats("lever", "https://api.lever.co/v0/postings/{slug}?mode=json")
def parse_lever(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    jobs_list = body if isinstance(body, list) else (body.get("data") or [] if isinstance(body, dict) else [])
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
        cats = j.get("categories") or {}
        chunks = [j.get("descriptionPlain") or strip_html(j.get("description"))]
        for lst in (j.get("lists") or []):
            if isinstance(lst, dict):
                chunks.append(str(lst.get("text") or ""))
                chunks.append(strip_html(lst.get("content")))
        chunks.append(j.get("additionalPlain") or strip_html(j.get("additional")))
        ts = j.get("createdAt")
        posted = None
        if isinstance(ts, (int, float)):
            try:
                if ts > 0:
                    posted = time.strftime("%Y-%m-%d", time.gmtime(ts / 1000))
            except (ValueError, OSError, OverflowError):
                posted = None
        jid = j.get("id")
        raw_url = j.get("hostedUrl") or j.get("applyUrl")
        url = raw_url if raw_url and str(raw_url).startswith(("http://", "https://")) else f"https://jobs.lever.co/{slug}/{jid}"
        loc_val = cats.get("location") if isinstance(cats, dict) else str(cats or "")
        out.append(Job(
            job_id=f"lever:{slug}:{jid}",
            ats="lever",
            company=company,
            title=(j.get("text") or "").strip(),
            location=str(loc_val or "").strip(),
            url=url,
            description="\n\n".join(c for c in chunks if c).strip(),
            posted_at=posted,
            salary=cats.get("commitment") if isinstance(cats, dict) else None,
        ))
    return out


@register_ats("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
def parse_ashby(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    jobs_list = (body.get("jobPostings") or body.get("jobs") or []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
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
        url = raw_url if raw_url and str(raw_url).startswith(("http://", "https://")) else f"https://jobs.ashbyhq.com/{slug}/{jid}"
        loc_val = j.get("location")
        if isinstance(loc_val, dict):
            loc_val = loc_val.get("name") or loc_val.get("location") or ""
        out.append(Job(
            job_id=f"ashby:{slug}:{jid}",
            ats="ashby",
            company=company,
            title=(j.get("title") or "").strip(),
            location=str(loc_val or "").strip(),
            url=url,
            description=(j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")) or "").strip(),
            posted_at=j.get("publishedAt") or j.get("publishedDate"),
            salary=salary,
        ))
    return out


@register_ats("workable", "https://apply.workable.com/api/v2/accounts/{slug}/jobs")
def parse_workable(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    jobs_list = (body.get("results") or body.get("jobs") or []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
        loc = j.get("location") or {}
        loc_str = loc.get("city") or loc.get("country") or j.get("location_str") or "" if isinstance(loc, dict) else str(loc or "")
        shortcode = j.get("shortcode") or j.get("id")
        raw_url = j.get("url") or j.get("application_url")
        url = raw_url if raw_url and str(raw_url).startswith(("http://", "https://")) else f"https://apply.workable.com/{slug}/j/{shortcode}/"
        out.append(Job(
            job_id=f"workable:{slug}:{shortcode}",
            ats="workable",
            company=company,
            title=(j.get("title") or "").strip(),
            location=str(loc_str).strip(),
            url=url,
            description=strip_html(j.get("description")),
            posted_at=j.get("published") or j.get("created_at") or j.get("published_on"),
        ))
    return out


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
        loc = j.get("location") or {}
        loc_str = loc.get("city") or loc.get("country") or "" if isinstance(loc, dict) else str(loc or "")
        jid = j.get("id")
        ad = j.get("jobAd") or {}
        raw_url = (j.get("applyUrl") or ad.get("applyUrl")) if isinstance(ad, dict) else j.get("applyUrl")
        url = raw_url if raw_url and str(raw_url).startswith(("http://", "https://")) else f"https://jobs.smartrecruiters.com/{slug}/{jid}"
        desc = None
        if isinstance(ad, dict):
            sections = ad.get("sections")
            if isinstance(sections, dict):
                jd_sec = sections.get("jobDescription")
                if isinstance(jd_sec, dict):
                    desc = jd_sec.get("text")
        out.append(Job(
            job_id=f"smartrecruiters:{slug}:{jid}",
            ats="smartrecruiters",
            company=company,
            title=(j.get("name") or j.get("title") or "").strip(),
            location=str(loc_str).strip(),
            url=url,
            description=strip_html(desc),
            posted_at=j.get("releasedDate") or j.get("createdOn"),
        ))
    return out


@register_ats("bamboohr", "https://{slug}.bamboohr.com/careers/list")
def parse_bamboohr(slug: str, company: str, body: Any) -> list[Job]:
    out: list[Job] = []
    jobs_list = (body.get("result") or body.get("jobs") or []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    for j in jobs_list:
        if not isinstance(j, dict):
            continue
        jid = j.get("id") or j.get("jobOpeningId")
        loc = j.get("location") or {}
        if isinstance(loc, dict):
            loc_parts = [loc.get("city"), loc.get("state")]
            loc_str = ", ".join(p for p in loc_parts if p) or "Remote/Unspecified"
        else:
            loc_str = str(loc or "Remote/Unspecified")
        url = f"https://{slug}.bamboohr.com/careers/{jid}"
        out.append(Job(
            job_id=f"bamboohr:{slug}:{jid}",
            ats="bamboohr",
            company=company,
            title=(j.get("jobOpeningName") or j.get("title") or "").strip(),
            location=str(loc_str).strip(),
            url=url,
            description=strip_html(j.get("description") or j.get("jobDescription")),
            posted_at=j.get("datePosted") or j.get("postedDate"),
        ))
    return out


@register_ats("recruitee", "https://{slug}.recruitee.com/api/offers/")
def parse_recruitee(slug: str, company: str, body: Any) -> list[Job]:
    out: list[Job] = []
    offers = (body.get("offers") or []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    for j in offers:
        if not isinstance(j, dict):
            continue
        jid = j.get("id")
        loc_str = j.get("location") or j.get("city") or j.get("country") or ("Remote" if j.get("remote") else "Unspecified")
        raw_url = j.get("careers_url") or j.get("url")
        url = raw_url if raw_url and str(raw_url).startswith(("http://", "https://")) else f"https://{slug}.recruitee.com/o/{jid}"
        out.append(Job(
            job_id=f"recruitee:{slug}:{jid}",
            ats="recruitee",
            company=company,
            title=(j.get("title") or "").strip(),
            location=str(loc_str).strip(),
            url=url,
            description=strip_html(j.get("description") or j.get("requirements")),
            posted_at=j.get("created_at") or j.get("published_at"),
            salary=j.get("salary_range") or j.get("compensation"),
        ))
    return out


@register_ats("breezy", "https://{slug}.breezy.hr/json")
@register_ats("breezyhr", "https://{slug}.breezy.hr/json")
def parse_breezy(slug: str, company: str, body: Any) -> list[Job]:
    out: list[Job] = []
    positions = (body.get("positions") or []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    for j in positions:
        if not isinstance(j, dict):
            continue
        jid = j.get("id") or j.get("friendly_id")
        loc = j.get("location") or {}
        loc_name = loc.get("name") if isinstance(loc, dict) else str(loc)
        if isinstance(loc, dict) and loc.get("is_remote"):
            loc_name = f"{loc_name} (Remote)" if loc_name else "Remote"
        raw_url = j.get("url")
        url = raw_url if raw_url and str(raw_url).startswith(("http://", "https://")) else f"https://{slug}.breezy.hr/p/{jid}"
        out.append(Job(
            job_id=f"breezy:{slug}:{jid}",
            ats="breezy",
            company=company,
            title=(j.get("name") or j.get("title") or "").strip(),
            location=str(loc_name or "Remote/Unspecified").strip(),
            url=url,
            description=strip_html(j.get("description") or j.get("summary")),
            posted_at=j.get("published_date") or j.get("updated_at"),
            salary=j.get("type", {}).get("name") if isinstance(j.get("type"), dict) else None,
        ))
    return out


@register_ats("pinpoint", "https://{slug}.pinpoint.work/en/postings.json")
def parse_pinpoint(slug: str, company: str, body: Any) -> list[Job]:
    out: list[Job] = []
    data_list = (body.get("data") or body.get("jobs") or []) if isinstance(body, dict) else (body if isinstance(body, list) else [])
    for j in data_list:
        if not isinstance(j, dict):
            continue
        jid = j.get("id")
        loc = j.get("location") or {}
        loc_str = loc.get("city") or loc.get("country") or j.get("location_name") if isinstance(loc, dict) else str(loc or "")
        if not loc_str:
            loc_str = "Remote" if j.get("workplace_type") == "remote" else "Unspecified"
        raw_url = j.get("url")
        url = raw_url if raw_url and str(raw_url).startswith(("http://", "https://")) else f"https://{slug}.pinpoint.work/en/postings/{jid}"
        out.append(Job(
            job_id=f"pinpoint:{slug}:{jid}",
            ats="pinpoint",
            company=company,
            title=(j.get("title") or "").strip(),
            location=str(loc_str).strip(),
            url=url,
            description=strip_html(j.get("description") or j.get("summary") or j.get("body")),
            posted_at=j.get("published_at") or j.get("created_at"),
            salary=j.get("salary_range") or j.get("compensation"),
        ))
    return out


# Dict compatibility wrapper pointing to the registry
ENDPOINTS = REGISTERED_ATS

# Global in-memory cache for high-throughput ATS job pooling (TTL: 30 minutes)
_GLOBAL_ATS_CACHE: dict[str, tuple[float, list[Job]]] = {}
_ATS_CACHE_LOCK = threading.Lock()   # Fix 11: protect concurrent reads/writes
_MAX_ATS_CACHE_SIZE = 500
_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # Fix 12: 10 MB hard cap per ATS response


def _prune_ats_cache(now: float, ttl: float = 1800.0) -> None:
    """Sweep expired ATS cached jobs and cap memory size. Caller must hold _ATS_CACHE_LOCK."""
    expired = [k for k, (ts, _) in _GLOBAL_ATS_CACHE.items() if now - ts >= ttl]
    for k in expired:
        _GLOBAL_ATS_CACHE.pop(k, None)
    if len(_GLOBAL_ATS_CACHE) > _MAX_ATS_CACHE_SIZE:
        excess = len(_GLOBAL_ATS_CACHE) - _MAX_ATS_CACHE_SIZE
        for k in list(_GLOBAL_ATS_CACHE.keys())[:excess]:
            _GLOBAL_ATS_CACHE.pop(k, None)


def clear_ats_cache() -> None:
    """Clear all pre-cached ATS results."""
    with _ATS_CACHE_LOCK:
        _GLOBAL_ATS_CACHE.clear()


def fetch_board(ats: str, slug: str, company: str | None = None,
                session: Any = None,
                use_cache: bool = True,
                cache_ttl: float = 1800.0) -> list[Job]:
    """Hit one company's public board with caching and retries. Returns [] on failure."""
    ats_lower = ats.lower()
    if ats_lower not in REGISTERED_ATS:
        raise ValueError(f"unknown ATS: {ats}")

    cache_key = f"{ats_lower}:{slug}"
    now = time.time()

    # Thread-safe cache read
    with _ATS_CACHE_LOCK:
        if use_cache and cache_key in _GLOBAL_ATS_CACHE:
            ts, cached_jobs = _GLOBAL_ATS_CACHE[cache_key]
            if now - ts < cache_ttl:
                return list(cached_jobs)
            else:
                _GLOBAL_ATS_CACHE.pop(cache_key, None)

    url_tpl, parser = REGISTERED_ATS[ats_lower]
    sess = session or requests
    max_retries = 2
    for attempt in range(max_retries):
        try:
            r = sess.get(url_tpl.format(slug=slug), headers=UA, timeout=TIMEOUT)
            if r.status_code == 200:
                # Guard against oversized responses (e.g., broken or malicious ATS)
                raw_bytes = getattr(r, "content", None)
                if raw_bytes is None:
                    raw_text = getattr(r, "text", "")
                    raw_bytes = raw_text.encode("utf-8") if isinstance(raw_text, str) else b""
                content_len = len(raw_bytes)
                if content_len > _MAX_RESPONSE_BYTES:
                    print(f"  ! {ats}/{slug} -> response too large ({content_len // 1024} KB), skipping")
                    return []
                jobs = parser(slug, company or slug, r.json())
                # Thread-safe cache write
                with _ATS_CACHE_LOCK:
                    if use_cache:
                        _prune_ats_cache(now, cache_ttl)
                        _GLOBAL_ATS_CACHE[cache_key] = (now, list(jobs))
                return jobs

            elif r.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
            else:
                print(f"  ! {ats}/{slug} -> HTTP {r.status_code}")
                return []
        except (requests.RequestException, KeyError, ValueError, TypeError) as e:
            if attempt < max_retries - 1:
                time.sleep(1.0 * (attempt + 1))
                continue
            print(f"  ! {ats}/{slug} -> {type(e).__name__}: {e}")
            return []
    return []


def fetch_all(companies: Iterable[dict] | str | Any, sleep: float = 0.25,
              max_workers: int = 8, use_cache: bool = True) -> list[Job]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from pathlib import Path
    import yaml

    company_list: list[dict] = []
    if isinstance(companies, (str, Path)):
        p = Path(companies)
        if p.is_file():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            company_list = data.get("companies", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
    elif isinstance(companies, dict):
        company_list = companies.get("companies", [])
    elif isinstance(companies, Iterable):
        company_list = [c for c in companies if isinstance(c, dict)]

    if not company_list:
        return []

    import os
    if os.environ.get("VERCEL") == "1":
        company_list = company_list[:10]
        print(f"  [vercel] serverless environment detected — throttling crawl to first {len(company_list)} companies to prevent timeout.")

    jobs: list[Job] = []
    from urllib3.util import Retry
    from requests.adapters import HTTPAdapter
    with requests.Session() as session:
        retries = Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        if max_workers > 1 and len(company_list) > 1:
            def worker(c: dict) -> tuple[dict, list[Job]]:
                try:
                    res = fetch_board(c["ats"], c["slug"], c.get("name"), session=session, use_cache=use_cache)
                except TypeError:
                    res = fetch_board(c["ats"], c["slug"], c.get("name"), session=session)
                return c, res

            with ThreadPoolExecutor(max_workers=min(max_workers, len(company_list))) as executor:
                futures = [executor.submit(worker, c) for c in company_list]
                for future in as_completed(futures):
                    try:
                        c, got = future.result()
                        if got:
                            print(f"  {c.get('name') or c['slug']:<28} {len(got):>4} jobs  ({c['ats']})")
                        jobs.extend(got)
                    except (requests.RequestException, KeyError, ValueError, TypeError) as e:
                        print(f"  ! worker error: {e}")
        else:
            for c in company_list:
                try:
                    got = fetch_board(c["ats"], c["slug"], c.get("name"), session=session, use_cache=use_cache)
                except TypeError:
                    got = fetch_board(c["ats"], c["slug"], c.get("name"), session=session)
                if got:
                    print(f"  {c.get('name') or c['slug']:<28} {len(got):>4} jobs  ({c['ats']})")
                jobs.extend(got)
                if sleep > 0:
                    time.sleep(sleep)

    return jobs
