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
 * - Drag-and-Drop Resume Studio AI File & Text Parser
 * - Accessible Full Memory & Event Teardown Management
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
  CACHED_PROFILE: 'jobhunt_cached_profile',
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
  trackerView: 'table',
  activeTab: 'digest',
  activeKitId: null,
  jobsMap: {},
  jobsList: [],
  isSyncing: false,
  isSavingProfile: false,
  isOffline: !navigator.onLine,
  lastSyncTimestamp: Date.now()
};

function switchTrackerView(viewMode) {
  appState.trackerView = viewMode === 'kanban' ? 'kanban' : 'table';
  Storage.set(localStorage, 'jobhunt_tracker_view', appState.trackerView);
  const btnTable = document.getElementById('btn-view-table');
  const btnKanban = document.getElementById('btn-view-kanban');
  if (btnTable) btnTable.classList.toggle('active', appState.trackerView === 'table');
  if (btnKanban) btnKanban.classList.toggle('active', appState.trackerView === 'kanban');
  const container = document.getElementById('job-list-container');
  if (container && appState.jobsList) {
    container.innerHTML = renderJobsListHtml(appState.jobsList);
  }
}

function renderKanbanCardHtml(j) {
  const score = j.score != null ? Number(j.score).toFixed(1) : 'N/A';
  const scoreClass = j.score >= 8.5 ? 'score-high' : (j.score >= 7.0 ? 'score-mid' : 'score-low');
  const stage = j.application_stage || (j.applied ? 'applied' : 'to_apply');
  const searchQuery = appState.search;
  const applyUrl = resolveJobUrl(j);
  const hasDraft = j.draft && (j.draft.cover_note || j.draft.fit_summary || j.draft.cold_outreach);

  return `
    <div class="kanban-card" id="kanban-card-${escapeHtml(j.job_id)}" onclick="if(event.target.tagName!=='SELECT'&&event.target.tagName!=='A'&&event.target.tagName!=='BUTTON') openKitModal('${escapeHtml(j.job_id)}')">
      <div class="kanban-card-top">
        <span class="kanban-card-company">${highlightText(j.company, searchQuery)}</span>
        <span class="score-badge ${scoreClass}">${score}</span>
      </div>
      <div class="kanban-card-title">${highlightText(j.title, searchQuery)}</div>
      <div class="kanban-card-meta">
        <span>${escapeHtml(j.location || 'Remote/Unspecified')}</span>
        <span>·</span>
        <span class="ats-tag" style="font-size:10px;">${escapeHtml(j.ats || 'ats')}</span>
      </div>
      <div class="kanban-card-actions">
        <select class="kanban-stage-select" aria-label="Application stage for ${escapeHtml(j.title || 'Job')} at ${escapeHtml(j.company || 'Company')}" onchange="updateJobStageDirect('${escapeHtml(j.job_id)}', this.value)" onclick="event.stopPropagation()">
          <option value="to_apply" ${stage==='to_apply'?'selected':''}>To Apply</option>
          <option value="applied" ${stage==='applied'?'selected':''}>Applied</option>
          <option value="interviewing" ${stage==='interviewing'?'selected':''}>Interviewing</option>
          <option value="offer" ${stage==='offer'?'selected':''}>Offer</option>
          <option value="rejected" ${stage==='rejected'?'selected':''}>Rejected</option>
        </select>
        <div style="display:flex; gap:4px;">
          ${hasDraft ? `<button class="btn btn-secondary btn-sm" style="padding:2px 6px; font-size:11px;" onclick="event.stopPropagation(); openKitModal('${escapeHtml(j.job_id)}')">Kit</button>` : ''}
          <a href="${escapeHtml(applyUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="padding:2px 6px; font-size:11px; text-decoration:none;" onclick="event.stopPropagation()">Link</a>
        </div>
      </div>
    </div>
  `;
}

function renderKanbanBoardHtml(jobs) {
  const stages = [
    { key: 'to_apply', label: 'To Apply', icon: '📝' },
    { key: 'applied', label: 'Applied', icon: '🚀' },
    { key: 'interviewing', label: 'Interviewing', icon: '💬' },
    { key: 'offer', label: 'Offer', icon: '🎉' },
    { key: 'rejected', label: 'Archived', icon: '📁' },
  ];

  const columns = {};
  stages.forEach(s => { columns[s.key] = []; });

  jobs.forEach(j => {
    const st = j.application_stage || (j.applied ? 'applied' : 'to_apply');
    if (columns[st]) {
      columns[st].push(j);
    } else {
      columns['to_apply'].push(j);
    }
  });

  return `
    <div class="kanban-board-container">
      ${stages.map(s => `
        <div class="kanban-column" id="kanban-col-${s.key}">
          <div class="kanban-column-header">
            <span class="kanban-col-title"><span>${s.icon}</span> <span>${s.label}</span></span>
            <span class="kanban-col-count">${columns[s.key].length}</span>
          </div>
          <div class="kanban-cards-list">
            ${columns[s.key].length > 0
              ? columns[s.key].map(j => renderKanbanCardHtml(j)).join('')
              : '<div style="text-align:center; padding:30px 10px; font-size:12px; color:var(--text-muted);">No jobs in this stage</div>'
            }
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

async function updateJobStageDirect(jobId, newStage) {
  const j = appState.jobsMap[jobId];
  if (!j) return;

  const oldStage = j.application_stage;
  const oldApplied = j.applied;

  j.application_stage = newStage;
  j.applied = (newStage === 'applied' || newStage === 'interviewing' || newStage === 'offer' || newStage === 'rejected');

  const container = document.getElementById('job-list-container');
  if (container && appState.jobsList) {
    container.innerHTML = renderJobsListHtml(appState.jobsList);
  }

  showToast(`Moved to ${newStage.replace('_', ' ')}`, 'success');

  try {
    const res = await authFetch('/api/jobs/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, stage: newStage })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      if (data.version) appState.version = data.version;
      if (data.stats) updateStatsDisplay(data.stats);
      broadcastSync('STATE_MUTATED', { job_id: jobId, stage: newStage });
    } else {
      throw new Error(data.message || 'Stage update failed');
    }
  } catch (err) {
    j.application_stage = oldStage;
    j.applied = oldApplied;
    if (container && appState.jobsList) {
      container.innerHTML = renderJobsListHtml(appState.jobsList);
    }
    showToast('Failed to update stage: ' + err.message, 'error');
  }
}

// Render HTML for an array of jobs (supports Table and Kanban views)
function renderJobsListHtml(jobs) {
  if (appState.trackerView === 'kanban') {
    return renderKanbanBoardHtml(jobs);
  }
  return jobs.map(j => renderJobCardHtml(j, false)).join('');
}

// Supabase Authentication Global State
let supabaseClient = null;
let currentAuthSession = null;
let authConfig = {
  auth_required: false,
  supabase_url: '',
  supabase_anon_key: ''
};

// Authenticated Fetch Wrapper with Automatic Token Refresh
async function authFetch(url, options = {}) {
  const opts = { ...options };
  const headers = new Headers(opts.headers || {});

  // Retrieve freshest token from active Supabase session if available
  if (supabaseClient) {
    try {
      const { data } = await supabaseClient.auth.getSession();
      if (data?.session) {
        currentAuthSession = data.session;
      }
    } catch (e) {
      console.warn('Session refresh notice:', e);
    }
  }

  if (currentAuthSession && currentAuthSession.access_token) {
    headers.set('Authorization', `Bearer ${currentAuthSession.access_token}`);
  }

  opts.headers = headers;

  try {
    const res = await fetch(url, opts);
    if (res.status === 401 && authConfig.auth_required) {
      console.warn('Unauthorized API access (401). Prompting login.');
      stopHeartbeat();
      openAuthModal('signin');
      setAuthFeedback('Your secure session has expired or authentication is required. Please sign in.', 'error');
    }
    return res;
  } catch (err) {
    throw err;
  }
}

let jobsAbortController = null;
let heartbeatIntervalId = null;
let searchDebounceTimer = null;
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

// Toast Notifications (bounded queue with auto-portal creation)
function showToast(message, type = 'success', duration = 3000) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  while (activeToasts.length >= 4) {
    const oldest = activeToasts.shift();
    if (oldest && oldest.element && oldest.element.parentNode) {
      clearTimeout(oldest.timer);
      oldest.element.remove();
    }
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  let iconSvg = '';
  if (type === 'success') {
    iconSvg = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--success); flex-shrink:0;"><polyline points="20 6 9 17 4 12"></polyline></svg>';
  } else if (type === 'error') {
    iconSvg = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--danger); flex-shrink:0;"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>';
  } else {
    iconSvg = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--primary); flex-shrink:0;"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
  }
  toast.innerHTML = `${iconSvg}<span>${escapeHtml(message)}</span>`;
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
let lastSyncedUrl = '';

function syncUrlState() {
  try {
    const url = new URL(window.location.href);
    if (appState.activeTab) {
      url.searchParams.set('tab', appState.activeTab);
    }
    
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

    const currentHref = window.location.pathname + window.location.search + window.location.hash;
    const newHref = url.pathname + url.search + url.hash;

    // Only update history if the URL parameters actually changed
    if (currentHref !== newHref && lastSyncedUrl !== newHref) {
      lastSyncedUrl = newHref;
      window.history.replaceState(null, '', newHref);
    }
  } catch (e) {
    console.warn('URL sync error:', e);
  }
}

