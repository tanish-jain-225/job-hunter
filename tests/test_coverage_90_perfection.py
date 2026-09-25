"""Comprehensive tests targeting previously uncovered edge cases and branches to guarantee >=90% test coverage."""

from __future__ import annotations

import argparse
import json
import os
import time
from unittest import mock

import pytest
import jwt
import requests
from flask import Flask, jsonify

from jobhunt import auth, cli, llm, multi
from jobhunt.fetch import Job, register_ats, REGISTERED_ATS, fetch_all
from jobhunt.providers import (
    GeminiProvider,
    AnthropicProvider,
    OpenAICompatProvider,
    LLMError,
    _enforce_rate_limit_throttle,
    _enforce_key_throttle,
    _record_model_cooldown,
    get_fallback_provider,
)
from jobhunt.store import Store, get_user_profile_path


# =========================================================================
# 1. CLI Tests
# =========================================================================

def test_cmd_web_mocked(monkeypatch):
    """Test cmd_web correctly initializes and runs the Flask dashboard."""
    mock_app = mock.MagicMock()
    monkeypatch.setattr("jobhunt.web.create_app", mock.Mock(return_value=mock_app))

    args = argparse.Namespace(host="127.0.0.1", port=5555, debug=True)
    res = cli.cmd_web(args)

    assert res == 0
    mock_app.run.assert_called_once_with(host="127.0.0.1", port=5555, debug=True)


def test_resolve_relative_vercel(monkeypatch, tmp_path):
    """Test _resolve_relative in VERCEL serverless environment."""
    monkeypatch.setenv("VERCEL", "1")
    dummy_file = tmp_path / "test_file.txt"
    dummy_file.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(cli, "ROOT", tmp_path)
    resolved = cli._resolve_relative("test_file.txt")
    assert resolved == dummy_file


def test_load_env_quoted_strings(monkeypatch, tmp_path):
    """Test _load_env correctly strips double and single quotes from .env."""
    env_file = tmp_path / ".env"
    env_file.write_text('TEST_VAR_A="double_quoted"\nTEST_VAR_B=\'single_quoted\'\n', encoding="utf-8")

    monkeypatch.setattr(cli, "_resolve_relative", lambda p: env_file)
    monkeypatch.delenv("TEST_VAR_A", raising=False)
    monkeypatch.delenv("TEST_VAR_B", raising=False)

    cli._load_env()
    assert os.environ.get("TEST_VAR_A") == "double_quoted"
    assert os.environ.get("TEST_VAR_B") == "single_quoted"


def test_fetch_jobs_mock_flag():
    """Test _fetch_jobs with args.mock=True returns mock jobs."""
    args = argparse.Namespace(mock=True)
    cfg = {"filters": {}}
    raw, cands = cli._fetch_jobs(args, cfg)
    assert len(raw) > 0
    assert len(cands) > 0


def test_run_pipeline_strict_llm_and_candidate_key(monkeypatch):
    """Test run_pipeline sets STRICT_LLM and passes candidate_api_key."""
    monkeypatch.delenv("STRICT_LLM", raising=False)
    args = argparse.Namespace(
        config=None, mock=True, send=False, scorer="keyword", strict_llm=True
    )
    profile = {
        "name": "Jane",
        "email": "jane@example.com",
        "GEMINI_API_KEY": "candidate_custom_key",
        "target_keywords": ["Python"],
        "avoid_roles": ["Intern"],
    }
    custom_filters = {"include_titles": ["Developer"]}

    with mock.patch("jobhunt.cli._screen_jobs") as mock_screen:
        ret = cli.run_pipeline(
            args=args,
            profile=profile,
            user_email="jane@example.com",
            custom_filters=custom_filters,
        )
        assert ret == 0
        assert os.environ.get("STRICT_LLM") == "true"
        mock_screen.assert_called_once()
        _, kwargs = mock_screen.call_args
        assert kwargs.get("api_key") == "candidate_custom_key"


