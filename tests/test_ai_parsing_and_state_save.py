"""Comprehensive end-to-end test suite for enhanced AI parsing and save state integrity."""

from __future__ import annotations

import json
from unittest import mock
import pytest

from jobhunt import llm
from jobhunt.fetch import Job
from jobhunt.llm_utils import (
    parse_json,
    strip_json_comments,
    repair_truncated_json,
    _ensure_list,
    _as_list,
)
from jobhunt.store import Store


# =============================================================================
# 1. AI Parsing Tests: Resilient JSON, Comments, Truncation, Fences, Thoughts
# =============================================================================

def test_parse_json_with_single_and_multiline_comments():
    raw = """
    // Leading comment
    {
      "name": "Jane Doe", // Candidate name
      /* Multi-line explanation:
         Core skills extracted from experience */
      "skills": ["Python", "FastAPI"], // Skills list
      "url": "https://example.com/apply//123" // Note URL with double slash inside string
    }
    """
    res = parse_json(raw)
    assert res["name"] == "Jane Doe"
    assert res["skills"] == ["Python", "FastAPI"]
    assert res["url"] == "https://example.com/apply//123"


def test_strip_json_comments_standalone():
    raw = '{"site": "https://company.com/jobs/*test*"} /* trailing comment */'
    stripped = strip_json_comments(raw)
    assert stripped == '{"site": "https://company.com/jobs/*test*"} '
    assert strip_json_comments("") == ""


def test_repair_truncated_json_standalone():
    raw_arr = '[{"id": "job-1", "score": 9.0}, {"id": "job-2", "score": 8.5}, {"id": "job-3", "sc'
    repaired_arr = repair_truncated_json(raw_arr)
    assert repaired_arr == [{"id": "job-1", "score": 9.0}, {"id": "job-2", "score": 8.5}]

    raw_obj = '{"name": "Alice", "title": "Lead Engineer", "summary": "Strong'
    repaired_obj = repair_truncated_json(raw_obj)
    assert repaired_obj == {"name": "Alice", "title": "Lead Engineer"}
    assert repair_truncated_json("random string") is None


def test_parse_json_invalid_raises():
    with pytest.raises(ValueError, match="could not parse JSON"):
        parse_json("completely unparseable gibberish with no braces")


def test_parse_json_with_trailing_commas():
    raw = """
    {
      "items": [
        "one",
        "two",
      ],
      "active": true,
    }
    """
    res = parse_json(raw)
    assert res["items"] == ["one", "two"]
    assert res["active"] is True


def test_parse_json_with_python_literals():
    raw = """
    {
      "flag_true": True,
      "flag_false": False,
      "empty_val": None,
      "score": 9.5
    }
    """
    res = parse_json(raw)
    assert res["flag_true"] is True
    assert res["flag_false"] is False
    assert res["empty_val"] is None
    assert res["score"] == 9.5


def test_parse_json_with_single_quote_dict():
    raw = "{'company': 'Stripe', 'role': 'Software Engineer', 'score': 9}"
    res = parse_json(raw)
    assert res["company"] == "Stripe"
    assert res["score"] == 9


def test_parse_json_with_thought_and_thinking_blocks():
    raw_thought = "<thought>Analyzing the candidate match against the role requirements...</thought>\n{\"fit\": 9.0}"
    assert parse_json(raw_thought) == {"fit": 9.0}

    raw_thinking = "<thinking>Deep reasoning step 1\nStep 2</thinking>\n```json\n{\"fit\": 8.5}\n```"
    assert parse_json(raw_thinking) == {"fit": 8.5}


def test_parse_json_with_unclosed_thought_block():
    raw_unclosed = "<think>The model ran out of tokens while thinking but started emitting json\n[{\"job_id\": \"j1\", \"score\": 8.0}]"
    res = parse_json(raw_unclosed)
    assert isinstance(res, list)
    assert res[0]["job_id"] == "j1"


def test_parse_json_recovers_truncated_array():
    # Simulated token cutoff in the middle of job 2
    raw_truncated = '[{"job_id": "j1", "score": 9.0, "reason": "strong match"}, {"job_id": "j2", "score": 7.0, "reason": "incom'
    res = parse_json(raw_truncated)
    assert isinstance(res, list)
    assert len(res) == 1
    assert res[0]["job_id"] == "j1"
    assert res[0]["score"] == 9.0


