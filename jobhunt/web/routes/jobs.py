"""Job tracking, stage transitions, manual job creation, stats, and CSV export routes."""

from __future__ import annotations

import json
import logging
from typing import Any
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file

from ... import cli, llm
from ...auth import require_auth
from ...store import Store, get_writable_path
from ..state import ROOT, get_current_user_context, get_store_version

logger = logging.getLogger(__name__)

jobs_bp = Blueprint("jobs", __name__)


@jobs_bp.route("/api/config")
@require_auth
def api_config():
    """Return summary of active configuration and ATS boards."""
    cfg = cli._cfg(raise_on_error=False)
    filters = cfg.get("filters", {})
    companies_file = ROOT / cfg.get("companies_file", "companies.yaml")
    company_count = 0
    if companies_file.is_file():
        try:
            import yaml

            data = yaml.safe_load(companies_file.read_text(encoding="utf-8")) or {}
            company_count = len(data.get("companies", [])) if isinstance(data, dict) else len(data)
        except Exception:
            pass

    return jsonify(
        {
            "status": "success",
            "companies_count": company_count,
            "filters": {
                "include_titles_count": len(filters.get("include_titles", [])),
                "exclude_titles_count": len(filters.get("exclude_titles", [])),
                "locations": filters.get("locations", []),
                "allow_remote": bool(filters.get("allow_remote", True)),
                "max_age_days": filters.get("max_age_days", 28),
            },
            "score_threshold": cfg.get("score_threshold", 7.0),
            "max_per_digest": cfg.get("max_per_digest", 7),
        }
    )