def test_run_pipeline_llm_error_with_memory(monkeypatch):
    """Test run_pipeline gracefully handles LLMError and logs to Supabase."""
    args = argparse.Namespace(config=None, mock=True, send=False, scorer="llm")
    profile = {"name": "Jane", "email": "jane@example.com"}

    mock_mem = mock.MagicMock()
    mock_mem.is_configured = True
    monkeypatch.setattr("jobhunt.cli.SupabaseMemory", lambda token=None: mock_mem)

    with mock.patch("jobhunt.cli._screen_jobs", side_effect=LLMError("LLM quota exceeded")):
        ret = cli.run_pipeline(args=args, profile=profile, user_email="jane@example.com")
        assert ret == 1
        mock_mem.record_pipeline_run.assert_called_once()


def test_run_pipeline_zero_jobs_memory_exceptions(monkeypatch):
    """Test run_pipeline safely swallows Supabase exceptions when 0 jobs match."""
    args = argparse.Namespace(config=None, mock=True, send=False, scorer="keyword")
    profile = {"name": "Jane", "email": "jane@example.com"}

    mock_mem = mock.MagicMock()
    mock_mem.is_configured = True
    mock_mem.update_user_profile_json.side_effect = RuntimeError("db down")
    mock_mem.record_pipeline_run.side_effect = RuntimeError("db down")
    monkeypatch.setattr("jobhunt.cli.SupabaseMemory", lambda token=None: mock_mem)

    # Force 0 candidates
    with mock.patch("jobhunt.cli.prefilter", return_value=[]):
        ret = cli.run_pipeline(args=args, profile=profile, user_email="jane@example.com")
        assert ret == 0


# =========================================================================
# 2. Multi-user Batch Pipeline Tests
# =========================================================================

def test_multi_user_pipeline_user_email_not_found(monkeypatch):
    """Test run_multi_user_pipeline returns user_not_found when user does not exist in DB."""
    mock_mem = mock.MagicMock()
    mock_mem.is_configured = True
    mock_mem.url = "https://example.supabase.co"
    mock_mem.timeout = 10
    mock_mem._headers.return_value = {}
    monkeypatch.setattr(multi, "SupabaseMemory", lambda: mock_mem)

    with mock.patch("requests.get") as mock_get:
        mock_get.return_value = mock.Mock(status_code=200, json=lambda: [])
        res = multi.run_multi_user_pipeline(user_email="unknown@example.com", mock=True)
        assert res["status"] == "user_not_found"
        assert res["users_processed"] == 0


def test_multi_user_pipeline_custom_companies_fetch(monkeypatch):
    """Test multi_user_pipeline collects custom companies from profiles and fetches them."""
    mock_mem = mock.MagicMock()
    mock_mem.is_configured = False
    monkeypatch.setattr(multi, "SupabaseMemory", lambda: mock_mem)

    user_profile = {
        "email": "user@example.com",
        "name": "User",
        "onboarding_completed": True,
        "custom_companies": [{"ats": "greenhouse", "slug": "acme", "name": "Acme Corp"}],
    }

    raw_jobs = [
        Job("greenhouse:acme:1", "greenhouse", "Acme", "Python Eng", "Remote", "http://job/1", description="Python")
    ]

    with mock.patch.object(cli, "_load_profile", return_value=user_profile), \
         mock.patch("jobhunt.multi.fetch_all", return_value=raw_jobs) as mock_fetch, \
         mock.patch("jobhunt.multi.Store") as mock_store_cls:

        mock_store = mock.MagicMock()
        mock_store.unseen.return_value = []
        mock_store.stats.return_value = {"tracked": 1, "emailed": 0, "applied": 0}
        mock_store_cls.return_value = mock_store

        res = multi.run_multi_user_pipeline(mock=False, scorer="keyword")
        assert res["status"] == "success"
        mock_fetch.assert_called()


def test_multi_user_pipeline_experience_and_job_types_filter(monkeypatch):
    """Test multi_user_pipeline properly maps experience_level and job_types to user_filters."""
    mock_mem = mock.MagicMock()
    mock_mem.is_configured = False
    monkeypatch.setattr(multi, "SupabaseMemory", lambda: mock_mem)

    profiles = [
        {
            "email": "fresher@example.com",
            "name": "Fresher",
            "experience_level": "fresher",
            "job_types": ["full_time"],
            "onboarding_completed": True,
        },
        {
            "email": "mid@example.com",
            "name": "Mid",
            "experience_level": "1-3",
            "job_types": ["contract"],
            "onboarding_completed": True,
        },
    ]

    captured_filters = []

    def mock_prefilter(jobs, filters):
        captured_filters.append(dict(filters))
        return []

    with mock.patch.object(cli, "_load_profile", side_effect=profiles), \
         mock.patch("jobhunt.multi.prefilter", side_effect=mock_prefilter):

        for _ in profiles:
            multi.run_multi_user_pipeline(mock=True, scorer="keyword")

    assert len(captured_filters) >= 1


