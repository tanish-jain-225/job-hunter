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


def test_fetch_all_concurrent(monkeypatch):
    def mock_fetch_board(ats, slug, company=None, session=None):
        return [
            Job(f"{ats}:{slug}:1", ats, company or slug, "Role", "Remote", "http://ex.com", "desc")
        ]

    monkeypatch.setattr(fetch, "fetch_board", mock_fetch_board)

    companies = [
        {"ats": "greenhouse", "slug": "c1", "name": "C1"},
        {"ats": "lever", "slug": "c2", "name": "C2"},
        {"ats": "ashby", "slug": "c3", "name": "C3"},
    ]
    results = fetch_all(companies, sleep=0, max_workers=4)
    assert len(results) == 3

