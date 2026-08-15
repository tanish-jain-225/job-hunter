/**
 * Job Hunter — Executive Career Dashboard Client Engine
 * 
 * Features:
 * - Zero-Refresh Real-Time State Synchronization Engine
 * - Sub-millisecond Optimistic UI Updates (Applied Toggle, Job Deletion, Custom Job Insertion)
 * - Cross-Tab Instant Sync via BroadcastChannel & Storage Event Listeners
 * - Adaptive Background Heartbeat (polling /api/sync with version hash comparison)
 * - Deep-Linking & State Persistence (Tabs, Filters, Search, Sort, Modal)
 * - Match-Highlighted Live Search with embedded clear button & keyboard shortcut ('/')
 * - Modal In-Place Applied Status Controls & Zero-Flicker Digest Sync
 * - Full Memory & Event Teardown Management
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
  DRAFT_CUSTOM_JOB: 'jobhunt_draft_custom_job',
  DRAFT_APPLIED_ID: 'jobhunt_draft_applied_id',
  ACTIVE_KIT: 'jobhunt_active_kit'
};

// Safe Storage Wrapper
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

// Global In-Memory Application State
const appState = {
  version: null,
  stats: { tracked: 0, emailed: 0, applied: 0, shortlisted: 0, unapplied: 0 },
  filter: 'all',
  ats: 'all',
  sort: 'date',
  search: '',
  activeTab: 'digest',
  activeKitId: null,
  jobsMap: {},
  jobsList: [],
  isSyncing: false,
  isOffline: !navigator.onLine,
  lastSyncTimestamp: Date.now()
};

let jobsAbortController = null;
let heartbeatIntervalId = null;
let searchDebounceTimer = null;
let lastIframeDigestUrl = '';
const copyTimeoutMap = new Map();
const activeToasts = [];

// Cross-Tab BroadcastChannel Engine
let syncChannel = null;
try {
  if (typeof BroadcastChannel !== 'undefined') {
    syncChannel = new BroadcastChannel('jobhunt_sync');
    syncChannel.onmessage = (event) => {
      if (event.data && (event.data.type === 'SYNC_UPDATE' || event.data.type === 'STATE_MUTATED')) {
        syncDashboard(false);
      }
    };
  }
} catch (e) {
  console.warn('BroadcastChannel unavailable:', e);
}

// Fallback multi-tab storage listener
window.addEventListener('storage', (e) => {
  if (e.key === STORAGE_KEYS.CACHED_STATS || e.key === 'jobhunt_sync_ping') {
    syncDashboard(false);
  }
});

function broadcastSync(type = 'STATE_MUTATED', payload = {}) {
  if (syncChannel) {
    try {
      syncChannel.postMessage({ type, timestamp: Date.now(), ...payload });
    } catch (e) {
      console.warn('Sync post error:', e);
    }
  }
  // Storage event fallback trigger
  Storage.set(localStorage, 'jobhunt_sync_ping', Date.now());
}

// Enforce Light Mode theme
document.documentElement.setAttribute('data-theme', 'light');

// Utility: Debounce function
function debounce(fn, delay = 200) {
  return function (...args) {
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      fn.apply(this, args);
      searchDebounceTimer = null;
    }, delay);
  };
}

// Toast Notifications (bounded queue)
function showToast(message, type = 'success', duration = 3000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

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

  const toastRecord = { element: toast, timer: null };

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

// Safe JSON parser
async function parseJsonResponse(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch (err) {
    if (!res.ok) {
      throw new Error(`Server HTTP ${res.status} (${res.statusText || 'Server Error'})`);
    }
    throw new Error('Unexpected server response format');
  }
}

// URL State Syncing & Deep-Linking Helper
function syncUrlState() {
  try {
    const url = new URL(window.location.href);
    url.searchParams.set('tab', appState.activeTab);
    
    if (appState.filter && appState.filter !== 'all') {
      url.searchParams.set('status', appState.filter);
    } else {
      url.searchParams.delete('status');
    }

    if (appState.ats && appState.ats !== 'all') {
      url.searchParams.set('ats', appState.ats);
    } else {
      url.searchParams.delete('ats');
    }

    if (appState.sort && appState.sort !== 'date') {
      url.searchParams.set('sort', appState.sort);
    } else {
      url.searchParams.delete('sort');
    }

    if (appState.search) {
      url.searchParams.set('search', appState.search);
    } else {
      url.searchParams.delete('search');
    }

    if (appState.activeKitId) {
      url.searchParams.set('kit', appState.activeKitId);
    } else {
      url.searchParams.delete('kit');
    }

    window.history.replaceState({}, '', url.toString());
  } catch (e) {
    console.warn('URL sync error:', e);
  }
}

// Live Sync UI Status Controller
function setSyncStatus(status, label = null) {
  const indicator = document.getElementById('sync-status-indicator');
  const textEl = document.getElementById('sync-text');
  const btnSyncIcon = document.getElementById('btn-sync-icon');
  if (!indicator || !textEl) return;

  indicator.classList.remove('syncing', 'offline');
  if (btnSyncIcon) btnSyncIcon.classList.remove('spinning');

  if (status === 'syncing') {
    indicator.classList.add('syncing');
    textEl.innerText = label || 'Syncing...';
    if (btnSyncIcon) btnSyncIcon.classList.add('spinning');
  } else if (status === 'offline') {
    indicator.classList.add('offline');
    textEl.innerText = 'Offline';
  } else {
    textEl.innerText = label || 'Live Synced';
  }
}

// Metrics & Filter Counts Renderer
function renderMetrics(stats) {
  if (!stats) return;
  appState.stats = { ...appState.stats, ...stats };

  const trackedEl = document.getElementById('metric-tracked');
  const emailedEl = document.getElementById('metric-emailed');
  const appliedEl = document.getElementById('metric-applied');

  if (trackedEl && trackedEl.innerText !== String(stats.tracked ?? 0)) {
    trackedEl.innerText = stats.tracked ?? 0;
    trackedEl.style.transform = 'scale(1.15)';
    setTimeout(() => { trackedEl.style.transform = 'scale(1)'; }, 200);
  }
  if (emailedEl) emailedEl.innerText = stats.emailed ?? 0;
  if (appliedEl && appliedEl.innerText !== String(stats.applied ?? 0)) {
    appliedEl.innerText = stats.applied ?? 0;
    appliedEl.style.transform = 'scale(1.15)';
    setTimeout(() => { appliedEl.style.transform = 'scale(1)'; }, 200);
  }

  // Update dynamic count badges on filter pills
  const countAll = document.getElementById('count-all');
  const countShortlisted = document.getElementById('count-shortlisted');
  const countApplied = document.getElementById('count-applied');
  const countUnapplied = document.getElementById('count-unapplied');

  if (countAll) countAll.innerText = stats.tracked ?? 0;
  if (countShortlisted) countShortlisted.innerText = stats.shortlisted ?? 0;
  if (countApplied) countApplied.innerText = stats.applied ?? 0;
  if (countUnapplied) countUnapplied.innerText = stats.unapplied ?? 0;

  Storage.set(localStorage, STORAGE_KEYS.CACHED_STATS, {
    stats: stats,
    timestamp: Date.now()
  });
}

// Master Zero-Refresh Sync Engine: Checks version and reconciles data
async function syncDashboard(force = false) {
  if (appState.isSyncing && !force) return;
  if (!navigator.onLine) {
    setSyncStatus('offline');
    return;
  }

  appState.isSyncing = true;
  if (force) setSyncStatus('syncing');

  try {
    const res = await fetch('/api/sync', { cache: 'no-store' });
    const data = await parseJsonResponse(res);

    if (data.status === 'success') {
      const serverVersion = data.version;
      const hasVersionChanged = appState.version !== serverVersion;
      appState.version = serverVersion;
      appState.lastSyncTimestamp = Date.now();

      renderMetrics(data.stats);

      // If version changed or force reload requested, update jobs & digest
      if (hasVersionChanged || force) {
        await fetchAndRenderJobs(false);
        refreshDigest(true);
      }

      setSyncStatus('synced');
    }
  } catch (err) {
    console.warn('Sync check notice:', err);
    if (!navigator.onLine) {
      setSyncStatus('offline');
    }
  } finally {
    appState.isSyncing = false;
  }
}

// Manual Sync Button Trigger
async function manualSync() {
  setSyncStatus('syncing', 'Syncing now...');
  await syncDashboard(true);
  showToast('Dashboard is up to date!', 'success', 2000);
}

// Tab Switching with URL & LocalStorage Persistence
function switchTab(tab) {
  appState.activeTab = tab;
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
    fetchAndRenderJobs(false);
  }
}

// Filter Pills with State Persistence
function setFilter(filter) {
  appState.filter = filter;
  Storage.set(localStorage, STORAGE_KEYS.STATUS_FILTER, filter);

  document.querySelectorAll('.filter-pills .pill').forEach(el => el.classList.remove('active'));
  const pill = document.getElementById('pill-' + filter);
  if (pill) pill.classList.add('active');

  syncUrlState();
  fetchAndRenderJobs(false);
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

// Highlight matching search query in strings safely
function highlightText(text, query) {
  if (!text) return '';
  const escapedText = escapeHtml(text);
  if (!query || !query.trim()) return escapedText;

  const q = query.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const regex = new RegExp(`(${q})`, 'gi');
  return escapedText.replace(regex, '<span class="highlight-match">$1</span>');
}

// Render HTML for single job item card
function renderJobCardHtml(j, isNew = false) {
  const score = j.score != null ? Number(j.score).toFixed(1) : 'N/A';
  const scoreClass = j.score >= 8.5 ? 'score-high' : (j.score >= 7.0 ? 'score-mid' : 'score-low');
  const isApplied = Boolean(j.applied);
  const hasDraft = j.draft && (j.draft.cover_note || j.draft.fit_summary);
  const applyUrl = resolveJobUrl(j);
  const searchQuery = appState.search;

  return `
    <div class="job-item ${isNew ? 'job-item-new' : ''}" id="job-card-${escapeHtml(j.job_id)}">
      <div class="job-meta">
        <div class="job-header-row">
          <span class="job-title">${highlightText(j.title, searchQuery)}</span>
          <span class="ats-tag">${escapeHtml(j.ats || 'ats')}</span>
          ${isNew ? '<span class="badge-live-sync">✨ Just Added</span>' : ''}
        </div>
        <div class="job-sub">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 4px;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg><strong>${highlightText(j.company, searchQuery)}</strong> 
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle; margin-right: 4px; margin-left: 8px;"><path d="M12 2a8 8 0 0 0-8 8c0 5.25 8 12 8 12s8-6.75 8-12a8 8 0 0 0-8-8z"></path><circle cx="12" cy="10" r="3"></circle></svg>${highlightText(j.location || 'Remote/Unspecified', searchQuery)}
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
}

// Render HTML for an array of jobs
function renderJobsListHtml(jobs) {
  return jobs.map(j => renderJobCardHtml(j, false)).join('');
}

// Fetch and Render Jobs with AbortController & SWR
async function fetchAndRenderJobs(showLoadingIndicator = true) {
  const container = document.getElementById('job-list-container');
  const searchInput = document.getElementById('tracker-search-input');
  const atsSelect = document.getElementById('tracker-ats-select');
  const sortSelect = document.getElementById('tracker-sort-select');

  appState.search = searchInput ? searchInput.value.trim() : '';
  appState.ats = atsSelect ? atsSelect.value : 'all';
  appState.sort = sortSelect ? sortSelect.value : 'date';

  Storage.set(localStorage, STORAGE_KEYS.SEARCH_QUERY, appState.search);
  Storage.set(localStorage, STORAGE_KEYS.ATS_FILTER, appState.ats);
  Storage.set(localStorage, STORAGE_KEYS.SORT_BY, appState.sort);
  syncUrlState();

  if (jobsAbortController) {
    jobsAbortController.abort();
  }
  jobsAbortController = new AbortController();
  const currentSignal = jobsAbortController.signal;

  if (showLoadingIndicator && container && (!container.children.length || container.innerText.includes('Loading'))) {
    container.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-muted);"><span class="spinner" style="display:inline-block; margin-right:8px;"></span>Loading jobs...</div>';
  }

  try {
    const url = `/api/jobs?status=${encodeURIComponent(appState.filter)}&ats=${encodeURIComponent(appState.ats)}&sort=${encodeURIComponent(appState.sort)}&search=${encodeURIComponent(appState.search)}`;
    const res = await fetch(url, { signal: currentSignal, cache: 'no-store' });
    const data = await parseJsonResponse(res);

    if (data.status !== 'success' || !data.jobs || data.jobs.length === 0) {
      if (container) {
        container.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-muted);">No matching jobs found in tracking store.</div>';
      }
      appState.jobsMap = {};
      appState.jobsList = [];
      return;
    }

    appState.jobsList = data.jobs;
    appState.jobsMap = {};
    data.jobs.forEach(j => { appState.jobsMap[j.job_id] = j; });

    if (container) {
      container.innerHTML = renderJobsListHtml(data.jobs);
    }

    // Re-sync modal if open
    if (appState.activeKitId && appState.jobsMap[appState.activeKitId]) {
      updateModalAppliedButton(appState.jobsMap[appState.activeKitId]);
    }

  } catch (err) {
    if (err.name === 'AbortError') return;
    if (container) {
      container.innerHTML = `<div style="text-align:center; padding:40px; color:var(--danger);">Notice: ${escapeHtml(err.message)}</div>`;
    }
  }
}

// Search Input Handlers
function handleSearchInput() {
  const input = document.getElementById('tracker-search-input');
  const clearBtn = document.getElementById('search-clear-btn');
  if (input && clearBtn) {
    clearBtn.style.display = input.value.trim() ? 'flex' : 'none';
  }
  debouncedSearch();
}

const debouncedSearch = debounce(() => {
  fetchAndRenderJobs(false);
}, 180);

function clearSearch() {
  const input = document.getElementById('tracker-search-input');
  const clearBtn = document.getElementById('search-clear-btn');
  if (input) {
    input.value = '';
    input.focus();
  }
  if (clearBtn) clearBtn.style.display = 'none';
  fetchAndRenderJobs(false);
}

// Copy section text helper
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

// Application Kit Modal
function updateModalAppliedButton(job) {
  const btn = document.getElementById('modal-applied-toggle-btn');
  if (!btn || !job) return;

  const isApplied = Boolean(job.applied);
  btn.className = isApplied ? 'btn btn-secondary btn-sm btn-applied' : 'btn btn-secondary btn-sm';
  btn.innerHTML = isApplied
    ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Applied`
    : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>Mark Applied`;
  btn.setAttribute('data-job-id', job.job_id);
  btn.setAttribute('data-action', isApplied ? 'unmark' : 'mark');
}

function toggleModalAppliedDirect() {
  const btn = document.getElementById('modal-applied-toggle-btn');
  if (!btn) return;
  const jobId = btn.getAttribute('data-job-id');
  const action = btn.getAttribute('data-action') || 'mark';
  if (jobId) {
    toggleAppliedDirect(jobId, action);
  }
}

function openKitModal(jobId) {
  const j = appState.jobsMap[jobId];
  if (!j || !j.draft) return;

  appState.activeKitId = jobId;
  Storage.set(sessionStorage, STORAGE_KEYS.ACTIVE_KIT, jobId);
  syncUrlState();

  const titleEl = document.getElementById('modal-job-title');
  const metaEl = document.getElementById('modal-job-meta');
  const bodyEl = document.getElementById('modal-body');

  if (titleEl) titleEl.innerText = j.title || 'Job Application Kit';
  if (metaEl) metaEl.innerText = `${j.company} · ${j.location || 'Remote/Unspecified'}`;

  updateModalAppliedButton(j);

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

function closeKitModal() {
  const modalEl = document.getElementById('kit-modal');
  if (modalEl) modalEl.classList.remove('active');

  const bodyEl = document.getElementById('modal-body');
  if (bodyEl) bodyEl.innerHTML = '';

  appState.activeKitId = null;
  Storage.remove(sessionStorage, STORAGE_KEYS.ACTIVE_KIT);
  syncUrlState();
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
  if (consoleBox) consoleBox.innerText = `Starting pipeline execution...\n[1/5] Scanning ATS endpoints...\n[2/5] Filtering candidate matches...\n[3/5] Scoring via AI engine...`;

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
      await syncDashboard(true);
      broadcastSync('STATE_MUTATED');
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

// Toggle Applied Status with Optimistic UI & Zero-Refresh Sync
async function toggleAppliedDirect(jobId, action) {
  const btn = document.getElementById('btn-app-' + jobId);
  const isUnmark = action === 'unmark';
  const job = appState.jobsMap[jobId];

  // 1. Optimistic Local State Update
  if (job) {
    job.applied = !isUnmark;
    if (appState.activeKitId === jobId) {
      updateModalAppliedButton(job);
    }
  }

  // 2. Optimistic Button UI Update
  if (btn) {
    btn.innerHTML = isUnmark 
      ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>Mark Applied`
      : `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg>Applied`;
    btn.className = isUnmark ? 'btn btn-secondary btn-sm' : 'btn btn-secondary btn-sm btn-applied';
    btn.setAttribute('onclick', `toggleAppliedDirect('${escapeHtml(jobId)}', '${isUnmark ? 'mark' : 'unmark'}')`);
  }

  // 3. Optimistic Stats Update
  const newAppliedCount = Math.max(0, (appState.stats.applied || 0) + (isUnmark ? -1 : 1));
  const newUnappliedCount = Math.max(0, (appState.stats.unapplied || 0) + (isUnmark ? 1 : -1));
  renderMetrics({
    ...appState.stats,
    applied: newAppliedCount,
    unapplied: newUnappliedCount
  });

  try {
    const res = await fetch('/api/applied', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, action: action })
    });
    const data = await parseJsonResponse(res);

    if (data.status === 'success') {
      showToast(data.message, 'success');
      appState.version = data.version;
      renderMetrics(data.stats);
      refreshDigest(true);
      broadcastSync('STATE_MUTATED', { jobId, applied: !isUnmark });
    } else {
      // Revert optimistic state on error
      if (job) job.applied = isUnmark;
      fetchAndRenderJobs(false);
      showToast('Notice: ' + data.message, 'error');
    }
  } catch (err) {
    if (job) job.applied = isUnmark;
    fetchAndRenderJobs(false);
    showToast('Notice: ' + err.message, 'error');
  }
}

// Delete Job with Instant Optimistic Collapse
async function deleteJobDirect(jobId) {
  if (!confirm(`Are you sure you want to delete job '${jobId}' from tracking store?`)) {
    return;
  }

  const card = document.getElementById('job-card-' + jobId);
  if (card) {
    card.classList.add('removing');
  }

  // Optimistic count decrement
  const newTracked = Math.max(0, (appState.stats.tracked || 1) - 1);
  renderMetrics({ ...appState.stats, tracked: newTracked });

  try {
    const res = await fetch('/api/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId })
    });
    const data = await parseJsonResponse(res);

    if (data.status === 'success') {
      delete appState.jobsMap[jobId];
      if (card) card.remove();
      if (appState.activeKitId === jobId) closeKitModal();
      showToast(data.message, 'success');
      appState.version = data.version;
      renderMetrics(data.stats);
      refreshDigest(true);
      broadcastSync('STATE_MUTATED', { jobId, deleted: true });
    } else {
      if (card) card.classList.remove('removing');
      showToast('Notice: ' + data.message, 'error');
      fetchAndRenderJobs(false);
    }
  } catch (err) {
    if (card) card.classList.remove('removing');
    showToast('Notice: ' + err.message, 'error');
    fetchAndRenderJobs(false);
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
      appState.version = data.version;
      renderMetrics(data.stats);
      await fetchAndRenderJobs(false);
      refreshDigest(true);
      broadcastSync('STATE_MUTATED');
    } else {
      if (status) status.innerText = '❌ ' + data.message;
      showToast(data.message, 'error');
    }
  } catch (err) {
    if (status) status.innerText = '❌ Notice: ' + err.message;
    showToast(err.message, 'error');
  }
}

// Add Custom Job from Sidebar Form with Instant UI Prepend
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

      appState.version = data.version;
      renderMetrics(data.stats);

      // Prepend to current job list if matches filter
      if (data.job) {
        appState.jobsMap[data.job.job_id] = data.job;
        const container = document.getElementById('job-list-container');
        if (container) {
          if (container.innerText.includes('No matching') || container.innerText.includes('Loading')) {
            container.innerHTML = '';
          }
          container.insertAdjacentHTML('afterbegin', renderJobCardHtml(data.job, true));
        }
      }

      refreshDigest(true);
      broadcastSync('STATE_MUTATED');
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

  if (appState.activeTab !== 'digest' && !force) return;

  const url = '/api/digest?t=' + Date.now();
  if (lastIframeDigestUrl === url) return;
  lastIframeDigestUrl = url;

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

  const savedDraft = Storage.get(sessionStorage, STORAGE_KEYS.DRAFT_CUSTOM_JOB, null);
  if (savedDraft) {
    if (savedDraft.title && document.getElementById('add-title')) document.getElementById('add-title').value = savedDraft.title;
    if (savedDraft.company && document.getElementById('add-company')) document.getElementById('add-company').value = savedDraft.company;
    if (savedDraft.location && document.getElementById('add-location')) document.getElementById('add-location').value = savedDraft.location;
    if (savedDraft.url && document.getElementById('add-url')) document.getElementById('add-url').value = savedDraft.url;
    if (savedDraft.score && document.getElementById('add-score')) document.getElementById('add-score').value = savedDraft.score;
    if (savedDraft.applied && document.getElementById('add-applied')) document.getElementById('add-applied').checked = savedDraft.applied;
  }

  const txtApplied = document.getElementById('txt-job-id');
  if (txtApplied) {
    txtApplied.addEventListener('input', () => {
      Storage.set(sessionStorage, STORAGE_KEYS.DRAFT_APPLIED_ID, txtApplied.value);
    });
    const savedAppliedId = Storage.get(sessionStorage, STORAGE_KEYS.DRAFT_APPLIED_ID, '');
    if (savedAppliedId) txtApplied.value = savedAppliedId;
  }
}

// Adaptive Background Polling Heartbeat
function startHeartbeat() {
  stopHeartbeat();
  heartbeatIntervalId = setInterval(() => {
    if (!document.hidden && navigator.onLine) {
      syncDashboard(false);
    }
  }, 2500);
}

function stopHeartbeat() {
  if (heartbeatIntervalId) {
    clearInterval(heartbeatIntervalId);
    heartbeatIntervalId = null;
  }
}

// Visibility & Online Event Handlers
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopHeartbeat();
  } else {
    syncDashboard(false);
    startHeartbeat();
  }
});

window.addEventListener('online', () => {
  appState.isOffline = false;
  setSyncStatus('syncing', 'Reconnected — syncing...');
  syncDashboard(true);
  showToast('Network connection restored', 'success');
  startHeartbeat();
});

window.addEventListener('offline', () => {
  appState.isOffline = true;
  setSyncStatus('offline');
  showToast('You are offline. Reconnecting...', 'info');
});

// Clean teardown on pagehide
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
    if (document.getElementById('kit-modal')?.classList.contains('active')) {
      closeKitModal();
    } else {
      const searchInput = document.getElementById('tracker-search-input');
      if (searchInput && searchInput.value) {
        clearSearch();
      }
    }
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
  const params = new URLSearchParams(window.location.search);
  const hash = window.location.hash.replace('#', '').toLowerCase();

  const tabParam = params.get('tab') || (hash === 'tracker' || hash === 'digest' ? hash : null);
  const statusParam = params.get('status');
  const atsParam = params.get('ats');
  const sortParam = params.get('sort');
  const searchParam = params.get('search');
  const kitParam = params.get('kit');

  appState.activeTab = tabParam || Storage.get(localStorage, STORAGE_KEYS.ACTIVE_TAB, 'digest');
  appState.filter = statusParam || Storage.get(localStorage, STORAGE_KEYS.STATUS_FILTER, 'all');
  appState.ats = atsParam || Storage.get(localStorage, STORAGE_KEYS.ATS_FILTER, 'all');
  appState.sort = sortParam || Storage.get(localStorage, STORAGE_KEYS.SORT_BY, 'date');
  appState.search = searchParam || Storage.get(localStorage, STORAGE_KEYS.SEARCH_QUERY, '');

  if (kitParam) {
    appState.activeKitId = kitParam;
  }

  // Populate controls
  const searchInput = document.getElementById('tracker-search-input');
  const clearBtn = document.getElementById('search-clear-btn');
  const atsSelect = document.getElementById('tracker-ats-select');
  const sortSelect = document.getElementById('tracker-sort-select');

  if (searchInput) {
    searchInput.value = appState.search;
    if (clearBtn) clearBtn.style.display = appState.search ? 'flex' : 'none';
  }
  if (atsSelect) atsSelect.value = appState.ats;
  if (sortSelect) sortSelect.value = appState.sort;

  // Set filter pill
  document.querySelectorAll('.filter-pills .pill').forEach(el => el.classList.remove('active'));
  const activePill = document.getElementById('pill-' + appState.filter);
  if (activePill) activePill.classList.add('active');

  // Hydrate cached stats
  const cachedStats = Storage.get(localStorage, STORAGE_KEYS.CACHED_STATS, null);
  if (cachedStats && cachedStats.stats) {
    renderMetrics(cachedStats.stats);
  }

  // Set active tab
  switchTab(appState.activeTab);

  // Initialize draft saving
  initDraftSaving();

  // Initial full sync and start heartbeat
  syncDashboard(true);
  startHeartbeat();
});
