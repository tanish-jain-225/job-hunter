"""Unit tests for jobhunt.fetch module (HTTP calls, parsers, and error handling)."""
from __future__ import annotations

import pytest
import requests

from jobhunt import fetch
from jobhunt.fetch import Job, fetch_all, fetch_board


class DummyResponse:
    def __init__(self, status_code: int, json_data: dict | list | None = None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


class DummySession:
    def __init__(self, response: DummyResponse | None = None, raise_exc: Exception | None = None):
        self.response = response
        self.raise_exc = raise_exc

    def get(self, url, headers=None, timeout=None):
        if self.raise_exc:
            raise self.raise_exc
        return self.response


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
