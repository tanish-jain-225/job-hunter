"""Unit tests for Supabase PostgreSQL memory module (jobhunt.memory)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jobhunt.memory import SupabaseMemory
from jobhunt.store import Store


@pytest.fixture
def mock_supabase_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock-project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "mock-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "mock-service-key")
    monkeypatch.setenv("AUTH_REQUIRED", "true")


def test_supabase_memory_is_configured(mock_supabase_env):
    mem = SupabaseMemory()
    assert mem.is_configured is True
    assert mem.url == "https://mock-project.supabase.co"
    assert mem.service_key == "mock-service-key"


def test_supabase_memory_unconfigured(monkeypatch):
    import jobhunt.auth as auth_mod
    monkeypatch.setattr(auth_mod, "_ENV_LOADED", True)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    mem = SupabaseMemory()
    assert mem.is_configured is False
    assert mem.get_user_profile("user@domain.com") is None
    assert mem.load_user_jobs("user@domain.com") == {}


def test_get_user_profile_success(mock_supabase_env):
    mem = SupabaseMemory()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{
        "email": "candidate@test.com",
        "name": "Jane Doe",
        "title": "Senior Backend Engineer",
        "skills": ["Python", "Go", "PostgreSQL"],
    }]

    with patch("requests.get", return_value=mock_resp) as mock_get:
        profile = mem.get_user_profile("candidate@test.com")
        assert profile is not None
        assert profile["name"] == "Jane Doe"
        assert "Python" in profile["skills"]
        mock_get.assert_called_once()


def test_upsert_user_profile(mock_supabase_env):
    mem = SupabaseMemory()
    mock_resp = MagicMock()
    mock_resp.status_code = 201

    with patch("requests.post", return_value=mock_resp) as mock_post:
        ok = mem.upsert_user_profile("candidate@test.com", {
            "name": "Jane Doe",
            "title": "Staff Engineer",
            "experience_years": 8,
        })
        assert ok is True
        mock_post.assert_called_once()


def test_load_and_save_user_jobs(mock_supabase_env):
    mem = SupabaseMemory()
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = [
        {
            "job_id": "greenhouse:stripe:101",
            "company": "Stripe",
            "title": "Backend Engineer",
            "location": "Remote",
            "score": 9.0,
            "applied": True,
        }
    ]

    with patch("requests.get", return_value=mock_get_resp):
        jobs = mem.load_user_jobs("candidate@test.com")
        assert len(jobs) == 1
        assert "greenhouse:stripe:101" in jobs
        assert jobs["greenhouse:stripe:101"]["applied"] is True

    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 201
    with patch("requests.post", return_value=mock_post_resp):
        ok = mem.save_user_job("candidate@test.com", {
            "job_id": "lever:acme:202",
            "company": "Acme",
            "title": "Staff SRE",
            "score": 8.8,
        })
        assert ok is True


def test_bulk_upsert_and_mark_applied(mock_supabase_env):
    mem = SupabaseMemory()
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 201
    with patch("requests.post", return_value=mock_post_resp):
        count = mem.bulk_upsert_user_jobs("candidate@test.com", [
            {"job_id": "ashby:openai:301", "company": "OpenAI", "title": "Research Engineer"},
            {"job_id": "ashby:openai:302", "company": "OpenAI", "title": "Systems Engineer"},
        ])
        assert count == 2

    mock_patch_resp = MagicMock()
    mock_patch_resp.status_code = 204
    with patch("requests.patch", return_value=mock_patch_resp):
        ok = mem.set_job_applied("candidate@test.com", "ashby:openai:301", applied=True)
        assert ok is True


def test_delete_user_job(mock_supabase_env):
    mem = SupabaseMemory()
    mock_del_resp = MagicMock()
    mock_del_resp.status_code = 204
    with patch("requests.delete", return_value=mock_del_resp):
        ok = mem.delete_user_job("candidate@test.com", "ashby:openai:301")
        assert ok is True


def test_pipeline_runs_history(mock_supabase_env):
    mem = SupabaseMemory()
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 201
    with patch("requests.post", return_value=mock_post_resp):
        ok = mem.record_pipeline_run("candidate@test.com", {
            "scanned": 450,
            "matched": 12,
            "shortlisted": 5,
            "status": "completed",
            "logs": "Successful scan",
        })
        assert ok is True

    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = [
        {"id": 1, "user_email": "candidate@test.com", "jobs_scanned": 450, "shortlisted": 5}
    ]
    with patch("requests.get", return_value=mock_get_resp):
        history = mem.get_pipeline_history("candidate@test.com")
        assert len(history) == 1
        assert history[0]["jobs_scanned"] == 450


def test_store_integration_with_supabase_memory(mock_supabase_env, tmp_path):
    path = tmp_path / "seen.json"
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = [
        {
            "job_id": "greenhouse:stripe:999",
            "company": "Stripe",
            "title": "Infrastructure Engineer",
            "score": 9.2,
            "applied": False,
        }
    ]

    with patch("requests.get", return_value=mock_get_resp):
        st = Store(path, user_email="candidate@test.com", token="mock-jwt-token")
        assert "greenhouse:stripe:999" in st.data
        assert st.data["greenhouse:stripe:999"]["title"] == "Infrastructure Engineer"

    # Marking applied should trigger Supabase update
    mock_patch_resp = MagicMock()
    mock_patch_resp.status_code = 204
    with patch("requests.patch", return_value=mock_patch_resp) as mock_patch:
        st.mark_applied("greenhouse:stripe:999")
        assert st.data["greenhouse:stripe:999"]["applied"] is True
        mock_patch.assert_called_once()


def test_supabase_memory_session_retry_setup(monkeypatch):
    import sys
    import jobhunt.memory as mem_mod

    # Temporarily delete pytest from sys.modules check to trigger real session creation
    monkeypatch.delitem(sys.modules, "pytest", raising=False)
    monkeypatch.setattr(mem_mod, "_SESSION", None)

    sess = mem_mod._get_session()

    import requests
    from requests.adapters import HTTPAdapter
    assert isinstance(sess, requests.Session)
    assert "https://" in sess.adapters
    adapter = sess.adapters["https://"]
    assert isinstance(adapter, HTTPAdapter)
    assert adapter.max_retries.total == 3
    assert adapter.max_retries.backoff_factor == 0.5
    assert 502 in adapter.max_retries.status_forcelist

