"""Tests for application pipeline stages (to_apply, applied, interviewing, offer, rejected), notes, test email briefing, and custom job addition."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from app import app


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    with app.test_client() as client:
        yield client


def test_api_jobs_stage_flow(client):
    # 1. Add a job
    add_resp = client.post(
        "/api/jobs/add",
        json={
            "title": "Staff Backend Engineer",
            "company": "Figma",
            "location": "Remote",
            "url": "https://figma.com/jobs/123",
            "score": 9.5,
            "stage": "to_apply",
        },
    )
    assert add_resp.status_code == 200
    data = add_resp.get_json()
    job_id = data["job_id"]
    assert job_id is not None

    # 2. Transition stage to 'interviewing'
    stage_resp = client.post(
        "/api/jobs/stage",
        json={
            "job_id": job_id,
            "stage": "interviewing",
        },
    )
    assert stage_resp.status_code == 200
    sdata = stage_resp.get_json()
    assert sdata["status"] == "success"
    assert sdata["stage"] == "interviewing"
    assert sdata["applied"] is True

    # 3. Add private candidate notes
    notes_resp = client.post(
        "/api/jobs/notes",
        json={
            "job_id": job_id,
            "notes": "Spoke with hiring manager, technical round scheduled on Friday.",
        },
    )
    assert notes_resp.status_code == 200
    ndata = notes_resp.get_json()
    assert ndata["status"] == "success"
    assert "technical round" in ndata["notes"]


def test_api_email_test_endpoint(client, monkeypatch):
    # Test with mock mailer
    monkeypatch.setenv("SMTP_PASS", "real_test_password_here")
    monkeypatch.setenv("MAIL_TO", "candidate@example.com")

    from jobhunt import mailer

    mock_send = MagicMock()
    monkeypatch.setattr(mailer, "send", mock_send)

    resp = client.post("/api/email/test")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["target_email"]
    assert mock_send.called


def test_api_jobs_stage_invalid_stage(client):
    resp = client.post("/api/jobs/stage", json={"job_id": "test:1", "stage": "invalid_stage_xyz"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["status"] == "error"
    assert "Invalid stage" in data["message"]


def test_api_add_job_score_clamping(client):
    resp = client.post(
        "/api/jobs/add",
        json={
            "title": "Principal Architect",
            "company": "Stripe",
            "score": 99.0,
        },
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["job"]["score"] == 10.0


def test_api_jobs_stages_and_stats(client):
    """Verify /api/jobs supports filtering across stages and /api/stats includes stage counts."""
    from unittest.mock import MagicMock, patch

    mock_st = MagicMock()
    mock_st.data = {
        "j1": {"title": "Job 1", "company": "A", "score": 8.5, "stage": "to_apply", "applied": False},
        "j2": {"title": "Job 2", "company": "B", "score": 9.0, "stage": "applied", "applied": True},
        "j3": {"title": "Job 3", "company": "C", "score": 7.5, "stage": "interviewing", "applied": True},
        "j4": {"title": "Job 4", "company": "D", "score": 9.5, "stage": "offer", "applied": True},
        "j5": {"title": "Job 5", "company": "E", "score": 5.0, "stage": "rejected", "applied": False},
    }
    with patch("jobhunt.web.routes.jobs.Store", return_value=mock_st):
        for stage in ("to_apply", "applied", "interviewing", "offer", "rejected", "unapplied"):
            r = client.get(f"/api/jobs?status={stage}")
            assert r.status_code == 200
            data = r.get_json()
            assert "jobs" in data

        r_stats = client.get("/api/stats")
        assert r_stats.status_code == 200
        stats = r_stats.get_json()
        assert "stages" in stats
        stages = stats["stages"]
        assert stages["to_apply"] == 1
        assert stages["applied"] == 3
        assert stages["interviewing"] == 1
        assert stages["offer"] == 1
        assert stages["rejected"] == 1


def test_asset_hash_context_processor():
    """Verify asset_hash template context processor generates mtime hash or fallback."""
    from jobhunt.web import create_app
    test_app = create_app()
    test_app.config["TESTING"] = True
    with test_app.test_request_context():
        for func in test_app.template_context_processors[None]:
            res = func()
            if isinstance(res, dict) and "asset_hash" in res:
                fn = res["asset_hash"]
                h1 = fn("css/style.css")
                assert len(h1) > 0
                h2 = fn("css/non_existent.css")
                assert h2 == "103"
                return
        assert False, "asset_hash context processor not found"