def test_parse_json_recovers_truncated_dict():
    raw_truncated_dict = '{"fit_summary": "Great match for Python developer", "salary": "20 LPA", "gaps": ["Kubernetes"'
    res = parse_json(raw_truncated_dict)
    assert isinstance(res, dict)
    assert res["fit_summary"] == "Great match for Python developer"
    assert res["salary"] == "20 LPA"


# =============================================================================
# 2. _as_list and _ensure_list Robustness Tests
# =============================================================================

def test_as_list_with_various_wrapper_keys():
    assert _as_list({"data": [{"job_id": "1"}]}) == [{"job_id": "1"}]
    assert _as_list({"candidates": [{"job_id": "2"}]}) == [{"job_id": "2"}]
    assert _as_list({"evaluations": [{"job_id": "3"}]}) == [{"job_id": "3"}]
    assert _as_list({"output": [{"job_id": "4"}]}) == [{"job_id": "4"}]
    assert _as_list({"matches": [{"job_id": "5"}]}) == [{"job_id": "5"}]
    assert _as_list(None) == []


def test_ensure_list_formats():
    # Comma-separated string
    assert _ensure_list("Python, FastAPI, Docker, PostgreSQL") == ["Python", "FastAPI", "Docker", "PostgreSQL"]

    # Numbered list
    numbered = "1. First project\n2. Second project\n3. Third project"
    assert _ensure_list(numbered) == ["First project", "Second project", "Third project"]

    # Bulleted list
    bulleted = "- Skill A\n* Skill B\n• Skill C"
    assert _ensure_list(bulleted) == ["Skill A", "Skill B", "Skill C"]

    # List of objects
    dict_list = [{"name": "React"}, {"skill": "Node.js"}, {"value": "AWS"}]
    assert _ensure_list(dict_list) == ["React", "Node.js", "AWS"]

    # Dict of values
    dict_val = {"b1": "Bullet one", "b2": "Bullet two"}
    assert _ensure_list(dict_val) == ["Bullet one", "Bullet two"]


# =============================================================================
# 3. AI Scoring and Draft Parsing Tests
# =============================================================================

def test_parse_score_various_formats():
    assert llm._parse_score(8.5) == 8.5
    assert llm._parse_score(10) == 10.0
    assert llm._parse_score("8/10") == 8.0
    assert llm._parse_score("9.5 / 10") == 9.5
    assert llm._parse_score("Score: 7") == 7.0
    assert llm._parse_score("not_a_number") == 0.0
    assert llm._parse_score(None) == 0.0
    assert llm._parse_score(15) == 10.0  # Clamped
    assert llm._parse_score(-5) == 0.0   # Clamped


def test_build_profile_normalization():
    mock_provider = mock.MagicMock()
    # Mock LLM returning wrapped in 1-element list, with string years_experience, and comma-separated skills
    mock_provider.complete.return_value = json.dumps([
        {
            "name": "Jane Candidate",
            "current_title": "Senior Backend Developer",
            "years_experience": "4+ years",
            "core_skills": ["Python", "Golang", "Kubernetes"],
            "target_titles": ["Backend Engineer", "Platform Engineer"],
            "domains": ["Cloud", "Distributed Systems"],
            "notable_projects": ["Engineered low-latency broker in Go"],
            "education": "B.Tech in Computer Science",
            "seniority": "senior",
            "experience_level": "3-5",
            "job_types": ["fulltime", "remote"],
            "location_preference": "all_india"
        }
    ])

    prof = llm.build_profile(resume_text="Sample resume text", provider=mock_provider, model="gemini-3.5-flash")
    assert isinstance(prof, dict)
    assert prof["name"] == "Jane Candidate"
    assert prof["years_experience"] == 4.0
    assert prof["experience_years"] == 4.0
    assert isinstance(prof["core_skills"], list)
    assert prof["core_skills"] == prof["skills"]
    assert "Python" in prof["core_skills"]
    assert prof["target_titles"] == prof["target_keywords"]
    assert "Backend Engineer" in prof["target_titles"]
    assert prof["title"] == prof["current_title"] == "Senior Backend Developer"
    assert prof["experience_level"] == "3-5"
    assert prof["notice_period"] == "30_days"


