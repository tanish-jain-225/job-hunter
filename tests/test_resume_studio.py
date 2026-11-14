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

    with (
        patch("jobhunt.llm.build_profile", return_value=mock_profile),
        patch("requests.post", return_value=MagicMock(status_code=201)),
        patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])),
    ):
        res = client.post(
            "/api/resume/upload",
            json={"resume_text": "Experienced Cloud Architect with AWS & Terraform expertise."},
            headers={"Authorization": "Bearer mock-token"},
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
    data = {"file": (io.BytesIO(file_content), "david_resume.txt")}

    with (
        patch("jobhunt.llm.build_profile", return_value=mock_profile),
        patch("requests.post", return_value=MagicMock(status_code=201)),
        patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])),
    ):
        res = client.post(
            "/api/resume/upload",
            data=data,
            content_type="multipart/form-data",
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        result = res.get_json()
        assert result["status"] == "success"
        assert result["profile"]["name"] == "David Miller"
        assert result["profile"]["resume_filename"] == "david_resume.txt"


def test_resume_upload_empty_fails(client, mock_supabase_env):
    res = client.post("/api/resume/upload", json={}, headers={"Authorization": "Bearer mock-token"})
    assert res.status_code == 400
    assert "No resume file or text" in res.get_json()["message"]


def test_profile_get_and_post_notification_preferences(client, mock_supabase_env):
    mock_existing_profile = [
        {
            "email": "dev@test.com",
            "name": "Dev User",
            "title": "Backend Dev",
            "email_notifications_enabled": True,
            "notification_email": "alerts@dev.com",
            "min_score_notification": 8.0,
            "skills": ["Python", "FastAPI"],
        }
    ]

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
                "skills": ["Python", "FastAPI", "PostgreSQL", "Redis"],
            },
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res_post.status_code == 200
        assert res_post.get_json()["status"] == "success"


def test_get_or_initialize_user(mock_supabase_env):
    mem = SupabaseMemory()
    # When user does not exist in DB, a minimal blank stub is returned.
    # Content fields are intentionally empty — no fake defaults are written.
    with (
        patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])),
        patch("requests.post", return_value=MagicMock(status_code=201)),
    ):
        profile = mem.get_or_initialize_user("alex.doe@example.com", user_meta={"full_name": "Alex Doe"})
        # New user stub: email is set, name/skills are blank, flag is False
        assert profile["email"] == "alex.doe@example.com"
        assert profile["name"] == ""  # no fake defaults
        assert profile["skills"] == []  # no pre-populated skill list
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
                "onboarding_completed": True,
            },
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res_post.status_code == 200
        data = res_post.get_json()
        assert data["status"] == "success"
        assert data["profile"]["onboarding_completed"] is True
        assert data["profile"]["name"] == "Sarah Connor"


def test_profile_reset_endpoint(client, mock_supabase_env):
    """Verify POST /api/profile/reset properly resets profile to blank stub."""
    with (
        patch("requests.post", return_value=MagicMock(status_code=201)),
        patch(
            "requests.get",
            return_value=MagicMock(status_code=200, json=lambda: [{"email": "user@test.com", "name": "Existing Name"}]),
        ),
    ):
        res = client.post("/api/profile/reset", headers={"Authorization": "Bearer mock-token"})
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert data["profile"]["title"] == ""
        assert data["profile"]["skills"] == []
        assert data["profile"]["notice_period"] == "30_days"
        assert data["profile"]["current_ctc_lpa"] == 0
        assert data["profile"]["expected_ctc_lpa"] == 0
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
                "skills": [],
            },
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert "Python" in data["profile"]["skills"]
        assert "Docker" in data["profile"]["skills"]


