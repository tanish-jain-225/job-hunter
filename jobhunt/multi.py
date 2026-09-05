"""Multi-tenant single-pass batch execution engine for Job Hunter.

Enables hundreds of users to receive daily job intelligence at zero infrastructure cost:
1. Fetches all target ATS company boards ONCE into a shared in-memory pool.
2. Iterates over all active users in Supabase PostgreSQL (or local profiles).
3. Pre-filters jobs dynamically against each candidate's specific criteria.
4. Screens and drafts application kits using frontier LLMs (Groq / Gemini / Claude).
5. Dispatches personalized HTML briefings via email for users with notifications enabled.
6. Records run metrics and audits per user.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")

from . import cli, digest, llm, mailer
from .fetch import fetch_all
from .mock import fetch_all_mock
from .memory import SupabaseMemory
from .prefilter import prefilter
from .providers import resolve
from .store import Store

ROOT = Path(__file__).resolve().parent.parent


def merge_user_profile(row: dict) -> dict:
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
    res["preferred_sectors"] = (
        row.get("preferred_sectors")
        if row.get("preferred_sectors") is not None
        else (pjson.get("preferred_sectors") or [])
    )
    res["min_score_notification"] = (
        row.get("min_score_notification")
        if row.get("min_score_notification") is not None
        else pjson.get("min_score_notification")
    )
    res["notification_email"] = (
        row.get("notification_email")
        if row.get("notification_email") is not None
        else (pjson.get("notification_email") or row.get("email") or "")
    )
    return res


def run_multi_user_pipeline(
    config_path: str | Path | None = None,
    mock: bool = False,
    scorer: str = "llm",
    force_send: bool = False,
    user_email: str | None = None,
) -> dict[str, Any]:
    """Execute a batch for all active accounts or one explicitly selected account."""
    cfg = cli._cfg(config_path, raise_on_error=False)
    cli._load_env()
    memory = SupabaseMemory()

    print("=" * 70)
    print(" 🏹 JOB HUNTER — Multi-User Automated Batch Pipeline")
    print("=" * 70)

    # 1. Fetch all raw jobs ONCE (shared pool)
    fetch_max_workers = int(cfg.get("fetch_max_workers", 8))
    companies_file = ROOT / cfg.get("companies_file", "companies.yaml")

    print("\n[1/4] Crawling target ATS boards into shared global job pool...")
    if mock:
        raw_jobs = fetch_all_mock()
    else:
        raw_jobs = fetch_all(companies_file, max_workers=fetch_max_workers, use_cache=True)
    print(f"  Total raw postings discovered: {len(raw_jobs)}")

    if not raw_jobs:
        print("  ! No jobs retrieved. Ending batch run.")
        return {"status": "no_jobs", "users_processed": 0, "dispatched": 0}

    # 2. Retrieve all active users from Supabase
    users_to_process: list[dict[str, Any]] = []
    if memory.is_configured:
        try:
            # Admin operation: list ALL user profiles for batch processing.
            # This is the ONLY place where use_service_key=True is appropriate —
            # we intentionally bypass RLS here to enumerate all users for the batch run.
            endpoint = f"{memory.url}/rest/v1/user_profiles"
            headers = memory._headers(use_service_key=True)
            params = {"select": "*", "order": "created_at.asc"}
            if user_email:
                params["email"] = f"eq.{user_email.lower().strip()}"
            resp = requests.get(endpoint, headers=headers, params=params, timeout=memory.timeout)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for u in data:
                        merged_u = merge_user_profile(u)
                        if user_email and (merged_u.get("email") or "").lower().strip() != user_email.lower().strip():
                            continue
                        # Include users who completed onboarding or have non-empty profile
                        if merged_u.get("onboarding_completed") or merged_u.get("name") or merged_u.get("skills"):
                            users_to_process.append(merged_u)
        except Exception as e:
            print(f"  ! Supabase user query error: {e}")

    # Never cross tenant boundaries or use a local fallback for a targeted run.
    if user_email and not users_to_process:
        return {"status": "user_not_found", "users_processed": 0, "dispatched": 0}

    # Fallback to local profile only for the scheduled/local all-user mode.
    if not users_to_process and not user_email:
        local_prof = cli._load_profile(cfg, raise_on_error=False)
        if local_prof:
            local_prof.setdefault("email", os.environ.get("MAIL_TO", "user@local"))
            local_prof.setdefault("notification_email", os.environ.get("MAIL_TO", "user@local"))
            local_prof.setdefault("email_notifications_enabled", True)
            users_to_process.append(local_prof)

    print(f"\n[2/4] Loaded {len(users_to_process)} candidate profiles for screening.")

    # Merge custom target companies from all active users into global pool
    all_custom_comps: list[dict] = []
    for u in users_to_process:
        pjson_raw = u.get("profile_json")
        pjson: dict[str, Any] = pjson_raw if isinstance(pjson_raw, dict) else {}
        u_custom = u.get("custom_companies") or pjson.get("custom_companies") or []
        if isinstance(u_custom, list):
            for c in u_custom:
                if isinstance(c, dict) and c.get("ats") and c.get("slug"):
                    all_custom_comps.append(c)
    if all_custom_comps and not mock:
        extra_jobs = fetch_all([], max_workers=fetch_max_workers, custom_companies=all_custom_comps, use_cache=True)
        if extra_jobs:
            existing_jids = {j.job_id for j in raw_jobs}
            new_extras = [j for j in extra_jobs if j.job_id not in existing_jids]
            raw_jobs.extend(new_extras)
            print(f"  Added {len(new_extras)} postings from user custom target boards.")

    users_processed = 0
    total_matches = 0
    total_shortlisted = 0
    dispatched_emails = 0

    score_threshold = float(cfg.get("score_threshold", 7.0))
    max_per_digest = int(cfg.get("max_per_digest", 7))
    smtp_pass = os.environ.get("SMTP_PASS", "")
    has_smtp = bool(smtp_pass and "your-gmail" not in smtp_pass and "paste-your" not in smtp_pass)

    # 3. Process each user individually with strict isolation
    for idx, user in enumerate(users_to_process, 1):
        user_email = (user.get("email") or user.get("notification_email") or f"user_{idx}").lower().strip()
        user_name = user.get("name") or user_email.split("@")[0].capitalize()
        print("\n--------------------------------------------------")
        print(f"[{idx}/{len(users_to_process)}] Processing Candidate: {user_name} ({user_email})")
        print("--------------------------------------------------")

        try:
            # Prepare user profile dictionary
            profile_dict = dict(user) if user else {}
            profile_dict.setdefault("name", user_name)
            if user:
                profile_dict["current_title"] = user.get("title") or ""
                profile_dict["core_skills"] = user.get("skills") or []
                profile_dict["target_keywords"] = user.get("target_keywords") or []
                profile_dict["target_titles"] = user.get("target_keywords") or []
                profile_dict["exclude_keywords"] = user.get("exclude_keywords") or []
                profile_dict["exclude_titles"] = user.get("exclude_keywords") or []
                profile_dict["education"] = user.get("education") or ""
                profile_dict["years_experience"] = user.get("experience_years") or 0.0

            # Build dynamic per-user filters
            user_filters = dict(cfg.get("filters", {}))
            user_targets = user.get("target_keywords") or []
            if user_targets and isinstance(user_targets, list):
                user_filters["include_titles"] = [t for t in user_targets if t]
            user_excludes = user.get("exclude_keywords") or []
            if user_excludes and isinstance(user_excludes, list):
                user_filters["exclude_titles"] = [t for t in user_excludes if t]

            preferred_locs = user.get("preferred_locations") or []
            if preferred_locs and isinstance(preferred_locs, list):
                user_filters["locations"] = preferred_locs

            job_types = user.get("job_types") or []
            if job_types and isinstance(job_types, list):
                user_filters["job_types"] = job_types

            exp_level = user.get("experience_level") or ""
            if exp_level in ("fresher", "0-1"):
                existing_inc = list(user_filters.get("include_titles", []))
                existing_inc.append(r"\b(fresher|entry.level|graduate|junior|intern|trainee|associate|0.1.year)\b")
                user_filters["include_titles"] = existing_inc
            elif exp_level == "1-3":
                existing_exc = list(user_filters.get("exclude_titles", []))
                existing_exc.append(r"\b(senior|staff|principal|lead|head|director|vp)\b")
                user_filters["exclude_titles"] = existing_exc

            # Stage A: Deterministic pre-filter
            user_candidates = prefilter(raw_jobs, user_filters)
            print(f"  Pre-filtered: {len(raw_jobs)} -> {len(user_candidates)} candidate postings")

            seen_file = cfg.get("seen_file", "state/seen.json")
            st = Store(seen_file, user_email=user_email, use_service_key=True)
            unseen_jobs = st.unseen(user_candidates) if user_candidates else []
            print(
                f"  New unseen jobs to evaluate: {len(unseen_jobs)} (skipping {len(user_candidates) - len(unseen_jobs)} seen)"
            )

            scored_jobs: list[Any] = []
            shortlist: list[Any] = []

            # Determine candidate score threshold
            user_min_score = user.get("min_score_notification")
            effective_threshold = (
                float(user_min_score)
                if user_min_score is not None and str(user_min_score).strip() != ""
                else score_threshold
            )

            if unseen_jobs:
                max_jobs_to_screen = int(os.environ.get("MAX_JOBS_TO_SCREEN") or cfg.get("max_jobs_to_screen", 40))
                if len(unseen_jobs) > max_jobs_to_screen:
                    # Pass 1: Instant keyword pre-ranking across ALL unseen jobs (0.01s)
                    llm.keyword_screen(unseen_jobs, profile_dict)
                    unseen_jobs.sort(key=lambda j: j.score or 0.0, reverse=True)
                    print(
                        f"  [hybrid-rank] Pre-ranked {len(unseen_jobs)} unseen jobs via keyword engine -> selecting top {max_jobs_to_screen} high-relevance roles for LLM screening."
                    )
                    unseen_jobs = unseen_jobs[:max_jobs_to_screen]

                # Pass 2: LLM Frontier Screening with provider-aware rate limiting
                if scorer == "keyword" or mock:
                    llm.keyword_screen(unseen_jobs, profile_dict)
                else:
                    try:
                        provider, model = resolve("screen")
                        print(f"  Screening {len(unseen_jobs)} postings via {provider.name}/{model}...")
                        llm.screen(
                            unseen_jobs,
                            profile_dict,
                            batch_size=int(cfg.get("screen_batch_size", 8)),
                            jd_chars=int(cfg.get("screen_jd_chars", 800)),
                            delay_seconds=float(cfg.get("llm_delay_seconds", 6.0)),
                            max_workers=int(cfg.get("llm_max_workers", 1)),
                        )
                    except Exception as e:
                        print(f"  ! Screening error ({e}). Falling back to keyword matcher...")
                        llm.keyword_screen(unseen_jobs, profile_dict)

                scored_jobs = [j for j in unseen_jobs if j.score is not None]
                shortlist = [j for j in scored_jobs if (j.score or 0) >= effective_threshold]
                if not shortlist and scored_jobs:
                    # Guarantee UI dashboard job board is populated with candidate matches
                    shortlist = [j for j in sorted(scored_jobs, key=lambda x: x.score or 0, reverse=True) if (j.score or 0) >= 5.0]
                shortlist.sort(key=lambda j: j.score or 0, reverse=True)
                shortlist = shortlist[:max_per_digest]
                print(
                    f"  Scored: {len(scored_jobs)} jobs | {len(shortlist)} cleared threshold ({effective_threshold}+)"
                )

                # Stage D: Application kit drafting
                if shortlist and scorer != "keyword" and not mock:
                    try:
                        d_provider, d_model = resolve("draft")
                        print(f"  Drafting application kits via {d_provider.name}/{d_model}...")
                        llm.draft(
                            shortlist,
                            profile_dict,
                            jd_chars=int(cfg.get("draft_jd_chars", 7000)),
                            provider=d_provider,
                            model=d_model,
                            delay_seconds=float(cfg.get("llm_delay_seconds", 6.0)),
                        )
                    except Exception as e:
                        print(f"  ! Drafting error ({e}). Using standard kit drafts.")

                st.record(scored_jobs, emailed=False)
            else:
                if not user_candidates:
                    print("  No candidate matches passed pre-filter for this user.")
                else:
                    print("  All matching jobs were already evaluated in previous runs.")

            # Stage E: Build digest (contains shortlisted jobs or clean zero-match briefing)
            email_enabled = bool(user.get("email_notifications_enabled", False)) or force_send
            target_email = user.get("notification_email") or user_email

            subject, html_content = digest.build(
                shortlist,
                scanned=len(raw_jobs),
                candidates=len(user_candidates),
                stats=st.stats(),
                profile=profile_dict,
            )

            # Stage E.1: Persist exact digest HTML and shortlist metadata to candidate profile in Supabase
            if memory.is_configured:
                try:
                    digest_meta = {
                        "latest_digest_html": html_content,
                        "latest_digest_subject": subject,
                        "latest_digest_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                        "latest_digest_shortlisted": len(shortlist),
                        "latest_digest_job_ids": [j.job_id for j in shortlist],
                    }
                    memory.update_user_profile_json(user_email, digest_meta, use_service_key=True)
                except Exception as e:
                    print(f"  ! Failed to save latest digest HTML in Supabase: {e}")

            # Stage F: Dispatch email briefing if notifications enabled
            dispatched = False
            if email_enabled and has_smtp and not os.environ.get("VERCEL"):
                try:
                    status_desc = f"{len(shortlist)} matches" if shortlist else "0 new matches briefing"
                    print(f"  Dispatching briefing email ({status_desc}) to {target_email}...")
                    mailer.send(subject, html_content, to_email=target_email)
                    dispatched = True
                    dispatched_emails += 1
                    print("  ✓ Email briefing dispatched successfully!")

                    # Mark shortlisted jobs as emailed using the Store helper
                    # (handles Supabase sync atomically in one bulk_upsert call)
                    if shortlist:
                        emailed_count = st.mark_emailed([j.job_id for j in shortlist])
                        print(f"  Marked {emailed_count} jobs as emailed in tracker.")
                except Exception as e:
                    print(f"  ! Email dispatch failed: {e}")

            # Record run history in Supabase PostgreSQL memory
            if memory.is_configured:
                try:
                    run_log_msg = f"Screened {len(unseen_jobs)} new jobs, {len(shortlist)} shortlisted out of {len(raw_jobs)} scanned, email={'sent' if dispatched else 'skipped'}"
                    run_payload = {
                        "scanned": len(raw_jobs),
                        "matched": len(user_candidates),
                        "shortlisted": len(shortlist),
                        "status": "completed",
                        "logs": run_log_msg,
                    }
                    try:
                        memory.record_pipeline_run(user_email, run_payload, use_service_key=True)
                    except TypeError:
                        memory.record_pipeline_run(user_email, run_payload)
                except Exception as e:
                    print(f"  ! Failed to record pipeline run in Supabase: {e}")

            users_processed += 1
            total_matches += len(user_candidates)
            total_shortlisted += len(shortlist)
        except Exception as err:
            print(f"  ! Error processing candidate {user_name} ({user_email}): {err}")
            if memory.is_configured:
                try:
                    fail_payload = {
                        "scanned": len(raw_jobs),
                        "matched": 0,
                        "shortlisted": 0,
                        "status": "failed",
                        "logs": f"Error: {err}",
                    }
                    try:
                        memory.record_pipeline_run(user_email, fail_payload, use_service_key=True)
                    except TypeError:
                        memory.record_pipeline_run(user_email, fail_payload)
                except Exception:
                    pass
            users_processed += 1

    summary: dict[str, Any] = {
        "status": "success",
        "total_jobs_scanned": len(raw_jobs),
        "users_processed": users_processed,
        "total_matches": total_matches,
        "total_shortlisted": total_shortlisted,
        "dispatched_emails": dispatched_emails,
    }

    print("\n" + "=" * 70)
    print(" 🏁 MULTI-USER BATCH EXECUTION COMPLETE")
    print(
        f" Users: {users_processed} | Scanned: {len(raw_jobs)} | Shortlisted: {total_shortlisted} | Emails: {dispatched_emails}"
    )
    print("=" * 70)
    return summary
