/**
 * Job Hunter — Executive Career Dashboard Client Engine
 * 
 * Implements:
 * - Robust State Persistence across Refreshes (Active Tab, Filters, Search, Sort, Modal Deep-link)
 * - Session-Atomic Draft Auto-Saving (Add Custom Job & Mark Applied forms)
 * - Stale-While-Revalidate Caching for zero-flicker instant rendering
 * - Advanced Memory Management:
 *   - Visibility-aware polling heartbeat (pauses in background tabs)
 *   - AbortController cancellation for in-flight fetch requests
 *   - Debounced search queries to avoid network thrashing
 *   - Managed toast queue & bounded DOM nodes
 *   - Managed timer maps for copy buttons
 *   - Leak-free iframe document reloads and modal teardowns
 *   - Teardown on page unload
 */

// Storage Keys Constants
const STORAGE_KEYS = {
  ACTIVE_TAB: 'jobhunt_active_tab',
  STATUS_FILTER: 'jobhunt_status_filter',
  SEARCH_QUERY: 'jobhunt_search_query',
  ATS_FILTER: 'jobhunt_ats_filter',
  SORT_BY: 'jobhunt_sort_by',
  CACHED_STATS: 'jobhunt_cached_stats',
  CACHED_JOBS: 'jobhunt_cached_jobs',
  APPLIED_OVERLAY: 'jobhunt_applied_overlay',
  DRAFT_CUSTOM_JOB: 'jobhunt_draft_custom_job',
  DRAFT_APPLIED_ID: 'jobhunt_draft_applied_id',
  ACTIVE_KIT: 'jobhunt_active_kit'
};

// Safe Storage Wrapper (resilient to private browsing / quota limits)
const Storage = {
  get(storage, key, fallback = null) {
    try {
      const val = storage.getItem(key);
      if (val === null || val === undefined) return fallback;
      try {
        return JSON.parse(val);
      } catch {
        return val;
      }
    } catch (e) {
      console.warn('Storage read error:', e);
      return fallback;
    }
  },
  set(storage, key, value) {
    try {
      const serialized = typeof value === 'string' ? value : JSON.stringify(value);
      storage.setItem(key, serialized);
    } catch (e) {
      console.warn('Storage write error:', e);
    }
  },
  remove(storage, key) {
    try {
      storage.removeItem(key);
    } catch (e) {
      console.warn('Storage remove error:', e);
    }
  }
};

// Global In-Memory State & Cache
let currentFilter = 'all';
let currentAts = 'all';
let currentSort = 'date';
let currentSearch = '';
let currentActiveTab = 'digest';
let cachedJobsMap = {};
let jobsAbortController = null;
let heartbeatIntervalId = null;
let searchDebounceTimer = null;
const copyTimeoutMap = new Map();
const activeToasts = [];

// Cross-Tab Synchronization via BroadcastChannel + Storage Fallback
let syncChannel = null;
try {
  if (typeof BroadcastChannel !== 'undefined') {
    syncChannel = new BroadcastChannel('jobhunt_sync');
    syncChannel.onmessage = (event) => {
      if (event.data && event.data.type === 'SYNC_UPDATE') {
        refreshAllViews(false);
        showToast('Dashboard updated from another tab', 'info');
      }
    };
  }
} catch (e) {
  console.warn('BroadcastChannel unavailable:', e);
}

// Fallback storage sync across tabs
window.addEventListener('storage', (e) => {
  if (e.key === STORAGE_KEYS.CACHED_STATS || e.key === STORAGE_KEYS.APPLIED_OVERLAY) {
    refreshAllViews(false);
  }
});

function notifySync() {
  if (syncChannel) {
    try {
      syncChannel.postMessage({ type: 'SYNC_UPDATE', timestamp: Date.now() });
    } catch (e) {
      console.warn('Sync post error:', e);
    }
  }
}

// Enforce professional Light Mode theme
document.documentElement.setAttribute('data-theme', 'light');

// Utility: Debounce function for performance & memory control
function debounce(fn, delay = 250) {
  return function (...args) {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      fn.apply(this, args);
      searchDebounceTimer = null;
    }, delay);
  };
}