// Live Sync UI Status Controller
function setSyncStatus(status, label = null) {
  const indicator = document.getElementById('sync-status') || document.getElementById('sync-status-indicator');
  const textEl = document.getElementById('sync-text');
  if (!indicator || !textEl) return;

  indicator.classList.remove('syncing', 'offline');

  if (status === 'syncing') {
    indicator.classList.add('syncing');
    textEl.innerText = label || 'Syncing...';
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
  if (authConfig.auth_required && !currentAuthSession) return;
  if (appState.isSavingProfile) return;
  if (appState.isSyncing && !force) return;
  if (!navigator.onLine) {
    setSyncStatus('offline');
    return;
  }

  appState.isSyncing = true;
  if (force) setSyncStatus('syncing');

  try {
    const res = await authFetch('/api/sync', { cache: 'no-store' });
    const data = await parseJsonResponse(res);

    if (data.status === 'success') {
      const serverVersion = data.version;
      const hasVersionChanged = appState.version !== serverVersion;
      appState.version = serverVersion;
      appState.lastSyncTimestamp = Date.now();

      renderMetrics(data.stats);

      if (data.pipeline) {
        updatePipelineConsole(data.pipeline);
      }

      if (data.user_profile) {
        activeProfileData = data.user_profile;
        renderCandidateSummary(data.user_profile);
      }

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

// Live Pipeline Console & Button State Updater
function updatePipelineConsole(pipeline) {
  const btn = document.getElementById('btn-run');
  const spinner = document.getElementById('run-spinner');
  const text = document.getElementById('run-text');
  const consoleBox = document.getElementById('run-console');
  const mainConsole = document.getElementById('main-run-console');

  if (!pipeline) {
    if (spinner) spinner.style.display = 'none';
    updateJobSearchButtonState();
    return;
  }

  if (pipeline.running) {
    appState.pipelineRunning = true;
    if (btn) {
      btn.disabled = true;
      btn.classList.add('btn-inactive');
    }
    if (spinner) spinner.style.display = 'inline-block';
    if (text) text.innerText = 'Hunting Jobs...';
    if (consoleBox && pipeline.message) {
      consoleBox.innerText = `Scanning in progress...\n${pipeline.message}`;
    }
    if (mainConsole && pipeline.message) {
      mainConsole.innerText = pipeline.message;
    }
  } else {
    const wasRunning = appState.pipelineRunning;
    appState.pipelineRunning = false;
    if (spinner) spinner.style.display = 'none';
    if (text) text.innerText = 'Run Job Hunt Now';
    if (pipeline.step === 'completed' && consoleBox && pipeline.message) {
      consoleBox.innerText = pipeline.message;
    } else if (pipeline.step === 'error' && consoleBox && pipeline.message) {
      consoleBox.innerText = `Error: ${pipeline.message}`;
    }
    updateJobSearchButtonState();

    if (wasRunning) {
      fetchAndRenderJobs(false);
      refreshDigest(true);
    }
  }
}

// Keep job search button inactive until candidate profile radar details are filled
function updateJobSearchButtonState() {
  const btn = document.getElementById('btn-run');
  const spinner = document.getElementById('run-spinner');
  const text = document.getElementById('run-text');
  const consoleBox = document.getElementById('run-console');
  if (!btn) return;

  if (appState.pipelineRunning) {
    btn.disabled = true;
    btn.classList.add('btn-inactive');
    return;
  }

  const profile = activeProfileData || {};
  const isFilled = isCandidateProfileFilled(profile);

  if (!isFilled) {
    btn.disabled = true;
    btn.classList.add('btn-inactive');
    btn.setAttribute('aria-disabled', 'true');
    
    // Detect specifically what is missing across the three sections
    const missing = [];
    if (!profile.resume_text || !profile.resume_text.trim()) missing.push("Resume Text (Step 1)");
    if (!profile.name || !profile.name.trim()) missing.push("Candidate Name (Step 2)");
    if (!profile.skills || !profile.skills.length) missing.push("Skills (Step 2)");
    if (!profile.target_keywords || !profile.target_keywords.length) missing.push("Target Job Titles (Step 2)");
    if (!profile.job_types || !profile.job_types.length) missing.push("Job Types (Step 2)");
    if (!profile.experience_level) missing.push("Experience Level (Step 2)");
    
    let hasLocation = false;
    if (profile.location_preference) {
      const locPrefType = typeof profile.location_preference === 'object' ? profile.location_preference.type : profile.location_preference;
      if (locPrefType && locPrefType !== '') hasLocation = true;
    }
    if (Array.isArray(profile.preferred_locations) && profile.preferred_locations.length > 0) {
      hasLocation = true;
    }
    if (!hasLocation) missing.push("Location Preference (Step 2)");
    
    if (profile.min_score_notification == null || String(profile.min_score_notification).trim() === '') missing.push("Min AI Match Score (Step 3)");
    if (!profile.mail_mode) missing.push("Briefing Mode (Step 3)");

    btn.title = `Please fill all three sections to scan. Missing: ${missing.join(', ')}`;
    if (spinner) spinner.style.display = 'none';
    if (text) text.innerText = 'Run Job Hunt Now';
    if (consoleBox) {
      consoleBox.innerText = `Candidate radar incomplete. Please configure: ${missing.join(', ')}.`;
    }
  } else {
    btn.disabled = false;
    btn.classList.remove('btn-inactive');
    btn.removeAttribute('aria-disabled');
    btn.title = 'Click to trigger autonomous job search across target ATS endpoints';
    if (spinner) spinner.style.display = 'none';
    if (text) text.innerText = 'Run Job Hunt Now';
    if (consoleBox && (consoleBox.innerText.includes('Candidate radar incomplete') || consoleBox.innerText.includes('System ready'))) {
      consoleBox.innerText = "System ready. Click 'Run Job Hunt Now' to start scanning target ATS endpoints.";
    }
  }
}

// Manual Sync Button Trigger
async function manualSync() {
  setSyncStatus('syncing', 'Syncing now...');
  await syncDashboard(true);
  showToast('Dashboard is fully synchronized!', 'success', 2000);
}

// Tab Switching with URL & LocalStorage Persistence
function switchTab(tab, fetchData = true) {
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

  if (fetchData && (!authConfig.auth_required || currentAuthSession)) {
    if (tab === 'digest') {
      refreshDigest();
    } else if (tab === 'tracker') {
      fetchAndRenderJobs(false);
    }
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
  const hasDraft = j.draft && (j.draft.cover_note || j.draft.fit_summary || j.draft.cold_outreach);
  const applyUrl = resolveJobUrl(j);
  const searchQuery = appState.search;

  return `
    <div class="job-item ${isNew ? 'job-item-new' : ''}" id="job-card-${escapeHtml(j.job_id)}">
      <div class="job-meta">
        <div class="job-header-row">
          <span class="job-title">${highlightText(j.title, searchQuery)}</span>
          <span class="ats-tag">${escapeHtml(j.ats || 'ats')}</span>
          ${isNew ? '<span class="badge-live-sync">New Discovery</span>' : ''}
        </div>
        <div class="job-sub">
          <span class="job-sub-company"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>${highlightText(j.company, searchQuery)}</span>
          <span class="job-sub-location"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M12 2a8 8 0 0 0-8 8c0 5.25 8 12 8 12s8-6.75 8-12a8 8 0 0 0-8-8z"></path><circle cx="12" cy="10" r="3"></circle></svg>${highlightText(j.location || 'Remote/Unspecified', searchQuery)}</span>
          <span class="job-sub-id">(${escapeHtml(j.job_id)})</span>
        </div>
        ${j.reason ? `<div class="job-reason">${escapeHtml(j.reason)}</div>` : ''}
      </div>
      <div class="job-actions">
        <div class="job-score-row">
          <span class="score-badge ${scoreClass}">${score}</span>
        </div>
        <div class="job-action-btn-row">
          ${isApplied
            ? `<button class="btn btn-secondary btn-sm btn-applied" id="btn-app-${escapeHtml(j.job_id)}" title="Click to unmark applied" onclick="toggleAppliedDirect('${escapeHtml(j.job_id)}', 'unmark')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><polyline points="20 6 9 17 4 12"></polyline></svg><span>Applied</span></button>`
            : `<button class="btn btn-secondary btn-sm" id="btn-app-${escapeHtml(j.job_id)}" onclick="toggleAppliedDirect('${escapeHtml(j.job_id)}', 'mark')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg><span>Mark Applied</span></button>`
          }
          <button class="btn btn-secondary btn-sm btn-danger" title="Delete job entry" onclick="deleteJobDirect('${escapeHtml(j.job_id)}')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg><span>Delete</span></button>
        </div>
        <div class="job-action-btn-row">
          ${hasDraft ? `<button class="btn btn-secondary btn-sm" onclick="openKitModal('${escapeHtml(j.job_id)}')"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg><span>Inspect Kit</span></button>` : ''}
          <a href="${escapeHtml(applyUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="text-decoration:none;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg><span>Open Link</span></a>
        </div>
      </div>
    </div>
  `;
}


// Fetch and Render Jobs with AbortController & Rich Empty States
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

  // If unauthenticated and auth is strictly required, render lock screen placeholder
  if (authConfig.auth_required && !currentAuthSession) {
    if (container) {
      container.innerHTML = `
        <div class="auth-required-placeholder">
          <div class="auth-lock-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
          </div>
          <h3>Authentication Required</h3>
          <p>Sign in with your Supabase account to access your personal AI job match radar and pipeline controls.</p>
          <button class="btn btn-primary" onclick="openAuthModal('signin')" style="margin-top: 14px;" type="button">
            <span>Sign In to Unlock Board</span>
          </button>
        </div>
      `;
    }
    return;
  }

  if (showLoadingIndicator && container && (!container.children.length || container.innerText.includes('Loading'))) {
    container.innerHTML = '<div class="job-list-loading"><span class="spinner" style="display:inline-block;"></span><span>Loading jobs...</span></div>';
  }

  try {
    const backendStatus = ['internship', 'remote'].includes(appState.filter) ? 'all' : appState.filter;
    const url = `/api/jobs?status=${encodeURIComponent(backendStatus)}&ats=${encodeURIComponent(appState.ats)}&sort=${encodeURIComponent(appState.sort)}&search=${encodeURIComponent(appState.search)}`;
    const res = await authFetch(url, { signal: currentSignal, cache: 'no-store' });
    const data = await parseJsonResponse(res);

    if (data.status !== 'success' || !data.jobs || data.jobs.length === 0) {
      if (container) {
        const isBrandNew = (!appState.stats?.tracked || appState.stats.tracked === 0) && !appState.search && appState.filter === 'all' && appState.ats === 'all';
        if (isBrandNew) {
          if (appState.pipelineRunning) {
            container.innerHTML = `
              <div class="empty-state">
                <div class="empty-state-icon" style="background:#eff6ff; color:#3b82f6;">
                  <span class="spinner" style="display:inline-block; width: 28px; height: 28px; border-width: 3.5px; margin-right: 0;"></span>
                </div>
                <div class="empty-state-title">Autonomous Job Scan in Progress...</div>
                <div class="empty-state-desc">
                  Scanning 40+ ATS boards and matching jobs to your candidate profile in real time. Please wait, this takes about 10-15 seconds!
                </div>
                <div class="console" id="main-run-console" style="margin-top: 15px; width: 100%; text-align: left; max-height: 100px; overflow-y: auto; white-space: pre-wrap;">Scanning target endpoints...</div>
              </div>
            `;
          } else {
            const profileFilled = isCandidateProfileFilled(activeProfileData);
            if (!profileFilled) {
              container.innerHTML = `
                <div class="empty-state">
                  <div class="empty-state-icon" style="background:#fff1f2; color:#e11d48;">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                  </div>
                  <div class="empty-state-title">Candidate Profile Required</div>
                  <div class="empty-state-desc">
                    Please fill out your candidate profile info (Name, Target Roles, and Skills) before running an autonomous job hunt scan across 40+ ATS boards.
                  </div>
                  <button class="btn btn-primary" onclick="openProfileModal()" style="margin-top:10px; gap:8px;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
                    <span>Fill Profile Info &amp; Setup Radar</span>
                  </button>
                </div>
              `;
            } else {
              container.innerHTML = `
                <div class="empty-state">
                  <div class="empty-state-icon" style="background:#eff6ff; color:#3b82f6;">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                  </div>
                  <div class="empty-state-title">Your Live Job Radar is Ready</div>
                  <div class="empty-state-desc">
                    No opportunities have been scanned for your profile yet. Click below to launch your first autonomous job hunt scan across 40+ ATS boards!
                  </div>
                  <button class="btn btn-primary" onclick="runPipeline()" style="margin-top:10px; gap:8px;">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                    <span>Run First Job Hunt Now</span>
                  </button>
                </div>
              `;
            }
          }
        } else {
          container.innerHTML = `
            <div class="empty-state">
              <div class="empty-state-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
              </div>
              <div class="empty-state-title">No Matching Opportunities Found</div>
              <div class="empty-state-desc">
                ${appState.search ? `No jobs matched the query "<strong>${escapeHtml(appState.search)}</strong>".` : `No jobs currently meet the selected filter criteria.`}
              </div>
              <button class="btn btn-secondary btn-sm" onclick="resetFiltersAndSearch()" style="margin-top:6px;">
                Reset Filters & Search
              </button>
            </div>
          `;
        }
      }
      appState.jobsMap = {};
      appState.jobsList = [];
      return;
    }

    let filteredJobs = data.jobs;
    if (appState.filter === 'internship') {
      const kw = ['intern', 'trainee', 'fresher', 'graduate'];
      filteredJobs = filteredJobs.filter(j => kw.some(k => (j.title || '').toLowerCase().includes(k) || (j.location || '').toLowerCase().includes(k)));
    } else if (appState.filter === 'remote') {
      const kw = ['remote', 'wfh', 'hybrid'];
      filteredJobs = filteredJobs.filter(j => kw.some(k => (j.title || '').toLowerCase().includes(k) || (j.location || '').toLowerCase().includes(k)));
    }

    appState.jobsList = filteredJobs;
    appState.jobsMap = {};
    filteredJobs.forEach(j => { appState.jobsMap[j.job_id] = j; });

    if (container) {
      container.innerHTML = renderJobsListHtml(filteredJobs);
    }

    const countInternship = document.getElementById('count-internship');
    const countRemote = document.getElementById('count-remote');
    if (countInternship && data.jobs) {
      const internKw = ['intern', 'trainee', 'fresher', 'graduate'];
      countInternship.innerText = data.jobs.filter(j => internKw.some(k => (j.title || '').toLowerCase().includes(k) || (j.location || '').toLowerCase().includes(k))).length;
    }
    if (countRemote && data.jobs) {
      const remoteKw = ['remote', 'wfh', 'hybrid'];
      countRemote.innerText = data.jobs.filter(j => remoteKw.some(k => (j.title || '').toLowerCase().includes(k) || (j.location || '').toLowerCase().includes(k))).length;
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

function resetFiltersAndSearch() {
  const searchInput = document.getElementById('tracker-search-input');
  const atsSelect = document.getElementById('tracker-ats-select');
  const clearBtn = document.getElementById('search-clear-btn');

  if (searchInput) searchInput.value = '';
  if (clearBtn) clearBtn.style.display = 'none';
  if (atsSelect) atsSelect.value = 'all';

  appState.search = '';
  appState.ats = 'all';
  setFilter('all');
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

    btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#059669" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg><span style="color:#059669; font-weight:800;">Copied!</span>`;
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
    html += `<div class="kit-section"><div class="kit-label">Why It Fits</div><p style="font-size:13px; line-height:1.6; color:var(--text-body);">${escapeHtml(d.fit_summary)}</p></div>`;
  }

  const outreachLabelSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Outreach</span>`;
  const coverLabelSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Note</span>`;

  if (d.cold_outreach) {
    html += `
      <div class="kit-section">
        <div class="kit-label">
          <span>Cold Outreach (&lt;80 words)</span>
          <button class="copy-btn" id="btn-copy-outreach" data-original="outreach" onclick="copySectionText('outreach-text', 'btn-copy-outreach')">${outreachLabelSvg}</button>
        </div>
        <div class="cover-box" id="outreach-text" style="background:var(--success-bg); color:var(--success-hover); border-color:var(--success-border); font-family:var(--font-mono, monospace);">${escapeHtml(d.cold_outreach)}</div>
      </div>`;
  }

  if (d.cover_note) {
    html += `
      <div class="kit-section">
        <div class="kit-label">
          <span>Tailored Cover Note</span>
          <button class="copy-btn" id="btn-copy-cover" data-original="cover" onclick="copySectionText('cover-text', 'btn-copy-cover')">${coverLabelSvg}</button>
        </div>
        <div class="cover-box" id="cover-text">${escapeHtml(d.cover_note)}</div>
      </div>`;
  }

  if (d.tailored_bullets && d.tailored_bullets.length) {
    html += `<div class="kit-section"><div class="kit-label">Tailored Resume Highlights</div><ul style="padding-left:18px; font-size:13px; line-height:1.6; color:var(--text-body);">${d.tailored_bullets.map(b => `<li style="margin-bottom:4px;">${escapeHtml(b)}</li>`).join('')}</ul></div>`;
  }
  if (d.gaps && d.gaps.length) {
    html += `<div class="kit-section"><div class="kit-label" style="color:var(--danger);">Honest Gaps / Considerations</div><ul style="padding-left:18px; font-size:13px; line-height:1.6; color:var(--danger);">${d.gaps.map(g => `<li style="margin-bottom:4px;">${escapeHtml(g)}</li>`).join('')}</ul></div>`;
  }
  if (d.questions_to_ask && d.questions_to_ask.length) {
    html += `<div class="kit-section"><div class="kit-label">Questions To Ask Interviewers</div><ul style="padding-left:18px; font-size:13px; line-height:1.6; color:var(--text-body);">${d.questions_to_ask.map(q => `<li style="margin-bottom:4px;">${escapeHtml(q)}</li>`).join('')}</ul></div>`;
  }

  const modalApplyUrl = resolveJobUrl(j);
  html += `<div style="margin-top:16px; display:flex; justify-content:flex-end; width:100%;"><a href="${escapeHtml(modalApplyUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="display:inline-flex; align-items:center; justify-content:center; text-decoration:none;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px; flex-shrink: 0;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg><span>Open Posting Page</span></a></div>`;

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



// --------------------------------------------------------------------------
// SMTP Test Briefing Email Dispatcher
// --------------------------------------------------------------------------
async function sendTestBriefingEmail() {
  const spinner = document.getElementById('test-email-spinner');
  const btn = document.getElementById('btn-test-email');
  if (spinner) spinner.style.display = 'inline-block';
  if (btn) btn.disabled = true;

  try {
    const res = await authFetch('/api/email/test', { method: 'POST' });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      showToast(data.message || 'Test briefing dispatched to your inbox!', 'success', 5000);
    } else {
      throw new Error(data.message || 'Test email failed');
    }
  } catch (err) {
    showToast('Test email failed: ' + err.message, 'error', 5000);
  } finally {
    if (spinner) spinner.style.display = 'none';
    if (btn) btn.disabled = false;
  }
}

// ==========================================================================
// CANDIDATE PROFILE & RESUME STUDIO CONTROLLERS
// ==========================================================================

let activeProfileData = null;
let selectedResumeFile = null;

function renderCandidateSummary(profile) {
  if (!profile) return;
  activeProfileData = { ...profile };
  Storage.set(localStorage, STORAGE_KEYS.CACHED_PROFILE, activeProfileData);

  const nameEl = document.getElementById('summary-candidate-name');
  const titleEl = document.getElementById('summary-candidate-title');
  const skillsContainer = document.getElementById('summary-skills-tags');
  const notifIndicator = document.getElementById('notif-badge-indicator');

  const authDisplayName = (
    currentAuthSession?.user?.user_metadata?.full_name ||
    currentAuthSession?.user?.user_metadata?.name ||
    ''
  ).trim();

  const savedName = (activeProfileData.name || '').trim();
  const savedTitle = (activeProfileData.title || '').trim();
  
  const rawSkills = Array.isArray(activeProfileData.skills) ? activeProfileData.skills : [];
  const skillsList = rawSkills.map(s => String(s).trim()).filter(Boolean);

  const isFilled = Boolean(savedName || savedTitle || skillsList.length > 0);
  const isComplete = Boolean(activeProfileData.onboarding_completed) || Boolean((savedName || savedTitle) && skillsList.length > 0);

  if (nameEl) {
    const displayName = savedName || authDisplayName || (currentAuthSession?.user?.email ? currentAuthSession.user.email.split('@')[0] : '');
    nameEl.innerText = displayName || 'Setup Profile';
    nameEl.classList.toggle('profile-incomplete-label', !savedName && !authDisplayName);
  }

  if (titleEl) {
    titleEl.innerText = savedTitle || (isFilled ? 'Candidate Profile' : 'Click to configure your profile');
    titleEl.classList.toggle('profile-incomplete-label', !savedTitle);
  }

  if (skillsContainer) {
    if (skillsList.length > 0) {
      skillsContainer.innerHTML = skillsList.slice(0, 8).map(s => `<span class="studio-skill-tag">${escapeHtml(s)}</span>`).join('');
    } else {
      skillsContainer.innerHTML = '<span class="studio-skill-tag studio-skill-placeholder">No skills added yet</span>';
    }
  }

  if (notifIndicator) {
    const isEnabled = Boolean(activeProfileData.email_notifications_enabled);
    notifIndicator.className = isEnabled ? 'notif-badge-on' : 'notif-badge-off';
    notifIndicator.innerText = isEnabled ? 'Email Alerts: Active' : 'Email Alerts: Off';
  }

  updateJobSearchButtonState();
}

// --------------------------------------------------------------------------
// Compulsory Onboarding Setup Wizard Engine
// --------------------------------------------------------------------------
let isOnboardingOpen = false;
let selectedOnboardingFile = null;
let parsedResumeData = null;

function isCandidateProfileFilled(profile) {
  if (!profile) return false;
  
  // Section 1: Resume Text Context
  const hasResume = (profile.resume_text || '').trim().length > 0;
  
  // Section 2: Roles, Name, Skills, Job Types, Exp Level, Location Pref
  const hasName = (profile.name || '').trim().length > 0;
  const hasSkills = Array.isArray(profile.skills) && profile.skills.length > 0;
  const hasTargets = Array.isArray(profile.target_keywords) && profile.target_keywords.length > 0;
  const hasJobTypes = Array.isArray(profile.job_types) && profile.job_types.length > 0;
  const hasExpLevel = (profile.experience_level || '').trim().length > 0;
  
  let hasLocation = false;
  if (profile.location_preference) {
    const locPrefType = typeof profile.location_preference === 'object' ? profile.location_preference.type : profile.location_preference;
    if (locPrefType && locPrefType !== '') hasLocation = true;
  }
  if (Array.isArray(profile.preferred_locations) && profile.preferred_locations.length > 0) {
    hasLocation = true;
  }

  // Section 3: AI score and Briefing mode
  const hasScore = profile.min_score_notification != null && String(profile.min_score_notification).trim() !== '';
  const hasMailMode = (profile.mail_mode || '').trim().length > 0;

  return Boolean(hasResume && hasName && hasSkills && hasTargets && hasJobTypes && hasExpLevel && hasLocation && hasScore && hasMailMode);
}

function isProfileIncomplete(profile) {
  return !isCandidateProfileFilled(profile);
}

function checkAndPromptOnboarding(profile) {
  // Never auto-force the popup on login - user decides when to fill up profile
  return;
}

function openOnboardingModal() {
  const modalEl = document.getElementById('onboarding-modal');
  if (!modalEl) return;
  isOnboardingOpen = true;
  modalEl.classList.add('active');
  switchOnboardingStep(1);

  // Resolve auth identity defaults
  const authName = (
    currentAuthSession?.user?.user_metadata?.full_name ||
    currentAuthSession?.user?.user_metadata?.name ||
    ''
  ).trim();

  // Pre-populate from real saved data only.
  const nameInput    = document.getElementById('onboard-prof-name');
  const titleInput   = document.getElementById('onboard-prof-title');
  const yearsInput   = document.getElementById('onboard-prof-years');
  const eduInput     = document.getElementById('onboard-prof-education');
  const skillsInput  = document.getElementById('onboard-prof-skills');
  const targetsInput = document.getElementById('onboard-prof-targets');
  const excludesInput= document.getElementById('onboard-prof-excludes');
  const notifToggle  = document.getElementById('onboard-toggle-email-alerts');

  const p = activeProfileData || {};
  const savedName    = (p.name || '').trim();
  const savedTitle   = (p.title || '').trim();
  const savedYears   = p.experience_years ? String(p.experience_years) : '';
  const savedEdu     = (p.education || '').trim();
  const savedSkills  = Array.isArray(p.skills) && p.skills.length ? p.skills.join(', ') : '';
  const savedTargets = Array.isArray(p.target_keywords) && p.target_keywords.length ? p.target_keywords.join(', ') : '';
  const savedExcludes= Array.isArray(p.exclude_keywords) && p.exclude_keywords.length ? p.exclude_keywords.join(', ') : '';

  if (nameInput)    nameInput.value    = savedName;
  if (titleInput)   titleInput.value   = savedTitle;
  if (yearsInput)   yearsInput.value   = savedYears;
  if (eduInput)     eduInput.value     = savedEdu;
  if (skillsInput)  skillsInput.value  = savedSkills;
  if (targetsInput) targetsInput.value = savedTargets;
  if (excludesInput)excludesInput.value= savedExcludes;
  if (notifToggle)  notifToggle.checked = Boolean(p.email_notifications_enabled);

  populateSection2FromProfile(p);
}

function closeOnboardingModal(force = false) {
  const modalEl = document.getElementById('onboarding-modal');
  if (modalEl) modalEl.classList.remove('active');
  isOnboardingOpen = false;
  selectedOnboardingFile = null;
  Storage.set(sessionStorage, 'onboarding_dismissed', true);
}

function switchOnboardingStep(step) {
  const step1 = document.getElementById('onboarding-step-1');
  const step2 = document.getElementById('onboarding-step-2');
  const ind1 = document.getElementById('onboarding-step-indicator-1');
  const ind2 = document.getElementById('onboarding-step-indicator-2');
  const conn1 = document.getElementById('step-connector-1');

  const c1 = document.getElementById('step-circle-1');
  const c2 = document.getElementById('step-circle-2');

  if (step === 1) {
    if (step1) step1.style.display = 'block';
    if (step2) step2.style.display = 'none';
    if (ind1) { ind1.className = 'step-node active'; }
    if (ind2) { ind2.className = 'step-node'; }
    if (conn1) { conn1.className = 'step-connector'; }
    if (c1) c1.innerText = '1';
    if (c2) c2.innerText = '2';
  } else if (step === 2) {
    if (step1) step1.style.display = 'none';
    if (step2) step2.style.display = 'block';
    if (ind1) { ind1.className = 'step-node completed'; }
    if (ind2) { ind2.className = 'step-node active'; }
    if (conn1) { conn1.className = 'step-connector active'; }
    if (c1) c1.innerText = '✓';
    if (c2) c2.innerText = '2';
  }
}

function handleOnboardingFileSelected(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  selectedOnboardingFile = file;
  const dropText = document.getElementById('onboarding-dropzone-text');
  if (dropText) {
    dropText.innerText = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  }
}

function initOnboardingDropzone() {
  const dropzone = document.getElementById('onboarding-dropzone');
  if (!dropzone) return;

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('dragover');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('dragover');
    }, false);
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length > 0) {
      selectedOnboardingFile = files[0];
      const dropText = document.getElementById('onboarding-dropzone-text');
      if (dropText) {
        dropText.innerText = `Selected: ${files[0].name} (${(files[0].size / 1024).toFixed(1)} KB)`;
      }
    }
  }, false);
}