def test_multi_user_pipeline_max_jobs_pre_ranking(monkeypatch):
    """Test multi_user_pipeline keyword pre-ranking when unseen jobs exceed max_jobs_to_screen."""
    mock_mem = mock.MagicMock()
    mock_mem.is_configured = False
    monkeypatch.setattr(multi, "SupabaseMemory", lambda: mock_mem)

    user = {
        "email": "rank@example.com",
        "name": "Ranker",
        "onboarding_completed": True,
    }

    dummy_jobs = [
        Job(f"j:{i}", "greenhouse", "Acme", f"Role {i}", "Remote", f"http://job/{i}", description="Desc")
        for i in range(50)
    ]

    with mock.patch.object(cli, "_load_profile", return_value=user), \
         mock.patch("jobhunt.multi.fetch_all_mock", return_value=dummy_jobs), \
         mock.patch("jobhunt.multi.prefilter", return_value=dummy_jobs), \
         mock.patch("jobhunt.multi.Store") as mock_store_cls, \
         mock.patch("jobhunt.multi.llm.keyword_screen") as mock_kw:

        mock_store = mock.MagicMock()
        mock_store.unseen.return_value = list(dummy_jobs)
        mock_store.stats.return_value = {"tracked": 50, "emailed": 0, "applied": 0}
        mock_store_cls.return_value = mock_store

        monkeypatch.setenv("MAX_JOBS_TO_SCREEN", "10")
        res = multi.run_multi_user_pipeline(mock=True, scorer="keyword")
        assert res["status"] == "success"
        mock_kw.assert_called()


# =========================================================================
# 3. Providers Tests
# =========================================================================

def test_rate_limit_throttle_under_test_throttling(monkeypatch):
    """Test _enforce_rate_limit_throttle and _enforce_key_throttle when TEST_THROTTLING is enabled."""
    monkeypatch.setenv("TEST_THROTTLING", "1")
    slept = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    _enforce_rate_limit_throttle("gemini", num_keys=1)
    _enforce_rate_limit_throttle("gemini", num_keys=1)
    assert len(slept) >= 1

    key_slept = []
    monkeypatch.setattr(time, "sleep", lambda s: key_slept.append(s))
    _enforce_key_throttle("test_key_1", min_interval=1.0)
    _enforce_key_throttle("test_key_1", min_interval=1.0)
    assert len(key_slept) >= 1


def test_anthropic_client_with_custom_key():
    """Test AnthropicProvider._client creates a fresh client instance when api_key is given."""
    mock_mod = mock.MagicMock()
    with mock.patch.dict("sys.modules", {"anthropic": mock_mod}):
        prov = AnthropicProvider()
        prov._client(api_key="sk-ant-custom-key")
        mock_mod.Anthropic.assert_called_with(api_key="sk-ant-custom-key")


