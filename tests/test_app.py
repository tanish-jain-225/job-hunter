"""Unit test suite for Flask Web Dashboard (app.py)."""

from __future__ import annotations

import pytest

from app import app


import os


@pytest.fixture(autouse=True)
def bypass_auth_for_app_tests():
    old_val = os.environ.get("AUTH_REQUIRED")
    os.environ["AUTH_REQUIRED"] = "false"
    yield
    if old_val is None:
        os.environ.pop("AUTH_REQUIRED", None)
    else:
        os.environ["AUTH_REQUIRED"] = old_val


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_route(client):
    """Verify index route renders Light Mode dashboard HTML."""
    res = client.get("/")
    if res.status_code != 200:
        print("DIAGNOSTIC STATUS:", res.status_code)
        print("DIAGNOSTIC DATA:", res.data.decode("utf-8", errors="replace"))
    assert res.status_code == 200
    assert b"Job Hunter" in res.data
    assert b"Run Job Hunt Now" in res.data


def test_static_and_brand_assets(client):
    """Verify static CSS, JS, logo, and favicon are served with 200 OK and appropriate content types."""
    res_css = client.get("/static/css/style.css")
    assert res_css.status_code == 200
    assert "text/css" in res_css.content_type
    assert len(res_css.data) > 1000

    res_js = client.get("/static/js/app.js")
    assert res_js.status_code == 200
    assert "javascript" in res_js.content_type
    assert len(res_js.data) > 1000

    res_logo = client.get("/logo.png")
    assert res_logo.status_code == 200
    assert res_logo.content_type == "image/png"

    res_fav = client.get("/favicon.ico")
    assert res_fav.status_code in (200, 204)


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
    completed_profile = {
        "name": "Test User",
        "onboarding_completed": True,
        "skills": ["Python", "Go"],
        "target_keywords": ["Backend Engineer"],
        "email_notifications_enabled": False,
        "notification_email": "test@example.com",
        "profile_json": {"name": "Test User", "core_skills": ["Python"]},
    }
    monkeypatch.setattr(
        "jobhunt.memory.SupabaseMemory.get_user_profile", lambda self, email, token=None: completed_profile
    )
    monkeypatch.setattr("jobhunt.cli.run_pipeline", lambda **kw: 0)
    res = client.post("/api/run", json={"mock": True})
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"


def test_api_jobs_add_delete_and_unmark(client):
    """Verify custom job addition, status toggling, and deletion via API."""
    # 1. Add custom job
    res_add = client.post(
        "/api/jobs/add",
        json={
            "title": "Lead AI Architect",
            "company": "Antigravity Corp",
            "location": "San Francisco, CA",
            "url": "https://antigravity.ai/jobs/1",
            "score": 9.2,
            "applied": False,
        },
    )
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
    res_add = client.post(
        "/api/jobs/add",
        json={"title": "Principal Systems Engineer", "company": "SyncCorp", "score": 9.8, "applied": False},
    )
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


def test_api_cache_control_headers(client):
    """Verify dynamic API endpoints include security and cache headers."""
    res_stats = client.get("/api/stats")
    assert res_stats.status_code == 200
    assert "no-store" in res_stats.headers.get("Cache-Control", "")
    assert "no-cache" in res_stats.headers.get("Cache-Control", "")
    assert res_stats.headers.get("X-Content-Type-Options") == "nosniff"
    assert res_stats.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert res_stats.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    res_jobs = client.get("/api/jobs")
    assert res_jobs.status_code == 200
    assert "no-store" in res_jobs.headers.get("Cache-Control", "")