async function submitOnboardingResumeParse() {
  const btn = document.getElementById('btn-onboarding-parse');
  const spinner = document.getElementById('onboarding-spinner');
  const btnText = document.getElementById('onboarding-parse-btn-text');
  const alertEl = document.getElementById('onboarding-status-alert');
  const pasteText = document.getElementById('onboarding-paste-text')?.value || '';

  if (!selectedOnboardingFile && !pasteText.trim()) {
    showToast('Please select a resume file or paste resume text.', 'info');
    return;
  }

  if (btn) btn.disabled = true;
  if (spinner) spinner.style.display = 'inline-block';
  if (btnText) btnText.innerText = 'Extracting candidate profile with AI...';
  if (alertEl) alertEl.style.display = 'none';

  try {
    let res;
    if (selectedOnboardingFile) {
      const formData = new FormData();
      formData.append('file', selectedOnboardingFile);
      res = await authFetch('/api/resume/upload', {
        method: 'POST',
        body: formData
      });
    } else {
      res = await authFetch('/api/resume/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume_text: pasteText, filename: 'pasted_resume.txt' })
      });
    }

    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      showToast('Resume parsed successfully!', 'success');
      if (alertEl) {
        alertEl.className = 'studio-alert success';
        alertEl.innerText = `✅ ${data.message}`;
        alertEl.style.display = 'block';
      }

      const p = data.profile || {};
      const extractedText = data.resume_text || p.resume_text || '';
      parsedResumeData = p;
      activeProfileData = { ...activeProfileData, resume_text: extractedText, resume_filename: selectedOnboardingFile?.name || '' };

      // Populate editable text area with extracted text context so user can alter it
      const pasteInput = document.getElementById('onboarding-paste-text');
      if (pasteInput && extractedText) {
        pasteInput.value = extractedText;
      }

      // Render live preview card
      const previewCard = document.getElementById('onboarding-preview-card');
      const prevName = document.getElementById('preview-name');
      const prevTitle = document.getElementById('preview-title');
      const prevYears = document.getElementById('preview-years');
      const prevSkills = document.getElementById('preview-skills-container');

      if (prevName) prevName.innerText = p.name || 'Candidate';
      if (prevTitle) prevTitle.innerText = p.title || 'Software Engineer';
      if (prevYears) prevYears.innerText = `${p.experience_years || 2} Years`;
      if (prevSkills) {
        const skillsList = p.skills || [];
        prevSkills.innerHTML = skillsList.slice(0, 10).map(s => `<span class="preview-tag">${escapeHtml(s)}</span>`).join('');
      }
      if (previewCard) previewCard.style.display = 'block';

      // Advance to Step 2 so user can review or click Auto-Fill
      setTimeout(() => {
        switchOnboardingStep(2);
      }, 700);
    } else {
      showToast('Resume parsing error: ' + data.message, 'error');
      if (alertEl) {
        alertEl.className = 'studio-alert error';
        alertEl.innerText = `Error: ${data.message}`;
        alertEl.style.display = 'block';
      }
    }
  } catch (err) {
    showToast('Notice: ' + err.message, 'error');
    if (alertEl) {
      alertEl.className = 'studio-alert error';
      alertEl.innerText = err.message;
      alertEl.style.display = 'block';
    }
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
    if (btnText) btnText.innerText = 'Extract Candidate Profile with AI';
  }
}