def test_resume_upload_pdf_file_fallback_parsing(client, mock_supabase_env):
    """Verify /api/resume/upload with PDF file correctly extracts text and falls back smartly."""
    pdf_content = b"%PDF-1.4 Mock PDF Stream"
    data = {"file": (io.BytesIO(pdf_content), "resume.pdf")}

    with (
        patch(
            "jobhunt.llm.extract_text_from_pdf",
            return_value="John Doe\nExperienced Python and AWS engineer with microservices.",
        ),
        patch("jobhunt.llm.build_profile", side_effect=Exception("LLM Rate Limit")),
        patch("requests.post", return_value=MagicMock(status_code=201)),
        patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])),
    ):
        res = client.post(
            "/api/resume/upload",
            data=data,
            content_type="multipart/form-data",
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        data_res = res.get_json()
        assert data_res["status"] == "success"
        assert data_res["profile"]["name"] == "John Doe"
        assert "Python" in data_res["profile"]["skills"] or "AWS" in data_res["profile"]["skills"]


def test_profile_preferences_notice_and_ctc(client, mock_supabase_env):
    """Verify GET and POST /api/profile/preferences with notice period and CTC parameters."""
    mock_profile = [
        {
            "email": "user@test.com",
            "preferred_locations": ["Bengaluru", "Pune"],
            "location_preference": "all_india",
            "job_types": ["fulltime"],
            "experience_level": "1-3",
            "notice_period": "15_days",
            "current_ctc_lpa": 12,
            "expected_ctc_lpa": 20,
            "min_salary_lpa": 18,
            "preferred_sectors": ["fintech"],
        }
    ]

    with patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: mock_profile)):
        res = client.get("/api/profile/preferences", headers={"Authorization": "Bearer mock-token"})
        assert res.status_code == 200
        prefs = res.get_json()["preferences"]
        assert prefs["notice_period"] == "15_days"
        assert prefs["current_ctc_lpa"] == 12
        assert prefs["expected_ctc_lpa"] == 20
        assert prefs["location_preference"] == "all_india"

    with patch("requests.post", return_value=MagicMock(status_code=201)):
        res_post = client.post(
            "/api/profile/preferences",
            json={
                "notice_period": "immediate",
                "current_ctc_lpa": 15,
                "expected_ctc_lpa": 25,
                "location_preference": "all_india",
            },
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res_post.status_code == 200
        saved = res_post.get_json()["preferences"]
        assert saved["notice_period"] == "immediate"
        assert saved["current_ctc_lpa"] == 15
        assert saved["expected_ctc_lpa"] == 25
        assert saved["location_preference"] == "all_india"


def test_profile_settings_full_roundtrip_persistence(client, mock_supabase_env):
    """Verify POST /api/profile retains notice_period, CTCs, education, and job_types in profile_json."""
    from jobhunt.memory import SupabaseMemory

    posted_payload = {}

    def mock_post(url, headers=None, params=None, json=None, timeout=None):
        nonlocal posted_payload
        posted_payload = json
        return MagicMock(status_code=201)

    mem = SupabaseMemory()
    with patch("jobhunt.memory._get_session") as mock_sess:
        mock_sess.return_value.post.side_effect = mock_post
        ok = mem.upsert_user_profile(
            "candidate@test.com",
            {
                "name": "Jane Doe",
                "education": "B.Tech Computer Science",
                "notice_period": "60_days",
                "current_ctc_lpa": 14.5,
                "expected_ctc_lpa": 22.0,
                "job_types": ["fulltime", "remote"],
                "preferred_locations": ["Bengaluru", "Pune"],
            },
        )
        assert ok is True
        assert posted_payload["profile_json"]["notice_period"] == "60_days"
        assert posted_payload["profile_json"]["current_ctc_lpa"] == 14.5
        assert posted_payload["profile_json"]["expected_ctc_lpa"] == 22.0
        assert posted_payload["profile_json"]["education"] == "B.Tech Computer Science"
        assert posted_payload["profile_json"]["job_types"] == ["fulltime", "remote"]

    # Now verify get_user_profile reconstructs them cleanly from row + profile_json
    mock_db_row = [
        {
            "email": "candidate@test.com",
            "name": "Jane Doe",
            "education": "B.Tech Computer Science",
            "profile_json": posted_payload["profile_json"],
            "preferred_locations": ["Bengaluru", "Pune"],
            "job_types": ["fulltime", "remote"],
        }
    ]
    with patch("jobhunt.memory._get_session") as mock_sess:
        mock_sess.return_value.get.return_value = MagicMock(status_code=200, json=lambda: mock_db_row)
        prof = mem.get_user_profile("candidate@test.com")
        assert prof is not None
        assert prof["notice_period"] == "60_days"
        assert prof["current_ctc_lpa"] == 14.5
        assert prof["expected_ctc_lpa"] == 22.0
        assert prof["education"] == "B.Tech Computer Science"
        assert prof["job_types"] == ["fulltime", "remote"]
        assert prof["min_score_notification"] == 7.5


def test_resume_upload_size_limit_rejection(client, mock_supabase_env):
    """Verify POST /api/resume/upload rejects files exceeding 5MB."""
    import io

    huge_file = io.BytesIO(b"A" * (6 * 1024 * 1024))
    res = client.post(
        "/api/resume/upload",
        data={"file": (huge_file, "large_resume.txt")},
        content_type="multipart/form-data",
        headers={"Authorization": "Bearer mock-token"},
    )
    assert res.status_code == 400
    assert "5MB" in res.get_json()["message"]


def test_resume_upload_text_length_limit_rejection(client, mock_supabase_env):
    """Verify POST /api/resume/upload rejects text exceeding 100k characters."""
    res = client.post(
        "/api/resume/upload",
        json={"resume_text": "A" * 100_001, "filename": "huge.txt"},
        headers={"Authorization": "Bearer mock-token"},
    )
    assert res.status_code == 400
    assert "maximum allowed length" in res.get_json()["message"]


def test_resume_upload_unsupported_extension_rejection(client, mock_supabase_env):
    """Verify POST /api/resume/upload rejects non-PDF and non-TXT extensions."""
    import io

    doc_file = io.BytesIO(b"binary document content")
    res = client.post(
        "/api/resume/upload",
        data={"file": (doc_file, "resume.docx")},
        content_type="multipart/form-data",
        headers={"Authorization": "Bearer mock-token"},
    )
    assert res.status_code == 400
    assert "Only PDF and TXT" in res.get_json()["message"]


def test_resume_upload_fallback_experience_and_clean_name(client, mock_supabase_env):
    """Verify smart fallback parses YoE accurately and sanitizes username without numeric suffixes."""
    raw_resume = """
    Tanish Jain
    Full Stack Developer
    B.Tech Computer Science
    4 years of experience building scalable distributed systems in Python and React.
    Docker, PostgreSQL, FastAPI.
    """
    with (
        patch("jobhunt.llm.build_profile", side_effect=Exception("LLM Timeout")),
        patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [{"name": "Tanish Jain"}])),
    ):
        res = client.post(
            "/api/resume/upload",
            json={"resume_text": raw_resume, "filename": "resume.txt"},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        prof = data["profile"]
        assert prof["name"] == "Tanish Jain"
        assert prof["experience_years"] == 4.0
        assert prof["experience_level"] == "3-5"
        assert prof["seniority"] == "mid"
        assert "Python" in prof["skills"]
        assert "React" in prof["skills"]
        assert "FastAPI" in prof["skills"]


def test_api_jobs_search_matches_skills_and_fit_reasons(client, mock_supabase_env, monkeypatch):
    """Verify /api/jobs?search= matches skills and fit reasons."""
    from jobhunt.store import Store

    mock_store = Store()
    mock_store.data = {
        "greenhouse:eng-1": {
            "title": "Software Engineer II",
            "company": "Acme Corp",
            "location": "Bengaluru",
            "score": 8.5,
            "skills": ["Rust", "Distributed Systems"],
            "fit_reasons": "Strong alignment with backend distributed systems",
        },
        "lever:front-1": {
            "title": "Web Developer",
            "company": "Beta Inc",
            "location": "Remote",
            "score": 7.0,
            "skills": ["Vue.js"],
            "fit_reasons": "Frontend focus",
        },
    }
    monkeypatch.setattr("jobhunt.web.routes.jobs.Store", lambda *args, **kwargs: mock_store)

    # Search for Rust (matches skills)
    res = client.get("/api/jobs?search=rust", headers={"Authorization": "Bearer mock-token"})
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["job_id"] == "greenhouse:eng-1"

    # Search for "backend distributed" (matches fit_reasons)
    res = client.get("/api/jobs?search=backend%20distributed", headers={"Authorization": "Bearer mock-token"})
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["jobs"]) == 1
    assert data["jobs"][0]["job_id"] == "greenhouse:eng-1"


