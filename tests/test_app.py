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


def test_api_jobs_add_delete_and_unmark(client):
    """Verify custom job addition, status toggling, and deletion via API."""
    # 1. Add custom job
    res_add = client.post("/api/jobs/add", json={
        "title": "Lead AI Architect",
        "company": "Antigravity Corp",
        "location": "San Francisco, CA",
        "url": "https://antigravity.ai/jobs/1",
        "score": 9.2,
        "applied": False
    })
    assert res_add.status_code == 200
    add_data = res_add.get_json()
    assert add_data["status"] == "success"
    job_id = add_data["job_id"]
    assert "antigravitycorp" in job_id

    # 2. Verify job appears in /api/jobs and /api/jobs?status=unapplied
    res_list = client.get("/api/jobs?status=unapplied")
    assert res_list.status_code == 200
    job_ids = [j["job_id"] for j in res_list.get_json()["jobs"]]
    assert job_id in job_ids

    # 3. Mark applied
    res_mark = client.post("/api/applied", json={"job_id": job_id, "action": "mark"})
    assert res_mark.status_code == 200
    assert res_mark.get_json()["status"] == "success"

    # 4. Unmark applied
    res_unmark = client.post("/api/applied", json={"job_id": job_id, "action": "unmark"})
    assert res_unmark.status_code == 200
    assert res_unmark.get_json()["status"] == "success"

    # 5. Delete job
    res_delete = client.post("/api/delete", json={"job_id": job_id})
    assert res_delete.status_code == 200
    assert res_delete.get_json()["status"] == "success"

    # Verify job is removed
    res_after = client.get("/api/jobs")
    job_ids_after = [j["job_id"] for j in res_after.get_json()["jobs"]]
    assert job_id not in job_ids_after


def test_api_end_to_end_digest_rebuild(client):
    """Verify force rebuild of digest HTML dynamically syncs shortlist changes."""
    # Add high-score job
    res_add = client.post("/api/jobs/add", json={
        "title": "Principal Systems Engineer",
        "company": "SyncCorp",
        "score": 9.8,
        "applied": False
    })
    assert res_add.status_code == 200

    # Request digest with force rebuild timestamp
    res_digest = client.get("/api/digest?t=123456789")
    assert res_digest.status_code == 200
    html_text = res_digest.data.decode("utf-8")
    assert "SyncCorp" in html_text or "Principal Systems Engineer" in html_text


def test_api_delete_errors(client):
    """Verify /api/delete 400 and 404 responses."""
    # Missing job_id
    res_missing = client.post("/api/delete", json={})
    assert res_missing.status_code == 400

    # Unknown job_id
    res_unknown = client.post("/api/delete", json={"job_id": "nonexistent:999"})
    assert res_unknown.status_code == 404


def test_api_jobs_add_missing_fields(client):
    """Verify /api/jobs/add 400 when title or company is missing."""
    res_no_title = client.post("/api/jobs/add", json={"company": "Acme"})
    assert res_no_title.status_code == 400

    res_no_company = client.post("/api/jobs/add", json={"title": "Engineer"})
    assert res_no_company.status_code == 400


def test_logo_route(client):
    """Verify /logo.png route returns logo file or 204."""
    res = client.get("/logo.png")
    assert res.status_code in (200, 204)


def test_api_config(client):
    """Verify /api/config endpoint returns configuration summary."""
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "companies_count" in data
    assert "filters" in data
    assert "score_threshold" in data


def test_api_export_csv(client):
    """Verify /api/export/csv endpoint serves CSV download file."""
    res = client.get("/api/export/csv")
    assert res.status_code == 200
    assert res.mimetype == "text/csv"
    assert "attachment" in res.headers.get("Content-Disposition", "")
    assert b"job_id" in res.data


def test_api_jobs_ats_and_sorting(client):
    """Verify /api/jobs filtering by ats and sorting options."""
    # Add custom jobs with distinct attributes
    client.post("/api/jobs/add", json={"title": "Alpha Dev", "company": "AAA", "ats": "greenhouse", "score": 6.0})
    client.post("/api/jobs/add", json={"title": "Beta Dev", "company": "BBB", "ats": "lever", "score": 9.5})

    # Test ATS filter
    res_gh = client.get("/api/jobs?ats=greenhouse")
    assert res_gh.status_code == 200
    for j in res_gh.get_json()["jobs"]:
        assert j.get("ats", "").lower() == "greenhouse" or "greenhouse" in j.get("job_id", "")

    # Test Sort by Score
    res_score_sort = client.get("/api/jobs?sort=score")
    assert res_score_sort.status_code == 200
    scores = [j.get("score", 0) for j in res_score_sort.get_json()["jobs"] if j.get("score") is not None]
    assert scores == sorted(scores, reverse=True)

    # Test Sort by Company
    res_comp_sort = client.get("/api/jobs?sort=company")
    assert res_comp_sort.status_code == 200
    companies = [j.get("company", "").lower() for j in res_comp_sort.get_json()["jobs"]]
    assert companies == sorted(companies)



