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
  <title>Job Hunter — Executive AI Career Dashboard</title>
  <link rel="icon" type="image/png" href="/logo.png">
  <link rel="shortcut icon" type="image/png" href="/logo.png">
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
      --primary-light: #e0e7ff;
      --success: #059669;
      --success-bg: #ecfdf5;
      --warning: #d97706;
      --warning-bg: #fffbeb;
      --danger: #dc2626;
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
      max-width: 1320px;
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
      gap: 14px;
    }
    .brand-icon {
      width: 48px;
      height: 48px;
      border-radius: 12px;
      object-fit: contain;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.06);
    }
    .brand h1 {
      font-size: 22px;
      font-weight: 800;
      color: var(--text-main);
      letter-spacing: -0.025em;
    }
    .brand p {
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 500;
    }

    /* Metrics Pills */
    .metrics {
      display: flex;
      gap: 12px;
    }
    .metric-pill {
      background: #f1f5f9;
      border: 1px solid var(--border);
      padding: 10px 18px;
      border-radius: 10px;
      text-align: center;
      min-width: 105px;
      transition: transform 0.15s ease;
    }
    .metric-pill:hover {
      transform: translateY(-1px);
    }
    .metric-val {
      font-size: 20px;
      font-weight: 800;
      color: var(--primary);
    }
    .metric-label {
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 700;
      color: var(--text-muted);
      letter-spacing: 0.05em;
    }

    /* Grid Layout */
    .grid {
      display: grid;
      grid-template-columns: 320px 1fr;
      gap: 24px;
    }
    @media (max-width: 920px) {
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
      font-size: 15px;
      font-weight: 700;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--text-main);
      letter-spacing: -0.01em;
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
      box-shadow: 0 4px 10px rgba(79, 70, 229, 0.3);
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
      padding: 6px 14px;
      font-size: 12px;
      border-radius: 6px;
      font-weight: 600;
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
      font-weight: 600;
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
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .form-input:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.12);
    }

    .checkbox-label {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 13px;
      color: var(--text-muted);
      cursor: pointer;
      user-select: none;
      font-weight: 500;
    }

    /* Console Output */
    .console {
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 14px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      color: #334155;
      max-height: 150px;
      overflow-y: auto;
      margin-top: 16px;
      white-space: pre-wrap;
      line-height: 1.6;
    }

    /* Viewport Tabs */
    .tab-bar {
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--border);
      margin-bottom: 20px;
    }
    .tab-btn {
      padding: 10px 20px;
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

    /* Board Controls & Job Cards */
    .tracker-bar {
      display: flex;
      gap: 12px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }
    .tracker-search { flex: 1; min-width: 240px; }
    .filter-pills { display: flex; gap: 6px; }
    .pill {
      padding: 8px 14px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      background: #ffffff;
      color: var(--text-muted);
      border: 1px solid var(--border);
      cursor: pointer;
      transition: all 0.15s;
    }
    .pill:hover { border-color: var(--border-hover); color: var(--text-main); }
    .pill.active {
      background: var(--primary);
      color: #ffffff;
      border-color: var(--primary);
      box-shadow: 0 2px 4px rgba(79, 70, 229, 0.2);
    }

    .job-list {
      display: flex;
      flex-direction: column;
      gap: 14px;
      max-height: 740px;
      overflow-y: auto;
      padding-right: 4px;
    }
    .job-item {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px 20px;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 16px;
      transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
    }
    .job-item:hover {
      border-color: var(--border-hover);
      box-shadow: var(--shadow-md);
      transform: translateY(-1px);
    }
    .job-meta { flex: 1; }
    .job-title {
      font-size: 16px;
      font-weight: 700;
      color: var(--text-main);
      margin-bottom: 4px;
      line-height: 1.3;
    }
    .job-sub {
      font-size: 13px;
      color: var(--text-muted);
      margin-bottom: 8px;
    }
    .ats-tag {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      background: #f1f5f9;
      color: #475569;
      margin-left: 6px;
    }
    .job-reason {
      font-size: 12px;
      color: #334155;
      background: #f8fafc;
      padding: 8px 12px;
      border-radius: 8px;
      border: 1px solid #e2e8f0;
      margin-top: 8px;
    }

    .job-actions {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 10px;
    }
    .score-badge {
      padding: 4px 12px;
      border-radius: 999px;
      font-size: 13px;
      font-weight: 800;
      min-width: 48px;
      text-align: center;
    }
    .score-high { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
    .score-mid { background: #fef9c3; color: #a16207; border: 1px solid #fef08a; }
    .score-low { background: #f1f5f9; color: #64748b; border: 1px solid #e2e8f0; }

    /* Modal Dialog for Kit Inspection */
    .modal-overlay {
      display: none;
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(15, 23, 42, 0.45);
      backdrop-filter: blur(4px);
      z-index: 1000;
      justify-content: center;
      align-items: center;
      padding: 20px;
    }
    .modal-overlay.active { display: flex; }
    .modal-content {
      background: #ffffff;
      border-radius: 16px;
      max-width: 720px;
      width: 100%;
      max-height: 85vh;
      overflow-y: auto;
      box-shadow: 0 20px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1);
      border: 1px solid var(--border);
      padding: 24px 28px;
      position: relative;
    }
    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 20px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border);
    }
    .modal-title { font-size: 18px; font-weight: 800; color: var(--text-main); }
    .modal-subtitle { font-size: 13px; color: var(--text-muted); margin-top: 2px; }
    .modal-close {
      background: #f1f5f9;
      border: none;
      width: 32px;
      height: 32px;
      border-radius: 50%;
      font-size: 18px;
      font-weight: 700;
      cursor: pointer;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .modal-close:hover { background: #e2e8f0; color: var(--text-main); }

    .kit-section {
      margin-bottom: 20px;
    }
    .kit-label {
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 800;
      color: var(--text-muted);
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }
    .cover-box {
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px;
      font-size: 13px;
      line-height: 1.6;
      color: #334155;
      white-space: pre-wrap;
    }
    .copy-btn {
      float: right;
      font-size: 11px;
      padding: 4px 10px;
      background: #ffffff;
      border: 1px solid var(--border);
      border-radius: 6px;
      cursor: pointer;
      font-weight: 600;
    }
    .copy-btn:hover { background: var(--primary-light); color: var(--primary); }

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
      <img src="/logo.png" alt="Job Hunter Logo" class="brand-icon">
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
          <span style="font-size:13px; color:var(--text-muted); font-weight:500;">Latest generated HTML digest briefing preview</span>
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

  <!-- Modal for Inspecting Application Kit -->
  <div class="modal-overlay" id="kit-modal">
    <div class="modal-content">
      <div class="modal-header">
        <div>
          <div class="modal-title" id="modal-job-title">Job Application Kit</div>
          <div class="modal-subtitle" id="modal-job-meta">Company · Location</div>
        </div>
        <button class="modal-close" onclick="closeKitModal()">×</button>
      </div>
      <div id="modal-body">
        <!-- Kit Details populated dynamically -->
      </div>
    </div>
  </div>

  <script>
    let currentFilter = 'all';
    let cachedJobsMap = {};

    async function parseJsonResponse(res) {
      const text = await res.text();
      try {
        return JSON.parse(text);
      } catch (err) {
        if (!res.ok) {
          throw new Error(`Server returned HTTP ${res.status} (${res.statusText || 'Server Error'})`);
        }
        throw new Error(`Unexpected server response`);
      }
    }

    async function loadStats() {
      try {
        const res = await fetch('/api/stats');
        const data = await parseJsonResponse(res);
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
      const pill = document.getElementById('pill-' + filter);
      if (pill) pill.classList.add('active');
      fetchAndRenderJobs();
    }

    async function fetchAndRenderJobs() {
      const container = document.getElementById('job-list-container');
      const search = document.getElementById('tracker-search-input').value.trim();

      try {
        const url = `/api/jobs?status=${encodeURIComponent(currentFilter)}&search=${encodeURIComponent(search)}`;
        const res = await fetch(url);
        const data = await parseJsonResponse(res);

        if (data.status !== 'success' || !data.jobs || data.jobs.length === 0) {
          container.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-muted);">No matching jobs found in tracking store.</div>';
          return;
        }

        cachedJobsMap = {};
        data.jobs.forEach(j => { cachedJobsMap[j.job_id] = j; });

        container.innerHTML = data.jobs.map(j => {
          const score = j.score != null ? Number(j.score).toFixed(1) : 'N/A';
          const scoreClass = j.score >= 8.5 ? 'score-high' : (j.score >= 7.0 ? 'score-mid' : 'score-low');
          const isApplied = Boolean(j.applied);
          const hasDraft = j.draft && (j.draft.cover_note || j.draft.fit_summary);

          return `
            <div class="job-item">
              <div class="job-meta">
                <div style="display:flex; align-items:center; gap:8px;">
                  <span class="job-title">${escapeHtml(j.title)}</span>
                  <span class="ats-tag">${escapeHtml(j.ats || 'ats')}</span>
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
                  ${hasDraft ? `<button class="btn btn-secondary btn-sm" onclick="openKitModal('${escapeHtml(j.job_id)}')">Inspect Kit 📄</button>` : ''}
                  <a href="${escapeHtml(j.url)}" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration:none;">Open Link ↗</a>
                </div>
              </div>
            </div>
          `;
        }).join('');

      } catch (err) {
        container.innerHTML = `<div style="text-align:center; padding:40px; color:var(--danger);">Notice: ${escapeHtml(err.message)}</div>`;
      }
    }

    function openKitModal(jobId) {
      const j = cachedJobsMap[jobId];
      if (!j || !j.draft) return;

      document.getElementById('modal-job-title').innerText = j.title || 'Job Application Kit';
      document.getElementById('modal-job-meta').innerText = `${j.company} · ${j.location || 'Remote/Unspecified'}`;

      const d = j.draft;
      let html = '';

      if (d.fit_summary) {
        html += `<div class="kit-section"><div class="kit-label">Why It Fits</div><p style="font-size:13px; color:#334155; line-height:1.5;">${escapeHtml(d.fit_summary)}</p></div>`;
      }
      if (d.cover_note) {
        html += `
          <div class="kit-section">
            <div class="kit-label">Cover Note
              <button class="copy-btn" id="btn-copy-cover" onclick="copyCoverNote()">Copy Note 📋</button>
            </div>
            <div class="cover-box" id="cover-text">${escapeHtml(d.cover_note)}</div>
          </div>`;
      }
      if (d.tailored_bullets && d.tailored_bullets.length) {
        html += `<div class="kit-section"><div class="kit-label">Tailored Resume Bullets</div><ul style="padding-left:18px; font-size:13px; color:#334155;">${d.tailored_bullets.map(b => `<li style="margin-bottom:4px;">${escapeHtml(b)}</li>`).join('')}</ul></div>`;
      }
      if (d.gaps && d.gaps.length) {
        html += `<div class="kit-section"><div class="kit-label">Honest Gaps</div><ul style="padding-left:18px; font-size:13px; color:#334155;">${d.gaps.map(g => `<li style="margin-bottom:4px;">${escapeHtml(g)}</li>`).join('')}</ul></div>`;
      }
      if (d.questions_to_ask && d.questions_to_ask.length) {
        html += `<div class="kit-section"><div class="kit-label">Questions To Ask</div><ul style="padding-left:18px; font-size:13px; color:#334155;">${d.questions_to_ask.map(q => `<li style="margin-bottom:4px;">${escapeHtml(q)}</li>`).join('')}</ul></div>`;
      }

      html += `<div style="margin-top:20px; text-align:right;"><a href="${escapeHtml(j.url)}" target="_blank" class="btn btn-secondary btn-sm" style="display:inline-block; text-decoration:none;">Open Posting Page ↗</a></div>`;

      document.getElementById('modal-body').innerHTML = html;
      document.getElementById('kit-modal').classList.add('active');
    }

    function closeKitModal() {
      document.getElementById('kit-modal').classList.remove('active');
    }

    function copyCoverNote() {
      const txt = document.getElementById('cover-text').innerText;
      navigator.clipboard.writeText(txt).then(() => {
        const btn = document.getElementById('btn-copy-cover');
        btn.innerText = 'Copied! ✓';
        setTimeout(() => { btn.innerText = 'Copy Note 📋'; }, 2000);
      });
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
      consoleBox.innerText = 'Starting pipeline execution...\\n[1/5] Scanning ATS endpoints...\\n[2/5] Filtering candidate matches...';

      try {
        const res = await fetch('/api/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mock: isMock })
        });
        const data = await parseJsonResponse(res);
        if (data.status === 'success') {
          consoleBox.innerText = '✅ ' + data.message + '\\nDigest generated & tracking store updated!';
          refreshDigest();
          loadStats();
          fetchAndRenderJobs();
        } else {
          consoleBox.innerText = '❌ Error: ' + (data.message || 'Pipeline failed');
        }
      } catch (err) {
        consoleBox.innerText = '❌ Notice: ' + err.message;
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
        const data = await parseJsonResponse(res);
        if (data.status === 'success') {
          loadStats();
          fetchAndRenderJobs();
        } else {
          alert('Notice: ' + data.message);
        }
      } catch (err) {
        alert('Notice: ' + err.message);
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
        const data = await parseJsonResponse(res);
        if (data.status === 'success') {
          status.innerText = '✅ ' + data.message;
          txt.value = '';
          loadStats();
          fetchAndRenderJobs();
        } else {
          status.innerText = '❌ ' + data.message;
        }
      } catch (err) {
        status.innerText = '❌ Notice: ' + err.message;
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
    """Serve latest out/digest.html file or dynamically generate digest from Store data."""
    cfg = cli._cfg(raise_on_error=False)
    digest_file = cfg.get("digest_file", "out/digest.html")

    writable_path = get_writable_path(digest_file)
    root_path = ROOT / digest_file

    target = writable_path if writable_path.is_file() else root_path

    if target.is_file():
        return send_file(target, mimetype="text/html")

    # If digest.html does not exist on disk, generate on the fly from Store data
    seen_file = cfg.get("seen_file", "seen.json")
    st = Store(seen_file)
    from jobhunt import digest
    from jobhunt.fetch import Job
    jobs_list = []
    for jid, d in st.data.items():
        if (d.get("score") or 0) >= 7.0:
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
    """Mark a job as applied."""
    data = request.get_json(silent=True) or {}
    job_id = data.get("job_id", "").strip()

    if not job_id:
        return jsonify({"status": "error", "message": "Job ID is required"}), 400

    cfg = cli._cfg(raise_on_error=False)
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
