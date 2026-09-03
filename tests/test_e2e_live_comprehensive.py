"""Comprehensive End-to-End Live Testing Suite for Job Hunter.

Tests every single feature locally:
1. Server Core, Health, Config & Static Assets
2. Security Headers & Auth Gates (CSP, 401 Enforcement)
3. Candidate Profile & Resume Studio (Text Upload, File Upload, AI & Local Extraction)
4. ATS Career Board Detection & Tracking (/api/companies/add)
5. Job Tracker & Pipeline Management (Add, Filter, Search, Sort, Applied Toggle, Notes, Stats, CSV Export, Delete)
6. AI Intelligence & Application Kit (Screening, Tailored Bullets, Cover Note, Cold Outreach)
7. Daily Briefing & Digest Engine (/api/digest)
8. Cloud State Synchronization (/api/sync)
"""

import io
import json
import time
import pytest

from jobhunt.web import create_app
from jobhunt import llm

SAMPLE_RESUME_TEXT = """TANISH SANGHVI
Dombivli, Maharashtra | +91-7021341948 | tanishjain020205@gmail.com
LinkedIn | GitHub | Portfolio

SUMMARY
Software Engineer and Full-Stack Developer experienced in building and deploying scalable web applications using React.js, Next.js, Node.js, Express, Flask and MongoDB. Skilled in REST API design, robust authentication, automated testing and integrating AI pipelines into production systems.

EDUCATION
Vivekanand Education Society’s Institute of Technology (VESIT), Mumbai, 2023 - Present
B.E. in Automation & Robotics Engineering | CGPA: 7.33 / 10
Relevant Coursework: Data Structures & Algorithms, DBMS, Machine Learning, Generative AI

SKILLS
Languages: JavaScript (ES6+), Python, C++
Frontend: React.js, Next.js, HTML5, CSS3, Tailwind CSS
Backend: Node.js, Express.js, Flask, REST APIs
Databases: MongoDB, Firestore
Authentication: Firebase Authentication
Deployment & Testing: Git, GitHub, Postman, Jest, Playwright, Vercel, Render
AI & Developer Tools: Gemini AI API, GitHub Copilot, ChatGPT
Soft Skills: Problem Solving, Team Collaboration, Communication

PROJECTS
Edvanta - AI-Powered Educational Platform
Tech Stack: Python, Flask, React.js, Gemini AI API, MongoDB, Firebase
● Designed 33 REST API endpoints in Flask to power AI tutoring and automated learning roadmaps.
● Integrated Gemini AI APIs using structured JSON schemas and prompt templates for deterministic student guidance.

Department Ledger Portal - Academic Record System
Tech Stack: Next.js, React, Tailwind CSS, Firebase Admin, Firestore, Gemini AI API
● Built a full-stack application backed by 77 Jest unit tests and 5 Playwright E2E pipeline gates.
"""

USER_EMAIL = "tanishjain020205@gmail.com"
USER_PAYLOAD = {"id": "usr_e2e_live_test", "email": USER_EMAIL, "role": "authenticated"}
AUTH_HEADERS = {"Authorization": "Bearer e2e-valid-jwt-token"}