const ROLE_PRESETS = {
  fullstack: {
    title: 'Full Stack Engineer',
    skills: ['TypeScript', 'React', 'Node.js', 'Python', 'PostgreSQL', 'REST APIs', 'Docker', 'Git'],
    targets: ['Full Stack Engineer', 'Full Stack Developer', 'Software Engineer', 'Senior Full Stack Engineer'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  },
  backend: {
    title: 'Backend Engineer',
    skills: ['Python', 'Go', 'PostgreSQL', 'FastAPI', 'Redis', 'Docker', 'Microservices', 'Distributed Systems'],
    targets: ['Backend Engineer', 'Backend Developer', 'Systems Engineer', 'Software Engineer II'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  },
  frontend: {
    title: 'Frontend Engineer',
    skills: ['JavaScript', 'TypeScript', 'React', 'Next.js', 'CSS3', 'HTML5', 'Tailwind', 'REST APIs'],
    targets: ['Frontend Engineer', 'Frontend Developer', 'UI Engineer', 'Web Developer'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  },
  ai_ml: {
    title: 'AI / Machine Learning Engineer',
    skills: ['Python', 'PyTorch', 'LLMs', 'OpenAI', 'Gemini', 'LangChain', 'FastAPI', 'Vector DBs'],
    targets: ['AI Engineer', 'ML Engineer', 'Machine Learning Engineer', 'AI Software Engineer'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  },
  devops: {
    title: 'DevOps / Cloud / SRE',
    skills: ['Kubernetes', 'Docker', 'AWS', 'GCP', 'Terraform', 'CI/CD', 'Linux', 'Prometheus'],
    targets: ['DevOps Engineer', 'Site Reliability Engineer', 'Cloud Engineer', 'Platform Engineer'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  },
  data_engineer: {
    title: 'Data Engineer',
    skills: ['Python', 'SQL', 'PostgreSQL', 'Apache Spark', 'Airflow', 'Snowflake', 'BigQuery', 'Kafka'],
    targets: ['Data Engineer', 'Data Platform Engineer', 'Analytics Engineer', 'ETL Engineer'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  },
  product_manager: {
    title: 'Product Manager',
    skills: ['System Design', 'Agile', 'Jira', 'Roadmapping', 'User Research', 'Product Strategy'],
    targets: ['Product Manager', 'Associate PM', 'Technical PM', 'Growth PM'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  },
  mobile_dev: {
    title: 'Mobile Developer',
    skills: ['Swift', 'Kotlin', 'Flutter', 'React Native', 'iOS', 'Android', 'Mobile App Development'],
    targets: ['Android Developer', 'iOS Developer', 'Flutter Developer', 'React Native Developer', 'Mobile Engineer'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  },
  qa_engineer: {
    title: 'QA / SDET',
    skills: ['Selenium', 'Cypress', 'Playwright', 'Test Automation', 'Manual Testing', 'QA'],
    targets: ['QA Engineer', 'SDET', 'Test Engineer', 'Automation Engineer', 'Quality Engineer'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  },
  security: {
    title: 'Security Engineer',
    skills: ['Cybersecurity', 'Penetration Testing', 'AppSec', 'Network Security', 'Cryptography'],
    targets: ['Security Engineer', 'AppSec Engineer', 'Penetration Tester', 'Cybersecurity Analyst', 'Cloud Security'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  },
  blockchain: {
    title: 'Blockchain / Web3',
    skills: ['Solidity', 'Smart Contracts', 'Web3.js', 'Ethereum', 'Rust', 'Cryptography'],
    targets: ['Blockchain Developer', 'Smart Contract Engineer', 'Web3 Developer', 'Solidity Developer'],
    excludes: [],
    job_types: ['fulltime', 'internship']
  }
};

function applyRolePreset(presetKey) {
  const preset = ROLE_PRESETS[presetKey];
  if (!preset) return;

  document.querySelectorAll('.btn-preset-chip').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('onclick')?.includes(`'${presetKey}'`));
  });

  const targetsInput = document.getElementById('onboard-prof-targets');
  if (targetsInput) targetsInput.value = preset.targets.join(', ');

  const excludesInput = document.getElementById('onboard-prof-excludes');
  if (excludesInput) excludesInput.value = preset.excludes.join(', ');

  const profTargetsInput = document.getElementById('prof-targets');
  if (profTargetsInput) profTargetsInput.value = preset.targets.join(', ');
  const profExcludesInput = document.getElementById('prof-excludes');
  if (profExcludesInput) profExcludesInput.value = preset.excludes.join(', ');
  
  // Set job types
  ['onboard-job-types', 'prof-job-types'].forEach(containerId => {
    const container = document.getElementById(containerId);
    if (container) {
      container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        const isTarget = preset.job_types.includes(cb.value);
        cb.checked = isTarget;
        const label = cb.closest('.chip-toggle');
        if (label) label.classList.toggle('active', isTarget);
      });
    }
  });

  if (!activeProfileData) activeProfileData = {};
  activeProfileData.title = preset.title;
  activeProfileData.skills = preset.skills;
  activeProfileData.target_keywords = preset.targets;
  activeProfileData.exclude_keywords = preset.excludes;
  activeProfileData.job_types = preset.job_types;

  showToast(`Applied "${preset.title}" preset! Targets & skills updated.`, 'success', 2500);
}

function selectNotificationMode(isDaily) {
  const ondemandCard = document.getElementById('mode-card-ondemand');
  const dailyCard = document.getElementById('mode-card-daily');
  const ondemandRadio = document.getElementById('mode-radio-ondemand');
  const dailyRadio = document.getElementById('mode-radio-daily');
  const toggle = document.getElementById('onboard-toggle-email-alerts');

  if (ondemandCard) ondemandCard.classList.toggle('active', !isDaily);
  if (dailyCard) dailyCard.classList.toggle('active', isDaily);
  if (ondemandRadio) ondemandRadio.innerText = isDaily ? '○' : '●';
  if (dailyRadio) dailyRadio.innerText = isDaily ? '●' : '○';
  if (toggle) toggle.checked = isDaily;
}

async function saveOnboardingProfile(launchScan = false) {
  const targetsInput = document.getElementById('onboard-prof-targets');
  const targets = targetsInput
    ? targetsInput.value.split(',').map(s => s.trim()).filter(Boolean)
    : (Array.isArray(activeProfileData?.target_keywords) ? activeProfileData.target_keywords : []);

  const excludesInput = document.getElementById('onboard-prof-excludes');
  const excludes = excludesInput
    ? excludesInput.value.split(',').map(s => s.trim()).filter(Boolean)
    : (Array.isArray(activeProfileData?.exclude_keywords) ? activeProfileData.exclude_keywords : []);

  const notifToggle = document.getElementById('onboard-toggle-email-alerts');
  const notifEnabled = notifToggle ? Boolean(notifToggle.checked) : false;

  const authName = (
    currentAuthSession?.user?.user_metadata?.full_name ||
    currentAuthSession?.user?.user_metadata?.name ||
    ''
  ).trim();

  const nameInput = document.getElementById('onboard-prof-name');
  const name = nameInput ? nameInput.value.trim() : (activeProfileData?.name || authName || '');

  const titleInput = document.getElementById('onboard-prof-title');
  const title = titleInput ? titleInput.value.trim() : (activeProfileData?.title || activeProfileData?.current_title || '');

  const yearsInput = document.getElementById('onboard-prof-years');
  const years = yearsInput ? (parseFloat(yearsInput.value) || 0) : (activeProfileData?.experience_years || 0);

  const eduInput = document.getElementById('onboard-prof-education');
  const education = eduInput ? eduInput.value.trim() : (activeProfileData?.education || '');

  const skillsInput = document.getElementById('onboard-prof-skills');
  const skills = skillsInput
    ? skillsInput.value.split(',').map(s => s.trim()).filter(Boolean)
    : (Array.isArray(activeProfileData?.skills) ? activeProfileData.skills : []);

  const resumeTextInput = document.getElementById('onboarding-paste-text');
  const resumeText = resumeTextInput ? resumeTextInput.value.trim() : (activeProfileData?.resume_text || '');

  const jobTypes = getSelectedJobTypes('onboard-job-types');
  const expLevel = getSelectedExpLevel('onboard-exp');
  const preferredLocations = getLocationPreference('onboard-location-pref', 'onboard-specific-cities');

  const payload = {
    name,
    title,
    experience_years: years,
    education,
    skills,
    target_keywords: targets,
    exclude_keywords: excludes,
    resume_text: resumeText,
    resume_filename: activeProfileData?.resume_filename || '',
    email_notifications_enabled: notifEnabled,
    notification_email: currentAuthSession?.user?.email || activeProfileData?.notification_email || '',
    min_score_notification: activeProfileData?.min_score_notification || null,
    onboarding_completed: Boolean(title || (skills.length > 0) || (targets.length > 0)),
    job_types: jobTypes,
    experience_level: expLevel,
    preferred_locations: preferredLocations
  };

  appState.isSavingProfile = true;

  try {
    const res = await authFetch('/api/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await parseJsonResponse(res);

    if (data.status === 'success') {
      const savedProfile = data.profile || payload;
      activeProfileData = { ...savedProfile };
      Storage.set(localStorage, STORAGE_KEYS.CACHED_PROFILE, activeProfileData);
      renderCandidateSummary(savedProfile);
      updateJobSearchButtonState();
      closeOnboardingModal(true);
      Storage.set(sessionStorage, 'onboarding_dismissed', true);
      showToast('Profile setup complete! Welcome to Job Hunter.', 'success', 3500);
      appState.isSavingProfile = false;
      await syncDashboard(true);

      if (launchScan) {
        // Automatically launch first autonomous radar scan
        setTimeout(() => {
          triggerJobSearch();
        }, 400);
      }
    } else {
      showToast('Failed to save profile: ' + data.message, 'error');
    }
  } catch (err) {
    showToast('Notice: ' + err.message, 'error');
  } finally {
    appState.isSavingProfile = false;
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
  }
}

// --------------------------------------------------------------------------
// Settings Modal & Preferences Manager
// --------------------------------------------------------------------------
async function openProfileModal(tab = 'resume') {
  const modalEl = document.getElementById('profile-modal');
  if (!modalEl) return;
  modalEl.classList.add('active');
  
  // Always start with Part 1 (Step 1: Resume & Text Context)
  profileWizardGoTo(1);

  // Auth identity — only these two are auto-filled as defaults
  const authName = (
    currentAuthSession?.user?.user_metadata?.full_name ||
    currentAuthSession?.user?.user_metadata?.name ||
    ''
  ).trim();
  const authEmail = currentAuthSession?.user?.email || '';

  try {
    const res = await authFetch('/api/profile');
    const data = await parseJsonResponse(res);
    if (data.status === 'success' && data.profile) {
      const p = data.profile;
      activeProfileData = p;
      renderCandidateSummary(p);

      const nameInput    = document.getElementById('prof-name');
      const titleInput   = document.getElementById('prof-title');
      const yearsInput   = document.getElementById('prof-years');
      const eduInput     = document.getElementById('prof-education');
      const skillsInput  = document.getElementById('prof-skills');
      const targetsInput = document.getElementById('prof-targets');
      const excludesInput= document.getElementById('prof-excludes');
      const resumeTextInput = document.getElementById('prof-resume-text');
      const notifToggle  = document.getElementById('toggle-email-alerts');
      const notifEmail   = document.getElementById('notif-target-email');
      const notifScore   = document.getElementById('notif-min-score');

      if (nameInput) nameInput.value = (p.name || '').trim();
      if (resumeTextInput) resumeTextInput.value = p.resume_text || '';
      if (titleInput)    titleInput.value   = (p.title || p.current_title || '').trim();
      if (yearsInput)    yearsInput.value   = (p.experience_years || p.years_experience) ? String(p.experience_years || p.years_experience) : '';
      if (eduInput)      eduInput.value     = (p.education || '').trim();
      if (skillsInput)   skillsInput.value  = Array.isArray(p.skills) ? p.skills.join(', ') : (Array.isArray(p.core_skills) ? p.core_skills.join(', ') : '');
      if (targetsInput)  targetsInput.value = Array.isArray(p.target_keywords) && p.target_keywords.length ? p.target_keywords.join(', ') : (Array.isArray(p.target_titles) && p.target_titles.length ? p.target_titles.join(', ') : '');
      if (excludesInput) excludesInput.value= Array.isArray(p.exclude_keywords) && p.exclude_keywords.length ? p.exclude_keywords.join(', ') : '';

      // ── Step 3: Selectable Mail Mode (Default is unselected)
      if (p.email_notifications_enabled === true) {
        selectMailMode('daily');
      } else if (p.mail_mode === 'onetime') {
        selectMailMode('onetime');
      } else {
        selectMailMode('none');
      }

      if (notifEmail)  notifEmail.value    = p.notification_email || authEmail;
      if (notifScore)  notifScore.value    = (p.min_score_notification != null && p.min_score_notification !== '') ? String(p.min_score_notification) : '';

      // ── Step 1 Next button: always accessible
      const nextBtn = document.getElementById('profile-next-1');
      if (nextBtn) nextBtn.disabled = false;

      if (p.resume_filename || p.resume_text) {
        const dropText = document.getElementById('dropzone-text');
        if (dropText) {
          dropText.innerText = p.resume_filename
            ? `Current resume: ${p.resume_filename} — drop a new file to replace`
            : 'Resume context saved — drop a new file anytime to update';
        }
      }

      // ── Populate Section 2 fields from saved profile
      populateSection2FromProfile(p);
    } else {
      const nameInput  = document.getElementById('prof-name');
      const notifEmail = document.getElementById('notif-target-email');
      const targetsInput = document.getElementById('prof-targets');
      const excludesInput= document.getElementById('prof-excludes');
      if (nameInput)  nameInput.value  = '';
      if (notifEmail && authEmail) notifEmail.value = authEmail;
      if (targetsInput)  targetsInput.value  = '';
      if (excludesInput) excludesInput.value = '';
      selectMailMode('none');
    }
  } catch (err) {
    console.warn('Profile fetch notice:', err);
    const nameInput  = document.getElementById('prof-name');
    const notifEmail = document.getElementById('notif-target-email');
    const targetsInput = document.getElementById('prof-targets');
    const excludesInput= document.getElementById('prof-excludes');
    if (nameInput)  nameInput.value  = '';
    if (notifEmail && authEmail) notifEmail.value = authEmail;
    if (targetsInput)  targetsInput.value  = '';
    if (excludesInput) excludesInput.value = '';
    selectMailMode('none');
  }
}

function selectMailMode(mode) {
  const isDaily = mode === 'daily';
  const isOnetime = mode === 'onetime';
  const dailyRadio = document.getElementById('radio-mode-daily');
  const onetimeRadio = document.getElementById('radio-mode-onetime');
  const dailyCard = document.getElementById('settings-mode-card-daily') || document.getElementById('mode-card-daily');
  const onetimeCard = document.getElementById('mode-card-onetime');

  if (dailyRadio) dailyRadio.checked = isDaily;
  if (onetimeRadio) onetimeRadio.checked = isOnetime;

  if (dailyCard) {
    dailyCard.style.borderColor = isDaily ? '#0F172A' : '#E2E8F0';
    dailyCard.style.background = isDaily ? '#F8FAFC' : '#FFFFFF';
  }
  if (onetimeCard) {
    onetimeCard.style.borderColor = isOnetime ? '#0F172A' : '#E2E8F0';
    onetimeCard.style.background = isOnetime ? '#F8FAFC' : '#FFFFFF';
  }
}

// Comprehensive Section 2 Auto-Fill Helper (covers Name, Target Roles, Excluded Keywords, Experience, Job Types, Locations)
function populateSection2FromProfile(p, isAutoFill = false) {
  if (!p) return;

  // 1. Candidate Name
  let nameVal = (p.name || '').trim();
  if (!nameVal && isAutoFill && p.resume_text) {
    const lines = p.resume_text.split('\n').map(l => l.trim()).filter(Boolean);
    if (lines.length > 0 && lines[0].length < 40) nameVal = lines[0];
  }
  const nameInput = document.getElementById('prof-name');
  const onbNameInput = document.getElementById('onboard-prof-name');
  if (nameInput) nameInput.value = nameVal;
  if (onbNameInput) onbNameInput.value = nameVal;

  // 2. Target Job Titles (Included)
  let targets = [];
  if (Array.isArray(p.target_keywords) && p.target_keywords.length) {
    targets = p.target_keywords;
  } else if (Array.isArray(p.target_titles) && p.target_titles.length) {
    targets = p.target_titles;
  } else if (p.title || p.current_title) {
    targets = [p.title || p.current_title];
  } else if (isAutoFill) {
    const rawSkills = Array.isArray(p.skills) ? p.skills : (Array.isArray(p.core_skills) ? p.core_skills : []);
    const skillsLower = rawSkills.map(s => String(s).toLowerCase());
    if (skillsLower.some(s => s.includes('react') || s.includes('vue') || s.includes('front') || s.includes('javascript') || s.includes('next'))) {
      targets.push('Full Stack Developer', 'Frontend Engineer', 'Software Engineer');
    }
    if (skillsLower.some(s => s.includes('python') || s.includes('node') || s.includes('flask') || s.includes('backend') || s.includes('django') || s.includes('sql'))) {
      targets.push('Backend Engineer', 'Software Engineer');
    }
    if (targets.length === 0) {
      targets = ['Software Engineer', 'Full Stack Developer', 'Backend Engineer'];
    }
  }
  const targetsStr = Array.from(new Set(targets)).join(', ');
  const targetsInput = document.getElementById('prof-targets');
  const onbTargetsInput = document.getElementById('onboard-prof-targets');
  if (targetsInput) targetsInput.value = targetsStr;
  if (onbTargetsInput) onbTargetsInput.value = targetsStr;

  // 3. Excluded Title Keywords
  let excludes = [];
  if (Array.isArray(p.exclude_keywords) && p.exclude_keywords.length) {
    excludes = p.exclude_keywords;
  } else if (isAutoFill) {
    excludes = ['Manager', 'Director', 'Sales', 'Recruiter', 'VP'];
  }
  const excludesStr = excludes.join(', ');
  const excludesInput = document.getElementById('prof-excludes');
  const onbExcludesInput = document.getElementById('onboard-prof-excludes');
  if (excludesInput) excludesInput.value = excludesStr;
  if (onbExcludesInput) onbExcludesInput.value = excludesStr;

  // 4. Experience Level
  let expKey = '';
  const years = p.experience_years != null ? Number(p.experience_years) : (p.years_experience != null ? Number(p.years_experience) : null);
  const seniority = (p.seniority || '').toLowerCase();
  if (p.experience_level) {
    expKey = p.experience_level;
  } else if (years != null && years > 0) {
    if (years <= 1) expKey = '0-1';
    else if (years <= 3) expKey = '1-3';
    else if (years <= 5) expKey = '3-5';
    else expKey = '5+';
  } else if (seniority.includes('senior') || seniority.includes('lead') || seniority.includes('staff')) {
    expKey = '5+';
  } else if (seniority.includes('intern') || seniority.includes('fresher') || seniority.includes('new-grad') || isAutoFill) {
    expKey = (years === 0 || seniority.includes('intern') || seniority.includes('fresher')) ? 'fresher' : '0-1';
  }

  ['prof-exp', 'onboard-exp'].forEach(nameAttr => {
    document.querySelectorAll(`input[name="${nameAttr}"]`).forEach(radio => {
      const isMatch = expKey && radio.value === expKey;
      radio.checked = isMatch;
      const chip = radio.closest('.chip-radio');
      if (chip) chip.classList.toggle('active', isMatch);
    });
  });

  // 5. Job Type Preferences
  let jobTypes = Array.isArray(p.job_types) && p.job_types.length ? p.job_types : [];
  if (isAutoFill && jobTypes.length === 0) {
    if (expKey === 'fresher' || seniority.includes('intern')) {
      jobTypes = ['fulltime', 'internship', 'remote'];
    } else {
      jobTypes = ['fulltime', 'remote', 'hybrid'];
    }
  }

  ['prof-job-types', 'onboard-job-types'].forEach(containerId => {
    const container = document.getElementById(containerId);
    if (container) {
      container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        const isMatch = jobTypes.includes(cb.value);
        cb.checked = isMatch;
        const toggle = cb.closest('.chip-toggle');
        if (toggle) toggle.classList.toggle('active', isMatch);
      });
    }
  });

  // 6. Location Preference & Specific Cities
  let locPref = '';
  let citiesList = [];
  if (p.location_preference) {
    locPref = typeof p.location_preference === 'object' ? (p.location_preference.type || '') : p.location_preference;
    citiesList = Array.isArray(p.location_preference.locations) ? p.location_preference.locations : [];
  } else if (Array.isArray(p.preferred_locations) && p.preferred_locations.length) {
    locPref = 'specific_cities';
    citiesList = p.preferred_locations;
  } else if (isAutoFill) {
    locPref = 'all_india';
  }

  ['prof-location-pref', 'onboard-location-pref'].forEach(radioName => {
    document.querySelectorAll(`input[name="${radioName}"]`).forEach(r => {
      const isMatch = locPref && r.value === locPref;
      r.checked = isMatch;
      const opt = r.closest('.radio-option');
      if (opt) opt.classList.toggle('active', isMatch);
    });
  });

  const isSpecific = locPref === 'specific_cities';
  const profSpecificInput = document.getElementById('prof-specific-cities-input');
  if (profSpecificInput) profSpecificInput.style.display = isSpecific ? 'block' : 'none';
  const onbSpecificInput = document.getElementById('specific-cities-input');
  if (onbSpecificInput) onbSpecificInput.style.display = isSpecific ? 'block' : 'none';

  const citiesStr = citiesList.length ? citiesList.join(', ') : '';
  const profCities = document.getElementById('prof-specific-cities');
  if (profCities) profCities.value = citiesStr;
  const onbCities = document.getElementById('onboard-specific-cities');
  if (onbCities) onbCities.value = citiesStr;
}

async function autoFillRolesFromResume() {
  const profResumeText = document.getElementById('prof-resume-text')?.value?.trim() || '';
  const onbResumeText = document.getElementById('onboarding-paste-text')?.value?.trim() || '';
  const resumeText = profResumeText || onbResumeText || activeProfileData?.resume_text || '';

  if (!resumeText && !parsedResumeData) {
    showToast('Please upload or enter your resume text in Step 1 first.', 'info');
    if (document.getElementById('profile-modal')?.classList.contains('active')) {
      profileWizardGoTo(1);
    } else {
      switchOnboardingStep(1);
    }
    return;
  }

  // If parsedResumeData already exists in memory, populate all Step 2 fields instantly
  if (parsedResumeData && (parsedResumeData.target_keywords?.length || parsedResumeData.skills?.length || parsedResumeData.name || parsedResumeData.title)) {
    activeProfileData = { ...activeProfileData, ...parsedResumeData, resume_text: resumeText };
    populateSection2FromProfile(parsedResumeData, true);
    renderCandidateSummary(activeProfileData);
    showToast('All Step 2 criteria auto-filled from your resume!', 'success', 3500);
    return;
  }

  const btn = document.getElementById('btn-autofill-roles') || document.getElementById('btn-onboard-autofill');
  const spinner = document.getElementById('autofill-roles-spinner');
  const btnText = document.getElementById('autofill-roles-btn-text');
  if (btn) btn.disabled = true;
  if (spinner) spinner.style.display = 'inline-block';
  if (btnText) btnText.innerText = 'Extracting criteria from resume...';

  try {
    const res = await authFetch('/api/resume/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_text: resumeText, filename: 'text_context.txt' })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      const p = data.profile || {};
      parsedResumeData = p;
      activeProfileData = { ...activeProfileData, ...p, resume_text: resumeText };
      renderCandidateSummary(activeProfileData);

      populateSection2FromProfile(p, true);
      showToast('All Step 2 criteria auto-filled from your resume!', 'success', 3500);
    } else {
      showToast('Auto-fill notice: ' + (data.message || 'could not parse criteria'), 'info');
    }
  } catch (err) {
    showToast('Auto-fill notice: ' + err.message, 'info');
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
    if (btnText) btnText.innerText = 'Auto-Fill from Resume Context';
  }
}


function closeProfileModal() {
  const modalEl = document.getElementById('profile-modal');
  if (modalEl) modalEl.classList.remove('active');
  selectedResumeFile = null;
  // Reset wizard state to Part 1
  profileWizardGoTo(1);
  const nextBtn = document.getElementById('profile-next-1');
  if (nextBtn) nextBtn.disabled = false;
  const previewCard = document.getElementById('studio-resume-preview-card');
  if (previewCard) previewCard.style.display = 'none';
  const alertEl = document.getElementById('resume-status-alert');
  if (alertEl) alertEl.style.display = 'none';
  const dropText = document.getElementById('dropzone-text');
  if (dropText) dropText.innerText = 'Click or drag & drop a new resume PDF / TXT file';
  const fileInput = document.getElementById('resume-file-input');
  if (fileInput) fileInput.value = '';
}

function flushUserProfileData() {
  const preservedEmail = (
    currentAuthSession?.user?.email ||
    activeProfileData?.notification_email ||
    activeProfileData?.email ||
    document.getElementById('notif-target-email')?.value ||
    ''
  ).trim();

  // 1. Clear all text, textarea, and numeric inputs across Profile & Onboarding modals
  const fieldIds = [
    'prof-name', 'prof-title', 'prof-years', 'prof-education',
    'prof-skills', 'prof-targets', 'prof-excludes', 'prof-resume-text',
    'prof-specific-cities', 'notif-min-score',
    'onboard-prof-name', 'onboard-prof-title', 'onboard-prof-years',
    'onboard-prof-education', 'onboard-prof-skills', 'onboard-prof-targets',
    'onboard-prof-excludes', 'onboard-specific-cities', 'onboarding-paste-text',
    'resume-paste-text'
  ];
  fieldIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });

  // Preserve email input intact
  const emailInput = document.getElementById('notif-target-email');
  if (emailInput && preservedEmail) {
    emailInput.value = preservedEmail;
  }

  // 2. Clear Job Type Checkbox Chips
  ['prof-job-types', 'onboard-job-types'].forEach(containerId => {
    const container = document.getElementById(containerId);
    if (container) {
      container.querySelectorAll('input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
      });
      container.querySelectorAll('.chip-toggle').forEach(chip => {
        chip.classList.remove('active');
      });
    }
  });

  // 3. Reset Location Preference Radios & hide specific cities input
  ['prof-location-pref', 'onboard-location-pref'].forEach(radioName => {
    document.querySelectorAll(`input[name="${radioName}"]`).forEach(r => {
      r.checked = false;
    });
  });
  document.querySelectorAll('.location-pref-options .radio-option').forEach(el => {
    el.classList.remove('active');
  });

  const profSpecificInput = document.getElementById('prof-specific-cities-input');
  if (profSpecificInput) profSpecificInput.style.display = 'none';
  const onbSpecificInput = document.getElementById('specific-cities-input');
  if (onbSpecificInput) onbSpecificInput.style.display = 'none';

  // 4. Reset Experience Level Radios
  ['prof-exp', 'onboard-exp'].forEach(radioName => {
    document.querySelectorAll(`input[name="${radioName}"]`).forEach(r => {
      r.checked = false;
    });
  });
  document.querySelectorAll('.exp-level-chips .chip-radio').forEach(el => {
    el.classList.remove('active');
  });

  // 5. Clear Section 3 Mail Mode cards and radio selections
  const dailyRadio = document.getElementById('radio-mode-daily');
  const onetimeRadio = document.getElementById('radio-mode-onetime');
  const dailyCard = document.getElementById('settings-mode-card-daily') || document.getElementById('mode-card-daily');
  const onetimeCard = document.getElementById('mode-card-onetime');
  if (dailyRadio) dailyRadio.checked = false;
  if (onetimeRadio) onetimeRadio.checked = false;
  if (dailyCard) {
    dailyCard.style.borderColor = '#E2E8F0';
    dailyCard.style.background = '#FFFFFF';
  }
  if (onetimeCard) {
    onetimeCard.style.borderColor = '#E2E8F0';
    onetimeCard.style.background = '#FFFFFF';
  }

  // 6. Clear Onboarding Notification Mode selection cards & alert toggles
  const ondemandCard = document.getElementById('mode-card-ondemand');
  const onbDailyCard = document.getElementById('mode-card-daily');
  const ondemandRadio = document.getElementById('mode-radio-ondemand');
  const onbDailyRadio = document.getElementById('mode-radio-daily');
  const onboardToggle = document.getElementById('onboard-toggle-email-alerts');
  const profToggle = document.getElementById('toggle-email-alerts');
  if (ondemandCard) ondemandCard.classList.remove('active');
  if (onbDailyCard) onbDailyCard.classList.remove('active');
  if (ondemandRadio) ondemandRadio.innerText = '○';
  if (onbDailyRadio) onbDailyRadio.innerText = '○';
  if (onboardToggle) onboardToggle.checked = false;
  if (profToggle) profToggle.checked = false;

  // 7. Reset dropzone text, file inputs, and previews
  const dropText = document.getElementById('dropzone-text');
  if (dropText) dropText.innerText = 'Click or drag & drop a new resume PDF / TXT file';
  const fileInput = document.getElementById('resume-file-input');
  if (fileInput) fileInput.value = '';
  selectedResumeFile = null;

  const onbDropText = document.getElementById('onboarding-dropzone-text');
  if (onbDropText) onbDropText.innerText = 'Click or drag & drop your resume file here (.pdf, .txt)';
  const onbFileInput = document.getElementById('onboarding-file-input');
  if (onbFileInput) onbFileInput.value = '';
  selectedOnboardingFile = null;

  const previewCard = document.getElementById('studio-resume-preview-card');
  if (previewCard) previewCard.style.display = 'none';
  const onbPreviewCard = document.getElementById('onboarding-preview-card');
  if (onbPreviewCard) onbPreviewCard.style.display = 'none';

  const previewElements = [
    'studio-prev-name', 'studio-prev-title', 'studio-prev-years', 'studio-prev-skills',
    'preview-name', 'preview-title', 'preview-years'
  ];
  previewElements.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.innerText = '—';
  });
  const previewSkillsContainer = document.getElementById('preview-skills-container');
  if (previewSkillsContainer) previewSkillsContainer.innerHTML = '';

  const alertEl = document.getElementById('resume-status-alert');
  if (alertEl) { alertEl.style.display = 'none'; alertEl.innerHTML = ''; }
  const onbAlertEl = document.getElementById('onboarding-status-alert');
  if (onbAlertEl) { onbAlertEl.style.display = 'none'; onbAlertEl.innerHTML = ''; }

  // 8. Reset role preset chips active state
  document.querySelectorAll('.btn-preset-chip').forEach(btn => btn.classList.remove('active'));

  parsedResumeData = null;

  // 9. Update in-memory local state completely empty
  activeProfileData = {
    name: '',
    title: '',
    education: '',
    experience_years: 0,
    skills: [],
    target_keywords: [],
    exclude_keywords: [],
    resume_text: '',
    resume_filename: '',
    preferred_locations: [],
    location_preference: '',
    job_types: [],
    experience_level: '',
    notable_projects: [],
    domains: [],
    email_notifications_enabled: false,
    min_score_notification: null,
    onboarding_completed: false,
    notification_email: preservedEmail,
    email: preservedEmail,
    mail_mode: ''
  };

  renderCandidateSummary(activeProfileData);
  updateJobSearchButtonState();
  Storage.set(localStorage, STORAGE_KEYS.CACHED_PROFILE, activeProfileData);

  // Instantly persist the empty state to the server so background /api/sync never brings old data back
  authFetch('/api/profile/reset', { method: 'POST' }).catch(err => {
    console.warn('Profile reset sync error:', err);
  });

  showToast('All profile data emptied successfully.', 'info', 3500);
}


