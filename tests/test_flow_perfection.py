"""Comprehensive validation tests for 10/10 perfection enhancements."""

import json
import os
import time
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from app import app as flask_app
from jobhunt.providers import (
    AnthropicProvider,
    GeminiProvider,
    OpenAICompatProvider,
    LLMError,
)
from jobhunt.fetch import detect_ats_from_url, fetch_all, Job
from jobhunt.llm import generate_followup_note
from jobhunt.multi import run_multi_user_pipeline
from jobhunt.cli import run_pipeline
from jobhunt.web.state import (
    publish_user_pipeline_log,
    get_user_pipeline_logs,
    clear_user_pipeline_logs,
    set_user_pipeline_state,
)


@pytest.fixture(autouse=True)
def bypass_auth_for_perfection_tests():
    old_val = os.environ.get("AUTH_REQUIRED")
    os.environ["AUTH_REQUIRED"] = "false"
    yield
    if old_val is None:
        os.environ.pop("AUTH_REQUIRED", None)
    else:
        os.environ["AUTH_REQUIRED"] = old_val


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from jobhunt.memory import invalidate_user_cache
    invalidate_user_cache()
    flask_app.config["TESTING"] = True
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.is_configured", property(lambda self: False))
    monkeypatch.setattr("jobhunt.store.SupabaseMemory.is_configured", property(lambda self: False))
    monkeypatch.setattr("jobhunt.web.routes.pipeline.SupabaseMemory.is_configured", property(lambda self: False))
    seen_tmp = tmp_path / "seen.json"
    seen_tmp.write_text("{}", encoding="utf-8")
    target_fn = lambda p: tmp_path / Path(p).name
    monkeypatch.setattr("jobhunt.store.get_writable_path", target_fn)
    monkeypatch.setattr("jobhunt.web.routes.jobs.get_writable_path", target_fn)
    monkeypatch.setattr("jobhunt.web.routes.pipeline.get_writable_path", target_fn)
    with flask_app.test_client() as client:
        yield client