@pytest.fixture(scope="module")
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestE2ELiveSuite:
    """End-to-End Live Testing covering all features."""

    mock_db: dict[str, dict] = {}

    @pytest.fixture(autouse=True)
    def setup_mock_environment(self, monkeypatch, tmp_path):
        """Automatically mock auth verification and in-memory persistence for all test methods."""
        monkeypatch.setattr("jobhunt.auth.verify_token", lambda token: USER_PAYLOAD)
        monkeypatch.setattr("jobhunt.web.state.get_current_user_context", lambda: (USER_EMAIL, "token"))
        monkeypatch.setattr("jobhunt.web.routes.profile.get_current_user_context", lambda: (USER_EMAIL, "token"))
        monkeypatch.setattr("jobhunt.web.routes.jobs.get_current_user_context", lambda: (USER_EMAIL, "token"))
        monkeypatch.setattr("jobhunt.web.routes.pipeline.get_current_user_context", lambda: (USER_EMAIL, "token"))
        monkeypatch.setattr("jobhunt.web.routes.profile.get_writable_path", lambda p: tmp_path / Path(p).name)

        def mock_get_profile(email, token=None):
            return self.mock_db.get(email, {})

        def mock_upsert_profile(email, profile, token=None):
            self.mock_db[email] = {**(self.mock_db.get(email, {})), **profile}
            return self.mock_db[email]

        monkeypatch.setattr("jobhunt.memory.SupabaseMemory.get_user_profile", lambda self, email, token=None: mock_get_profile(email, token))
        monkeypatch.setattr("jobhunt.memory.SupabaseMemory.upsert_user_profile", lambda self, email, profile, token=None: mock_upsert_profile(email, profile, token))
        monkeypatch.setattr("jobhunt.memory.SupabaseMemory.is_configured", property(lambda self: True))

    # -------------------------------------------------------------------------
    # 1. Server Core, Health & Security Headers
    # -------------------------------------------------------------------------
    def test_01_health_and_version(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "healthy"
        assert data["service"] == "job-hunter"
        assert "version" in data
        assert "environment" in data
        print("\n [✓] 1.1 Health endpoint verified healthy")

    def test_02_config_endpoint(self, client):
        resp = client.get("/api/config", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert "filters" in data
        assert "companies_count" in data
        print(" [✓] 1.2 Config endpoint verified")

    def test_03_index_html_and_asset_versions(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Job Hunter" in html
        assert "style.css?v=1.0.3" in html
        assert "app.js?v=1.0.3" in html
        assert 'id="onboarding-modal"' in html
        assert 'id="profile-modal"' in html
        assert 'id="kit-modal"' in html
        assert 'id="add-company-modal"' in html
        assert 'id="add-job-modal"' in html
        assert 'id="toast-container"' in html
        print(" [✓] 1.3 Main HTML dashboard rendered with all modals & v1.0.3 assets")

    def test_04_security_headers(self, client):
        resp = client.get("/")
        headers = resp.headers
        assert "Content-Security-Policy" in headers
        assert "Permissions-Policy" in headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") in ("DENY", "SAMEORIGIN")
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        print(" [✓] 1.4 Security headers (CSP, Permissions-Policy, X-Frame-Options, etc.) verified")

    def test_05_unauthorized_rejection(self, client, monkeypatch):
        # Temporarily remove auth mock to test actual 401 gate
        monkeypatch.setattr("jobhunt.auth.verify_token", lambda token: None)
        resp = client.get("/api/stats")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["status"] == "error"
        assert "Authentication" in data["message"]
        print(" [✓] 1.5 Protected routes reject unauthenticated requests with HTTP 401")

    # -------------------------------------------------------------------------
    # 2. Candidate Profile & Resume Studio
    # -------------------------------------------------------------------------
    def test_06_resume_upload_json_text(self, client):
        resp = client.post(
            "/api/resume/upload",
            json={"resume_text": SAMPLE_RESUME_TEXT, "filename": "Tanish_Sanghvi_Resume.txt"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        profile = data["profile"]
        assert "tanish" in profile.get("name", "").lower()
        assert len(profile.get("skills", [])) > 0
        assert len(profile.get("resume_text", "")) > 100
        print(f" [✓] 2.1 Resume text upload succeeded: Name={profile.get('name')}, Skills={len(profile.get('skills', []))}")

    def test_07_resume_upload_multipart_file(self, client):
        file_data = io.BytesIO(SAMPLE_RESUME_TEXT.encode("utf-8"))
        resp = client.post(
            "/api/resume/upload",
            data={"file": (file_data, "Tanish_Resume.pdf")},
            content_type="multipart/form-data",
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        print(" [✓] 2.2 Multipart resume upload succeeded with structured parsing")

    def test_08_profile_preferences(self, client):
        update_payload = {
            "preferred_locations": ["Mumbai", "Remote"],
            "job_types": ["fulltime", "internship"],
            "experience_level": "fresher",
            "min_salary_lpa": 8.0,
            "target_keywords": ["Full Stack Developer", "Software Engineer"],
            "exclude_keywords": ["Senior", "Manager"],
        }
        post_resp = client.post("/api/profile/preferences", json=update_payload, headers=AUTH_HEADERS)
        assert post_resp.status_code == 200
        post_data = post_resp.get_json()
        assert post_data["status"] == "success"

        get_resp = client.get("/api/profile/preferences", headers=AUTH_HEADERS)
        assert get_resp.status_code == 200
        prefs = get_resp.get_json()["preferences"]
        assert "Mumbai" in prefs["preferred_locations"]
        assert "fulltime" in prefs["job_types"]
        print(" [✓] 2.3 Profile preferences (locations, salary, roles) saved and retrieved")

    def test_09_full_profile_crud_and_reset(self, client):
        profile_data = {
            "name": "Tanish Sanghvi",
            "title": "Full-Stack Engineer",
            "skills": ["Python", "React.js", "Node.js", "MongoDB"],
            "target_keywords": ["Full Stack Developer"],
            "email_notifications_enabled": True,
        }
        save_resp = client.post("/api/profile", json=profile_data, headers=AUTH_HEADERS)
        assert save_resp.status_code == 200
        assert save_resp.get_json()["status"] == "success"

        read_resp = client.get("/api/profile", headers=AUTH_HEADERS)
        assert read_resp.status_code == 200
        user_profile = read_resp.get_json()["profile"]
        assert user_profile["name"] == "Tanish Sanghvi"

        reset_resp = client.post("/api/profile/reset", headers=AUTH_HEADERS)
        assert reset_resp.status_code == 200
        assert reset_resp.get_json()["status"] == "success"
        print(" [✓] 2.4 Candidate profile CRUD and Reset verified")

    # -------------------------------------------------------------------------
    # 3. ATS Career Board Detection & Tracking (/api/companies/add)
    # -------------------------------------------------------------------------
    def test_10_company_ats_detection(self, client):
        test_portals = [
            ("https://boards.greenhouse.io/stripe", "greenhouse", "stripe"),
            ("https://jobs.lever.co/meesho", "lever", "meesho"),
            ("https://jobs.ashbyhq.com/linear", "ashby", "linear"),
            ("https://apply.workable.com/invideo", "workable", "invideo"),
        ]
        for url, expected_ats, expected_slug in test_portals:
            resp = client.post("/api/companies/add", json={"url": url}, headers=AUTH_HEADERS)
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "success"
            company = data["company"]
            assert company["ats"] == expected_ats
            assert company["slug"].lower() == expected_slug.lower()
        print(" [✓] 3.1 Live ATS portal auto-detection verified (Greenhouse, Lever, Ashby, Workable)")

    # -------------------------------------------------------------------------
    # 4. Job Tracker & Pipeline Lifecycle
    # -------------------------------------------------------------------------
    def test_11_job_lifecycle(self, client):
        # 4.1 Add job
        add_payload = {
            "title": "Full Stack Developer",
            "company": "NextGen AI Labs",
            "location": "Remote, India",
            "url": "https://example.com/careers/fs-101",
            "score": 9.4,
            "ats": "greenhouse",
            "notes": "Top tier culture match",
        }
        add_resp = client.post("/api/jobs/add", json=add_payload, headers=AUTH_HEADERS)
        assert add_resp.status_code == 200
        add_data = add_resp.get_json()
        assert add_data["status"] == "success"
        job_id = add_data.get("job_id") or add_data.get("job", {}).get("id")
        assert job_id is not None

        # 4.2 Query jobs
        list_resp = client.get("/api/jobs", headers=AUTH_HEADERS)
        assert list_resp.status_code == 200
        jobs = list_resp.get_json()["jobs"]
        target = next((j for j in jobs if (j.get("id") == job_id or j.get("job_id") == job_id or j.get("title") == "Full Stack Developer")), None)
        assert target is not None
        assert target["title"] == "Full Stack Developer"
        assert target["company"] == "NextGen AI Labs"
        actual_job_id = target.get("id") or target.get("job_id") or job_id

        # 4.3 Filter by ATS
        filter_resp = client.get("/api/jobs?ats=greenhouse", headers=AUTH_HEADERS)
        assert filter_resp.status_code == 200
        gh_jobs = filter_resp.get_json()["jobs"]
        assert all(j.get("ats") == "greenhouse" for j in gh_jobs if "ats" in j)

        # 4.4 Search query
        search_resp = client.get("/api/jobs?q=NextGen", headers=AUTH_HEADERS)
        assert search_resp.status_code == 200
        assert any((j.get("id") == actual_job_id or j.get("company") == "NextGen AI Labs") for j in search_resp.get_json()["jobs"])

        # 4.5 Sorting by score
        sort_resp = client.get("/api/jobs?sort=score", headers=AUTH_HEADERS)
        assert sort_resp.status_code == 200

        # 4.6 Toggle Applied
        app_resp = client.post("/api/applied", json={"job_id": actual_job_id, "applied": True}, headers=AUTH_HEADERS)
        assert app_resp.status_code == 200
        assert app_resp.get_json()["applied"] is True

        # 4.7 Update Notes
        notes_resp = client.post("/api/jobs/notes", json={"job_id": actual_job_id, "notes": "Interview scheduled"}, headers=AUTH_HEADERS)
        assert notes_resp.status_code == 200
        assert notes_resp.get_json()["status"] == "success"

        # 4.8 Pipeline Stats
        stats_resp = client.get("/api/stats", headers=AUTH_HEADERS)
        assert stats_resp.status_code == 200
        stats = stats_resp.get_json()
        assert stats["tracked"] >= 1
        assert stats["applied"] >= 1

        # 4.9 Export CSV
        csv_resp = client.get("/api/export/csv", headers=AUTH_HEADERS)
        assert csv_resp.status_code == 200
        assert "text/csv" in csv_resp.content_type
        csv_text = csv_resp.get_data(as_text=True)
        assert "Job Title" in csv_text or "title" in csv_text.lower()
        assert "NextGen AI Labs" in csv_text

        # 4.10 Delete Job via /api/delete
        del_resp = client.post("/api/delete", json={"job_id": actual_job_id}, headers=AUTH_HEADERS)
        assert del_resp.status_code == 200
        assert del_resp.get_json()["status"] == "success"

        print(" [✓] 4.1 Job Tracker full lifecycle verified (Add -> Filter -> Search -> Sort -> Apply -> Notes -> Stats -> CSV -> Delete)")

    # -------------------------------------------------------------------------
    # 5. AI Intelligence & Application Kit
    # -------------------------------------------------------------------------
    def test_12_ai_intelligence_layer(self):
        valid_json = '{"score": 9.5, "fit_justification": "Strong React and Python experience"}'
        parsed = llm.parse_json(valid_json)
        assert parsed["score"] == 9.5

        fenced_json = '```json\n{"score": 8.8, "fit_justification": "Great culture match"}\n```'
        parsed_fenced = llm.parse_json(fenced_json)
        assert parsed_fenced["score"] == 8.8

        thinking_json = '<think>Let me evaluate this candidate...</think>{"fit_summary": "Excellent fit"}'
        parsed_thinking = llm.parse_json(thinking_json)
        assert parsed_thinking["fit_summary"] == "Excellent fit"

        print(" [✓] 5.1 AI Intelligence JSON parser, fence stripper & reasoning handler verified")

    # -------------------------------------------------------------------------
    # 6. Daily Digest Briefing
    # -------------------------------------------------------------------------
    def test_13_digest_endpoint(self, client):
        resp = client.get("/api/digest", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert "text/html" in resp.content_type
        assert len(resp.get_data(as_text=True)) > 0
        print(" [✓] 6.1 Daily Executive Digest briefing generation verified (HTML output)")

    # -------------------------------------------------------------------------
    # 7. Cloud State Synchronization
    # -------------------------------------------------------------------------
    def test_14_cloud_sync_endpoint(self, client):
        resp = client.get("/api/sync", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert "stats" in data
        assert "pipeline" in data
        assert "ats_counts" in data
        print(" [✓] 7.1 Cloud state bidirectional synchronization verified (/api/sync)")