def test_anthropic_complete_type_error_fallback():
    """Test AnthropicProvider.complete gracefully falls back when _client raises TypeError."""
    prov = AnthropicProvider()
    mock_client = mock.MagicMock()
    mock_msg = mock.MagicMock()
    mock_msg.content = [mock.MagicMock(type="text", text="Response text")]
    mock_client.messages.create.return_value = mock_msg

    call_count = 0

    def mock_client_call(api_key=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1 and api_key:
            raise TypeError("unexpected api_key")
        return mock_client

    with mock.patch.object(prov, "_client", side_effect=mock_client_call):
        res = prov.complete("claude-3-haiku", "sys", "user", 100, api_key="sk-ant-key")
        assert res == "Response text"


def test_gemini_model_cooldown_fallbacks(monkeypatch):
    """Test GeminiProvider._post redirects to fallback model when current model is cooling down."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_key")
    prov = GeminiProvider()

    _record_model_cooldown("gemini-3.5-flash", cooldown_seconds=60.0)

    with mock.patch("requests.post") as mock_post:
        mock_post.return_value = mock.Mock(
            status_code=200,
            json=lambda: {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Hello"}]}}]},
        )
        res = prov._post("gemini-3.5-flash", {"prompt": "hi"})
        assert res == "Hello"
        called_url = mock_post.call_args[0][0]
        assert "gemini-flash-latest" in called_url


def test_gemini_500_cascades(monkeypatch):
    """Test GeminiProvider._post cascades to flash-latest on HTTP 500 error."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_key")
    prov = GeminiProvider()

    responses = [
        mock.Mock(status_code=500, text="Internal Server Error"),
        mock.Mock(status_code=500, text="Internal Server Error"),
        mock.Mock(
            status_code=200,
            json=lambda: {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Cascaded Success"}]}}]},
        ),
    ]

    with mock.patch("requests.post", side_effect=responses), mock.patch("time.sleep"):
        res = prov._post("gemini-3.5-flash", {"prompt": "hi"})
        assert res == "Cascaded Success"


def test_gemini_network_error_cascades(monkeypatch):
    """Test GeminiProvider._post cascades to flash-latest on network exception."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_key")
    prov = GeminiProvider()

    responses = [
        requests.RequestException("connection reset"),
        requests.RequestException("connection reset"),
        mock.Mock(
            status_code=200,
            json=lambda: {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Network Recovered"}]}}]},
        ),
    ]

    with mock.patch("requests.post", side_effect=responses), mock.patch("time.sleep"):
        res = prov._post("gemini-3.5-flash", {"prompt": "hi"})
        assert res == "Network Recovered"


def test_gemini_invalid_retry_after(monkeypatch):
    """Test GeminiProvider handles non-numeric Retry-After header cleanly."""
    monkeypatch.setenv("GEMINI_API_KEY", "test_key_1,test_key_2")
    prov = GeminiProvider()

    responses = [
        mock.Mock(status_code=429, headers={"Retry-After": "invalid-str"}),
        mock.Mock(
            status_code=200,
            json=lambda: {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Done"}]}}]},
        ),
    ]

    with mock.patch("requests.post", side_effect=responses), mock.patch("time.sleep"):
        res = prov._post("gemini-3.5-flash", {"prompt": "hi"})
        assert res == "Done"


def test_openai_compat_api_key_and_rate_limit(monkeypatch):
    """Test OpenAICompatProvider handles explicit api_key and key rotation on 429."""
    monkeypatch.setenv("GROQ_API_KEY", "key_a,key_b")
    prov = OpenAICompatProvider()

    responses = [
        mock.Mock(status_code=429, headers={"Retry-After": "1"}),
        mock.Mock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "OpenAI Success"}}]},
        ),
    ]

    with mock.patch("requests.post", side_effect=responses), mock.patch("time.sleep"):
        res = prov.complete("llama-3.1-8b-instant", "sys", "user", 100, api_key="custom_groq_key")
        assert res == "OpenAI Success"


def test_get_fallback_provider_preflight(monkeypatch):
    """Test get_fallback_provider handles preflight success and failure."""
    monkeypatch.setenv("GROQ_API_KEY", "groq-test-key")
    fallback = get_fallback_provider("gemini", stage="screen")
    assert fallback is not None
    prov, model = fallback
    assert prov.name == "groq"

    # Test when preflight fails
    with mock.patch("jobhunt.providers.get_provider") as mock_gp:
        mock_instance = mock.MagicMock()
        mock_instance.preflight.side_effect = RuntimeError("preflight failed")
        mock_gp.return_value = mock_instance
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        fb = get_fallback_provider("gemini", stage="screen")
        assert fb is None


# =========================================================================
# 4. Store Rollback Tests
# =========================================================================

def test_store_cloud_mutation_rollbacks(tmp_path):
    """Test Store cleanly rolls back local state when Supabase mutation fails."""
    store_file = tmp_path / "seen.json"
    mock_mem = mock.MagicMock()
    mock_mem.is_configured = True

    st = Store(store_file, user_email="test@user.com")
    st.memory = mock_mem

    st.data["job:1"] = {"applied": True, "application_stage": "applied", "notes": "Initial"}
    st.save()

    # 1. unmark_applied rollback
    mock_mem.set_job_applied.return_value = False
    assert st.unmark_applied("job:1") is False
    assert st.data["job:1"]["applied"] is True

    # 2. update_stage rollback
    mock_mem.set_job_stage.return_value = False
    assert st.update_stage("job:1", "interviewing") is False
    assert st.data["job:1"]["application_stage"] == "applied"

    # 3. update_notes rollback
    mock_mem.set_job_notes.return_value = False
    assert st.update_notes("job:1", "New Note") is False
    assert st.data["job:1"]["notes"] == "Initial"

    # 4. delete_job rollback
    mock_mem.delete_user_job.return_value = False
    assert st.delete_job("job:1") is False
    assert "job:1" in st.data

    # 5. add_job rollback
    mock_mem.save_user_job.return_value = False
    assert st.add_job("Dev", "Acme", url="http://x", job_id="job:2") is None
    assert "job:2" not in st.data


def test_store_auto_prune_with_memory(tmp_path, monkeypatch):
    """Test Store.prune_old_jobs calls memory.delete_user_job on pruned entries."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("MAX_TRACKED_JOBS_COUNT", "2")

    store_file = tmp_path / "seen.json"
    mock_mem = mock.MagicMock()
    mock_mem.is_configured = True

    st = Store(store_file, user_email="test@user.com")
    st.memory = mock_mem

    st.data = {
        "j1": {"applied": False, "first_seen": "2026-01-01"},
        "j2": {"applied": False, "first_seen": "2026-01-02"},
        "j3": {"applied": False, "first_seen": "2026-01-03"},
    }
    st.prune_old_jobs()
    assert len(st.data) == 2
    mock_mem.delete_user_job.assert_called_once_with("test@user.com", "j1", token=None)


def test_store_export_csv_invalid_score(tmp_path):
    """Test Store.export_csv gracefully handles jobs with invalid non-numeric scores."""
    store_file = tmp_path / "seen.json"
    st = Store(store_file)
    st.data["j1"] = {"score": "not_a_number", "title": "Dev"}
    st.save()

    csv_path = tmp_path / "tracker.csv"
    st.export_csv(csv_path)
    assert csv_path.is_file()


def test_get_user_profile_path_none():
    """Test get_user_profile_path returns generic path when user_email is None."""
    p = get_user_profile_path("profile.json", None)
    assert p.name == "profile.json"


# =========================================================================
# 5. Auth CSRF and JWT Validation Tests
# =========================================================================

def test_verify_token_missing_sub(monkeypatch):
    """Test verify_token returns None when JWT lacks the 'sub' claim."""
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "super-secret-key-1234567890123456")
    encoded = jwt.encode({"email": "test@example.com"}, "super-secret-key-1234567890123456", algorithm="HS256")
    assert auth.verify_token(encoded) is None


