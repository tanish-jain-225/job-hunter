"""Unit tests for Public Multi-Tenant Resume Studio & Notification Toggles."""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest

from app import app
from jobhunt.memory import SupabaseMemory


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
    monkeypatch.setenv("GEMINI_API_KEY", "mock-gemini-key")



def test_resume_upload_text_payload(client, mock_supabase_env):
    mock_profile = {
        "name": "Sarah Connor",
        "current_title": "Senior Cloud Architect",
        "years_experience": 6,
        "education": "M.S. in Software Engineering",
        "core_skills": ["AWS", "Kubernetes", "Terraform", "Python", "Go"],
        "target_titles": ["Staff Cloud Architect", "Principal SRE"],
        "domains": ["infrastructure", "cloud"],
        "notable_projects": ["Designed multi-region cloud resilience architecture"],
        "seniority": "staff",
    }

    with patch("jobhunt.llm.build_profile", return_value=mock_profile), \
         patch("requests.post", return_value=MagicMock(status_code=201)), \
         patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])):

        res = client.post(
            "/api/resume/upload",
            json={"resume_text": "Experienced Cloud Architect with AWS & Terraform expertise."},
            headers={"Authorization": "Bearer mock-token"}
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert data["profile"]["name"] == "Sarah Connor"
        assert data["profile"]["title"] == "Senior Cloud Architect"
        assert "Terraform" in data["profile"]["skills"]


def test_resume_upload_file_multipart(client, mock_supabase_env):
    mock_profile = {
        "name": "David Miller",
        "current_title": "Full Stack Engineer",
        "years_experience": 3,
        "education": "B.S. in Computer Science",
        "core_skills": ["React", "Node.js", "PostgreSQL", "TypeScript"],
        "target_titles": ["Full Stack Engineer", "Frontend Specialist"],
        "domains": ["fullstack", "web"],
        "notable_projects": ["Built reactive dashboard systems"],
        "seniority": "mid",
    }

    file_content = b"Resume text content for David Miller..."
    data = {
        "file": (io.BytesIO(file_content), "david_resume.txt")
    }

    with patch("jobhunt.llm.build_profile", return_value=mock_profile), \
         patch("requests.post", return_value=MagicMock(status_code=201)), \
         patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])):

        res = client.post(
            "/api/resume/upload",
            data=data,
            content_type="multipart/form-data",
            headers={"Authorization": "Bearer mock-token"}
        )
        assert res.status_code == 200
        result = res.get_json()
        assert result["status"] == "success"
        assert result["profile"]["name"] == "David Miller"
        assert result["profile"]["resume_filename"] == "david_resume.txt"


def test_resume_upload_empty_fails(client, mock_supabase_env):
    res = client.post(
        "/api/resume/upload",
        json={},
        headers={"Authorization": "Bearer mock-token"}
    )
    assert res.status_code == 400
    assert "No resume file or text" in res.get_json()["message"]


def test_profile_get_and_post_notification_preferences(client, mock_supabase_env):
    mock_existing_profile = [{
        "email": "dev@test.com",
        "name": "Dev User",
        "title": "Backend Dev",
        "email_notifications_enabled": True,
        "notification_email": "alerts@dev.com",
        "min_score_notification": 8.0,
        "skills": ["Python", "FastAPI"],
    }]

    with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: mock_existing_profile)):
        res = client.get("/api/profile", headers={"Authorization": "Bearer mock-token"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert data["profile"]["email_notifications_enabled"] is True
        assert data["profile"]["notification_email"] == "alerts@dev.com"

    # Test saving updated preferences
    with patch("requests.post", return_value=MagicMock(status_code=201)):
        res_post = client.post(
            "/api/profile",
            json={
                "name": "Dev User Updated",
                "title": "Lead Backend Dev",
                "email_notifications_enabled": False,
                "notification_email": "alerts@dev.com",
                "min_score_notification": 8.5,
                "skills": ["Python", "FastAPI", "PostgreSQL", "Redis"]
            },
            headers={"Authorization": "Bearer mock-token"}
        )
        assert res_post.status_code == 200
        assert res_post.get_json()["status"] == "success"


def test_get_or_initialize_user(mock_supabase_env):
    mem = SupabaseMemory()
    # When user does not exist in DB, a minimal blank stub is returned.
    # Content fields are intentionally empty — no fake defaults are written.
    with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])), \
         patch("requests.post", return_value=MagicMock(status_code=201)):

        profile = mem.get_or_initialize_user(
            "tanish.jain@example.com",
            user_meta={"full_name": "Tanish Jain"}
        )
        # New user stub: email is set, name/skills are blank, flag is False
        assert profile["email"] == "tanish.jain@example.com"
        assert profile["name"] == ""          # no fake defaults
        assert profile["skills"] == []         # no pre-populated skill list
        assert profile["onboarding_completed"] is False
        assert profile["email_notifications_enabled"] is False