def test_profile_settings_modal_elements_and_structure(client):
    """Verify templates have visible prof-title input and save button exclusively in final step 3."""
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    # prof-title should NOT be hidden
    assert '<input type="hidden" id="prof-title"' not in html
    assert 'id="prof-title"' in html
    assert 'Headline Professional Title' in html
    assert 'data-action="save-profile-preferences"' in html
    assert 'id="btn-profile-save"' in html
    assert 'id="btn-profile-save-step2"' not in html


def test_profile_settings_empty_exclusions_and_contacts_preserved(client, mock_supabase_env):
    """Verify POST /api/profile respects user-cleared empty exclude_keywords and preserves contact fields."""
    with patch("requests.post", return_value=MagicMock(status_code=201)):
        res = client.post(
            "/api/profile",
            json={
                "name": "Jordan Dev",
                "title": "Staff Engineer",
                "skills": ["Python", "FastAPI"],
                "target_keywords": ["Staff Engineer"],
                "exclude_keywords": [],
                "phone": "+91 98765 43210",
                "linkedin": "https://linkedin.com/in/jordandev",
                "github": "https://github.com/jordandev",
                "summary": "Specialist in distributed systems and cloud orchestration.",
            },
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        prof = data["profile"]
        assert prof["exclude_keywords"] == []
        assert prof["phone"] == "+91 98765 43210"
        assert prof["linkedin"] == "https://linkedin.com/in/jordandev"
        assert prof["github"] == "https://github.com/jordandev"
        assert prof["summary"] == "Specialist in distributed systems and cloud orchestration."


def test_profile_post_type_validation_rejects_non_strings(client, mock_supabase_env):
    """Verify POST /api/profile rejects non-string types for name, title, and resume_text with HTTP 400."""
    for field, invalid_val in [("name", 12345), ("title", ["Senior Dev"]), ("resume_text", {"text": "invalid"})]:
        res = client.post(
            "/api/profile",
            json={field: invalid_val},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 400
        data = res.get_json()
        assert data["status"] == "error"
        assert f"{field} must be a string." in data["message"]


def test_profile_post_strips_sensitive_api_keys(client, mock_supabase_env):
    """Verify POST /api/profile strips sensitive credential fields from candidate profile."""
    with patch("requests.post", return_value=MagicMock(status_code=201)):
        res = client.post(
            "/api/profile",
            json={
                "name": "Jane Safe",
                "title": "Security Architect",
                "openai_api_key": "sk-secret-key-12345",
                "custom_token": "token-xyz",
                "admin_password": "super-secret-password",
            },
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        profile = res.get_json()["profile"]
        assert "openai_api_key" not in profile
        assert "custom_token" not in profile
        assert "admin_password" not in profile


def test_profile_post_cloud_upsert_failure(client, mock_supabase_env):
    """Verify POST /api/profile returns 503 if Supabase storage upsert fails."""
    with patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=False):
        res = client.post(
            "/api/profile",
            json={"name": "Cloud Retry", "title": "DevOps"},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 503
        assert "could not be saved" in res.get_json()["message"]


def test_resume_upload_corrupt_pdf_fails(client, mock_supabase_env):
    """Verify POST /api/resume/upload returns 400 when PDF parsing raises ValueError."""
    with patch("jobhunt.llm.extract_text_from_pdf", side_effect=ValueError("Corrupt PDF stream")):
        doc_file = io.BytesIO(b"%PDF-1.4 Mock invalid pdf")
        res = client.post(
            "/api/resume/upload",
            data={"file": (doc_file, "corrupt.pdf")},
            content_type="multipart/form-data",
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 400
        assert "Corrupt PDF stream" in res.get_json()["message"]


def test_resume_upload_non_string_fields_rejected(client, mock_supabase_env):
    """Verify POST /api/resume/upload rejects non-string resume_text or filename."""
    res = client.post(
        "/api/resume/upload",
        json={"resume_text": 12345, "filename": "test.txt"},
        headers={"Authorization": "Bearer mock-token"},
    )
    assert res.status_code == 400
    assert "must be strings" in res.get_json()["message"]


def test_resume_upload_experience_level_categories(client, mock_supabase_env):
    """Verify fallback parser categorizes YoE into 0-1, 1-3, and 5+ brackets accurately."""
    yoe_cases = [
        ("0.5 years of experience", "0-1", "entry"),
        ("2 years of experience", "1-3", "mid"),
        ("7 years of experience", "5+", "senior"),
    ]
    for text, exp_level, seniority in yoe_cases:
        with (
            patch("jobhunt.llm.build_profile", side_effect=Exception("Timeout")),
            patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])),
        ):
            res = client.post(
                "/api/resume/upload",
                json={"resume_text": f"Alex Dev\nSoftware Engineer\n{text}\nPython", "filename": "resume.txt"},
                headers={"Authorization": "Bearer mock-token"},
            )
            assert res.status_code == 200
            prof = res.get_json()["profile"]
            assert prof["experience_level"] == exp_level
            assert prof["seniority"] == seniority


def test_profile_preferences_unauthenticated_or_failed_upsert(client, mock_supabase_env):
    """Verify POST /api/profile/preferences handles unauthenticated context (400) and cloud storage failure (503)."""
    # 1. Unauthenticated context
    with patch("jobhunt.web.routes.profile.get_current_user_context", return_value=(None, None)):
        res = client.post("/api/profile/preferences", json={"notice_period": "immediate"})
        assert res.status_code == 400
        assert "Authentication required" in res.get_json()["message"]

    # 2. Cloud storage failure
    with patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=False):
        res = client.post(
            "/api/profile/preferences",
            json={"notice_period": "immediate"},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 503
        assert "could not be saved" in res.get_json()["message"]


def test_profile_unauthenticated_contexts_and_reset_cloud_failure(client, mock_supabase_env):
    """Verify missing user context returns proper 400/401 and reset cloud failure returns 503."""
    with patch("jobhunt.web.routes.profile.get_current_user_context", return_value=(None, None)):
        res_post = client.post("/api/profile", json={"name": "No Auth"})
        assert res_post.status_code == 400
        assert "email required" in res_post.get_json()["message"]

        res_upload = client.post("/api/resume/upload", json={"resume_text": "text"})
        assert res_upload.status_code == 401
        assert "Authentication required" in res_upload.get_json()["message"]

    with patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=False):
        res_reset_fail = client.post("/api/profile/reset", headers={"Authorization": "Bearer mock-token"})
        assert res_reset_fail.status_code == 503
        assert "could not be saved" in res_reset_fail.get_json()["message"]


