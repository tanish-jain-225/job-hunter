"""Tests verifying zero-cost 300 DAU sustainability and codeless autoscaling past 1,000+ DAU."""

from __future__ import annotations

import smtplib
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from jobhunt import fetch, mailer, memory, multi, providers, providers_throttle
from jobhunt.parsers import Job
from jobhunt.store import Store
from jobhunt.web import create_app


ROOT = Path(__file__).resolve().parent.parent


def test_aimd_adaptive_throttle_scales_up_and_backs_off():
    """Verify AIMD accelerates paid-tier keys without 429s and backs off on rate-limit spikes."""
    providers_throttle.reset_provider_state()
    try:
        paid_key = "AIzaPaidTierKey1"
        free_key = "AIzaFreeTierKey1"

        assert providers_throttle.get_adaptive_key_interval(paid_key, "gemini", 5.0) == 5.0

        # Sustained clean calls probe downward aggressively toward 0.05s floor
        for _ in range(20):
            providers_throttle._record_key_success(paid_key, "gemini", default_interval=5.0)
        fast_interval = providers_throttle.get_adaptive_key_interval(paid_key, "gemini", 5.0)
        assert fast_interval < 0.25

        # Free key hits 429: backs off multiplicatively and enforces protective floor
        for _ in range(5):
            providers_throttle._record_key_success(free_key, "gemini", default_interval=5.0)
        assert providers_throttle.get_adaptive_key_interval(free_key, "gemini", 5.0) < 5.0

        backed_off = providers_throttle._record_key_rate_limit(free_key, "gemini", default_interval=5.0)
        assert backed_off >= 5.0

        # Floor holds for initial post-429 successes, then lifts after 25 consecutive clean calls
        for _ in range(5):
            providers_throttle._record_key_success(free_key, "gemini", default_interval=5.0)
        held_interval = providers_throttle.get_adaptive_key_interval(free_key, "gemini", 5.0)
        assert held_interval >= 4.0

        for _ in range(30):
            providers_throttle._record_key_success(free_key, "gemini", default_interval=5.0)
        recovered_interval = providers_throttle.get_adaptive_key_interval(free_key, "gemini", 5.0)
        assert recovered_interval < 0.5
    finally:
        providers_throttle.reset_provider_state()


def test_gemini_and_openai_providers_update_aimd_on_200_and_429(monkeypatch):
    """Verify GeminiProvider and OpenAICompatProvider report success/429 to AIMD state."""
    providers_throttle.reset_provider_state()
    try:
        key_g = "AIzaTestGeminiAimd"
        monkeypatch.setenv("GEMINI_API_KEY", key_g)
        gemini = providers.GeminiProvider()

        ok_resp = MagicMock(status_code=200)
        ok_resp.json.return_value = {
            "candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"ok": true}'}]}}],
        }
        with patch("jobhunt.providers.requests.post", return_value=ok_resp):
            for _ in range(5):
                assert gemini.complete("gemini-3.5-flash", "sys", "usr", 100) == '{"ok": true}'
        assert providers_throttle.get_adaptive_key_interval(key_g, "gemini", 5.0) < 5.0

        # 429 triggers backoff hook before rotating/raising
        rate_resp = MagicMock(status_code=429, text="RESOURCE_EXHAUSTED quota exceeded", headers={})
        with patch("jobhunt.providers.requests.post", return_value=rate_resp), pytest.raises(providers.LLMError):
            gemini.complete("gemini-3.5-flash", "sys", "usr", 100)
        assert providers_throttle.get_adaptive_key_interval(key_g, "gemini", 5.0) >= 5.0

        # OpenAI-compatible (e.g., Groq) updates AIMD too
        key_o = "gsk_test_aimd_key"
        monkeypatch.setenv("GROQ_API_KEY", key_o)
        groq = providers.GroqProvider()
        ok_oai = MagicMock(status_code=200)
        ok_oai.json.return_value = {"choices": [{"message": {"content": "hello"}}]}
        with patch("jobhunt.providers.requests.post", return_value=ok_oai):
            for _ in range(5):
                assert groq.complete("llama-3.3-70b-versatile", "sys", "usr", 100) == "hello"
        assert providers_throttle.get_adaptive_key_interval(key_o, "groq", 2.0) < 2.0
    finally:
        providers_throttle.reset_provider_state()