// Profile wizard step navigation
function profileWizardGoTo(step) {
  const subtitles = ['', 'Step 1 of 3 — Resume & Text Context', 'Step 2 of 3 — Target Roles & Exclusions', 'Step 3 of 3 — Match Score & Mail Modes'];
  const subtitle = document.getElementById('profile-wizard-subtitle');
  if (subtitle) subtitle.innerText = subtitles[step] || '';

  [1, 2, 3].forEach(s => {
    const stepEl = document.getElementById(`profile-step-${s}`);
    const nodeEl = document.getElementById(`pws-node-${s}`);
    const circleEl = nodeEl ? nodeEl.querySelector('.wizard-step-circle') : null;
    if (stepEl) stepEl.style.display = s === step ? 'block' : 'none';
    if (nodeEl) {
      nodeEl.classList.toggle('active', s === step);
      nodeEl.classList.toggle('completed', s < step);
    }
    if (circleEl) {
      circleEl.innerText = s < step ? '✓' : String(s);
    }
  });
  [1, 2].forEach(s => {
    const conn = document.getElementById(`pws-conn-${s}`);
    if (conn) conn.classList.toggle('active', s < step);
  });
}

function profileWizardNext(fromStep) {
  profileWizardGoTo(fromStep + 1);
}

function profileWizardBack(fromStep) {
  profileWizardGoTo(fromStep - 1);
}

