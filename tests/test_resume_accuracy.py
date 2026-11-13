"""Tests for resume parsing accuracy, grounded timeline YoE, canonical skill normalization,
and headline synthesis.
"""

from __future__ import annotations

from unittest import mock

import pytest

from app import app
from jobhunt.llm_utils import (
    calculate_timeline_yoe,
    clean_pdf_extracted_text,
    detect_preferred_locations_smart,
    extract_text_from_pdf,
    normalize_technical_skills,
    parse_contact_smart,
    parse_education_smart,
    parse_month_year,
    parse_projects_smart,
    parse_summary_smart,
    sanitize_candidate_name,
    synthesize_headline_and_targets,
)
from jobhunt.web.routes.profile import _extract_skills_from_text


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


def test_parse_education_smart_accuracy():
    """Verify smart education parser extracts degree, long university names, end-of-interval grad year, and CGPA."""
    edu_text = """
    EDUCATION
    Vivekanand Education Society’s Institute of Technology, Mumbai 2023 – 2027 (Expected)
    B.E. in Automation and Robotics Engineering
    CGPA: 7.43/10.0
    """
    edu, yr = parse_education_smart(edu_text)
    assert yr == 2027
    assert "Vivekanand Education Society" in edu
    assert "Automation and Robotics Engineering" in edu
    assert "CGPA: 7.43/10.0" in edu
    # Ensure substring 'mba' from 'Mumbai' did not match degree
    assert not any(seg.strip().lower() == "mba" for seg in edu.split(","))


def test_parse_projects_smart_accuracy():
    """Verify smart projects parser extracts project titles, tech stack headers, and deliverable descriptions."""
    proj_text = """
    PROJECTS
    Department Ledger Portal – Academic Records System Live Demo | GitHub
    Next.js, React, Firebase Firestore, Jest, Playwright
    • Built an academic records portal with separate student, faculty and administrator workflows.
    • Automated grade tracking reducing compilation turnaround by 40%.

    Edvanta – AI-Assisted Learning Platform Live Demo | GitHub
    Python, Flask, React, MongoDB, Firebase, Pydantic
    • Designed and deployed 33 modular REST endpoints supporting assessment workflows.
    • Integrated schema validation with Pydantic for high payload safety.
    """
    projects = parse_projects_smart(proj_text)
    assert len(projects) == 2
    assert "Department Ledger Portal" in projects[0]
    assert "Edvanta" in projects[1]
    assert "academic records portal" in projects[0]
    assert "modular REST endpoints" in projects[1]


def test_parse_summary_smart_accuracy():
    """Verify smart executive summary parser extracts career overview and excludes bullet points."""
    text = """
    TANISH SANGHVI
    Professional Summary
    Final-year Automation and Robotics Engineering student with hands-on project experience building full-stack applications.
    Worked with relational and NoSQL databases, authentication, schema validation and automated testing pipelines.

    Technical Skills
    Python, SQL, JavaScript
    """
    summary = parse_summary_smart(text)
    assert "Automation and Robotics Engineering" in summary
    assert "full-stack applications" in summary


def test_parse_contact_smart_accuracy():
    """Verify smart contact parser extracts phone numbers, emails, and LinkedIn / GitHub profile links."""
    text = """
    TANISH SANGHVI
    Dombivli, Maharashtra, India | +91-7021341948 | tanishjain020205@gmail.com
    Links & Profiles:
    - https://www.linkedin.com/in/tanish-jain-tj02022005
    - https://github.com/tanish-jain-225
    - https://department-ledger-portal.vercel.app
    """
    contacts = parse_contact_smart(text)
    assert contacts["phone"] == "+91-7021341948"
    assert contacts["email"] == "tanishjain020205@gmail.com"
    assert "tanish-jain-225" in contacts["github"]
    assert "tanish-jain-tj02022005" in contacts["linkedin"]


def test_detect_preferred_locations_smart_corridors():
    """Verify Indian tech corridors and sub-metro clusters are mapped to primary metro hubs."""
    assert detect_preferred_locations_smart("Living in Dombivli, Maharashtra") == ["Mumbai"]
    assert detect_preferred_locations_smart("Office at Whitefield, Electronic City") == ["Bengaluru"]
    assert detect_preferred_locations_smart("Hinjewadi Phase 1, Magarpatta") == ["Pune"]
    assert detect_preferred_locations_smart("Hitec City, Gachibowli, Cyberabad") == ["Hyderabad"]
    assert detect_preferred_locations_smart("Noida Sector 62, Gurgaon Cyber City") == ["Delhi-NCR"]


