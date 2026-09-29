"""Fetch jobs from public ATS APIs with concurrency, caching, and SSRF defenses."""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from .parsers import (
    Job,
    ParserFunc,
    REGISTERED_ATS,
    register_ats,
    strip_html,
    extract_salary_hint,
    is_safe_url,
    detect_ats_from_url,
    parse_greenhouse,
    parse_lever,
    parse_ashby,
    parse_workable,
    parse_smartrecruiters,
    parse_bamboohr,
    parse_recruitee,
    parse_breezy,
    parse_pinpoint,
)

UA = {"User-Agent": "jobhunt/1.0 (personal job search agent)"}
TIMEOUT = 20

# Dict compatibility wrapper pointing to the registry
ENDPOINTS = REGISTERED_ATS

# Global in-memory cache for high-throughput ATS job pooling (TTL: 30 minutes)
_GLOBAL_ATS_CACHE: dict[str, tuple[float, list[Job]]] = {}
_ATS_CACHE_LOCK = threading.Lock()
_MAX_ATS_CACHE_SIZE = 500
_MAX_RESPONSE_BYTES = 30 * 1024 * 1024  # 30 MB hard cap per ATS response


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


def fetch_board(
    ats: str,
    slug: str,
    company: str | None = None,
    session: Any = None,
    use_cache: bool = True,
    cache_ttl: float = 1800.0,
) -> list[Job]:
    """Hit one company's public board with caching, retries, and SSRF validation. Returns [] on failure."""
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
    target_url = url_tpl.format(slug=slug)

    # SSRF Defense: Validate URL destination before requesting
    if not is_safe_url(target_url):
        print(f"  ! {ats}/{slug} -> blocked unsafe destination URL: {target_url}")
        return []

    sess = session or requests
    max_retries = 2
    for attempt in range(max_retries):
        try:
            r = sess.get(target_url, headers=UA, timeout=TIMEOUT)
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

                # Automatic pagination support for high-volume enterprise boards (capped at 500 jobs max)
                if ats_lower == "smartrecruiters" and len(jobs) == 100:
                    offset = 100
                    while offset < 500:
                        try:
                            next_url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100&offset={offset}"
                            if not is_safe_url(next_url):
                                break
                            r_next = sess.get(next_url, headers=UA, timeout=TIMEOUT)
                            if r_next.status_code == 200:
                                more_jobs = parser(slug, company or slug, r_next.json())
                                if not more_jobs:
                                    break
                                jobs.extend(more_jobs)
                                if len(more_jobs) < 100:
                                    break
                                offset += 100
                            else:
                                break
                        except Exception:
                            break

                elif ats_lower == "workable" and isinstance(r.json(), dict) and r.json().get("nextPage"):
                    next_token = r.json().get("nextPage")
                    while next_token and len(jobs) < 500:
                        try:
                            next_url = f"https://apply.workable.com/api/v1/widget/accounts/{slug}?token={next_token}"
                            if not is_safe_url(next_url):
                                break
                            r_next = sess.get(next_url, headers=UA, timeout=TIMEOUT)
                            if r_next.status_code == 200:
                                next_data = r_next.json()
                                more_jobs = parser(slug, company or slug, next_data)
                                if not more_jobs:
                                    break
                                jobs.extend(more_jobs)
                                next_token = next_data.get("nextPage") if isinstance(next_data, dict) else None
                            else:
                                break
                        except Exception:
                            break

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


def fetch_all(
    companies: Sequence[dict[str, Any]] | dict[str, Any] | str | Path | Any,
    sleep: float = 0.25,
    max_workers: int = 8,
    use_cache: bool = True,
    custom_companies: Iterable[dict] | None = None,
) -> list[Job]:
    """Fetch all postings across configured ATS boards concurrently."""
    company_list: list[dict] = []
    if isinstance(companies, (str, Path)):
        p = Path(companies)
        if p.is_file():
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            company_list = (
                data.get("companies", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            )
    elif isinstance(companies, dict):
        comps = companies.get("companies")
        company_list = [c for c in comps if isinstance(c, dict)] if isinstance(comps, list) else []
    elif isinstance(companies, Iterable):
        company_list = [c for c in companies if isinstance(c, dict)]

    # Merge optional custom companies without mutating original references
    if custom_companies:
        existing_keys = {f"{str(c.get('ats')).lower()}:{str(c.get('slug')).lower()}" for c in company_list}
        for cc in custom_companies:
            if isinstance(cc, dict) and cc.get("ats") and cc.get("slug"):
                ck = f"{str(cc['ats']).lower()}:{str(cc['slug']).lower()}"
                if ck not in existing_keys:
                    company_list.append(cc)
                    existing_keys.add(ck)

    if not company_list:
        return []

    if os.environ.get("VERCEL") == "1":
        company_list = company_list[:10]
        print(
            f"  [vercel] serverless environment detected — throttling crawl to first {len(company_list)} companies to prevent timeout."
        )

    jobs: list[Job] = []

    with requests.Session() as session:
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[502, 503, 504], raise_on_status=False)
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
                try:
                    for future in as_completed(futures, timeout=120):
                        try:
                            c, got = future.result()
                            if got:
                                print(f"  {c.get('name') or c['slug']:<28} {len(got):>4} jobs  ({c['ats']})")
                            jobs.extend(got)
                        except Exception as e:
                            print(f"  ! worker error: {e}")
                except Exception as te:
                    print(f"  ! fetch pool finished with timeout guard ({te})")
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


__all__ = [
    "Job",
    "ParserFunc",
    "REGISTERED_ATS",
    "ENDPOINTS",
    "UA",
    "TIMEOUT",
    "register_ats",
    "strip_html",
    "extract_salary_hint",
    "is_safe_url",
    "detect_ats_from_url",
    "clear_ats_cache",
    "fetch_board",
    "fetch_all",
    "parse_greenhouse",
    "parse_lever",
    "parse_ashby",
    "parse_workable",
    "parse_smartrecruiters",
    "parse_bamboohr",
    "parse_recruitee",
    "parse_breezy",
    "parse_pinpoint",
]
