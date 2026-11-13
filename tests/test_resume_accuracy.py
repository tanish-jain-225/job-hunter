"""Tests for resume parsing accuracy, grounded timeline YoE, canonical skill normalization,
and headline synthesis.
"""

from __future__ import annotations

from unittest import mock

import pytest

from app import app
from jobhunt.llm_utils import (
    calculate_timeline_yoe,
    normalize_technical_skills,
    parse_month_year,
    sanitize_candidate_name,
    synthesize_headline_and_targets,
)


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


def test_parse_month_year_formats():
    """Verify parse_month_year correctly identifies months, years, and ongoing intervals."""
    assert parse_month_year("Aug 2024") == (2024, 8)
    assert parse_month_year("August 2024") == (2024, 8)
    assert parse_month_year("08/2024") == (2024, 8)
    assert parse_month_year("2024-08") == (2024, 8)
    assert parse_month_year("2024") == (2024, 6)
    assert parse_month_year("Present") == (2026, 11)
    assert parse_month_year("Current") == (2026, 11)
    assert parse_month_year("") is None
    assert parse_month_year(None) is None


def test_calculate_timeline_yoe_merges_overlapping_stints():
    """Verify overlapping full-time employment intervals are merged without double-counting."""
    work_history = [
        {"role": "Software Engineer", "type": "full-time", "start": "Jan 2022", "end": "Dec 2023"},
        {"role": "Backend Engineer", "type": "full-time", "start": "Jun 2023", "end": "Dec 2024"},
    ]
    # Jan 2022 to Dec 2024 is 36 months = 3.0 years
    yoe = calculate_timeline_yoe(work_history)
    assert yoe == 3.0


def test_calculate_timeline_yoe_excludes_internships():
    """Verify student internships, apprenticeships, and trainee roles do not count toward full-time YoE."""
    work_history = [
        {"role": "Software Engineering Intern", "type": "internship", "start": "Jan 2023", "end": "Jun 2023"},
        {"role": "Frontend Trainee", "type": "trainee", "start": "Jul 2023", "end": "Dec 2023"},
        {"role": "Software Engineer", "type": "full-time", "start": "Jan 2024", "end": "Dec 2024"},
    ]
    yoe = calculate_timeline_yoe(work_history)
    # Only 2024 full-time stint counts: 12 months = 1.0 years
    assert yoe == 1.0


def test_calculate_timeline_yoe_clamps_freshers_and_students():
    """Verify students and freshers graduating in 2025/2026/2027 are clamped to 0.0 YoE."""
    resume_text = """
    Tanish Sanghvi
    Final-year Automation and Robotics Engineering student (Class of 2027)
    VESIT, Mumbai (Aug 2023 - May 2027)
    Built 4 years of college projects in Python and React.
    """
    yoe = calculate_timeline_yoe(None, graduation_year=2027, resume_text=resume_text)
    assert yoe == 0.0


def test_normalize_technical_skills_canonicalizes_and_strips_buzzwords():
    """Verify skill normalization maps synonyms to industry standard and strips soft skills."""
    raw_skills = [
        "React.js",
        "reactjs",
        "Postgres",
        "postgresql",
        "Python3",
        "Golang",
        "Problem Solving",
        "Communication",
        "Teamwork",
        "Docker",
        "AWS",
        "k8s",
        "Kubernetes",
        "CI/CD pipelines",
        "FastAPI",
    ]
    normalized = normalize_technical_skills(raw_skills)

    # Soft skills must be stripped
    assert "Problem Solving" not in normalized
    assert "Communication" not in normalized
    assert "Teamwork" not in normalized

    # Canonical mapping
    assert "React" in normalized
    assert normalized.count("React") == 1
    assert "PostgreSQL" in normalized
    assert normalized.count("PostgreSQL") == 1
    assert "Python" in normalized
    assert "Go" in normalized
    assert "Kubernetes" in normalized
    assert normalized.count("Kubernetes") == 1
    assert "Docker" in normalized
    assert "AWS" in normalized
    assert "FastAPI" in normalized


