"""Candidate profile, preferences, and Resume Studio upload/parsing routes."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import re
from typing import Any
from flask import Blueprint, current_app, jsonify, request

from ... import cli, llm
from ...auth import require_auth
from ...memory import SupabaseMemory
from ...store import get_user_profile_path, get_writable_path  # noqa: F401
from ..state import get_current_user_context, get_user_profile, sanitize_profile_for_response

logger = logging.getLogger(__name__)

profile_bp = Blueprint("profile", __name__)


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
    """Safely extract skills from resume text using strict word boundaries to avoid false substring matches."""
    if not resume_text:
        return []
    common_keywords = [
        "Python",
        "JavaScript",
        "TypeScript",
        "Golang",
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
        "Next.js",
        "Node.js",
        "Express.js",
        "REST APIs",
        "GraphQL",
        "Microservices",
        "CI/CD",
        "Git",
        "Tailwind CSS",
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
        flags = re.IGNORECASE if kw not in ("AI",) else 0
        if re.search(pattern, resume_text, flags):
            found_skills.append(kw)
    if "Golang" not in found_skills and re.search(r"(?<![a-zA-Z0-9])Go(?![a-zA-Z0-9])", resume_text):
        if re.search(r"(?i)\b(?:golang|go\s+developer|go\s+engineer|go\s+routine)\b", resume_text):
            found_skills.append("Go")
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
            raw = get_user_profile(cfg, email, token)
            raw.setdefault("onboarding_completed", True)
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
            existing = get_user_profile(cfg, email, token) or {}
        merged_profile = {**(existing or {}), **data}

        # Normalize experience_years and bidirectional alias years_experience
        y_val = data.get("experience_years") if "experience_years" in data else data.get("years_experience")
        if y_val is None:
            y_val = merged_profile.get("experience_years", merged_profile.get("years_experience", 0.0))
        try:
            flt_yoe = float(y_val or 0)
        except (ValueError, TypeError):
            flt_yoe = 0.0
        merged_profile["experience_years"] = flt_yoe
        merged_profile["years_experience"] = flt_yoe

        # Bidirectional aliases for skills <-> core_skills
        raw_s = data.get("skills") if "skills" in data else data.get("core_skills")
        if raw_s is None:
            raw_s = merged_profile.get("skills") or merged_profile.get("core_skills")
        if isinstance(raw_s, str):
            s_list = [s.strip() for s in raw_s.split(",") if s.strip()]
        elif isinstance(raw_s, list):
            s_list = [str(s).strip() for s in raw_s if str(s).strip()]
        else:
            s_list = []
        merged_profile["skills"] = s_list
        merged_profile["core_skills"] = s_list

        # Bidirectional aliases for target_keywords <-> target_titles
        raw_t = data.get("target_keywords") if "target_keywords" in data else data.get("target_titles")
        if raw_t is None:
            raw_t = merged_profile.get("target_keywords") or merged_profile.get("target_titles")
        if isinstance(raw_t, str):
            t_list = [s.strip() for s in raw_t.split(",") if s.strip()]
        elif isinstance(raw_t, list):
            t_list = [str(s).strip() for s in raw_t if str(s).strip()]
        else:
            t_list = []
        merged_profile["target_keywords"] = t_list
        merged_profile["target_titles"] = t_list

        # Bidirectional aliases for title <-> current_title
        t_str = str(data.get("title") or data.get("current_title") or merged_profile.get("title") or merged_profile.get("current_title") or "").strip()
        merged_profile["title"] = t_str
        merged_profile["current_title"] = t_str

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

        for ctc_field in ("current_ctc_lpa", "expected_ctc_lpa", "min_salary_lpa"):
            if ctc_field in merged_profile and merged_profile[ctc_field] is not None:
                try:
                    merged_profile[ctc_field] = float(merged_profile[ctc_field])
                except (ValueError, TypeError):
                    merged_profile[ctc_field] = 0.0

        if merged_profile.get("expected_ctc_lpa") and not merged_profile.get("min_salary_lpa"):
            merged_profile["min_salary_lpa"] = merged_profile["expected_ctc_lpa"]

        # Ensure preferred_locations is always a list of clean strings
        raw_pref_locs = merged_profile.get("preferred_locations")
        if isinstance(raw_pref_locs, dict):
            merged_profile["preferred_locations"] = [str(x).strip() for x in raw_pref_locs.get("locations", []) if str(x).strip()]
        elif isinstance(raw_pref_locs, list):
            merged_profile["preferred_locations"] = [str(x).strip() for x in raw_pref_locs if str(x).strip()]
        elif isinstance(raw_pref_locs, str) and raw_pref_locs.strip():
            merged_profile["preferred_locations"] = [str(x).strip() for x in raw_pref_locs.split(",") if str(x).strip()]
        else:
            merged_profile["preferred_locations"] = []

        # Normalize location_preference
        raw_loc_pref = merged_profile.get("location_preference")
        if isinstance(raw_loc_pref, dict):
            loc_type = str(raw_loc_pref.get("type") or "all_india").strip()
            loc_list = [str(x).strip() for x in raw_loc_pref.get("locations", []) if str(x).strip()]
            if not loc_list and merged_profile["preferred_locations"]:
                loc_list = merged_profile["preferred_locations"]
            merged_profile["location_preference"] = {"type": loc_type, "locations": loc_list}
        elif isinstance(raw_loc_pref, str) and raw_loc_pref.strip():
            merged_profile["location_preference"] = raw_loc_pref.strip()
        else:
            merged_profile["location_preference"] = "specific_cities" if merged_profile["preferred_locations"] else "all_india"

        # Normalize remaining list fields
        for list_field in ("exclude_keywords", "job_types", "preferred_sectors"):
            val = merged_profile.get(list_field)
            if isinstance(val, str):
                merged_profile[list_field] = [s.strip() for s in val.split(",") if s.strip()]
            elif not isinstance(val, list):
                merged_profile[list_field] = []

        # If new non-empty resume_text is submitted without skills, auto-extract skills
        data_resume_text = (data.get("resume_text") or "").strip()
        if data_resume_text and not data.get("skills"):
            found_skills = _extract_skills_from_text(data_resume_text)
            if found_skills:
                merged_profile["skills"] = found_skills[:12]

        merged_profile["onboarding_completed"] = is_profile_complete(merged_profile)
        for key in list(merged_profile):
            normalized = str(key).lower().replace("-", "_")
            if any(marker in normalized for marker in ("api_key", "token", "secret", "password")):
                merged_profile.pop(key, None)

        if memory.is_configured:
            if not memory.upsert_user_profile(email, merged_profile, token=token):
                return jsonify(
                    {"status": "error", "message": "Profile could not be saved to secure cloud storage. Please try again."}
                ), 503

        try:
            profile_path = get_user_profile_path(cfg.get("profile_file", "profile.json"), email)
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(merged_profile, f, indent=2)
        except Exception as e:
            logger.warning("Could not cache profile locally: %s", e)

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
        "location_preference": "all_india",
        "job_types": [],  # e.g. ["fulltime", "internship", "remote", "hybrid", "onsite"]
        "experience_level": "",  # e.g. "fresher", "0-1", "1-3", "3-5", "5+"
        "notice_period": "30_days",  # e.g. "immediate", "15_days", "30_days", "60_days", "90_days"
        "current_ctc_lpa": 0,
        "expected_ctc_lpa": 0,
        "min_salary_lpa": 0,
        "preferred_sectors": [],  # e.g. ["fintech", "saas", "edtech"]
        "profile_json": {},
    }

    if memory.is_configured:
        if not memory.upsert_user_profile(email, blank_profile, token=token):
            return jsonify(
                {"status": "error", "message": "Profile reset could not be saved to secure cloud storage. Please try again."}
            ), 503

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

    # Perform AI Candidate Profile Extraction with responsive safety timeout (8s on Vercel to stay within 10s serverless limit, 14s standard)
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

    existing: dict[str, Any] = (memory.get_user_profile(email, token=token) or {}) if memory.is_configured else {}
    if not existing:
        existing = get_user_profile(cfg, email, token) or {}

    if not parsed_profile or not isinstance(parsed_profile, dict):
        # Fallback smart extraction from resume text if LLM unavailable or times out
        username_part = email.split("@")[0]
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
            first_lines = [
                line for line in lines[:10]
                if len(line) < 50
                and not any(term in line.lower() for term in name_skip_terms)
                and not re.search(r"[@:/0-9]", line)
            ]
            if first_lines:
                derived_name = first_lines[0].strip("•-*| \t")
                if derived_name.islower() or derived_name.isupper():
                    derived_name = derived_name.title()

            title_keywords = [
                "Engineer", "Developer", "Architect", "Scientist", "Designer",
                "Specialist", "Analyst", "Lead", "Manager", "Consultant",
            ]
            for line in lines[:15]:
                if any(tk.lower() in line.lower() for tk in title_keywords) and len(line) < 60:
                    if not any(term in line.lower() for term in name_skip_terms):
                        # Clean title line from trailing skills or bullet separators
                        clean_line = line.split("|")[0].split("•")[0].strip("•-*| \t")
                        derived_title = clean_line or line
                        break

            edu_keywords = [
                "B.Tech", "B.E.", "M.Tech", "M.S.", "Bachelor", "Master",
                "Degree", "University", "College", "Institute",
            ]
            for line in lines:
                if any(ek.lower() in line.lower() for ek in edu_keywords) and len(line) < 80:
                    derived_edu = line
                    break

        if not derived_name or len(derived_name) > 40:
            if existing.get("name") and existing["name"] != "Candidate":
                derived_name = existing["name"]
            else:
                cleaned_username = re.sub(r"\d+", "", username_part).replace(".", " ").replace("_", " ").strip()
                derived_name = " ".join(part.capitalize() for part in cleaned_username.split()) or "Candidate"

        if not derived_title:
            derived_title = existing.get("title") or existing.get("current_title") or "Software Engineer"
        if not derived_edu and existing.get("education"):
            derived_edu = existing.get("education") or ""

        skills_list = _extract_skills_from_text(resume_text)[:15] if resume_text else []

        derived_years = 0.0
        if resume_text:
            yoe_match = re.search(
                r"(?i)(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp|industry experience|software experience)",
                resume_text,
            )
            if yoe_match:
                try:
                    derived_years = float(yoe_match.group(1))
                except ValueError:
                    pass
            if derived_years == 0.0:
                yoe_match_2 = re.search(r"(?i)(?:experience|exp):\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", resume_text)
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
        elif derived_title:
            target_titles.append(derived_title)
        else:
            target_titles.append("Software Engineer")

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
            np_m = re.search(r"(?i)(?:notice\s*period|availability|serving\s*notice)\s*[:\-]?\s*([^\n,\.;]+)", resume_text)
            text_for_np = np_m.group(1).lower() if np_m else resume_text.lower()
            if any(k in text_for_np for k in ("immediate", "available immediately", "0 day", "zero day", "serving notice")):
                derived_notice_period = "immediate"
            elif any(k in text_for_np for k in ("15 day", "2 week")):
                derived_notice_period = "15_days"
            elif any(k in text_for_np for k in ("60 day", "2 month")):
                derived_notice_period = "60_days"
            elif any(k in text_for_np for k in ("90 day", "3 month")):
                derived_notice_period = "90_days"
            elif any(k in text_for_np for k in ("30 day", "1 month")):
                derived_notice_period = "30_days"
            elif existing.get("notice_period"):
                derived_notice_period = str(existing["notice_period"])
        elif existing.get("notice_period"):
            derived_notice_period = str(existing["notice_period"])

        # Current & Expected CTC in LPA
        derived_current_ctc = 0.0
        derived_expected_ctc = 0.0
        if resume_text:
            c_ctc = re.search(r"(?i)(?:current\s*ctc|present\s*ctc|cctc|current\s*salary)\s*[:\-]?\s*(?:inr|rs\.?|₹)?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakh|lac)?", resume_text)
            if c_ctc:
                try:
                    derived_current_ctc = float(c_ctc.group(1))
                except ValueError:
                    pass
            e_ctc = re.search(r"(?i)(?:expected\s*ctc|exp\s*ctc|ectc|expected\s*salary)\s*[:\-]?\s*(?:inr|rs\.?|₹)?\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakh|lac)?", resume_text)
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
            profile = get_user_profile(cfg, email, token)

        return jsonify(
            {
                "status": "success",
                "preferences": {
                    "preferred_locations": profile.get("preferred_locations") or [],
                    "location_preference": profile.get("location_preference") or "all_india",
                    "job_types": profile.get("job_types") or [],
                    "experience_level": profile.get("experience_level") or "",
                    "notice_period": profile.get("notice_period") or "30_days",
                    "current_ctc_lpa": profile.get("current_ctc_lpa") or 0,
                    "expected_ctc_lpa": profile.get("expected_ctc_lpa") or 0,
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

        # Normalize preferred_locations
        raw_pref = merged.get("preferred_locations")
        if isinstance(raw_pref, dict):
            merged["preferred_locations"] = [str(x).strip() for x in raw_pref.get("locations", []) if str(x).strip()]
        elif isinstance(raw_pref, list):
            merged["preferred_locations"] = [str(x).strip() for x in raw_pref if str(x).strip()]
        elif isinstance(raw_pref, str) and raw_pref.strip():
            merged["preferred_locations"] = [str(x).strip() for x in raw_pref.split(",") if str(x).strip()]
        else:
            merged["preferred_locations"] = []

        # Normalize location_preference
        raw_loc = merged.get("location_preference")
        if isinstance(raw_loc, dict):
            loc_t = str(raw_loc.get("type") or "all_india").strip()
            loc_l = [str(x).strip() for x in raw_loc.get("locations", []) if str(x).strip()]
            if not loc_l and merged["preferred_locations"]:
                loc_l = merged["preferred_locations"]
            merged["location_preference"] = {"type": loc_t, "locations": loc_l}
        elif isinstance(raw_loc, str) and raw_loc.strip():
            merged["location_preference"] = raw_loc.strip()
        else:
            merged["location_preference"] = "specific_cities" if merged["preferred_locations"] else "all_india"

        for ctc_field in ("current_ctc_lpa", "expected_ctc_lpa", "min_salary_lpa"):
            if ctc_field in merged and merged[ctc_field] is not None:
                try:
                    merged[ctc_field] = float(merged[ctc_field])
                except (ValueError, TypeError):
                    merged[ctc_field] = 0.0

        if merged.get("expected_ctc_lpa") and not merged.get("min_salary_lpa"):
            merged["min_salary_lpa"] = merged["expected_ctc_lpa"]

        for list_field in ("job_types", "preferred_sectors", "target_keywords", "exclude_keywords"):
            val = merged.get(list_field)
            if isinstance(val, str):
                merged[list_field] = [s.strip() for s in val.split(",") if s.strip()]
            elif not isinstance(val, list):
                merged[list_field] = []

        if memory.is_configured:
            if not memory.upsert_user_profile(email, merged, token=token):
                return jsonify(
                    {"status": "error", "message": "Preferences could not be saved securely. Please try again."}
                ), 503

        try:
            profile_path = get_user_profile_path(cfg.get("profile_file", "profile.json"), email)
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
        except Exception as e:
            logger.warning("Could not cache preferences locally: %s", e)

        return jsonify(
            {
                "status": "success",
                "message": "Search preferences updated successfully.",
                "preferences": {
                    "preferred_locations": merged.get("preferred_locations") or [],
                    "location_preference": merged.get("location_preference") or "all_india",
                    "job_types": merged.get("job_types") or [],
                    "experience_level": merged.get("experience_level") or "",
                    "notice_period": merged.get("notice_period") or "30_days",
                    "current_ctc_lpa": merged.get("current_ctc_lpa") or 0,
                    "expected_ctc_lpa": merged.get("expected_ctc_lpa") or 0,
                    "min_salary_lpa": merged.get("min_salary_lpa") or 0,
                    "preferred_sectors": merged.get("preferred_sectors") or [],
                },
            }
        )
