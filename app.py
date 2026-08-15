"""Flask Web Dashboard for Job Hunter (job-hunter).

Provides a professional Light/Dark Mode web interface and REST API endpoints:
- GET /              : Interactive web dashboard with digest & job tracker
- GET /api/jobs      : Return tracked jobs JSON with search & status filters
- POST /api/run      : On-demand pipeline execution & email dispatch
- POST /api/applied  : Mark a job ID as applied
- GET /api/digest    : Serve latest out/digest.html briefing
- GET /api/stats     : Return tracker metrics JSON
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobhunt import cli
from jobhunt.store import Store, get_writable_path

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static")
)


@app.route("/")
@app.route("/api/index.py")
def index():
    """Render main Light Mode dashboard with digest & job tracker."""
    return render_template("index.html")


@app.route("/logo.png")
@app.route("/favicon.ico")
def serve_logo():
    logo_path = ROOT / "logo.png"
    if logo_path.is_file():
        return send_file(logo_path, mimetype="image/png")
    return "", 204


@app.errorhandler(Exception)
def handle_exception(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({
            "status": "error",
            "message": e.description or str(e)
        }), e.code
    import traceback
    print("Unhandled Exception in Flask app:\n", traceback.format_exc())
    return jsonify({
        "status": "error",
        "message": f"Internal Error: {str(e)}"
    }), 500


@app.route("/api/stats")
def api_stats():
    """Return tracker stats JSON."""
    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "seen.json")
    st = Store(seen_file)
    return jsonify(st.stats())


@app.route("/api/config")
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

    return jsonify({
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
    })


@app.route("/api/export/csv")
def api_export_csv():
    """Serve job tracker data exported as CSV file download."""
    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "seen.json")
    tracker_csv = cfg.get("tracker_csv", "out/tracker.csv")
    st = Store(seen_file)
    csv_path = st.export_csv(tracker_csv)
    return send_file(
        csv_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name="tracker.csv"
    )


@app.route("/api/jobs")
def api_jobs():
    """Return list of all tracked jobs with filtering and sorting support."""
    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "seen.json")
    st = Store(seen_file)

    status = request.args.get("status", "all").lower()
    ats_filter = request.args.get("ats", "all").lower().strip()
    search = request.args.get("search", "").lower().strip()
    min_score = request.args.get("min_score", type=float)
    sort_by = request.args.get("sort", "date").lower().strip()

    jobs_list = []
    for job_id, data in st.data.items():
        item = {"job_id": job_id, **data}
        job_ats = (item.get("ats") or (job_id.split(":")[0] if ":" in job_id else "custom")).lower()

        # Filter status
        if status == "shortlisted" and (item.get("score") or 0) < 7.0:
            continue
        elif status == "applied" and not item.get("applied"):
            continue
        elif status == "unapplied" and item.get("applied"):
            continue

        # Filter ATS provider
        if ats_filter != "all" and job_ats != ats_filter:
            continue

        # Filter min_score
        if min_score is not None and (item.get("score") or 0) < min_score:
            continue

        # Filter search text
        if search:
            searchable = f"{item.get('company', '')} {item.get('title', '')} {item.get('location', '')} {job_ats}".lower()
            if search not in searchable:
                continue

        jobs_list.append(item)

    # Sort logic
    if sort_by == "score":
        jobs_list.sort(key=lambda j: (j.get("score") if j.get("score") is not None else -1.0, j.get("first_seen", "")), reverse=True)
    elif sort_by == "company":
        jobs_list.sort(key=lambda j: j.get("company", "").lower())
    else:  # default: date
        jobs_list.sort(key=lambda j: j.get("first_seen", ""), reverse=True)

    return jsonify({
        "status": "success",
        "count": len(jobs_list),
        "jobs": jobs_list
    })


@app.route("/api/digest")
def api_digest():
    """Serve latest out/digest.html file or dynamically generate digest from Store data."""
    cfg = cli._cfg(raise_on_error=False)
    digest_file = cfg.get("digest_file", "out/digest.html")
    force_rebuild = request.args.get("t") is not None or request.args.get("force") is not None

    writable_path = get_writable_path(digest_file)
    root_path = ROOT / digest_file

    target = writable_path if writable_path.is_file() else root_path

    if target.is_file() and not force_rebuild:
        return send_file(target, mimetype="text/html")

    # If digest.html does not exist on disk or force rebuild requested, generate on the fly from Store data
    seen_file = cfg.get("seen_file", "seen.json")
    st = Store(seen_file)
    from jobhunt import digest
    from jobhunt.fetch import Job
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
                draft=d.get("draft"),
            )
            jobs_list.append(j)

    subject, html_content = digest.build(
        jobs_list[:7],
        scanned=len(st.data),
        candidates=len(st.data),
        stats=st.stats()
    )
    digest.write(html_content, digest_file)
    return html_content, 200, {"Content-Type": "text/html"}


@app.route("/api/run", methods=["POST"])
def api_run():
    """Trigger job search pipeline on demand."""
    data = request.get_json(silent=True) or {}
    use_mock = bool(data.get("mock", False))
    is_vercel = os.environ.get("VERCEL") == "1" or "VERCEL" in os.environ

    # Force mock mode on Vercel serverless to guarantee response < 0.5s without hitting Vercel 10s execution timeout
    if is_vercel:
        use_mock = True

    cli._load_env()
    smtp_pass = os.environ.get("SMTP_PASS", "")
    send_email = bool(smtp_pass and "your-gmail" not in smtp_pass and "paste-your" not in smtp_pass)

    args = argparse.Namespace(
        config=None,
        mock=use_mock,
        send=send_email if not is_vercel else False,
        scorer="keyword" if use_mock else "llm",
    )

    exit_code = cli.cmd_run(args)
    if exit_code != 0 and not use_mock:
        # LLM fallback to keyword scorer
        fallback_args = argparse.Namespace(
            config=None,
            mock=use_mock,
            send=send_email,
            scorer="keyword",
        )
        exit_code = cli.cmd_run(fallback_args)

    cfg = cli._cfg(raise_on_error=False)
    st = Store(cfg.get("seen_file", "seen.json"))

    if exit_code == 0:
        msg = "Pipeline completed successfully!"
        if is_vercel:
            msg += " (Fast mode on Vercel)"
        return jsonify({
            "status": "success",
            "message": msg,
            "stats": st.stats()
        })
    else:
        return jsonify({
            "status": "error",
            "message": f"Pipeline exited with code {exit_code}"
        }), 500


@app.route("/api/applied", methods=["POST"])
def api_applied():
    """Mark or unmark a job as applied."""
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "").strip()
    action = data.get("action", "mark").lower().strip()

    if not job_id:
        return jsonify({"status": "error", "message": "Job ID is required"}), 400

    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "seen.json")
    tracker_csv = cfg.get("tracker_csv", "out/tracker.csv")
    st = Store(seen_file)

    if action == "unmark":
        success = st.unmark_applied(job_id)
        msg_str = f"Unmarked '{job_id}' as applied."
    else:
        success = st.mark_applied(job_id)
        msg_str = f"Marked '{job_id}' as applied."

    if success:
        st.export_csv(tracker_csv)
        return jsonify({
            "status": "success",
            "message": msg_str,
            "stats": st.stats()
        })
    else:
        return jsonify({
            "status": "error",
            "message": f"Job ID '{job_id}' not found in tracking store."
        }), 404


@app.route("/api/delete", methods=["POST", "DELETE"])
def api_delete():
    """Delete a job entry from the tracking store."""
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "").strip()

    if not job_id:
        return jsonify({"status": "error", "message": "Job ID is required"}), 400

    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "seen.json")
    tracker_csv = cfg.get("tracker_csv", "out/tracker.csv")
    st = Store(seen_file)

    if st.delete_job(job_id):
        st.export_csv(tracker_csv)
        return jsonify({
            "status": "success",
            "message": f"Deleted job '{job_id}'.",
            "stats": st.stats()
        })
    else:
        return jsonify({
            "status": "error",
            "message": f"Job ID '{job_id}' not found in tracking store."
        }), 404


@app.route("/api/jobs/add", methods=["POST"])
def api_jobs_add():
    """Add a new job entry manually to the tracking store."""
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    company = data.get("company", "").strip()

    if not title or not company:
        return jsonify({"status": "error", "message": "Title and Company are required."}), 400

    location = data.get("location", "Remote/Unspecified").strip()
    url = data.get("url", "#").strip()
    ats = data.get("ats", "custom").strip()
    reason = data.get("reason", "Manually added via Dashboard").strip()
    applied = bool(data.get("applied", False))

    try:
        score = float(data.get("score", 7.5))
    except (TypeError, ValueError):
        score = 7.5

    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "seen.json")
    tracker_csv = cfg.get("tracker_csv", "out/tracker.csv")
    st = Store(seen_file)

    job_id = st.add_job(
        title=title,
        company=company,
        location=location,
        url=url,
        ats=ats,
        score=score,
        reason=reason,
        applied=applied,
    )
    st.export_csv(tracker_csv)

    return jsonify({
        "status": "success",
        "message": f"Added job '{title}' ({job_id}).",
        "job_id": job_id,
        "stats": st.stats()
    })


if __name__ == "__main__":
    print("=" * 60)
    print(" 🏹 Job Hunter Web Dashboard (Vercel Ready)")
    print(" Server running at: http://localhost:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