def test_detect_ats_from_url_all():
    """Test URL auto-detection across all 9 supported ATS platforms and edge cases."""
    # Greenhouse
    gh1 = detect_ats_from_url("https://boards.greenhouse.io/stripe")
    assert gh1 is not None and gh1["ats"] == "greenhouse" and gh1["slug"] == "stripe" and gh1["name"] == "Stripe"

    gh2 = detect_ats_from_url("https://job-boards.greenhouse.io/razorpay")
    assert gh2 is not None and gh2["ats"] == "greenhouse" and gh2["slug"] == "razorpay"

    gh3 = detect_ats_from_url("https://boards-api.greenhouse.io/v1/boards/airbnb")
    assert gh3 is not None and gh3["ats"] == "greenhouse" and gh3["slug"] == "airbnb"

    # Lever
    lev1 = detect_ats_from_url("https://jobs.lever.co/meesho")
    assert lev1 is not None and lev1["ats"] == "lever" and lev1["slug"] == "meesho"

    lev2 = detect_ats_from_url("https://api.lever.co/v0/postings/atlassian")
    assert lev2 is not None and lev2["ats"] == "lever" and lev2["slug"] == "atlassian"

    # Ashby
    ash1 = detect_ats_from_url("https://jobs.ashbyhq.com/postman")
    assert ash1 is not None and ash1["ats"] == "ashby" and ash1["slug"] == "postman"

    ash2 = detect_ats_from_url("https://api.ashbyhq.com/posting-api/job-board/sentry")
    assert ash2 is not None and ash2["ats"] == "ashby" and ash2["slug"] == "sentry"

    # Workable
    wrk1 = detect_ats_from_url("https://apply.workable.com/zepto")
    assert wrk1 is not None and wrk1["ats"] == "workable" and wrk1["slug"] == "zepto"

    wrk2 = detect_ats_from_url("https://invideo.workable.com")
    assert wrk2 is not None and wrk2["ats"] == "workable" and wrk2["slug"] == "invideo"

    # SmartRecruiters
    sr1 = detect_ats_from_url("https://jobs.smartrecruiters.com/Square")
    assert sr1 is not None and sr1["ats"] == "smartrecruiters" and sr1["slug"] == "Square"

    sr2 = detect_ats_from_url("https://careers.smartrecruiters.com/v1/companies/visa")
    assert sr2 is not None and sr2["ats"] == "smartrecruiters" and sr2["slug"] == "visa"

    # BambooHR
    bhr = detect_ats_from_url("https://swiggy.bamboohr.com/careers")
    assert bhr is not None and bhr["ats"] == "bamboohr" and bhr["slug"] == "swiggy"

    # Recruitee
    rec1 = detect_ats_from_url("https://tacobell.recruitee.com")
    assert rec1 is not None and rec1["ats"] == "recruitee" and rec1["slug"] == "tacobell"

    rec2 = detect_ats_from_url("https://careers.recruitee.com/hotjar")
    assert rec2 is not None and rec2["ats"] == "recruitee" and rec2["slug"] == "hotjar"

    # Breezy
    brz = detect_ats_from_url("https://cleartax.breezy.hr")
    assert brz is not None and brz["ats"] == "breezy" and brz["slug"] == "cleartax"

    # Pinpoint
    pin1 = detect_ats_from_url("https://hyperline.pinpoint.work")
    assert pin1 is not None and pin1["ats"] == "pinpoint" and pin1["slug"] == "hyperline"

    pin2 = detect_ats_from_url("https://linear.pinpointhq.com")
    assert pin2 is not None and pin2["ats"] == "pinpoint" and pin2["slug"] == "linear"

    # Edge cases
    assert detect_ats_from_url("https://example.com/jobs") is None
    assert detect_ats_from_url("") is None
    assert detect_ats_from_url(None) is None  # type: ignore
    assert detect_ats_from_url(123) is None  # type: ignore


def test_fetch_all_with_custom_companies():
    """Test fetch_all merges and dedupes custom company boards."""
    custom = [
        {"ats": "greenhouse", "slug": "stripe", "name": "Stripe"},
        {"ats": "greenhouse", "slug": "stripe", "name": "Duplicate Stripe"},
    ]
    with patch("jobhunt.fetch.fetch_board", return_value=[Job(job_id="gh:stripe:1", ats="greenhouse", company="Stripe", title="Dev", location="Remote", url="http://x", description="test description")]):
        jobs = fetch_all([], custom_companies=custom, max_workers=1)
        assert len(jobs) == 1
        assert jobs[0].company == "Stripe"


def test_generate_followup_note():
    """Test AI follow-up generator produces structured templates."""
    followup = generate_followup_note(
        job_title="Senior Backend Engineer",
        company="Stripe",
        candidate_name="Alex Doe",
        applied_on="2026-08-25",
        stage="applied",
    )
    assert isinstance(followup, dict)
    assert "Senior Backend Engineer" in followup["subject"]
    assert "Alex Doe" in followup["subject"]
    assert "Stripe" in followup["email_body"]
    assert "Alex Doe" in followup["email_body"]
    assert "Stripe" in followup["linkedin_dm"]


def test_pipeline_log_streaming_buffers():
    """Test thread-safe user pipeline log buffer lifecycle."""
    email = "test-streamer@example.com"
    clear_user_pipeline_logs(email)
    assert get_user_pipeline_logs(email) == []

    publish_user_pipeline_log(email, "")  # empty message ignore
    publish_user_pipeline_log(email, "Step 1: Crawling boards...")
    publish_user_pipeline_log(email, "Step 2: Prefiltering jobs...")
    logs = get_user_pipeline_logs(email)
    assert len(logs) == 2
    assert logs[0] == "Step 1: Crawling boards..."
    assert logs[1] == "Step 2: Prefiltering jobs..."

    clear_user_pipeline_logs(email)
    assert get_user_pipeline_logs(email) == []