// Toast Notifications (bounded queue with leak-free DOM cleanup)
function showToast(message, type = 'success', duration = 3000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  // Bound active toasts to max 4 to prevent DOM bloat
  while (activeToasts.length >= 4) {
    const oldest = activeToasts.shift();
    if (oldest && oldest.element && oldest.element.parentNode) {
      clearTimeout(oldest.timer);
      oldest.element.remove();
    }
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
  toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  const toastRecord = {
    element: toast,
    timer: null
  };

  toastRecord.timer = setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => {
      toast.remove();
      const idx = activeToasts.indexOf(toastRecord);
      if (idx !== -1) activeToasts.splice(idx, 1);
    }, 250);
  }, duration);

  activeToasts.push(toastRecord);
}

// Safe JSON response parser
async function parseJsonResponse(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch (err) {
    if (!res.ok) {
      throw new Error(`Server returned HTTP ${res.status} (${res.statusText || 'Server Error'})`);
    }
    throw new Error('Unexpected server response');
  }
}

// URL State Syncing & Deep-Linking Helper
function syncUrlState() {
  try {
    const url = new URL(window.location.href);
    url.searchParams.set('tab', currentActiveTab);
    
    if (currentFilter && currentFilter !== 'all') {
      url.searchParams.set('status', currentFilter);
    } else {
      url.searchParams.delete('status');
    }

    if (currentAts && currentAts !== 'all') {
      url.searchParams.set('ats', currentAts);
    } else {
      url.searchParams.delete('ats');
    }

    if (currentSort && currentSort !== 'date') {
      url.searchParams.set('sort', currentSort);
    } else {
      url.searchParams.delete('sort');
    }

    if (currentSearch) {
      url.searchParams.set('search', currentSearch);
    } else {
      url.searchParams.delete('search');
    }

    const activeKit = Storage.get(sessionStorage, STORAGE_KEYS.ACTIVE_KIT, '');
    if (activeKit) {
      url.searchParams.set('kit', activeKit);
    } else {
      url.searchParams.delete('kit');
    }

    window.history.replaceState({}, '', url.toString());
  } catch (e) {
    console.warn('URL sync error:', e);
  }
}

// Stats Loader with Stale-While-Revalidate Cache
async function loadStats() {
  // 1. Immediately hydrate from cache if available
  const cachedStats = Storage.get(localStorage, STORAGE_KEYS.CACHED_STATS, null);
  if (cachedStats && cachedStats.stats) {
    renderStats(cachedStats.stats);
  }

  // 2. Fetch fresh stats asynchronously
  try {
    const res = await fetch('/api/stats', { cache: 'no-store' });
    const data = await parseJsonResponse(res);
    renderStats(data);
    Storage.set(localStorage, STORAGE_KEYS.CACHED_STATS, {
      stats: data,
      timestamp: Date.now()
    });
  } catch (err) {
    console.error('Failed to load fresh stats:', err);
  }
}

function renderStats(stats) {
  const trackedEl = document.getElementById('metric-tracked');
  const emailedEl = document.getElementById('metric-emailed');
  const appliedEl = document.getElementById('metric-applied');

  if (trackedEl) trackedEl.innerText = stats.tracked ?? 0;
  if (emailedEl) emailedEl.innerText = stats.emailed ?? 0;
  if (appliedEl) appliedEl.innerText = stats.applied ?? 0;
}

// Refresh all views coordinating digest, jobs, and stats
async function refreshAllViews(notify = true) {
  await Promise.all([
    loadStats(),
    fetchAndRenderJobs()
  ]);
  
  if (currentActiveTab === 'digest') {
    refreshDigest(true);
  }
  
  if (notify) notifySync();
}

