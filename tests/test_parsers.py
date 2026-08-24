from __future__ import annotations
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhunt import mock
from jobhunt.fetch import Job, parse_ashby, parse_greenhouse, parse_lever, strip_html
from jobhunt.mock import fetch_all_mock
from jobhunt.prefilter import prefilter

CONFIG = yaml.safe_load((Path(__file__).resolve().parent.parent / "config.yaml").read_text(encoding="utf-8"))
FILTERS = CONFIG["filters"]

def test_strip_html_unescapes_twice():
    assert strip_html("&lt;p&gt;Go &amp;amp; Java&lt;/p&gt;") == "Go & Java"

def test_strip_html_turns_block_tags_into_newlines():
    out = strip_html("<p>One</p><p>Two</p><ul><li>a</li><li>b</li></ul>")
    assert "One" in out and "Two" in out and "<" not in out

def test_strip_html_handles_none_and_empty():
    assert strip_html(None) == ""
    assert strip_html("") == ""

def test_greenhouse_maps_every_field():
    jobs = parse_greenhouse("acme-edge", "Acme Edge", mock.GREENHOUSE["acme-edge"])
    j = next(j for j in jobs if j.title.startswith("Software Engineer II"))
    assert j.job_id == "greenhouse:acme-edge:5501001"
    assert j.ats == "greenhouse"
    assert j.company == "Acme Edge"
    assert j.location == "Bangalore, India"
    assert j.url.startswith("https://boards.greenhouse.io/")
    assert "distributed services" in j.description

def test_lever_concatenates_description_lists_and_additional():
    jobs = parse_lever("quantstack", "QuantStack", mock.LEVER["quantstack"])
    j = next(j for j in jobs if j.title == "Backend Engineer (Go)")
    assert "market data pipeline" in j.description
    assert "Requirements" in j.description
    assert "2-5 years backend experience" in j.description
    assert "No take-home" in j.description

def test_lever_createdAt_is_epoch_milliseconds():
    two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).date()
    jobs = parse_lever("quantstack", "QuantStack", mock.LEVER["quantstack"])
    j = next(j for j in jobs if j.title == "Backend Engineer (Go)")
    assert j.posted_at == two_days_ago.isoformat()

def test_ashby_skips_unlisted_drafts():
    jobs = parse_ashby("helioscale", "Helioscale", mock.ASHBY["helioscale"])
    assert all("unlisted" not in j.url for j in jobs)
    assert len(jobs) == 2

def test_ashby_reads_compensation_and_html_fallback():
    jobs = parse_ashby("helioscale", "Helioscale", mock.ASHBY["helioscale"])
    networking = next(j for j in jobs if j.title == "Software Engineer, Networking")
    assert networking.salary == "\u20b932L \u2013 \u20b948L"
    ds = next(j for j in jobs if j.title == "Data Scientist, Growth")
    assert "Causal inference" in ds.description

def test_job_ids_are_globally_unique_and_namespaced():
    jobs = fetch_all_mock()
    ids = [j.job_id for j in jobs]
    assert len(ids) == len(set(ids))
    assert all(re.match(r"^(greenhouse|lever|ashby):[^:]+:.+$", i) for i in ids)

def test_parsers_take_decoded_json_not_a_response():
    assert parse_greenhouse("x", "X", {}) == []
    assert parse_lever("x", "X", []) == []
    assert parse_ashby("x", "X", {}) == []

@pytest.mark.parametrize("title", [
    "Software Engineer II, Distributed Systems",
    "Software Development Engineer, Core Infra",
    "Backend Engineer (Go)",
    "Site Reliability Engineer",
    "SDE II",
])
def test_include_titles_match_real_titles(title):
    inc = FILTERS["include_titles"]
    if not inc:
        assert True  # open platform: all titles pass
    else:
        assert any(re.search(p, title, re.I) for p in inc), title

def test_bare_sde_regex_does_not_match_the_spelled_out_title():
    assert not re.search(r"\bsde\b", "Software Development Engineer", re.I)
    assert re.search(r"\bsde\b", "SDE II", re.I)
    inc = FILTERS["include_titles"]
    if not inc:
        assert True
    else:
        assert any(re.search(p, "Software Development Engineer, Core Infra", re.I) for p in inc)

def test_full_mock_funnel_keeps_non_stale_jobs():
    kept = prefilter(fetch_all_mock(), FILTERS)
    titles = sorted(j.title for j in kept)
    assert "Senior Software Engineer, Platform" not in titles
    assert "Backend Engineer (Go)" in titles
    assert "Site Reliability Engineer" in titles
    assert "Software Development Engineer, Core Infra" in titles
    assert "Software Engineer II, Distributed Systems" in titles
    assert "Software Engineer, Networking" in titles
    assert "Staff Software Engineer, Storage" in titles