def test_profile_local_cache_write_exceptions_logged_gracefully(client, mock_supabase_env):
    """Verify IOError on local file cache writes is caught and does not fail HTTP responses."""
    with (
        patch("builtins.open", side_effect=OSError("Disk write denied")),
        patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=True),
    ):
        res_post = client.post("/api/profile", json={"name": "Resilient Dev"}, headers={"Authorization": "Bearer mock-token"})
        assert res_post.status_code == 200

        res_pref = client.post("/api/profile/preferences", json={"notice_period": "immediate"}, headers={"Authorization": "Bearer mock-token"})
        assert res_pref.status_code == 200

        res_reset = client.post("/api/profile/reset", headers={"Authorization": "Bearer mock-token"})
        assert res_reset.status_code == 200


def test_resume_upload_fallback_smart_parser_indian_context(client, mock_supabase_env):
    """Verify smart fallback parser extracts Indian tech hubs, notice period, CTC, and guarantees bidirectional aliases."""
    resume_text = """
    Priya Sharma
    Senior Backend Developer | Python, Django, AWS, PostgreSQL
    priya.sharma@example.com | +91 9876543210 | Bengaluru, India

    PROFESSIONAL SUMMARY
    Backend Engineer with 4.5 years of industry experience designing high-throughput microservices.
    Currently located in Bengaluru, open to roles in Hyderabad or Pune.
    Notice Period: 15 days notice
    Current CTC: 16.5 LPA
    Expected CTC: 24 LPA

    TECHNICAL SKILLS
    Languages & Frameworks: Python, Django, FastAPI, Go, Docker, Kubernetes, AWS, Redis, SQL
    Education: B.Tech in Computer Science, Tier-1 Institute
    """

    # Force LLM build_profile to raise an exception so the fallback parser is exercised
    with (
        patch("jobhunt.llm.build_profile", side_effect=RuntimeError("AI Timeout")),
        patch("requests.post", return_value=MagicMock(status_code=201)),
        patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])),
    ):
        res = client.post(
            "/api/resume/upload",
            json={"resume_text": resume_text},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"

        prof = data["profile"]
        parsed = data["parsed_profile"]

        # Candidate name should not be 'PROFESSIONAL SUMMARY' or 'Candidate'
        assert prof["name"] == "Priya Sharma"
        assert parsed["name"] == "Priya Sharma"

        # Title cleaned of trailing skills
        assert "Senior Backend Developer" in prof["title"]
        assert prof["title"] == prof["current_title"]
        assert parsed["title"] == parsed["current_title"]

        # Experience years
        assert prof["experience_years"] == prof["years_experience"] == 4.5
        assert parsed["experience_years"] == parsed["years_experience"] == 4.5

        # Bidirectional aliases for skills & core_skills
        assert prof["skills"] == prof["core_skills"]
        assert parsed["skills"] == parsed["core_skills"]
        assert "Python" in prof["skills"]

        # Bidirectional aliases for target_keywords & target_titles
        assert prof["target_keywords"] == prof["target_titles"]
        assert parsed["target_keywords"] == parsed["target_titles"]

        # Indian tech hubs detected
        assert "Bengaluru" in prof["preferred_locations"]
        assert "Hyderabad" in prof["preferred_locations"]
        assert "Pune" in prof["preferred_locations"]
        assert prof["location_preference"] == "specific_cities"

        # Notice period & CTC extracted
        assert prof["notice_period"] == "15_days"
        assert prof["current_ctc_lpa"] == 16.5
        assert prof["expected_ctc_lpa"] == 24.0
        assert prof["min_salary_lpa"] == 24.0


def test_api_profile_save_and_retrieve_bidirectional_aliases(client, mock_supabase_env):
    """Verify POST /api/profile normalizes aliases and notice period properly."""
    with (
        patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=True),
        patch("requests.post", return_value=MagicMock(status_code=201)),
        patch("requests.get", return_value=MagicMock(status_code=200, json=lambda: [])),
    ):
        payload = {
            "name": "Karan Verma",
            "current_title": "Full Stack Engineer",
            "years_experience": 3.0,
            "core_skills": ["React", "Node.js", "TypeScript"],
            "target_titles": ["Full Stack Developer", "Software Engineer"],
            "notice_period": "Immediate",
            "current_ctc_lpa": "12.0",
            "expected_ctc_lpa": "18.0",
        }
        res = client.post("/api/profile", json=payload, headers={"Authorization": "Bearer mock-token"})
        assert res.status_code == 200
        saved = res.get_json()["profile"]

        assert saved["title"] == saved["current_title"] == "Full Stack Engineer"
        assert saved["experience_years"] == saved["years_experience"] == 3.0
        assert saved["skills"] == saved["core_skills"] == ["React", "Node.js", "TypeScript"]
        assert saved["target_keywords"] == saved["target_titles"] == ["Full Stack Developer", "Software Engineer"]
        assert saved["notice_period"] == "immediate"
        assert saved["current_ctc_lpa"] == 12.0
        assert saved["expected_ctc_lpa"] == 18.0


