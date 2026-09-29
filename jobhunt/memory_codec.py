"""Profile row normalization and serialization helpers for SupabaseMemory."""

from __future__ import annotations

from typing import Any, Dict


def merge_db_profile_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Merge a Supabase DB row with its embedded profile_json blob into a unified profile dict.

    The DB schema stores flat columns (name, title, skills, ...) as the source of truth.
    profile_json is a legacy/extended blob that may contain additional fields. Flat columns
    always win over profile_json values when both are present.
    """
    pjson = row.get("profile_json") or {}
    if not isinstance(pjson, dict):
        pjson = {}
    res = {**pjson, **row}
    res["name"] = row.get("name") if row.get("name") is not None else (pjson.get("name") or "")
    res["title"] = (
        row.get("title") if row.get("title") is not None else (pjson.get("title") or pjson.get("current_title") or "")
    )
    res["skills"] = (
        row.get("skills")
        if row.get("skills") is not None
        else (pjson.get("skills") if pjson.get("skills") is not None else (pjson.get("core_skills") or []))
    )
    res["target_keywords"] = (
        row.get("target_keywords")
        if row.get("target_keywords") is not None
        else (
            pjson.get("target_keywords")
            if pjson.get("target_keywords") is not None
            else (pjson.get("target_titles") or [])
        )
    )
    res["exclude_keywords"] = (
        row.get("exclude_keywords")
        if row.get("exclude_keywords") is not None
        else (pjson.get("exclude_keywords") if pjson.get("exclude_keywords") is not None else [])
    )
    res["resume_text"] = (
        row.get("resume_text") if row.get("resume_text") is not None else (pjson.get("resume_text") or "")
    )
    res["resume_filename"] = (
        row.get("resume_filename") if row.get("resume_filename") is not None else (pjson.get("resume_filename") or "")
    )
    res["email_notifications_enabled"] = bool(
        row.get("email_notifications_enabled", pjson.get("email_notifications_enabled", False))
    )
    res["onboarding_completed"] = bool(row.get("onboarding_completed", pjson.get("onboarding_completed", False)))
    res["preferred_locations"] = (
        row.get("preferred_locations")
        if row.get("preferred_locations") is not None
        else (pjson.get("preferred_locations") or [])
    )
    res["location_preference"] = (
        row.get("location_preference")
        if row.get("location_preference") is not None
        else (pjson.get("location_preference") or "all_india")
    )
    res["job_types"] = row.get("job_types") if row.get("job_types") is not None else (pjson.get("job_types") or [])
    res["experience_level"] = (
        row.get("experience_level")
        if row.get("experience_level") is not None
        else (pjson.get("experience_level") or "")
    )
    res["min_salary_lpa"] = (
        row.get("min_salary_lpa") if row.get("min_salary_lpa") is not None else (pjson.get("min_salary_lpa") or 0)
    )
    res["notice_period"] = row.get("notice_period") or pjson.get("notice_period") or "30_days"
    res["current_ctc_lpa"] = (
        row.get("current_ctc_lpa") if row.get("current_ctc_lpa") is not None else pjson.get("current_ctc_lpa")
    )
    res["expected_ctc_lpa"] = (
        row.get("expected_ctc_lpa")
        if row.get("expected_ctc_lpa") is not None
        else (pjson.get("expected_ctc_lpa") or row.get("min_salary_lpa") or pjson.get("min_salary_lpa") or 0)
    )
    res["education"] = row.get("education") or pjson.get("education") or ""
    res["experience_years"] = (
        row.get("experience_years")
        if row.get("experience_years") is not None
        else (pjson.get("experience_years") if pjson.get("experience_years") is not None else pjson.get("years_experience", 0))
    )
    res["preferred_sectors"] = (
        row.get("preferred_sectors")
        if row.get("preferred_sectors") is not None
        else (pjson.get("preferred_sectors") or [])
    )
    res["min_score_notification"] = (
        row.get("min_score_notification")
        if row.get("min_score_notification") is not None
        else (pjson.get("min_score_notification") or 7.5)
    )
    res["notification_email"] = (
        row.get("notification_email")
        if row.get("notification_email") is not None
        else (pjson.get("notification_email") or row.get("email") or "")
    )
    return res