def test_onboarding_completed_profile_save(client, mock_supabase_env):
    """Verify onboarding wizard saves profile with onboarding_completed flag."""
    with patch("requests.post", return_value=MagicMock(status_code=201)):
        res_post = client.post(
            "/api/profile",
            json={
                "name": "Sarah Connor",
                "title": "Machine Learning Engineer",
                "experience_years": 4.5,
                "education": "M.S. AI",
                "skills": ["PyTorch", "Rust", "CUDA"],
                "target_keywords": ["ML Infra", "AI Systems"],
                "exclude_keywords": ["Manager", "Sales"],
                "email_notifications_enabled": True,
                "notification_email": "sarah@cyberdyne.org",
                "min_score_notification": 8.0,
                "onboarding_completed": True
            },
            headers={"Authorization": "Bearer mock-token"}
        )
        assert res_post.status_code == 200
        data = res_post.get_json()
        assert data["status"] == "success"
        assert data["profile"]["onboarding_completed"] is True
        assert data["profile"]["name"] == "Sarah Connor"


def test_profile_reset_endpoint(client, mock_supabase_env):
    """Verify POST /api/profile/reset properly resets profile to blank stub."""
    with patch("requests.post", return_value=MagicMock(status_code=201)), \
         patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [{"email": "user@test.com", "name": "Existing Name"}])):
        res = client.post(
            "/api/profile/reset",
            headers={"Authorization": "Bearer mock-token"}
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert data["profile"]["title"] == ""
        assert data["profile"]["skills"] == []
        assert data["profile"]["onboarding_completed"] is False


def test_profile_reset_unauthenticated(client, monkeypatch):
    """Verify POST /api/profile/reset returns 401 when unauthenticated and email is missing."""
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    with patch("jobhunt.web.routes.profile.get_current_user_context", return_value=(None, None)):
        res = client.post("/api/profile/reset")
        assert res.status_code == 401
        assert res.get_json()["status"] == "error"


def test_profile_get_unconfigured_supabase(client, monkeypatch, tmp_path):
    """Verify GET /api/profile falls back to local file when Supabase is not configured."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("AUTH_REQUIRED", "false")

    sample_profile = tmp_path / "profile.json"
    sample_profile.write_text('{"name": "Local Dev", "skills": ["Python"]}', encoding="utf-8")

    with patch("jobhunt.cli._load_profile", return_value={"name": "Local Dev", "skills": ["Python"]}):
        res = client.get("/api/profile")
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert data["profile"]["name"] == "Local Dev"
        assert data["profile"]["onboarding_completed"] is True
        assert data["memory_connected"] is False


def test_profile_post_extracts_skills_from_resume_text(client, mock_supabase_env):
    """Verify POST /api/profile auto-extracts skills from resume_text if skills are omitted."""
    with patch("requests.post", return_value=MagicMock(status_code=201)):
        res = client.post(
            "/api/profile",
            json={
                "name": "Alex Smith",
                "resume_text": "Experienced engineer with Python, Docker, Kubernetes, and PostgreSQL expertise.",
                "skills": []
            },
            headers={"Authorization": "Bearer mock-token"}
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert "Python" in data["profile"]["skills"]
        assert "Docker" in data["profile"]["skills"]


def test_resume_upload_pdf_file_fallback_parsing(client, mock_supabase_env):
    """Verify /api/resume/upload with PDF file correctly extracts text and falls back smartly."""
    pdf_content = b"%PDF-1.4 Mock PDF Stream"
    data = {
        "file": (io.BytesIO(pdf_content), "resume.pdf")
    }

    with patch("jobhunt.llm.extract_text_from_pdf", return_value="John Doe\nExperienced Python and AWS engineer with microservices."), \
         patch("jobhunt.llm.build_profile", side_effect=Exception("LLM Rate Limit")), \
         patch("requests.post", return_value=MagicMock(status_code=201)), \
         patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])):

        res = client.post(
            "/api/resume/upload",
            data=data,
            content_type="multipart/form-data",
            headers={"Authorization": "Bearer mock-token"}
        )
        assert res.status_code == 200
        data_res = res.get_json()
        assert data_res["status"] == "success"
        assert data_res["profile"]["name"] == "John Doe"
        assert "Python" in data_res["profile"]["skills"] or "AWS" in data_res["profile"]["skills"]


