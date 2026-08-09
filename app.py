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

from flask import Flask, jsonify, render_template_string, request, send_file

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jobhunt import cli
from jobhunt.store import Store, get_writable_path

app = Flask(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Job Hunter Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --border: #e2e8f0;
      --border-hover: #cbd5e1;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --primary: #4f46e5;
      --primary-hover: #4338ca;
      --success: #059669;
      --success-bg: #ecfdf5;
      --warning: #d97706;
      --shadow-sm: 0 1px 2px 0 rgba(15, 23, 42, 0.05);
      --shadow-md: 0 4px 6px -1px rgba(15, 23, 42, 0.06), 0 2px 4px -2px rgba(15, 23, 42, 0.04);
      --shadow-lg: 0 10px 15px -3px rgba(15, 23, 42, 0.08), 0 4px 6px -4px rgba(15, 23, 42, 0.03);
      --radius: 12px;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background-color: var(--bg);
      color: var(--text-main);
      line-height: 1.5;
      padding: 24px;
      max-width: 1280px;
      margin: 0 auto;
    }

    /* Header */
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: var(--card-bg);
      padding: 20px 28px;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      box-shadow: var(--shadow-sm);
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 16px;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-icon {
      font-size: 28px;
      background: #e0e7ff;
      width: 48px;
      height: 48px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 10px;
    }
    .brand h1 {
      font-size: 22px;
      font-weight: 700;
      color: var(--text-main);
      letter-spacing: -0.02em;
    }
    .brand p {
      font-size: 13px;
      color: var(--text-muted);
    }

    /* Metrics Pills */
    .metrics {
      display: flex;
      gap: 12px;
    }
    .metric-pill {
      background: #f1f5f9;
      border: 1px solid var(--border);
      padding: 8px 16px;
      border-radius: 8px;
      text-align: center;
      min-width: 100px;
    }
    .metric-val {
      font-size: 18px;
      font-weight: 700;
      color: var(--primary);
    }
    .metric-label {
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 600;
      color: var(--text-muted);
      letter-spacing: 0.05em;
    }

    /* Grid Layout */
    .grid {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 24px;
    }
    @media (max-width: 900px) {
      .grid { grid-template-columns: 1fr; }
    }

    /* Card */
    .card {
      background: var(--card-bg);
      border-radius: var(--radius);
      border: 1px solid var(--border);
      box-shadow: var(--shadow-sm);
      padding: 24px;
      margin-bottom: 24px;
    }
    .card-title {
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--text-main);
    }

    /* Buttons & Controls */
    .btn {
      width: 100%;
      background: var(--primary);
      color: #ffffff;
      border: none;
      padding: 12px 20px;
      font-size: 14px;
      font-weight: 600;
      border-radius: 8px;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      transition: all 0.15s ease-in-out;
      box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);
    }
    .btn:hover {
      background: var(--primary-hover);
      box-shadow: 0 4px 8px rgba(79, 70, 229, 0.3);
      transform: translateY(-1px);
    }
    .btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none;
    }
    .btn-secondary {
      background: #ffffff;
      color: var(--text-main);
      border: 1px solid var(--border);
      box-shadow: var(--shadow-sm);
      width: auto;
    }
    .btn-secondary:hover {
      background: #f8fafc;
      border-color: var(--border-hover);
      box-shadow: var(--shadow-md);
    }
    .btn-sm {
      padding: 6px 12px;
      font-size: 12px;
      border-radius: 6px;
    }
    .btn-applied {
      background: #ecfdf5;
      color: #059669;
      border: 1px solid #a7f3d0;
    }

    .form-group { margin-bottom: 16px; }
    .form-label {
      display: block;
      font-size: 13px;
      font-weight: 500;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    .form-input {
      width: 100%;
      padding: 10px 14px;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 14px;
      outline: none;
      transition: border-color 0.15s;
    }
    .form-input:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
    }

    .checkbox-label {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--text-muted);
      cursor: pointer;
      user-select: none;
    }

    /* Console */
    .console {
      background: #f1f5f9;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      font-family: ui-monospace, monospace;
      font-size: 12px;
      color: #334155;
      max-height: 140px;
      overflow-y: auto;
      margin-top: 16px;
      white-space: pre-wrap;
    }

    /* Viewport Tabs */
    .tab-bar {
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 16px;
    }
    .tab-btn {
      padding: 10px 18px;
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      font-size: 14px;
      font-weight: 600;
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.15s;
    }
    .tab-btn:hover { color: var(--text-main); }
    .tab-btn.active {
      color: var(--primary);
      border-bottom-color: var(--primary);
    }

    .viewport-frame {
      width: 100%;
      height: 780px;
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: #ffffff;
      box-shadow: var(--shadow-sm);
    }

    /* Board Table */
    .tracker-bar {
      display: flex;
      gap: 12px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    .tracker-search { flex: 1; min-width: 200px; }
    .filter-pills { display: flex; gap: 6px; }
    .pill {
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      background: #f1f5f9;
      color: var(--text-muted);
      border: 1px solid var(--border);
      cursor: pointer;
    }
    .pill.active {
      background: var(--primary);
      color: #ffffff;
      border-color: var(--primary);
    }

    .job-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
      max-height: 720px;
      overflow-y: auto;
      padding-right: 4px;
    }
    .job-item {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .job-item:hover {
      border-color: var(--border-hover);
      box-shadow: var(--shadow-sm);
    }
    .job-meta { flex: 1; }
    .job-title {
      font-size: 15px;
      font-weight: 700;
      color: var(--text-main);
      margin-bottom: 4px;
    }
    .job-sub {
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 8px;
    }
    .job-reason {
      font-size: 12px;
      color: #475569;
      background: #f8fafc;
      padding: 8px 10px;
      border-radius: 6px;
      border: 1px solid #f1f5f9;
    }
    .score-badge {
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      min-width: 42px;
      text-align: center;
    }
    .score-high { background: #dcfce7; color: #166534; }
    .score-mid { background: #fef9c3; color: #854d0e; }
    .score-low { background: #f1f5f9; color: #475569; }

    .job-actions {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 8px;
    }

    /* Spinner */
    .spinner {
      width: 16px;
      height: 16px;
      border: 2px solid #ffffff;
      border-top-color: transparent;
      border-radius: 50%;
      animation: spin 0.6s linear infinite;
      display: none;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>

  <!-- Top Navigation Header -->
  <header>
    <div class="brand">
      <div class="brand-icon">🏹</div>
      <div>
        <h1>Job Hunter</h1>
        <p>Autonomous AI Job-Search Web Board</p>
      </div>
    </div>
    <div class="metrics">
      <div class="metric-pill">
        <div class="metric-val" id="metric-tracked">--</div>
        <div class="metric-label">Tracked</div>
      </div>
      <div class="metric-pill">
        <div class="metric-val" id="metric-emailed">--</div>
        <div class="metric-label">Emailed</div>
      </div>
      <div class="metric-pill">
        <div class="metric-val" id="metric-applied">--</div>
        <div class="metric-label">Applied</div>
      </div>
    </div>
  </header>

  <!-- Main Grid -->
  <div class="grid">

    <!-- Sidebar Controls -->
    <div>

      <!-- Run Pipeline Card -->

      <div class="card">
        <div class="card-title">🚀 On-Demand Pipeline Trigger</div>
        <div class="form-group">
          <label class="checkbox-label">
            <input type="checkbox" id="chk-mock">
            Run with offline mock fixtures (--mock)
          </label>
        </div>
        <button class="btn" id="btn-run" onclick="runPipeline()">
          <span class="spinner" id="run-spinner"></span>
          <span id="run-text">Run Job Hunt Now</span>
        </button>
        <div class="console" id="run-console">System ready. Click 'Run Job Hunt Now' to start scanning.</div>
      </div>

      <!-- Quick Mark Applied Card -->
      <div class="card">
        <div class="card-title">📌 Quick Mark Applied</div>
        <div class="form-group">
          <label class="form-label" for="txt-job-id">Job ID (ats:company:id)</label>
          <input type="text" class="form-input" id="txt-job-id" placeholder="e.g. greenhouse:stripe:5501001">
        </div>
        <button class="btn btn-secondary" style="width:100%;" onclick="markAppliedFromInput()">Mark as Applied</button>
        <div id="applied-status" style="font-size:12px; margin-top:8px; color:var(--text-muted);"></div>
      </div>

    </div>

    <!-- Main Board Viewport -->
    <div>
      <div class="tab-bar">
        <button class="tab-btn active" id="tab-btn-digest" onclick="switchTab('digest')">📬 Daily Digest Briefing</button>
        <button class="tab-btn" id="tab-btn-tracker" onclick="switchTab('tracker')">📋 Interactive Job Board</button>
      </div>

      <!-- Tab 1: Digest Viewport -->
      <div id="tab-content-digest">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
          <span style="font-size:13px; color:var(--text-muted);">Latest generated HTML digest briefing preview</span>
          <div style="display:flex; gap:8px;">
            <button class="btn btn-secondary btn-sm" onclick="refreshDigest()">🔄 Refresh Digest</button>
            <a href="/api/digest" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration:none;">↗ Open Full Tab</a>
          </div>
        </div>
        <iframe class="viewport-frame" id="digest-frame" src="/api/digest"></iframe>
      </div>

      <!-- Tab 2: Tracker Board -->
      <div id="tab-content-tracker" style="display:none;">
        <div class="tracker-bar">
          <input type="text" class="form-input tracker-search" id="tracker-search-input"
                 placeholder="Search company, title, or location..." oninput="fetchAndRenderJobs()">
          <div class="filter-pills">
            <button class="pill active" id="pill-all" onclick="setFilter('all')">All Jobs</button>
            <button class="pill" id="pill-shortlisted" onclick="setFilter('shortlisted')">Shortlisted (7.0+)</button>
            <button class="pill" id="pill-applied" onclick="setFilter('applied')">Applied</button>
          </div>
        </div>
        <div class="job-list" id="job-list-container">
          <div style="text-align:center; padding:40px; color:var(--text-muted);">Loading job board data...</div>
        </div>
      </div>

    </div>

  </div>

  <script>
    let currentFilter = 'all';

    async function loadStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await res.json();
        document.getElementById('metric-tracked').innerText = data.tracked ?? 0;
        document.getElementById('metric-emailed').innerText = data.emailed ?? 0;
        document.getElementById('metric-applied').innerText = data.applied ?? 0;
      } catch (err) {
        console.error('Failed to load stats', err);
      }
    }

    function switchTab(tab) {
      document.getElementById('tab-content-digest').style.display = tab === 'digest' ? 'block' : 'none';
      document.getElementById('tab-content-tracker').style.display = tab === 'tracker' ? 'block' : 'none';

      document.getElementById('tab-btn-digest').classList.toggle('active', tab === 'digest');
      document.getElementById('tab-btn-tracker').classList.toggle('active', tab === 'tracker');


      if (tab === 'tracker') {
        fetchAndRenderJobs();
      }
    }

    function setFilter(filter) {
      currentFilter = filter;
      document.querySelectorAll('.filter-pills .pill').forEach(el => el.classList.remove('active'));
      document.getElementById('pill-' + filter).classList.add('active');
      fetchAndRenderJobs();
    }

    async function fetchAndRenderJobs() {
      const container = document.getElementById('job-list-container');
      const search = document.getElementById('tracker-search-input').value.trim();

      try {
        const url = `/api/jobs?status=${encodeURIComponent(currentFilter)}&search=${encodeURIComponent(search)}`;
        const res = await fetch(url);
        const data = await res.json();

        if (data.status !== 'success' || !data.jobs || data.jobs.length === 0) {
          container.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-muted);">No matching jobs found in tracking store.</div>';
          return;
        }

        container.innerHTML = data.jobs.map(j => {
          const score = j.score != null ? Number(j.score).toFixed(1) : 'N/A';
          const scoreClass = j.score >= 8.5 ? 'score-high' : (j.score >= 7.0 ? 'score-mid' : 'score-low');
          const isApplied = Boolean(j.applied);

          return `
            <div class="job-item">
              <div class="job-meta">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="job-title">${escapeHtml(j.title)}</span>
                </div>
                <div class="job-sub">
                  <strong>${escapeHtml(j.company)}</strong> · ${escapeHtml(j.location || 'Remote/Unspecified')}
                </div>
                ${j.reason ? `<div class="job-reason">💡 ${escapeHtml(j.reason)}</div>` : ''}
              </div>
              <div class="job-actions">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="score-badge ${scoreClass}">${score}</span>
                  ${isApplied
                    ? `<button class="btn btn-secondary btn-sm btn-applied" disabled>✓ Applied</button>`

                    : `<button class="btn btn-secondary btn-sm" onclick="markAppliedDirect('${escapeHtml(j.job_id)}')">Mark Applied</button>`
                  }
                </div>
                <div style="display:flex; gap:6px;">
                  <a href="${escapeHtml(j.url)}" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration:none;">Open Link ↗</a>
                </div>
              </div>
            </div>
          `;
        }).join('');

      } catch (err) {
        container.innerHTML = `<div style="text-align:center; padding:40px; color:#ef4444;">Error loading jobs: ${err.message}</div>`;
      }
    }

    async function runPipeline() {
      const btn = document.getElementById('btn-run');
      const spinner = document.getElementById('run-spinner');
      const text = document.getElementById('run-text');
      const consoleBox = document.getElementById('run-console');
      const isMock = document.getElementById('chk-mock').checked;

      btn.disabled = true;
      spinner.style.display = 'block';
      text.innerText = 'Hunting Jobs...';
      consoleBox.innerText = 'Starting pipeline execution...\\n[1/5] Scraping ATS endpoints...';

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mock: isMock })
        });
        const data = await res.json();
        if (data.status === 'success') {
          consoleBox.innerText = '✅ ' + data.message + '\\nDigest generated & tracking updated!';
          refreshDigest();
          loadStats();
          fetchAndRenderJobs();
        } else {
          consoleBox.innerText = '❌ Error: ' + (data.message || 'Pipeline failed');
        }
      } catch (err) {
        consoleBox.innerText = '❌ Network Error: ' + err.message;
      } finally {
        btn.disabled = false;
        spinner.style.display = 'none';
        text.innerText = 'Run Job Hunt Now';
      }
    }

    async function markAppliedDirect(jobId) {
      try {
        const res = await fetch('/api/applied', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: jobId })
        });
        const data = await res.json();
        if (data.status === 'success') {
          loadStats();
          fetchAndRenderJobs();
        } else {
          alert('Error: ' + data.message);
        }
      } catch (err) {
        alert('Network Error: ' + err.message);
      }
    }

    async function markAppliedFromInput() {
      const txt = document.getElementById('txt-job-id');
      const status = document.getElementById('applied-status');
      const jobId = txt.value.trim();
      if (!jobId) {
        status.innerText = 'Please enter a valid Job ID.';
        return;
      }

      try {
        const res = await fetch('/api/applied', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_id: jobId })
        });
        const data = await res.json();
        if (data.status === 'success') {
          status.innerText = '✅ ' + data.message;
          txt.value = '';
          loadStats();
          fetchAndRenderJobs();
        } else {
          status.innerText = '❌ ' + data.message;
        }
      } catch (err) {
        status.innerText = '❌ Error: ' + err.message;
      }
    }

    function refreshDigest() {
      const frame = document.getElementById('digest-frame');
      frame.src = '/api/digest?t=' + new Date().getTime();
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    // Initial load
    loadStats();
  </script>
</body>
</html>
"""


@app.route("/")
@app.route("/api/index.py")
def index():
    """Render main Light Mode dashboard with digest & job tracker."""
    return render_template_string(HTML_TEMPLATE)


@app.errorhandler(Exception)
def handle_exception(e):
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


@app.route("/api/jobs")
def api_jobs():
    """Return list of all tracked jobs with filtering support."""
    cfg = cli._cfg(raise_on_error=False)
    seen_file = cfg.get("seen_file", "seen.json")
    st = Store(seen_file)


    status = request.args.get("status", "all").lower()
    search = request.args.get("search", "").lower().strip()
    min_score = request.args.get("min_score", type=float)

    jobs_list = []
    for job_id, data in st.data.items():
        item = {"job_id": job_id, **data}

        # Filter status
        if status == "shortlisted" and (item.get("score") or 0) < 7.0:
            continue
        elif status == "applied" and not item.get("applied"):
            continue

        # Filter min_score
        if min_score is not None and (item.get("score") or 0) < min_score:
            continue

        # Filter search text
        if search:
            searchable = f"{item.get('company', '')} {item.get('title', '')} {item.get('location', '')}".lower()
            if search not in searchable:
                continue

        jobs_list.append(item)

    # Sort by first_seen reverse
    jobs_list.sort(key=lambda j: j.get("first_seen", ""), reverse=True)

    return jsonify({
        "status": "success",
        "count": len(jobs_list),
        "jobs": jobs_list
    })


@app.route("/api/digest")
def api_digest():
    """Serve latest out/digest.html file or fallback placeholder."""
    cfg = cli._cfg(raise_on_error=False)
    digest_file = cfg.get("digest_file", "out/digest.html")


    writable_path = get_writable_path(digest_file)
    root_path = ROOT / digest_file

    target = writable_path if writable_path.is_file() else root_path

    if target.is_file():
        return send_file(target, mimetype="text/html")

    return """<!doctype html>
<html>
<body style="font-family:sans-serif; text-align:center; padding:60px; color:#64748b; background:#0f1115;">
  <div style="max-width:640px; margin:0 auto;">
    <h2 style="color:#e6e8ec;">📬 No Digest Available Yet</h2>
    <p style="color:#8b93a3;">Click <strong>"Run Job Hunt Now"</strong> on the dashboard to trigger your first job scan!</p>
  </div>
</body>
</html>""", 200, {"Content-Type": "text/html"}


@app.route("/api/run", methods=["POST"])
def api_run():
    """Trigger job search pipeline on demand."""
    data = request.get_json(silent=True) or {}
    use_mock = bool(data.get("mock", False))

    cli._load_env()
    smtp_pass = os.environ.get("SMTP_PASS", "")
    send_email = bool(smtp_pass and "your-gmail" not in smtp_pass and "paste-your" not in smtp_pass)

    args = argparse.Namespace(
        config=None,
        mock=use_mock,
        send=send_email,
        scorer="llm",
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

    cfg = cli._cfg()
    st = Store(cfg.get("seen_file", "seen.json"))

    if exit_code == 0:
        return jsonify({
            "status": "success",
            "message": "Pipeline completed successfully!",
            "stats": st.stats()
        })
    else:
        return jsonify({
            "status": "error",
            "message": f"Pipeline exited with code {exit_code}"
        }), 500


@app.route("/api/applied", methods=["POST"])
def api_applied():
    """Mark a job as applied."""
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "").strip()

    if not job_id:
        return jsonify({"status": "error", "message": "Job ID is required"}), 400

    cfg = cli._cfg()
    seen_file = cfg.get("seen_file", "seen.json")
    tracker_csv = cfg.get("tracker_csv", "out/tracker.csv")
    st = Store(seen_file)

    if st.mark_applied(job_id):
        st.export_csv(tracker_csv)
        return jsonify({
            "status": "success",
            "message": f"Marked '{job_id}' as applied.",
            "stats": st.stats()
        })
    else:
        return jsonify({
            "status": "error",
            "message": f"Job ID '{job_id}' not found in tracking store."
        }), 404


if __name__ == "__main__":
    print("=" * 60)
    print(" 🏹 Job Hunter Web Dashboard (Vercel Ready)")
    print(" Server running at: http://localhost:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