def test_stale_posting_is_dropped_by_freshness_gate():
    kept = prefilter(fetch_all_mock(), FILTERS)
    assert not any("Senior Software Engineer, Platform" == j.title for j in kept)

def test_wrong_city_dropped_but_remote_kept():
    remote_job = Job(job_id="greenhouse:acme:999", ats="greenhouse", company="Acme",
                     title="Backend Engineer", location="Remote - Global",
                     url="https://example.com/999", description="Go",
                     posted_at=datetime.now(timezone.utc).isoformat())
    explicit_filter = dict(FILTERS, locations=["india", "bangalore", "mumbai"], allow_remote=True)
    kept = prefilter(fetch_all_mock() + [remote_job], explicit_filter)
    assert not any("San Francisco" in (j.location or "") for j in kept)
    assert any("Remote" in (j.location or "") for j in kept)

def test_allow_remote_is_what_lets_an_out_of_region_remote_role_through():
    remote = Job(job_id="lever:x:1", ats="lever", company="X",
                 title="Backend Engineer", location="Remote - Global",
                 url="https://example.com", description="Go")
    explicit_on = dict(FILTERS, locations=["india", "bangalore"], allow_remote=True)
    explicit_off = dict(FILTERS, locations=["india", "bangalore"], allow_remote=False)
    assert len(prefilter([remote], explicit_on)) == 1
    assert prefilter([remote], explicit_off) == []

def test_exclude_locations_drops_out_of_region_remote():
    us_remote = Job(job_id="greenhouse:x:2", ats="greenhouse", company="X",
                    title="Backend Engineer", location="Remote - United States",
                    url="https://example.com", description="Python")
    india_remote = Job(job_id="greenhouse:x:3", ats="greenhouse", company="X",
                      title="Backend Engineer", location="Remote - India",
                      url="https://example.com", description="Python")
    kept = prefilter([us_remote, india_remote],
                     dict(FILTERS, exclude_locations=[r"\b(united states|usa)\b"]))
    assert len(kept) == 1
    assert kept[0].job_id == "greenhouse:x:3"

def test_empty_filters_keep_everything():
    jobs = fetch_all_mock()
    assert len(prefilter(jobs, {})) == len(jobs)

def test_prefilter_invalid_date_handling():
    from jobhunt.prefilter import _parse_date
    assert _parse_date(None) is None
    assert _parse_date("") is None
    assert _parse_date("not-a-date") is None
    invalid_date_job = Job(job_id="test:1", ats="test", company="Test", title="Backend Engineer",
                           location="Remote", url="http://ex.com", description="Go",
                           posted_at="completely-invalid-date-string")
    assert len(prefilter([invalid_date_job], {"max_age_days": 10})) == 1

def test_workable_and_smartrecruiters_parsers():
    from jobhunt.fetch import parse_workable, parse_smartrecruiters
    w_jobs = parse_workable("vector", "Vector", {"results": [{"shortcode": "W123",
        "title": "Backend Engineer", "location": {"city": "Bangalore", "country": "India"},
        "url": "https://apply.workable.com/vector/j/W123/",
        "description": "<p>Python &amp; Flask API</p>", "published": "2026-08-01"}]})
    assert len(w_jobs) == 1 and w_jobs[0].job_id == "workable:vector:W123"
    assert w_jobs[0].location == "Bangalore"
    sr_jobs = parse_smartrecruiters("visa", "Visa", {"content": [{"id": "SR456",
        "name": "Software Engineer II", "location": {"city": "Mumbai"},
        "refNumber": "https://jobs.smartrecruiters.com/visa/SR456",
        "jobAd": {"sections": {"jobDescription": {"text": "<p>Node.js</p>"}}},
        "releasedDate": "2026-08-05"}]})
    assert len(sr_jobs) == 1 and sr_jobs[0].job_id == "smartrecruiters:visa:SR456"
    assert sr_jobs[0].location == "Mumbai"

def test_bamboohr_parser():
    from jobhunt.fetch import parse_bamboohr
    b_jobs = parse_bamboohr("acme", "Acme Corp", {"result": [{"id": "101",
        "jobOpeningName": "Senior Platform Engineer",
        "location": {"city": "Pune", "state": "MH"},
        "description": "<p>Kubernetes</p>", "datePosted": "2026-08-10"}]})
    assert len(b_jobs) == 1 and b_jobs[0].job_id == "bamboohr:acme:101"
    assert b_jobs[0].location == "Pune, MH"