def test_sanitize_candidate_name_strips_headers_and_noise():
    """Verify name sanitization extracts real candidate names and rejects document titles and contact info."""
    lines = [
        "RESUME",
        "Tanish Sanghvi | Software Engineer | tanish@example.com | +91 7021341948",
        "Dombivli, Maharashtra, India",
        "Summary of Qualifications",
    ]
    name = sanitize_candidate_name(None, text_lines=lines)
    assert name == "Tanish Sanghvi"

    # Direct dirty raw names
    assert sanitize_candidate_name("Resume - John Doe") == "John Doe"
    assert sanitize_candidate_name("Candidate Name: Jane Doe") == "Jane Doe"
    assert sanitize_candidate_name("Curriculum Vitae") == ""
    assert sanitize_candidate_name("Software Engineer") == ""


def test_synthesize_headline_and_targets_replaces_student_role():
    """Verify headline synthesis converts non-professional titles (e.g. Student, Fresher) to stack-derived titles."""
    skills = ["Python", "FastAPI", "React", "Next.js", "PostgreSQL", "Docker"]
    title, targets = synthesize_headline_and_targets("Final-year Student", skills, yoe=0.0)

    assert title.lower() not in {"student", "fresher", "intern", "candidate"}
    assert title in ("Full Stack Developer", "Backend Engineer", "Software Engineer")
    assert len(targets) >= 3
    assert all(t.lower() not in {"student", "fresher", "intern"} for t in targets)


def test_synthesize_headline_for_backend_engineer():
    """Verify backend-focused skills yield Backend Engineer headline."""
    skills = ["Python", "FastAPI", "Django", "PostgreSQL", "Redis", "Docker"]
    title, targets = synthesize_headline_and_targets("", skills, yoe=2.0)

    assert title == "Backend Engineer"
    assert "Backend Engineer" in targets
    assert "Python Developer" in targets