// Tab Switching with URL & LocalStorage Persistence
function switchTab(tab) {
  currentActiveTab = tab;
  Storage.set(localStorage, STORAGE_KEYS.ACTIVE_TAB, tab);

  const digestContent = document.getElementById('tab-content-digest');
  const trackerContent = document.getElementById('tab-content-tracker');
  const digestBtn = document.getElementById('tab-btn-digest');
  const trackerBtn = document.getElementById('tab-btn-tracker');

  if (digestContent) digestContent.style.display = tab === 'digest' ? 'block' : 'none';
  if (trackerContent) trackerContent.style.display = tab === 'tracker' ? 'block' : 'none';

  if (digestBtn) digestBtn.classList.toggle('active', tab === 'digest');
  if (trackerBtn) trackerBtn.classList.toggle('active', tab === 'tracker');

  syncUrlState();

  if (tab === 'digest') {
    refreshDigest();
  } else if (tab === 'tracker') {
    fetchAndRenderJobs();
  }
}

// Filter Pills with State Persistence
function setFilter(filter) {
  currentFilter = filter;
  Storage.set(localStorage, STORAGE_KEYS.STATUS_FILTER, filter);

  document.querySelectorAll('.filter-pills .pill').forEach(el => el.classList.remove('active'));
  const pill = document.getElementById('pill-' + filter);
  if (pill) pill.classList.add('active');

  syncUrlState();
  fetchAndRenderJobs();
}

// URL resolver for jobs
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