@jobs_bp.route("/api/companies")
@require_auth
def api_companies():
    """Return parsed list of all supported company boards with ATS and category info."""
    cfg = cli._cfg(raise_on_error=False)
    companies_file = ROOT / cfg.get("companies_file", "companies.yaml")
    companies: list[dict] = []
    if companies_file.is_file():
        try:
            import yaml

            data = yaml.safe_load(companies_file.read_text(encoding="utf-8")) or {}
            companies = (
                data.get("companies", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            )
        except Exception as e:
            logger.warning(f"Failed to load companies.yaml: {e}")

    search = request.args.get("search", "").lower().strip()
    ats_filter = request.args.get("ats", "all").lower().strip()

    filtered = []
    for c in companies:
        name = str(c.get("name", ""))
        slug = str(c.get("slug", ""))
        ats = str(c.get("ats", ""))

        if ats_filter != "all" and ats.lower() != ats_filter:
            continue
        if search and (search not in name.lower() and search not in slug.lower() and search not in ats.lower()):
            continue
        filtered.append(c)

    return jsonify(
        {
            "status": "success",
            "total": len(companies),
            "count": len(filtered),
            "companies": filtered,
        }
    )


@jobs_bp.route("/api/companies/custom", methods=["GET"])
@require_auth
def api_get_custom_companies():
    """List candidate's custom added ATS target boards."""
    email, token = get_current_user_context()
    from ...memory import SupabaseMemory

    memory = SupabaseMemory(token=token)
    custom_comps: list[dict] = []
    if email and memory.is_configured:
        prof = memory.get_user_profile(email, token=token) or {}
        pjson_raw = prof.get("profile_json")
        pjson: dict[str, Any] = pjson_raw if isinstance(pjson_raw, dict) else {}
        custom_comps = prof.get("custom_companies") or pjson.get("custom_companies") or []
    else:
        cfg = cli._cfg(raise_on_error=False)
        profile_path = get_writable_path(cfg.get("profile_file", "profile.json"))
        prof = {}
        if profile_path.is_file():
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    prof = json.load(f)
            except Exception:
                prof = {}
        if not prof:
            prof = cli._load_profile(cfg, raise_on_error=False) or {}
        custom_comps = prof.get("custom_companies") or []

    return jsonify({"status": "success", "count": len(custom_comps), "companies": custom_comps})


@jobs_bp.route("/api/companies/add", methods=["POST"])
@require_auth
def api_add_custom_company():
    """Validate and add a custom target company career board."""
    from ...fetch import detect_ats_from_url, REGISTERED_ATS
    from ...verify import check_single_board
    from ...memory import SupabaseMemory

    data = request.get_json(silent=True) or {}
    url = str(data.get("url") or "").strip()
    ats = str(data.get("ats") or "").strip().lower()
    slug = str(data.get("slug") or "").strip()
    name = str(data.get("name") or "").strip()

    if url:
        detected = detect_ats_from_url(url)
        if not detected:
            return jsonify({
                "status": "error",
                "message": "Could not identify ATS platform from URL. Supported: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy, Pinpoint."
            }), 400
        ats = detected["ats"]
        slug = detected["slug"]
        if not name:
            name = detected["name"]

    if not ats or not slug:
        return jsonify({"status": "error", "message": "ATS type and company slug are required."}), 400

    if ats not in REGISTERED_ATS:
        return jsonify({"status": "error", "message": f"Unsupported ATS '{ats}'. Supported: {', '.join(REGISTERED_ATS)}"}), 400

    company_entry = {"ats": ats, "slug": slug, "name": name or slug.replace("-", " ").title()}

    # Validate live HTTP accessibility before saving
    _, is_valid, detail = check_single_board(company_entry, timeout=5)
    if not is_valid:
        return jsonify({
            "status": "error",
            "message": f"Board validation failed for {ats}:{slug} (HTTP {detail}). Please verify the slug or URL."
        }), 400

    email, token = get_current_user_context()
    memory = SupabaseMemory(token=token)

    if email and memory.is_configured:
        prof = memory.get_user_profile(email, token=token) or {}
        pjson_raw = prof.get("profile_json")
        pjson: dict[str, Any] = dict(pjson_raw) if isinstance(pjson_raw, dict) else {}
        existing = list(prof.get("custom_companies") or pjson.get("custom_companies") or [])
        existing = [c for c in existing if not (c.get("ats") == ats and c.get("slug") == slug)]
        existing.append(company_entry)
        pjson["custom_companies"] = existing
        prof["custom_companies"] = existing
        prof["profile_json"] = pjson
        memory.upsert_user_profile(email, prof, token=token)
    else:
        cfg = cli._cfg(raise_on_error=False)
        profile_path = get_writable_path(cfg.get("profile_file", "profile.json"))
        prof = {}
        if profile_path.is_file():
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    prof = json.load(f)
            except Exception:
                prof = {}
        if not prof:
            prof = cli._load_profile(cfg, raise_on_error=False) or {}
        existing = list(prof.get("custom_companies") or [])
        existing = [c for c in existing if not (c.get("ats") == ats and c.get("slug") == slug)]
        existing.append(company_entry)
        prof["custom_companies"] = existing
        try:
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(prof, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not cache profile locally: {e}")

    return jsonify({
        "status": "success",
        "message": f"Successfully registered and verified {company_entry['name']} ({ats})!",
        "company": company_entry,
    })


@jobs_bp.route("/api/companies/custom", methods=["DELETE"])
@require_auth
def api_delete_custom_company():
    """Remove a custom company board from candidate tracking profile."""
    from ...memory import SupabaseMemory

    data = request.get_json(silent=True) or {}
    ats = str(data.get("ats") or "").strip().lower()
    slug = str(data.get("slug") or "").strip()

    if not ats or not slug:
        return jsonify({"status": "error", "message": "ATS and slug are required"}), 400

    email, token = get_current_user_context()
    memory = SupabaseMemory(token=token)

    if email and memory.is_configured:
        prof = memory.get_user_profile(email, token=token) or {}
        pjson_raw = prof.get("profile_json")
        pjson: dict[str, Any] = dict(pjson_raw) if isinstance(pjson_raw, dict) else {}
        existing = list(prof.get("custom_companies") or pjson.get("custom_companies") or [])
        filtered = [c for c in existing if not (str(c.get("ats")).lower() == ats and str(c.get("slug")).lower() == slug)]
        pjson["custom_companies"] = filtered
        prof["custom_companies"] = filtered
        prof["profile_json"] = pjson
        memory.upsert_user_profile(email, prof, token=token)
    else:
        cfg = cli._cfg(raise_on_error=False)
        profile_path = get_writable_path(cfg.get("profile_file", "profile.json"))
        prof = {}
        if profile_path.is_file():
            try:
                with open(profile_path, "r", encoding="utf-8") as f:
                    prof = json.load(f)
            except Exception:
                prof = {}
        if not prof:
            prof = cli._load_profile(cfg, raise_on_error=False) or {}
        existing = list(prof.get("custom_companies") or [])
        filtered = [c for c in existing if not (str(c.get("ats")).lower() == ats and str(c.get("slug")).lower() == slug)]
        prof["custom_companies"] = filtered
        try:
            profile_path.parent.mkdir(parents=True, exist_ok=True)
            with open(profile_path, "w", encoding="utf-8") as f:
                json.dump(prof, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not cache profile locally: {e}")

    return jsonify({"status": "success", "message": f"Removed {ats}:{slug} from custom companies"})


@jobs_bp.route("/api/stats")
@require_auth
def api_stats():
    """Return tracker stats JSON with complete count breakdown."""
    email, token = get_current_user_context()
    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "state/seen.json")
    st = Store(seen_file, user_email=email, token=token)

    # Resolve the user's actual notification threshold — from their Supabase profile
    # if available, otherwise fall back to the global config score_threshold.
    base_threshold = float(cfg.get("score_threshold", 7.0))
    user_threshold = base_threshold
    if email:
        from ...memory import SupabaseMemory
        mem = SupabaseMemory(token=token)
        if mem.is_configured:
            prof = mem.get_user_profile(email, token=token)
            if prof:
                raw = prof.get("min_score_notification") or (
                    prof.get("profile_json") or {}
                ).get("min_score_notification")
                if raw is not None:
                    try:
                        user_threshold = float(raw)
                    except (ValueError, TypeError):
                        pass

    total_count = len(st.data)
    shortlisted_count = sum(1 for v in st.data.values() if (v.get("score") or 0.0) >= user_threshold)
    applied_count = sum(1 for v in st.data.values() if v.get("applied"))
    unapplied_count = total_count - applied_count

    stats = {
        "tracked": total_count,
        "emailed": sum(1 for v in st.data.values() if v.get("emailed")),
        "applied": applied_count,
        "unapplied": unapplied_count,
        "shortlisted": shortlisted_count,
        "user_threshold": user_threshold,
        "version": get_store_version(st),
    }
    return jsonify(stats)


@jobs_bp.route("/api/export/csv")
@require_auth
def api_export_csv():
    """Serve job tracker data exported as CSV file download (strictly user isolated)."""
    email, token = get_current_user_context()
    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "state/seen.json")
    tracker_csv = cfg.get("tracker_csv", "out/tracker.csv")
    st = Store(seen_file, user_email=email, token=token)
    csv_path = Path(st.export_csv(tracker_csv)).resolve()
    return send_file(str(csv_path), mimetype="text/csv", as_attachment=True, download_name="tracker.csv")


@jobs_bp.route("/api/jobs")
@require_auth
def api_jobs():
    """Return list of all tracked jobs with filtering and sorting support (strictly user isolated)."""
    email, token = get_current_user_context()
    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "state/seen.json")
    st = Store(seen_file, user_email=email, token=token)

    status = request.args.get("status", "all").lower()
    ats_filter = request.args.get("ats", "all").lower().strip()
    search = request.args.get("search", "").lower().strip()
    min_score = request.args.get("min_score", type=float)
    sort_by = request.args.get("sort", "date").lower().strip()

    # Resolve the user's actual notification threshold for the "shortlisted" status filter.
    # This ensures the interactive board's "shortlisted" view is consistent with what
    # was included in the email briefing — both use the user's min_score_notification.
    shortlist_threshold = float(cfg.get("score_threshold", 7.0))
    if email and status == "shortlisted":
        from ...memory import SupabaseMemory
        mem = SupabaseMemory(token=token)
        if mem.is_configured:
            prof = mem.get_user_profile(email, token=token)
            if prof:
                raw = prof.get("min_score_notification") or (
                    prof.get("profile_json") or {}
                ).get("min_score_notification")
                if raw is not None:
                    try:
                        shortlist_threshold = float(raw)
                    except (ValueError, TypeError):
                        pass

    jobs_list = []
    for job_id, data in st.data.items():
        item = {"job_id": job_id, **data}
        job_ats = (item.get("ats") or (job_id.split(":")[0] if ":" in job_id else "custom")).lower()

        # Filter status
        if status == "shortlisted" and (item.get("score") or 0.0) < shortlist_threshold:
            continue
        elif status == "applied" and not item.get("applied"):
            continue
        elif status == "unapplied" and item.get("applied"):
            continue

        # Filter ATS provider
        if ats_filter != "all" and job_ats != ats_filter:
            continue

        # Filter min_score
        if min_score is not None and (item.get("score") or 0.0) < min_score:
            continue

        # Filter search text
        if search:
            searchable = (
                f"{item.get('company', '')} {item.get('title', '')} {item.get('location', '')} {job_ats}".lower()
            )
            if search not in searchable:
                continue

        jobs_list.append(item)

    # Sort logic
    def _safe_score(j: dict) -> float:
        val = j.get("score")
        if val is None:
            return -1.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return -1.0

    if sort_by == "score":
        jobs_list.sort(
            key=lambda j: (_safe_score(j), j.get("first_seen", "")),
            reverse=True,
        )
    elif sort_by == "company":
        jobs_list.sort(key=lambda j: j.get("company", "").lower())
    else:  # default: date
        jobs_list.sort(key=lambda j: j.get("first_seen", ""), reverse=True)

    return jsonify({"status": "success", "count": len(jobs_list), "jobs": jobs_list})



