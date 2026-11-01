"""Targeted tests for Custom Companies, Jobs route edge-cases, and Pipeline cloud dispatch."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_supabase_env(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock-project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "mock-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "mock-service-key")
    monkeypatch.setenv("AUTH_REQUIRED", "false")


def test_api_companies_filtering_and_corrupt_yaml(client, tmp_path: Path, mock_supabase_env):
    """Verify /api/companies filters by ATS, search term, and handles corrupt YAML gracefully."""
    comp_file = tmp_path / "companies.yaml"
    comp_file.write_text(
        "companies:\n  - name: Stripe\n    slug: stripe\n    ats: greenhouse\n  - name: Linear\n    slug: linear\n    ats: ashby\n",
        encoding="utf-8",
    )

    with (
        patch("jobhunt.web.routes.jobs.ROOT", tmp_path),
        patch("jobhunt.cli._cfg", return_value={"companies_file": "companies.yaml"}),
    ):
        # 1. Total list
        res = client.get("/api/companies")
        assert res.status_code == 200
        assert res.get_json()["total"] == 2

        # 2. Filter by ATS
        res_ats = client.get("/api/companies?ats=ashby")
        assert res_ats.status_code == 200
        assert res_ats.get_json()["count"] == 1
        assert res_ats.get_json()["companies"][0]["slug"] == "linear"

        # 3. Filter by search
        res_search = client.get("/api/companies?search=str")
        assert res_search.status_code == 200
        assert res_search.get_json()["count"] == 1
        assert res_search.get_json()["companies"][0]["slug"] == "stripe"

        # 4. Corrupt YAML
        comp_file.write_text("companies: [unclosed yaml", encoding="utf-8")
        res_corrupt = client.get("/api/companies")
        assert res_corrupt.status_code == 200
        assert res_corrupt.get_json()["total"] == 0


def test_api_companies_custom_retrieval(client, mock_supabase_env, tmp_path: Path):
    """Verify GET /api/companies/custom returns target boards from Supabase or local cache."""
    mock_prof = {"custom_companies": [{"ats": "greenhouse", "slug": "acme", "name": "Acme Corp"}]}
    with patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value=mock_prof):
        res = client.get("/api/companies/custom")
        assert res.status_code == 200
        data = res.get_json()
        assert data["count"] == 1
        assert data["companies"][0]["slug"] == "acme"

    # Local fallback when Supabase is unconfigured
    with (
        patch("jobhunt.web.routes.jobs.get_current_user_context", return_value=(None, None)),
        patch("jobhunt.memory.SupabaseMemory.is_configured", False),
        patch("jobhunt.web.routes.jobs.get_user_profile_path", return_value=tmp_path / "missing.json"),
        patch("jobhunt.web.routes.jobs.cli._load_profile", return_value={"custom_companies": [{"ats": "lever", "slug": "beta"}]}),
    ):
        res_local = client.get("/api/companies/custom")
        assert res_local.status_code == 200
        assert res_local.get_json()["count"] == 1
        assert res_local.get_json()["companies"][0]["slug"] == "beta"


def test_api_companies_add_validation_and_persistence(client, mock_supabase_env):
    """Verify POST /api/companies/add validates inputs, verifies board, and handles errors."""
    # 1. Unrecognized URL
    res_bad_url = client.post(
        "/api/companies/add",
        json={"url": "https://example.com/careers/unknown"},
    )
    assert res_bad_url.status_code == 400
    assert "Could not identify ATS" in res_bad_url.get_json()["message"]

    # 2. Missing ATS or slug
    res_missing = client.post(
        "/api/companies/add",
        json={"ats": "greenhouse"},
    )
    assert res_missing.status_code == 400
    assert "ATS type and company slug are required" in res_missing.get_json()["message"]

    # 3. Unsupported ATS
    res_unsupported = client.post(
        "/api/companies/add",
        json={"ats": "unsupported_ats", "slug": "acme"},
    )
    assert res_unsupported.status_code == 400
    assert "Unsupported ATS" in res_unsupported.get_json()["message"]

    # 4. Live board verification failure
    with patch("jobhunt.verify.check_single_board", return_value=(None, False, "404")):
        res_check_fail = client.post(
            "/api/companies/add",
            json={"ats": "greenhouse", "slug": "nonexistent-co"},
        )
        assert res_check_fail.status_code == 400
        assert "Board validation failed" in res_check_fail.get_json()["message"]

    # 5. Success with Supabase upsert
    with (
        patch("jobhunt.verify.check_single_board", return_value=(None, True, "200")),
        patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=True),
    ):
        res_ok = client.post(
            "/api/companies/add",
            json={"ats": "greenhouse", "slug": "gitlab", "name": "GitLab"},
        )
        assert res_ok.status_code == 200
        assert res_ok.get_json()["status"] == "success"

    # 6. Supabase upsert failure -> 503
    with (
        patch("jobhunt.verify.check_single_board", return_value=(None, True, "200")),
        patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=False),
    ):
        res_fail = client.post(
            "/api/companies/add",
            json={"ats": "greenhouse", "slug": "gitlab", "name": "GitLab"},
        )
        assert res_fail.status_code == 503
        assert "could not be saved" in res_fail.get_json()["message"]


def test_api_companies_delete_validation(client, mock_supabase_env):
    """Verify DELETE /api/companies/custom handles validation, Supabase, and local deletion."""
    # 1. Missing fields
    res_missing = client.delete("/api/companies/custom", json={})
    assert res_missing.status_code == 400

    # 2. Supabase deletion success
    with (
        patch(
            "jobhunt.memory.SupabaseMemory.get_user_profile",
            return_value={"custom_companies": [{"ats": "greenhouse", "slug": "gitlab"}]},
        ),
        patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=True),
    ):
        res_ok = client.delete(
            "/api/companies/custom",
            json={"ats": "greenhouse", "slug": "gitlab"},
        )
        assert res_ok.status_code == 200
        assert "Removed greenhouse:gitlab" in res_ok.get_json()["message"]

    # 3. Supabase deletion failure -> 503
    with (
        patch(
            "jobhunt.memory.SupabaseMemory.get_user_profile",
            return_value={"custom_companies": [{"ats": "greenhouse", "slug": "gitlab"}]},
        ),
        patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=False),
    ):
        res_fail = client.delete(
            "/api/companies/custom",
            json={"ats": "greenhouse", "slug": "gitlab"},
        )
        assert res_fail.status_code == 503


def test_api_jobs_add_edge_cases(client, mock_supabase_env):
    """Verify POST /api/jobs/add handles edge-case validations and store persistence failures."""
    # 1. Non-string text fields
    res_bad_type = client.post(
        "/api/jobs/add",
        json={"title": "Dev", "company": "Co", "location": 123},
    )
    assert res_bad_type.status_code == 400
    assert "must be strings" in res_bad_type.get_json()["message"]

    # 2. Invalid applied boolean string
    res_bad_applied = client.post(
        "/api/jobs/add",
        json={"title": "Dev", "company": "Co", "applied": "not_a_bool"},
    )
    assert res_bad_applied.status_code == 400
    assert "Applied must be a boolean" in res_bad_applied.get_json()["message"]

    # 3. Invalid stage
    res_bad_stage = client.post(
        "/api/jobs/add",
        json={"title": "Dev", "company": "Co", "stage": "unknown_stage"},
    )
    assert res_bad_stage.status_code == 400
    assert "Invalid stage" in res_bad_stage.get_json()["message"]

    # 4. Discrepancy between applied and stage
    res_discrepancy = client.post(
        "/api/jobs/add",
        json={"title": "Dev", "company": "Co", "applied": False, "stage": "interviewing"},
    )
    assert res_discrepancy.status_code == 400
    assert "Applied must match the selected stage" in res_discrepancy.get_json()["message"]

    # 5. Store persistence failure on add_job -> 503
    with patch("jobhunt.store.Store.add_job", return_value=None):
        res_store_fail = client.post(
            "/api/jobs/add",
            json={"title": "Dev", "company": "Co"},
        )
        assert res_store_fail.status_code == 503
        assert "Job could not be persisted" in res_store_fail.get_json()["message"]

    # 6. Store update_stage failure -> 503
    with (
        patch("jobhunt.store.Store.add_job", return_value="custom:1"),
        patch("jobhunt.store.Store.update_stage", return_value=False),
    ):
        res_stage_fail = client.post(
            "/api/jobs/add",
            json={"title": "Dev", "company": "Co", "stage": "interviewing", "applied": True},
        )
        assert res_stage_fail.status_code == 503
        assert "Job stage could not be persisted" in res_stage_fail.get_json()["message"]


def test_api_jobs_followup_route(client, mock_supabase_env):
    """Verify POST /api/jobs/followup retrieves candidate name and generates structured note."""
    with (
        patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value={"name": "Alex Chen"}),
        patch("jobhunt.llm.generate_followup_note", return_value={"subject": "Follow-up", "body": "Thank you..."}) as mock_gen,
    ):
        res = client.post(
            "/api/jobs/followup",
            json={"title": "Staff Engineer", "company": "Acme Corp", "applied_on": "2026-10-15"},
        )
        assert res.status_code == 200
        assert res.get_json()["followup"]["subject"] == "Follow-up"
        mock_gen.assert_called_once_with(
            job_title="Staff Engineer",
            company="Acme Corp",
            candidate_name="Alex Chen",
            applied_on="2026-10-15",
            stage="applied",
        )


def test_api_run_cloud_dispatch_edge_cases(client, mock_supabase_env, monkeypatch: pytest.MonkeyPatch):
    """Verify POST /api/run cloud dispatch validates authentication, repo config, and Vercel failures."""
    monkeypatch.setenv("GH_TOKEN", "mock-gh-token")
    mock_ready_profile = {
        "name": "Dev User",
        "skills": ["Python", "Docker"],
        "target_keywords": ["Backend"],
        "onboarding_completed": True,
    }

    # 1. Unauthenticated cloud dispatch -> 403
    with (
        patch("jobhunt.web.routes.pipeline.get_current_user_context", return_value=(None, None)),
        patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value=mock_ready_profile),
        patch("jobhunt.web.routes.pipeline.get_user_profile", return_value=mock_ready_profile),
        patch("jobhunt.web.routes.pipeline.is_profile_complete", return_value=True),
    ):
        res_no_auth = client.post("/api/run", json={"cloud": True})
        assert res_no_auth.status_code == 403
        assert res_no_auth.get_json()["code"] == "USER_EMAIL_REQUIRED"

    # 2. Missing GITHUB_REPOSITORY -> 500
    def mock_env_get(key, default=""):
        if key in ("GITHUB_REPOSITORY", "VERCEL_GIT_REPO_OWNER", "VERCEL_GIT_REPO_SLUG"):
            return ""
        if key == "GH_TOKEN":
            return "mock-gh-token"
        return default

    with (
        patch("jobhunt.web.routes.pipeline.get_current_user_context", return_value=("user@test.com", "token")),
        patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value=mock_ready_profile),
        patch("jobhunt.web.routes.pipeline.get_user_profile", return_value=mock_ready_profile),
        patch("jobhunt.web.routes.pipeline.is_profile_complete", return_value=True),
        patch("jobhunt.web.routes.pipeline.os.environ.get", side_effect=mock_env_get),
    ):
        res_no_repo = client.post("/api/run", json={"cloud": True})
        assert res_no_repo.status_code == 500
        assert res_no_repo.get_json()["code"] == "REPO_NOT_CONFIGURED"

    # 3. Vercel environment with GitHub API failure -> 502
    mock_resp = MagicMock(status_code=401, text="Unauthorized")
    with (
        patch("jobhunt.web.routes.pipeline.get_current_user_context", return_value=("user@test.com", "token")),
        patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value=mock_ready_profile),
        patch("jobhunt.web.routes.pipeline.get_user_profile", return_value=mock_ready_profile),
        patch("jobhunt.web.routes.pipeline.is_profile_complete", return_value=True),
        patch("jobhunt.web.routes.pipeline.os.environ.get", lambda key, default="": "1" if key == "VERCEL" else ("testuser/testrepo" if key == "GITHUB_REPOSITORY" else ("mock-gh-token" if key == "GH_TOKEN" else default))),
        patch("requests.post", return_value=mock_resp),
    ):
        res_gh_fail = client.post("/api/run", json={"cloud": True})
        assert res_gh_fail.status_code == 502
        assert res_gh_fail.get_json()["code"] == "CLOUD_DISPATCH_FAILED"