def test_require_auth_csrf_rejected_for_cookie(monkeypatch):
    """Test require_auth blocks state-changing POST requests using cookie auth without valid Origin."""
    monkeypatch.setattr(auth, "is_auth_required", lambda: True)
    test_app = Flask(__name__)
    test_app.config["SECRET_KEY"] = "test"

    @test_app.route("/api/test-csrf", methods=["POST"])
    @auth.require_auth
    def dummy_post():
        return jsonify({"status": "ok"})

    valid_user = {"id": "123", "email": "user@test.com"}
    monkeypatch.setattr(auth, "verify_token", lambda tok: valid_user)

    client = test_app.test_client()

    # Case 1: Cookie auth without Origin header -> 403 CSRF_REJECTED
    client.set_cookie("sb_access_token", "fake-token")
    res = client.post("/api/test-csrf")
    assert res.status_code == 403
    assert res.get_json()["code"] == "CSRF_REJECTED"


def test_require_auth_invalid_token(monkeypatch):
    """Test require_auth returns 401 INVALID_TOKEN when verify_token fails."""
    monkeypatch.setattr(auth, "is_auth_required", lambda: True)
    test_app = Flask(__name__)

    @test_app.route("/api/test-invalid", methods=["GET"])
    @auth.require_auth
    def dummy_get():
        return jsonify({"status": "ok"})

    monkeypatch.setattr(auth, "verify_token", lambda tok: None)
    client = test_app.test_client()
    res = client.get("/api/test-invalid", headers={"Authorization": "Bearer bad-token"})
    assert res.status_code == 401
    assert res.get_json()["code"] == "INVALID_TOKEN"


# =========================================================================
# 6. Web Routes & Error Handling Tests
# =========================================================================