def test_resume_upload_delimiter_header_and_full_smart_fallback(client, mock_supabase_env):
    """Verify fallback parser extracts name from pipe-separated header, notice period, and CTC in LPA."""
    resume_content = (
        "Ananya Deshmukh | Senior Full Stack Engineer | ananya.deshmukh@fintech.co | +91 9876543210\n"
        "Bengaluru, Karnataka, India\n\n"
        "PROFESSIONAL SUMMARY\n"
        "Senior Full Stack Engineer with 5.5 years of industry experience building low-latency payment rails.\n"
        "Current CTC: 24 LPA | Expected CTC: 36 LPA\n"
        "Notice Period: Serving notice period, LWD 30th Nov (immediate joiner)\n\n"
        "TECHNICAL SKILLS\n"
        "Python, TypeScript, React, Next.js, Node.js, PostgreSQL, Redis, Docker, AWS, Kafka\n\n"
        "EDUCATION\n"
        "B.Tech Computer Science, NIT Surathkal (2020), 8.9 CGPA\n"
    )

    with (
        patch("jobhunt.llm.build_profile", side_effect=Exception("LLM offline in test")),
        patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value={}),
    ):
        res = client.post(
            "/api/resume/upload",
            json={"resume_text": resume_content, "filename": "ananya_resume.txt"},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"

        prof = data["profile"]
        assert prof["name"] == "Ananya Deshmukh"
        assert "Senior Full Stack Engineer" in prof["title"]
        assert prof["experience_years"] == 5.5
        assert "Python" in prof["skills"]
        assert "PostgreSQL" in prof["skills"]
        assert "Bengaluru" in prof["preferred_locations"]
        assert prof["current_ctc_lpa"] == 24.0
        assert prof["expected_ctc_lpa"] == 36.0
        assert prof["notice_period"] == "immediate"


def test_get_profile_returns_blank_stub_when_supabase_row_missing(client, mock_supabase_env):
    """Privacy invariant: configured Supabase with no DB row returns an uncompleted blank email-only stub."""
    with (
        patch("jobhunt.auth.verify_token", return_value={"email": "user@test.com"}),
        patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value=None),
    ):
        res = client.get("/api/profile", headers={"Authorization": "Bearer mock-token"})
        assert res.status_code == 200
        data = res.get_json()
        prof = data["profile"]
        assert prof["email"] == "user@test.com"
        assert prof["name"] == ""
        assert prof["skills"] == []
        assert prof["target_keywords"] == []
        assert prof["onboarding_completed"] is False