def test_custom_companies_api_validation_errors(client):
    """Test error handling on custom companies endpoint."""
    # Unknown ATS
    r1 = client.post("/api/companies/add", json={"url": "https://unknown-portal.com/careers"})
    assert r1.status_code == 400

    # Missing params
    r2 = client.post("/api/companies/add", json={})
    assert r2.status_code == 400

    # Invalid board
    with patch("jobhunt.verify.check_single_board", return_value=("greenhouse", False, 404)):
        r3 = client.post("/api/companies/add", json={"ats": "greenhouse", "slug": "nonexistent999"})
        assert r3.status_code == 400
        assert "Board validation failed" in r3.get_json()["message"]

    # Delete missing params
    r4 = client.delete("/api/companies/custom", json={})
    assert r4.status_code == 400


def test_custom_companies_api_supabase_flow(client, monkeypatch):
    """Test custom company CRUD flow when Supabase memory is active."""
    fake_mem = MagicMock()
    fake_mem.is_configured = True
    fake_prof = {"custom_companies": [{"ats": "lever", "slug": "meesho", "name": "Meesho"}]}
    fake_mem.get_user_profile.return_value = fake_prof

    monkeypatch.setattr("jobhunt.memory.SupabaseMemory", lambda *a, **kw: fake_mem)
    monkeypatch.setattr("jobhunt.web.routes.jobs.get_current_user_context", lambda: ("test@example.com", "token123"))

    with patch("jobhunt.verify.check_single_board", return_value=("greenhouse", True, 200)):
        # List
        r_list = client.get("/api/companies/custom")
        assert r_list.status_code == 200
        assert len(r_list.get_json()["companies"]) == 1

        # Add
        r_add = client.post("/api/companies/add", json={"url": "https://boards.greenhouse.io/stripe"})
        assert r_add.status_code == 200
        fake_mem.upsert_user_profile.assert_called()

        # Delete
        r_del = client.delete("/api/companies/custom", json={"ats": "lever", "slug": "meesho"})
        assert r_del.status_code == 200


