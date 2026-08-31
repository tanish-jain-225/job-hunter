"""Pipeline execution, real-time synchronization, history, digest, and email test routes."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from flask import Blueprint, jsonify, request, send_file

from ... import cli
from ...auth import require_auth
from ...memory import SupabaseMemory
from ...store import Store, get_writable_path
from ..state import (
    ROOT,
    get_current_user_context,
    get_store_version,
    get_user_pipeline_state,
    set_user_pipeline_state,
)

logger = logging.getLogger(__name__)

pipeline_bp = Blueprint("pipeline", __name__)


@pipeline_bp.route("/api/sync")
@require_auth
def api_sync():
    """High-speed real-time synchronization endpoint for client zero-refresh sync."""
    email, token = get_current_user_context()
    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "seen.json")
    st = Store(seen_file, user_email=email, token=token)

    # Ensure a minimal FK-safe stub exists for new users, then fetch their profile.
    memory = SupabaseMemory(token=token)
    user_profile = None
    if email and memory.is_configured:
        memory._ensure_user_profile_exists(email, token=token)
        user_profile = memory.get_user_profile(email, token=token)
    if not user_profile and not (email and memory.is_configured):
        raw_local = cli._load_profile(cfg, raise_on_error=False) or {}
        if raw_local:
            raw_local.setdefault("onboarding_completed", True)
            user_profile = raw_local

    score_threshold = float(cfg.get("score_threshold", 7.0))
    total_count = len(st.data)
    shortlisted_count = 0
    applied_count = 0
    unapplied_count = 0
    ats_counts: dict[str, int] = {}

    for jid, item in st.data.items():
        score = item.get("score") or 0.0
        applied = bool(item.get("applied"))
        job_ats = (item.get("ats") or (jid.split(":")[0] if ":" in jid else "custom")).lower()

        if score >= score_threshold:
            shortlisted_count += 1

        if applied:
            applied_count += 1
        else:
            unapplied_count += 1

        ats_counts[job_ats] = ats_counts.get(job_ats, 0) + 1

    stats = {
        "tracked": total_count,
        "emailed": sum(1 for v in st.data.values() if v.get("emailed")),
        "applied": applied_count,
        "unapplied": unapplied_count,
        "shortlisted": shortlisted_count,
    }

    # Fetch active in-memory pipeline state or sync latest remote run from Supabase
    pipe_state = get_user_pipeline_state(email)
    dispatched_at = pipe_state.get("dispatched_at") or 0

    if email and memory.is_configured:
        try:
            recent_runs = memory.get_pipeline_history(email, limit=1, token=token)
            if recent_runs and isinstance(recent_runs, list) and len(recent_runs) > 0:
                last_run = recent_runs[0]
                run_ts_raw = str(last_run.get("run_timestamp") or "")

                # Check if this run occurred after the latest on-demand dispatch
                is_newer = False
                if run_ts_raw and dispatched_at:
                    try:
                        from datetime import datetime

                        clean_ts = run_ts_raw.replace("Z", "+00:00")
                        run_dt = datetime.fromisoformat(clean_ts).timestamp()
                        if run_dt >= (dispatched_at - 5):  # 5s clock skew tolerance
                            is_newer = True
                    except Exception:
                        is_newer = True
                elif not dispatched_at:
                    is_newer = False

                if is_newer:
                    run_logs = (
                        last_run.get("logs")
                        or f"Cloud Radar completed: {last_run.get('shortlisted', 0)} shortlisted out of {last_run.get('jobs_scanned', 0)} scanned."
                    )
                    pipe_state["last_remote_run"] = run_ts_raw
                    pipe_state["running"] = False
                    pipe_state["step"] = "completed"
                    pipe_state["message"] = run_logs
                    pipe_state.pop("dispatched_at", None)
                    set_user_pipeline_state(email, running=False, step="completed", message=run_logs)
                elif pipe_state.get("running"):
                    # Check GitHub Actions API for live workflow execution state
                    gh_token = (
                        os.environ.get("GH_TOKEN")
                        or os.environ.get("GITHUB_TOKEN")
                        or os.environ.get("GITHUB_PAT")
                        or ""
                    ).strip()
                    if gh_token:
                        try:
                            import requests

                            v_owner = os.environ.get("VERCEL_GIT_REPO_OWNER")
                            v_slug = os.environ.get("VERCEL_GIT_REPO_SLUG")
                            v_repo = f"{v_owner}/{v_slug}" if (v_owner and v_slug) else None
                            repo_name = (
                                os.environ.get("GITHUB_REPOSITORY") or v_repo or "tanish-jain-225/job-hunter"
                            ).strip()
                            gh_url = (
                                f"https://api.github.com/repos/{repo_name}/actions/workflows/daily.yml/runs?per_page=1"
                            )
                            gh_headers = {
                                "Authorization": f"Bearer {gh_token}",
                                "Accept": "application/vnd.github+json",
                                "User-Agent": "Job-Hunter-Web-App",
                            }
                            gh_r = requests.get(gh_url, headers=gh_headers, timeout=4)
                            if gh_r.status_code == 200:
                                runs_data = gh_r.json().get("workflow_runs", [])
                                if runs_data:
                                    top_run = runs_data[0]
                                    run_created_raw = str(
                                        top_run.get("run_started_at") or top_run.get("created_at") or ""
                                    )
                                    is_gh_newer = True
                                    if run_created_raw and dispatched_at:
                                        try:
                                            from datetime import datetime

                                            clean_gh_ts = run_created_raw.replace("Z", "+00:00")
                                            gh_dt = datetime.fromisoformat(clean_gh_ts).timestamp()
                                            if gh_dt < (dispatched_at - 10):
                                                is_gh_newer = False
                                        except Exception:
                                            pass

                                    if not is_gh_newer:
                                        pipe_state["running"] = True
                                        pipe_state["step"] = "running"
                                        pipe_state["message"] = (
                                            "Cloud Radar: Workflow dispatching in GitHub Actions cloud..."
                                        )
                                    else:
                                        gh_status = top_run.get("status")  # queued, in_progress, completed
                                        gh_conclusion = top_run.get("conclusion")  # success, failure, etc.
                                        if gh_status in ("queued", "in_progress"):
                                            pipe_state["running"] = True
                                            pipe_state["step"] = "running"
                                            pipe_state["message"] = (
                                                f"Cloud Radar ({gh_status}): Crawling 100+ ATS company boards in GitHub Actions cloud..."
                                            )
                                        elif gh_status == "completed":
                                            if gh_conclusion == "success":
                                                pipe_state["running"] = False
                                                pipe_state["step"] = "completed"
                                                pipe_state["message"] = (
                                                    "Cloud Radar completed! 100+ company boards crawled and candidate fits evaluated."
                                                )
                                                pipe_state.pop("dispatched_at", None)
                                                set_user_pipeline_state(
                                                    email,
                                                    running=False,
                                                    step="completed",
                                                    message=pipe_state["message"],
                                                )
                                            else:
                                                pipe_state["running"] = False
                                                pipe_state["step"] = "error"
                                                pipe_state["message"] = (
                                                    f"GitHub Actions completed with status: {gh_conclusion}"
                                                )
                                                pipe_state.pop("dispatched_at", None)
                                                set_user_pipeline_state(
                                                    email, running=False, step="error", message=pipe_state["message"]
                                                )
                        except Exception:
                            pass
        except Exception:
            pass

    version = get_store_version(st)

    return jsonify(
        {
            "status": "success",
            "version": version,
            "stats": stats,
            "ats_counts": ats_counts,
            "pipeline": pipe_state,
            "user_email": email,
            "user_profile": user_profile,
            "memory_connected": memory.is_configured,
            "timestamp": time.time(),
        }
    )


@pipeline_bp.route("/api/digest")
@require_auth
def api_digest():
    """Serve latest out/digest.html file or dynamically generate personalized digest from Store data."""
    email, token = get_current_user_context()
    cfg = cli._cfg(raise_on_error=False)
    digest_file = cfg.get("digest_file", "out/digest.html")
    force_rebuild = (
        request.args.get("t") is not None
        or request.args.get("force") is not None
        or request.args.get("live") is not None
    )

    seen_file = cfg.get("seen_file", "seen.json")
    st = Store(seen_file, user_email=email, token=token)

    writable_path = get_writable_path(digest_file)
    root_path = ROOT / digest_file
    target = writable_path if writable_path.is_file() else root_path

    # If force_rebuild or file does not exist, build live personalized digest
    if not target.is_file() or force_rebuild:
        from ... import digest
        from ...fetch import Job

        jobs_list = []
        for jid, d in st.data.items():
            if (d.get("score") or 0) >= 7.0 and not d.get("applied"):
                j = Job(
                    job_id=jid,
                    ats=jid.split(":")[0] if ":" in jid else "jobhunt",
                    company=d.get("company", ""),
                    title=d.get("title", ""),
                    location=d.get("location", ""),
                    url=d.get("url", "#"),
                    description="",
                    score=d.get("score"),
                    reason=d.get("reason"),
                    draft=d.get("draft") or {},
                )
                jobs_list.append(j)

        # Sort shortlist by score descending
        jobs_list.sort(key=lambda x: x.score if x.score is not None else -1.0, reverse=True)

        memory = SupabaseMemory(token=token)
        profile_data = None
        scanned_count = len(st.data)
        candidates_count = len(st.data)

        if email and memory.is_configured:
            remote_profile = memory.get_user_profile(email, token=token)
            if remote_profile:
                profile_data = remote_profile.get("profile_json") or remote_profile
            recent_runs = memory.get_pipeline_history(email, limit=1, token=token)
            if recent_runs and isinstance(recent_runs, list) and len(recent_runs) > 0:
                latest_run = recent_runs[0]
                if latest_run.get("jobs_scanned"):
                    scanned_count = int(latest_run["jobs_scanned"])
                if latest_run.get("candidates_matched"):
                    candidates_count = int(latest_run["candidates_matched"])

        if not profile_data:
            profile_data = cli._load_profile(cfg, raise_on_error=False)

        subject, html_content = digest.build(
            jobs_list[:7],
            scanned=scanned_count,
            candidates=candidates_count,
            stats=st.stats(),
            profile=profile_data,
        )
        try:
            digest.write(html_content, digest_file)
        except Exception:
            pass
        return html_content, 200, {"Content-Type": "text/html"}

    return send_file(str(Path(target).resolve()), mimetype="text/html")


@pipeline_bp.route("/api/run", methods=["POST"])
@require_auth
def api_run():
    """Trigger job search pipeline with personalized user criteria and email notification toggle.

    Rate limited to 5 calls/hour/IP (when flask-limiter is installed) to protect
    free-tier LLM quota from runaway clients or accidental retry loops.
    """
    from flask import current_app

    limiter = current_app.extensions.get("limiter")
    if limiter:
        try:
            limiter.limit("5 per hour")(lambda: None)()
        except Exception:
            # If rate limit exceeded, flask-limiter raises 429 automatically.
            # Any other exception means limiter is misconfigured — skip silently.
            pass
    data = request.get_json(silent=True) or {}
    use_mock = bool(data.get("mock", False))
    is_vercel = os.environ.get("VERCEL") == "1"

    email, token = get_current_user_context()
    cli._load_env()
    memory = SupabaseMemory(token=token)

    now_utc = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    set_user_pipeline_state(
        email,
        running=True,
        step="running",
        message="Scanning ATS boards and fetching job listings...",
        last_run=now_utc,
    )

    # Check user's candidate profile & email notification toggle preference
    user_profile = None
    if email and memory.is_configured:
        user_profile = memory.get_user_profile(email, token=token)
    if not user_profile:
        if not (email and memory.is_configured):
            cfg_temp = cli._cfg(raise_on_error=False)
            user_profile = cli._load_profile(cfg_temp, raise_on_error=False)

    # Guard: block pipeline if candidate profile is still empty/incomplete
    profile_is_stub = not user_profile or (
        not bool(user_profile.get("onboarding_completed"))
        and not (user_profile.get("name") or "").strip()
        and not (user_profile.get("skills") or [])
        and not (user_profile.get("target_keywords") or [])
    )
    if profile_is_stub:
        set_user_pipeline_state(
            email,
            running=False,
            step="idle",
            exit_code=0,
            message="System ready. Click 'Run Job Hunt Now' to start scanning.",
        )
        return jsonify(
            {
                "status": "error",
                "message": "Please complete your candidate profile before running the job hunt pipeline.",
            }
        ), 400

    target_email = email or ""
    if user_profile:
        target_email = user_profile.get("notification_email") or email or ""

    profile_dict = dict(user_profile) if user_profile else {}
    if user_profile:
        profile_dict["current_title"] = user_profile.get("title") or ""
        profile_dict["core_skills"] = user_profile.get("skills") or []
        profile_dict["target_keywords"] = user_profile.get("target_keywords") or []
        profile_dict["target_titles"] = user_profile.get("target_keywords") or []
        profile_dict["exclude_keywords"] = user_profile.get("exclude_keywords") or []
        profile_dict["exclude_titles"] = user_profile.get("exclude_keywords") or []
        profile_dict["education"] = user_profile.get("education") or ""
        profile_dict["years_experience"] = user_profile.get("experience_years") or 0.0
        if email:
            profile_dict["email"] = email

    smtp_pass = os.environ.get("SMTP_PASS", "")
    has_smtp = bool(smtp_pass and "your-gmail" not in smtp_pass and "paste-your" not in smtp_pass)
    # Manual on-demand scan: always dispatch on-the-spot email briefing when SMTP is configured (even in One-Time Mode)
    send_email = bool(has_smtp and target_email and not is_vercel)

    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "seen.json")
    st = Store(seen_file, user_email=email, token=token)

    gh_token = (
        os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_PAT") or ""
    ).strip()
    v_owner = os.environ.get("VERCEL_GIT_REPO_OWNER")
    v_slug = os.environ.get("VERCEL_GIT_REPO_SLUG")
    v_repo = f"{v_owner}/{v_slug}" if (v_owner and v_slug) else None
    repo_name = (os.environ.get("GITHUB_REPOSITORY") or v_repo or "tanish-jain-225/job-hunter").strip()

    # Option 1: If on Vercel or cloud requested and GH_TOKEN is provided, trigger GitHub Actions workflow directly
    prefer_cloud = is_vercel or bool(data.get("cloud", False))
    if prefer_cloud and gh_token and not use_mock:
        try:
            import requests

            gh_url = f"https://api.github.com/repos/{repo_name}/actions/workflows/daily.yml/dispatches"
            gh_headers = {
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Job-Hunter-Web-App",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            gh_payload = {"ref": "main", "inputs": {"mode": "multi"}}
            gh_resp = requests.post(gh_url, json=gh_payload, headers=gh_headers, timeout=8)
            if gh_resp.status_code in (200, 204):
                msg = "Autonomous Radar dispatched to GitHub Actions! Crawling 100+ company boards in the cloud..."
                dispatched_time = time.time()
                set_user_pipeline_state(
                    email,
                    running=True,
                    step="running",
                    message=msg,
                    last_run=now_utc,
                )
                pipe_st = get_user_pipeline_state(email)
                pipe_st["dispatched_at"] = dispatched_time
                return jsonify(
                    {
                        "status": "dispatched",
                        "mode": "github_actions",
                        "message": msg,
                        "dispatched_at": dispatched_time,
                        "pipeline": pipe_st,
                        "version": get_store_version(st),
                        "stats": st.stats(),
                    }
                ), 200
            else:
                logger.warning("GitHub workflow_dispatch returned %s: %s", gh_resp.status_code, gh_resp.text)
        except Exception as gh_err:
            logger.warning("GitHub workflow dispatch request failed: %s", gh_err)

    # If on Vercel without GH_TOKEN and not in mock mode, guide user to GitHub Actions
    if is_vercel and not gh_token and not use_mock:
        gh_actions_url = f"https://github.com/{repo_name}/actions/workflows/daily.yml"
        msg = "Cloud Radar: GitHub Actions is ready to crawl 100+ live boards. Triggering workflow..."
        return jsonify(
            {
                "status": "need_github_dispatch",
                "mode": "github_actions",
                "message": msg,
                "actions_url": gh_actions_url,
                "pipeline": get_user_pipeline_state(email),
                "version": get_store_version(st),
                "stats": st.stats(),
            }
        ), 200

    # Build custom_filters from user's search preferences
    custom_filters = {}
    if user_profile:
        preferred_locs = user_profile.get("preferred_locations") or []
        job_types = user_profile.get("job_types") or []
        exp_level = user_profile.get("experience_level") or ""

        # Location filter: if user set preferred locations, use them; otherwise all-India open
        if preferred_locs:
            custom_filters["locations"] = preferred_locs
        # else: leave empty = accept all locations

        # Job types filter
        if job_types:
            custom_filters["job_types"] = job_types
        # else: accept all types

        # Experience level → inject into include/exclude patterns
        if exp_level == "fresher" or exp_level == "0-1":
            # Only include entry-level / fresher / internship roles
            existing_inc = list(custom_filters.get("include_titles", []))
            existing_inc.extend([r"\b(fresher|entry.level|graduate|junior|intern|trainee|associate|0.1.year)\b"])
            custom_filters["include_titles"] = existing_inc
        elif exp_level == "1-3":
            existing_exc = list(custom_filters.get("exclude_titles", []))
            existing_exc.append(r"\b(senior|staff|principal|lead|head|director|vp)\b")
            custom_filters["exclude_titles"] = existing_exc

    def worker():
        try:
            exit_code = cli.run_pipeline(
                profile=profile_dict,
                user_email=email,
                token=token,
                store=st,
                to_email=target_email,
                send=send_email,
                scorer="keyword" if use_mock else "llm",
                mock=use_mock,
                custom_filters=custom_filters if custom_filters else None,
            )
            if exit_code != 0 and not use_mock:
                exit_code = cli.run_pipeline(
                    profile=profile_dict,
                    user_email=email,
                    token=token,
                    store=st,
                    to_email=target_email,
                    send=send_email,
                    scorer="keyword",
                    mock=use_mock,
                    custom_filters=custom_filters if custom_filters else None,
                )
        except Exception as e:
            exit_code = 1
            set_user_pipeline_state(
                email,
                running=False,
                step="error",
                message=f"Pipeline failed: {str(e)}",
                exit_code=1,
            )
            return

        if exit_code == 0:
            msg = "Pipeline completed successfully!"
            if is_vercel:
                msg += " (Fast mode on Vercel)"
            set_user_pipeline_state(
                email,
                running=False,
                step="completed",
                message=msg,
                exit_code=0,
            )
            try:
                st.export_csv(cfg.get("tracker_csv", "out/tracker.csv"))
            except Exception:
                pass
        else:
            set_user_pipeline_state(
                email,
                running=False,
                step="error",
                message=f"Pipeline exited with code {exit_code}",
                exit_code=exit_code,
            )

    from flask import current_app
    import threading

    is_testing = current_app.testing or bool(data.get("sync")) or is_vercel
    if is_testing:
        worker()
        version = get_store_version(st)
        p_state = get_user_pipeline_state(email)
        if p_state.get("exit_code") == 0:
            return jsonify(
                {
                    "status": "success",
                    "message": p_state.get("message"),
                    "version": version,
                    "stats": st.stats(),
                    "pipeline": p_state,
                }
            )
        else:
            return jsonify(
                {
                    "status": "error",
                    "message": p_state.get("message"),
                    "version": version,
                    "pipeline": p_state,
                }
            ), 500
    else:
        t = threading.Thread(target=worker, daemon=True)
        t.start()
        return jsonify(
            {
                "status": "success",
                "message": "Pipeline execution started in background.",
                "version": get_store_version(st),
                "stats": st.stats(),
                "pipeline": get_user_pipeline_state(email),
            }
        ), 202


@pipeline_bp.route("/api/history")
@require_auth
def api_history():
    """Return past pipeline runs and execution memory for the authenticated user."""
    email, token = get_current_user_context()
    memory = SupabaseMemory(token=token)
    history = []
    if email and memory.is_configured:
        history = memory.get_pipeline_history(email, limit=15, token=token)

    return jsonify({"status": "success", "email": email, "history": history})


@pipeline_bp.route("/api/email/test", methods=["POST"])
@require_auth
def api_email_test():
    """Send a live test career briefing email to verify SMTP delivery."""
    email, token = get_current_user_context()
    cfg = cli._cfg(raise_on_error=False)
    memory = SupabaseMemory(token=token)

    user_profile = None
    if email and memory.is_configured:
        user_profile = memory.get_user_profile(email, token=token)
    if not user_profile:
        user_profile = cli._load_profile(cfg, raise_on_error=False)

    target_email = ""
    if user_profile:
        target_email = user_profile.get("notification_email") or email or ""
    if not target_email:
        target_email = email or os.environ.get("MAIL_TO", "")

    if not target_email:
        return jsonify({"status": "error", "message": "No destination email address found in profile."}), 400

    smtp_pass = os.environ.get("SMTP_PASS", "")
    if not smtp_pass or "your-gmail" in smtp_pass or "paste-your" in smtp_pass:
        return jsonify(
            {
                "status": "error",
                "message": "SMTP is not configured on the server. Please set SMTP_USER and SMTP_PASS in .env",
            }
        ), 400

    from ... import digest, mailer
    from ...fetch import Job

    demo_job = Job(
        job_id="test:sample:101",
        ats="greenhouse",
        company="Razorpay",
        title="Software Engineer, Core Infrastructure",
        location="Bengaluru, India (Hybrid)",
        url="https://razorpay.com/jobs",
        description="Core Infrastructure and Distributed Systems engineering.",
        score=9.2,
        reason="Direct match for distributed systems, Go, and high throughput APIs.",
        draft={
            "fit_summary": "Top match for candidate background with direct alignment on distributed services.",
            "india_eligibility": "Verified India-Friendly",
            "best_project": "Distributed Systems & API Platform",
            "tailored_bullets": [
                "Engineered high-throughput backend services handling thousands of RPS.",
                "Optimized SQL query latency and automated CI/CD deployment pipelines.",
            ],
            "matching_skills": ["Python", "Go", "PostgreSQL", "Docker", "REST APIs"],
            "gaps": ["Review specific cloud architecture requirements."],
            "cover_note": "Hi Hiring Team, I am reaching out regarding the Software Engineer opening at Razorpay. My background in building high-throughput backend services aligns directly with your infrastructure requirements.",
            "cold_outreach": "Hi! Saw your Software Engineer role at Razorpay. Built scalable backend systems and distributed services. Would love to connect!",
            "questions_to_ask": ["What are the primary latency and scale milestones for this team?"],
        },
    )

    subject, html_content = digest.build(
        [demo_job],
        scanned=10,
        candidates=5,
        stats={"tracked": 1, "emailed": 1, "applied": 0},
        profile=user_profile or {},
    )

    try:
        mailer.send(f"[Test Briefing] {subject}", html_content, to_email=target_email)
        return jsonify(
            {
                "status": "success",
                "message": f"Test briefing successfully sent to {target_email}!",
                "target_email": target_email,
            }
        )
    except Exception as e:
        return jsonify({"status": "error", "message": f"SMTP delivery failed: {str(e)}"}), 500