def test_memory_load_user_jobs_paginates_past_1000_rows(monkeypatch):
    """Verify PostgREST chunk pagination fetches >1,000 tracked jobs without truncation."""
    monkeypatch.setenv("SUPABASE_URL", "https://scale.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    memory.clear_memory_cache()

    page1 = [
        {"job_id": f"gh:co:{i}", "company": "Co", "title": "Eng", "url": "https://x.com/1"}
        for i in range(1000)
    ]
    page2 = [
        {"job_id": f"gh:co:{1000 + i}", "company": "Co", "title": "Eng", "url": "https://x.com/2"}
        for i in range(50)
    ]
    seen_offsets: list[str] = []

    def fake_get(url, headers=None, params=None, timeout=None):
        seen_offsets.append(str((params or {}).get("offset", "0")))
        resp = MagicMock(status_code=200)
        resp.json.return_value = page1 if params.get("offset") == "0" else page2
        return resp

    mem = memory.SupabaseMemory()
    with patch.object(memory._get_session(), "get", side_effect=fake_get):
        loaded = mem.load_user_jobs("scale@example.com")

    assert len(loaded) == 1050
    assert seen_offsets == ["0", "1000"]
    assert memory._CACHE_TTL >= 30.0
    memory.clear_memory_cache()


def test_store_default_prune_cap_is_300_preserving_applied_jobs(monkeypatch, tmp_path: Path):
    """Verify default production pruning caps unapplied clutter at 300 while preserving active stages."""
    monkeypatch.setenv("CI", "true")
    monkeypatch.delenv("MAX_TRACKED_JOBS_COUNT", raising=False)

    st = Store(tmp_path / "seen_cap.json")
    initial_jobs = [
        Job(
            job_id=f"gh:co:{i}",
            ats="greenhouse",
            company="Co",
            title=f"Role {i}",
            location="Remote",
            url=f"https://boards.greenhouse.io/co/jobs/{i}",
            description="Python",
            score=7.5,
        )
        for i in range(300)
    ]
    st.record(initial_jobs, emailed=False)
    # Mark first 5 jobs as applied/interviewing; they must survive pruning beyond 300
    for i in range(5):
        st.data[f"gh:co:{i}"]["applied"] = True
        st.data[f"gh:co:{i}"]["application_stage"] = "applied" if i < 3 else "interviewing"

    extra_jobs = [
        Job(
            job_id=f"gh:co:{300 + i}",
            ats="greenhouse",
            company="Co",
            title=f"Role {300 + i}",
            location="Remote",
            url=f"https://boards.greenhouse.io/co/jobs/{300 + i}",
            description="Python",
            score=7.5,
        )
        for i in range(25)
    ]
    st.record(extra_jobs, emailed=False)
    assert len(st.data) == 300
    for i in range(5):
        assert f"gh:co:{i}" in st.data


def test_mailer_dynamic_cap_and_smtp_quota_detection():
    """Verify hardcoded 450 ceiling is gone and SMTP daily quota responses trigger fast abort."""
    assert mailer.MAX_DAILY_SEND >= 50000
    assert mailer.is_smtp_quota_error(smtplib.SMTPDataError(550, b"5.4.5 Daily user sending limit exceeded"))
    assert mailer.is_smtp_quota_error(RuntimeError("421 4.7.0 Try again later, closing connection"))
    assert not mailer.is_smtp_quota_error(RuntimeError("temporary socket timeout"))

    sess = mailer.SMTPSession(host="smtp.example.com", port=587, user="bot@example.com", password="secret")
    mock_smtp = MagicMock()
    mock_smtp.send_message.side_effect = smtplib.SMTPDataError(550, b"5.4.5 Daily user sending limit exceeded")
    sess.server = mock_smtp

    msg = mailer.build_message("Subj", "<p>Hi</p>", "u@example.com", "bot@example.com")
    with patch.object(sess, "connect") as spy_connect, pytest.raises(smtplib.SMTPDataError):
        sess.send_message(msg)
    # Quota errors must NOT trigger redundant reconnect+retry loop
    spy_connect.assert_not_called()


def test_multi_user_profile_pagination_and_lightweight_columns(monkeypatch, tmp_path: Path):
    """Verify multi.py paginates >1,000 Supabase users and skips downloading heavy resume_text blobs."""
    monkeypatch.setenv("SUPABASE_URL", "https://scale.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "srv")

    page1 = [
        {"email": f"u{i}@example.com", "name": f"User {i}", "onboarding_completed": True, "skills": ["Python"]}
        for i in range(1000)
    ]
    page2 = [
        {"email": f"u{1000 + i}@example.com", "name": f"User {1000 + i}", "onboarding_completed": True, "skills": ["Go"]}
        for i in range(3)
    ]
    observed_selects: list[str] = []
    observed_offsets: list[str] = []

    def fake_get(url, headers=None, params=None, timeout=None):
        observed_selects.append(str((params or {}).get("select", "")))
        observed_offsets.append(str((params or {}).get("offset", "0")))
        resp = MagicMock(status_code=200)
        resp.json.return_value = page1 if params.get("offset") == "0" else page2
        return resp

    called_users: list[str] = []

    def fake_process_user(idx, total_users, user, **kwargs):
        called_users.append(user["email"])
        return 1, 0, 0

    with (
        patch("requests.get", side_effect=fake_get),
        patch("jobhunt.multi.fetch_all", return_value=[Job("1", "gh", "Co", "Dev", "Remote", "https://x", "desc")]),
        patch("jobhunt.multi._process_single_user", side_effect=fake_process_user),
    ):
        res = multi.run_multi_user_pipeline(mock=False, scorer="keyword")

    assert res["users_processed"] == 1003
    assert len(called_users) == 1003
    assert observed_offsets == ["0", "1000"]
    assert all("resume_text" not in sel and "*" not in sel for sel in observed_selects)


def test_multi_user_shared_pool_circuit_breaker_preserves_byok_and_smtp_fallback(monkeypatch, tmp_path: Path):
    """Verify shared LLM/SMTP quota circuit breakers fast-fallback shared users while BYOK still uses LLM."""
    monkeypatch.setenv("SUPABASE_URL", "https://scale.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "srv")
    monkeypatch.setenv("SMTP_PASS", "valid-app-password")
    monkeypatch.setenv("MULTI_MAX_WORKERS", "1")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("STRICT_LLM", raising=False)

    users = [
        {
            "email": "shared1@example.com",
            "name": "Shared One",
            "onboarding_completed": True,
            "skills": ["Python"],
            "target_keywords": ["Python"],
            "email_notifications_enabled": True,
            "mail_mode": "daily",
            "min_score_notification": 5.0,
        },
        {
            "email": "shared2@example.com",
            "name": "Shared Two",
            "onboarding_completed": True,
            "skills": ["Python"],
            "target_keywords": ["Python"],
            "email_notifications_enabled": True,
            "mail_mode": "daily",
            "min_score_notification": 5.0,
        },
        {
            "email": "byok@example.com",
            "name": "BYOK User",
            "onboarding_completed": True,
            "skills": ["Python"],
            "target_keywords": ["Python"],
            "profile_json": {"GEMINI_API_KEY": "AIzaUserOwnKey123"},
            "email_notifications_enabled": True,
            "mail_mode": "daily",
            "min_score_notification": 5.0,
        },
    ]

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = users

    llm_calls: list[tuple[str, str | None]] = []

    def fake_llm_screen(jobs, profile, **kwargs):
        api_key = kwargs.get("api_key")
        llm_calls.append((profile["email"], api_key))
        if not api_key:
            raise RuntimeError("429 quota exceeded on shared pool")
        for j in jobs:
            j.score = 9.2
            j.reason = "BYOK personalized match"

    smtp_attempts: list[str] = []

    def fake_send(subject, html_body, to_email=None, **kwargs):
        smtp_attempts.append(to_email or "")
        raise smtplib.SMTPDataError(550, b"5.4.5 Daily user sending limit exceeded")

    saved_digests: list[str] = []
    job = Job("gh:acme:1", "greenhouse", "Acme", "Python Engineer", "Remote", "https://boards.greenhouse.io/acme/1", "Python APIs")

    st_counter = 0

    def fake_store(*a, **kw):
        nonlocal st_counter
        st_counter += 1
        return Store(tmp_path / f"seen_{st_counter}.json")

    with (
        patch("requests.get", return_value=mock_resp),
        patch("jobhunt.multi.fetch_all", return_value=[job]),
        patch("jobhunt.multi.Store", side_effect=fake_store),
        patch("jobhunt.multi.resolve", return_value=(MagicMock(name="gemini"), "gemini-3.5-flash")),
        patch("jobhunt.multi.llm.screen", side_effect=fake_llm_screen),
        patch("jobhunt.multi.llm.draft", return_value=None),
        patch("jobhunt.multi.mailer.SMTPSession") as mock_smtp_cls,
        patch("jobhunt.multi.mailer.send", side_effect=fake_send),
        patch.object(memory.SupabaseMemory, "record_pipeline_run", return_value=True),
        patch.object(memory.SupabaseMemory, "prune_pipeline_runs", return_value=True),
        patch.object(
            memory.SupabaseMemory,
            "update_user_profile_json",
            side_effect=lambda email, meta, **kw: saved_digests.append(email) or True,
        ),
    ):
        mock_smtp_cls.return_value.__enter__.return_value = MagicMock()
        res = multi.run_multi_user_pipeline(mock=False, scorer="llm")

    assert res["status"] == "success"
    assert res["users_processed"] == 3
    # shared2 bypassed LLM cleanly after shared1 tripped pool breaker; BYOK still invoked LLM with own key!
    assert llm_calls == [
        ("shared1@example.com", None),
        ("byok@example.com", "AIzaUserOwnKey123"),
    ]
    # All 3 users had digests built and saved in Supabase despite SMTP daily quota error
    assert set(saved_digests) == {"shared1@example.com", "shared2@example.com", "byok@example.com"}
    # Only 1 SMTP attempt fired before smtp_quota_exhausted breaker protected the rest of the batch
    assert smtp_attempts == ["shared1@example.com"]
    # Original raw_jobs item stayed untouched by BYOK mutations (job isolation across users)
    assert job.score is None


def test_api_sync_skips_redundant_profile_stub_for_existing_users(monkeypatch):
    """Verify /api/sync only calls _ensure_user_profile_exists when profile row is missing."""
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setenv("SUPABASE_URL", "https://scale.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("MAIL_TO", "existing@example.com")

    app = create_app()
    client = app.test_client()

    with (
        patch.object(memory.SupabaseMemory, "load_user_jobs", return_value={}),
        patch.object(memory.SupabaseMemory, "get_user_profile", return_value={"email": "existing@example.com"}),
        patch.object(memory.SupabaseMemory, "_ensure_user_profile_exists") as spy_ensure,
    ):
        resp = client.get("/api/sync")
        assert resp.status_code == 200
        spy_ensure.assert_not_called()

    # Now verify missing row DOES lazily initialize once
    with (
        patch.object(memory.SupabaseMemory, "load_user_jobs", return_value={}),
        patch.object(memory.SupabaseMemory, "get_user_profile", side_effect=[None, {"email": "existing@example.com"}]),
        patch.object(memory.SupabaseMemory, "_ensure_user_profile_exists") as spy_ensure,
    ):
        resp2 = client.get("/api/sync")
        assert resp2.status_code == 200
        spy_ensure.assert_called_once()


def test_fetch_all_optional_gha_disk_cache(monkeypatch, tmp_path: Path):
    """Verify JOBHUNT_ATS_DISK_CACHE=1 serves rapid consecutive runs from disk without HTTP."""
    cache_file = tmp_path / "ats_pool_cache.json"
    monkeypatch.setenv("JOBHUNT_ATS_DISK_CACHE", "1")
    monkeypatch.setenv("JOBHUNT_ATS_CACHE_PATH", str(cache_file))
    monkeypatch.setenv("JOBHUNT_ATS_CACHE_TTL", "1800")

    companies = [{"ats": "greenhouse", "slug": "stripe", "name": "Stripe"}]
    sample_job = Job("greenhouse:stripe:1", "greenhouse", "Stripe", "Backend Engineer", "Remote", "https://stripe.com/1", "Python")

    with patch("jobhunt.fetch.fetch_board", return_value=[sample_job]) as spy_board:
        first = fetch.fetch_all(companies, max_workers=1, use_cache=True)
        assert len(first) == 1
        assert spy_board.call_count == 1
        assert cache_file.is_file()

        second = fetch.fetch_all(companies, max_workers=1, use_cache=True)
        assert len(second) == 1
        assert second[0].job_id == "greenhouse:stripe:1"
        assert spy_board.call_count == 1  # Zero extra HTTP calls!

        # Expired TTL misses and re-crawls
        monkeypatch.setenv("JOBHUNT_ATS_CACHE_TTL", "0")
        time.sleep(0.01)
        third = fetch.fetch_all(companies, max_workers=1, use_cache=True)
        assert len(third) == 1
        assert spy_board.call_count == 2


def test_workflow_and_frontend_cadence_zero_cost_defaults():
    """Verify workflow removes 40m/450/1000 artificial ceilings and frontend uses idle-aware 60s heartbeat."""
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "daily.yml").read_text(encoding="utf-8"))
    hunt = wf["jobs"]["hunt"]
    assert hunt["timeout-minutes"] == 360

    setup_step = next(s for s in hunt["steps"] if str(s.get("uses", "")).startswith("actions/setup-python"))
    assert setup_step["with"]["cache"] == "pip"

    run_step = next(s for s in hunt["steps"] if s.get("name") == "Execute Autonomous Job Hunter Radar")
    assert run_step["env"]["JOBHUNT_ATS_DISK_CACHE"] == "1"
    assert "'300'" in str(run_step["env"]["MAX_TRACKED_JOBS_COUNT"])

    app_js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "HEARTBEAT_INTERVAL_MS = 60000" in app_js
    assert "HEARTBEAT_IDLE_TIMEOUT_MS" in app_js
    assert "setTimeout(poll, 5000)" in app_js


def test_seen_archive_fifo_prevents_reappearance_zero_db_overhead(tmp_path, monkeypatch):
    """Pruned jobs enter a compact FIFO seen_archive so scans never re-surface old jobs."""
    from jobhunt.store import Store, decode_seen_archive, job_id_digest

    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("MAX_TRACKED_JOBS_COUNT", "2")
    monkeypatch.setenv("MAX_SEEN_ARCHIVE_COUNT", "3")

    seen_file = tmp_path / "seen.json"
    st = Store(seen_file)
    jobs = [
        Job(f"greenhouse:acme:{i}", "greenhouse", "Acme", f"Role {i}", "Remote", f"https://acme.test/{i}", "Python")
        for i in range(1, 7)
    ]

    # Save 6 jobs with UI cap=2 -> 4 pruned -> FIFO archive keeps newest 3 of the 4 pruned (jobs 2, 3, 4; job 1 rotates out)
    st.record(jobs, emailed=False)
    assert len(st.data) == 2
    assert "greenhouse:acme:5" in st.data
    assert "greenhouse:acme:6" in st.data
    assert st.archive_path.is_file()
    digests = decode_seen_archive(st.archive_path.read_text(encoding="utf-8"))
    assert len(digests) == 3
    assert job_id_digest("greenhouse:acme:1") not in digests
    for idx in (2, 3, 4):
        assert job_id_digest(f"greenhouse:acme:{idx}") in digests

    # Reload a fresh Store from disk without passing seen_archive manually: jobs 2..6 remain filtered out
    st2 = Store(seen_file)
    unseen_after_reload = [j.job_id for j in st2.unseen(jobs)]
    assert unseen_after_reload == ["greenhouse:acme:1"]


def test_seen_archive_syncs_supabase_only_on_prune_and_sanitized_in_api(tmp_path, monkeypatch):
    """Supabase profile_json.seen_archive syncs ONLY when rows are evicted and is hidden from browser JSON."""
    from jobhunt.store import Store, encode_seen_archive, extract_seen_archive, job_id_digest
    from jobhunt.web.state import sanitize_profile_for_response

    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("MAX_TRACKED_JOBS_COUNT", "2")
    monkeypatch.setenv("MAX_SEEN_ARCHIVE_COUNT", "2000")
    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "srv-key")

    updates: list[dict] = []
    seen_file = tmp_path / "seen_cloud.json"
    st = Store(seen_file, user_email="alice@test.com", use_service_key=True, seen_archive="")
    with (
        patch.object(st.memory, "load_user_jobs", return_value={}),
        patch.object(st.memory, "bulk_upsert_user_jobs", return_value=True),
        patch.object(st.memory, "delete_user_job", return_value=True),
        patch.object(
            st.memory,
            "update_user_profile_json",
            side_effect=lambda email, upd, **kw: updates.append({"email": email, "upd": upd, "kw": kw}) or True,
        ),
    ):
        # 2 jobs <= cap(2): ZERO seen_archive DB writes!
        st.record(
            [
                Job("gh:a:1", "greenhouse", "A", "Eng 1", "Remote", "https://a/1", "Python"),
                Job("gh:a:2", "greenhouse", "A", "Eng 2", "Remote", "https://a/2", "Python"),
            ],
            emailed=False,
        )
        assert updates == []

        # 3rd job pushes gh:a:1 out -> exactly ONE update_user_profile_json write with digest of gh:a:1
        st.record([Job("gh:a:3", "greenhouse", "A", "Eng 3", "Remote", "https://a/3", "Python")], emailed=False)
        assert len(updates) == 1
        assert updates[0]["email"] == "alice@test.com"
        assert updates[0]["kw"].get("use_service_key") is True
        packed = updates[0]["upd"]["seen_archive"]
        assert packed == encode_seen_archive([job_id_digest("gh:a:1")], 2000)

        # Subsequent save without additional evictions writes ZERO times
        st.save(auto_export=False)
        assert len(updates) == 1

    # Profile extraction + browser sanitization check
    profile_row = {"email": "alice@test.com", "profile_json": {"seen_archive": packed, "skills": ["Python"]}}
    assert extract_seen_archive(profile_row, memory_configured=True) == packed
    sanitized = sanitize_profile_for_response(profile_row)
    assert "seen_archive" not in sanitized
    assert "seen_archive" not in sanitized.get("profile_json", {})
    assert sanitized["profile_json"]["skills"] == ["Python"]


def test_multi_batch_respects_user_seen_archive_from_profile(tmp_path, monkeypatch):
    """multi.run_multi_user_pipeline must skip jobs already recorded in user profile_json.seen_archive."""
    from pathlib import Path
    from jobhunt import memory, multi
    from jobhunt.store import job_id_digest

    monkeypatch.setenv("SUPABASE_URL", "https://demo.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "srv-key")
    monkeypatch.setattr("jobhunt.store.get_writable_path", lambda p: tmp_path / Path(p).name)
    memory.clear_memory_cache()

    archived_job = Job("gh:acme:old1", "greenhouse", "Acme", "Python Engineer", "Remote", "https://acme/old1", "Python")
    fresh_job = Job("gh:acme:new2", "greenhouse", "Acme", "Python Engineer", "Remote", "https://acme/new2", "Python")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [
        {
            "email": "bob@test.com",
            "name": "Bob",
            "title": "Python Engineer",
            "skills": ["Python"],
            "target_keywords": ["Python Engineer"],
            "onboarding_completed": True,
            "email_notifications_enabled": False,
            "profile_json": {"seen_archive": job_id_digest("gh:acme:old1")},
        }
    ]

    screened_ids: list[str] = []

    def fake_screen(jobs, *args, **kwargs):
        for j in jobs:
            screened_ids.append(j.job_id)
            j.score = 8.5
            j.reason = "Match"

    with (
        patch("requests.get", return_value=mock_resp),
        patch("jobhunt.multi.fetch_all", return_value=[archived_job, fresh_job]),
        patch("jobhunt.memory.SupabaseMemory.load_user_jobs", return_value={}),
        patch("jobhunt.memory.SupabaseMemory.bulk_upsert_user_jobs", return_value=True),
        patch("jobhunt.memory.SupabaseMemory.update_user_profile_json", return_value=True),
        patch("jobhunt.memory.SupabaseMemory.record_pipeline_run", return_value=True),
        patch("jobhunt.memory.SupabaseMemory.prune_pipeline_runs", return_value=True),
        patch("jobhunt.multi.resolve", return_value=(MagicMock(name="gemini"), "gemini-3.5-flash")),
        patch("jobhunt.multi.llm.screen", side_effect=fake_screen),
        patch("jobhunt.multi.llm.draft", return_value=None),
    ):
        multi.run_multi_user_pipeline(mock=False)

    assert screened_ids == ["gh:acme:new2"]


def test_web_templates_sync_dynamic_package_version():
    """Rendered landing and dashboard views must dynamically match jobhunt.__version__."""
    from jobhunt import __version__, create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert f"releases/tag/v{__version__}" in html
        assert f"Release v{__version__}" in html



