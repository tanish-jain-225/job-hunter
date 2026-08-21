"""Tests for Kanban application stages, notes, test email briefing, and custom job addition."""
from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from app import app


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with app.test_client() as client:
        yield client


def test_api_jobs_stage_flow(client):
    # 1. Add a job
    add_resp = client.post("/api/jobs/add", json={
        "title": "Staff Backend Engineer",
        "company": "Figma",
        "location": "Remote",
        "url": "https://figma.com/jobs/123",
        "score": 9.5,
        "stage": "to_apply",
    })
    assert add_resp.status_code == 200
    data = add_resp.get_json()
    job_id = data["job_id"]
    assert job_id is not None

    # 2. Transition stage to 'interviewing'
    stage_resp = client.post("/api/jobs/stage", json={
        "job_id": job_id,
        "stage": "interviewing",
    })
    assert stage_resp.status_code == 200
    sdata = stage_resp.get_json()
    assert sdata["status"] == "success"
    assert sdata["stage"] == "interviewing"
    assert sdata["applied"] is True

    # 3. Add private candidate notes
    notes_resp = client.post("/api/jobs/notes", json={
        "job_id": job_id,
        "notes": "Spoke with hiring manager, technical round scheduled on Friday.",
    })
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