@jobs_bp.route("/api/applied", methods=["POST"])
@require_auth
def api_applied():
    """Mark or unmark a job as applied with immediate version bump."""
    email, token = get_current_user_context()
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "").strip()
    action = data.get("action", "mark").lower().strip()

    if not job_id:
        return jsonify({"status": "error", "message": "Job ID is required"}), 400

    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "state/seen.json")
    tracker_csv = cfg.get("tracker_csv", "out/tracker.csv")
    st = Store(seen_file, user_email=email, token=token)

    if action == "unmark":
        success = st.unmark_applied(job_id)
        msg_str = f"Unmarked '{job_id}' as applied."
    else:
        success = st.mark_applied(job_id)
        msg_str = f"Marked '{job_id}' as applied."

    if success:
        st.export_csv(tracker_csv)
        version = get_store_version(st)
        return jsonify(
            {
                "status": "success",
                "message": msg_str,
                "job_id": job_id,
                "applied": action != "unmark",
                "version": version,
                "stats": st.stats(),
            }
        )
    else:
        return jsonify({"status": "error", "message": f"Job ID '{job_id}' not found in tracking store."}), 404


@jobs_bp.route("/api/delete", methods=["POST", "DELETE"])
@require_auth
def api_delete():
    """Delete a job entry from the tracking store with immediate version bump."""
    email, token = get_current_user_context()
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "").strip()

    if not job_id:
        return jsonify({"status": "error", "message": "Job ID is required"}), 400

    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "state/seen.json")
    tracker_csv = cfg.get("tracker_csv", "out/tracker.csv")
    st = Store(seen_file, user_email=email, token=token)

    if st.delete_job(job_id):
        st.export_csv(tracker_csv)
        version = get_store_version(st)
        return jsonify(
            {
                "status": "success",
                "message": f"Job '{job_id}' removed from tracking store.",
                "job_id": job_id,
                "version": version,
                "stats": st.stats(),
            }
        )
    else:
        return jsonify({"status": "error", "message": f"Job ID '{job_id}' not found in tracking store."}), 404


