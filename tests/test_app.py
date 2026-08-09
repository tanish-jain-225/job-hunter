"""Unit test suite for Flask Web Dashboard (app.py)."""
from __future__ import annotations

import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_route(client):
    """Verify index route renders Light Mode dashboard HTML."""
    res = client.get("/")
    assert res.status_code == 200
    assert b"Job Hunter" in res.data
    assert b"Run Job Hunt Now" in res.data


def test_api_stats(client):
    """Verify /api/stats endpoint returns JSON statistics."""
    res = client.get("/api/stats")
    assert res.status_code == 200
    data = res.get_json()
    assert "tracked" in data
    assert "emailed" in data
    assert "applied" in data


def test_api_jobs(client):
    """Verify /api/jobs endpoint returns structured job list with status & search filters."""
    res = client.get("/api/jobs")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "count" in data
    assert isinstance(data["jobs"], list)

    # Test status filter
    res_shortlisted = client.get("/api/jobs?status=shortlisted")
    assert res_shortlisted.status_code == 200
    shortlisted_data = res_shortlisted.get_json()
    for job in shortlisted_data["jobs"]:
        assert (job.get("score") or 0) >= 7.0

    # Test search filter
    res_search = client.get("/api/jobs?search=nonexistentcompanyxyz123")
    assert res_search.status_code == 200
    assert res_search.get_json()["count"] == 0


def test_api_digest_fallback(client, tmp_path, monkeypatch):
    """Verify /api/digest returns valid HTML response."""
    res = client.get("/api/digest")
    assert res.status_code == 200
    lower_data = res.data.lower()
    assert b"doctype html" in lower_data or b"html" in lower_data


def test_api_applied_missing_id(client):
    """Verify /api/applied returns 400 if job_id missing."""
    res = client.post("/api/applied", json={})
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"


def test_api_applied_unknown_id(client, tmp_path, monkeypatch):
    """Verify /api/applied returns 404 error if job_id not in store."""
    res = client.post("/api/applied", json={"job_id": "greenhouse:fake:999"})
    assert res.status_code == 404
    data = res.get_json()
    assert data["status"] == "error"


def test_api_run_mock(client, monkeypatch):
    """Verify /api/run with mock mode executes pipeline cleanly."""
    monkeypatch.setattr("jobhunt.cli.cmd_run", lambda args: 0)
    res = client.post("/api/run", json={"mock": True})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
