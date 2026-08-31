"""Unit tests for jobhunt.fetch module (HTTP calls, parsers, and error handling)."""

from __future__ import annotations

import pytest
import requests

from conftest import DummyResponse, DummySession
from jobhunt import fetch
from jobhunt.fetch import Job, fetch_all, fetch_board


def test_job_to_dict():
    job = Job(
        job_id="greenhouse:acme:1",
        ats="greenhouse",
        company="Acme",
        title="Engineer",
        location="Remote",
        url="https://example.com",
        description="Desc",
    )
    d = job.to_dict()
    assert isinstance(d, dict)
    assert d["job_id"] == "greenhouse:acme:1"
    assert d["company"] == "Acme"


def test_fetch_board_unknown_ats():
    with pytest.raises(ValueError, match="unknown ATS"):
        fetch_board("unknown_ats", "slug")


def test_fetch_board_non_200():
    session = DummySession(response=DummyResponse(404))
    jobs = fetch_board("greenhouse", "acme", session=session)
    assert jobs == []


def test_fetch_board_exception():
    session = DummySession(raise_exc=requests.RequestException("Connection error"))
    jobs = fetch_board("lever", "acme", session=session)
    assert jobs == []


def test_fetch_board_success():
    payload = {
        "jobs": [
            {
                "id": 123,
                "title": "Software Engineer",
                "location": {"name": "Remote"},
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
                "content": "<p>Job Description</p>",
            }
        ]
    }
    session = DummySession(response=DummyResponse(200, payload))
    jobs = fetch_board("greenhouse", "acme", company="Acme Corp", session=session)
    assert len(jobs) == 1
    assert jobs[0].title == "Software Engineer"
    assert jobs[0].company == "Acme Corp"


def test_fetch_all(monkeypatch):
    calls = []

    def mock_fetch_board(ats, slug, company=None, session=None):
        calls.append((ats, slug, company))
        return [
            Job(
                job_id=f"{ats}:{slug}:1",
                ats=ats,
                company=company or slug,
                title="Role",
                location="Remote",
                url="https://example.com",
                description="Desc",
            )
        ]

    monkeypatch.setattr(fetch, "fetch_board", mock_fetch_board)

    companies = [
        {"ats": "greenhouse", "slug": "acme", "name": "Acme Inc"},
        {"ats": "lever", "slug": "beta"},
    ]
    results = fetch_all(companies, sleep=0)
    assert len(results) == 2
    assert len(calls) == 2
    assert calls[0] == ("greenhouse", "acme", "Acme Inc")
    assert calls[1] == ("lever", "beta", None)


def test_fetch_all_with_filepath(tmp_path, monkeypatch):
    calls = []

    def mock_fetch_board(ats, slug, company=None, session=None):
        calls.append((ats, slug, company))
        return []

    monkeypatch.setattr(fetch, "fetch_board", mock_fetch_board)

    f = tmp_path / "companies.yaml"
    f.write_text("companies:\n  - {ats: greenhouse, slug: stripe, name: Stripe}\n")

    results = fetch_all(str(f), sleep=0)
    assert len(results) == 0
    assert len(calls) == 1
    assert calls[0] == ("greenhouse", "stripe", "Stripe")


def test_register_ats_decorator():
    @fetch.register_ats("custom_ats", "https://example.com/api/{slug}")
    def parse_custom(slug, company, body):
        return [Job("custom:1", "custom_ats", company, "Title", "Loc", "http://ex.com", "desc")]

    assert "custom_ats" in fetch.REGISTERED_ATS
    url_tpl, parser = fetch.REGISTERED_ATS["custom_ats"]
    assert url_tpl == "https://example.com/api/{slug}"
    parsed = parser("slug1", "Comp", {})
    assert len(parsed) == 1
    assert parsed[0].job_id == "custom:1"