def test_blank_profile_matches_reset_output_and_multi_keeps_empty_name(client, mock_supabase_env, capsys):
    """Signup stub and reset output must share one identical blank shape; batch processing never infers name."""
    from jobhunt import digest, multi
    from jobhunt.memory import create_blank_profile

    stub = create_blank_profile("user@test.com")
    with (
        patch("jobhunt.auth.verify_token", return_value={"email": "user@test.com"}),
        patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=True),
    ):
        res = client.post("/api/profile/reset", headers={"Authorization": "Bearer mock-token"})
        assert res.status_code == 200
        reset_prof = res.get_json()["profile"]
        assert reset_prof == stub

    # Also verify multi.py does not infer a name from email when user profile has blank name
    captured_profiles = []
    mock_users = [
        {
            "email": "alex.mercer@example.com",
            "name": "",
            "skills": ["Python"],
            "target_keywords": ["Backend"],
            "profile_json": {},
        }
    ]
    mock_resp = MagicMock(status_code=200, json=lambda: mock_users)
    orig_build = digest.build

    def spy_build(*args, **kwargs):
        captured_profiles.append(dict(kwargs.get("profile") or {}))
        return orig_build(*args, **kwargs)

    with (
        patch("requests.get", return_value=mock_resp),
        patch("jobhunt.multi.prefilter", return_value=[]),
        patch("jobhunt.digest.build", side_effect=spy_build),
        patch("jobhunt.mailer.send", return_value=True),
        patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", return_value=True),
        patch("jobhunt.memory.SupabaseMemory.record_pipeline_run", return_value=True),
        patch("jobhunt.memory.SupabaseMemory.prune_pipeline_runs", return_value=0),
    ):
        res_multi = multi.run_multi_user_pipeline(mock=True, scorer="keyword", force_send=True)

    captured_stdout = capsys.readouterr().out
    assert res_multi["status"] == "success"
    assert "Processing Candidate: alex.mercer@example.com" in captured_stdout
    assert "Alex" not in captured_stdout
    assert len(captured_profiles) == 1
    assert captured_profiles[0]["name"] == ""