// Render HTML for a list of jobs
function renderJobsListHtml(jobs) {
  const appliedOverlay = Storage.get(localStorage, STORAGE_KEYS.APPLIED_OVERLAY, {}) || {};

  return jobs.map(j => {
    const score = j.score != null ? Number(j.score).toFixed(1) : 'N/A';
    const scoreClass = j.score >= 8.5 ? 'score-high' : (j.score >= 7.0 ? 'score-mid' : 'score-low');
    
    // Client-side applied overlay takes precedence for instant responsiveness
    const isApplied = (j.job_id in appliedOverlay) ? Boolean(appliedOverlay[j.job_id]) : Boolean(j.applied);
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
}

// Fetch and Render Jobs with AbortController & SWR Caching
async function fetchAndRenderJobs() {
  const container = document.getElementById('job-list-container');
  const searchInput = document.getElementById('tracker-search-input');
  const atsSelect = document.getElementById('tracker-ats-select');
  const sortSelect = document.getElementById('tracker-sort-select');

  currentSearch = searchInput ? searchInput.value.trim() : '';
  currentAts = atsSelect ? atsSelect.value : 'all';
  currentSort = sortSelect ? sortSelect.value : 'date';

  // Persist selections
  Storage.set(localStorage, STORAGE_KEYS.SEARCH_QUERY, currentSearch);
  Storage.set(localStorage, STORAGE_KEYS.ATS_FILTER, currentAts);
  Storage.set(localStorage, STORAGE_KEYS.SORT_BY, currentSort);
  syncUrlState();

  // 1. Cancel any previous in-flight fetch request
  if (jobsAbortController) {
    jobsAbortController.abort();
  }
  jobsAbortController = new AbortController();
  const currentSignal = jobsAbortController.signal;

  // 2. Stale-While-Revalidate: render cached jobs if available and container is empty
  const cacheKey = `${currentFilter}_${currentAts}_${currentSort}_${currentSearch}`;
  const cachedData = Storage.get(sessionStorage, STORAGE_KEYS.CACHED_JOBS, null);
  if (cachedData && cachedData.key === cacheKey && cachedData.jobs && cachedData.jobs.length > 0) {
    cachedJobsMap = {};
    cachedData.jobs.forEach(j => { cachedJobsMap[j.job_id] = j; });
    if (container && (!container.children.length || container.innerText.includes('Loading'))) {
      container.innerHTML = renderJobsListHtml(cachedData.jobs);
    }
  }

  try {
    const url = `/api/jobs?status=${encodeURIComponent(currentFilter)}&ats=${encodeURIComponent(currentAts)}&sort=${encodeURIComponent(currentSort)}&search=${encodeURIComponent(currentSearch)}`;
    const res = await fetch(url, { signal: currentSignal, cache: 'no-store' });
    const data = await parseJsonResponse(res);

    if (data.status !== 'success' || !data.jobs || data.jobs.length === 0) {
      if (container) {
        container.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-muted);">No matching jobs found in tracking store.</div>';
      }
      cachedJobsMap = {};
      return;
    }

    // Cleanly update cachedJobsMap without unbounded memory accumulation
    cachedJobsMap = {};
    data.jobs.forEach(j => { cachedJobsMap[j.job_id] = j; });

    // Cache to sessionStorage
    Storage.set(sessionStorage, STORAGE_KEYS.CACHED_JOBS, {
      key: cacheKey,
      jobs: data.jobs,
      timestamp: Date.now()
    });

    if (container) {
      container.innerHTML = renderJobsListHtml(data.jobs);
    }

    // Check if a deep-linked kit modal needs to be reopened
    const activeKitId = Storage.get(sessionStorage, STORAGE_KEYS.ACTIVE_KIT, '');
    if (activeKitId && cachedJobsMap[activeKitId]) {
      openKitModal(activeKitId);
    }

  } catch (err) {
    if (err.name === 'AbortError') {
      // Ignored: request cancelled in favor of a newer user interaction
      return;
    }
    if (container) {
      container.innerHTML = `<div style="text-align:center; padding:40px; color:var(--danger);">Notice: ${escapeHtml(err.message)}</div>`;
    }
  }
}

// Copy section text with managed timeout map to prevent orphaned timers
function copySectionText(textId, btnId) {
  const el = document.getElementById(textId);
  if (!el) return;
  const txt = el.innerText;
  
  navigator.clipboard.writeText(txt).then(() => {
    const btn = document.getElementById(btnId);
    if (!btn) return;

    const type = btn.getAttribute('data-original');
    let originalHtml = '';
    if (type === 'outreach') {
      originalHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Outreach</span>`;
    } else if (type === 'cover') {
      originalHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Note</span>`;
    }

    btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg><span style="color:#10b981;">Copied!</span>`;
    showToast('Copied to clipboard!', 'success');

    // Clear existing timer if any
    if (copyTimeoutMap.has(btnId)) {
      clearTimeout(copyTimeoutMap.get(btnId));
    }

    const timerId = setTimeout(() => {
      const liveBtn = document.getElementById(btnId);
      if (liveBtn) liveBtn.innerHTML = originalHtml;
      copyTimeoutMap.delete(btnId);
    }, 2000);

    copyTimeoutMap.set(btnId, timerId);
  }).catch(err => {
    showToast('Clipboard copy failed: ' + err.message, 'error');
  });
}

// Open Application Kit Modal with Deep-Link and Memory Cleanliness
function openKitModal(jobId) {
  const j = cachedJobsMap[jobId];
  if (!j || !j.draft) return;

  Storage.set(sessionStorage, STORAGE_KEYS.ACTIVE_KIT, jobId);
  syncUrlState();

  const titleEl = document.getElementById('modal-job-title');
  const metaEl = document.getElementById('modal-job-meta');
  const bodyEl = document.getElementById('modal-body');

  if (titleEl) titleEl.innerText = j.title || 'Job Application Kit';
  if (metaEl) metaEl.innerText = `${j.company} · ${j.location || 'Remote/Unspecified'}`;

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
    html += `<div class="kit-section"><div class="kit-label" style="color:var(--danger);">Honest Gaps / Considerations</div><ul style="padding-left:18px; font-size:13.5px; line-height:1.6; color:var(--text-main);">${d.gaps.map(g => `<li style="margin-bottom:6px; color:#b91c1c;">${escapeHtml(g)}</li>`).join('')}</ul></div>`;
  }
  if (d.questions_to_ask && d.questions_to_ask.length) {
    html += `<div class="kit-section"><div class="kit-label">Questions To Ask</div><ul style="padding-left:18px; font-size:13.5px; line-height:1.6; color:var(--text-main);">${d.questions_to_ask.map(q => `<li style="margin-bottom:6px;">${escapeHtml(q)}</li>`).join('')}</ul></div>`;
  }

  const modalApplyUrl = resolveJobUrl(j);
  html += `<div style="margin-top:24px; text-align:right;"><a href="${escapeHtml(modalApplyUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="display:inline-flex; align-items:center; text-decoration:none;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>Open Posting Page</a></div>`;

  if (bodyEl) bodyEl.innerHTML = html;
  const modalEl = document.getElementById('kit-modal');
  if (modalEl) modalEl.classList.add('active');
}

// Close Modal and Clean DOM Memory
function closeKitModal() {
  const modalEl = document.getElementById('kit-modal');
  if (modalEl) modalEl.classList.remove('active');

  // Free DOM strings and memory
  const bodyEl = document.getElementById('modal-body');
  if (bodyEl) bodyEl.innerHTML = '';

  Storage.remove(sessionStorage, STORAGE_KEYS.ACTIVE_KIT);
  syncUrlState();
}

function copyCoverNote() {
  copySectionText('cover-text', 'btn-copy-cover');
}

// Pipeline Execution
async function runPipeline() {
  const btn = document.getElementById('btn-run');
  const spinner = document.getElementById('run-spinner');
  const text = document.getElementById('run-text');
  const consoleBox = document.getElementById('run-console');
  const isMock = false;

  if (btn) btn.disabled = true;
  if (spinner) spinner.style.display = 'block';
  if (text) text.innerText = 'Hunting Jobs...';
  if (consoleBox) consoleBox.innerText = `Starting pipeline execution...\n[1/5] Scanning ATS endpoints...\n[2/5] Filtering candidate matches...`;

  try {
    const res = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mock: isMock })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      if (consoleBox) consoleBox.innerText = `✅ ${data.message}\nDigest generated & tracking store updated!`;
      showToast('Pipeline run completed successfully!', 'success');
      await refreshAllViews(true);
    } else {
      if (consoleBox) consoleBox.innerText = '❌ Error: ' + (data.message || 'Pipeline failed');
      showToast('Pipeline failed: ' + data.message, 'error');
    }
  } catch (err) {
    if (consoleBox) consoleBox.innerText = '❌ Notice: ' + err.message;
    showToast('Notice: ' + err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
    if (text) text.innerText = 'Run Job Hunt Now';
  }
}

// Toggle Applied Status with Client-side Overlay & Backend Sync
async function toggleAppliedDirect(jobId, action) {
  const btn = document.getElementById('btn-app-' + jobId);
  const isUnmark = action === 'unmark';

  // Optimistic overlay update in localStorage
  const appliedOverlay = Storage.get(localStorage, STORAGE_KEYS.APPLIED_OVERLAY, {}) || {};
  appliedOverlay[jobId] = !isUnmark;
  Storage.set(localStorage, STORAGE_KEYS.APPLIED_OVERLAY, appliedOverlay);

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
      await refreshAllViews(true);
    } else {
      // Revert overlay on failure
      appliedOverlay[jobId] = isUnmark;
      Storage.set(localStorage, STORAGE_KEYS.APPLIED_OVERLAY, appliedOverlay);
      showToast('Notice: ' + data.message, 'error');
      fetchAndRenderJobs();
    }
  } catch (err) {
    appliedOverlay[jobId] = isUnmark;
    Storage.set(localStorage, STORAGE_KEYS.APPLIED_OVERLAY, appliedOverlay);
    showToast('Notice: ' + err.message, 'error');
    fetchAndRenderJobs();
  }
}

// Delete Job Direct
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
      // Clean overlay
      const appliedOverlay = Storage.get(localStorage, STORAGE_KEYS.APPLIED_OVERLAY, {}) || {};
      delete appliedOverlay[jobId];
      Storage.set(localStorage, STORAGE_KEYS.APPLIED_OVERLAY, appliedOverlay);

      showToast(data.message, 'success');
      await refreshAllViews(true);
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

// Mark Applied from Sidebar Input
async function markAppliedFromInput(action) {
  const txt = document.getElementById('txt-job-id');
  const status = document.getElementById('applied-status');
  const jobId = txt ? txt.value.trim() : '';
  
  if (!jobId) {
    if (status) status.innerText = 'Please enter a valid Job ID.';
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
      if (status) status.innerText = '✅ ' + data.message;
      showToast(data.message, 'success');
      if (txt) txt.value = '';
      Storage.remove(sessionStorage, STORAGE_KEYS.DRAFT_APPLIED_ID);
      await refreshAllViews(true);
    } else {
      if (status) status.innerText = '❌ ' + data.message;
      showToast(data.message, 'error');
    }
  } catch (err) {
    if (status) status.innerText = '❌ Notice: ' + err.message;
    showToast(err.message, 'error');
  }
}

// Add Custom Job from Sidebar Form
async function addCustomJobFromInput() {
  const titleEl = document.getElementById('add-title');
  const companyEl = document.getElementById('add-company');
  const locEl = document.getElementById('add-location');
  const urlEl = document.getElementById('add-url');
  const scoreEl = document.getElementById('add-score');
  const appliedEl = document.getElementById('add-applied');
  const status = document.getElementById('add-job-status');

  const title = titleEl ? titleEl.value.trim() : '';
  const company = companyEl ? companyEl.value.trim() : '';

  if (!title || !company) {
    if (status) status.innerText = 'Please enter both Job Title and Company.';
    showToast('Please enter both Job Title and Company.', 'error');
    return;
  }

  if (status) status.innerText = 'Adding job...';

  try {
    const res = await fetch('/api/jobs/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        company: company,
        location: locEl ? locEl.value.trim() || 'Remote/Unspecified' : 'Remote/Unspecified',
        url: urlEl ? urlEl.value.trim() || '#' : '#',
        score: parseFloat(scoreEl ? scoreEl.value : 8.0) || 8.0,
        applied: appliedEl ? appliedEl.checked : false
      })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      if (status) status.innerText = '✅ ' + data.message;
      showToast(data.message, 'success');

      // Clear form inputs and draft
      if (titleEl) titleEl.value = '';
      if (companyEl) companyEl.value = '';
      if (locEl) locEl.value = '';
      if (urlEl) urlEl.value = '';
      if (appliedEl) appliedEl.checked = false;
      Storage.remove(sessionStorage, STORAGE_KEYS.DRAFT_CUSTOM_JOB);

      await refreshAllViews(true);
    } else {
      if (status) status.innerText = '❌ ' + data.message;
      showToast(data.message, 'error');
    }
  } catch (err) {
    if (status) status.innerText = '❌ Notice: ' + err.message;
    showToast(err.message, 'error');
  }
}

// Leak-Free Digest Iframe Refresh
function refreshDigest(force = false) {
  const frame = document.getElementById('digest-frame');
  if (!frame) return;

  // Only refresh if tab is active or force rebuild requested
  if (currentActiveTab !== 'digest' && !force) return;

  const url = '/api/digest?t=' + Date.now();
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

// HTML Escaper
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Form Draft Auto-Saver (Session Atomicity)
function initDraftSaving() {
  const fields = ['add-title', 'add-company', 'add-location', 'add-url', 'add-score', 'add-applied'];
  
  function saveCustomDraft() {
    const draft = {
      title: document.getElementById('add-title')?.value || '',
      company: document.getElementById('add-company')?.value || '',
      location: document.getElementById('add-location')?.value || '',
      url: document.getElementById('add-url')?.value || '',
      score: document.getElementById('add-score')?.value || '8.0',
      applied: document.getElementById('add-applied')?.checked || false
    };
    Storage.set(sessionStorage, STORAGE_KEYS.DRAFT_CUSTOM_JOB, draft);
  }

  fields.forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('input', saveCustomDraft);
      el.addEventListener('change', saveCustomDraft);
    }
  });

  // Restore custom job draft if present
  const savedDraft = Storage.get(sessionStorage, STORAGE_KEYS.DRAFT_CUSTOM_JOB, null);
  if (savedDraft) {
    if (savedDraft.title && document.getElementById('add-title')) document.getElementById('add-title').value = savedDraft.title;
    if (savedDraft.company && document.getElementById('add-company')) document.getElementById('add-company').value = savedDraft.company;
    if (savedDraft.location && document.getElementById('add-location')) document.getElementById('add-location').value = savedDraft.location;
    if (savedDraft.url && document.getElementById('add-url')) document.getElementById('add-url').value = savedDraft.url;
    if (savedDraft.score && document.getElementById('add-score')) document.getElementById('add-score').value = savedDraft.score;
    if (savedDraft.applied && document.getElementById('add-applied')) document.getElementById('add-applied').checked = savedDraft.applied;
  }

  // Quick applied draft
  const txtApplied = document.getElementById('txt-job-id');
  if (txtApplied) {
    txtApplied.addEventListener('input', () => {
      Storage.set(sessionStorage, STORAGE_KEYS.DRAFT_APPLIED_ID, txtApplied.value);
    });
    const savedAppliedId = Storage.get(sessionStorage, STORAGE_KEYS.DRAFT_APPLIED_ID, '');
    if (savedAppliedId) txtApplied.value = savedAppliedId;
  }
}

// Memory-Conscious Polling / Heartbeat Lifecycle
function startHeartbeat() {
  stopHeartbeat();
  heartbeatIntervalId = setInterval(() => {
    if (!document.hidden) {
      loadStats();
    }
  }, 10000);
}

function stopHeartbeat() {
  if (heartbeatIntervalId) {
    clearInterval(heartbeatIntervalId);
    heartbeatIntervalId = null;
  }
}

// Visibility change handler: pauses background resource consumption
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopHeartbeat();
  } else {
    refreshAllViews(false);
    startHeartbeat();
  }
});

// Clean teardown on page hide / unload
window.addEventListener('pagehide', () => {
  stopHeartbeat();
  if (jobsAbortController) jobsAbortController.abort();
  if (syncChannel) syncChannel.close();
});

// Keyboard Shortcuts: '/' to search, 'Esc' to close modal
document.addEventListener('keydown', (e) => {
  if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
    e.preventDefault();
    switchTab('tracker');
    const input = document.getElementById('tracker-search-input');
    if (input) {
      input.focus();
      input.select();
    }
  } else if (e.key === 'Escape') {
    closeKitModal();
  }
});

// Click outside modal to close
document.addEventListener('click', (e) => {
  const modal = document.getElementById('kit-modal');
  if (modal && e.target === modal) {
    closeKitModal();
  }
});

// Initialization on DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
  // 1. Restore URL query params or Storage
  const params = new URLSearchParams(window.location.search);
  const hash = window.location.hash.replace('#', '').toLowerCase();

  const tabParam = params.get('tab') || (hash === 'tracker' || hash === 'digest' ? hash : null);
  const statusParam = params.get('status');
  const atsParam = params.get('ats');
  const sortParam = params.get('sort');
  const searchParam = params.get('search');
  const kitParam = params.get('kit');

  currentActiveTab = tabParam || Storage.get(localStorage, STORAGE_KEYS.ACTIVE_TAB, 'digest');
  currentFilter = statusParam || Storage.get(localStorage, STORAGE_KEYS.STATUS_FILTER, 'all');
  currentAts = atsParam || Storage.get(localStorage, STORAGE_KEYS.ATS_FILTER, 'all');
  currentSort = sortParam || Storage.get(localStorage, STORAGE_KEYS.SORT_BY, 'date');
  currentSearch = searchParam || Storage.get(localStorage, STORAGE_KEYS.SEARCH_QUERY, '');

  if (kitParam) {
    Storage.set(sessionStorage, STORAGE_KEYS.ACTIVE_KIT, kitParam);
  }

  // 2. Populate input controls
  const searchInput = document.getElementById('tracker-search-input');
  const atsSelect = document.getElementById('tracker-ats-select');
  const sortSelect = document.getElementById('tracker-sort-select');

  if (searchInput) {
    searchInput.value = currentSearch;
    searchInput.addEventListener('input', debounce(() => fetchAndRenderJobs(), 250));
  }
  if (atsSelect) atsSelect.value = currentAts;
  if (sortSelect) sortSelect.value = currentSort;

  // 3. Set filter pills
  document.querySelectorAll('.filter-pills .pill').forEach(el => el.classList.remove('active'));
  const activePill = document.getElementById('pill-' + currentFilter);
  if (activePill) activePill.classList.add('active');

  // 4. Set active tab
  switchTab(currentActiveTab);

  // 5. Initialize draft auto-saving
  initDraftSaving();

  // 6. Initial data load & start heartbeat
  loadStats();
  fetchAndRenderJobs();
  startHeartbeat();
});