VALID_APPLICATION_STAGES = {"to_apply", "applied", "interviewing", "offer", "rejected"}


@jobs_bp.route("/api/jobs/stage", methods=["POST"])
@require_auth
def api_jobs_stage():
    """Update job application pipeline stage (to_apply, applied, interviewing, offer, rejected)."""
    email, token = get_current_user_context()
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "").strip()
    stage = data.get("stage", "to_apply").lower().strip()

    if not job_id:
        return jsonify({"status": "error", "message": "Job ID is required"}), 400

    if stage not in VALID_APPLICATION_STAGES:
        allowed = ", ".join(sorted(VALID_APPLICATION_STAGES))
        return jsonify({"status": "error", "message": f"Invalid stage '{stage}'. Must be one of: {allowed}"}), 400

    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "state/seen.json")
    tracker_csv = cfg.get("tracker_csv", "out/tracker.csv")
    st = Store(seen_file, user_email=email, token=token)

    if st.update_stage(job_id, stage):
        st.export_csv(tracker_csv)
        version = get_store_version(st)
        return jsonify(
            {
                "status": "success",
                "message": f"Updated stage for '{job_id}' to '{stage}'.",
                "job_id": job_id,
                "stage": stage,
                "applied": st.data.get(job_id, {}).get("applied", False),
                "version": version,
                "stats": st.stats(),
            }
        )
    else:
        return jsonify({"status": "error", "message": f"Job ID '{job_id}' not found."}), 404


@jobs_bp.route("/api/jobs/notes", methods=["POST"])
@require_auth
def api_jobs_notes():
    """Update private candidate notes for a tracked job."""
    email, token = get_current_user_context()
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "").strip()
    notes = data.get("notes", "")

    if not job_id:
        return jsonify({"status": "error", "message": "Job ID is required"}), 400

    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "state/seen.json")
    st = Store(seen_file, user_email=email, token=token)

    if st.update_notes(job_id, notes):
        version = get_store_version(st)
        return jsonify(
            {
                "status": "success",
                "message": "Notes saved.",
                "job_id": job_id,
                "notes": notes,
                "version": version,
                "stats": st.stats(),
            }
        )
    else:
        return jsonify({"status": "error", "message": f"Job ID '{job_id}' not found."}), 404