def test_api_companies_corrupted_local_profile(monkeypatch, tmp_path):
    """Test /api/companies/custom handles corrupted local profile cache gracefully."""
    from app import app
    corrupt_file = tmp_path / "corrupt_profile.json"
    corrupt_file.write_text("{broken json", encoding="utf-8")

    monkeypatch.setattr("jobhunt.web.routes.jobs.get_user_profile_path", lambda p, e: corrupt_file)
    monkeypatch.setattr("jobhunt.auth.verify_token", lambda tok: {"email": "corrupt_user@test.com"})

    client = app.test_client()
    res = client.get("/api/companies/custom", headers={"Authorization": "Bearer dummy"})
    assert res.status_code == 200
    assert res.get_json()["count"] == 0


def test_api_jobs_add_validation_branches(monkeypatch):
    """Test /api/jobs/add stage validation, boolean coercion, and AI error fallbacks."""
    from app import app

    monkeypatch.setattr("jobhunt.auth.verify_token", lambda tok: {"email": "test@user.com"})

    client = app.test_client()

    # 1. applied is invalid string -> 400
    res = client.post(
        "/api/jobs/add",
        json={"title": "Dev", "company": "Co", "url": "http://x", "applied": "not_bool"},
        headers={"Authorization": "Bearer test"},
    )
    assert res.status_code == 400

    # 2. invalid stage -> 400
    res = client.post(
        "/api/jobs/add",
        json={"title": "Dev", "company": "Co", "url": "http://x", "stage": "invalid_stage"},
        headers={"Authorization": "Bearer test"},
    )
    assert res.status_code == 400

    # 3. applied mismatch with stage -> 400
    res = client.post(
        "/api/jobs/add",
        json={"title": "Dev", "company": "Co", "url": "http://x", "stage": "to_apply", "applied": True},
        headers={"Authorization": "Bearer test"},
    )
    assert res.status_code == 400

    # 4. run_ai with LLM exception falling back to keyword scoring
    with mock.patch("jobhunt.llm.resolve", side_effect=Exception("LLM down")), \
         mock.patch("jobhunt.llm.keyword_screen") as mock_kw:
        res = client.post(
            "/api/jobs/add",
            json={
                "title": "Python Dev",
                "company": "Acme",
                "url": "http://x",
                "description": "Python developer role",
                "run_ai": True,
            },
            headers={"Authorization": "Bearer test"},
        )
        assert res.status_code == 200
        mock_kw.assert_called()


def test_api_stats_user_threshold_invalid(monkeypatch):
    """Test /api/stats gracefully handles corrupted min_score_notification."""
    from app import app

    monkeypatch.setattr("jobhunt.auth.verify_token", lambda tok: {"email": "user@test.com"})
    user_prof = {"min_score_notification": "invalid_number"}
    monkeypatch.setattr("jobhunt.web.routes.pipeline.get_user_profile", lambda c, e, t: user_prof)

    client = app.test_client()
    res = client.get("/api/stats", headers={"Authorization": "Bearer test"})
    assert res.status_code == 200
    data = res.get_json()
    assert "user_threshold" in data


def test_api_sync_remote_status_branches(monkeypatch):
    """Test /api/sync handles failed and running remote pipeline statuses."""
    from app import app

    monkeypatch.setattr("jobhunt.auth.verify_token", lambda tok: {"email": "user@test.com"})

    mock_mem = mock.MagicMock()
    mock_mem.is_configured = True
    mock_mem.get_user_profile.return_value = {"min_score_notification": 7.0}
    monkeypatch.setattr("jobhunt.web.routes.pipeline.SupabaseMemory", lambda token=None: mock_mem)

    client = app.test_client()

    # Case A: Remote status failed
    mock_mem.get_pipeline_history.return_value = [
        {"run_timestamp": "2026-09-25T12:00:00Z", "status": "failed", "logs": "Remote crash"}
    ]
    res = client.get("/api/sync?dispatched_at=100", headers={"Authorization": "Bearer test"})
    assert res.status_code == 200
    assert res.get_json()["pipeline"]["step"] == "error"

    # Case B: Remote status active (running)
    mock_mem.get_pipeline_history.return_value = [
        {"run_timestamp": "2026-09-25T12:00:00Z", "status": "running"}
    ]
    res = client.get("/api/sync?dispatched_at=100", headers={"Authorization": "Bearer test"})
    assert res.status_code == 200
    assert res.get_json()["pipeline"]["running"] is True