def test_job_followup_api_supabase_flow(client, monkeypatch):
    """Test /api/jobs/followup endpoint with candidate profile name."""
    fake_mem = MagicMock()
    fake_mem.is_configured = True
    fake_mem.get_user_profile.return_value = {"name": "Priya Sharma"}
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory", lambda *a, **kw: fake_mem)
    monkeypatch.setattr("jobhunt.web.routes.jobs.get_current_user_context", lambda: ("test@example.com", "token123"))

    res = client.post(
        "/api/jobs/followup",
        json={
            "title": "Staff Platform Engineer",
            "company": "Razorpay",
            "applied_on": "2026-08-20",
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert "Priya Sharma" in data["followup"]["email_body"]


def test_multi_user_batch_with_custom_companies(monkeypatch):
    """Test multi.py crawls custom company boards across users."""
    user_with_custom = {
        "email": "candidate@example.com",
        "name": "Candidate",
        "skills": ["Python", "Flask"],
        "onboarding_completed": True,
        "email_notifications_enabled": False,
        "custom_companies": [{"ats": "greenhouse", "slug": "customco", "name": "Custom Co"}],
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [user_with_custom]

    monkeypatch.setattr("requests.get", lambda *a, **kw: mock_resp)
    with patch("jobhunt.fetch.fetch_all", return_value=[Job(job_id="gh:customco:1", ats="greenhouse", company="Custom Co", title="Backend Dev", location="India", url="http://x", description="test description")]), \
         patch("jobhunt.llm.keyword_screen", return_value=[]):
        res = run_multi_user_pipeline(mock=False, scorer="keyword")
        assert res["status"] == "success" or "users_processed" in res


def test_cli_run_pipeline_with_custom_companies():
    """Test cli.run_pipeline handles custom companies from profile."""
    profile = {
        "name": "Test User",
        "skills": ["Go", "Kubernetes"],
        "target_keywords": ["Backend"],
        "custom_companies": [{"ats": "greenhouse", "slug": "testslug", "name": "Test Slug"}],
    }
    with patch("jobhunt.fetch.fetch_all", return_value=[]):
        code = run_pipeline(profile=profile, scorer="keyword", mock=True)
        assert code == 0


def test_pipeline_stream_sse_endpoint_direct(client):
    """Test /api/pipeline/stream Server-Sent Events endpoint."""
    email = "anonymous"
    publish_user_pipeline_log(email, "SSE Test Log Line 1")
    set_user_pipeline_state(email, running=False, step="idle")

    res = client.get("/api/pipeline/stream")
    assert res.status_code == 200
    assert "text/event-stream" in res.headers.get("Content-Type", "")
    text = res.get_data(as_text=True)
    assert "init" in text or "done" in text


def test_custom_companies_local_file_lifecycle(client, tmp_path, monkeypatch):
    """Test custom company CRUD when stored in local profile.json file."""
    prof_tmp = tmp_path / "profile.json"
    prof_tmp.write_text(json.dumps({"name": "Local Candidate", "custom_companies": []}), encoding="utf-8")
    monkeypatch.setattr("jobhunt.store.get_writable_path", lambda p: prof_tmp)
    monkeypatch.setattr("jobhunt.web.routes.jobs.get_writable_path", lambda p: prof_tmp)

    with patch("jobhunt.verify.check_single_board", return_value=("lever", True, 200)):
        # Add
        r_add = client.post("/api/companies/add", json={"ats": "lever", "slug": "localco", "name": "Local Co"})
        assert r_add.status_code == 200

        # List
        r_list = client.get("/api/companies/custom")
        assert r_list.status_code == 200
        assert any(c["slug"] == "localco" for c in r_list.get_json()["companies"])

        # Delete
        r_del = client.delete("/api/companies/custom", json={"ats": "lever", "slug": "localco"})
        assert r_del.status_code == 200
        assert "Removed" in r_del.get_json()["message"]


def test_anthropic_complete_retries_and_raises():
    """Test Anthropic retry loop on error and eventual LLMError."""
    p = AnthropicProvider()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("Rate limit exceeded")
    with patch.object(p, "_client", return_value=mock_client), patch("time.sleep"):
        with pytest.raises(LLMError, match="anthropic error"):
            p.complete(model="claude-3-haiku", system="sys", user="usr", max_tokens=100)


def test_anthropic_complete_document_retries_and_raises():
    """Test Anthropic document completion retry loop and error."""
    p = AnthropicProvider()
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("Doc failure")
    with patch.object(p, "_client", return_value=mock_client), patch("time.sleep"):
        with pytest.raises(LLMError, match="anthropic document error"):
            p.complete_document(model="claude-3-haiku", prompt="test", pdf=b"%PDF-1.4", max_tokens=100)


def test_gemini_429_all_keys_cooldown(monkeypatch: pytest.MonkeyPatch):
    """Test Gemini 429 when single key is configured (all keys cooling down)."""
    monkeypatch.setenv("GEMINI_API_KEY", "single_test_key")
    p = GeminiProvider()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "15"}
    mock_resp.text = "Too Many Requests"

    with patch("requests.post", return_value=mock_resp), patch("time.sleep") as mock_sleep:
        with pytest.raises(LLMError, match="gemini HTTP 429"):
            p._post("gemini-3.7-flash", {"contents": []})
        assert mock_sleep.called


def test_gemini_404_model_fallbacks(monkeypatch: pytest.MonkeyPatch):
    """Test Gemini 404 automatic model fallback to gemini-2.5-flash and gemini-flash-latest."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_fallback_key")
    p = GeminiProvider()

    resp_404 = MagicMock()
    resp_404.status_code = 404
    resp_404.text = "Model not found"

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Success from fallback"}]}}]
    }

    with patch("requests.post", side_effect=[resp_404, resp_200]):
        res = p._post("gemini-3.7-flash", {"contents": []})
        assert "Success from fallback" in res

    with patch("requests.post", side_effect=[resp_404, resp_200]):
        res2 = p._post("custom-old-model", {"contents": []})
        assert "Success from fallback" in res2


def test_openai_compat_429_and_500(monkeypatch: pytest.MonkeyPatch):
    """Test OpenAI-compatible provider 429 cooldown and 500 retry."""
    monkeypatch.setenv("GROQ_API_KEY", "groq_key_1")
    p = OpenAICompatProvider()

    resp_429 = MagicMock()
    resp_429.status_code = 429
    resp_429.headers = {"Retry-After": "20"}
    resp_429.text = "Rate limited"

    with patch("requests.post", return_value=resp_429), patch("time.sleep"):
        with pytest.raises(LLMError, match="HTTP 429"):
            p.complete(model="llama3", system="sys", user="usr", max_tokens=50)

    resp_500 = MagicMock()
    resp_500.status_code = 500
    resp_500.text = "Internal error"
    with patch("requests.post", return_value=resp_500), patch("time.sleep"):
        with pytest.raises(LLMError, match="HTTP 500"):
            p.complete(model="llama3", system="sys", user="usr", max_tokens=50)


def test_pipeline_sync_github_actions_branches(client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test the full GitHub Actions polling branches in /api/sync."""
    monkeypatch.setenv("GH_TOKEN", "fake_gh_pat_123")
    monkeypatch.setenv("GITHUB_REPOSITORY", "test-org/job-hunter")
    monkeypatch.setattr("jobhunt.web.routes.pipeline.SupabaseMemory.is_configured", property(lambda self: True))

    dev_email = "developer@local"
    from jobhunt.web.state import set_user_pipeline_state
    from datetime import datetime, timezone
    now = time.time()
    set_user_pipeline_state(dev_email, running=True, step="running", message="Cloud dispatched", dispatched_at=now)

    newer_iso = datetime.fromtimestamp(now + 60, timezone.utc).isoformat()
    gh_resp_in_progress = MagicMock()
    gh_resp_in_progress.status_code = 200
    gh_resp_in_progress.json.return_value = {
        "workflow_runs": [
            {
                "status": "in_progress",
                "conclusion": None,
                "created_at": newer_iso,
                "run_started_at": newer_iso,
            }
        ]
    }

    # Mock get_pipeline_history to return an older run so it falls through to GH Actions polling
    mock_mem = MagicMock()
    mock_mem.is_configured = True
    mock_mem.get_pipeline_history.return_value = [{"run_timestamp": "2020-01-01T00:00:00Z"}]
    mock_mem.get_user_profile.return_value = None
    mock_mem._ensure_user_profile_exists.return_value = None

    with patch("jobhunt.web.routes.pipeline.SupabaseMemory", return_value=mock_mem), patch("requests.get", return_value=gh_resp_in_progress):
        r = client.get("/api/sync")
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "success"
        assert data["pipeline"]["running"] is True
        assert "Crawling 100+ ATS" in data["pipeline"]["message"]

    from jobhunt.web.routes.pipeline import _GH_STATUS_CACHE
    _GH_STATUS_CACHE.clear()

    gh_resp_success = MagicMock()
    gh_resp_success.status_code = 200
    gh_resp_success.json.return_value = {
        "workflow_runs": [
            {
                "status": "completed",
                "conclusion": "success",
                "created_at": newer_iso,
                "run_started_at": newer_iso,
            }
        ]
    }

    with patch("jobhunt.web.routes.pipeline.SupabaseMemory", return_value=mock_mem), patch("requests.get", return_value=gh_resp_success):
        r = client.get("/api/sync")
        assert r.status_code == 200
        data = r.get_json()
        assert data["pipeline"]["running"] is False
        assert data["pipeline"]["step"] == "completed"

    _GH_STATUS_CACHE.clear()
    set_user_pipeline_state(dev_email, running=True, step="running", message="Cloud dispatched", dispatched_at=now)
    gh_resp_fail = MagicMock()
    gh_resp_fail.status_code = 200
    gh_resp_fail.json.return_value = {
        "workflow_runs": [
            {
                "status": "completed",
                "conclusion": "failure",
                "created_at": newer_iso,
                "run_started_at": newer_iso,
            }
        ]
    }

    with patch("jobhunt.web.routes.pipeline.SupabaseMemory", return_value=mock_mem), patch("requests.get", return_value=gh_resp_fail):
        r = client.get("/api/sync")
        assert r.status_code == 200
        data = r.get_json()
        assert data["pipeline"]["running"] is False
        assert data["pipeline"]["step"] == "error"

    _GH_STATUS_CACHE.clear()
    future_dispatch = now + 1000
    set_user_pipeline_state(dev_email, running=True, step="running", message="Cloud dispatched", dispatched_at=future_dispatch)
    with patch("jobhunt.web.routes.pipeline.SupabaseMemory", return_value=mock_mem), patch("requests.get", return_value=gh_resp_in_progress):
        r = client.get("/api/sync")
        assert r.status_code == 200
        data = r.get_json()
        assert "Workflow dispatching in GitHub Actions cloud" in data["pipeline"]["message"]

    stale_dispatch = now - 200
    set_user_pipeline_state(dev_email, running=True, step="running", message="Stuck run", dispatched_at=stale_dispatch)
    _GH_STATUS_CACHE.clear()
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    mock_memory = MagicMock()
    mock_memory.is_configured = True
    mock_memory.get_pipeline_history.return_value = [{"run_timestamp": "2026-09-01T00:00:00Z"}]
    mock_memory.get_user_profile.return_value = None
    mock_memory._ensure_user_profile_exists.return_value = None
    with patch("jobhunt.web.routes.pipeline.SupabaseMemory", return_value=mock_memory):
        r = client.get("/api/sync")
        assert r.status_code == 200
        data = r.get_json()
        assert data["pipeline"]["running"] is False
        assert data["pipeline"]["step"] == "completed"


def test_pipeline_stats_and_digest_rebuild(client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Test /api/sync stats calculation and /api/digest live generation with remote profile fallback."""
    import hashlib
    dev_email = "developer@local"
    user_hash = hashlib.md5(dev_email.encode("utf-8")).hexdigest()[:12]
    st_file = tmp_path / f"seen_{user_hash}.json"
    st_data = {
        "job1": {"title": "SWE", "company": "Stripe", "ats": "greenhouse", "score": 8.5, "applied": False, "emailed": True},
        "job2": {"title": "Dev", "company": "Meesho", "ats": "lever", "score": 6.0, "applied": True, "emailed": False},
        "custom:123": {"title": "Lead", "company": "Acme", "score": 9.0, "applied": False},
    }
    st_file.write_text(json.dumps(st_data), encoding="utf-8")

    r = client.get("/api/sync")
    assert r.status_code == 200
    stats = r.get_json()["stats"]
    assert stats["tracked"] == 3
    assert stats["shortlisted"] == 2
    assert stats["applied"] == 1
    assert stats["unapplied"] == 2

    mock_memory = MagicMock()
    mock_memory.is_configured = True
    mock_memory.get_user_profile.return_value = {
        "profile_json": {"name": "Alex", "email": "alex@test.com", "target_roles": ["Engineer"]}
    }
    mock_memory.get_pipeline_history.return_value = [{"jobs_scanned": 150, "candidates_matched": 10}]
    with patch("jobhunt.web.routes.pipeline.SupabaseMemory", return_value=mock_memory):
        r2 = client.get("/api/digest?force=1")
        assert r2.status_code == 200
        assert "text/html" in r2.headers.get("Content-Type", "")



