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
        # Split by category headers, commas, bullets, pipes, or newlines
        cleaned_lines = []
        for line in sec_text.splitlines():
            line_str = re.sub(r"(?i)^[a-z\s]+:\s*", "", line.strip())  # remove e.g. "Languages: ", "Frameworks: "
            if line_str:
                cleaned_lines.append(line_str)
        tokens = re.split(r"[,•·|\t\n;/]+", " ".join(cleaned_lines))
        for tok in tokens:
            cleaned = tok.strip("•-*| \t()[]{}")
            if 1 < len(cleaned) <= 25 and not re.search(r"[@:/0-9]", cleaned):
                # Only add if it looks like a clean tech term (starts with letter)
                if re.match(r"^[A-Za-z][A-Za-z0-9#\+\.\-\s]{0,24}$", cleaned):
                    # Filter out non-technical noise words
                    skip_words = {"proficient", "familiar", "basics", "strong", "advanced", "intermediate", "tools", "languages", "frameworks", "databases"}
                    if cleaned.lower() not in skip_words:
                        add_skill(cleaned)

    # 2. Comprehensive catalog of 100+ modern engineering and tech stack keywords
    common_keywords = [
        "Python", "JavaScript", "TypeScript", "Golang", "Java", "C++", "C#", "Rust", "Ruby", "PHP", "Swift", "Kotlin", "Scala", "SQL",
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "SQLite", "Cassandra", "DynamoDB", "Firebase", "Firestore",
        "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Terraform", "Linux", "Git", "GitHub Actions", "CI/CD",
        "FastAPI", "Flask", "Django", "React", "Next.js", "Node.js", "Express.js", "NestJS", "Spring Boot", "ASP.NET", "Vue.js", "Angular", "Svelte",
        "REST APIs", "GraphQL", "gRPC", "Microservices", "Celery", "Kafka", "RabbitMQ", "WebSockets", "Prisma", "SQLAlchemy",
        "Tailwind CSS", "Redux", "Bootstrap", "HTML", "CSS", "Bash", "Shell",
        "Jest", "Playwright", "Pytest", "Selenium", "Cypress", "Postman",
        "Distributed Systems", "System Design", "OOP", "Data Structures", "Algorithms",
        "AI", "LLM", "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "PyTorch", "TensorFlow", "scikit-learn", "Pandas", "NumPy", "LangChain", "HuggingFace", "RAG",
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
            inferred = [cur]
            if "backend" in cur.lower():
                inferred.extend(["Software Engineer", "Backend Developer", "Full Stack Developer"])
            elif "frontend" in cur.lower():
                inferred.extend(["Frontend Engineer", "React Developer", "Software Engineer"])
            elif "ai" in cur.lower() or "ml" in cur.lower():
                inferred.extend(["Machine Learning Engineer", "Python Developer", "Data Scientist"])
            else:
                inferred.extend(["Software Engineer", "Backend Developer", "Full Stack Developer"])
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

        if not merged_profile.get("exclude_keywords"):
            merged_profile["exclude_keywords"] = ["Manager", "Director", "Sales", "Recruiter", "VP"]

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

    if not resume_text and not resume_bytes:
        return jsonify({"status": "error", "message": "No resume file or text content provided."}), 400

    memory = SupabaseMemory(token=token)

    # Perform AI Candidate Profile Extraction with responsive safety timeout (8.0s on Vercel to stay within 10s serverless limit, 14.0s standard)
    parsed_profile = None
    is_vercel = os.environ.get("VERCEL") == "1"
    extraction_timeout = 8.0 if is_vercel else 14.0
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
        derived_edu = ""
        if resume_text:
            lines = [line.strip() for line in resume_text.splitlines() if line.strip()]
            name_skip_terms = {
                "resume", "curriculum vitae", "cv", "portfolio", "github", "linkedin",
                "contact", "email", "phone", "summary", "professional summary",
                "executive summary", "objective", "career objective", "about me",
                "profile", "personal profile", "experience", "work experience",
                "skills", "technical skills", "education", "projects", "certifications",
            }

            # 1. Check explicit name label
            name_pat = re.search(
                r"(?i)^(?:name|candidate(?:\s+name)?|full\s+name)\s*[:\-]\s*([A-Za-z\s\.\'-]{2,40})",
                resume_text,
                re.MULTILINE,
            )
            if name_pat:
                cand = name_pat.group(1).strip("•-*| \t")
                if not any(term in cand.lower() for term in name_skip_terms):
                    derived_name = cand.title()

            # 2. Check top lines before major section headers (splitting contact delimiters like |, •, -, ,)
            if not derived_name:
                for line in lines[:8]:
                    if any(term in line.lower() for term in name_skip_terms):
                        continue
                    segments = re.split(r"[|•·,\t/]+", line)
                    for seg in segments:
                        clean_seg = seg.strip("•-*| \t()[]{}")
                        if 2 <= len(clean_seg) <= 35 and not re.search(r"[@:/0-9]", clean_seg):
                            if not any(term in clean_seg.lower() for term in name_skip_terms):
                                words = clean_seg.split()
                                if 1 <= len(words) <= 4:
                                    derived_name = clean_seg.title() if (clean_seg.islower() or clean_seg.isupper()) else clean_seg
                                    break
                    if derived_name:
                        break

            # 3. Check headline professional title
            title_keywords = [
                "Engineer", "Developer", "Architect", "Scientist", "Designer",
                "Specialist", "Analyst", "Lead", "Manager", "Consultant", "SDE",
            ]
            role_pat = re.search(
                r"(?i)^(?:title|designation|current\s+role|role)\s*[:\-]\s*([A-Za-z\s\.\'-]{3,50})",
                resume_text,
                re.MULTILINE,
            )
            if role_pat:
                clean_r = role_pat.group(1).strip("•-*| \t")
                if not any(term in clean_r.lower() for term in name_skip_terms):
                    derived_title = clean_r

            if not derived_title:
                for line in lines[:15]:
                    if any(tk.lower() in line.lower() for tk in title_keywords) and len(line) < 150:
                        if not any(term in line.lower() for term in name_skip_terms):
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

            edu_keywords = [
                "B.Tech", "B.E.", "M.Tech", "M.S.", "Bachelor", "Master",
                "Degree", "University", "College", "Institute", "BCA", "MCA", "B.Sc", "M.Sc",
            ]
            for line in lines:
                if any(ek.lower() in line.lower() for ek in edu_keywords) and len(line) < 80:
                    derived_edu = line
                    break

        if not derived_name or len(derived_name) > 40:
            if existing.get("name") and existing["name"] != "Candidate":
                derived_name = existing["name"]
            else:
                derived_name = ""

        skills_list = _extract_skills_from_text(resume_text)[:15] if resume_text else []

        if not derived_title or derived_title.lower() in {"student", "fresher", "intern", "candidate", "b.tech student"}:
            skills_lower = [s.lower() for s in skills_list]
            if any(k in skills_lower for k in ("react", "vue", "angular", "next.js", "frontend", "html", "css")) and not any(k in skills_lower for k in ("django", "fastapi", "spring", "golang")):
                derived_title = "Frontend Developer"
            elif any(k in skills_lower for k in ("python", "fastapi", "django", "golang", "go", "java", "sql", "backend", "postgresql")):
                derived_title = "Backend Engineer"
            elif any(k in skills_lower for k in ("pytorch", "tensorflow", "machine learning", "deep learning", "ai", "llm")):
                derived_title = "AI/ML Engineer"
            else:
                derived_title = existing.get("title") or existing.get("current_title") or "Software Engineer"

        if not derived_edu and existing.get("education"):
            derived_edu = existing.get("education") or ""

        derived_years = 0.0
        if resume_text:
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
        if derived_years == 0.0 and (existing.get("experience_years") or existing.get("years_experience")):
            try:
                derived_years = float(existing.get("experience_years") or existing.get("years_experience") or 0.0)
            except (ValueError, TypeError):
                pass

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

        target_titles: list[str] = []
        if isinstance(existing.get("target_keywords"), list) and existing["target_keywords"]:
            target_titles.extend(existing["target_keywords"])
        elif isinstance(existing.get("target_titles"), list) and existing["target_titles"]:
            target_titles.extend(existing["target_titles"])

        if derived_title and derived_title not in target_titles:
            target_titles.append(derived_title)

        # Supplement high-signal target titles tailored to specialization
        tl_lower = [t.lower() for t in target_titles]
        if "backend" in derived_title.lower():
            for t in ["Backend Engineer", "Software Engineer", "Python Developer", "Full Stack Developer", "Software Development Engineer"]:
                if t.lower() not in tl_lower and len(target_titles) < 5:
                    target_titles.append(t)
                    tl_lower.append(t.lower())
        elif "frontend" in derived_title.lower():
            for t in ["Frontend Engineer", "React Developer", "Software Engineer", "UI Engineer", "Full Stack Developer"]:
                if t.lower() not in tl_lower and len(target_titles) < 5:
                    target_titles.append(t)
                    tl_lower.append(t.lower())
        elif "full" in derived_title.lower():
            for t in ["Full Stack Developer", "Software Engineer", "Backend Engineer", "Frontend Engineer", "Full Stack Engineer"]:
                if t.lower() not in tl_lower and len(target_titles) < 5:
                    target_titles.append(t)
                    tl_lower.append(t.lower())
        elif "ai" in derived_title.lower() or "ml" in derived_title.lower():
            for t in ["AI/ML Engineer", "Machine Learning Engineer", "Python Developer", "Data Scientist", "Software Engineer"]:
                if t.lower() not in tl_lower and len(target_titles) < 5:
                    target_titles.append(t)
                    tl_lower.append(t.lower())
        else:
            for t in ["Software Engineer", "Backend Developer", "Full Stack Developer", "Software Development Engineer", "SDE"]:
                if t.lower() not in tl_lower and len(target_titles) < 5:
                    target_titles.append(t)
                    tl_lower.append(t.lower())

        # Indian tech hub city detection from resume text
        detected_locations: list[str] = []
        if resume_text:
            hub_patterns = {
                "Bengaluru": [r"\bbengaluru\b", r"\bbangalore\b", r"\bblr\b"],
                "Hyderabad": [r"\bhyderabad\b", r"\bhyd\b"],
                "Pune": [r"\bpune\b"],
                "Delhi-NCR": [r"\bdelhi\b", r"\bgurgaon\b", r"\bgurugram\b", r"\bnoida\b", r"\bncr\b"],
                "Mumbai": [r"\bmumbai\b", r"\bbombay\b"],
                "Chennai": [r"\bchennai\b", r"\bmadras\b"],
                "Remote": [r"\bremote\b", r"\bwork from home\b", r"\bwfh\b"],
            }
            rt_lower = resume_text.lower()
            for hub_name, patterns in hub_patterns.items():
                if any(re.search(pat, rt_lower) for pat in patterns):
                    if hub_name not in detected_locations:
                        detected_locations.append(hub_name)
        if not detected_locations and existing.get("preferred_locations"):
            detected_locations = [str(x).strip() for x in existing.get("preferred_locations", []) if str(x).strip()]

        if detected_locations:
            derived_loc_pref = "remote_only" if detected_locations == ["Remote"] else "specific_cities"
        else:
            derived_loc_pref = str(existing.get("location_preference") or "all_india")

        # Notice period detection
        derived_notice_period = "30_days"
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

        parsed_profile = {
            "name": derived_name or "",
            "title": derived_title or "Software Engineer",
            "current_title": derived_title or "Software Engineer",
            "years_experience": derived_years,
            "experience_years": derived_years,
            "education": derived_edu or "",
            "skills": skills_list,
            "core_skills": skills_list,
            "target_keywords": target_titles[:5],
            "target_titles": target_titles[:5],
            "domains": ["Software Engineering"],
            "notable_projects": [],
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

    # Extract existing notification preferences
    existing_notif = bool((existing or {}).get("email_notifications_enabled", False))
    existing_target_email = (existing or {}).get("notification_email") or email

    full_profile = {
        "email": email,
        "name": parsed_profile.get("name") or (existing or {}).get("name") or "",
        "title": parsed_profile.get("title") or parsed_profile.get("current_title") or (existing or {}).get("title") or (existing or {}).get("current_title") or "",
        "current_title": parsed_profile.get("current_title") or parsed_profile.get("title") or (existing or {}).get("current_title") or (existing or {}).get("title") or "",
        "education": parsed_profile.get("education") or (existing or {}).get("education") or "",
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
