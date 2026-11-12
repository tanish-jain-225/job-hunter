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

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
import copy
import hashlib
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any
import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8", errors="replace")

from . import cli, digest, llm, mailer
from .fetch import fetch_all
from .mock import fetch_all_mock
from .memory import SupabaseMemory, merge_db_profile_row
from .prefilter import prefilter
from .providers import _get_active_api_keys, resolve
from .store import Store, extract_seen_archive

ROOT = Path(__file__).resolve().parent.parent

_BATCH_PROFILE_COLUMNS = (
    "email,name,title,experience_years,experience_level,skills,"
    "target_keywords,exclude_keywords,preferred_locations,job_types,education,"
    "email_notifications_enabled,notification_email,min_score_notification,"
    "onboarding_completed,min_salary_lpa,preferred_sectors,profile_json,created_at"
)


def _is_pool_exhausted_error(exc: BaseException) -> bool:
    """Detect shared LLM pool exhaustion (HTTP 429, daily quota, invalid/missing shared keys)."""
    msg = str(exc or "").lower()
    return any(
        tok in msg
        for tok in (
            "429",
            "quota",
            "rate limit",
            "resource_exhausted",
            "no api key",
            "api keys are invalid",
            "all models",
            "cooling down",
        )
    )


def _process_single_user(
    idx: int,
    total_users: int,
    user: dict[str, Any],
    *,
    raw_jobs: list[Any],
    cfg: dict[str, Any],
    memory: SupabaseMemory,
    scorer: str,
    mock: bool,
    force_send: bool,
    score_threshold: float,
    max_per_digest: int,
    has_smtp: bool,
    smtp_session: Any,
    batch_state: dict[str, Any],
) -> tuple[int, int, int]:
    """Process one candidate isolated from other tenants. Returns (matched, shortlisted, emails_sent)."""
    user_email = (user.get("email") or user.get("notification_email") or f"user_{idx}").lower().strip()
    raw_name = str(user.get("name") or "").strip()
    user_name = "" if raw_name.lower() == "candidate" else raw_name
    display_label = user_name or user_email
    print("\n--------------------------------------------------")
    print(f"[{idx}/{total_users}] Processing Candidate: {display_label} ({user_email})")
    print("--------------------------------------------------")

    state_lock: threading.Lock = batch_state["lock"]
    smtp_lock: threading.Lock = batch_state["smtp_lock"]

    try:
        # Prepare user profile dictionary (privacy-first: never infer name from email)
        profile_dict = dict(user) if user else {}
        profile_dict["name"] = user_name
        if user:
            profile_dict["current_title"] = user.get("title") or ""
            profile_dict["core_skills"] = user.get("skills") or []
            profile_dict["target_keywords"] = user.get("target_keywords") or []
            profile_dict["target_titles"] = user.get("target_keywords") or []
            profile_dict["exclude_keywords"] = user.get("exclude_keywords") or []
            profile_dict["exclude_titles"] = user.get("exclude_keywords") or []
            profile_dict["education"] = user.get("education") or ""
            profile_dict["years_experience"] = user.get("experience_years") or 0.0

        # Candidate-specific API key (BYOK: immune to shared pool exhaustion circuit breaker)
        user_dict: dict[str, Any] = user if isinstance(user, dict) else {}
        raw_pjson = user_dict.get("profile_json")
        user_pjson: dict[str, Any] = raw_pjson if isinstance(raw_pjson, dict) else {}
        candidate_api_key = user_dict.get("GEMINI_API_KEY") or user_pjson.get("GEMINI_API_KEY")
        candidate_api_key = str(candidate_api_key).strip() if candidate_api_key else None

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

        # Stage A: Deterministic pre-filter + per-tenant Job isolation when multiple users share the pool
        filtered_refs = prefilter(raw_jobs, user_filters)
        if total_users > 1:
            user_candidates = []
            for orig_job in filtered_refs:
                jc = copy.copy(orig_job)
                jc.draft = dict(orig_job.draft) if getattr(orig_job, "draft", None) else {}
                user_candidates.append(jc)
        else:
            user_candidates = list(filtered_refs)
        print(f"  Pre-filtered: {len(raw_jobs)} -> {len(user_candidates)} candidate postings")

        base_seen_file = cfg.get("seen_file", "state/seen.json")
        if total_users > 1 and memory.is_configured:
            email_digest = hashlib.sha256(user_email.encode("utf-8")).hexdigest()[:12]
            user_seen_file = str(Path(base_seen_file).parent / f"seen_{email_digest}.json")
        else:
            user_seen_file = str(base_seen_file)
        store_archive = extract_seen_archive(user_dict, memory_configured=memory.is_configured)
        st = Store(user_seen_file, user_email=user_email, use_service_key=True, seen_archive=store_archive)
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

        strict_llm = os.environ.get("STRICT_LLM", "").strip().lower() in ("1", "true", "yes")
        with state_lock:
            skip_shared_llm = bool(
                batch_state["shared_llm_exhausted"] and not candidate_api_key and not strict_llm
            )

        if unseen_jobs:
            max_jobs_to_screen = int(os.environ.get("MAX_JOBS_TO_SCREEN") or cfg.get("max_jobs_to_screen", 10))
            if len(unseen_jobs) > max_jobs_to_screen:
                # Pass 1: Instant keyword pre-ranking across ALL unseen jobs (0.01s)
                llm.keyword_screen(unseen_jobs, profile_dict)
                unseen_jobs.sort(key=lambda j: j.score or 0.0, reverse=True)
                print(
                    f"  [hybrid-rank] Pre-ranked {len(unseen_jobs)} unseen jobs via keyword engine -> selecting top {max_jobs_to_screen} high-relevance roles for LLM screening."
                )
                unseen_jobs = unseen_jobs[:max_jobs_to_screen]

            # Pass 2: LLM Frontier Screening with shared-pool circuit breaker
            if scorer == "keyword" or mock:
                llm.keyword_screen(unseen_jobs, profile_dict)
            elif skip_shared_llm:
                print("  [pool-circuit] Shared LLM quota exhausted earlier in batch — using instant keyword matcher...")
                llm.keyword_screen(unseen_jobs, profile_dict)
            else:
                try:
                    provider, model = resolve("screen")
                    print(f"  Screening {len(unseen_jobs)} postings via {provider.name}/{model}...")
                    llm.screen(
                        unseen_jobs,
                        profile_dict,
                        provider=provider,
                        model=model,
                        batch_size=int(cfg.get("screen_batch_size", 10)),
                        jd_chars=int(cfg.get("screen_jd_chars", 800)),
                        delay_seconds=float(cfg.get("llm_delay_seconds", 0.0)),
                        max_workers=int(cfg.get("llm_max_workers", 1)),
                        api_key=candidate_api_key,
                    )
                    if not candidate_api_key and any(j.score is not None for j in unseen_jobs):
                        with state_lock:
                            batch_state["shared_llm_empty_runs"] = 0
                except Exception as e:
                    if strict_llm:
                        raise
                    if not candidate_api_key and _is_pool_exhausted_error(e):
                        with state_lock:
                            batch_state["shared_llm_exhausted"] = True
                    print(f"  ! Screening error ({e}). Falling back to keyword matcher...")
                    llm.keyword_screen(unseen_jobs, profile_dict)

                if not strict_llm and unseen_jobs and not any(j.score is not None for j in unseen_jobs):
                    if not candidate_api_key:
                        with state_lock:
                            batch_state["shared_llm_empty_runs"] += 1
                            if batch_state["shared_llm_empty_runs"] >= 2:
                                batch_state["shared_llm_exhausted"] = True
                    print("  ! LLM screening produced 0 scored jobs. Falling back to keyword matcher...")
                    llm.keyword_screen(unseen_jobs, profile_dict)

            scored_jobs = [j for j in unseen_jobs if j.score is not None]
            shortlist = [j for j in scored_jobs if (j.score or 0) >= effective_threshold]
            shortlist.sort(key=lambda j: j.score or 0, reverse=True)
            shortlist = shortlist[:max_per_digest]
            print(
                f"  Scored: {len(scored_jobs)} jobs | {len(shortlist)} cleared threshold ({effective_threshold}+)"
            )

            # Stage D: Application kit drafting (exclusive to top-1 match meeting score >= 7.5)
            with state_lock:
                skip_draft_pool = bool(
                    batch_state["shared_llm_exhausted"] and not candidate_api_key and not strict_llm
                )
            top_draft = [j for j in shortlist[:1] if (j.score or 0) >= 7.5]
            if top_draft and scorer != "keyword" and not mock and not skip_draft_pool:
                try:
                    d_provider, d_model = resolve("draft")
                    print(f"  Drafting top application kit via {d_provider.name}/{d_model} for #{top_draft[0].job_id}...")
                    llm.draft(
                        top_draft,
                        profile_dict,
                        jd_chars=int(cfg.get("draft_jd_chars", 7000)),
                        provider=d_provider,
                        model=d_model,
                        delay_seconds=float(cfg.get("llm_delay_seconds", 0.0)),
                        api_key=candidate_api_key,
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
        user_mail_mode = str(user.get("mail_mode") or "").strip().lower()
        is_daily_mode = (user_mail_mode == "daily") or (
            bool(user.get("email_notifications_enabled", False)) and user_mail_mode != "onetime"
        )
        email_enabled = is_daily_mode or bool(user.get("email_notifications_enabled", False)) or force_send
        target_email = (user.get("notification_email") or user.get("email") or user_email).strip()

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

        # Stage F: Dispatch email briefing with thread-safe SMTP & upstream daily quota circuit breaker
        dispatched = False
        should_dispatch = (
            is_daily_mode
            or force_send
            or bool(user.get("send_empty_digest"))
            or (email_enabled and bool(shortlist))
        )
        with state_lock:
            smtp_blocked = bool(batch_state["smtp_quota_exhausted"])
        if should_dispatch and smtp_blocked:
            print("  ! SMTP daily quota exhausted earlier in batch — skipping dispatch (digest saved to dashboard).")
        elif should_dispatch and has_smtp and not os.environ.get("VERCEL"):
            try:
                status_desc = f"{len(shortlist)} matches" if shortlist else "0 new matches daily briefing"
                print(f"  Dispatching briefing email ({status_desc}) to {target_email}...")
                with smtp_lock:
                    with state_lock:
                        if batch_state["smtp_quota_exhausted"]:
                            raise RuntimeError("SMTP daily quota exhausted")
                    try:
                        mailer.send(
                            subject,
                            html_content,
                            to_email=target_email,
                            session=smtp_session if isinstance(smtp_session, mailer.SMTPSession) else None,
                        )
                    except TypeError:
                        mailer.send(subject, html_content, to_email=target_email)
                dispatched = True
                print("  [OK] Email briefing dispatched successfully!")

                if shortlist:
                    emailed_count = st.mark_emailed([j.job_id for j in shortlist])
                    print(f"  Marked {emailed_count} jobs as emailed in tracker.")
            except Exception as e:
                if mailer.is_smtp_quota_error(e):
                    with state_lock:
                        batch_state["smtp_quota_exhausted"] = True
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

            try:
                memory.prune_pipeline_runs(user_email, keep_days=30, use_service_key=True)
            except Exception:
                pass

        return len(user_candidates), len(shortlist), 1 if dispatched else 0
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
        return 0, 0, 0


def merge_user_profile(row: dict) -> dict:
    """Merge a Supabase DB row with its profile_json blob. Delegates to the canonical implementation in memory.py."""
    return merge_db_profile_row(row)


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
    print(" JOB HUNTER -- Multi-User Automated Batch Pipeline")
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
            # Admin operation: list ALL user profiles for batch processing using PostgREST pagination.
            # Excludes large resume_text/resume_filename blobs unnecessary for job screening/digesting.
            # This is the ONLY place where use_service_key=True is appropriate —
            # we intentionally bypass RLS here to enumerate all users for the batch run.
            endpoint = f"{memory.url}/rest/v1/user_profiles"
            headers = memory._headers(use_service_key=True)
            page_size = 1000
            offset = 0
            while True:
                params = {
                    "select": _BATCH_PROFILE_COLUMNS,
                    "order": "created_at.asc",
                    "limit": str(page_size),
                    "offset": str(offset),
                }
                if user_email:
                    params["email"] = f"eq.{user_email.lower().strip()}"
                resp = requests.get(endpoint, headers=headers, params=params, timeout=memory.timeout)
                if resp.status_code != 200:
                    print(f"  ! Supabase user query HTTP {resp.status_code}: {resp.text[:300]}")
                    break
                data = resp.json()
                if not isinstance(data, list) or not data:
                    break
                for u in data:
                    merged_u = merge_user_profile(u)
                    if user_email and (merged_u.get("email") or "").lower().strip() != user_email.lower().strip():
                        continue
                    # Include users who completed onboarding or have non-empty profile
                    if merged_u.get("onboarding_completed") or merged_u.get("name") or merged_u.get("skills"):
                        users_to_process.append(merged_u)
                if len(data) < page_size:
                    break
                offset += len(data)
        except Exception as e:
            print(f"  ! Supabase user query error: {e}")

    # Never cross tenant boundaries or use a local fallback for a targeted run.
    if user_email and not users_to_process:
        print(f"  ! Candidate profile not found or incomplete for targeted user: {user_email}")
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

    raw_workers = os.environ.get("MULTI_MAX_WORKERS") or cfg.get("multi_max_workers")
    if raw_workers is not None and str(raw_workers).strip() != "":
        worker_count = max(1, int(raw_workers))
    elif mock or len(users_to_process) <= 1:
        worker_count = 1
    else:
        key_pool_size = max(
            1,
            len(_get_active_api_keys("gemini")),
            len(_get_active_api_keys("groq")),
            len(_get_active_api_keys("anthropic")),
        )
        worker_count = min(12, max(4, key_pool_size * 4))

    batch_state: dict[str, Any] = {
        "lock": threading.Lock(),
        "smtp_lock": threading.Lock(),
        "shared_llm_exhausted": False,
        "shared_llm_empty_runs": 0,
        "smtp_quota_exhausted": False,
    }

    # 3. Process users with persistent thread-safe SMTP session and strict tenant isolation
    smtp_cm = mailer.SMTPSession() if (has_smtp and not os.environ.get("VERCEL")) else nullcontext()
    with smtp_cm as smtp_session:
        total_users = len(users_to_process)
        if worker_count > 1 and total_users > 1:
            with ThreadPoolExecutor(max_workers=min(worker_count, total_users)) as executor:
                futures = [
                    executor.submit(
                        _process_single_user,
                        idx,
                        total_users,
                        user,
                        raw_jobs=raw_jobs,
                        cfg=cfg,
                        memory=memory,
                        scorer=scorer,
                        mock=mock,
                        force_send=force_send,
                        score_threshold=score_threshold,
                        max_per_digest=max_per_digest,
                        has_smtp=has_smtp,
                        smtp_session=smtp_session,
                        batch_state=batch_state,
                    )
                    for idx, user in enumerate(users_to_process, 1)
                ]
                for future in as_completed(futures):
                    matched_c, shortlisted_c, emailed_c = future.result()
                    users_processed += 1
                    total_matches += matched_c
                    total_shortlisted += shortlisted_c
                    dispatched_emails += emailed_c
        else:
            for idx, user in enumerate(users_to_process, 1):
                matched_c, shortlisted_c, emailed_c = _process_single_user(
                    idx,
                    total_users,
                    user,
                    raw_jobs=raw_jobs,
                    cfg=cfg,
                    memory=memory,
                    scorer=scorer,
                    mock=mock,
                    force_send=force_send,
                    score_threshold=score_threshold,
                    max_per_digest=max_per_digest,
                    has_smtp=has_smtp,
                    smtp_session=smtp_session,
                    batch_state=batch_state,
                )
                users_processed += 1
                total_matches += matched_c
                total_shortlisted += shortlisted_c
                dispatched_emails += emailed_c

    summary: dict[str, Any] = {
        "status": "success",
        "total_jobs_scanned": len(raw_jobs),
        "users_processed": users_processed,
        "total_matches": total_matches,
        "total_shortlisted": total_shortlisted,
        "dispatched_emails": dispatched_emails,
    }

    print("\n" + "=" * 70)
    print(" MULTI-USER BATCH EXECUTION COMPLETE")
    print(
        f" Users: {users_processed} | Scanned: {len(raw_jobs)} | Shortlisted: {total_shortlisted} | Emails: {dispatched_emails}"
    )
    print("=" * 70)
    return summary
