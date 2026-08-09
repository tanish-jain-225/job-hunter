"""Fetch jobs from public ATS APIs. No auth, no scraping, no ToS risk."""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Iterable

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# Adapters & ATS Registry. Each takes raw JSON body and returns list[Job].
# Keeping parse separate from HTTP is what makes offline testing possible.
# --------------------------------------------------------------------------

from typing import Callable

ParserFunc = Callable[[str, str, Any], list[Job]]
REGISTERED_ATS: dict[str, tuple[str, ParserFunc]] = {}


def register_ats(name: str, url_template: str) -> Callable[[ParserFunc], ParserFunc]:
    """Decorator to register a new ATS board parser."""
    def decorator(func: ParserFunc) -> ParserFunc:
        REGISTERED_ATS[name.lower()] = (url_template, func)
        return func
    return decorator


@register_ats("greenhouse", "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
def parse_greenhouse(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    for j in (body or {}).get("jobs", []):
        loc = (j.get("location") or {}).get("name") or ""
        out.append(Job(
            job_id=f"greenhouse:{slug}:{j.get('id')}",
            ats="greenhouse",
            company=company,
            title=(j.get("title") or "").strip(),
            location=loc.strip(),
            url=j.get("absolute_url") or "",
            description=strip_html(j.get("content")),
            posted_at=j.get("updated_at") or j.get("first_published"),
        ))
    return out


@register_ats("lever", "https://api.lever.co/v0/postings/{slug}?mode=json")
def parse_lever(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    for j in (body or []):
        cats = j.get("categories") or {}
        # Lever splits the JD across descriptionPlain + a `lists` array.
        chunks = [j.get("descriptionPlain") or strip_html(j.get("description"))]
        for lst in (j.get("lists") or []):
            chunks.append(str(lst.get("text") or ""))
            chunks.append(strip_html(lst.get("content")))
        chunks.append(j.get("additionalPlain") or strip_html(j.get("additional")))
        ts = j.get("createdAt")
        posted = None
        if isinstance(ts, (int, float)):
            posted = time.strftime("%Y-%m-%d", time.gmtime(ts / 1000))
        out.append(Job(
            job_id=f"lever:{slug}:{j.get('id')}",
            ats="lever",
            company=company,
            title=(j.get("text") or "").strip(),
            location=(cats.get("location") or "").strip(),
            url=j.get("hostedUrl") or j.get("applyUrl") or "",
            description="\n\n".join(c for c in chunks if c).strip(),
            posted_at=posted,
            salary=cats.get("commitment"),
        ))
    return out


@register_ats("ashby", "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true")
def parse_ashby(slug: str, company: str, body: Any) -> list[Job]:
    out = []
    for j in (body or {}).get("jobs", []):
        if j.get("isListed") is False:
            continue
        comp = j.get("compensation") or {}
        salary = None
        summary = comp.get("compensationTierSummary") or comp.get("summaryComponents")
        if isinstance(summary, str):
            salary = summary
        out.append(Job(
            job_id=f"ashby:{slug}:{j.get('id')}",
            ats="ashby",
            company=company,
            title=(j.get("title") or "").strip(),
            location=(j.get("location") or "").strip(),
            url=j.get("jobUrl") or j.get("applyUrl") or "",
            description=(j.get("descriptionPlain") or strip_html(j.get("descriptionHtml")) or "").strip(),
            posted_at=j.get("publishedAt"),
            salary=salary,
        ))
    return out


# Dict compatibility wrapper pointing to the registry
ENDPOINTS = REGISTERED_ATS


def fetch_board(ats: str, slug: str, company: str | None = None,
                session: requests.Session | None = None) -> list[Job]:
    """Hit one company's public board. Returns [] on any failure (never raises)."""
    ats_lower = ats.lower()
    if ats_lower not in REGISTERED_ATS:
        raise ValueError(f"unknown ATS: {ats}")
    url_tpl, parser = REGISTERED_ATS[ats_lower]
    sess = session or requests
    try:
        r = sess.get(url_tpl.format(slug=slug), headers=UA, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"  ! {ats}/{slug} -> HTTP {r.status_code}")
            return []
        return parser(slug, company or slug, r.json())
    except (requests.RequestException, KeyError, ValueError, TypeError) as e:
        print(f"  ! {ats}/{slug} -> {type(e).__name__}: {e}")
        return []


def fetch_all(companies: Iterable[dict] | str | Any, sleep: float = 0.25,
              max_workers: int = 8) -> list[Job]:
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

    jobs: list[Job] = []
    session = requests.Session()

    if max_workers > 1 and len(company_list) > 1:
        def worker(c: dict) -> tuple[dict, list[Job]]:
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
            got = fetch_board(c["ats"], c["slug"], c.get("name"), session=session)
            if got:
                print(f"  {c.get('name') or c['slug']:<28} {len(got):>4} jobs  ({c['ats']})")
            jobs.extend(got)
            if sleep > 0:
                time.sleep(sleep)

    return jobs