def test_job_queue_categories():
    # Score >= 90: Exceptional
    j1 = Job("1", "gh", "Acme", "Role", "Remote", "http://x", "desc", score=9.5)
    assert j1.queue_category == "🔥 Exceptional"
    assert j1.score_100 == 95

    # Score >= 80: Strong Apply
    j2 = Job("2", "gh", "Acme", "Role", "Remote", "http://x", "desc", score=8.2)
    assert j2.queue_category == "🟢 Strong Apply"
    assert j2.score_100 == 82

    # Score >= 70: Apply
    j3 = Job("3", "gh", "Acme", "Role", "Remote", "http://x", "desc", score=7.4)
    assert j3.queue_category == "🟡 Apply"
    assert j3.score_100 == 74

    # Score >= 60: Consider
    j4 = Job("4", "gh", "Acme", "Role", "Remote", "http://x", "desc", score=6.3)
    assert j4.queue_category == "⚪ Consider"
    assert j4.score_100 == 63

    # Score < 60: Skip
    j5 = Job("5", "gh", "Acme", "Role", "Remote", "http://x", "desc", score=4.0)
    assert j5.queue_category == "🔴 Skip"
    assert j5.score_100 == 40

    # Score is None
    j6 = Job("6", "gh", "Acme", "Role", "Remote", "http://x", "desc", score=None)
    assert j6.queue_category == "🔴 Skip"
    assert j6.score_100 == 0


def test_fetch_all_dict_and_empty_inputs(monkeypatch):
    # Dict input with companies key
    called = []

    def mock_fetch_board(ats, slug, company=None, session=None):
        called.append((ats, slug))
        return [Job(f"{ats}:{slug}:1", ats, company or slug, "Role", "Remote", "http://ex.com", "desc")]

    monkeypatch.setattr(fetch, "fetch_board", mock_fetch_board)

    res_dict = fetch_all({"companies": [{"ats": "greenhouse", "slug": "acme"}]}, sleep=0)
    assert len(res_dict) == 1

    # Empty inputs
    assert fetch_all([], sleep=0) == []
    assert fetch_all("nonexistent_file_path.yaml", sleep=0) == []


def test_fetch_all_single_worker_with_sleep(monkeypatch):
    called = []

    def mock_fetch_board(ats, slug, company=None, session=None):
        called.append((ats, slug))
        return [Job(f"{ats}:{slug}:1", ats, company or slug, "Role", "Remote", "http://ex.com", "desc")]

    monkeypatch.setattr(fetch, "fetch_board", mock_fetch_board)

    companies = [{"ats": "greenhouse", "slug": "c1"}, {"ats": "lever", "slug": "c2"}]
    # Single worker branch with small sleep
    res = fetch_all(companies, sleep=0.01, max_workers=1)
    assert len(res) == 2
    assert len(called) == 2


def test_fetch_all_worker_error(monkeypatch):
    def mock_fetch_board(ats, slug, company=None, session=None):
        if slug == "bad":
            raise requests.RequestException("Worker failed")
        return [Job(f"{ats}:{slug}:1", ats, company or slug, "Role", "Remote", "http://ex.com", "desc")]

    monkeypatch.setattr(fetch, "fetch_board", mock_fetch_board)

    companies = [
        {"ats": "greenhouse", "slug": "good1"},
        {"ats": "greenhouse", "slug": "bad"},
        {"ats": "greenhouse", "slug": "good2"},
    ]
    res = fetch_all(companies, sleep=0, max_workers=3)
    assert len(res) == 2


def test_parsers_non_dict_elements():
    # Workable with non-dict items
    w_jobs = fetch.parse_workable("slug", "Co", {"results": ["invalid_string", 123]})
    assert w_jobs == []

    # SmartRecruiters with non-dict items
    sr_jobs = fetch.parse_smartrecruiters("slug", "Co", {"content": ["invalid_string"]})
    assert sr_jobs == []

    # SmartRecruiters with list body directly
    sr_jobs_list = fetch.parse_smartrecruiters("slug", "Co", [{"id": "1", "name": "Dev", "location": {}}])
    assert len(sr_jobs_list) == 1

    # BambooHR with non-dict items
    b_jobs = fetch.parse_bamboohr("slug", "Co", {"result": [None, 42]})
    assert b_jobs == []


def test_fetch_all_session_retry_setup(monkeypatch):
    import requests
    from unittest.mock import MagicMock

    mock_session = MagicMock()
    monkeypatch.setattr(requests, "Session", lambda: mock_session)
    monkeypatch.setattr(fetch, "fetch_board", lambda *args, **kwargs: [])

    fetch_all([{"ats": "greenhouse", "slug": "test"}], max_workers=1)

    session_mock = mock_session.__enter__.return_value
    assert session_mock.mount.call_count == 2
    # Verify adapter properties from the first mount call
    adapter = session_mock.mount.call_args_list[0][0][1]
    assert adapter.max_retries.total == 3
    assert adapter.max_retries.backoff_factor == 0.3
    assert 502 in adapter.max_retries.status_forcelist
