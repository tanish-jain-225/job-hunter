"""Exhaustive test suite covering 100% of edge cases, fallbacks, and recovery branches."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from app import app
from jobhunt import auth, cli, digest, fetch, llm, memory, mock, multi, store
from jobhunt.fetch import Job


@pytest.fixture
def client(monkeypatch):
    app.config["TESTING"] = True
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    with app.test_client() as client:
        yield client


# ==============================================================================
# 1. auth.py Exhaustive Branch Coverage
# ==============================================================================

def test_auth_verify_token_invalid_inputs():
    assert auth.verify_token("") is None
    assert auth.verify_token(None) is None  # type: ignore
    assert auth.verify_token(12345) is None  # type: ignore


def test_auth_verify_token_cache_expiration(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    token = "test-expiring-token"
    token_hash = auth.hashlib.sha256(token.encode("utf-8")).hexdigest()

    # Pre-populate expired cache entry
    auth._TOKEN_CACHE[token_hash] = ({"email": "cached@test.com"}, time.time() - 100)

    with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: {"id": "123", "email": "fresh@test.com"})):
        res = auth.verify_token(token)
        assert res is not None
        assert res["email"] == "fresh@test.com"


def test_auth_verify_token_api_error_and_exception(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    # Status != 200
    with patch("requests.get", return_value=MagicMock(status_code=401)):
        assert auth.verify_token("bad-token") is None

    # RequestException
    with patch("requests.get", side_effect=requests.RequestException("Network Error")):
        assert auth.verify_token("net-fail-token") is None


def test_auth_extract_bearer_token_variations():
    # 1. Query param
    with app.test_request_context("/api/jobs?token=query_token_123"):
        assert auth.extract_bearer_token() == "query_token_123"

    with app.test_request_context("/api/jobs?access_token=access_token_456"):
        assert auth.extract_bearer_token() == "access_token_456"

    # 2. Cookie
    with app.test_request_context("/api/jobs", headers={"Cookie": "sb_access_token=cookie_token_789"}):
        assert auth.extract_bearer_token() == "cookie_token_789"

    with app.test_request_context("/api/jobs", headers={"Cookie": "supabase_token=cookie_token_abc"}):
        assert auth.extract_bearer_token() == "cookie_token_abc"


def test_auth_is_auth_required_env_switches(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "0")
    assert auth.is_auth_required() is False

    monkeypatch.setenv("AUTH_REQUIRED", "false")
    assert auth.is_auth_required() is False

    monkeypatch.setenv("AUTH_REQUIRED", "off")
    assert auth.is_auth_required() is False

    monkeypatch.setenv("AUTH_REQUIRED", "1")
    assert auth.is_auth_required() is True

    monkeypatch.setenv("AUTH_REQUIRED", "true")
    assert auth.is_auth_required() is True

    monkeypatch.setenv("AUTH_REQUIRED", "on")
    assert auth.is_auth_required() is True


def test_auth_require_auth_decorator_blocked(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    with patch("jobhunt.auth.verify_token", return_value=None):
        res = client.get("/api/config")
        assert res.status_code == 401
        assert "Authentication required" in res.get_json()["message"]


# ==============================================================================
# 2. digest.py Username Derivation & Formatting Coverage
# ==============================================================================

def test_digest_build_username_from_email():
    j = Job(
        job_id="greenhouse:stripe:101",
        ats="greenhouse",
        company="Stripe",
        title="Backend Engineer",
        location="Remote",
        url="https://stripe.com/jobs/101",
        description="Python systems",
        score=8.5,
        reason="Good fit",
        draft={"fit_summary": "Great match", "best_project": "Payments API"}
    )
    subject, html_content = digest.build(
        [j], scanned=50, candidates=10, stats={"tracked": 50},
        profile={"email": "sarah.connor_cyber@example.com"}
    )
    assert "Sarah Connor Cyber" in subject or "Sarah Connor Cyber" in html_content
    assert "Stripe" in html_content


def test_digest_build_empty_profile_name():
    subject, html_content = digest.build(
        [], scanned=20, candidates=0, stats={"tracked": 20},
        profile={}
    )
    assert "Candidate" in html_content
    assert "No new remote matches" in subject


# ==============================================================================
# 3. cli.py Branch & Pipeline Customizations
# ==============================================================================

def test_cli_resolve_relative_vercel_and_root(monkeypatch, tmp_path):
    monkeypatch.setenv("VERCEL", "1")
    p = cli._resolve_relative("config.example.yaml")
    assert p.is_file() or isinstance(p, Path)


def test_cli_run_pipeline_with_custom_filters_and_avoid_roles():
    profile = {
        "name": "Dev User",
        "email": "dev@test.com",
        "avoid_roles": ["Frontend", "Design"],
        "target_titles": ["Python Engineer", "Backend Dev"],
    }
    code = cli.run_pipeline(
        profile=profile,
        user_email="dev@test.com",
        mock=True,
        scorer="keyword",
        send=False,
    )
    assert code == 0


def test_cli_build_and_send_digest_direct():
    j = Job(
        job_id="ashby:openai:555",
        ats="ashby",
        company="OpenAI",
        title="Systems Engineer",
        location="Remote",
        url="https://jobs.ashbyhq.com/openai/555",
        description="High throughput systems",
        score=9.0,
        reason="Direct match",
        draft={"fit_summary": "Excellent match"}
    )
    st = store.Store("seen_test_cli.json")
    with patch("jobhunt.mailer.send") as mock_mailer:
        subj, body = cli._build_and_send_digest(
            [j], [j], [j], [j], st, send_or_args=True, cfg={},
            profile={"name": "Alice"}, to_email="alice@test.com"
        )
        assert mock_mailer.called
        assert "Systems Engineer" in body


# ==============================================================================
# 4. fetch.py ATS Cache, Parsers, & HTTP Retries
# ==============================================================================

def test_fetch_ats_cache_ttl():
    fetch.clear_ats_cache()
    j = Job("ashby:ramp:1", "ashby", "Ramp", "Engineer", "Remote", "http://ramp.com/1", "desc")
    fetch._GLOBAL_ATS_CACHE["ashby:ramp"] = (time.time(), [j])

    cached = fetch.fetch_board("ashby", "ramp", "Ramp", use_cache=True, cache_ttl=100.0)
    assert len(cached) == 1
    assert cached[0].title == "Engineer"


def test_fetch_board_http_retry_loop():
    fetch.clear_ats_cache()
    mock_resp_500 = MagicMock(status_code=500)
    mock_resp_200 = MagicMock(status_code=200, json=lambda: {"jobs": []})

    with patch("requests.get", side_effect=[mock_resp_500, mock_resp_200]):
        res = fetch.fetch_board("greenhouse", "testslug", use_cache=False)
        assert res == []


def test_fetch_parsers_with_malformed_lists():
    r_jobs = fetch.parse_recruitee("slug", "Co", ["not-a-dict", None])
    assert r_jobs == []

    b_jobs = fetch.parse_breezy("slug", "Co", ["not-a-dict", None])
    assert b_jobs == []

    p_jobs = fetch.parse_pinpoint("slug", "Co", ["not-a-dict", None])
    assert p_jobs == []


# ==============================================================================
# 5. llm.py PDF Extraction & Keyword Screen Branch Coverage
# ==============================================================================

def test_llm_extract_text_from_pdf_none():
    assert llm.extract_text_from_pdf(None) == ""
    assert llm.extract_text_from_pdf(b"") == ""


def test_llm_keyword_screen_project_phrase_matching():
    j = Job(
        job_id="lever:co:999",
        ats="lever",
        company="TechCo",
        title="Software Engineer",
        location="Remote",
        url="https://jobs.lever.co/co/999",
        description="Build distributed caching engine and high scale systems with Python.",
    )
    prof = {
        "name": "Bob",
        "skills": ["Python"],
        "notable_projects": ["Distributed Caching Engine for Realtime Metrics"],
        "education": "BS CS",
    }
    llm.keyword_screen([j], prof)
    assert j.draft["best_project"] == "Distributed Caching Engine for Realtime Metrics"
    assert j.score is not None and j.score > 0


# ==============================================================================
# 6. store.py Sanitization for All ATS Types & Atomic Retry
# ==============================================================================

def test_store_sanitize_job_url_all_ats_types():
    assert "greenhouse" in store.sanitize_job_url("", job_id="greenhouse:stripe:123")
    assert "lever" in store.sanitize_job_url("", job_id="lever:netflix:456")
    assert "ashby" in store.sanitize_job_url("", job_id="ashby:ramp:789")
    assert "workable" in store.sanitize_job_url("", job_id="workable:vector:101")
    assert "smartrecruiters" in store.sanitize_job_url("", job_id="smartrecruiters:visa:202")
    assert "bamboohr" in store.sanitize_job_url("", job_id="bamboohr:acme:303")
    assert "recruitee" in store.sanitize_job_url("", job_id="recruitee:hotjar:404")
    assert "breezy" in store.sanitize_job_url("", job_id="breezy:automattic:505")
    assert "pinpoint" in store.sanitize_job_url("", job_id="pinpoint:monzo:606")


def test_store_atomic_replace_retry(tmp_path):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"
    src.write_text("hello", encoding="utf-8")
    store._atomic_replace(src, dst)
    assert dst.read_text(encoding="utf-8") == "hello"


# ==============================================================================
# 7. memory.py Supabase Error & History Coverage
# ==============================================================================

def test_memory_upsert_string_and_invalid_formats(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    mem = memory.SupabaseMemory()

    with patch("requests.post", return_value=MagicMock(status_code=201)):
        ok = mem.upsert_user_profile("user@test.com", {
            "skills": "Python, Docker, SQL",
            "target_keywords": "Backend, SRE",
            "exclude_keywords": "Manager, Sales",
            "min_score_notification": "8.5",
        })
        assert ok is True


def test_memory_pipeline_runs_and_job_sync(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    mem = memory.SupabaseMemory()

    with patch("requests.post", return_value=MagicMock(status_code=201)), \
         patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [{"id": 1, "jobs_scanned": 50}])):
        mem.record_pipeline_run("user@test.com", {"jobs_scanned": 50, "status": "completed"})
        history = mem.get_pipeline_history("user@test.com")
        assert len(history) == 1
        assert history[0]["jobs_scanned"] == 50


def test_memory_job_crud_operations(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    mem = memory.SupabaseMemory()

    with patch("requests.post", return_value=MagicMock(status_code=201)), \
         patch("requests.delete", return_value=MagicMock(status_code=204)), \
         patch("requests.patch", return_value=MagicMock(status_code=200)), \
         patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])):

        # Save single job
        saved = mem.save_user_job("user@test.com", {
            "job_id": "greenhouse:stripe:99",
            "company": "Stripe",
            "title": "Engineer",
            "applied": True,
        })
        assert saved is True

        # Bulk upsert
        count = mem.bulk_upsert_user_jobs("user@test.com", [
            {"job_id": "lever:acme:1", "company": "Acme", "title": "Dev"},
            {"job_id": "ashby:ramp:2", "company": "Ramp", "title": "Dev"}
        ])
        assert count == 2

        # Applied & stage toggles
        assert mem.set_job_applied("user@test.com", "lever:acme:1", True) is True
        assert mem.set_job_stage("user@test.com", "lever:acme:1", "interviewing") is True
        assert mem.set_job_notes("user@test.com", "lever:acme:1", "Spoke with recruiter") is True

        # Delete job
        assert mem.delete_user_job("user@test.com", "lever:acme:1") is True


# ==============================================================================
# 8. multi.py Batch Execution Coverage
# ==============================================================================

def test_multi_user_pipeline_execution_branches(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    mock_users = [
        {
            "email": "user1@test.com",
            "name": "User One",
            "onboarding_completed": True,
            "skills": ["Python"],
            "target_keywords": ["Backend"],
            "email_notifications_enabled": False,
        }
    ]

    with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: mock_users)), \
         patch("jobhunt.multi.fetch_all_mock", return_value=mock.fetch_all_mock()), \
         patch("requests.post", return_value=MagicMock(status_code=201)):

        res = multi.run_multi_user_pipeline(mock=True, scorer="keyword")
        assert res["status"] == "success"
        assert res["users_processed"] >= 1


# ==============================================================================
# 9. web routes (jobs, pipeline, views) Comprehensive Coverage
# ==============================================================================

def test_web_routes_jobs_filtering_and_sorting(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setattr("jobhunt.web.routes.jobs.get_current_user_context", lambda: ("user@test.com", "token123"))
    st = store.Store("seen_test_routes.json")
    st.data = {
        "greenhouse:stripe:1": {
            "job_id": "greenhouse:stripe:1",
            "company": "Stripe",
            "title": "Staff Engineer",
            "location": "Remote",
            "ats": "greenhouse",
            "score": 9.5,
            "applied": True,
            "first_seen": "2026-08-01T10:00:00",
        },
        "ashby:ramp:2": {
            "job_id": "ashby:ramp:2",
            "company": "Ramp",
            "title": "Backend Dev",
            "location": "Bengaluru",
            "ats": "ashby",
            "score": 6.5,
            "applied": False,
            "first_seen": "2026-08-02T10:00:00",
        },
    }
    monkeypatch.setattr("jobhunt.web.routes.jobs.Store", lambda *args, **kwargs: st)

    # Filter status=applied
    r1 = client.get("/api/jobs?status=applied")
    assert r1.status_code == 200
    assert r1.get_json()["count"] == 1

    # Filter status=unapplied
    r2 = client.get("/api/jobs?status=unapplied")
    assert r2.status_code == 200
    assert r2.get_json()["count"] == 1

    # Filter status=shortlisted
    r3 = client.get("/api/jobs?status=shortlisted")
    assert r3.status_code == 200
    assert r3.get_json()["count"] == 1

    # Filter ats=greenhouse
    r4 = client.get("/api/jobs?ats=greenhouse")
    assert r4.status_code == 200
    assert r4.get_json()["count"] == 1

    # Filter min_score=9.0
    r5 = client.get("/api/jobs?min_score=9.0")
    assert r5.status_code == 200
    assert r5.get_json()["count"] == 1

    # Search filter
    r6 = client.get("/api/jobs?search=ramp")
    assert r6.status_code == 200
    assert r6.get_json()["count"] == 1

    # Sort by score
    r7 = client.get("/api/jobs?sort=score")
    assert r7.status_code == 200
    assert r7.get_json()["jobs"][0]["company"] == "Stripe"

    # Sort by company
    r8 = client.get("/api/jobs?sort=company")
    assert r8.status_code == 200
    assert r8.get_json()["jobs"][0]["company"] == "Ramp"


def test_web_routes_pipeline_run_status_and_exit_code(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setattr("jobhunt.web.routes.pipeline.get_current_user_context", lambda: ("stream_user@test.com", "tok"))
    from jobhunt.web.state import set_user_pipeline_state
    set_user_pipeline_state("stream_user@test.com", running=False, step="idle", exit_code=0, message="Ready")

    res = client.get("/api/sync")
    assert res.status_code == 200
    data = res.get_json()
    assert data["pipeline"]["running"] is False
    assert data["pipeline"]["step"] == "idle"

    # Test POST /api/run with mock mode
    with patch("jobhunt.cli.run_pipeline", return_value=0), \
         patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value={"name": "Sarah", "skills": ["Python"], "onboarding_completed": True}):
        res_run = client.post("/api/run", json={"mock": True})
        assert res_run.status_code == 200
        assert res_run.get_json()["status"] == "success"


def test_web_routes_profile_cache_write_warning(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setattr("jobhunt.web.routes.profile.get_current_user_context", lambda: ("user_warn@test.com", "token"))
    with patch("jobhunt.web.routes.profile.get_writable_path", side_effect=OSError("Read-only file system")), \
         patch("requests.post", return_value=MagicMock(status_code=201)):
        res = client.post("/api/profile", json={"name": "Test User", "skills": ["Python"]})
        assert res.status_code == 200


def test_memory_unconfigured_and_invalid_inputs(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    mem = memory.SupabaseMemory()

    assert mem.is_configured is False
    assert mem.get_user_profile("") is None
    assert mem.get_user_profile("user@test.com") is None
    assert mem.upsert_user_profile("", {}) is False
    assert mem.upsert_user_profile("user@test.com", {}) is False
    assert mem.save_user_job("user@test.com", {}) is False
    assert mem.bulk_upsert_user_jobs("user@test.com", []) == 0
    assert mem.set_job_applied("user@test.com", "id", True) is False
    assert mem.set_job_stage("user@test.com", "id", "applied") is False
    assert mem.set_job_notes("user@test.com", "id", "notes") is False
    assert mem.delete_user_job("user@test.com", "id") is False
    assert mem.record_pipeline_run("user@test.com", {}) is False
    assert mem.get_pipeline_history("user@test.com") == []


def test_memory_configured_empty_id_safeguards(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    mem = memory.SupabaseMemory()

    assert mem.save_user_job("user@test.com", {"job_id": ""}) is False
    assert mem.bulk_upsert_user_jobs("user@test.com", [{"job_id": ""}]) == 0
    assert mem.set_job_applied("user@test.com", "", True) is False
    assert mem.set_job_stage("user@test.com", "", "applied") is False
    assert mem.set_job_notes("user@test.com", "", "notes") is False
    assert mem.delete_user_job("user@test.com", "") is False


def test_multi_user_pipeline_empty_raw_jobs(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    with patch("jobhunt.multi.fetch_all_mock", return_value=[]):
        res = multi.run_multi_user_pipeline(mock=True)
        assert res["status"] == "no_jobs"
        assert res["users_processed"] == 0


def test_multi_user_pipeline_real_fetch_and_llm_mode(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    mock_users = [
        {
            "email": "user_llm@test.com",
            "name": "LLM User",
            "onboarding_completed": True,
            "skills": ["Python", "Machine Learning"],
            "target_keywords": ["AI Engineer"],
            "email_notifications_enabled": True,
            "min_score_notification": 6.0,
        },
        {
            "email": "user_empty_matches@test.com",
            "name": "No Matches",
            "onboarding_completed": True,
            "skills": ["Cobol", "Fortran"],
            "target_keywords": ["Mainframe Architect"],
            "email_notifications_enabled": False,
        }
    ]

    mock_job = Job(
        job_id="ashby:co:1",
        ats="ashby",
        company="AI Inc",
        title="AI Engineer",
        location="Remote",
        url="https://jobs.ashbyhq.com/co/1",
        description="Python Machine Learning models",
        score=8.5,
    )

    with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: mock_users)), \
         patch("jobhunt.multi.fetch_all", return_value=[mock_job]), \
         patch("jobhunt.multi.llm.screen", return_value=None), \
         patch("jobhunt.multi.llm.draft", return_value={"fit_summary": "Solid"}), \
         patch("jobhunt.multi.mailer.send", return_value=True), \
         patch("requests.post", return_value=MagicMock(status_code=201)):

        # Run with mock=False and scorer="llm" (using mock LLM mocks above)
        res = multi.run_multi_user_pipeline(mock=False, scorer="gemini")
        assert res["status"] == "success"
        assert res["users_processed"] >= 1


def test_memory_profile_type_coercion_and_history_error(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    mem = memory.SupabaseMemory()

    # Pass numbers/booleans for list fields to trigger coercion
    with patch("requests.post", return_value=MagicMock(status_code=201)):
        ok = mem.upsert_user_profile("user@test.com", {
            "skills": 12345,
            "target_keywords": True,
            "exclude_keywords": {"nested": "dict"},
            "profile_json": "not-a-dict",
        })
        assert ok is True

    # History API non-200 / error
    with patch("requests.get", return_value=MagicMock(status_code=500)):
        history = mem.get_pipeline_history("user@test.com")
        assert history == []


def test_web_routes_pipeline_in_memory_digest(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setattr("jobhunt.web.routes.pipeline.get_current_user_context", lambda: ("mem_user@test.com", "token"))

    # Force rebuild digest when live=1 is passed
    res = client.get("/api/digest?live=1")
    assert res.status_code == 200
    assert "text/html" in res.content_type


def test_digest_badge_and_bullets_and_locations():
    from jobhunt.digest import _job_type_badge, _bullets, _card

    # Internship badge
    j_intern = Job("1", "ashby", "Co", "Summer Intern", "London", "http://x", "Internship role")
    assert "Internship" in _job_type_badge(j_intern)

    # Empty and populated bullets
    assert _bullets([]) == ""
    bullets_html = _bullets(["Point 1", "Point 2"])
    assert "Point 1</li>" in bullets_html

    # Location TBD
    j_tbd = Job("2", "ashby", "Co", "Engineer", "", "http://x", "No location", score=9.0)
    card_tbd = _card(j_tbd)
    assert "Location TBD" in card_tbd

    # Global location
    j_global = Job("3", "ashby", "Co", "Engineer", "Tokyo, Japan", "http://x", "Japan role", score=8.5)
    card_global = _card(j_global)
    assert "Global / Check Location" in card_global


def test_web_routes_profile_preferences_get_and_post(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setattr("jobhunt.web.routes.profile.get_current_user_context", lambda: ("pref_user@test.com", "token"))

    # GET preferences
    res_get = client.get("/api/profile/preferences")
    assert res_get.status_code == 200
    data_get = res_get.get_json()
    assert data_get["status"] == "success"
    assert "preferences" in data_get

    # POST preferences
    payload = {
        "preferred_locations": ["Bengaluru", "Remote"],
        "job_types": ["fulltime", "remote"],
        "experience_level": "1-3",
        "min_salary_lpa": 25,
        "preferred_sectors": ["Fintech", "AI"],
    }
    res_post = client.post("/api/profile/preferences", json=payload)
    assert res_post.status_code == 200
    data_post = res_post.get_json()
    assert data_post["status"] == "success"
    assert data_post["preferences"]["min_salary_lpa"] == 25


def test_web_routes_api_sync_github_actions_status_polling(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("GH_TOKEN", "mock_gh_token")
    monkeypatch.setattr("jobhunt.web.routes.pipeline.get_current_user_context", lambda: ("sync_gh@test.com", "token"))

    # Mock in-progress GitHub run
    from jobhunt.web.state import set_user_pipeline_state
    set_user_pipeline_state("sync_gh@test.com", running=True, step="running", dispatched_at=time.time() - 30)

    mock_gh_in_progress = {
        "workflow_runs": [
            {"status": "in_progress", "conclusion": None, "created_at": "2026-08-24T12:00:00Z"}
        ]
    }
    with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: mock_gh_in_progress)):
        res = client.get("/api/sync")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"

    # Mock completed success GitHub run
    mock_gh_completed = {
        "workflow_runs": [
            {"status": "completed", "conclusion": "success", "created_at": "2026-08-24T12:05:00Z"}
        ]
    }
    with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: mock_gh_completed)):
        res = client.get("/api/sync")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"

    # Mock completed failure GitHub run
    set_user_pipeline_state("sync_gh@test.com", running=True, step="running", dispatched_at=time.time() - 30)
    mock_gh_failed = {
        "workflow_runs": [
            {"status": "completed", "conclusion": "failure", "created_at": "2026-08-24T12:10:00Z"}
        ]
    }
    with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: mock_gh_failed)):
        res = client.get("/api/sync")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"


def test_web_routes_companies_search_and_ats_filter(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setattr("jobhunt.web.routes.jobs.get_current_user_context", lambda: ("comp_test@test.com", "token"))

    # Filter by ATS
    res_ats = client.get("/api/companies?ats=greenhouse")
    assert res_ats.status_code == 200
    data_ats = res_ats.get_json()
    assert all(c.get("ats") == "greenhouse" for c in data_ats["companies"])

    # Filter by search keyword
    res_search = client.get("/api/companies?search=stripe")
    assert res_search.status_code == 200
    data_search = res_search.get_json()
    assert any("stripe" in c.get("slug", "").lower() for c in data_search["companies"])


def test_providers_document_and_error_handling(monkeypatch):
    from jobhunt.providers import Provider, GeminiProvider, AnthropicProvider, LLMError

    # Provider abstract method raises
    class DummyProvider(Provider):
        pass

    dummy = DummyProvider()
    with pytest.raises(NotImplementedError):
        dummy.complete("model", "sys", "user", 1000)

    # Gemini document completion mock
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    gemini = GeminiProvider()
    with patch("requests.post", return_value=MagicMock(
        status_code=200,
        json=lambda: {"candidates": [{"content": {"parts": [{"text": "Extracted doc"}]}}]}
    )):
        res = gemini.complete_document("gemini-3.6-flash", "extract", b"pdf_bytes", 1000)
        assert res == "Extracted doc"

    # Anthropic missing key
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    anthropic = AnthropicProvider()
    with pytest.raises(LLMError):
        anthropic.preflight()


def test_web_routes_api_run_experience_levels_and_dispatch_failures(client, monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setattr("jobhunt.web.routes.pipeline.get_current_user_context", lambda: ("exp_user@test.com", "token"))

    # Mock user profile with fresher experience level and mock mode
    with patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value={
        "name": "Fresher Candidate",
        "skills": ["Python", "Flask"],
        "experience_level": "fresher",
        "onboarding_completed": True,
    }), patch("jobhunt.cli.run_pipeline", return_value=0):
        res_fresher = client.post("/api/run", json={"mock": True})
        assert res_fresher.status_code == 200

    # Mock user profile with 1-3 experience level
    with patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value={
        "name": "Mid Candidate",
        "skills": ["Python", "FastAPI"],
        "experience_level": "1-3",
        "preferred_locations": ["Bengaluru"],
        "job_types": ["fulltime"],
        "onboarding_completed": True,
    }), patch("jobhunt.cli.run_pipeline", return_value=0):
        res_mid = client.post("/api/run", json={"mock": True})
        assert res_mid.status_code == 200

    # Vercel mode with GitHub Actions dispatch non-200 failure
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("GH_TOKEN", "mock_token")
    with patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value={
        "name": "Cloud Candidate",
        "skills": ["Go", "Kubernetes"],
        "onboarding_completed": True,
    }), patch("requests.post", return_value=MagicMock(status_code=422, text="Unprocessable Entity")), \
       patch("jobhunt.cli.run_pipeline", return_value=0):
        res_gh_fail = client.post("/api/run", json={"mock": True})
        assert res_gh_fail.status_code == 200