// Handler for parsing directly from the Resume Text Context textarea
async function submitTextContextParse() {
  const textInput = document.getElementById('prof-resume-text') || document.getElementById('onboarding-paste-text');
  const rawText = textInput ? textInput.value.trim() : '';
  if (!rawText) {
    showToast('Please enter or paste your resume text context.', 'info');
    return;
  }

  const btn = document.getElementById('btn-reparse-text');
  const spinner = document.getElementById('reparse-text-spinner');
  if (btn) btn.disabled = true;
  if (spinner) spinner.style.display = 'inline-block';

  try {
    const res = await authFetch('/api/resume/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_text: rawText, filename: 'text_context.txt' })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      const p = data.profile || {};
      activeProfileData = { ...activeProfileData, ...p, resume_text: rawText };
      renderCandidateSummary(activeProfileData);

      // Auto-fill form inputs
      const nameInput = document.getElementById('prof-name');
      const titleInput = document.getElementById('prof-title');
      const yearsInput = document.getElementById('prof-years');
      const eduInput = document.getElementById('prof-education');
      const skillsInput = document.getElementById('prof-skills');
      const targetsInput = document.getElementById('prof-targets');
      const excludesInput = document.getElementById('prof-excludes');

      if (nameInput && p.name) nameInput.value = p.name;
      if (titleInput && p.title) titleInput.value = p.title;
      if (yearsInput && p.experience_years) yearsInput.value = p.experience_years;
      if (eduInput && p.education) eduInput.value = p.education;
      if (skillsInput && p.skills) skillsInput.value = Array.isArray(p.skills) ? p.skills.join(', ') : p.skills;
      if (targetsInput && p.target_keywords && p.target_keywords.length) {
        targetsInput.value = Array.isArray(p.target_keywords) ? p.target_keywords.join(', ') : p.target_keywords;
      }
      if (excludesInput && p.exclude_keywords && p.exclude_keywords.length) {
        excludesInput.value = Array.isArray(p.exclude_keywords) ? p.exclude_keywords.join(', ') : p.exclude_keywords;
      }

      showToast('Candidate profile extracted from text context!', 'success');
      setTimeout(() => profileWizardGoTo(2), 600);
    } else {
      showToast('Failed to extract profile: ' + (data.message || 'error'), 'error');
    }
  } catch (err) {
    showToast('Text parsing error: ' + err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
  }
}

// Auto-parse PDF on file selection — populates text context & profile fields
async function handleResumeFileSelectedAndParse(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  selectedResumeFile = file;

  const dropText = document.getElementById('dropzone-text');
  const alertEl = document.getElementById('resume-status-alert');
  const previewCard = document.getElementById('studio-resume-preview-card');
  const nextBtn = document.getElementById('profile-next-1');
  const resumeTextInput = document.getElementById('prof-resume-text');

  if (dropText) dropText.innerText = `⏳ Parsing: ${file.name} (${(file.size / 1024).toFixed(1)} KB)...`;
  if (alertEl) { alertEl.style.display = 'none'; }
  if (nextBtn) nextBtn.disabled = false;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 90000);

  try {
    const formData = new FormData();
    formData.append('file', file);
    const res = await authFetch('/api/resume/upload', {
      method: 'POST',
      body: formData,
      signal: controller.signal
    });
    clearTimeout(timeoutId);
    const data = await parseJsonResponse(res);

    if (data.status === 'success') {
      const p = data.profile || {};
      const extractedText = data.resume_text || p.resume_text || '';
      parsedResumeData = p;
      activeProfileData = { ...activeProfileData, resume_text: extractedText, resume_filename: file.name };

      // Update dropzone label and text context textarea
      if (dropText) dropText.innerText = `✅ Text extracted from ${file.name}`;
      if (resumeTextInput && extractedText) resumeTextInput.value = extractedText;

      // Show inline extraction preview
      if (previewCard) {
        document.getElementById('studio-prev-name').innerText = p.name || '—';
        document.getElementById('studio-prev-title').innerText = p.title || '—';
        document.getElementById('studio-prev-years').innerText = p.experience_years ? `${p.experience_years} years` : '—';
        const skills = p.skills || [];
        document.getElementById('studio-prev-skills').innerText = skills.slice(0, 8).join(', ') || '—';
        previewCard.style.display = 'block';
      }

      showToast('Resume extracted! Click "Auto-Fill from Resume Context" in Step 2 if you wish to auto-populate fields.', 'success', 3500);
    } else {

      if (dropText) dropText.innerText = `⚠️ ${file.name} — parse failed, click to retry or edit text below`;
      if (alertEl) {
        alertEl.className = 'studio-alert error';
        alertEl.innerText = `Notice: ${data.message || 'Resume parsing failed. You can paste/edit details manually.'}`;
        alertEl.style.display = 'block';
      }
      showToast('Resume parsing notice: ' + (data.message || 'unknown error'), 'info');
    }
  } catch (err) {
    clearTimeout(timeoutId);
    const isTimeout = err.name === 'AbortError';
    const msg = isTimeout ? 'Parsing timed out — proceed to enter details manually.' : err.message;
    if (dropText) dropText.innerText = `⚠️ ${file.name} — click to retry or skip below`;
    if (alertEl) {
      alertEl.className = 'studio-alert error';
      alertEl.innerText = `${msg} You can click 'Skip & Enter Manually' to fill your profile directly.`;
      alertEl.style.display = 'block';
    }
    showToast(isTimeout ? 'Resume parse timed out. You can fill details manually.' : 'Notice: ' + err.message, 'info');
  }
}

