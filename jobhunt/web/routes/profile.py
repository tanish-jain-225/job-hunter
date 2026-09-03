"""Candidate profile, preferences, and Resume Studio upload/parsing routes."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
from typing import Any
from flask import Blueprint, jsonify, request

from ... import cli, llm
from ...auth import require_auth
from ...memory import SupabaseMemory
from ...store import get_writable_path
from ..state import get_current_user_context

logger = logging.getLogger(__name__)

profile_bp = Blueprint("profile", __name__)


def _extract_skills_from_text(resume_text: str) -> list[str]:
    """Safely extract skills from resume text using strict word boundaries to avoid false substring matches."""
    if not resume_text:
        return []
    common_keywords = [
        "Python",
        "JavaScript",
        "TypeScript",
        "Golang",
        "Go",
        "Java",
        "C++",
        "C#",
        "Rust",
        "PostgreSQL",
        "SQL",
        "MySQL",
        "MongoDB",
        "Redis",
        "Docker",
        "Kubernetes",
        "AWS",
        "GCP",
        "Azure",
        "FastAPI",
        "Flask",
        "Django",
        "React",
        "React.js",
        "Next.js",
        "Node.js",
        "Express.js",
        "REST APIs",
        "GraphQL",
        "Microservices",
        "CI/CD",
        "Git",
        "Tailwind CSS",
        "Tailwind",
        "Jest",
        "Playwright",
        "Firebase",
        "Firestore",
        "Distributed Systems",
        "AI",
        "LLM",
    ]
    found_skills: list[str] = []
    for kw in common_keywords:
        escaped = re.escape(kw)
        pattern = rf"(?<![a-zA-Z0-9]){escaped}(?![a-zA-Z0-9])"
        if re.search(pattern, resume_text, re.IGNORECASE):
            found_skills.append(kw)
    return found_skills


@profile_bp.route("/api/profile", methods=["GET", "POST"])
@require_auth
def api_profile():
    """Get or update candidate search profile, notification toggles, and memory preferences."""
    email, token = get_current_user_context()
    memory = SupabaseMemory(token=token)
    cfg = cli._cfg(raise_on_error=False)

    if request.method == "GET":
        # Return the DB profile exactly as stored — even if it is a blank stub.
        profile = None
        if email and memory.is_configured:
            memory._ensure_user_profile_exists(email, token=token)
            profile = memory.get_user_profile(email, token=token)
        # If Supabase is not configured fall back to the local profile file.
        if not profile:
            raw = cli._load_profile(cfg, raise_on_error=False) or {}
            raw.setdefault("onboarding_completed", True)
            profile = raw

        return jsonify(
            {"status": "success", "email": email, "profile": profile, "memory_connected": memory.is_configured}
        )

    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        if not email:
            return jsonify({"status": "error", "message": "Authenticated user email required."}), 400

        skills_val = data.get("skills")
        target_val = data.get("target_keywords")
        # Mark onboarding complete only if candidate criteria exist
        data["onboarding_completed"] = bool(
            (data.get("name") or "").strip()
            or (data.get("title") or "").strip()
            or (isinstance(skills_val, list) and len(skills_val) > 0)
            or (isinstance(target_val, list) and len(target_val) > 0)
        )

        # Merge with existing profile in Supabase so existing background data is preserved
        existing = memory.get_user_profile(email, token=token) if memory.is_configured else {}
        merged_profile = {**(existing or {}), **data}

        # If new non-empty resume_text is submitted without skills, auto-extract skills
        data_resume_text = (data.get("resume_text") or "").strip()
        if data_resume_text and not data.get("skills"):
            found_skills = _extract_skills_from_text(data_resume_text)
            if found_skills:
                merged_profile["skills"] = found_skills[:12]

        if memory.is_configured:
            memory.upsert_user_profile(email, merged_profile, token=token)

        try:
            profile_path = get_writable_path(cfg.get("profile_file", "profile.json"))
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(merged_profile, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not cache profile locally: {e}")

        return jsonify(
            {
                "status": "success",
                "message": "Candidate profile and preferences successfully stored in Supabase PostgreSQL.",
                "profile": merged_profile,
                "email": email,
            }
        )


@profile_bp.route("/api/profile/reset", methods=["POST"])
@require_auth
def api_profile_reset():
    """Flush out candidate profile, resume text, target criteria, and notification preferences."""
    email, token = get_current_user_context()
    if not email:
        return jsonify({"status": "error", "message": "Authentication required."}), 401

    memory = SupabaseMemory(token=token)
    cfg = cli._cfg(raise_on_error=False)

    blank_profile: dict[str, Any] = {
        "email": email,
        "name": "",
        "title": "",
        "education": "",
        "experience_years": 0,
        "skills": [],
        "target_keywords": [],
        "exclude_keywords": [],
        "resume_text": "",
        "resume_filename": "",
        "email_notifications_enabled": False,
        "notification_email": email,
        "min_score_notification": None,
        "onboarding_completed": False,
        "preferred_locations": [],
        "job_types": [],  # e.g. ["fulltime", "internship", "remote", "hybrid", "onsite"]
        "experience_level": "",  # e.g. "fresher", "0-1", "1-3", "3-5", "5+"
        "min_salary_lpa": 0,
        "preferred_sectors": [],  # e.g. ["fintech", "saas", "edtech"]
        "profile_json": {},
    }

    if memory.is_configured:
        memory.upsert_user_profile(email, blank_profile, token=token)

    try:
        profile_path = get_writable_path(cfg.get("profile_file", "profile.json"))
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(blank_profile, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not reset local profile cache: {e}")

    return jsonify(
        {
            "status": "success",
            "message": "Your profile information and resume context have been completely flushed.",
            "profile": blank_profile,
        }
    )


@profile_bp.route("/api/resume/upload", methods=["POST"])
@require_auth
def api_resume_upload():
    """Upload and parse candidate resume (PDF/TXT) -> dynamic AI profile extraction and Supabase sync."""
    email, token = get_current_user_context()
    if not email:
        return jsonify({"status": "error", "message": "Authentication required."}), 401

    resume_text = ""
    resume_bytes = None
    is_pdf = False
    filename = ""

    # Check multipart file upload
    if "file" in request.files:
        file = request.files["file"]
        filename = file.filename or "resume"
        content = file.read()
        if filename.lower().endswith(".pdf"):
            is_pdf = True
            resume_bytes = content
            resume_text = llm.extract_text_from_pdf(content)
        else:
            resume_text = content.decode("utf-8", errors="ignore")
    else:
        # Check raw JSON payload
        data = request.get_json(silent=True) or {}
        resume_text = data.get("resume_text", "").strip()
        filename = data.get("filename", "pasted_resume.txt")

    if not resume_text and not resume_bytes:
        return jsonify({"status": "error", "message": "No resume file or text content provided."}), 400

    memory = SupabaseMemory(token=token)

    # Perform AI Candidate Profile Extraction with 14s responsive safety timeout
    parsed_profile = None
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        provider, model = llm.resolve("draft")
        future = executor.submit(
            llm.build_profile,
            resume_bytes=resume_bytes,
            resume_text=resume_text,
            is_pdf=is_pdf,
            provider=provider,
            model=model,
        )
        parsed_profile = future.result(timeout=30.0)
    except Exception as e:
        logger.warning(f"AI profile extraction notice ({e}), using smart local parser.")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if not parsed_profile or not isinstance(parsed_profile, dict):
        # Fallback smart extraction from resume text if LLM unavailable or times out
        username_part = email.split("@")[0]
        derived_name = ""
        derived_title = ""
        derived_edu = ""
        if resume_text:
            lines = [l.strip() for l in resume_text.splitlines() if l.strip()]
            first_lines = [l for l in lines[:10] if len(l) < 50]
            if first_lines:
                derived_name = first_lines[0]
            title_keywords = ["Engineer", "Developer", "Architect", "Scientist", "Designer", "Specialist", "Analyst", "Lead", "Manager", "Consultant"]
            for l in lines[:15]:
                if any(tk.lower() in l.lower() for tk in title_keywords) and len(l) < 60:
                    derived_title = l
                    break
            edu_keywords = ["B.Tech", "B.E.", "M.Tech", "M.S.", "Bachelor", "Master", "Degree", "University", "College", "Institute"]
            for l in lines:
                if any(ek.lower() in l.lower() for ek in edu_keywords) and len(l) < 80:
                    derived_edu = l
                    break

        if not derived_name or len(derived_name) > 40:
            derived_name = " ".join(
                part.capitalize() for part in username_part.replace(".", " ").replace("_", " ").split()
            )

        skills_list = _extract_skills_from_text(resume_text)[:15] if resume_text else []

        target_titles: list[str] = []
        if derived_title:
            target_titles.append(derived_title)
        if any(s.lower() in ["python", "django", "fastapi", "flask", "node.js", "backend", "golang", "java"] for s in skills_list):
            if "Backend Engineer" not in target_titles:
                target_titles.append("Backend Engineer")
        if any(s.lower() in ["react", "next.js", "typescript", "frontend", "vue", "javascript"] for s in skills_list):
            if "Frontend Engineer" not in target_titles:
                target_titles.append("Frontend Engineer")
        if any(s.lower() in ["full stack", "fullstack", "node.js", "react", "next.js"] for s in skills_list):
            if "Full Stack Developer" not in target_titles:
                target_titles.append("Full Stack Developer")
        if not target_titles:
            target_titles = ["Software Engineer", "Full Stack Developer"]

        parsed_profile = {
            "name": derived_name or "",
            "current_title": derived_title or "Software Engineer",
            "years_experience": 0.0,
            "education": derived_edu or "",
            "core_skills": skills_list,
            "target_titles": target_titles[:5],
            "domains": ["Software Engineering", "Full Stack", "Web Development"],
            "notable_projects": [],
            "seniority": "mid",
            "experience_level": "0-1",
        }

    # Fetch existing profile to retain notification preferences
    existing = memory.get_user_profile(email, token=token) if memory.is_configured else {}
    existing_notif = bool((existing or {}).get("email_notifications_enabled", False))
    existing_target_email = (existing or {}).get("notification_email") or email

    full_profile = {
        "email": email,
        "name": parsed_profile.get("name") or "",
        "title": parsed_profile.get("current_title") or "",
        "education": parsed_profile.get("education") or "",
        "experience_years": parsed_profile.get("years_experience") or 0.0,
        "skills": parsed_profile.get("core_skills") or [],
        "target_keywords": parsed_profile.get("target_titles") or [],
        "exclude_keywords": parsed_profile.get("exclude_keywords") or (existing or {}).get("exclude_keywords") or [],
        "resume_text": resume_text or (existing or {}).get("resume_text") or "",
        "resume_filename": filename,
        "email_notifications_enabled": existing_notif,
        "notification_email": existing_target_email,
        "min_score_notification": (existing or {}).get("min_score_notification"),
        "preferred_locations": parsed_profile.get("preferred_locations")
        or (existing or {}).get("preferred_locations")
        or [],
        "location_preference": parsed_profile.get("location_preference")
        or (existing or {}).get("location_preference")
        or "all_india",
        "job_types": parsed_profile.get("job_types") or (existing or {}).get("job_types") or [],
        "experience_level": parsed_profile.get("experience_level") or (existing or {}).get("experience_level") or "",
        "seniority": parsed_profile.get("seniority") or "",
        "min_salary_lpa": (existing or {}).get("min_salary_lpa") or 0,
        "preferred_sectors": (existing or {}).get("preferred_sectors") or [],
        "profile_json": parsed_profile,
    }

    return jsonify(
        {
            "status": "success",
            "message": "Resume text successfully extracted. You can review and alter your text context before saving.",
            "resume_text": resume_text,
            "profile": full_profile,
            "parsed_profile": parsed_profile,
        }
    )


@profile_bp.route("/api/profile/preferences", methods=["GET", "POST"])
@require_auth
def api_profile_preferences():
    """Get or update user search preferences (job types, locations, experience level, salary)."""
    email, token = get_current_user_context()
    memory = SupabaseMemory(token=token)
    cfg = cli._cfg(raise_on_error=False)

    if request.method == "GET":
        profile = None
        if email and memory.is_configured:
            profile = memory.get_user_profile(email, token=token)
        if not profile:
            profile = cli._load_profile(cfg, raise_on_error=False) or {}

        return jsonify(
            {
                "status": "success",
                "preferences": {
                    "preferred_locations": profile.get("preferred_locations") or [],
                    "job_types": profile.get("job_types") or [],
                    "experience_level": profile.get("experience_level") or "",
                    "min_salary_lpa": profile.get("min_salary_lpa") or 0,
                    "preferred_sectors": profile.get("preferred_sectors") or [],
                    "target_keywords": profile.get("target_keywords") or [],
                    "exclude_keywords": profile.get("exclude_keywords") or [],
                },
            }
        )

    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        if not email:
            return jsonify({"status": "error", "message": "Authentication required."}), 400

        # Merge with existing profile
        existing = memory.get_user_profile(email, token=token) if memory.is_configured else {}
        merged = {**(existing or {}), **data, "onboarding_completed": True}

        if memory.is_configured:
            memory.upsert_user_profile(email, merged, token=token)

        try:
            profile_path = get_writable_path(cfg.get("profile_file", "profile.json"))
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            with open(profile_path, "w", encoding="utf-8") as f:
                import json

                json.dump(merged, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not cache preferences locally: {e}")

        return jsonify(
            {
                "status": "success",
                "message": "Search preferences updated successfully.",
                "preferences": {
                    "preferred_locations": merged.get("preferred_locations") or [],
                    "job_types": merged.get("job_types") or [],
                    "experience_level": merged.get("experience_level") or "",
                    "min_salary_lpa": merged.get("min_salary_lpa") or 0,
                    "preferred_sectors": merged.get("preferred_sectors") or [],
                },
            }
        )