@jobs_bp.route("/api/add", methods=["POST"])
@jobs_bp.route("/api/jobs/add", methods=["POST"])
@require_auth
def api_add():
    """Manually add a custom job entry to store with optional on-demand AI scoring."""
    email, token = get_current_user_context()
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    company = data.get("company", "").strip()

    if not title or not company:
        return jsonify({"status": "error", "message": "Title and Company are required."}), 400

    location = data.get("location", "Remote/Unspecified").strip()
    url = data.get("url", "#").strip()
    ats = data.get("ats", "custom").strip()
    description = data.get("description", "").strip()
    reason = data.get("reason", "Custom opportunity added via Dashboard").strip()
    applied = bool(data.get("applied", False))
    stage = data.get("stage", "applied" if applied else "to_apply")

    has_explicit_score = "score" in data and data["score"] is not None and str(data["score"]).strip() != ""
    try:
        raw_score = float(data.get("score", 7.5))
        score = max(0.0, min(10.0, raw_score))
    except (TypeError, ValueError):
        score = 7.5

    draft = data.get("draft") or {}

    # On-demand AI scoring if description provided and score not explicitly set
    if description and (data.get("run_ai") or not has_explicit_score):
        cfg_temp = cli._cfg(raise_on_error=False)
        user_prof = cli._load_profile(cfg_temp, raise_on_error=False) or {}
        from ...fetch import Job

        temp_job = Job(
            job_id="custom:temp:1",
            ats=ats,
            company=company,
            title=title,
            location=location,
            url=url,
            description=description,
        )
        try:
            provider, model = llm.resolve("screen")
            llm.screen([temp_job], user_prof, provider=provider, model=model, delay_seconds=0)
            if temp_job.score is not None:
                score = temp_job.score
                reason = temp_job.reason or reason
        except Exception:
            llm.keyword_screen([temp_job], user_prof)
            if temp_job.score is not None:
                score = temp_job.score
                reason = temp_job.reason or reason

        # Draft kit
        try:
            d_provider, d_model = llm.resolve("draft")
            llm.draft([temp_job], user_prof, provider=d_provider, model=d_model, delay_seconds=0)
            if temp_job.draft:
                draft = temp_job.draft
        except Exception:
            pass

    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "state/seen.json")
    tracker_csv = cfg.get("tracker_csv", "out/tracker.csv")
    st = Store(seen_file, user_email=email, token=token)

    job_id = st.add_job(
        title=title,
        company=company,
        location=location,
        url=url,
        ats=ats,
        score=score,
        reason=reason,
        applied=applied,
        draft=draft,
    )
    if stage and stage != "to_apply":
        st.update_stage(job_id, stage)

    st.export_csv(tracker_csv)
    version = get_store_version(st)

    new_job_data = st.data.get(job_id, {})

    return jsonify(
        {
            "status": "success",
            "message": f"Added job '{title}' ({job_id}).",
            "job_id": job_id,
            "job": {"job_id": job_id, **new_job_data},
            "version": version,
            "stats": st.stats(),
        }
    )


@jobs_bp.route("/api/jobs/followup", methods=["POST"])
@require_auth
def api_job_followup():
    """Generate tailored follow-up outreach templates for an applied opportunity."""
    data = request.get_json(silent=True) or {}
    title = str(data.get("title") or "").strip()
    company = str(data.get("company") or "").strip()
    applied_on = str(data.get("applied_on") or "").strip()
    stage = str(data.get("stage") or "applied").strip()

    email, token = get_current_user_context()
    from ...memory import SupabaseMemory

    candidate_name = ""
    memory = SupabaseMemory(token=token)
    if email and memory.is_configured:
        prof = memory.get_user_profile(email, token=token) or {}
        candidate_name = prof.get("name") or ""
    if not candidate_name:
        cfg = cli._cfg(raise_on_error=False)
        prof = cli._load_profile(cfg, raise_on_error=False) or {}
        candidate_name = prof.get("name") or ""

    followup_data = llm.generate_followup_note(
        job_title=title,
        company=company,
        candidate_name=candidate_name,
        applied_on=applied_on,
        stage=stage,
    )
    return jsonify({"status": "success", "followup": followup_data})