// Legacy handler kept for onboarding dropzone (uses the old separate parse button)
function handleResumeFileSelected(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  selectedResumeFile = file;
  const dropText = document.getElementById('dropzone-text');
  if (dropText) {
    dropText.innerText = `Selected: ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
  }
}

// Drag and drop dropzone initialization
function initDropzoneHandlers() {
  const dropzone = document.getElementById('resume-dropzone');
  if (!dropzone) return;

  ['dragenter', 'dragover'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add('dragover');
    }, false);
  });

  ['dragleave', 'drop'].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove('dragover');
    }, false);
  });

  dropzone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files && files.length > 0) {
      selectedResumeFile = files[0];
      const dropText = document.getElementById('dropzone-text');
      if (dropText) {
        dropText.innerText = `Selected: ${files[0].name} (${(files[0].size / 1024).toFixed(1)} KB)`;
      }
    }
  }, false);
}

async function submitResumeParse() {
  const btn = document.getElementById('btn-parse-resume');
  const spinner = document.getElementById('resume-spinner');
  const btnText = document.getElementById('resume-btn-text');
  const alertEl = document.getElementById('resume-status-alert');
  const pasteText = document.getElementById('resume-paste-text')?.value || '';

  if (!selectedResumeFile && !pasteText.trim()) {
    showToast('Please select a resume file or paste resume text.', 'info');
    return;
  }

  if (btn) btn.disabled = true;
  if (spinner) spinner.style.display = 'inline-block';
  if (btnText) btnText.innerText = 'Extracting candidate profile with AI...';
  if (alertEl) alertEl.style.display = 'none';

  try {
    let res;
    if (selectedResumeFile) {
      const formData = new FormData();
      formData.append('file', selectedResumeFile);
      res = await authFetch('/api/resume/upload', {
        method: 'POST',
        body: formData
      });
    } else {
      res = await authFetch('/api/resume/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume_text: pasteText, filename: 'pasted_resume.txt' })
      });
    }

    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      showToast('Resume parsed! Click "Auto-Fill from Resume Context" to populate fields.', 'success');
      if (alertEl) {
        alertEl.className = 'studio-alert success';
        alertEl.innerText = `✅ ${data.message}`;
        alertEl.style.display = 'block';
      }
      const p = data.profile || {};
      const extractedText = data.resume_text || p.resume_text || pasteText || '';
      parsedResumeData = p;
      activeProfileData = { ...activeProfileData, resume_text: extractedText };
      const resumeTextInput = document.getElementById('prof-resume-text') || document.getElementById('resume-paste-text');
      if (resumeTextInput && extractedText) resumeTextInput.value = extractedText;
    } else {
      showToast('Resume parsing error: ' + data.message, 'error');
      if (alertEl) {
        alertEl.className = 'studio-alert error';
        alertEl.innerText = `Error: ${data.message}`;
        alertEl.style.display = 'block';
      }
    }
  } catch (err) {
    showToast('Notice: ' + err.message, 'error');
    if (alertEl) {
      alertEl.className = 'studio-alert error';
      alertEl.innerText = err.message;
      alertEl.style.display = 'block';
    }
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
    if (btnText) btnText.innerText = 'Parse Resume with AI & Update Memory';
  }
}

async function saveProfilePreferences() {
  const nameInput = document.getElementById('prof-name');
  const name = nameInput ? nameInput.value.trim() : (activeProfileData?.name || '');

  const targetsInput = document.getElementById('prof-targets');
  const targets = targetsInput && targetsInput.value.trim() !== ''
    ? targetsInput.value.split(',').map(s => s.trim()).filter(Boolean)
    : (Array.isArray(activeProfileData?.target_keywords) ? activeProfileData.target_keywords : []);

  const titleInput = document.getElementById('prof-title');
  const title = titleInput && titleInput.value.trim() !== ''
    ? titleInput.value.trim()
    : (targets.length > 0 ? targets[0] : (activeProfileData?.title || ''));

  const yearsInput = document.getElementById('prof-years');
  const years = yearsInput && yearsInput.value.trim() !== ''
    ? (parseFloat(yearsInput.value) || 0)
    : (activeProfileData?.experience_years || 0);

  const eduInput = document.getElementById('prof-education');
  const education = eduInput && eduInput.value.trim() !== ''
    ? eduInput.value.trim()
    : (activeProfileData?.education || '');

  const skillsInput = document.getElementById('prof-skills');
  const skills = skillsInput && skillsInput.value.trim() !== ''
    ? skillsInput.value.split(',').map(s => s.trim()).filter(Boolean)
    : (Array.isArray(activeProfileData?.skills) ? activeProfileData.skills : (Array.isArray(parsedResumeData?.skills) ? parsedResumeData.skills : []));

  const excludesInput = document.getElementById('prof-excludes');
  const excludes = excludesInput && excludesInput.value.trim() !== ''
    ? excludesInput.value.split(',').map(s => s.trim()).filter(Boolean)
    : (Array.isArray(activeProfileData?.exclude_keywords) ? activeProfileData.exclude_keywords : []);

  const dailyRadio = document.getElementById('radio-mode-daily');
  const notifEnabled = dailyRadio ? Boolean(dailyRadio.checked) : false;

  const onetimeRadio = document.getElementById('radio-mode-onetime');
  const onetimeSelected = onetimeRadio ? Boolean(onetimeRadio.checked) : false;
  const mailMode = notifEnabled ? 'daily' : (onetimeSelected ? 'onetime' : '');

  const notifEmail = currentAuthSession?.user?.email || activeProfileData?.notification_email || '';

  const minScoreInput = document.getElementById('notif-min-score');
  const minScoreVal = minScoreInput ? minScoreInput.value.trim() : '';
  const notifScore = minScoreVal ? parseFloat(minScoreVal) : null;

  const resumeTextInput = document.getElementById('prof-resume-text');
  const resumeText = resumeTextInput ? resumeTextInput.value.trim() : (activeProfileData?.resume_text || '');

  const jobTypes = getSelectedJobTypes('prof-job-types');
  const expLevel = getSelectedExpLevel('prof-exp');
  const locationPref = getLocationPreference('prof-location-pref', 'prof-specific-cities');

  const payload = {
    name,
    title,
    experience_years: years,
    education,
    skills,
    target_keywords: targets,
    exclude_keywords: excludes,
    resume_text: resumeText,
    resume_filename: activeProfileData?.resume_filename || '',
    email_notifications_enabled: notifEnabled,
    mail_mode: mailMode,
    notification_email: notifEmail,
    min_score_notification: notifScore,
    onboarding_completed: Boolean(name || title || (skills.length > 0) || (targets.length > 0) || resumeText),
    job_types: jobTypes,
    experience_level: expLevel,
    location_preference: locationPref,
    preferred_locations: locationPref,
    domains: activeProfileData?.domains || parsedResumeData?.domains || [],
    notable_projects: activeProfileData?.notable_projects || parsedResumeData?.notable_projects || []
  };

  const btn = document.getElementById('btn-profile-save');
  const spinner = document.getElementById('profile-save-spinner');
  const btnText = document.getElementById('profile-save-btn-text');
  if (btn) btn.disabled = true;
  if (spinner) spinner.style.display = 'inline-block';
  if (btnText) btnText.innerText = 'Saving...';

  appState.isSavingProfile = true;

  try {
    const res = await authFetch('/api/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      const savedProfile = data.profile || payload;
      activeProfileData = { ...savedProfile };
      Storage.set(localStorage, STORAGE_KEYS.CACHED_PROFILE, activeProfileData);
      renderCandidateSummary(savedProfile);
      updateJobSearchButtonState();
      showToast('Profile saved successfully! Candidate radar updated.', 'success', 3500);
      closeProfileModal();
      closeOnboardingModal(true);
      Storage.set(sessionStorage, 'onboarding_dismissed', true);
      appState.isSavingProfile = false;
      await syncDashboard(true);
    } else {
      showToast('Failed to save profile: ' + data.message, 'error');
    }
  } catch (err) {
    showToast('Failed to save profile: ' + err.message, 'error');
  } finally {
    appState.isSavingProfile = false;
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
    if (btnText) btnText.innerText = 'Save Profile';
  }
}

function handleNotificationToggleChange() {
  const isChecked = Boolean(document.getElementById('toggle-email-alerts')?.checked);
  const indicator = document.getElementById('notif-badge-indicator');
  if (indicator) {
    indicator.className = isChecked ? 'notif-badge-on' : 'notif-badge-off';
    indicator.innerText = isChecked ? 'Email Alerts: Active' : 'Email Alerts: Off';
  }
}

function triggerJobSearch() {
  return runPipeline();
}

// Pipeline Execution (Non-Blocking Live Polling)
async function runPipeline() {
  if (authConfig.auth_required && !currentAuthSession) {
    openAuthModal('signin');
    showToast('Please sign in to trigger autonomous pipeline scans.', 'info');
    return;
  }

  if (!isCandidateProfileFilled(activeProfileData)) {
    openOnboardingModal();
    showToast('Please fill candidate profile radar details (Name, Target Title, Skills) first.', 'info', 4000);
    return;
  }

  const btn = document.getElementById('btn-run');
  const spinner = document.getElementById('run-spinner');
  const text = document.getElementById('run-text');
  const consoleBox = document.getElementById('run-console');
  const isMock = false;

  appState.pipelineRunning = true;
  if (btn) {
    btn.disabled = true;
    btn.classList.add('btn-inactive');
  }
  if (spinner) spinner.style.display = 'inline-block';
  if (text) text.innerText = 'Starting Scanner...';
  if (consoleBox) consoleBox.innerText = 'Initiating autonomous pipeline scan in background...';

  // Render the scanning loading state inside the main job listing card immediately
  fetchAndRenderJobs(false);

  try {
    const res = await authFetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mock: isMock })
    });
    const data = await parseJsonResponse(res);

    if (data.status === 'success' || data.status === 'busy') {
      showToast('Pipeline scanner running in background...', 'info', 2500);

      // Continuous non-blocking progress poller
      const pollPipeline = async () => {
        try {
          const syncRes = await authFetch('/api/sync', { cache: 'no-store' });
          const syncData = await parseJsonResponse(syncRes);
          if (syncData.status === 'success') {
            updatePipelineConsole(syncData.pipeline);
            renderMetrics(syncData.stats);

            if (syncData.pipeline && syncData.pipeline.running) {
              setTimeout(pollPipeline, 1000);
            } else {
              // Completed or errored
              appState.pipelineRunning = false;
              if (syncData.pipeline && syncData.pipeline.step === 'completed') {
                showToast('Pipeline scan completed successfully!', 'success');
                await fetchAndRenderJobs(false);
                refreshDigest(true);
                broadcastSync('STATE_MUTATED');
              } else if (syncData.pipeline && syncData.pipeline.step === 'error') {
                showToast(syncData.pipeline.message || 'Pipeline scan encountered an error', 'error');
              }
              updateJobSearchButtonState();
            }
          }
        } catch (pollErr) {
          console.warn('Pipeline poll notice:', pollErr);
          setTimeout(pollPipeline, 2000);
        }
      };

      setTimeout(pollPipeline, 800);

    } else {
      appState.pipelineRunning = false;
      // Backend guard: profile not yet filled — redirect user to onboarding
      if (data.message && data.message.includes('candidate profile')) {
        if (consoleBox) consoleBox.innerText = 'Candidate radar incomplete. Please configure your profile to activate autonomous job scouting.';
        showToast('Please complete your candidate profile first.', 'info', 4500);
        openOnboardingModal();
      } else {
        if (consoleBox) consoleBox.innerText = 'Error: ' + (data.message || 'Failed to start pipeline');
        showToast('Pipeline notice: ' + data.message, 'error');
      }
      updateJobSearchButtonState();
    }
  } catch (err) {
    appState.pipelineRunning = false;
    if (consoleBox) consoleBox.innerText = 'Notice: ' + err.message;
    showToast('Notice: ' + err.message, 'error');
    updateJobSearchButtonState();
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

  // 2.5. Optimistic Card Removal for Active Status Filter
  if ((appState.filter === 'applied' && isUnmark) || (appState.filter === 'unapplied' && !isUnmark)) {
    const card = document.getElementById('job-card-' + jobId);
    if (card) {
      card.style.transition = 'all 0.25s ease';
      card.style.opacity = '0';
      card.style.transform = 'translateY(10px)';
      setTimeout(() => {
        card.remove();
        const container = document.getElementById('job-list-container');
        if (container && !container.querySelector('.job-card')) {
          container.innerHTML = `
            <div class="empty-state">
              <div class="empty-state-icon">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
              </div>
              <div class="empty-state-title">No Matching Opportunities Found</div>
              <div class="empty-state-desc">
                No jobs currently meet the selected filter criteria.
              </div>
            </div>
          `;
        }
      }, 250);
    }
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
    const res = await authFetch('/api/applied', {
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
    const res = await authFetch('/api/delete', {
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





// Authenticated Digest Viewport Refresh (Shadow DOM Isolated Rendering — Zero about:srcdoc Subframe History Entries)
let digestShadowRoot = null;

async function refreshDigest(force = false) {
  const container = document.getElementById('digest-frame');
  if (!container) return;

  if (authConfig.auth_required && !currentAuthSession) {
    return;
  }

  if (appState.activeTab !== 'digest' && !force) return;

  try {
    const res = await authFetch('/api/digest?t=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) {
      if (res.status === 401) {
        const unauthMarkup = '<div style="font-family:sans-serif; text-align:center; padding:60px 20px; color:#64748b;"><h3>🔒 Authentication Required</h3><p>Please sign in to view your career digest.</p></div>';
        if (container.tagName === 'IFRAME') {
          container.srcdoc = unauthMarkup;
        } else {
          if (!digestShadowRoot) {
            digestShadowRoot = container.shadowRoot || container.attachShadow({ mode: 'open' });
          }
          digestShadowRoot.innerHTML = unauthMarkup;
        }
        return;
      }
      throw new Error(`HTTP ${res.status}`);
    }
    const html = await res.text();
    if (container.tagName === 'IFRAME') {
      container.srcdoc = html;
    } else {
      if (!digestShadowRoot) {
        digestShadowRoot = container.shadowRoot || container.attachShadow({ mode: 'open' });
      }
      digestShadowRoot.innerHTML = html;
    }
  } catch (e) {
    console.warn('Digest preview notice:', e);
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
    if (document.getElementById('custom-job-modal')?.classList.contains('active')) {
      closeCustomJobModal();
    } else if (document.getElementById('kit-modal')?.classList.contains('active')) {
      closeKitModal();
    } else if (document.getElementById('profile-modal')?.classList.contains('active')) {
      closeProfileModal();
    } else if (document.getElementById('onboarding-modal')?.classList.contains('active')) {
      closeOnboardingModal(true);
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
  const customJobModal = document.getElementById('custom-job-modal');
  if (customJobModal && e.target === customJobModal) {
    closeCustomJobModal();
  }
  const kitModal = document.getElementById('kit-modal');
  if (kitModal && e.target === kitModal) {
    closeKitModal();
  }
  const profileModal = document.getElementById('profile-modal');
  if (profileModal && e.target === profileModal) {
    closeProfileModal();
  }
  const onboardingModal = document.getElementById('onboarding-modal');
  if (onboardingModal && e.target === onboardingModal) {
    closeOnboardingModal(true);
  }
});

// ==============================================================================
// Supabase Authentication & Landing Page View Controller
// ==============================================================================

function setAppView(view) {
  const landingView = document.getElementById('landing-view');
  const dashboardView = document.getElementById('dashboard-view');
  const headerMetrics = document.getElementById('header-metrics');
  const landingNavLinks = document.getElementById('landing-nav-links');

  if (view === 'dashboard') {
    if (landingView) landingView.style.display = 'none';
    if (dashboardView) dashboardView.style.display = 'flex';
    if (headerMetrics) headerMetrics.style.display = 'flex';
    if (landingNavLinks) landingNavLinks.style.display = 'none';
    setSyncStatus('synced', 'Live Synced');
  } else {
    if (landingView) landingView.style.display = 'flex';
    if (dashboardView) dashboardView.style.display = 'none';
    if (headerMetrics) headerMetrics.style.display = 'none';
    if (landingNavLinks) landingNavLinks.style.display = 'flex';
    setSyncStatus('synced', 'Radar: Online');
  }
}

function switchAuthTab(tab) {
  const isSignIn = tab === 'signin';
  const tabSignIn = document.getElementById('tab-signin');
  const tabSignUp = document.getElementById('tab-signup');
  const formSignIn = document.getElementById('form-signin');
  const formSignUp = document.getElementById('form-signup');

  if (tabSignIn) tabSignIn.classList.toggle('active', isSignIn);
  if (tabSignUp) tabSignUp.classList.toggle('active', !isSignIn);
  if (formSignIn) formSignIn.style.display = isSignIn ? 'flex' : 'none';
  if (formSignUp) formSignUp.style.display = !isSignIn ? 'flex' : 'none';
  setAuthFeedback('');
}

function scrollToAuth(tab = 'signin') {
  switchAuthTab(tab);
  const authAnchor = document.getElementById('auth-card-anchor');
  if (authAnchor) {
    authAnchor.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(() => {
      const emailInput = document.getElementById(tab === 'signup' ? 'signup-email' : 'signin-email');
      if (emailInput) emailInput.focus();
    }, 400);
  }
}

function openAuthModal(tab = 'signin') {
  setAppView('landing');
  scrollToAuth(tab);
}

function closeAuthModal() {
  setAuthFeedback('');
}

function setAuthFeedback(message, type = 'error') {
  const el = document.getElementById('auth-feedback');
  if (!el) return;
  if (!message) {
    el.style.display = 'none';
    el.innerText = '';
    el.className = 'auth-feedback';
    return;
  }
  el.className = `auth-feedback ${type}`;
  el.innerText = message;
  el.style.display = 'block';
}

function updateUserHeader(session) {
  const userEmail = document.getElementById('user-email');
  const userAvatar = document.getElementById('user-avatar');

  if (session && session.user) {
    setAppView('dashboard');
    const email = session.user.email || 'User';
    if (userEmail) userEmail.innerText = email;
    if (userAvatar) userAvatar.innerText = email.charAt(0).toUpperCase();
  } else {
    setAppView('landing');
  }
}

async function handleSignInSubmit(e) {
  e.preventDefault();
  if (!supabaseClient) {
    setAuthFeedback('Supabase client not initialized. Please verify SUPABASE_URL & ANON_KEY.', 'error');
    return;
  }

  const email = document.getElementById('signin-email')?.value.trim();
  const password = document.getElementById('signin-password')?.value;
  const spinner = document.getElementById('signin-spinner');
  const btnText = document.getElementById('signin-submit-text');
  const submitBtn = document.getElementById('btn-submit-signin');

  if (!email || !password) {
    setAuthFeedback('Please enter both email and password.', 'error');
    return;
  }

  if (spinner) spinner.style.display = 'inline-block';
  if (btnText) btnText.innerText = 'Signing in...';
  if (submitBtn) submitBtn.disabled = true;
  setAuthFeedback('');

  try {
    const { data, error } = await supabaseClient.auth.signInWithPassword({
      email: email,
      password: password,
    });

    if (error) {
      if (error.message.toLowerCase().includes('invalid login credentials')) {
        setAuthFeedback('Invalid email or password. If you haven\'t created an account yet, click "Create Account" above first.', 'error');
      } else if (error.message.toLowerCase().includes('email not confirmed')) {
        setAuthFeedback('Email not confirmed yet. Please check your inbox for the Supabase verification email, or disable "Confirm email" in Supabase Settings.', 'error');
      } else {
        setAuthFeedback(error.message, 'error');
      }
    } else {
      currentAuthSession = data.session;
      updateUserHeader(data.session);
      showToast('Signed in successfully!', 'success');
      syncDashboard(true);
      startHeartbeat();
    }
  } catch (err) {
    setAuthFeedback(err.message, 'error');
  } finally {
    if (spinner) spinner.style.display = 'none';
    if (btnText) btnText.innerText = 'Sign In to Dashboard';
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function handleSignUpSubmit(e) {
  e.preventDefault();
  if (!supabaseClient) {
    setAuthFeedback('Supabase client not initialized.', 'error');
    return;
  }

  const email = document.getElementById('signup-email')?.value.trim();
  const password = document.getElementById('signup-password')?.value;
  const spinner = document.getElementById('signup-spinner');
  const btnText = document.getElementById('signup-submit-text');
  const submitBtn = document.getElementById('btn-submit-signup');

  if (!email || !password) {
    setAuthFeedback('Please enter email and password.', 'error');
    return;
  }

  if (password.length < 6) {
    setAuthFeedback('Password must be at least 6 characters.', 'error');
    return;
  }

  if (spinner) spinner.style.display = 'inline-block';
  if (btnText) btnText.innerText = 'Creating account...';
  if (submitBtn) submitBtn.disabled = true;
  setAuthFeedback('');

  try {
    const { data, error } = await supabaseClient.auth.signUp({
      email: email,
      password: password,
    });

    if (error) {
      if (error.message.toLowerCase().includes('user already registered')) {
        setAuthFeedback('An account with this email already exists. Please switch to "Sign In" above.', 'error');
      } else {
        setAuthFeedback(error.message, 'error');
      }
    } else if (data?.user && !data?.session) {
      setAuthFeedback('Registration successful! Please check your email inbox to confirm your account (or disable "Confirm email" in Supabase settings).', 'success');
      showToast('Confirmation email dispatched', 'info');
    } else if (data?.session) {
      currentAuthSession = data.session;
      updateUserHeader(data.session);
      showToast('Account created and signed in!', 'success');
      syncDashboard(true);
      startHeartbeat();
    }
  } catch (err) {
    setAuthFeedback(err.message, 'error');
  } finally {
    if (spinner) spinner.style.display = 'none';
    if (btnText) btnText.innerText = 'Create Account & Start';
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function handleGoogleSignIn() {
  if (!supabaseClient) {
    setAuthFeedback('Supabase client not initialized.', 'error');
    return;
  }

  try {
    const { error } = await supabaseClient.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin
      }
    });
    if (error) {
      setAuthFeedback(error.message, 'error');
    }
  } catch (err) {
    setAuthFeedback(err.message, 'error');
  }
}

async function handleForgotPassword() {
  if (!supabaseClient) {
    showToast('Supabase client not initialized', 'error');
    return;
  }
  const emailInput = document.getElementById('signin-email');
  const email = emailInput ? emailInput.value.trim() : '';

  if (!email) {
    setAuthFeedback('Please enter your email address above, then click "Forgot password?".', 'error');
    return;
  }

  try {
    const { error } = await supabaseClient.auth.resetPasswordForEmail(email, {
      redirectTo: window.location.origin
    });
    if (error) {
      setAuthFeedback(error.message, 'error');
    } else {
      setAuthFeedback('Password reset link sent to ' + email, 'success');
      showToast('Password reset link sent to your email', 'success');
    }
  } catch (err) {
    setAuthFeedback(err.message, 'error');
  }
}

async function handleSignOut() {
  if (!confirm('Are you sure you want to sign out?')) {
    return;
  }

  try {
    if (supabaseClient) {
      await supabaseClient.auth.signOut();
    }
  } catch (e) {
    console.warn('SignOut notice:', e);
  }

  currentAuthSession = null;
  updateUserHeader(null);
  stopHeartbeat();
  showToast('Signed out successfully', 'info');
  setAppView('landing');
}

async function initAuth() {
  try {
    const res = await fetch('/api/auth/config', { cache: 'no-store' });
    const cfg = await parseJsonResponse(res);

    authConfig = {
      auth_required: Boolean(cfg.auth_required),
      supabase_url: cfg.supabase_url || '',
      supabase_anon_key: cfg.supabase_anon_key || ''
    };

    if (window.supabase && authConfig.supabase_url && authConfig.supabase_anon_key) {
      supabaseClient = window.supabase.createClient(authConfig.supabase_url, authConfig.supabase_anon_key, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
          storage: window.localStorage
        }
      });

      // Get initial session from localStorage
      const { data } = await supabaseClient.auth.getSession();
      currentAuthSession = data?.session || null;

      // Listen for auth state changes across all tabs and token refreshes
      supabaseClient.auth.onAuthStateChange((event, session) => {
        currentAuthSession = session;
        updateUserHeader(session);
        if (session) {
          setAppView('dashboard');
          syncDashboard(true);
          startHeartbeat();

          // Clean up OAuth fragment from address bar if present
          if (window.location.hash && window.location.hash.includes('access_token')) {
            window.history.replaceState(null, '', window.location.pathname + window.location.search);
          }
        } else {
          stopHeartbeat();
          if (authConfig.auth_required) {
            setAppView('landing');
          }
        }
      });
    }

    // Initialize View based on restored session
    if (currentAuthSession) {
      setAppView('dashboard');
      updateUserHeader(currentAuthSession);
      syncDashboard(true);
      startHeartbeat();
    } else if (authConfig.auth_required) {
      setAppView('landing');
      stopHeartbeat();
    } else {
      // Local dev mode with auth bypassed
      setAppView('dashboard');
      syncDashboard(true);
      startHeartbeat();
    }
  } catch (err) {
    console.warn('Auth configuration init error:', err);
    setAppView('dashboard');
    syncDashboard(true);
    startHeartbeat();
  }
}


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

  // Hydrate cached stats & profile
  const cachedStats = Storage.get(localStorage, STORAGE_KEYS.CACHED_STATS, null);
  if (cachedStats && cachedStats.stats) {
    renderMetrics(cachedStats.stats);
  }

  const cachedProfile = Storage.get(localStorage, STORAGE_KEYS.CACHED_PROFILE, null);
  if (cachedProfile) {
    activeProfileData = cachedProfile;
    renderCandidateSummary(cachedProfile);
  }

  // Set active tab without firing unauthenticated network requests
  switchTab(appState.activeTab, false);

  // Initialize draft saving & dropzones
  initDraftSaving();
  initDropzoneHandlers();
  initOnboardingDropzone();

  // Initialize Supabase Authentication & start data sync
  initAuth();

  // Initial check on job search button activation state
  updateJobSearchButtonState();
});

// Job Type & Location Preference Extraction Helpers
function getSelectedJobTypes(containerId) {
  const container = document.getElementById(containerId);
  if (!container) return [];
  const checked = Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map(cb => cb.value);
  return checked;
}

function getSelectedExpLevel(nameAttr) {
  const selected = document.querySelector(`input[name="${nameAttr}"]:checked`);
  return selected ? selected.value : '';
}

function getLocationPreference(radioName, specificInputId) {
  const selected = document.querySelector(`input[name="${radioName}"]:checked`);
  if (!selected) {
    return { type: '', locations: [] };
  }
  const type = selected.value;
  let locations = [];
  if (type === 'specific_cities') {
    const input = document.getElementById(specificInputId);
    if (input) {
      locations = input.value.split(',').map(s => s.trim()).filter(Boolean);
    }
  }
  return { type, locations };
}

// Global UI listeners for chips and radios
document.addEventListener('change', (e) => {
  if (e.target.matches('input[type="checkbox"]') && e.target.closest('.chip-toggle')) {
    e.target.closest('.chip-toggle').classList.toggle('active', e.target.checked);
  }
  if (e.target.matches('input[type="radio"]') && e.target.closest('.chip-radio')) {
    const name = e.target.name;
    document.querySelectorAll(`input[name="${name}"]`).forEach(radio => {
      radio.closest('.chip-radio').classList.toggle('active', radio.checked);
    });
  }
  if (e.target.matches('input[name="onboard-location-pref"]') || e.target.matches('input[name="prof-location-pref"]')) {
    const name = e.target.name;
    document.querySelectorAll(`input[name="${name}"]`).forEach(radio => {
      radio.closest('.radio-option').classList.toggle('active', radio.checked);
    });
    
    // Toggle specific cities input
    const isSpecific = e.target.value === 'specific_cities';
    const inputContainer = document.getElementById(name === 'onboard-location-pref' ? 'specific-cities-input' : 'prof-specific-cities-input');
    if (inputContainer) {
      inputContainer.style.display = isSpecific ? 'block' : 'none';
    }
  }
});

// Copy to Clipboard global helper
function copyToClipboard(text, btnEl) {
  navigator.clipboard.writeText(text).then(() => {
    const originalText = btnEl.innerHTML;
    btnEl.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#059669" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><polyline points="20 6 9 17 4 12"></polyline></svg><span style="color:#059669; font-weight:800;">Copied!</span>`;
    showToast('Copied to clipboard!', 'success');
    
    setTimeout(() => {
      btnEl.innerHTML = originalText;
    }, 2000);
  }).catch(err => {
    showToast('Clipboard copy failed: ' + err.message, 'error');
  });
}