def test_build_profile_bidirectional_aliases_and_indian_context():
    mock_provider = mock.MagicMock()
    mock_provider.complete.return_value = json.dumps({
        "name": "Arjun Sharma",
        "title": "Lead Platform Engineer",
        "experience_years": 8.5,
        "skills": ["Go", "Kubernetes", "AWS", "Kafka"],
        "target_keywords": ["Staff Engineer", "Principal Architect"],
        "notice_period": "Immediate (0 days notice)",
        "preferred_locations": "Bengaluru, Hyderabad, Pune",
        "current_ctc_lpa": "28 LPA",
        "expected_ctc_lpa": "38 LPA",
    })

    prof = llm.build_profile(resume_text="Resume", provider=mock_provider, model="gemini-3.5-flash")
    assert prof["name"] == "Arjun Sharma"
    assert prof["title"] == prof["current_title"] == "Lead Platform Engineer"
    assert prof["experience_years"] == prof["years_experience"] == 8.5
    assert prof["skills"] == prof["core_skills"] == ["Go", "Kubernetes", "AWS", "Kafka"]
    assert prof["target_keywords"] == prof["target_titles"] == ["Staff Engineer", "Principal Architect"]
    assert prof["notice_period"] == "immediate"
    assert prof["preferred_locations"] == ["Bengaluru", "Hyderabad", "Pune"]
    assert prof["location_preference"] == "specific_cities"
    assert prof["current_ctc_lpa"] == 28.0
    assert prof["expected_ctc_lpa"] == 38.0
    assert prof["min_salary_lpa"] == 38.0


def test_draft_synonym_and_alias_mapping():
    mock_provider = mock.MagicMock()
    # LLM using slight naming synonyms e.g. summary, bullets, compensation, outreach
    mock_provider.complete.return_value = json.dumps({
        "summary": "Outstanding match for Backend role.",
        "eligibility": "India-Based Role",
        "type": "remote",
        "compensation": "₹25-30 LPA",
        "project": "Distributed message queue",
        "bullets": ["Architected streaming pipeline", "Optimized DB queries by 40%"],
        "skills": ["Go", "Kafka", "PostgreSQL"],
        "missing_skills": ["Kafka Admin"],
        "note": "Dear Hiring Manager, I am writing to apply...",
        "outreach": "Hi! Noticed your Backend position...",
        "referral": "Hi Alex, wondering if you could refer me...",
        "questions": ["How do you scale partitions?", "What is the sprint rhythm?"]
    })

    job = Job(
        job_id="test:1",
        ats="greenhouse",
        company="TechCorp",
        title="Backend Engineer",
        location="Bengaluru",
        url="https://example.com/job/1",
        description="We are looking for a Go engineer to build Kafka systems.",
    )

    llm.draft([job], profile={"name": "Jane"}, provider=mock_provider, model="gemini-3.5-flash", delay_seconds=0)

    assert job.draft["fit_summary"] == "Outstanding match for Backend role."
    assert job.draft["india_eligibility"] == "India-Based Role"
    assert job.draft["salary_range_inr"] == "₹25-30 LPA"
    assert job.draft["best_project"] == "Distributed message queue"
    assert len(job.draft["tailored_bullets"]) == 2
    assert "Go" in job.draft["matching_skills"]
    assert "Kafka Admin" in job.draft["gaps"]
    assert "Dear Hiring Manager" in job.draft["cover_note"]
    assert "Noticed your Backend position" in job.draft["cold_outreach"]
    assert "refer me" in job.draft["referral_request"]
    assert len(job.draft["questions_to_ask"]) == 2


# =============================================================================
# 4. State Save & Store Integrity Tests
# =============================================================================

def test_store_add_job_with_direct_stage(tmp_path):
    store_file = tmp_path / "seen.json"
    st = Store(store_file)

    jid = st.add_job(
        title="Staff Engineer",
        company="Stripe",
        location="Remote",
        url="https://stripe.com/jobs/1",
        stage="interviewing",
        score=9.2,
    )

    assert jid is not None
    assert st.data[jid]["application_stage"] == "interviewing"
    assert st.data[jid]["applied"] is True
    assert st.data[jid]["applied_on"] is not None

    # Reload store from disk
    st_reloaded = Store(store_file)
    assert jid in st_reloaded.data
    assert st_reloaded.data[jid]["application_stage"] == "interviewing"
    assert st_reloaded.data[jid]["applied"] is True
    assert st_reloaded.data[jid]["score"] == 9.2

