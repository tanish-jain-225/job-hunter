"""Deterministic filter that runs BEFORE any LLM call.

Cost story: ~2000 raw jobs → ~200 candidates for near-zero cost,
so the LLM only ever reads jobs that passed title + location + freshness + job_type.

India-first: Empty locations = accept all Indian cities + remote + global.
Empty include_titles = accept all titles (LLM scorer decides fit).
Empty job_types = accept all employment types.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .fetch import Job

# Remote / work-from-home detection patterns
REMOTE_HINTS = (
    "remote", "anywhere", "work from home", "wfh", "distributed",
    "work-from-home", "fully remote", "100% remote",
)

# Hybrid detection patterns
HYBRID_HINTS = (
    "hybrid", "flexible", "partial remote", "2 days from home",
    "3 days from home", "work from office",
)

# Internship detection patterns
INTERNSHIP_HINTS = (
    "intern", "internship", "trainee", "apprentice", "co-op", "coop",
    "summer intern", "graduate intern", "fresher", "entry level",
)

# Comprehensive list of Indian cities / regions for "All India" match
INDIA_LOCATIONS = [
    "india", "mumbai", "bengaluru", "bangalore", "pune", "hyderabad",
    "delhi", "new delhi", "ncr", "noida", "gurgaon", "gurugram",
    "chennai", "kolkata", "ahmedabad", "surat", "jaipur", "lucknow",
    "thane", "navi mumbai", "indore", "bhopal", "nagpur", "coimbatore",
    "kochi", "cochin", "chandigarh", "bhubaneswar", "visakhapatnam",
    "vizag", "vadodara", "baroda", "patna", "mysore", "mysuru",
    "hubli", "mangalore", "thiruvananthapuram", "trivandrum",
    "mohali", "panchkula", "ghaziabad", "faridabad", "meerut",
    "rajasthan", "karnataka", "maharashtra", "telangana", "tamilnadu",
    "andhra", "gujarat", "uttar pradesh", "haryana",
    "in",  # ISO country code
]


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.fromisoformat(v) if fmt is None else datetime.strptime(v, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# Negation patterns to prevent false positives
REMOTE_NEGATIONS = ("not remote", "no remote", "non-remote", "not open to remote", "no wfh", "in-office only")
INTERN_NEGATIONS = ("not an internship", "no interns", "non-internship", "not an intern")


def _detect_job_type(j: Job) -> set[str]:
    """Infer job type(s) from title + location + description."""
    hay = f"{j.title} {j.location} {(j.description or '')[:500]}".lower()
    types: set[str] = set()

    is_remote = any(h in hay for h in REMOTE_HINTS) and not any(neg in hay for neg in REMOTE_NEGATIONS)
    is_hybrid = any(h in hay for h in HYBRID_HINTS)
    is_intern = any(h in hay for h in INTERNSHIP_HINTS) and not any(neg in hay for neg in INTERN_NEGATIONS)

    if is_remote:
        types.add("remote")
    if is_hybrid:
        types.add("hybrid")
    if is_intern:
        types.add("internship")
    if not types or ("remote" not in types and "hybrid" not in types):
        types.add("onsite")
    if not is_intern:
        types.add("fulltime")
    else:
        types.add("internship")

    return types


def prefilter(jobs: list[Job], cfg: dict) -> list[Job]:
    inc = cfg.get("include_titles") or []
    exc = cfg.get("exclude_titles") or []
    locs = [loc.lower().strip() for loc in (cfg.get("locations") or [])]
    exc_locs = cfg.get("exclude_locations") or []
    allow_remote = bool(cfg.get("allow_remote", True))
    max_age = cfg.get("max_age_days")
    job_types_filter = [jt.lower().strip() for jt in (cfg.get("job_types") or [])]
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age) if max_age else None

    # Pre-compile patterns once
    # If include_titles is empty, match everything (wildcard)
    inc_re = [re.compile(p, re.I) for p in inc] if inc else []
    exc_re = [re.compile(p, re.I) for p in exc] if exc else []
    exc_locs_re = [re.compile(p, re.I) for p in exc_locs] if exc_locs else []

    def _match(patterns: list, text: str) -> bool:
        return any(p.search(text) for p in patterns)

    kept, stats = [], {"title": 0, "location": 0, "age": 0, "job_type": 0}
    for j in jobs:
        # Title filter: if include_titles is empty, accept all. Otherwise pattern-match.
        if inc_re and not _match(inc_re, j.title):
            stats["title"] += 1
            continue
        if exc_re and _match(exc_re, j.title):
            stats["title"] += 1
            continue

        # Location filter
        loc_lower = (j.location or "").lower()
        hay = f"{j.location} {j.title}".lower()
        is_in_target = any(loc in hay for loc in locs) if locs else True

        if exc_locs_re and _match(exc_locs_re, loc_lower) and (not locs or not is_in_target):
            stats["location"] += 1
            continue

        if locs:
            is_remote = allow_remote and any(h in hay for h in REMOTE_HINTS)
            is_hybrid = allow_remote and any(h in hay for h in HYBRID_HINTS)
            if not is_remote and not is_hybrid and not is_in_target:
                stats["location"] += 1
                continue

        # Age filter
        if cutoff:
            posted = _parse_date(j.posted_at)
            if posted and posted < cutoff:
                stats["age"] += 1
                continue

        # Job type filter (only if user has specified job_types preference)
        if job_types_filter:
            detected = _detect_job_type(j)
            if not detected.intersection(set(job_types_filter)):
                stats["job_type"] += 1
                continue

        kept.append(j)

    total = len(jobs)
    print(
        f"  prefilter: {total} -> {len(kept)} "
        f"(dropped title={stats['title']} location={stats['location']} "
        f"stale={stats['age']} job_type={stats['job_type']})"
    )
    return kept