def test_extract_skills_ungluing_and_category_prefixes():
    """Verify adjacent line endpoints are never glued and ampersand category headers are parsed cleanly."""
    resume_section = """
    TECHNICAL SKILLS
    Languages: Python, SQL, JavaScript, TypeScript, C++
    Frameworks & Libraries: React, Next.js, Flask, Node.js, Express.js
    Databases & Platforms: PostgreSQL, MongoDB, Firebase, Supabase
    Developer Tools: Git, GitHub Actions, Postman, Vercel, Render, debugging
    """
    skills = _extract_skills_from_text(resume_section)

    # Glued tokens must NOT exist
    assert "C++ React" not in skills
    assert "Supabase Pytest" not in skills
    assert "debugging Git" not in skills

    # Individual canonical skills must be extracted cleanly
    assert "Python" in skills
    assert "C++" in skills
    assert "React" in skills
    assert "Flask" in skills
    assert "PostgreSQL" in skills
    assert "Supabase" in skills
    assert "Git" in skills
    assert "Vercel" in skills
    assert "Render" in skills

    # Duty/soft buzzwords must be stripped
    assert "debugging" not in skills


def test_clean_pdf_extracted_text_repairs_artifacts():
    """Verify clean_pdf_extracted_text unglues years, CGPA, links, and repairs broken hyphenation."""
    raw = "Mumbai2023 EngineeringCGPA SystemLive Demo genera-\ntion hands- on •Python"
    cleaned = clean_pdf_extracted_text(raw)
    assert "Mumbai 2023" in cleaned
    assert "Engineering CGPA" in cleaned
    assert "generation" in cleaned
    assert "hands-on" in cleaned
    assert "• Python" in cleaned


def test_real_user_pdf_resume_parsing(client, mock_supabase_env):
    """End-to-end test against the real uploaded resume PDF verifying accuracy across all dimensions."""
    import os
    pdf_path = r"C:\Users\Tanish\.gemini\antigravity\brain\da974832-2702-4d2d-bba5-411944c7c095\.user_uploaded\media_1793514186809_c2998b57.pdf"
    if not os.path.exists(pdf_path):
        pytest.skip("Local test PDF resume not found on disk")

    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()

    extracted_txt = extract_text_from_pdf(pdf_bytes)
    assert len(extracted_txt) > 200

    # Test through fallback upload route
    with (
        mock.patch("jobhunt.llm.build_profile", side_effect=Exception("LLM fallback trigger")),
        mock.patch("jobhunt.memory.SupabaseMemory.get_user_profile", return_value={}),
    ):
        res = client.post(
            "/api/resume/upload",
            json={"resume_text": extracted_txt, "filename": "tanish_sanghvi_resume.pdf"},
            headers={"Authorization": "Bearer mock-token"},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"

        prof = data["profile"]
        assert prof["name"] == "Tanish Sanghvi"
        assert prof["experience_years"] == 0.0
        assert prof["experience_level"] == "fresher"
        assert prof["notice_period"] == "immediate"
        assert "Mumbai" in prof["preferred_locations"]

        # Skills validation
        assert "Python" in prof["skills"]
        assert "React" in prof["skills"]
        assert "Flask" in prof["skills"]
        assert "PostgreSQL" in prof["skills"]
        assert "C++ React" not in prof["skills"]
        assert "Supabase Pytest" not in prof["skills"]
        assert "debugging Git" not in prof["skills"]

        # Education & projects
        assert "Vivekanand Education Society" in prof["education"]
        assert prof["graduation_year"] == 2027
        assert len(prof["notable_projects"]) >= 3
        assert any("Edvanta" in p for p in prof["notable_projects"])
        assert any("Department Ledger Portal" in p for p in prof["notable_projects"])

        # Contact validation
        assert prof["phone"] == "+91-7021341948"
        assert prof["candidate_email"] == "tanishjain020205@gmail.com"
        assert prof["notification_email"] == "tanishjain020205@gmail.com"
        assert data["parsed_profile"]["email"] == "tanishjain020205@gmail.com"
        assert "tanish-jain-225" in prof["github"]
        assert "tanish-jain-tj02022005" in prof["linkedin"]


