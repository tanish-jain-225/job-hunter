let currentFilter = 'all';
let cachedJobsMap = {};

// Cross-Tab Broadcast Channel Sync
const syncChannel = (typeof BroadcastChannel !== 'undefined') ? new BroadcastChannel('jobhunt_sync') : null;
if (syncChannel) {
  syncChannel.onmessage = (event) => {
    if (event.data && event.data.type === 'SYNC_UPDATE') {
      refreshAllViews(false);
      showToast('Dashboard updated from another tab', 'info');
    }
  };
}

function notifySync() {
  if (syncChannel) {
    syncChannel.postMessage({ type: 'SYNC_UPDATE', timestamp: Date.now() });
  }
}

// Enforce professional Light Mode theme
document.documentElement.setAttribute('data-theme', 'light');

function showToast(message, type = 'success', duration = 3000) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
  toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 250);
  }, duration);
}

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

async function refreshAllViews(notify = true) {
  await loadStats();
  await fetchAndRenderJobs();
  refreshDigest();
  if (notify) notifySync();
}

function switchTab(tab) {
  document.getElementById('tab-content-digest').style.display = tab === 'digest' ? 'block' : 'none';
  document.getElementById('tab-content-tracker').style.display = tab === 'tracker' ? 'block' : 'none';

  document.getElementById('tab-btn-digest').classList.toggle('active', tab === 'digest');
  document.getElementById('tab-btn-tracker').classList.toggle('active', tab === 'tracker');

  if (tab === 'digest') {
    refreshDigest();
  } else if (tab === 'tracker') {
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

function resolveJobUrl(j) {
  if (!j) return '#';
  let url = (j.url || '').trim();
  if (url && url !== '#' && !url.startsWith('javascript:')) {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      return url;
    }
    if (url.includes('.') && !url.startsWith('/')) {
      return 'https://' + url;
    }
  }

  // Auto-resolve based on ATS and job_id
  const jobId = j.job_id || '';
  if (jobId.includes(':')) {
    const parts = jobId.split(':');
    const ats = (j.ats || parts[0] || '').toLowerCase();
    const slug = parts[1] || '';
    const rawId = parts[2] || '';

    if (ats === 'greenhouse' && slug && rawId) {
      return `https://boards.greenhouse.io/${slug}/jobs/${rawId}`;
    } else if (ats === 'lever' && slug && rawId) {
      return `https://jobs.lever.co/${slug}/${rawId}`;
    } else if (ats === 'ashby' && slug && rawId) {
      return `https://jobs.ashbyhq.com/${slug}/${rawId}`;
    } else if (ats === 'workable' && slug && rawId) {
      return `https://apply.workable.com/${slug}/j/${rawId}/`;
    } else if (ats === 'smartrecruiters' && slug && rawId) {
      return `https://jobs.smartrecruiters.com/${slug}/${rawId}`;
    } else if (ats === 'bamboohr' && slug && rawId) {
      return `https://${slug}.bamboohr.com/careers/${rawId}`;
    }
  }

  const query = `${j.company || ''} ${j.title || ''} jobs apply`.trim();
  return `https://www.google.com/search?q=${encodeURIComponent(query || 'tech jobs apply')}`;
}

async function fetchAndRenderJobs() {
  const container = document.getElementById('job-list-container');
  const searchInput = document.getElementById('tracker-search-input');
  const atsSelect = document.getElementById('tracker-ats-select');
  const sortSelect = document.getElementById('tracker-sort-select');

  const search = searchInput ? searchInput.value.trim() : '';
  const ats = atsSelect ? atsSelect.value : 'all';
  const sort = sortSelect ? sortSelect.value : 'date';

  try {
    const url = `/api/jobs?status=${encodeURIComponent(currentFilter)}&ats=${encodeURIComponent(ats)}&sort=${encodeURIComponent(sort)}&search=${encodeURIComponent(search)}`;
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
      const applyUrl = resolveJobUrl(j);

      return `
        <div class="job-item" id="job-card-${escapeHtml(j.job_id)}">
          <div class="job-meta">
            <div class="job-header-row">
              <span class="job-title">${escapeHtml(j.title)}</span>
              <span class="ats-tag">${escapeHtml(j.ats || 'ats')}</span>
            </div>
            <div class="job-sub">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 4px;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg><strong>${escapeHtml(j.company)}</strong> 
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 4px; margin-left: 8px;"><path d="M12 2a8 8 0 0 0-8 8c0 5.25 8 12 8 12s8-6.75 8-12a8 8 0 0 0-8-8z"></path><circle cx="12" cy="10" r="3"></circle></svg>${escapeHtml(j.location || 'Remote/Unspecified')}
              <span style="font-size:11px; color:var(--text-muted); margin-left:8px; display:inline-block; overflow-wrap:anywhere;">(${escapeHtml(j.job_id)})</span>
            </div>
            ${j.reason ? `<div class="job-reason">💡 ${escapeHtml(j.reason)}</div>` : ''}
          </div>
          <div class="job-actions">
            <div class="job-score-row">
              <span class="score-badge ${scoreClass}">${score}</span>
            </div>
            <div class="job-action-btn-row">
              ${isApplied
                ? `<button class="btn btn-secondary btn-sm btn-applied" id="btn-app-${escapeHtml(j.job_id)}" title="Click to unmark applied" onclick="toggleAppliedDirect('${escapeHtml(j.job_id)}', 'unmark')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Applied</button>`
                : `<button class="btn btn-secondary btn-sm" id="btn-app-${escapeHtml(j.job_id)}" onclick="toggleAppliedDirect('${escapeHtml(j.job_id)}', 'mark')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>Mark Applied</button>`
              }
              <button class="btn btn-secondary btn-sm btn-danger" title="Delete job entry" onclick="deleteJobDirect('${escapeHtml(j.job_id)}')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>Delete</button>
            </div>
            <div class="job-action-btn-row">
              ${hasDraft ? `<button class="btn btn-secondary btn-sm" onclick="openKitModal('${escapeHtml(j.job_id)}')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>Inspect Kit</button>` : ''}
              <a href="${escapeHtml(applyUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="text-decoration:none; display:inline-flex; align-items:center;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>Open Link</a>
            </div>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    container.innerHTML = `<div style="text-align:center; padding:40px; color:var(--danger);">Notice: ${escapeHtml(err.message)}</div>`;
  }
}