def test_profile_preferences_strips_credentials_and_clamps_bounds(client, mock_supabase_env):
    """POST /api/profile/preferences strips credential keys, clamps bounds, and preserves email & onboarding state."""
    captured = {}

    def fake_upsert(email, payload, token=None):
        captured["email"] = email
        captured["payload"] = dict(payload)
        return True

    with (
        patch("jobhunt.auth.verify_token", return_value={"email": "user@test.com"}),
        patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value=None),
        patch("jobhunt.memory.SupabaseMemory.upsert_user_profile", side_effect=fake_upsert),
    ):
        res = client.post(
            "/api/profile/preferences",
            json={
                "email": "attacker@evil.com",
                "api_key": "sk-secret",
                "smtp_password": "pw",
                "custom_token": "tok",
                "client_secret": "sec",
                "current_ctc_lpa": -10,
                "expected_ctc_lpa": 50000,
                "min_salary_lpa": float("nan"),
                "job_types": [f"type-{i}" for i in range(40)],
            },
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        prefs = res.get_json()["preferences"]
        assert prefs["current_ctc_lpa"] == 0.0
        assert prefs["expected_ctc_lpa"] == 1000.0
        assert prefs["min_salary_lpa"] == 1000.0
        assert len(prefs["job_types"]) == 30

        saved = captured["payload"]
        assert saved["email"] == "user@test.com"
        assert saved["onboarding_completed"] is False
        for forbidden in ("api_key", "smtp_password", "custom_token", "client_secret"):
            assert forbidden not in saved


def test_resume_upload_does_not_leak_local_profile_when_supabase_configured(client, mock_supabase_env):
    """Privacy invariant: configured Supabase with no DB row must never fall back to local profile.json during upload."""
    with (
        patch("jobhunt.auth.verify_token", return_value={"email": "newuser@test.com"}),
        patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value=None),
        patch(
            "jobhunt.web.routes.profile.get_user_profile",
            return_value={"name": "Leaked Local User", "title": "Staff Eng", "skills": ["Rust"]},
        ) as mock_local_fallback,
        patch("jobhunt.llm.resolve", side_effect=RuntimeError("offline")),
    ):
        res = client.post(
            "/api/resume/upload",
            json={"resume_text": "Python Developer with 2 years experience.", "filename": "cv.txt"},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        mock_local_fallback.assert_not_called()
        prof = res.get_json()["profile"]
        assert prof["email"] == "newuser@test.com"
        assert prof["name"] == ""
        assert "Leaked Local User" not in prof.values()
        assert "Rust" not in prof.get("skills", [])







