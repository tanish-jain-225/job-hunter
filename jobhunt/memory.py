"""Supabase PostgreSQL Multi-Tenant Memory & State Management Module for Job Hunter.

Provides persistent per-user storage keyed on the authenticated user's email:
- User candidate profile, uploaded resume text, & search preferences (`user_profiles`)
- Email notification preferences and toggle switches
- Tracked jobs, fit scores, application kits, & applied states (`user_tracked_jobs`)
- Pipeline execution logs & run history (`user_pipeline_runs`)

Utilizes PostgREST REST API over HTTPS with strict tenant isolation and local caching.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from .auth import get_supabase_config


class SupabaseMemory:
    """Supabase PostgreSQL client managing persistent user memory and strict tenant isolation."""

    def __init__(self, token: Optional[str] = None):
        cfg = get_supabase_config()
        self.url = cfg.get("supabase_url", "").rstrip("/")
        self.anon_key = cfg.get("supabase_anon_key", "")
        self.service_key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        self.token = token
        self.timeout = 7.0

    @property
    def is_configured(self) -> bool:
        """Check if Supabase endpoint credentials are validly configured."""
        return bool(self.url and (self.anon_key or self.service_key))

    def _headers(self, token: Optional[str] = None) -> Dict[str, str]:
        """Build authorized PostgREST HTTP headers."""
        active_token = token or self.token
        key = self.service_key or self.anon_key
        auth_val = f"Bearer {active_token}" if active_token else f"Bearer {key}"
        return {
            "apikey": key,
            "Authorization": auth_val,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates",
        }

    # --------------------------------------------------------------------------
    # 1. User Profiles & Candidate Studio Memory
    # --------------------------------------------------------------------------
    def get_user_profile(self, email: str, token: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve user candidate profile, resume, and preferences from Supabase."""
        if not self.is_configured or not email:
            return None

        clean_email = email.lower().strip()
        try:
            endpoint = f"{self.url}/rest/v1/user_profiles"
            params = {"email": f"eq.{clean_email}", "select": "*"}
            resp = requests.get(endpoint, headers=self._headers(token), params=params, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    row = data[0]
                    pjson = row.get("profile_json") or {}
                    if not isinstance(pjson, dict):
                        pjson = {}
                    return {
                        **pjson,
                        **row,
                        "resume_text": row.get("resume_text") or pjson.get("resume_text") or "",
                        "resume_filename": row.get("resume_filename") or pjson.get("resume_filename") or "",
                        "email_notifications_enabled": bool(row.get("email_notifications_enabled", pjson.get("email_notifications_enabled", False))),
                        "notification_email": row.get("notification_email") or pjson.get("notification_email") or clean_email,
                        "min_score_notification": float(row.get("min_score_notification") or pjson.get("min_score_notification") or 7.5),
                        "onboarding_completed": bool(row.get("onboarding_completed", pjson.get("onboarding_completed", False))),
                        "name": row.get("name") or pjson.get("name") or "",
                        "title": row.get("title") or row.get("current_title") or pjson.get("title") or pjson.get("current_title") or "",
                        "skills": row.get("skills") or pjson.get("skills") or pjson.get("core_skills") or [],
                        "target_keywords": row.get("target_keywords") or pjson.get("target_keywords") or pjson.get("target_titles") or [],
                        "exclude_keywords": row.get("exclude_keywords") or pjson.get("exclude_keywords") or [],
                    }
            return None
        except Exception as e:
            print(f"[SupabaseMemory] get_user_profile error for {clean_email}: {e}")
            return None

    def upsert_user_profile(self, email: str, profile: Dict[str, Any], token: Optional[str] = None) -> bool:
        """Upsert candidate profile, uploaded resume text, and notification preferences in Supabase."""
        if not self.is_configured or not email:
            return False

        clean_email = email.lower().strip()

        raw_skills = profile.get("skills") or profile.get("core_skills") or []
        if isinstance(raw_skills, str):
            skills_list = [s.strip() for s in raw_skills.split(",") if s.strip()]
        elif isinstance(raw_skills, list):
            skills_list = [str(s).strip() for s in raw_skills if str(s).strip()]
        else:
            skills_list = []

        raw_targets = profile.get("target_keywords") or profile.get("target_titles") or []
        if isinstance(raw_targets, str):
            targets_list = [s.strip() for s in raw_targets.split(",") if s.strip()]
        elif isinstance(raw_targets, list):
            targets_list = [str(s).strip() for s in raw_targets if str(s).strip()]
        else:
            targets_list = []

        raw_excludes = profile.get("exclude_keywords") or profile.get("exclude_titles") or []
        if isinstance(raw_excludes, str):
            excludes_list = [s.strip() for s in raw_excludes.split(",") if s.strip()]
        elif isinstance(raw_excludes, list):
            excludes_list = [str(s).strip() for s in raw_excludes if str(s).strip()]
        else:
            excludes_list = []

        existing_pjson = profile.get("profile_json") or {}
        if not isinstance(existing_pjson, dict):
            existing_pjson = {}

        raw_min_score = profile.get("min_score_notification")
        try:
            min_score_val = float(raw_min_score) if raw_min_score is not None else 7.5
        except (ValueError, TypeError):
            min_score_val = 7.5

        pjson_merged = {
            **existing_pjson,
            "resume_text": profile.get("resume_text") if profile.get("resume_text") is not None else (existing_pjson.get("resume_text") or ""),
            "resume_filename": profile.get("resume_filename") if profile.get("resume_filename") is not None else (existing_pjson.get("resume_filename") or ""),
            "email_notifications_enabled": bool(profile.get("email_notifications_enabled", False)),
            "notification_email": profile.get("notification_email") or clean_email,
            "min_score_notification": min_score_val,
            "onboarding_completed": bool(profile.get("onboarding_completed", False)),
            "name": profile.get("name") or "",
            "title": profile.get("title") or profile.get("current_title") or "",
            "skills": skills_list,
            "target_keywords": targets_list,
            "exclude_keywords": excludes_list,
            "preferred_locations": profile.get("preferred_locations") or [],
            "job_types": profile.get("job_types") or [],
            "experience_level": profile.get("experience_level") or "",
            "min_salary_lpa": float(profile.get("min_salary_lpa") or 0),
            "preferred_sectors": profile.get("preferred_sectors") or [],
        }

        payload = {
            "email": clean_email,
            "name": profile.get("name") or "",
            "title": profile.get("title") or profile.get("current_title") or "",
            "education": profile.get("education") or "",
            "experience_years": float(profile.get("experience_years") or profile.get("years_experience") or 0),
            "skills": skills_list,
            "target_keywords": targets_list,
            "exclude_keywords": excludes_list,
            "resume_text": profile.get("resume_text") or "",
            "resume_filename": profile.get("resume_filename") or "",
            "email_notifications_enabled": bool(profile.get("email_notifications_enabled", False)),
            "notification_email": profile.get("notification_email") or clean_email,
            "min_score_notification": min_score_val,
            "onboarding_completed": bool(profile.get("onboarding_completed", False)),
            "preferred_locations": profile.get("preferred_locations") or [],
            "job_types": profile.get("job_types") or [],
            "experience_level": profile.get("experience_level") or "",
            "min_salary_lpa": float(profile.get("min_salary_lpa") or 0),
            "preferred_sectors": profile.get("preferred_sectors") or [],
            "profile_json": pjson_merged,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            endpoint = f"{self.url}/rest/v1/user_profiles"
            headers = self._headers(token)
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
            params = {"on_conflict": "email"}
            resp = requests.post(endpoint, headers=headers, params=params, json=payload, timeout=self.timeout)
            if resp.status_code not in (200, 201, 204):
                print(f"[SupabaseMemory] upsert_user_profile HTTP {resp.status_code}: {resp.text}")
            return resp.status_code in (200, 201, 204)
        except Exception as e:
            print(f"[SupabaseMemory] upsert_user_profile error for {clean_email}: {e}")
            return False

    def get_or_initialize_user(
        self,
        email: str,
        token: Optional[str] = None,
        user_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Retrieve existing user profile or create a minimal blank stub for new users.

        For new users we only store the bare minimum needed to satisfy foreign key
        constraints (email + notification_email). All content fields (name, title,
        skills, etc.) are left empty so the UI correctly presents a blank form and
        the onboarding wizard is triggered. No fake default data is written.
        """
        clean_email = email.lower().strip()
        existing = self.get_user_profile(clean_email, token=token)
        if existing:
            return existing

        # Minimal stub — only the fields required for FK integrity and notification routing.
        # Content fields are intentionally empty; onboarding_completed=False signals the UI.
        stub_profile = {
            "email": clean_email,
            "name": "",
            "title": "",
            "education": "",
            "experience_years": 0,
            "skills": [],
            "target_keywords": [],
            "exclude_keywords": [],
            "resume_text": "",
            "resume_filename": "",
            "profile_json": {},
            "email_notifications_enabled": False,
            "notification_email": clean_email,
            "min_score_notification": 7.5,
            "onboarding_completed": False,
        }

        self.upsert_user_profile(clean_email, stub_profile, token=token)
        return stub_profile

    # --------------------------------------------------------------------------
    # 2. Tracked Jobs Memory (Strict User Isolation)
    # --------------------------------------------------------------------------
    def load_user_jobs(self, email: str, limit: int = 10000, token: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Load all tracked jobs for a given user email from Supabase PostgreSQL."""
        if not self.is_configured or not email:
            return {}

        clean_email = email.lower().strip()
        jobs_map: Dict[str, Dict[str, Any]] = {}
        try:
            endpoint = f"{self.url}/rest/v1/user_tracked_jobs"
            params = {
                "user_email": f"eq.{clean_email}",
                "select": "job_id,company,title,location,url,ats,score,reason,applied,applied_on,application_stage,notes,salary_range,emailed,draft,first_seen,created_at",
                "order": "created_at.desc",
                "limit": str(limit),
            }
            resp = requests.get(endpoint, headers=self._headers(token), params=params, timeout=self.timeout)
            if resp.status_code == 200:
                records = resp.json()
                for r in records:
                    jid = r.get("job_id")
                    if jid:
                        applied = bool(r.get("applied"))
                        stage = r.get("application_stage") or ("applied" if applied else "to_apply")
                        jobs_map[jid] = {
                            "job_id": jid,
                            "company": r.get("company", ""),
                            "title": r.get("title", ""),
                            "location": r.get("location", ""),
                            "url": r.get("url", "#"),
                            "ats": r.get("ats", "custom"),
                            "score": float(r["score"]) if r.get("score") is not None else None,
                            "reason": r.get("reason"),
                            "applied": applied,
                            "applied_on": r.get("applied_on"),
                            "application_stage": stage,
                            "notes": r.get("notes") or "",
                            "salary_range": r.get("salary_range") or "",
                            "emailed": bool(r.get("emailed")),
                            "draft": r.get("draft") or {},
                            "first_seen": r.get("first_seen") or r.get("created_at"),
                        }
            return jobs_map
        except Exception as e:
            print(f"[SupabaseMemory] load_user_jobs error for {clean_email}: {e}")
            return {}

    def save_user_job(self, email: str, job_dict: Dict[str, Any], token: Optional[str] = None) -> bool:
        """Save or update a single job record in Supabase for user email."""
        if not self.is_configured or not email:
            return False

        clean_email = email.lower().strip()
        jid = str(job_dict.get("job_id", "")).strip()
        if not jid:
            return False

        self._ensure_user_profile_exists(clean_email, token)

        applied = bool(job_dict.get("applied", False))
        stage = job_dict.get("application_stage") or ("applied" if applied else "to_apply")

        payload = {
            "user_email": clean_email,
            "job_id": jid,
            "company": job_dict.get("company", ""),
            "title": job_dict.get("title", ""),
            "location": job_dict.get("location", "Remote/Unspecified"),
            "url": job_dict.get("url", "#"),
            "ats": job_dict.get("ats", "custom"),
            "score": job_dict.get("score"),
            "reason": job_dict.get("reason"),
            "applied": applied,
            "applied_on": job_dict.get("applied_on"),
            "application_stage": stage,
            "notes": job_dict.get("notes") or "",
            "salary_range": job_dict.get("salary_range") or "",
            "emailed": bool(job_dict.get("emailed", False)),
            "draft": job_dict.get("draft") or {},
            "first_seen": job_dict.get("first_seen") or datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            endpoint = f"{self.url}/rest/v1/user_tracked_jobs"
            headers = self._headers(token)
            headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
            return resp.status_code in (200, 201, 204)
        except Exception as e:
            print(f"[SupabaseMemory] save_user_job error for {clean_email} ({jid}): {e}")
            return False

    def bulk_upsert_user_jobs(self, email: str, jobs: List[Dict[str, Any]], token: Optional[str] = None) -> int:
        """Bulk upsert multiple jobs into Supabase PostgreSQL memory for user email."""
        if not self.is_configured or not email or not jobs:
            return 0

        clean_email = email.lower().strip()
        self._ensure_user_profile_exists(clean_email, token)

        records = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for j in jobs:
            jid = str(j.get("job_id", "")).strip()
            if not jid:
                continue
            applied = bool(j.get("applied", False))
            stage = j.get("application_stage") or ("applied" if applied else "to_apply")
            records.append({
                "user_email": clean_email,
                "job_id": jid,
                "company": j.get("company", ""),
                "title": j.get("title", ""),
                "location": j.get("location", "Remote/Unspecified"),
                "url": j.get("url", "#"),
                "ats": j.get("ats", "custom"),
                "score": j.get("score"),
                "reason": j.get("reason"),
                "applied": applied,
                "applied_on": j.get("applied_on"),
                "application_stage": stage,
                "notes": j.get("notes") or "",
                "salary_range": j.get("salary_range") or "",
                "emailed": bool(j.get("emailed", False)),
                "draft": j.get("draft") or {},
                "first_seen": j.get("first_seen") or now_iso,
                "updated_at": now_iso,
            })

        if not records:
            return 0

        inserted_count = 0
        chunk_size = 100
        for i in range(0, len(records), chunk_size):
            chunk = records[i:i + chunk_size]
            try:
                endpoint = f"{self.url}/rest/v1/user_tracked_jobs"
                headers = self._headers(token)
                headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
                resp = requests.post(endpoint, headers=headers, json=chunk, timeout=self.timeout)
                if resp.status_code in (200, 201, 204):
                    inserted_count += len(chunk)
            except Exception as e:
                print(f"[SupabaseMemory] bulk_upsert_user_jobs batch error for {clean_email}: {e}")

        return inserted_count

    def set_job_applied(self, email: str, job_id: str, applied: bool = True, token: Optional[str] = None) -> bool:
        """Update the applied status and application stage of a job in Supabase."""
        if not self.is_configured or not email or not job_id:
            return False

        clean_email = email.lower().strip()
        applied_on = datetime.now(timezone.utc).isoformat() if applied else None
        stage = "applied" if applied else "to_apply"
        payload = {
            "applied": applied,
            "applied_on": applied_on,
            "application_stage": stage,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            endpoint = f"{self.url}/rest/v1/user_tracked_jobs"
            headers = self._headers(token)
            headers["Prefer"] = "return=minimal"
            params = {
                "user_email": f"eq.{clean_email}",
                "job_id": f"eq.{job_id.strip()}",
            }
            resp = requests.patch(endpoint, headers=headers, params=params, json=payload, timeout=self.timeout)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"[SupabaseMemory] set_job_applied error for {clean_email} ({job_id}): {e}")
            return False

    def set_job_stage(self, email: str, job_id: str, stage: str, token: Optional[str] = None) -> bool:
        """Update the Kanban pipeline stage of a job in Supabase."""
        if not self.is_configured or not email or not job_id or not stage:
            return False

        clean_email = email.lower().strip()
        clean_stage = stage.lower().strip()
        applied = clean_stage in ("applied", "interviewing", "offer", "rejected")
        applied_on = datetime.now(timezone.utc).isoformat() if applied else None

        payload: dict[str, Any] = {
            "application_stage": clean_stage,
            "applied": applied,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if applied:
            payload["applied_on"] = applied_on

        try:
            endpoint = f"{self.url}/rest/v1/user_tracked_jobs"
            headers = self._headers(token)
            headers["Prefer"] = "return=minimal"
            params = {
                "user_email": f"eq.{clean_email}",
                "job_id": f"eq.{job_id.strip()}",
            }
            resp = requests.patch(endpoint, headers=headers, params=params, json=payload, timeout=self.timeout)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"[SupabaseMemory] set_job_stage error for {clean_email} ({job_id}): {e}")
            return False

    def set_job_notes(self, email: str, job_id: str, notes: str, token: Optional[str] = None) -> bool:
        """Update candidate private notes for a job in Supabase."""
        if not self.is_configured or not email or not job_id:
            return False

        clean_email = email.lower().strip()
        payload = {
            "notes": str(notes or ""),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            endpoint = f"{self.url}/rest/v1/user_tracked_jobs"
            headers = self._headers(token)
            headers["Prefer"] = "return=minimal"
            params = {
                "user_email": f"eq.{clean_email}",
                "job_id": f"eq.{job_id.strip()}",
            }
            resp = requests.patch(endpoint, headers=headers, params=params, json=payload, timeout=self.timeout)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"[SupabaseMemory] set_job_notes error for {clean_email} ({job_id}): {e}")
            return False

    def delete_user_job(self, email: str, job_id: str, token: Optional[str] = None) -> bool:
        """Delete a job record from Supabase PostgreSQL for user email."""
        if not self.is_configured or not email or not job_id:
            return False

        clean_email = email.lower().strip()
        try:
            endpoint = f"{self.url}/rest/v1/user_tracked_jobs"
            headers = self._headers(token)
            params = {
                "user_email": f"eq.{clean_email}",
                "job_id": f"eq.{job_id.strip()}",
            }
            resp = requests.delete(endpoint, headers=headers, params=params, timeout=self.timeout)
            return resp.status_code in (200, 204)
        except Exception as e:
            print(f"[SupabaseMemory] delete_user_job error for {clean_email} ({job_id}): {e}")
            return False

    # --------------------------------------------------------------------------
    # 3. Pipeline Execution History & Memory Logs
    # --------------------------------------------------------------------------
    def record_pipeline_run(self, email: str, run_data: Dict[str, Any], token: Optional[str] = None) -> bool:
        """Log a pipeline execution history event into Supabase PostgreSQL."""
        if not self.is_configured or not email:
            return False

        clean_email = email.lower().strip()
        self._ensure_user_profile_exists(clean_email, token)

        payload = {
            "user_email": clean_email,
            "run_timestamp": run_data.get("timestamp") or datetime.now(timezone.utc).isoformat(),
            "jobs_scanned": int(run_data.get("scanned", 0)),
            "candidates_matched": int(run_data.get("matched", 0)),
            "shortlisted": int(run_data.get("shortlisted", 0)),
            "status": run_data.get("status", "completed"),
            "logs": run_data.get("logs", ""),
        }

        try:
            endpoint = f"{self.url}/rest/v1/user_pipeline_runs"
            headers = self._headers(token)
            headers["Prefer"] = "return=minimal"
            resp = requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
            return resp.status_code in (200, 201, 204)
        except Exception as e:
            print(f"[SupabaseMemory] record_pipeline_run error for {clean_email}: {e}")
            return False

    def get_pipeline_history(self, email: str, limit: int = 10, token: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve recent pipeline run history for user email."""
        if not self.is_configured or not email:
            return []

        clean_email = email.lower().strip()
        try:
            endpoint = f"{self.url}/rest/v1/user_pipeline_runs"
            params = {
                "user_email": f"eq.{clean_email}",
                "select": "*",
                "order": "run_timestamp.desc",
                "limit": str(limit),
            }
            resp = requests.get(endpoint, headers=self._headers(token), params=params, timeout=self.timeout)
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            print(f"[SupabaseMemory] get_pipeline_history error for {clean_email}: {e}")
            return []

    # --------------------------------------------------------------------------
    # 4. Internal Helpers
    # --------------------------------------------------------------------------
    def _ensure_user_profile_exists(self, email: str, token: Optional[str] = None) -> None:
        """Ensure a base profile record exists in user_profiles to satisfy foreign keys."""
        if not self.is_configured or not email:
            return
        try:
            endpoint = f"{self.url}/rest/v1/user_profiles"
            headers = self._headers(token)
            headers["Prefer"] = "resolution=ignore-duplicates,return=minimal"
            payload = {
                "email": email.lower().strip(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            requests.post(endpoint, headers=headers, json=payload, timeout=self.timeout)
        except Exception:
            pass
