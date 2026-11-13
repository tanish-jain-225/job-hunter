"""Candidate profile, preferences, and Resume Studio upload/parsing routes."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import math
import os
import re
from typing import Any
from flask import Blueprint, current_app, jsonify, request

from ... import cli, llm
from ...auth import require_auth
from ...llm_utils import (
    calculate_timeline_yoe,
    clean_pdf_extracted_text,
    detect_preferred_locations_smart,
    normalize_technical_skills,
    parse_contact_smart,
    parse_education_smart,
    parse_projects_smart,
    parse_summary_smart,
    sanitize_candidate_name,
    synthesize_headline_and_targets,
)
from ...memory import SupabaseMemory, create_blank_profile, invalidate_user_cache
from ...store import get_user_profile_path, get_writable_path  # noqa: F401
from ..state import enforce_rate_limit, get_current_user_context, get_user_profile, sanitize_profile_for_response

logger = logging.getLogger(__name__)

profile_bp = Blueprint("profile", __name__)

_SENSITIVE_KEY_MARKERS = ("api_key", "token", "secret", "password")
_MAX_CTC_LPA = 1000.0


def _strip_sensitive_fields(payload: dict[str, Any]) -> None:
    """Remove credential-like keys before persisting profile or preference payloads."""
    for key in list(payload):
        normalized = str(key).lower().replace("-", "_")
        if any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS):
            payload.pop(key, None)


def _clamp_float(value: Any, *, minimum: float = 0.0, maximum: float = _MAX_CTC_LPA) -> float:
    """Parse finite numeric input and clamp it within safe domain bounds."""
    try:
        parsed = float(value if value is not None else 0.0)
    except (ValueError, TypeError):
        return 0.0
    if not math.isfinite(parsed):
        return 0.0
    return max(minimum, min(maximum, parsed))


def _normalize_string_list(value: Any, *, max_items: int = 30, max_len: int = 100) -> list[str]:
    """Normalize comma-separated or list inputs into bounded stripped strings."""
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, list):
        items = value
    else:
        return []
    return [cleaned[:max_len] for item in items if (cleaned := str(item).strip())][:max_items]


def _normalize_preference_fields(
    target: dict[str, Any],
    *,
    list_fields: tuple[str, ...] = ("exclude_keywords", "job_types", "preferred_sectors"),
) -> None:
    """Normalize shared location, CTC, and list fields on profile/preference payloads."""
    raw_pref = target.get("preferred_locations")
    pref_source = raw_pref.get("locations", []) if isinstance(raw_pref, dict) else raw_pref
    target["preferred_locations"] = _normalize_string_list(pref_source, max_items=30, max_len=100)

    raw_loc = target.get("location_preference")
    if isinstance(raw_loc, dict):
        loc_type = str(raw_loc.get("type") or "all_india").strip()[:50]
        loc_list = _normalize_string_list(raw_loc.get("locations", []), max_items=30, max_len=100)
        if not loc_list and target["preferred_locations"]:
            loc_list = list(target["preferred_locations"])
        target["location_preference"] = {"type": loc_type, "locations": loc_list}
    elif isinstance(raw_loc, str) and raw_loc.strip():
        target["location_preference"] = raw_loc.strip()[:50]
    else:
        target["location_preference"] = "specific_cities" if target["preferred_locations"] else "all_india"

    for ctc_field in ("current_ctc_lpa", "expected_ctc_lpa", "min_salary_lpa"):
        if ctc_field in target and target[ctc_field] is not None:
            target[ctc_field] = _clamp_float(target[ctc_field], minimum=0.0, maximum=_MAX_CTC_LPA)

    if target.get("expected_ctc_lpa") and not target.get("min_salary_lpa"):
        target["min_salary_lpa"] = target["expected_ctc_lpa"]

    for list_field in list_fields:
        target[list_field] = _normalize_string_list(target.get(list_field), max_items=30, max_len=100)


def _extract_preferences_view(profile: dict[str, Any], *, include_keywords: bool = True) -> dict[str, Any]:
    """Serialize preference fields consistently across GET and POST responses."""
    prefs: dict[str, Any] = {
        "preferred_locations": profile.get("preferred_locations") or [],
        "location_preference": profile.get("location_preference") or "all_india",
        "job_types": profile.get("job_types") or [],
        "experience_level": profile.get("experience_level") or "",
        "notice_period": profile.get("notice_period") or "30_days",
        "current_ctc_lpa": profile.get("current_ctc_lpa") or 0,
        "expected_ctc_lpa": profile.get("expected_ctc_lpa") or 0,
        "min_salary_lpa": profile.get("min_salary_lpa") or 0,
        "preferred_sectors": profile.get("preferred_sectors") or [],
    }
    if include_keywords:
        prefs["target_keywords"] = profile.get("target_keywords") or []
        prefs["exclude_keywords"] = profile.get("exclude_keywords") or []
    return prefs


def _persist_profile_state(
    memory: SupabaseMemory,
    cfg: dict[str, Any],
    email: str,
    token: str | None,
    profile_data: dict[str, Any],
    *,
    cloud_error_message: str,
) -> tuple[Any, int] | None:
    """Persist profile data to Supabase when configured and update the local JSON cache."""
    if memory.is_configured:
        if not memory.upsert_user_profile(email, profile_data, token=token):
            return jsonify({"status": "error", "message": cloud_error_message}), 503

    try:
        profile_path = get_user_profile_path(cfg.get("profile_file", "profile.json"), email)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(profile_data, f, indent=2)
    except Exception as e:
        logger.warning("Could not cache profile locally: %s", e)
    return None


def is_profile_complete(profile: dict[str, Any]) -> bool:
    """Return whether a candidate has the minimum data required to run a hunt."""
    if profile.get("onboarding_completed") is True:
        return True
    name = str(profile.get("name") or "").strip()
    skills = profile.get("skills") or profile.get("core_skills") or []
    targets = profile.get("target_keywords") or profile.get("target_titles") or []
    has_skills = isinstance(skills, (list, tuple, set)) and any(str(item).strip() for item in skills)
    has_targets = isinstance(targets, (list, tuple, set)) and any(str(item).strip() for item in targets)
    return bool(name and has_skills and has_targets)


def _extract_skills_from_text(resume_text: str) -> list[str]:
    """Safely extract technical skills from resume text using section heuristics and strict word boundaries."""
    if not resume_text:
        return []

    found_skills: list[str] = []
    seen_lower: set[str] = set()

    def add_skill(sk: str) -> None:
        sk_clean = sk.strip()
        if sk_clean and len(sk_clean) <= 30 and sk_clean.lower() not in seen_lower:
            seen_lower.add(sk_clean.lower())
            found_skills.append(sk_clean)

    # 1. Section-aware extraction: check explicit Skills section
    skills_sec_m = re.search(
        r"(?i)(?:technical\s+skills|skills\s*(?:&|and)\s*technologies|core\s+competencies|technologies|technical\s+expertise|skills)\s*[:\n](.*?)(?=\n\s*(?:experience|work\s+history|employment|projects|education|certifications|awards|summary|objective|$))",
        resume_text,
        re.DOTALL,
    )
    if skills_sec_m:
        sec_text = skills_sec_m.group(1)
        # Process lines individually to avoid joining adjacent line tokens (e.g. "C++ React")
        for line in sec_text.splitlines():
            line_str = re.sub(r"^[^:\n]{1,50}:\s*", "", line.strip())  # remove e.g. "Languages: ", "Backend & APIs: "
            if not line_str:
                continue
            line_str = re.sub(r"\(.*?\)", "", line_str)
            tokens = re.split(r"[,•·|\t;/]+", line_str)
            for tok in tokens:
                cleaned = tok.strip("•-*| \t()[]{}")
                if 1 < len(cleaned) <= 30 and not re.search(r"[@:]", cleaned) and not re.match(r"^\d+$", cleaned):
                    # Only add if it starts with a letter
                    if re.match(r"^[A-Za-z][A-Za-z0-9#\+\.\-\s]{0,29}$", cleaned):
                        # Filter out non-technical noise words
                        skip_words = {
                            "proficient", "familiar", "basics", "strong", "advanced", "intermediate",
                            "tools", "languages", "frameworks", "databases", "libraries", "platforms",
                            "apis", "developer", "backend", "frontend", "fullstack", "full stack",
                            "debugging", "error handling", "audit logging", "document autofill", "autofill",
                            "testing", "engineering", "development",
                        }
                        if cleaned.lower() not in skip_words:
                            add_skill(cleaned)

    # 2. Comprehensive catalog of 150+ modern cross-domain professional and technical keywords
    common_keywords = [
        # Engineering & Tech Stack
        "Python", "JavaScript", "TypeScript", "Golang", "Java", "C++", "C#", "Rust", "Ruby", "PHP", "Swift", "Kotlin", "Scala", "SQL",
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "SQLite", "Cassandra", "DynamoDB", "Firebase", "Firestore",
        "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Terraform", "Linux", "Git", "GitHub Actions", "CI/CD",
        "FastAPI", "Flask", "Django", "React", "Next.js", "Node.js", "Express.js", "NestJS", "Spring Boot", "ASP.NET", "Vue.js", "Angular", "Svelte",
        "REST APIs", "GraphQL", "gRPC", "Microservices", "Celery", "Kafka", "RabbitMQ", "WebSockets", "Prisma", "SQLAlchemy",
        "Tailwind CSS", "Redux", "Bootstrap", "HTML", "CSS", "Bash", "Shell",
        "Jest", "Playwright", "Pytest", "Selenium", "Cypress", "Postman",
        "Distributed Systems", "System Design", "OOP", "Data Structures", "Algorithms",
        "AI", "LLM", "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "PyTorch", "TensorFlow", "scikit-learn", "Pandas", "NumPy", "LangChain", "HuggingFace", "RAG",
        # Product & Design
        "Product Management", "Product Roadmapping", "PRDs", "User Stories", "A/B Testing", "Feature Prioritization", "Jira", "Confluence", "Linear", "Mixpanel", "Amplitude",
        "Figma", "Sketch", "Adobe XD", "Wireframing", "Prototyping", "Design Systems", "User Research", "Usability Testing", "UI/UX", "Interaction Design", "Visual Design",
        # Data & Analytics
        "Tableau", "Power BI", "Looker", "Metabase", "dbt", "Snowflake", "BigQuery", "Excel", "Advanced Excel",
        # Marketing & Growth
        "SEO", "SEM", "Google Ads", "Meta Ads", "HubSpot", "Marketo", "Google Analytics", "Content Strategy", "Copywriting", "Email Marketing", "Growth Marketing",
        # Sales & Business Development
        "Salesforce", "B2B Sales", "Lead Generation", "CRM", "Cold Outreach", "Pipeline Management", "Solution Selling", "Account Management",
        # Finance & Accounting
        "Financial Modeling", "Valuation", "QuickBooks", "Tally", "SAP", "Auditing", "Budgeting", "Financial Forecasting", "IFRS", "GAAP",
        # HR & People Operations
        "Talent Acquisition", "Technical Recruiting", "Recruiting", "HRIS", "Workday", "BambooHR", "People Operations", "Employee Relations",
        # Operations & Project Management
        "Supply Chain", "Logistics", "Operations Management", "Process Optimization", "Asana", "Monday.com", "PMP", "Scrum Master", "Agile",
        # Legal & Compliance
        "Contract Management", "Regulatory Compliance", "GDPR", "Due Diligence",
    ]

    for kw in common_keywords:
        escaped = re.escape(kw)
        pattern = rf"(?<![a-zA-Z0-9]){escaped}(?![a-zA-Z0-9])"
        flags = re.IGNORECASE if kw not in ("AI", "C", "R", "Go") else 0
        if re.search(pattern, resume_text, flags):
            add_skill(kw)

    if "Golang" not in found_skills and "Go" not in found_skills:
        if re.search(r"(?i)\b(?:golang|go\s+developer|go\s+engineer|go\s+routine|go\s+lang)\b", resume_text):
            add_skill("Go")

    return normalize_technical_skills(found_skills)


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
            if not profile:
                profile = create_blank_profile(email)
        else:
            raw = get_user_profile(cfg, email, token) or {}
            if raw and (raw.get("name") or raw.get("skills") or raw.get("core_skills")):
                raw.setdefault("onboarding_completed", True)
            elif email and not raw:
                raw = create_blank_profile(email)
            profile = raw

        return jsonify(
            {"status": "success", "email": email, "profile": sanitize_profile_for_response(profile), "memory_connected": memory.is_configured}
        )

    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        if not email:
            return jsonify({"status": "error", "message": "Authenticated user email required."}), 400

        for field in ("name", "title", "resume_text"):
            if field in data and not isinstance(data[field], str):
                return jsonify({"status": "error", "message": f"{field} must be a string."}), 400
        # Merge with existing profile in Supabase/local memory so existing background data is preserved
        existing = memory.get_user_profile(email, token=token) if memory.is_configured else {}
        if not existing:
            existing = {} if memory.is_configured else (get_user_profile(cfg, email, token) or {})
        merged_profile = {**(existing or {}), **data, "email": email}

        # Normalize experience_years and bidirectional alias years_experience
        y_val = data.get("experience_years") if "experience_years" in data else data.get("years_experience")
        if y_val is None:
            y_val = merged_profile.get("experience_years", merged_profile.get("years_experience", 0.0))
        flt_yoe = _clamp_float(y_val, minimum=0.0, maximum=70.0)
        merged_profile["experience_years"] = flt_yoe
        merged_profile["years_experience"] = flt_yoe

        # Bidirectional aliases for skills <-> core_skills
        raw_s = data.get("skills") if "skills" in data else data.get("core_skills")
        if raw_s is None:
            raw_s = merged_profile.get("skills") or merged_profile.get("core_skills")
        s_list = _normalize_string_list(raw_s, max_items=50, max_len=80)
        merged_profile["skills"] = s_list
        merged_profile["core_skills"] = s_list

        # Bidirectional aliases for target_keywords <-> target_titles
        raw_t = data.get("target_keywords") if "target_keywords" in data else data.get("target_titles")
        if raw_t is None:
            raw_t = merged_profile.get("target_keywords") or merged_profile.get("target_titles")
        t_list = _normalize_string_list(raw_t, max_items=30, max_len=100)
        merged_profile["target_keywords"] = t_list
        merged_profile["target_titles"] = t_list

        # Bidirectional aliases for title <-> current_title
        t_str = str(data.get("title") or data.get("current_title") or merged_profile.get("title") or merged_profile.get("current_title") or "").strip()[:200]
        merged_profile["title"] = t_str
        merged_profile["current_title"] = t_str

        # Candidate name normalization (strictly privacy-first: never synthesize from email or placeholders)
        raw_name = str(data.get("name") if "name" in data else (existing.get("name") or "")).strip()[:150]
        merged_profile["name"] = "" if raw_name == "Candidate" else raw_name
        merged_profile["education"] = str(merged_profile.get("education") or "").strip()[:300]
        if isinstance(merged_profile.get("resume_text"), str):
            merged_profile["resume_text"] = merged_profile["resume_text"][:50_000]

        # Smart title & target keywords cross-inference
        if not merged_profile.get("title") and merged_profile.get("target_keywords"):
            merged_profile["title"] = merged_profile["target_keywords"][0]
            merged_profile["current_title"] = merged_profile["target_keywords"][0]

        if not merged_profile.get("target_keywords") and merged_profile.get("title"):
            cur = merged_profile["title"]
            _, inferred = synthesize_headline_and_targets(
                cur,
                merged_profile.get("skills") or [],
                yoe=float(merged_profile.get("experience_years") or 0.0),
                domains=merged_profile.get("domains"),
            )
            merged_profile["target_keywords"] = inferred[:5]
            merged_profile["target_titles"] = inferred[:5]

        # Notice period normalization
        raw_np = str(data.get("notice_period") or merged_profile.get("notice_period") or "").lower().strip()
        if "imm" in raw_np or raw_np == "0":
            norm_np = "immediate"
        elif "15" in raw_np or "2 week" in raw_np:
            norm_np = "15_days"
        elif "60" in raw_np or "2 month" in raw_np:
            norm_np = "60_days"
        elif "90" in raw_np or "3 month" in raw_np:
            norm_np = "90_days"
        elif "30" in raw_np or "1 month" in raw_np:
            norm_np = "30_days"
        elif raw_np in {"immediate", "15_days", "30_days", "60_days", "90_days"}:
            norm_np = raw_np
        else:
            norm_np = "30_days"
        merged_profile["notice_period"] = norm_np

        _normalize_preference_fields(merged_profile)

        # Smart experience level calculation if missing
        if not merged_profile.get("experience_level"):
            y = float(merged_profile.get("experience_years") or 0.0)
            if y <= 0.0:
                merged_profile["experience_level"] = "fresher"
            elif y <= 1.0:
                merged_profile["experience_level"] = "0-1"
            elif y <= 3.0:
                merged_profile["experience_level"] = "1-3"
            elif y <= 5.0:
                merged_profile["experience_level"] = "3-5"
            else:
                merged_profile["experience_level"] = "5+"

        if not merged_profile.get("exclude_keywords"):
            exp_lvl = merged_profile.get("experience_level")
            if exp_lvl in ("fresher", "0-1"):
                merged_profile["exclude_keywords"] = ["Director", "VP", "Chief", "Head of", "Principal"]
            elif exp_lvl in ("3-5", "5+"):
                merged_profile["exclude_keywords"] = ["Intern", "Trainee", "Junior", "Fresher"]
            else:
                merged_profile["exclude_keywords"] = []

        if not merged_profile.get("job_types"):
            if merged_profile.get("experience_level") == "fresher":
                merged_profile["job_types"] = ["fulltime", "internship", "remote"]
            else:
                merged_profile["job_types"] = ["fulltime", "remote", "hybrid"]

        # If resume_text is available but skills are missing, auto-extract skills
        data_resume_text = (data.get("resume_text") or merged_profile.get("resume_text") or "").strip()
        if data_resume_text and not merged_profile.get("skills"):
            found_skills = _extract_skills_from_text(data_resume_text)
            if found_skills:
                merged_profile["skills"] = found_skills[:15]
                merged_profile["core_skills"] = found_skills[:15]

        merged_profile["onboarding_completed"] = is_profile_complete(merged_profile)
        _strip_sensitive_fields(merged_profile)

        persist_err = _persist_profile_state(
            memory,
            cfg,
            email,
            token,
            merged_profile,
            cloud_error_message="Profile could not be saved to secure cloud storage. Please try again.",
        )
        if persist_err is not None:
            return persist_err

        return jsonify(
            {
                "status": "success",
                "message": "Candidate profile and preferences successfully stored in Supabase PostgreSQL.",
                "profile": sanitize_profile_for_response(merged_profile),
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
    cfg = cli._cfg(raise_on_error=False)
    memory = SupabaseMemory(token=token)
    blank_profile = create_blank_profile(email)

    if memory.is_configured:
        if not memory.upsert_user_profile(email, blank_profile, token=token):
            return jsonify(
                {"status": "error", "message": "Profile reset could not be saved to secure cloud storage. Please try again."}
            ), 503
    invalidate_user_cache(email)

    try:
        profile_path = get_user_profile_path(cfg.get("profile_file", "profile.json"), email)
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        with open(profile_path, "w", encoding="utf-8") as f:
            json.dump(blank_profile, f, indent=2)
    except Exception as e:
        logger.warning("Could not reset local profile cache: %s", e)

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
    enforce_rate_limit("15 per hour")
    email, token = get_current_user_context()
    if not email:
        return jsonify({"status": "error", "message": "Authentication required."}), 401
    cfg = cli._cfg(raise_on_error=False)

    resume_text = ""
    resume_bytes = None
    is_pdf = False
    filename = ""

    # Check multipart file upload
    if "file" in request.files:
        file = request.files["file"]
        filename = file.filename or "resume"
        content = file.read()
        if len(content) > 5 * 1024 * 1024:
            return jsonify({"status": "error", "message": "File exceeds 5MB size limit."}), 400

        if filename.lower().endswith(".pdf"):
            if not content.startswith(b"%PDF-") and not current_app.testing:
                return jsonify({"status": "error", "message": "The uploaded file is not a valid PDF."}), 400
            is_pdf = True
            resume_bytes = content
            try:
                resume_text = llm.extract_text_from_pdf(content)
            except ValueError as e:
                return jsonify({"status": "error", "message": str(e)}), 400
        elif filename.lower().endswith(".txt"):
            resume_text = content.decode("utf-8", errors="ignore")
        else:
            return jsonify({"status": "error", "message": "Only PDF and TXT resume files are supported."}), 400
    else:
        # Check raw JSON payload
        data = request.get_json(silent=True) or {}
        resume_text = data.get("resume_text", "")
        filename = data.get("filename", "pasted_resume.txt")
        if not isinstance(resume_text, str) or not isinstance(filename, str):
            return jsonify({"status": "error", "message": "resume_text and filename must be strings."}), 400
        resume_text = resume_text.strip()
        if len(resume_text) > 100_000:
            return jsonify({"status": "error", "message": "Resume text exceeds maximum allowed length."}), 400

    if resume_text:
        resume_text = clean_pdf_extracted_text(resume_text)

    if not resume_text and not resume_bytes:
        return jsonify({"status": "error", "message": "No resume file or text content provided."}), 400

    memory = SupabaseMemory(token=token)

    # Perform AI Candidate Profile Extraction with responsive safety timeout (8.5s on Vercel to stay within 10s serverless limit, 35.0s standard)
    parsed_profile = None
    is_vercel = os.environ.get("VERCEL") == "1"
    extraction_timeout = 8.5 if is_vercel else 35.0
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
        parsed_profile = future.result(timeout=extraction_timeout)
    except Exception as e:
        logger.warning("AI profile extraction notice (%s), using smart local parser.", e)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if memory.is_configured:
        existing: dict[str, Any] = memory.get_user_profile(email, token=token) or {}
    else:
        existing = get_user_profile(cfg, email, token) or {}

    if not parsed_profile or not isinstance(parsed_profile, dict):
        # Fallback smart extraction from resume text if LLM unavailable or times out
        derived_name = ""
        derived_title = ""
        derived_edu, smart_grad_yr = parse_education_smart(resume_text) if resume_text else ("", None)

        if resume_text:
            lines = [line.strip() for line in resume_text.splitlines() if line.strip()]

            # 1. Check explicit name label
            name_pat = re.search(
                r"(?i)^(?:name|candidate(?:\s+name)?|full\s+name)\s*[:\-]\s*([A-Za-z\s\.\'-]{2,40})",
                resume_text,
                re.MULTILINE,
            )
            if name_pat:
                derived_name = sanitize_candidate_name(name_pat.group(1))

            # 2. Check top lines before major section headers (splitting contact delimiters like |, •, -, ,)
            if not derived_name:
                derived_name = sanitize_candidate_name(None, text_lines=lines)

            # 3. Check headline professional title
            title_keywords = [
                "Engineer", "Developer", "Architect", "Scientist", "Designer",
                "Specialist", "Analyst", "Lead", "Manager", "Consultant", "SDE",
                "Officer", "Director", "Executive", "Associate", "Representative",
                "Strategist", "Generalist", "Coordinator", "Counsel", "Partner",
            ]
            role_pat = re.search(
                r"(?i)^(?:title|designation|current\s+role|role)\s*[:\-]\s*([A-Za-z\s\.\'-]{3,50})",
                resume_text,
                re.MULTILINE,
            )
            if role_pat:
                clean_r = role_pat.group(1).strip("•-*| \t")
                if not any(term in clean_r.lower() for term in ("resume", "cv", "summary", "profile", "skills")):
                    derived_title = clean_r

            if not derived_title:
                for line in lines[:15]:
                    if any(tk.lower() in line.lower() for tk in title_keywords) and len(line) < 150:
                        segments = re.split(r"[|•·\t/]+", line)
                        for seg in segments:
                            clean_seg = seg.strip("•-*| \t()[]{}")
                            if any(tk.lower() in clean_seg.lower() for tk in title_keywords) and not re.search(r"[@:]", clean_seg) and len(clean_seg) < 60:
                                derived_title = clean_seg
                                break
                        if derived_title:
                            break
                        clean_line = line.split("|")[0].split("•")[0].split("-")[0].strip("•-*| \t")
                        if clean_line and any(tk.lower() in clean_line.lower() for tk in title_keywords):
                            derived_title = clean_line
                            break

        if not derived_name or len(derived_name) > 40:
            if existing.get("name") and existing["name"] != "Candidate":
                derived_name = existing["name"]
            else:
                derived_name = ""

        skills_list = _extract_skills_from_text(resume_text)[:25] if resume_text else []

        # Grounded timeline calculation for YoE
        derived_years = calculate_timeline_yoe(None, graduation_year=smart_grad_yr, resume_text=resume_text)
        is_student_or_fresher = bool(
            resume_text and re.search(r"(?i)\b(?:final[- ]year|student|undergraduate|fresher|pre[- ]final)\b", resume_text)
            and re.search(r"\b(202[5-9]|203\d)\b", resume_text)
        )
        if not is_student_or_fresher and derived_years == 0.0 and resume_text:
            yoe_match = re.search(
                r"(?i)(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:total\s+)?(?:experience|exp|industry\s+experience|work\s+experience|software\s+experience)",
                resume_text,
            )
            if yoe_match:
                try:
                    derived_years = float(yoe_match.group(1))
                except ValueError:
                    pass
            if derived_years == 0.0:
                yoe_match_2 = re.search(r"(?i)(?:total\s+)?(?:experience|exp):\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", resume_text)
                if yoe_match_2:
                    try:
                        derived_years = float(yoe_match_2.group(1))
                    except ValueError:
                        pass
        if not is_student_or_fresher and derived_years == 0.0 and (existing.get("experience_years") or existing.get("years_experience")):
            try:
                derived_years = float(existing.get("experience_years") or existing.get("years_experience") or 0.0)
            except (ValueError, TypeError):
                pass

        if is_student_or_fresher:
            derived_years = 0.0

        # Synthesize professional title and target titles (never leaving 'Student' or 'Fresher')
        derived_title, syn_targets = synthesize_headline_and_targets(
            derived_title, skills_list, yoe=derived_years, domains=existing.get("domains")
        )

        target_titles: list[str] = []
        if isinstance(existing.get("target_keywords"), list) and existing["target_keywords"]:
            target_titles.extend([t for t in existing["target_keywords"] if str(t).lower() not in {"student", "fresher", "intern", "candidate"}])
        elif isinstance(existing.get("target_titles"), list) and existing["target_titles"]:
            target_titles.extend([t for t in existing["target_titles"] if str(t).lower() not in {"student", "fresher", "intern", "candidate"}])

        if not target_titles:
            target_titles = syn_targets
        elif derived_title and derived_title not in target_titles:
            target_titles.insert(0, derived_title)

        if not derived_edu and existing.get("education"):
            derived_edu = existing.get("education") or ""

        if derived_years <= 0.0:
            derived_exp_level = "fresher"
            derived_seniority = "entry"
        elif derived_years < 1.0:
            derived_exp_level = "0-1"
            derived_seniority = "entry"
        elif derived_years < 3.0:
            derived_exp_level = "1-3"
            derived_seniority = "mid"
        elif derived_years < 5.0:
            derived_exp_level = "3-5"
            derived_seniority = "mid"
        else:
            derived_exp_level = "5+"
            derived_seniority = "senior"

        # Indian tech hub city detection from resume text
        detected_locations = detect_preferred_locations_smart(resume_text) if resume_text else []
        if not detected_locations and existing.get("preferred_locations"):
            detected_locations = [str(x).strip() for x in existing.get("preferred_locations", []) if str(x).strip()]

        if detected_locations:
            derived_loc_pref = "remote_only" if detected_locations == ["Remote"] else "specific_cities"
        else:
            derived_loc_pref = str(existing.get("location_preference") or "all_india")

        # Notice period detection
        derived_notice_period = "immediate" if derived_years <= 0.0 else "30_days"
        if resume_text:
            np_m = re.search(r"(?i)(?:notice\s*period|notice|availability|serving\s*notice|joining\s*time)\s*[:\-]?\s*([^\n,\.;]+)", resume_text)
            text_for_np = np_m.group(1).lower() if np_m else resume_text.lower()
            if any(k in text_for_np for k in ("immediate", "available immediately", "join immediately", "0 day", "zero day", "serving notice", "lwd")):
                derived_notice_period = "immediate"
            elif any(k in text_for_np for k in ("15 day", "2 week", "15d")):
                derived_notice_period = "15_days"
            elif any(k in text_for_np for k in ("60 day", "2 month", "60d")):
                derived_notice_period = "60_days"
            elif any(k in text_for_np for k in ("90 day", "3 month", "90d")):
                derived_notice_period = "90_days"
            elif any(k in text_for_np for k in ("30 day", "1 month", "30d")):
                derived_notice_period = "30_days"
            elif existing.get("notice_period"):
                derived_notice_period = str(existing["notice_period"])
        elif existing.get("notice_period"):
            derived_notice_period = str(existing["notice_period"])

        # Current & Expected CTC in LPA
        derived_current_ctc = 0.0
        derived_expected_ctc = 0.0
        if resume_text:
            c_ctc = re.search(r"(?i)(?:current\s*ctc|present\s*ctc|cctc|current\s*salary|current\s*fixed|fixed\s*ctc|current\s*pkg|current\s*package)\s*[:\-]?\s*(?:inr|rs\.?|₹)?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?|lacs?|l\b)?", resume_text)
            if c_ctc:
                try:
                    derived_current_ctc = float(c_ctc.group(1))
                except ValueError:
                    pass
            e_ctc = re.search(r"(?i)(?:expected\s*ctc|exp\s*ctc|ectc|expected\s*salary|expected\s*pkg|expected\s*package)\s*[:\-]?\s*(?:inr|rs\.?|₹)?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakhs?|lacs?|l\b)?", resume_text)
            if e_ctc:
                try:
                    derived_expected_ctc = float(e_ctc.group(1))
                except ValueError:
                    pass
        if derived_current_ctc == 0.0 and existing.get("current_ctc_lpa"):
            try:
                derived_current_ctc = float(existing["current_ctc_lpa"])
            except (ValueError, TypeError):
                pass
        if derived_expected_ctc == 0.0 and existing.get("expected_ctc_lpa"):
            try:
                derived_expected_ctc = float(existing["expected_ctc_lpa"])
            except (ValueError, TypeError):
                pass

        derived_projects = parse_projects_smart(resume_text) if resume_text else []
        derived_summary = parse_summary_smart(resume_text) if resume_text else ""
        derived_contacts = parse_contact_smart(resume_text) if resume_text else {}

        parsed_profile = {
            "name": derived_name or "",
            "title": derived_title or "Professional",
            "current_title": derived_title or "Professional",
            "years_experience": derived_years,
            "experience_years": derived_years,
            "graduation_year": smart_grad_yr,
            "education": derived_edu or "",
            "skills": skills_list,
            "core_skills": skills_list,
            "target_keywords": target_titles[:5],
            "target_titles": target_titles[:5],
            "domains": [derived_title] if derived_title else ["Professional"],
            "notable_projects": derived_projects,
            "summary": derived_summary,
            "profile_text": derived_summary,
            "email": derived_contacts.get("email") or email,
            "phone": derived_contacts.get("phone") or "",
            "github": derived_contacts.get("github") or "",
            "linkedin": derived_contacts.get("linkedin") or "",
            "seniority": derived_seniority,
            "experience_level": derived_exp_level,
            "preferred_locations": detected_locations,
            "location_preference": derived_loc_pref,
            "notice_period": derived_notice_period,
            "current_ctc_lpa": derived_current_ctc,
            "expected_ctc_lpa": derived_expected_ctc,
            "min_salary_lpa": derived_expected_ctc,
        }
    else:
        # Guarantee aliases on LLM parsed_profile as well
        if "core_skills" in parsed_profile and "skills" not in parsed_profile:
            parsed_profile["skills"] = parsed_profile["core_skills"]
        elif "skills" in parsed_profile and "core_skills" not in parsed_profile:
            parsed_profile["core_skills"] = parsed_profile["skills"]
        if "target_titles" in parsed_profile and "target_keywords" not in parsed_profile:
            parsed_profile["target_keywords"] = parsed_profile["target_titles"]
        elif "target_keywords" in parsed_profile and "target_titles" not in parsed_profile:
            parsed_profile["target_titles"] = parsed_profile["target_keywords"]
        if "current_title" in parsed_profile and "title" not in parsed_profile:
            parsed_profile["title"] = parsed_profile["current_title"]
        elif "title" in parsed_profile and "current_title" not in parsed_profile:
            parsed_profile["current_title"] = parsed_profile["title"]
        if "years_experience" in parsed_profile and "experience_years" not in parsed_profile:
            parsed_profile["experience_years"] = parsed_profile["years_experience"]
        elif "experience_years" in parsed_profile and "years_experience" not in parsed_profile:
            parsed_profile["years_experience"] = parsed_profile["experience_years"]

        # Ensure sanitized name
        s_name = sanitize_candidate_name(parsed_profile.get("name"), resume_text.splitlines() if resume_text else None)
        if s_name:
            parsed_profile["name"] = s_name

        # Ensure normalized skills
        if parsed_profile.get("skills"):
            parsed_profile["skills"] = normalize_technical_skills(parsed_profile["skills"])
            parsed_profile["core_skills"] = parsed_profile["skills"]

        # Ensure headline title and targets
        p_cur_title = str(parsed_profile.get("title") or parsed_profile.get("current_title") or "").strip()
        p_title, p_targets = synthesize_headline_and_targets(
            p_cur_title,
            parsed_profile.get("skills") or [],
            yoe=float(parsed_profile.get("experience_years") or 0.0),
            domains=parsed_profile.get("domains"),
        )
        parsed_profile["title"] = p_title
        parsed_profile["current_title"] = p_title

        existing_targets = parsed_profile.get("target_keywords") or parsed_profile.get("target_titles") or []
        if isinstance(existing_targets, str):
            existing_targets = [x.strip() for x in existing_targets.split(",") if x.strip()]
        clean_targets = [
            str(t).strip() for t in existing_targets
            if str(t).strip() and str(t).strip().lower() not in {"student", "fresher", "intern", "candidate"}
        ]
        if clean_targets:
            parsed_profile["target_keywords"] = clean_targets
            parsed_profile["target_titles"] = clean_targets
        else:
            parsed_profile["target_keywords"] = p_targets
            parsed_profile["target_titles"] = p_targets

        # Enrich any missing fields from smart local parser
        if resume_text:
            if not parsed_profile.get("education"):
                s_edu, s_yr = parse_education_smart(resume_text)
                if s_edu:
                    parsed_profile["education"] = s_edu
                if not parsed_profile.get("graduation_year") and s_yr:
                    parsed_profile["graduation_year"] = s_yr
            if not parsed_profile.get("notable_projects"):
                parsed_profile["notable_projects"] = parse_projects_smart(resume_text)
            if not parsed_profile.get("summary"):
                parsed_profile["summary"] = parse_summary_smart(resume_text)
                if not parsed_profile.get("profile_text"):
                    parsed_profile["profile_text"] = parsed_profile["summary"]
            c_contacts = parse_contact_smart(resume_text)
            for cf in ("email", "phone", "github", "linkedin"):
                if not parsed_profile.get(cf) and c_contacts.get(cf):
                    parsed_profile[cf] = c_contacts[cf]
            if not parsed_profile.get("preferred_locations"):
                parsed_profile["preferred_locations"] = detect_preferred_locations_smart(resume_text)

    # Extract existing notification preferences
    existing_notif = bool((existing or {}).get("email_notifications_enabled", False))
    existing_target_email = (existing or {}).get("notification_email") or parsed_profile.get("email") or email

    full_profile = {
        "email": email,
        "candidate_email": parsed_profile.get("email") or "",
        "name": parsed_profile.get("name") or (existing or {}).get("name") or "",
        "title": parsed_profile.get("title") or parsed_profile.get("current_title") or (existing or {}).get("title") or (existing or {}).get("current_title") or "",
        "current_title": parsed_profile.get("current_title") or parsed_profile.get("title") or (existing or {}).get("current_title") or (existing or {}).get("title") or "",
        "education": parsed_profile.get("education") or (existing or {}).get("education") or "",
        "graduation_year": parsed_profile.get("graduation_year") or (existing or {}).get("graduation_year") or None,
        "summary": parsed_profile.get("summary") or (existing or {}).get("summary") or "",
        "profile_text": parsed_profile.get("summary") or parsed_profile.get("profile_text") or (existing or {}).get("summary") or "",
        "notable_projects": parsed_profile.get("notable_projects") or (existing or {}).get("notable_projects") or [],
        "phone": parsed_profile.get("phone") or (existing or {}).get("phone") or "",
        "github": parsed_profile.get("github") or (existing or {}).get("github") or "",
        "linkedin": parsed_profile.get("linkedin") or (existing or {}).get("linkedin") or "",
        "experience_years": parsed_profile.get("experience_years") or parsed_profile.get("years_experience") or (existing or {}).get("experience_years") or (existing or {}).get("years_experience") or 0.0,
        "years_experience": parsed_profile.get("years_experience") or parsed_profile.get("experience_years") or (existing or {}).get("years_experience") or (existing or {}).get("experience_years") or 0.0,
        "skills": parsed_profile.get("skills") or parsed_profile.get("core_skills") or (existing or {}).get("skills") or (existing or {}).get("core_skills") or [],
        "core_skills": parsed_profile.get("core_skills") or parsed_profile.get("skills") or (existing or {}).get("core_skills") or (existing or {}).get("skills") or [],
        "target_keywords": parsed_profile.get("target_keywords") or parsed_profile.get("target_titles") or (existing or {}).get("target_keywords") or (existing or {}).get("target_titles") or [],
        "target_titles": parsed_profile.get("target_titles") or parsed_profile.get("target_keywords") or (existing or {}).get("target_titles") or (existing or {}).get("target_keywords") or [],
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
        "seniority": parsed_profile.get("seniority") or (existing or {}).get("seniority") or "",
        "notice_period": parsed_profile.get("notice_period") or (existing or {}).get("notice_period") or "30_days",
        "current_ctc_lpa": parsed_profile.get("current_ctc_lpa") if parsed_profile.get("current_ctc_lpa") is not None else ((existing or {}).get("current_ctc_lpa") or 0.0),
        "expected_ctc_lpa": parsed_profile.get("expected_ctc_lpa") if parsed_profile.get("expected_ctc_lpa") is not None else ((existing or {}).get("expected_ctc_lpa") or 0.0),
        "min_salary_lpa": parsed_profile.get("min_salary_lpa") if parsed_profile.get("min_salary_lpa") is not None else ((existing or {}).get("min_salary_lpa") or 0.0),
        "preferred_sectors": (existing or {}).get("preferred_sectors") or [],
        "profile_json": parsed_profile,
    }

    return jsonify(
        {
            "status": "success",
            "message": "Resume text successfully extracted. You can review and alter your text context before saving.",
            "resume_text": resume_text,
            "profile": sanitize_profile_for_response(full_profile),
            "parsed_profile": sanitize_profile_for_response(parsed_profile),
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
            profile = create_blank_profile(email or "") if memory.is_configured else get_user_profile(cfg, email, token)

        return jsonify({"status": "success", "preferences": _extract_preferences_view(profile, include_keywords=True)})

    elif request.method == "POST":
        data = request.get_json(silent=True) or {}
        if not email:
            return jsonify({"status": "error", "message": "Authentication required."}), 400

        # Merge with existing profile while preserving ownership and real onboarding state
        if memory.is_configured:
            existing = memory.get_user_profile(email, token=token) or create_blank_profile(email)
        else:
            existing = get_user_profile(cfg, email, token) or create_blank_profile(email)
        merged = {**(existing or {}), **data, "email": email}
        merged.pop("id", None)
        merged["experience_level"] = str(merged.get("experience_level") or "").strip()[:30]
        merged["notice_period"] = str(merged.get("notice_period") or "30_days").strip()[:30]
        _normalize_preference_fields(
            merged,
            list_fields=("job_types", "preferred_sectors", "target_keywords", "exclude_keywords"),
        )
        merged["target_titles"] = list(merged.get("target_keywords") or [])
        merged["onboarding_completed"] = is_profile_complete(merged)
        _strip_sensitive_fields(merged)

        persist_err = _persist_profile_state(
            memory,
            cfg,
            email,
            token,
            merged,
            cloud_error_message="Preferences could not be saved securely. Please try again.",
        )
        if persist_err is not None:
            return persist_err

        return jsonify(
            {
                "status": "success",
                "message": "Search preferences updated successfully.",
                "preferences": _extract_preferences_view(merged, include_keywords=False),
            }
        )
