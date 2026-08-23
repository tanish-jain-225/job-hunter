"""Comprehensive multi-user dynamic execution and tenant isolation test suite."""
from __future__ import annotations

from unittest.mock import patch, MagicMock


from jobhunt import cli, digest, llm, mailer
from jobhunt.fetch import Job
from jobhunt.store import Store
import app as flask_app


def test_llm_dynamic_candidate_name_resolution():
    """Verify candidate name resolves dynamically from profile name, email, or clean fallback."""
    # Profile with explicit name
    assert llm._get_candidate_name({"name": "Alice Wonderland"}) == "Alice Wonderland"

    # Profile with email only
    assert llm._get_candidate_name({"email": "bob.marley@domain.com"}) == "Bob Marley"
    assert llm._get_candidate_name({"email": "charlie_smith@example.org"}) == "Charlie Smith"

    # Empty profile
    assert llm._get_candidate_name({}) == "Candidate"
    assert llm._get_candidate_name(None) == "Candidate"


def test_llm_dynamic_system_prompts():
    """Verify screening and draft prompts dynamically adapt to candidate details without hardcoded values."""
    custom_profile = {
        "name": "Sarah Connor",
        "email": "sarah@cyberdyne.org",
        "education": "M.S. in Machine Learning, Stanford University",
        "years_experience": 5.0,
        "seniority": "senior",
        "skills": ["Rust", "PyTorch", "CUDA", "Distributed Systems"],
        "target_keywords": ["ML Infrastructure Engineer", "AI Systems Lead"],
        "domains": ["high-throughput AI training", "GPU kernels"],
        "notable_projects": [
            "Skynet Neural Engine — 100k GPU cluster orchestration with custom CUDA kernels",
            "Terminator Vision — Real-time computer vision inference with 2ms p99 latency"
        ],
        "github": "https://github.com/sarahconnor"
    }

    screen_prompt = llm._build_screen_system(custom_profile)
    assert "candidate Sarah Connor" in screen_prompt
    assert "Stanford University" in screen_prompt
    assert "5.0 YoE" in screen_prompt
    assert "ML Infrastructure Engineer" in screen_prompt
    assert "Tanish" not in screen_prompt
    assert "VESIT" not in screen_prompt

    draft_prompt = llm._build_draft_system(custom_profile)
    assert "Sarah Connor" in draft_prompt
    assert "Stanford University" in draft_prompt
    assert "Skynet Neural Engine" in draft_prompt
    assert "https://github.com/sarahconnor" in draft_prompt
    assert "Tanish" not in draft_prompt
    assert "Edvanta" not in draft_prompt


def test_digest_build_dynamic_rendering():
    """Verify digest.build renders dynamic candidate identity and briefing."""
    profile_a = {
        "name": "Alex Mercer",
        "education": "B.Tech Computer Science",
        "email": "alex@mercer.dev"
    }

    jobs = [
        Job(
            job_id="ashby:openai:123",
            ats="ashby",
            company="OpenAI",
            title="Research Engineer",
            location="Remote",
            url="https://jobs.ashbyhq.com/openai/123",
            description="High performance AI model training and ML infrastructure.",
            score=9.5,
            reason="Direct ML match",
            draft={
                "fit_summary": "Exceptional fit for AI training infrastructure.",
                "india_eligibility": "Worldwide Remote",
                "best_project": "Distributed Matrix Multiplier",
                "tailored_bullets": ["Built high-speed matrix kernels"],
                "matching_skills": ["CUDA", "C++"],
                "gaps": ["None"],
                "cover_note": "Cover note for Alex",
                "cold_outreach": "Hi team, I am Alex...",
                "questions_to_ask": ["How do you handle checkpointing?"]
            }
        )
    ]

    subject, html_content = digest.build(jobs, scanned=100, candidates=10, stats={"tracked": 50}, profile=profile_a)
    assert "Alex Mercer" in subject
    assert "Alex Mercer" in html_content
    assert "B.Tech Computer Science" in html_content
    assert "Exceptional fit for AI training infrastructure." in html_content
    assert "Tanish" not in html_content


def test_store_multi_tenant_isolation(tmp_path, monkeypatch):
    """Verify two distinct users have strictly isolated Store instances and local caches."""
    monkeypatch.setenv("VERCEL", "0")

    store_user_a = Store("seen.json", user_email="user_a@enterprise.com")
    store_user_b = Store("seen.json", user_email="user_b@startup.io")

    # Verify distinct cache paths
    assert store_user_a.path != store_user_b.path
    assert "user_a" in str(store_user_a.path) or "seen_" in str(store_user_a.path)

    # User A adds a job
    job_a_id = store_user_a.add_job(
        title="Backend Engineer",
        company="Company Alpha",
        score=8.5,
        reason="Python & SQL match"
    )

    # User B should NOT have User A's job
    assert job_a_id in store_user_a.data
    assert job_a_id not in store_user_b.data
    assert len(store_user_b.data) == 0