function copySectionText(textId, btnId) {
  const el = document.getElementById(textId);
  if (!el) return;
  const txt = el.innerText;
  navigator.clipboard.writeText(txt).then(() => {
    const btn = document.getElementById(btnId);
    if (btn) {
      const type = btn.getAttribute('data-original');
      let originalHtml = '';
      if (type === 'outreach') {
        originalHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Outreach</span>`;
      } else if (type === 'cover') {
        originalHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Note</span>`;
      }
      
      btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg><span style="color:#10b981;">Copied!</span>`;
      
      showToast('Copied to clipboard!', 'success');
      setTimeout(() => { 
        if (btn) btn.innerHTML = originalHtml; 
      }, 2000);
    }
  });
}

function openKitModal(jobId) {
  const j = cachedJobsMap[jobId];
  if (!j || !j.draft) return;

  document.getElementById('modal-job-title').innerText = j.title || 'Job Application Kit';
  document.getElementById('modal-job-meta').innerText = `${j.company} · ${j.location || 'Remote/Unspecified'}`;

  const d = j.draft;
  let html = '';

  if (d.fit_summary) {
    html += `<div class="kit-section"><div class="kit-label">Why It Fits</div><p style="font-size:13.5px; line-height:1.6; color:var(--text-main);">${escapeHtml(d.fit_summary)}</p></div>`;
  }

  const outreachLabelSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Outreach</span>`;
  const coverLabelSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Note</span>`;

  if (d.cold_outreach) {
    html += `
      <div class="kit-section">
        <div class="kit-label" style="display:flex; justify-content:space-between; align-items:center;">
          <span>⚡ Cold Outreach (&lt;80 words)</span>
          <button class="copy-btn" id="btn-copy-outreach" data-original="outreach" onclick="copySectionText('outreach-text', 'btn-copy-outreach')">${outreachLabelSvg}</button>
        </div>
        <div class="cover-box" id="outreach-text" style="background:var(--success-bg); color:var(--success); border-color:var(--success-border); font-family:monospace;">${escapeHtml(d.cold_outreach)}</div>
      </div>`;
  }

  if (d.cover_note) {
    html += `
      <div class="kit-section">
        <div class="kit-label" style="display:flex; justify-content:space-between; align-items:center;">
          <span>📝 Cover Note</span>
          <button class="copy-btn" id="btn-copy-cover" data-original="cover" onclick="copySectionText('cover-text', 'btn-copy-cover')">${coverLabelSvg}</button>
        </div>
        <div class="cover-box" id="cover-text">${escapeHtml(d.cover_note)}</div>
      </div>`;
  }

  if (d.tailored_bullets && d.tailored_bullets.length) {
    html += `<div class="kit-section"><div class="kit-label">Tailored Resume Bullets</div><ul style="padding-left:18px; font-size:13.5px; line-height:1.6; color:var(--text-main);">${d.tailored_bullets.map(b => `<li style="margin-bottom:6px;">${escapeHtml(b)}</li>`).join('')}</ul></div>`;
  }
  if (d.gaps && d.gaps.length) {
    html += `<div class="kit-section"><div class="kit-label" style="color:var(--danger);">Honest Gaps / Gaps</div><ul style="padding-left:18px; font-size:13.5px; line-height:1.6; color:var(--text-main);">${d.gaps.map(g => `<li style="margin-bottom:6px; color:#b91c1c;">${escapeHtml(g)}</li>`).join('')}</ul></div>`;
  }
  if (d.questions_to_ask && d.questions_to_ask.length) {
    html += `<div class="kit-section"><div class="kit-label">Questions To Ask</div><ul style="padding-left:18px; font-size:13.5px; line-height:1.6; color:var(--text-main);">${d.questions_to_ask.map(q => `<li style="margin-bottom:6px;">${escapeHtml(q)}</li>`).join('')}</ul></div>`;
  }

  const modalApplyUrl = resolveJobUrl(j);
  html += `<div style="margin-top:24px; text-align:right;"><a href="${escapeHtml(modalApplyUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="display:inline-flex; align-items:center; text-decoration:none;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>Open Posting Page</a></div>`;

  document.getElementById('modal-body').innerHTML = html;
  document.getElementById('kit-modal').classList.add('active');
}

function closeKitModal() {
  document.getElementById('kit-modal').classList.remove('active');
}

function copyCoverNote() {
  copySectionText('cover-text', 'btn-copy-cover', 'Copy Note 📋');
}

async function runPipeline() {
  const btn = document.getElementById('btn-run');
  const spinner = document.getElementById('run-spinner');
  const text = document.getElementById('run-text');
  const consoleBox = document.getElementById('run-console');
  const isMock = false;

  btn.disabled = true;
  spinner.style.display = 'block';
  text.innerText = 'Hunting Jobs...';
  consoleBox.innerText = `Starting pipeline execution...\n[1/5] Scanning ATS endpoints...\n[2/5] Filtering candidate matches...`;

  try {
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mock: isMock })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      consoleBox.innerText = `✅ ${data.message}\nDigest generated & tracking store updated!`;
      showToast('Pipeline run completed successfully!', 'success');
      refreshAllViews();
    } else {
      consoleBox.innerText = '❌ Error: ' + (data.message || 'Pipeline failed');
      showToast('Pipeline failed: ' + data.message, 'error');
    }
  } catch (err) {
    consoleBox.innerText = '❌ Notice: ' + err.message;
    showToast('Notice: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    spinner.style.display = 'none';
    text.innerText = 'Run Job Hunt Now';
  }
}

async function toggleAppliedDirect(jobId, action) {
  const btn = document.getElementById('btn-app-' + jobId);
  const isUnmark = action === 'unmark';

  // Optimistic UI update
  if (btn) {
    btn.innerHTML = isUnmark 
      ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>Mark Applied`
      : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Applied`;
    btn.className = isUnmark ? 'btn btn-secondary btn-sm' : 'btn btn-secondary btn-sm btn-applied';
  }

  try {
    const res = await fetch('/api/applied', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, action: action })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      showToast(data.message, 'success');
      refreshAllViews();
    } else {
      // Rollback on error
      if (btn) {
        btn.innerHTML = isUnmark 
          ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Applied`
          : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>Mark Applied`;
        btn.className = isUnmark ? 'btn btn-secondary btn-sm btn-applied' : 'btn btn-secondary btn-sm';
      }
      showToast('Notice: ' + data.message, 'error');
    }
  } catch (err) {
    // Rollback on exception
    if (btn) {
      btn.innerHTML = isUnmark 
        ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Applied`
        : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>Mark Applied`;
      btn.className = isUnmark ? 'btn btn-secondary btn-sm btn-applied' : 'btn btn-secondary btn-sm';
    }
    showToast('Notice: ' + err.message, 'error');
  }
}

async function deleteJobDirect(jobId) {
  if (!confirm(`Are you sure you want to delete job '${jobId}' from tracking store?`)) {
    return;
  }

  const card = document.getElementById('job-card-' + jobId);
  if (card) {
    card.style.opacity = '0.4';
    card.style.pointerEvents = 'none';
  }

  try {
    const res = await fetch('/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      showToast(data.message, 'success');
      refreshAllViews();
    } else {
      if (card) {
        card.style.opacity = '1';
        card.style.pointerEvents = 'auto';
      }
      showToast('Notice: ' + data.message, 'error');
    }
  } catch (err) {
    if (card) {
      card.style.opacity = '1';
      card.style.pointerEvents = 'auto';
    }
    showToast('Notice: ' + err.message, 'error');
  }
}

async function markAppliedFromInput(action) {
  const txt = document.getElementById('txt-job-id');
  const status = document.getElementById('applied-status');
  const jobId = txt.value.trim();
  if (!jobId) {
    status.innerText = 'Please enter a valid Job ID.';
    showToast('Please enter a valid Job ID', 'error');
    return;
  }

  try {
    const res = await fetch('/api/applied', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, action: action || 'mark' })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      status.innerText = '✅ ' + data.message;
      showToast(data.message, 'success');
      txt.value = '';
      refreshAllViews();
    } else {
      status.innerText = '❌ ' + data.message;
      showToast(data.message, 'error');
    }
  } catch (err) {
    status.innerText = '❌ Notice: ' + err.message;
    showToast(err.message, 'error');
  }
}

async function addCustomJobFromInput() {
  const titleEl = document.getElementById('add-title');
  const companyEl = document.getElementById('add-company');
  const locEl = document.getElementById('add-location');
  const urlEl = document.getElementById('add-url');
  const scoreEl = document.getElementById('add-score');
  const appliedEl = document.getElementById('add-applied');
  const status = document.getElementById('add-job-status');

  const title = titleEl.value.trim();
  const company = companyEl.value.trim();

  if (!title || !company) {
    status.innerText = 'Please enter both Job Title and Company.';
    showToast('Please enter both Job Title and Company.', 'error');
    return;
  }

  status.innerText = 'Adding job...';

  try {
    const res = await fetch('/api/jobs/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        company: company,
        location: locEl.value.trim() || 'Remote/Unspecified',
        url: urlEl.value.trim() || '#',
        score: parseFloat(scoreEl.value) || 8.0,
        applied: appliedEl.checked
      })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      status.innerText = '✅ ' + data.message;
      showToast(data.message, 'success');
      titleEl.value = '';
      companyEl.value = '';
      locEl.value = '';
      urlEl.value = '';
      appliedEl.checked = false;
      refreshAllViews();
    } else {
      status.innerText = '❌ ' + data.message;
      showToast(data.message, 'error');
    }
  } catch (err) {
    status.innerText = '❌ Notice: ' + err.message;
    showToast(err.message, 'error');
  }
}

function refreshDigest() {
  const frame = document.getElementById('digest-frame');
  if (frame) {
    const url = '/api/digest?t=' + new Date().getTime();
    try {
      if (frame.contentWindow && frame.contentWindow.location) {
        frame.contentWindow.location.replace(url);
      } else {
        frame.src = url;
      }
    } catch (e) {
      frame.src = url;
    }
  }
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

// Auto Heartbeat (10s)
setInterval(() => {
  loadStats();
}, 10000);

// Sync on Tab Visibility / Focus
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) {
    refreshAllViews(false);
  }
});

// Keyboard Shortcuts: '/' to focus search, 'Esc' to close modal
document.addEventListener('keydown', (e) => {
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
    e.preventDefault();
    switchTab('tracker');
    const input = document.getElementById('tracker-search-input');
    if (input) input.focus();
  } else if (e.key === 'Escape') {
    closeKitModal();
  }
});

// Initial load
document.addEventListener('DOMContentLoaded', () => {
  loadStats();
});