def test_prefilter_stale_date_drop():
    old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
    old_job = Job("1", "gh", "Acme", "Software Engineer", "Remote", "http://x", "Python", posted_at=old_date)
    assert len(prefilter([old_job], {"max_age_days": 28, "include_titles": ["Software Engineer"]})) == 0

def test_recruitee_breezy_pinpoint_parsers():
    from jobhunt.fetch import parse_recruitee, parse_breezy, parse_pinpoint
    r_jobs = parse_recruitee("hotjar", "Hotjar", {"offers": [{"id": 12345,
        "title": "Backend Go Engineer", "city": "Amsterdam", "country": "Netherlands",
        "careers_url": "https://hotjar.recruitee.com/o/backend-go",
        "description": "<p>Build high volume APIs in Go and Postgres.</p>",
        "created_at": "2026-08-15T12:00:00Z", "salary_range": "\u20ac70k - \u20ac95k"}]})
    assert len(r_jobs) == 1 and r_jobs[0].job_id == "recruitee:hotjar:12345"
    assert r_jobs[0].salary == "\u20ac70k - \u20ac95k"
    b_jobs = parse_breezy("acme", "Acme", {"positions": [{"id": "brz999",
        "name": "Full Stack Engineer", "location": {"name": "Berlin", "is_remote": True},
        "url": "https://acme.breezy.hr/p/brz999",
        "description": "<p>TypeScript, React and Node.js</p>",
        "published_date": "2026-08-14", "type": {"name": "Full-Time"}}]})
    assert len(b_jobs) == 1 and "Remote" in b_jobs[0].location
    p_jobs = parse_pinpoint("scale", "Scale", {"data": [{"id": 789,
        "title": "Site Reliability Engineer", "location": {"city": "London", "country": "UK"},
        "url": "https://scale.pinpoint.work/en/postings/789",
        "description": "<p>Manage Kubernetes and AWS infrastructure.</p>",
        "published_at": "2026-08-16T10:00:00Z", "salary_range": "\u00a380,000 - \u00a3100,000"}]})
    assert len(p_jobs) == 1 and p_jobs[0].salary == "\u00a380,000 - \u00a3100,000"


def test_detect_job_type_and_negations():
    from jobhunt.prefilter import _detect_job_type

    # Remote
    j1 = Job("1", "gh", "A", "Senior Backend Engineer", "Remote, US", "http://x", "Fully remote role.")
    assert "remote" in _detect_job_type(j1)
    assert "fulltime" in _detect_job_type(j1)

    # Hybrid
    j2 = Job("2", "gh", "A", "Frontend Developer", "Bengaluru", "http://x", "Hybrid: 2 days from home.")
    assert "hybrid" in _detect_job_type(j2)

    # Intern
    j3 = Job("3", "gh", "A", "Software Engineering Intern", "Pune", "http://x", "Summer internship.")
    assert "internship" in _detect_job_type(j3)
    assert "fulltime" not in _detect_job_type(j3)

    # Onsite
    j4 = Job("4", "gh", "A", "Staff Engineer", "Mumbai Office", "http://x", "In-office only role.")
    assert "onsite" in _detect_job_type(j4)

    # Negation rules: 'not remote'
    j_not_remote = Job("5", "gh", "A", "DevOps", "Delhi", "http://x", "Candidate must work in office. Not remote / no wfh.")
    assert "remote" not in _detect_job_type(j_not_remote)

    # Negation rules: 'not an internship'
    j_not_intern = Job("6", "gh", "A", "Engineering Manager", "Bengaluru", "http://x", "Leadership role (not an internship).")
    assert "internship" not in _detect_job_type(j_not_intern)
    assert "fulltime" in _detect_job_type(j_not_intern)


def test_prefilter_job_types_filter_and_exclude_titles():
    now_iso = datetime.now(timezone.utc).isoformat()
    jobs = [
        Job("1", "gh", "A", "CTO & Co-Founder", "Remote", "http://x", "Exec", posted_at=now_iso),
        Job("2", "gh", "A", "Software Engineer", "Bangalore", "http://x", "remote full-time role", posted_at=now_iso),
        Job("3", "gh", "A", "Software Engineering Intern", "Bangalore", "http://x", "intern", posted_at=now_iso),
    ]

    # Fulltime filter + exclude CTO
    passed = prefilter(jobs, {"exclude_titles": [r"\bcto\b"], "job_types": ["fulltime"], "max_age_days": 30})
    assert len(passed) == 1 and passed[0].job_id == "2"

    # Internship filter
    passed_intern = prefilter(jobs, {"job_types": ["internship"], "max_age_days": 30})
    assert len(passed_intern) == 1 and passed_intern[0].job_id == "3"