def test_end_to_end_student_resume_upload_clamping(client, mock_supabase_env):
    """End-to-end integration test verifying a student resume upload produces 0.0 YoE, fresher level, and immediate notice."""
    student_resume = """
    Tanish Sanghvi | Software Engineer | tanishjain@example.com | +91 7021341948
    Dombivli, Maharashtra, India

    PROFESSIONAL SUMMARY
    Final-year Automation and Robotics Engineering student (Class of 2027) with hands-on experience building full-stack web applications.

    TECHNICAL SKILLS
    Languages: Python, JavaScript, TypeScript, SQL
    Frameworks: FastAPI, React, Next.js, Node.js
    Databases: PostgreSQL, Redis, Supabase
    Developer Tools: Docker, Git, GitHub Actions

    EDUCATION
    VESIT, Mumbai - B.E. Automation and Robotics Engineering (Aug 2023 - May 2027)
    """

    with (
        mock.patch("jobhunt.llm.build_profile", side_effect=Exception("LLM offline for test")),
        mock.patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value={}),
    ):
        res = client.post(
            "/api/resume/upload",
            json={"resume_text": student_resume, "filename": "tanish_resume.txt"},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"

        prof = data["profile"]
        assert prof["name"] == "Tanish Sanghvi"
        assert prof["experience_years"] == 0.0
        assert prof["years_experience"] == 0.0
        assert prof["experience_level"] == "fresher"
        assert prof["seniority"] == "entry"
        assert prof["notice_period"] == "immediate"
        assert prof["title"] not in {"Student", "Fresher", "Candidate"}
        assert "Python" in prof["skills"]
        assert "FastAPI" in prof["skills"]
        assert "React" in prof["skills"]
        assert "PostgreSQL" in prof["skills"]


def test_synthesize_headline_and_targets_product_manager():
    """Verify Product Management background dynamically derives Product Manager targets and avoids tech role leakage."""
    skills = ["PRDs", "Product Roadmapping", "User Stories", "A/B Testing", "Jira", "Mixpanel"]
    title, targets = synthesize_headline_and_targets("Associate Product Manager", skills, yoe=1.5)

    assert title == "Associate Product Manager"
    assert "Product Manager" in targets
    assert "Associate Product Manager" in targets
    assert "Product Owner" in targets
    # Strict universality verification: never pollute product search with software engineering roles
    assert "Software Engineer" not in targets
    assert "Backend Developer" not in targets


def test_synthesize_headline_and_targets_product_designer():
    """Verify UI/UX & Design background dynamically synthesizes Product Designer targets."""
    skills = ["Figma", "Sketch", "Wireframing", "Prototyping", "User Research", "Design Systems"]
    title, targets = synthesize_headline_and_targets("", skills, yoe=3.0)

    assert title == "Product Designer"
    assert "Product Designer" in targets
    assert "UI/UX Designer" in targets
    assert "UX Designer" in targets
    assert "Software Engineer" not in targets


def test_synthesize_headline_and_targets_data_analyst():
    """Verify Data & BI background synthesizes Data Analyst targets."""
    skills = ["SQL", "Tableau", "Power BI", "Data Analysis", "Snowflake"]
    title, targets = synthesize_headline_and_targets("", skills, yoe=2.0)

    assert title == "Data Analyst"
    assert "Data Analyst" in targets
    assert "Business Intelligence Analyst" in targets
    assert "Analytics Engineer" in targets
    assert "Software Engineer" not in targets


def test_synthesize_headline_and_targets_marketing_and_sales():
    """Verify Growth Marketing and Sales background synthesize relevant commercial roles."""
    mkt_skills = ["SEO", "SEM", "Google Ads", "Google Analytics", "HubSpot", "Content Strategy"]
    mkt_title, mkt_targets = synthesize_headline_and_targets("", mkt_skills, yoe=2.0)
    assert mkt_title == "Growth Marketer"
    assert "Growth Marketer" in mkt_targets
    assert "Digital Marketing Specialist" in mkt_targets
    assert "Software Engineer" not in mkt_targets

    sales_skills = ["Salesforce", "B2B Sales", "Lead Generation", "Pipeline Management", "Cold Outreach"]
    sales_title, sales_targets = synthesize_headline_and_targets("Account Executive", sales_skills, yoe=4.0)
    assert sales_title == "Account Executive"
    assert "Account Executive" in sales_targets
    assert "Business Development Representative" in sales_targets
    assert "Software Engineer" not in sales_targets


def test_synthesize_headline_and_targets_finance_and_accounting():
    """Verify Finance and Accounting background synthesizes Financial Analyst targets."""
    fin_skills = ["Financial Modeling", "Valuation", "QuickBooks", "Auditing", "Budgeting", "Excel"]
    fin_title, fin_targets = synthesize_headline_and_targets("", fin_skills, yoe=3.0)
    assert fin_title == "Financial Analyst"
    assert "Financial Analyst" in fin_targets
    assert "Accountant" in fin_targets
    assert "Software Engineer" not in fin_targets


def test_end_to_end_product_manager_resume_upload(client, mock_supabase_env):
    """End-to-end integration test verifying a Product Manager resume is parsed into product roles, not tech roles."""
    pm_resume = """
    Priya Sharma | Product Manager | priya.sharma@example.com | +91 9876543210
    Bengaluru, Karnataka, India

    PROFESSIONAL SUMMARY
    Product Manager with 3 years of experience owning product roadmap, PRDs, and user research.
    Led cross-functional feature prioritization and A/B testing increasing conversion by 28%.

    CORE COMPETENCIES
    Product Management, PRDs, Product Roadmapping, User Stories, A/B Testing, Jira, Amplitude

    EXPERIENCE
    Product Manager | FinTech Unicorn, Bengaluru (Jan 2023 - Present)
    - Authored 25+ detailed PRDs and user stories.
    - Designed and executed 15+ A/B tests to optimize onboarding funnel.

    EDUCATION
    MBA, Indian Institute of Management (2022)
    """

    with (
        mock.patch("jobhunt.llm.build_profile", side_effect=Exception("LLM offline for test")),
        mock.patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value={}),
    ):
        res = client.post(
            "/api/resume/upload",
            json={"resume_text": pm_resume, "filename": "priya_pm_resume.txt"},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"

        prof = data["profile"]
        assert prof["name"] == "Priya Sharma"
        assert "Product Manager" in prof["title"]
        assert any("Product" in t for t in prof["target_keywords"])
        assert "Software Engineer" not in prof["target_keywords"]
        assert "Product Management" in prof["skills"] or "PRDs" in prof["skills"]
        assert "A/B Testing" in prof["skills"]