def test_api_health(client, monkeypatch):
    """Verify /api/health returns valid system diagnostic and health payload."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "job-hunter"
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data
    assert "utc_time" in data

    # Test Vercel environment detection
    monkeypatch.setenv("VERCEL", "1")
    res_vercel = client.get("/api/health")
    assert res_vercel.status_code == 200
    assert res_vercel.get_json()["environment"] == "vercel"


def test_app_get_project_root_fallback(monkeypatch):
    import app as app_module
    from pathlib import Path

    # If no candidate has templates/index.html, it returns candidates[0]
    monkeypatch.setattr(Path, "is_file", lambda self: False)
    root = app_module._get_project_root()
    assert root is not None


def test_serve_logo_missing(client, monkeypatch):
    from pathlib import Path

    monkeypatch.setattr(Path, "is_file", lambda self: False)
    res = client.get("/logo.png")
    assert res.status_code == 204


def test_app_handle_exception_and_http_exception(client):
    from werkzeug.exceptions import NotFound
    import app as app_module

    # Test HTTPException handling (e.g. NotFound)
    with app_module.app.test_request_context():
        res_http, code_http = app_module.handle_exception(NotFound("Custom Not Found"))
        assert code_http == 404
        assert res_http.get_json()["status"] == "error"
        assert res_http.get_json()["message"] == "Custom Not Found"

    # Test generic unhandled Exception handling (500)
    with app_module.app.test_request_context():
        res_gen, code_gen = app_module.handle_exception(RuntimeError("Custom internal runtime failure"))
        assert code_gen == 500
        assert res_gen.get_json()["status"] == "error"
        assert "Custom internal runtime failure" in res_gen.get_json()["message"]


def test_api_config_yaml_error(client, monkeypatch):
    import yaml

    monkeypatch.setattr(yaml, "safe_load", lambda *a, **kw: (_ for _ in ()).throw(ValueError("YAML syntax error")))
    res = client.get("/api/config")
    assert res.status_code == 200
    assert res.get_json()["companies_count"] == 0


def test_api_jobs_filters_more(client):
    # Add an applied job and an unapplied job
    client.post("/api/jobs/add", json={"title": "Applied Role", "company": "AppCo", "applied": True, "score": 8.0})
    client.post("/api/jobs/add", json={"title": "Unapplied Role", "company": "UnAppCo", "applied": False, "score": 5.0})

    # Status applied
    res_app = client.get("/api/jobs?status=applied")
    assert res_app.status_code == 200
    assert any(j["company"] == "AppCo" for j in res_app.get_json()["jobs"])
    assert not any(j["company"] == "UnAppCo" for j in res_app.get_json()["jobs"])

    # Status unapplied
    res_unapp = client.get("/api/jobs?status=unapplied")
    assert res_unapp.status_code == 200
    assert any(j["company"] == "UnAppCo" for j in res_unapp.get_json()["jobs"])

    # Min score filter
    res_min_score = client.get("/api/jobs?min_score=7.5")
    assert res_min_score.status_code == 200
    for j in res_min_score.get_json()["jobs"]:
        assert (j.get("score") or 0) >= 7.5


def test_api_run_vercel_mode(client, monkeypatch):
    completed_profile = {
        "name": "Test User",
        "onboarding_completed": True,
        "skills": ["Python"],
        "target_keywords": ["Backend Engineer"],
        "email_notifications_enabled": False,
        "notification_email": "test@example.com",
        "profile_json": {"name": "Test User", "core_skills": ["Python"]},
    }
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(
        "jobhunt.memory.SupabaseMemory.get_user_profile", lambda self, email, token=None: completed_profile
    )
    monkeypatch.setattr("jobhunt.cli.run_pipeline", lambda **kw: 0)

    # 1. Unset token -> guides to GitHub Actions
    monkeypatch.setenv("GH_TOKEN", "")
    monkeypatch.setenv("GITHUB_TOKEN", "")
    monkeypatch.setenv("GITHUB_PAT", "")
    res_guide = client.post("/api/run")
    assert res_guide.status_code == 200
    assert res_guide.get_json()["status"] == "need_github_dispatch"
    assert "actions_url" in res_guide.get_json()

    # 2. Mock mode -> runs fast mock pipeline
    res_mock = client.post("/api/run", json={"mock": True})
    assert res_mock.status_code == 200
    assert "Fast mode on Vercel" in res_mock.get_json()["message"]

    # 3. With GH_TOKEN -> dispatches to GitHub Actions
    monkeypatch.setenv("GH_TOKEN", "mock_gh_pat_token")

    class MockResp:
        status_code = 204
        text = ""

    monkeypatch.setattr("requests.post", lambda *a, **kw: MockResp())
    res_dispatch = client.post("/api/run")
    assert res_dispatch.status_code == 200
    assert res_dispatch.get_json()["status"] == "dispatched"


def test_api_run_fallback_and_error(client, monkeypatch):
    completed_profile = {
        "name": "Test User",
        "onboarding_completed": True,
        "skills": ["Python"],
        "target_keywords": ["Backend Engineer"],
        "email_notifications_enabled": False,
        "notification_email": "test@example.com",
        "profile_json": {"name": "Test User", "core_skills": ["Python"]},
    }
    monkeypatch.setattr(
        "jobhunt.memory.SupabaseMemory.get_user_profile", lambda self, email, token=None: completed_profile
    )

    # First call fails, second succeeds (fallback to keyword)
    call_count = [0]

    def mock_run_pipeline(**kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return 1
        return 0

    monkeypatch.setattr("jobhunt.cli.run_pipeline", mock_run_pipeline)
    res = client.post("/api/run", json={"mock": False})
    assert res.status_code == 200
    assert call_count[0] == 2

    # Both fail -> returns 500
    monkeypatch.setattr("jobhunt.cli.run_pipeline", lambda **kw: 2)
    res_err = client.post("/api/run", json={"mock": False})
    assert res_err.status_code == 500
    assert res_err.get_json()["status"] == "error"


def test_api_jobs_add_invalid_score_fallback(client):
    res = client.post(
        "/api/jobs/add", json={"title": "Fallback Score Dev", "company": "ScoreCo", "score": "not_a_number"}
    )
    assert res.status_code == 200
    assert res.get_json()["status"] == "success"


def test_api_sync(client):
    """Verify /api/sync returns real-time state version, metrics, breakdown, and pipeline status."""
    res = client.get("/api/sync")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "version" in data
    assert isinstance(data["version"], str)
    assert "stats" in data
    assert "tracked" in data["stats"]
    assert "applied" in data["stats"]
    assert "unapplied" in data["stats"]
    assert "shortlisted" in data["stats"]
    assert "ats_counts" in data
    assert "pipeline" in data
    assert "timestamp" in data


def test_pipeline_api_sync_dispatched_at_filtering(client, monkeypatch):
    """Verify /api/sync ignores older historical runs when dispatched_at is set."""
    from jobhunt.web.state import set_user_pipeline_state
    import time
    from datetime import datetime, timezone

    test_email = "dispatch_test@example.com"
    now_ts = time.time()
    old_run_time = "2026-08-20T10:00:00+00:00"

    monkeypatch.setattr("jobhunt.web.routes.pipeline.get_current_user_context", lambda: (test_email, "mock_token"))
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.is_configured", True)
    set_user_pipeline_state(
        test_email, running=True, step="running", message="Dispatched to GitHub Actions...", dispatched_at=now_ts
    )

    mock_history = [
        {
            "user_email": test_email,
            "run_timestamp": old_run_time,
            "jobs_scanned": 1000,
            "shortlisted": 2,
            "status": "completed",
            "logs": "Old run from days ago",
        }
    ]

    monkeypatch.setattr(
        "jobhunt.memory.SupabaseMemory.get_pipeline_history", lambda self, email, limit=1, token=None: mock_history
    )

    res = client.get("/api/sync")
    assert res.status_code == 200
    data = res.get_json()
    assert data["pipeline"]["running"] is True

    # Fresh run after dispatch
    fresh_run_time = datetime.now(timezone.utc).isoformat()
    mock_history_fresh = [
        {
            "user_email": test_email,
            "run_timestamp": fresh_run_time,
            "jobs_scanned": 1200,
            "shortlisted": 5,
            "status": "completed",
            "logs": "Cloud Radar completed: 5 shortlisted out of 1200 scanned.",
        }
    ]
    monkeypatch.setattr(
        "jobhunt.memory.SupabaseMemory.get_pipeline_history",
        lambda self, email, limit=1, token=None: mock_history_fresh,
    )

    res_fresh = client.get("/api/sync")
    assert res_fresh.status_code == 200
    data_fresh = res_fresh.get_json()
    assert data_fresh["pipeline"]["running"] is False
    assert data_fresh["pipeline"]["step"] == "completed"
    assert "Cloud Radar completed" in data_fresh["pipeline"]["message"]
