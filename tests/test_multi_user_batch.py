"""Test multi-user single-pass automated batch pipeline and isolated user execution."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

import jobhunt.multi
from jobhunt.multi import run_multi_user_pipeline


@pytest.fixture(autouse=True)
def mock_multi_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock-multi.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "mock-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "mock-service-key")
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")


def test_multi_user_pipeline_mock_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):

    # Ensure memory returns 2 distinct active profiles
    mock_users = [
        {
            "email": "user1@example.com",
            "name": "Candidate Alpha",
            "title": "Backend Engineer",
            "skills": ["Python", "PostgreSQL", "Go"],
            "target_keywords": ["Backend", "Software Engineer"],
            "exclude_keywords": ["Senior Director"],
            "onboarding_completed": True,
            "email_notifications_enabled": False,
        },
        {
            "email": "user2@example.com",
            "name": "Candidate Beta",
            "title": "Data Scientist",
            "skills": ["Machine Learning", "Python", "SQL"],
            "target_keywords": ["Data Scientist", "Machine Learning"],
            "exclude_keywords": ["Frontend"],
            "onboarding_completed": True,
            "email_notifications_enabled": False,
        }
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_users

    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    res = run_multi_user_pipeline(mock=True, scorer="keyword")
    assert res["status"] == "success"
    assert res["users_processed"] == 2
    assert res["total_jobs_scanned"] > 0


def test_multi_user_pipeline_no_raw_jobs(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("jobhunt.multi.fetch_all_mock", lambda: [])
    res = run_multi_user_pipeline(mock=True)
    assert res["status"] == "no_jobs"
    assert res["users_processed"] == 0


def test_multi_user_pipeline_fallback_to_local_profile(monkeypatch: pytest.MonkeyPatch):
    # Mock Supabase returning empty
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = []
    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    # Mock local profile loader
    monkeypatch.setattr("jobhunt.cli._load_profile", lambda *a, **kw: {
        "name": "Local Candidate",
        "email": "local@test.com",
        "current_title": "Backend Engineer",
        "core_skills": ["Python", "Go"],
        "target_titles": ["Backend Engineer"],
    })

    res = run_multi_user_pipeline(mock=True, scorer="keyword")
    assert res["status"] == "success"
    assert res["users_processed"] >= 1


def test_multi_user_pipeline_supabase_query_exception(monkeypatch: pytest.MonkeyPatch):
    # Simulate network exception when querying user profiles
    def raise_err(*args, **kwargs):
        raise ConnectionError("Supabase connection timeout")

    monkeypatch.setattr(requests, "get", raise_err)
    monkeypatch.setattr("jobhunt.cli._load_profile", lambda *a, **kw: {
        "name": "Local Candidate",
        "email": "local@test.com",
        "current_title": "Backend Engineer",
    })

    res = run_multi_user_pipeline(mock=True, scorer="keyword")
    assert res["status"] == "success"
    assert res["users_processed"] >= 1


def test_multi_user_pipeline_with_email_and_drafting(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr("jobhunt.store.get_writable_path", lambda p: tmp_path / Path(p).name)
    user_email = f"fresh_user_{tmp_path.name}@example.com"
    mock_users = [
        {
            "email": user_email,
            "name": "Email Candidate",
            "title": "Software Engineer",
            "skills": ["Go", "Java", "Kubernetes"],
            "target_keywords": ["Software Engineer", "Backend"],
            "exclude_keywords": [],
            "onboarding_completed": True,
            "email_notifications_enabled": True,
            "notification_email": user_email,
            "experience_years": 4,
            "education": "BS CS",
        }
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_users
    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    # Set mock SMTP pass and not Vercel
    monkeypatch.setenv("SMTP_PASS", "valid-app-password")
    monkeypatch.delenv("VERCEL", raising=False)

    mailer_mock = MagicMock()
    monkeypatch.setattr("jobhunt.mailer.send", mailer_mock)

    # Mock memory record_pipeline_run
    mock_record_run = MagicMock()
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.record_pipeline_run", mock_record_run)

    res = run_multi_user_pipeline(mock=True, scorer="keyword")
    assert res["status"] == "success"
    assert res["users_processed"] == 1
    assert res["total_shortlisted"] > 0
    assert mailer_mock.called


def test_multi_user_pipeline_llm_mode_with_mock_provider(monkeypatch: pytest.MonkeyPatch):
    mock_users = [
        {
            "email": "llm_user@example.com",
            "name": "LLM Candidate",
            "title": "Backend Engineer",
            "skills": ["Go", "Python"],
            "target_keywords": ["Backend Engineer", "Software Engineer"],
            "onboarding_completed": True,
            "email_notifications_enabled": False,
        }
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_users
    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    mock_provider = MagicMock()
    mock_provider.name = "mock_prov"
    # Mock complete to return valid screen json array
    mock_provider.complete.side_effect = [
        '[{"job_id": "greenhouse:acme-edge:5501001", "score": 9.0, "reason": "Great fit"}]',
        '{"fit_summary": "Strong fit", "cover_note": "Cover text", "cold_outreach": "Outreach text", "tailored_bullets": ["Bullet 1"], "matching_skills": ["Go"], "gaps": [], "questions_to_ask": []}',
    ]

    monkeypatch.setattr("jobhunt.multi.resolve", lambda stage: (mock_provider, "mock-model"))

    res = run_multi_user_pipeline(mock=True, scorer="llm")
    assert res["status"] == "success"
    assert res["users_processed"] == 1


def test_multi_user_pipeline_candidate_error_isolation(monkeypatch: pytest.MonkeyPatch):
    # Two users; first one raises an exception during prefilter, second succeeds
    mock_users = [
        {"email": "broken@example.com", "name": "Broken User"},
        {"email": "good@example.com", "name": "Good User", "skills": ["Python"], "target_keywords": ["Software Engineer"]},
    ]
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_users
    monkeypatch.setattr(requests, "get", lambda *a, **kw: mock_resp)

    orig_prefilter = jobhunt.multi.prefilter
    calls = []

    def mock_prefilter(jobs, filters):
        calls.append(filters)
        if len(calls) == 1:
            raise RuntimeError("Unexpected candidate parsing failure")
        return orig_prefilter(jobs, filters)

    monkeypatch.setattr("jobhunt.multi.prefilter", mock_prefilter)

    res = run_multi_user_pipeline(mock=True, scorer="keyword")
    assert res["status"] == "success"
    assert res["users_processed"] == 2