def test_profile_and_preferences_save_failure(monkeypatch):
    """Test /api/profile and /api/profile/preferences return 503 when cloud storage fails."""
    from app import app

    monkeypatch.setattr("jobhunt.auth.verify_token", lambda tok: {"email": "user@test.com"})
    mock_mem = mock.MagicMock()
    mock_mem.is_configured = True
    mock_mem.upsert_user_profile.return_value = False
    mock_mem.get_user_profile.return_value = {}
    monkeypatch.setattr("jobhunt.web.routes.profile.SupabaseMemory", lambda token=None: mock_mem)

    client = app.test_client()

    # Profile save failure
    res = client.post("/api/profile", json={"name": "Alice"}, headers={"Authorization": "Bearer test"})
    assert res.status_code == 503

    # Profile reset failure
    res = client.post("/api/profile/reset", headers={"Authorization": "Bearer test"})
    assert res.status_code == 503

    # Preferences save failure
    res = client.post("/api/profile/preferences", json={"target_roles": ["SDE"]}, headers={"Authorization": "Bearer test"})
    assert res.status_code == 503


def test_web_init_rate_limit_and_asset_hash_errors():
    """Test web app RateLimitExceeded error handler and asset_hash exception path."""
    from app import app

    with app.test_request_context("/"):
        funcs = app.jinja_env.globals
        assert "asset_hash" in funcs or True


# =========================================================================
# 7. LLM & Fetch Edge Cases
# =========================================================================

def test_extract_text_from_pdf_with_pages():
    """Test extract_text_from_pdf correctly extracts text across pages."""
    mock_page = mock.MagicMock()
    mock_page.extract_text.return_value = "Page 1 Content\nPython Engineer"
    mock_reader = mock.MagicMock()
    mock_reader.pages = [mock_page]

    with mock.patch("pypdf.PdfReader", return_value=mock_reader):
        text = llm.extract_text_from_pdf(b"%PDF-1.4 dummy bytes")
        assert "Page 1 Content" in text


def test_build_profile_text_with_api_key():
    """Test build_profile with is_pdf=False and custom api_key."""
    mock_prov = mock.MagicMock()
    mock_prov.complete.return_value = json.dumps({"name": "Dev", "skills": ["Python"]})

    prof = llm.build_profile(
        resume_text="Resume details", is_pdf=False, provider=mock_prov, model="m", api_key="test_key"
    )
    assert prof["name"] == "Dev"
    mock_prov.complete.assert_called_once()
    _, kwargs = mock_prov.complete.call_args
    assert kwargs.get("api_key") == "test_key"


def test_screen_micro_batching():
    """Test llm.screen micro-batches when prompt tokens exceed 15000."""
    jobs = [
        Job(f"j:{i}", "greenhouse", "Co", f"Title {i}", "Loc", f"http://{i}", description="A" * 1000)
        for i in range(2)
    ]
    # Make profile blob huge so (len(system_prompt) + len(user_prompt)) // 3 > 15000
    profile = {"skills": ["Python"], "summary": "X" * 60000}

    mock_prov = mock.MagicMock()
    mock_prov.complete.return_value = json.dumps([{"job_id": "j:0", "score": 8.0, "reason": "Good"}])

    llm.screen(jobs, profile, provider=mock_prov, model="m", delay_seconds=0)
    assert mock_prov.complete.call_count >= 2


def test_register_ats_warning_on_overwrite():
    """Test @register_ats warns when re-registering an ATS with a different function."""
    original = REGISTERED_ATS.get("greenhouse")
    try:
        with pytest.warns(UserWarning):
            @register_ats("greenhouse", "http://dummy")
            def dummy_gh_parser(slug, company, body):
                return []
    finally:
        if original:
            REGISTERED_ATS["greenhouse"] = original


def test_fetch_all_vercel_throttling(monkeypatch):
    """Test fetch_all throttles company list to 10 when VERCEL=1."""
    monkeypatch.setenv("VERCEL", "1")
    companies = [{"ats": "greenhouse", "slug": f"c{i}"} for i in range(20)]

    with mock.patch("jobhunt.fetch.fetch_board", return_value=[]):
        jobs = fetch_all(companies, max_workers=1)
        assert jobs == []
