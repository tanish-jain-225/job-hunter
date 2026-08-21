"""Targeted unit tests covering edge cases, fallbacks, and error handlers across all modules."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from app import app, _get_store_version, _get_project_root, _get_user_pipeline_state
from jobhunt import auth, cli, memory


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    app.config["TESTING"] = True
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setattr("jobhunt.store.get_writable_path", lambda p: tmp_path / Path(p).name)
    with app.test_client() as client:
        yield client


# ==============================================================================
# 1. app.py Edge Cases & Error Boundaries
# ==============================================================================

def test_app_get_project_root_import_error():
    with patch("builtins.__import__", side_effect=ImportError("No module named jobhunt")):
        root = _get_project_root()
        assert isinstance(root, Path)


def test_app_store_version_exception():
    mock_store = MagicMock()
    mock_store.data = None
    version = _get_store_version(mock_store)
    assert isinstance(version, str)


def test_app_user_pipeline_state_retrieval():
    st1 = _get_user_pipeline_state("user_test_state@example.com")
    assert st1["running"] is False
    assert st1["step"] == "idle"


def test_app_api_profile_post_without_email(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app._get_current_user_context", lambda: (None, None))
    resp = client.post("/api/profile", json={"name": "No Email User"})
    assert resp.status_code == 400
    assert "Authenticated user email required" in resp.json["message"]


def test_app_api_profile_post_skills_extraction_from_resume_text(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app._get_current_user_context", lambda: ("candidate_extract@example.com", "fake-token"))
    resp = client.post("/api/profile", json={
        "name": "Alex",
        "resume_text": "Experienced building applications with Python, PostgreSQL, Docker, and REST APIs at scale.",
        "skills": [],
    })
    assert resp.status_code == 200
    data = resp.json
    assert "Python" in data["profile"]["skills"]
    assert "PostgreSQL" in data["profile"]["skills"]


def test_app_api_history_endpoint(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app._get_current_user_context", lambda: ("history_user@example.com", "token123"))
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.is_configured", True)
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.get_pipeline_history", lambda self, email, limit=15, token=None: [
        {"id": 1, "jobs_scanned": 10, "status": "completed"}
    ])
    resp = client.get("/api/history")
    assert resp.status_code == 200
    assert len(resp.json["history"]) == 1


def test_app_api_jobs_stage_missing_and_not_found(client):
    # Missing job_id
    r1 = client.post("/api/jobs/stage", json={"job_id": "", "stage": "applied"})
    assert r1.status_code == 400

    # Job not found
    r2 = client.post("/api/jobs/stage", json={"job_id": "nonexistent:job:123", "stage": "interviewing"})
    assert r2.status_code == 404


def test_app_api_jobs_notes_missing_and_not_found(client):
    # Missing job_id
    r1 = client.post("/api/jobs/notes", json={"job_id": "", "notes": "notes here"})
    assert r1.status_code == 400

    # Job not found
    r2 = client.post("/api/jobs/notes", json={"job_id": "nonexistent:job:999", "notes": "notes here"})
    assert r2.status_code == 404


def test_app_api_email_test_missing_target_and_smtp(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app._get_current_user_context", lambda: (None, None))
    monkeypatch.setenv("MAIL_TO", "")
    monkeypatch.setenv("SMTP_USER", "")
    monkeypatch.setattr("jobhunt.cli._load_profile", lambda *a, **kw: {})
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.get_user_profile", lambda *a, **kw: None)
    r1 = client.post("/api/email/test")
    assert r1.status_code == 400
    assert "No destination email address found" in r1.json["message"]

    # Target email provided but SMTP not configured
    monkeypatch.setattr("app._get_current_user_context", lambda: ("target@example.com", None))
    monkeypatch.setenv("SMTP_PASS", "")
    r2 = client.post("/api/email/test")
    assert r2.status_code == 400
    assert "SMTP is not configured" in r2.json["message"]


def test_app_api_email_test_delivery_exception(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app._get_current_user_context", lambda: ("target@example.com", None))
    monkeypatch.setenv("SMTP_PASS", "valid-app-password")
    monkeypatch.setattr("jobhunt.mailer.send", MagicMock(side_effect=Exception("Connection refused by SMTP server")))
    r = client.post("/api/email/test")
    assert r.status_code == 500
    assert "SMTP delivery failed" in r.json["message"]


def test_app_api_run_profile_stub_guard(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app._get_current_user_context", lambda: ("stub_user@example.com", "token"))
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.is_configured", property(lambda self: True))
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.get_user_profile", lambda *a, **kw: {
        "onboarding_completed": False,
        "name": "",
        "skills": [],
        "target_keywords": []
    })
    r = client.post("/api/run", json={"mock": True})
    assert r.status_code == 400
    assert "complete your candidate profile" in r.json["message"]


def test_app_api_run_pipeline_exception_handling(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app._get_current_user_context", lambda: ("user_err@example.com", "token"))
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.is_configured", property(lambda self: True))
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.get_user_profile", lambda *a, **kw: {
        "onboarding_completed": True,
        "name": "Tester",
        "title": "Engineer",
        "skills": ["Python"],
        "target_keywords": ["Engineer"],
        "education": "BS",
        "experience_years": 3,
        "exclude_keywords": ["Manager"],
    })
    monkeypatch.setattr("jobhunt.cli.run_pipeline", MagicMock(side_effect=RuntimeError("Fatal pipeline explosion")))
    r = client.post("/api/run", json={"mock": True})
    assert r.status_code == 500
    assert "Pipeline failed" in r.json["message"]


def test_app_api_add_with_ai_scoring(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app._get_current_user_context", lambda: ("user_add@example.com", "token"))
    monkeypatch.setattr("jobhunt.llm.resolve", lambda stage: (MagicMock(name="prov"), "model-test"))

    def mock_screen(jobs, prof, **kwargs):
        for j in jobs:
            j.score = 8.8
            j.reason = "AI fit match"

    def mock_draft(jobs, prof, **kwargs):
        for j in jobs:
            j.draft = {"fit_summary": "Great fit summary"}

    monkeypatch.setattr("jobhunt.llm.screen", mock_screen)
    monkeypatch.setattr("jobhunt.llm.draft", mock_draft)

    r = client.post("/api/jobs/add", json={
        "title": "Staff Infrastructure Engineer",
        "company": "Cloudflare",
        "location": "Remote",
        "description": "Distributed systems, edge computing, Go, and Linux systems engineering.",
        "run_ai": True,
    })
    assert r.status_code == 200
    assert r.json["job"]["score"] == 8.8
    assert r.json["job"]["draft"]["fit_summary"] == "Great fit summary"


def test_app_api_resume_upload_pdf_multipart_and_smart_fallback(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app._get_current_user_context", lambda: ("resume_user@example.com", "token"))
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.is_configured", property(lambda self: True))
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.upsert_user_profile", lambda *a, **kw: True)

    # Simulate LLM raising error to trigger smart local parsing
    monkeypatch.setattr("jobhunt.llm.resolve", MagicMock(side_effect=Exception("Quota exceeded")))

    fake_pdf_content = b"%PDF-1.4 ... Fake PDF header ... Candidate Resume: Jane Doe. Python, SQL, REST APIs, Docker, PostgreSQL."
    data = {
        "file": (io.BytesIO(fake_pdf_content), "jane_resume.pdf")
    }
    r = client.post("/api/resume/upload", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.json["profile"]["resume_filename"] == "jane_resume.pdf"
    assert "Python" in r.json["profile"]["skills"]


def test_app_api_resume_upload_unauthenticated(client, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("app._get_current_user_context", lambda: (None, None))
    r = client.post("/api/resume/upload", json={"resume_text": "hello"})
    assert r.status_code == 401


# ==============================================================================
# 2. jobhunt/memory.py String Normalization & Error Resilience
# ==============================================================================

def test_memory_upsert_string_skills_and_targets(monkeypatch: pytest.MonkeyPatch):
    mem = memory.SupabaseMemory()
    mem.url = "https://example.supabase.co"
    mem.anon_key = "anon-key-123"

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    monkeypatch.setattr(requests, "post", lambda *a, **kw: mock_resp)

    success = mem.upsert_user_profile("user_str@example.com", {
        "name": "String Skills User",
        "skills": "Python, Go, Docker , Kubernetes",
        "target_keywords": "Backend Engineer, Systems Engineer",
        "exclude_keywords": "Manager, Director",
        "experience_years": "5",
    })
    assert success is True


def test_memory_network_error_resilience(monkeypatch: pytest.MonkeyPatch):
    mem = memory.SupabaseMemory()
    mem.url = "https://example.supabase.co"
    mem.anon_key = "anon-key-123"

    def mock_get_error(*a, **kw):
        raise requests.RequestException("Timeout reaching Supabase")

    monkeypatch.setattr(requests, "get", mock_get_error)
    assert mem.get_user_profile("err_user@example.com") is None
    assert mem.load_user_jobs("err_user@example.com") == {}
    assert mem.get_pipeline_history("err_user@example.com") == []

    def mock_post_error(*a, **kw):
        raise requests.RequestException("Write timeout")

    monkeypatch.setattr(requests, "post", mock_post_error)
    assert mem.upsert_user_profile("err_user@example.com", {"name": "Test"}) is False
    assert mem.save_user_job("err_user@example.com", {"job_id": "ats:1"}) is False
    assert mem.bulk_upsert_user_jobs("err_user@example.com", [{"job_id": "ats:1"}]) == 0
    assert mem.record_pipeline_run("err_user@example.com", {}) is False


# ==============================================================================
# 3. jobhunt/cli.py CLI multi-run & Resolve Relative
# ==============================================================================

def test_cli_cmd_multi_run(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("jobhunt.multi.run_multi_user_pipeline", lambda **kw: {"status": "success"})
    args = MagicMock()
    args.config = None
    args.mock = True
    args.scorer = "keyword"
    args.send = False
    exit_code = cli.cmd_multi_run(args)
    assert exit_code == 0


def test_cli_resolve_relative_vercel(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("VERCEL", "1")
    p = cli._resolve_relative("config.example.yaml")
    assert isinstance(p, Path)


# ==============================================================================
# 4. jobhunt/auth.py Caching & Expiry
# ==============================================================================

def test_auth_token_cache_expiration():
    auth.clear_token_cache()
    token = "test_token_cache_123"
    token_hash = auth.hashlib.sha256(token.encode("utf-8")).hexdigest()

    # Place an expired token in cache
    auth._TOKEN_CACHE[token_hash] = ({"id": "cached_user", "email": "cached@example.com"}, auth.time.time() - 10)

    # verify_token should evict expired entry
    _ = auth.verify_token(token)
    assert token_hash not in auth._TOKEN_CACHE