def test_dynamic_mailer_dispatch():
    """Verify mailer.send dispatches to dynamically provided recipient."""
    with patch("smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        with patch.dict("os.environ", {"SMTP_USER": "mailer@system.com", "SMTP_PASS": "secretpass123"}):
            mailer.send("Subject Line", "<p>Body</p>", to_email="candidate_123@domain.org")

            assert mock_instance.send_message.called
            msg = mock_instance.send_message.call_args[0][0]
            assert msg["To"] == "candidate_123@domain.org"
            assert msg["From"] == "mailer@system.com"


def test_run_pipeline_dynamic_execution(tmp_path, monkeypatch):
    """Verify run_pipeline executes with dynamic user profile and store."""
    custom_profile = {
        "name": "Dev User",
        "email": "dev.user@cloud.com",
        "core_skills": ["Python", "FastAPI", "PostgreSQL"],
        "target_titles": ["Python Developer", "Backend Engineer"],
        "notable_projects": ["High Speed API Gateway"],
    }

    user_store = Store(tmp_path / "seen_test.json", user_email="dev.user@cloud.com")

    exit_code = cli.run_pipeline(
        profile=custom_profile,
        user_email="dev.user@cloud.com",
        store=user_store,
        scorer="keyword",
        mock=True,
        send=False,
    )

    assert exit_code == 0
    assert len(user_store.data) > 0


def test_flask_per_user_pipeline_state():
    """Verify Flask app maintains isolated thread-safe pipeline states per user."""
    state_a = flask_app._set_user_pipeline_state("user1@site.com", running=True, step="scanning", message="User 1 Scanning")
    state_b = flask_app._set_user_pipeline_state("user2@site.com", running=False, step="idle", message="User 2 Idle")

    assert state_a["running"] is True
    assert state_a["message"] == "User 1 Scanning"

    assert state_b["running"] is False
    assert state_b["message"] == "User 2 Idle"

    # Verify retrieval
    assert flask_app._get_user_pipeline_state("user1@site.com")["message"] == "User 1 Scanning"
    assert flask_app._get_user_pipeline_state("user2@site.com")["message"] == "User 2 Idle"


def test_store_supabase_purge_deleted_jobs(tmp_path, monkeypatch):
    """Verify that pulling remote jobs from Supabase purges deleted local cache jobs."""
    # Seed local cache file with 3 jobs
    cache_file = tmp_path / "seen_purge.json"
    st = Store(cache_file, user_email="purge_user@test.com")
    st.data = {
        "greenhouse:stripe:1": {"job_id": "greenhouse:stripe:1", "company": "Stripe", "score": 9.0},
        "ashby:ramp:2": {"job_id": "ashby:ramp:2", "company": "Ramp", "score": 8.0},
        "lever:warp:3": {"job_id": "lever:warp:3", "company": "Warp", "score": 7.0},
    }
    st.save()

    # Mock remote db to only return greenhouse:stripe:1 and lever:warp:3 (ashby:ramp:2 is deleted/missing)
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.is_configured", property(lambda self: True))
    monkeypatch.setattr(
        "jobhunt.memory.SupabaseMemory.load_user_jobs",
        lambda self, email, token=None: {
            "greenhouse:stripe:1": {"job_id": "greenhouse:stripe:1", "company": "Stripe", "score": 9.0},
            "lever:warp:3": {"job_id": "lever:warp:3", "company": "Warp", "score": 7.0},
        }
    )

    # Initialize store again to trigger cloud sync pull & check for purging
    st2 = Store(cache_file, user_email="purge_user@test.com")
    
    # Assert missing job is purged
    assert "ashby:ramp:2" not in st2.data
    assert "greenhouse:stripe:1" in st2.data
    assert "lever:warp:3" in st2.data


import pytest

@pytest.fixture
def client():
    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_api_run_async_endpoint(client, monkeypatch):
    """Verify that /api/run endpoint starts execution asynchronously and returns HTTP 202."""
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    monkeypatch.setattr("jobhunt.web.routes.pipeline.get_current_user_context", lambda: ("async_user@test.com", "token123"))
    monkeypatch.setattr("jobhunt.memory.SupabaseMemory.is_configured", property(lambda self: True))
    monkeypatch.setattr(
        "jobhunt.memory.SupabaseMemory.get_user_profile",
        lambda *a, **kw: {
            "onboarding_completed": True,
            "name": "Tester",
            "title": "Engineer",
            "skills": ["Python"],
            "target_keywords": ["Engineer"],
            "education": "BS",
            "experience_years": 3,
            "exclude_keywords": ["Manager"],
        }
    )

    # Mock threading.Thread to assert it gets spawned but don't actually run it to save time
    mock_start = MagicMock()
    monkeypatch.setattr("threading.Thread.start", mock_start)

    # Call /api/run in production-like non-testing mode by patching app.testing
    from app import app
    monkeypatch.setattr(app, "testing", False)

    res = client.post("/api/run", json={"mock": True})
    assert res.status_code == 202
    assert res.get_json()["status"] == "success"
    assert "started in background" in res.get_json()["message"]
    assert mock_start.called


def test_store_auto_pruning_limits(tmp_path, monkeypatch):
    """Verify that Store.save() automatically prunes old inactive jobs while preserving active ones."""
    cache_file = tmp_path / "seen_pruning_limit.json"
    st = Store(cache_file)
    
    # Setup 5 jobs
    st.data = {
        "greenhouse:stripe:1": {"job_id": "greenhouse:stripe:1", "company": "Stripe", "score": 9.0, "applied": True, "application_stage": "applied", "first_seen": "2026-08-01T10:00:00"},
        "ashby:ramp:2": {"job_id": "ashby:ramp:2", "company": "Ramp", "score": 8.0, "applied": False, "application_stage": "to_apply", "first_seen": "2026-08-02T10:00:00"},
        "lever:warp:3": {"job_id": "lever:warp:3", "company": "Warp", "score": 7.0, "applied": False, "application_stage": "to_apply", "first_seen": "2026-08-03T10:00:00"},
        "ashby:warp:4": {"job_id": "ashby:warp:4", "company": "Warp", "score": 6.0, "applied": False, "application_stage": "to_apply", "first_seen": "2026-08-04T10:00:00"},
        "greenhouse:warp:5": {"job_id": "greenhouse:warp:5", "company": "Warp", "score": 5.0, "applied": False, "application_stage": "to_apply", "first_seen": "2026-08-05T10:00:00"},
    }

    # Restrict limit to 3 tracked jobs
    monkeypatch.setenv("MAX_TRACKED_JOBS_COUNT", "3")
    
    # Save (which triggers prune_old_jobs)
    st.save(auto_export=False)
    
    # Should keep Stripe (since it's applied), Warp 5 (newest timestamp), and Warp 4 (next newest)
    # Ramp 2 and Warp 3 (oldest inactive jobs) should be pruned
    assert "greenhouse:stripe:1" in st.data
    assert "greenhouse:warp:5" in st.data
    assert "ashby:warp:4" in st.data
    assert "ashby:ramp:2" not in st.data
    assert "lever:warp:3" not in st.data


def test_run_pipeline_jobs_throttling(tmp_path, monkeypatch):
    """Verify that run_pipeline throttles LLM screening by MAX_JOBS_TO_SCREEN limit."""
    monkeypatch.setenv("MAX_JOBS_TO_SCREEN", "2")
    user_store = Store(tmp_path / "seen_throttle.json")
    
    # Mock prefilter to return 5 jobs
    mock_jobs = [
        Job("greenhouse:stripe:1", "greenhouse", "Stripe", "SE", "Remote", "http://stripe.com", "JD1"),
        Job("ashby:ramp:2", "ashby", "Ramp", "SE", "Remote", "http://ramp.com", "JD2"),
        Job("lever:warp:3", "lever", "Warp", "SE", "Remote", "http://warp.com", "JD3"),
        Job("ashby:warp:4", "ashby", "Warp", "SE", "Remote", "http://warp4.com", "JD4"),
        Job("greenhouse:warp:5", "greenhouse", "Warp", "SE", "Remote", "http://warp5.com", "JD5"),
    ]
    monkeypatch.setattr("jobhunt.cli.fetch_all_mock", lambda: mock_jobs)
    
    profile = {"name": "Tester", "skills": ["Python"]}
    
    # Execute pipeline in mock mode (using keyword scorer)
    cli.run_pipeline(
        profile=profile,
        user_email="test@user.com",
        store=user_store,
        scorer="keyword",
        mock=True,
        send=False,
    )
    
    # Only 2 jobs should have been screened and added to the store (due to throttle cap of 2)
    assert len(user_store.data) == 2


