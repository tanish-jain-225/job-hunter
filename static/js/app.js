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
  LOCATION_FILTER: 'jobhunt_location_filter',
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

// Indian Tech Hubs & Compensation Helpers
const INDIA_CITIES = [
  'bengaluru', 'bangalore', 'hyderabad', 'pune', 'delhi', 'ncr', 'noida', 'gurugram', 'gurgaon',
  'mumbai', 'chennai', 'kolkata', 'ahmedabad', 'surat', 'jaipur', 'lucknow', 'thane', 'navi mumbai',
  'indore', 'bhopal', 'nagpur', 'coimbatore', 'kochi', 'cochin', 'chandigarh', 'bhubaneswar',
  'visakhapatnam', 'vizag', 'vadodara', 'baroda', 'patna', 'mysore', 'mysuru', 'hubli', 'mangalore',
  'thiruvananthapuram', 'trivandrum', 'mohali', 'whitefield', 'electronic city', 'bellandur',
  'koramangala', 'hitec city', 'hiteccity', 'cyberabad', 'gachibowli', 'madhapur', 'hinjewadi',
  'magarpatta', 'manyata', 'delhi ncr', 'delhi-ncr', 'india', 'ind'
];

function isIndiaJob(j) {
  if (!j) return false;
  const loc = (j.location || '').toLowerCase();
  if (INDIA_CITIES.some(c => loc.includes(c))) return true;
  if (/\b(in|ind|india)\b/i.test(loc)) return true;
  return false;
}

function isRemoteJob(j) {
  if (!j) return false;
  const loc = (j.location || '').toLowerCase();
  const title = (j.title || '').toLowerCase();
  return ['remote', 'wfh', 'hybrid', 'anywhere', 'work from home'].some(k => loc.includes(k) || title.includes(k));
}

function formatSalaryBadge(j) {
  if (!j) return '';
  let sal = (j.salary || '').trim();
  if (!sal && j.title) {
    const match = j.title.match(/(\b\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?\s*(?:LPA|lpa|Lakh|lakhs|Lac|lacs)\b)/i) ||
                  j.title.match(/(₹\s*[\d,]+(?:\s*-\s*₹?\s*[\d,]+)?(?:\s*\/\s*(?:mo|month|yr|year|annum))?)/i);
    if (match) sal = match[1];
  }
  if (!sal && j.description) {
    const descSample = j.description.slice(0, 500);
    const match = descSample.match(/(\b\d+(?:\.\d+)?(?:\s*-\s*\d+(?:\.\d+)?)?\s*(?:LPA|lpa|Lakh|lakhs|Lac|lacs)\b)/i) ||
                  descSample.match(/(₹\s*[\d,]+(?:\s*-\s*₹?\s*[\d,]+)?(?:\s*\/\s*(?:mo|month|yr|year|annum))?)/i) ||
                  descSample.match(/(₹\s*[\d,]+(?:\s*stipend)?)/i);
    if (match) sal = match[1];
  }
  if (!sal) return '';
  const isRupee = sal.includes('₹') || /lpa|lakh|lac/i.test(sal);
  const icon = isRupee ? '₹' : '💰';
  return `<span class="badge-salary-pill" title="Compensation / Stipend">${icon} ${escapeHtml(sal)}</span>`;
}

// Global In-Memory Application State
const appState = {
  version: null,
  stats: { tracked: 0, emailed: 0, applied: 0, shortlisted: 0, unapplied: 0 },
  filter: 'all',
  locationFilter: Storage.get(localStorage, STORAGE_KEYS.LOCATION_FILTER, 'all') || 'all',
  ats: 'all',
  sort: 'date',
  search: '',
  page: 1,
  pageSize: Storage.get(localStorage, 'jobhunt_page_size', 10) || 10,
  activeTab: 'digest',
  activeKitId: null,
  jobsMap: {},
  jobsList: [],
  isSyncing: false,
  isSavingProfile: false,
  isOffline: !navigator.onLine,
  authInitialized: false,
  digestRefreshing: false,
  lastSyncTimestamp: Date.now()
};

// Accessible modal focus management (WCAG 2.2 AA focus trap & restoration)
let _lastFocusedBeforeModal = null;
function _getModalFocusableElements(modalEl) {
  if (!modalEl) return [];
  const selectors = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';
  return Array.from(modalEl.querySelectorAll(selectors)).filter(
    el => el.offsetParent !== null && !el.closest('[style*="display: none"]') && !el.closest('[style*="display:none"]')
  );
}
function activateModalFocus(modalEl, preferredEl = null) {
  if (!modalEl) return;
  if (!_lastFocusedBeforeModal && document.activeElement instanceof HTMLElement) {
    _lastFocusedBeforeModal = document.activeElement;
  }
  requestAnimationFrame(() => {
    const target = (preferredEl && preferredEl.offsetParent !== null)
      ? preferredEl
      : (_getModalFocusableElements(modalEl)[0] || modalEl);
    if (target && typeof target.focus === 'function') {
      target.focus({ preventScroll: true });
    }
  });
}
function _getActiveModalOverlay() {
  return document.querySelector('.modal-overlay.active');
}

function deactivateModalFocus() {
  const activeOverlay = _getActiveModalOverlay();
  if (activeOverlay) return;
  if (_lastFocusedBeforeModal && document.contains(_lastFocusedBeforeModal)) {
    try {
      _lastFocusedBeforeModal.focus({ preventScroll: true });
    } catch (e) {}
  }
  _lastFocusedBeforeModal = null;
}

/**
 * Calculates follow-up elapsed time and badges for active opportunities.
 * @param {Object} j - Job object
 * @returns {Object|null} Elapsed badge info or null
 */
function getElapsedAppliedInfo(j) {
  const stage = j.application_stage || (j.applied ? 'applied' : 'to_apply');
  if (stage !== 'applied' && stage !== 'interviewing') return null;
  const appliedDateStr = j.applied_on || j.first_seen || j.created_at;
  if (!appliedDateStr) return null;
  try {
    const appliedTime = new Date(appliedDateStr).getTime();
    if (isNaN(appliedTime)) return null;
    const diffDays = Math.floor((Date.now() - appliedTime) / (1000 * 60 * 60 * 24));
    if (diffDays >= 4) {
      return {
        days: diffDays,
        badgeText: `${diffDays}d ago · Follow Up`,
        isDue: diffDays >= 5
      };
    }
  } catch (e) {}
  return null;
}

/**
 * Updates application pipeline stage with optimistic UI rollback on failure.
 * @param {string} jobId - Unique identifier for the job
 * @param {string} newStage - Target stage (to_apply, applied, interviewing, offer, rejected)
 */
async function updateJobStageDirect(jobId, newStage) {
  if (!checkAuthOrRedirect('update application pipeline stage')) return;
  const j = appState.jobsMap[jobId];
  if (!j) return;
  if (inFlightJobActions.has(jobId)) {
    showToast('That opportunity is already being updated.', 'info', 2200);
    return;
  }
  inFlightJobActions.add(jobId);

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
      if (data.stats) renderMetrics(data.stats);
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
  } finally {
    inFlightJobActions.delete(jobId);
  }
}

/**
 * Renders the responsive pagination bar controls.
 * @param {number} totalJobs - Total filtered jobs count
 * @param {number} startIdx - Zero-indexed start position
 * @param {number} endIdx - End position
 * @param {number} totalPages - Total computed page count
 * @returns {string} HTML markup for pagination controls
 */
function renderPaginationHtml(totalJobs, startIdx, endIdx, totalPages) {
  const currentPage = appState.page || 1;
  const currentSize = appState.pageSize || 10;

  if (totalJobs === 0) return '';

  // Generate page numbers array (with ellipsis if large)
  const pages = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (currentPage > 3) pages.push('...');
    const startP = Math.max(2, currentPage - 1);
    const endP = Math.min(totalPages - 1, currentPage + 1);
    for (let i = startP; i <= endP; i++) pages.push(i);
    if (currentPage < totalPages - 2) pages.push('...');
    pages.push(totalPages);
  }

  const pageButtons = pages.map(p => {
    if (p === '...') return `<span class="pagination-ellipsis" aria-hidden="true">…</span>`;
    const isActive = p === currentPage;
    return `<button type="button" class="pagination-btn ${isActive ? 'active' : ''}" data-action="set-page" data-page="${p}" ${isActive ? 'aria-current="page"' : ''} title="Go to page ${p}">${p}</button>`;
  }).join('');

  return `
    <div class="pagination-bar" role="navigation" aria-label="Job Board Pagination">
      <div class="pagination-info">
        Opportunities Feed
      </div>
      <div class="pagination-controls">
        <button type="button" class="pagination-btn pagination-nav-btn" data-action="set-page" data-page="${currentPage - 1}" ${currentPage <= 1 ? 'disabled' : ''} aria-label="Previous Page" title="Previous Page">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
          <span>Prev</span>
        </button>
        <div class="pagination-pages-group">
          ${pageButtons}
        </div>
        <button type="button" class="pagination-btn pagination-nav-btn" data-action="set-page" data-page="${currentPage + 1}" ${currentPage >= totalPages ? 'disabled' : ''} aria-label="Next Page" title="Next Page">
          <span>Next</span>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"></polyline></svg>
        </button>
      </div>
      <div class="pagination-size-wrapper">
        <label for="pagination-page-size" class="pagination-size-label">Per Page:</label>
        <select id="pagination-page-size" class="pagination-size-select" aria-label="Opportunities per page">
          <option value="10" ${currentSize === 10 ? 'selected' : ''}>10</option>
          <option value="25" ${currentSize === 25 ? 'selected' : ''}>25</option>
          <option value="50" ${currentSize === 50 ? 'selected' : ''}>50</option>
        </select>
      </div>
    </div>
  `;
}

/**
 * Navigates to a specific pagination page and scrolls view into focus.
 * @param {number} pageNum - Target page number
 */
function setPage(pageNum) {
  const totalJobs = appState.jobsList ? appState.jobsList.length : 0;
  const totalPages = Math.ceil(totalJobs / (appState.pageSize || 10)) || 1;
  const target = Math.max(1, Math.min(pageNum, totalPages));
  appState.page = target;
  const container = document.getElementById('job-list-container');
  if (container && appState.jobsList) {
    container.innerHTML = renderJobsListHtml(appState.jobsList);
    const trackerBar = document.querySelector('.tracker-bar');
    if (trackerBar) {
      trackerBar.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
}

/**
 * Updates page size preference and persists to localStorage.
 * @param {number|string} newSize - Target page size (10, 25, 50)
 */
function setPageSize(newSize) {
  appState.pageSize = parseInt(newSize, 10) || 10;
  appState.page = 1;
  Storage.set(localStorage, 'jobhunt_page_size', appState.pageSize);
  const container = document.getElementById('job-list-container');
  if (container && appState.jobsList) {
    container.innerHTML = renderJobsListHtml(appState.jobsList);
  }
}

/**
 * Workflow Guide Banner Controls
 */
function dismissWorkflowGuide() {
  const banner = document.getElementById('workflow-guide-banner');
  if (banner) {
    banner.style.display = 'none';
    try {
      localStorage.setItem('jobhunter_guide_dismissed', 'true');
    } catch (e) {}
  }
}

function toggleWorkflowGuide() {
  const banner = document.getElementById('workflow-guide-banner');
  if (banner) {
    const isHidden = banner.style.display === 'none';
    banner.style.display = isHidden ? 'block' : 'none';
    if (isHidden) {
      try {
        localStorage.removeItem('jobhunter_guide_dismissed');
      } catch (e) {}
    }
  }
}

function initWorkflowGuideState() {
  try {
    const dismissed = localStorage.getItem('jobhunter_guide_dismissed');
    const banner = document.getElementById('workflow-guide-banner');
    if (banner && dismissed === 'true') {
      banner.style.display = 'none';
    }
  } catch (e) {}
}

/**
 * Renders HTML for an array of jobs with pure Table/Card layout & pagination.
 * @param {Array<Object>} jobs - List of filtered and sorted job objects
 * @returns {string} HTML markup
 */
function renderJobsListHtml(jobs) {
  if (!jobs || jobs.length === 0) {
    const search = appState.search || '';
    if (search) {
      return `
        <div class="empty-state">
          <div class="empty-state-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          </div>
          <div class="empty-state-title">No Matching Opportunities Found</div>
          <div class="empty-state-desc">
            No opportunities matched your search "<strong>${escapeHtml(search)}</strong>".
          </div>
          <button class="btn btn-secondary btn-sm" data-action="clear-search" style="margin-top:8px;">
            Clear Search
          </button>
        </div>
      `;
    }
    if (appState.filter === 'applied') {
      return `
        <div class="empty-state">
          <div class="empty-state-icon" style="background:var(--primary-light, #eff6ff); color:var(--primary, #4f46e5);">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </div>
          <div class="empty-state-title">No Applications Tracked Yet</div>
          <div class="empty-state-desc">
            When you apply for roles, mark them as <strong>Applied</strong> using the stage selector on each job card. Job Hunter will automatically track your follow-up timeline and trigger smart outreach alerts!
          </div>
          <button class="btn btn-secondary btn-sm" data-action="set-filter" data-filter="all" style="margin-top:8px;">
            View All Opportunities
          </button>
        </div>
      `;
    }
    return `
      <div class="empty-state">
        <div class="empty-state-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
        </div>
        <div class="empty-state-title">No Opportunities in This View</div>
        <div class="empty-state-desc">
          No jobs currently match this view filter.
        </div>
        <button class="btn btn-secondary btn-sm" data-action="reset-filters-and-search" style="margin-top:8px;">
          Reset Filters &amp; Search
        </button>
      </div>
    `;
  }
  const totalJobs = jobs.length;
  const pageSize = appState.pageSize || 10;
  const totalPages = Math.ceil(totalJobs / pageSize) || 1;

  if (!appState.page || appState.page < 1) appState.page = 1;
  if (appState.page > totalPages) appState.page = totalPages;

  const startIdx = (appState.page - 1) * pageSize;
  const endIdx = Math.min(startIdx + pageSize, totalJobs);
  const pagedSlice = jobs.slice(startIdx, endIdx);

  const cardsHtml = pagedSlice.map(j => renderJobCardHtml(j, false)).join('');
  const paginationHtml = renderPaginationHtml(totalJobs, startIdx, endIdx, totalPages);

  const cloudBannerHtml = appState.pipelineRunning ? `
    <div class="cloud-radar-banner" role="status" aria-live="polite">
      <div class="cloud-radar-spinner-wrap">
        <span class="spinner cloud-radar-spinner"></span>
      </div>
      <div class="cloud-radar-info">
        <div class="cloud-radar-title">Autonomous Cloud Radar Active (GitHub Actions)</div>
        <div class="cloud-radar-sub">Scouting 114+ ATS company boards across 10,000+ job listings in the cloud. New matching roles will automatically sync upon completion (~1–2 minutes).</div>
      </div>
    </div>
  ` : '';

  return `
    ${cloudBannerHtml}
    <div class="jobs-table-container">
      ${cardsHtml}
    </div>
    ${paginationHtml}
  `;
}

// Supabase Authentication Global State
let supabaseClient = null;
let currentAuthSession = null;
let authConfig = {
  auth_required: false,
  supabase_url: '',
  supabase_anon_key: ''
};
let sessionRefreshInFlight = null;

// Proactively ensure valid, unexpired Supabase session token
async function ensureFreshSession() {
  if (!supabaseClient) return currentAuthSession;

  const nowSec = Math.floor(Date.now() / 1000);
  const expiresAt = currentAuthSession?.expires_at || 0;
  // If no session or token is expiring within 90 seconds, perform proactive refresh
  const needsRefresh = !currentAuthSession || (expiresAt > 0 && expiresAt - nowSec < 90);

  if (!needsRefresh) {
    return currentAuthSession;
  }

  if (sessionRefreshInFlight) {
    return await sessionRefreshInFlight;
  }

  sessionRefreshInFlight = (async () => {
    try {
      if (currentAuthSession) {
        const { data, error } = await supabaseClient.auth.refreshSession();
        if (!error && data?.session) {
          currentAuthSession = data.session;
          return currentAuthSession;
        }
      }
      const { data } = await supabaseClient.auth.getSession();
      if (data?.session) {
        currentAuthSession = data.session;
      }
    } catch (e) {
      console.warn('Proactive session refresh notice:', e);
    } finally {
      sessionRefreshInFlight = null;
    }
    return currentAuthSession;
  })();

  return await sessionRefreshInFlight;
}

// Central Authentication & Utility Access Guard
function checkAuthOrRedirect(actionName = 'access this utility') {
  if (authConfig.auth_required && !currentAuthSession) {
    setAppView('landing');
    openAuthModal('signin');
    showToast(`Please sign in to ${actionName}.`, 'info', 3500);
    return false;
  }
  return true;
}

// Authenticated Fetch Wrapper with Proactive Token Refresh & Silent Retry
async function authFetch(url, options = {}) {
  const opts = { ...options };
  const headers = new Headers(opts.headers || {});
  const method = (opts.method || 'GET').toUpperCase();
  const isMutation = !['GET', 'HEAD', 'OPTIONS'].includes(method);
  const requestKey = isMutation
    ? `${method}:${url}:${typeof opts.body === 'string' ? opts.body : 'form-data'}`
    : null;

  if (requestKey && inFlightMutationKeys.has(requestKey)) {
    return new Response(JSON.stringify({
      status: 'busy',
      message: 'This action is already being submitted. Please wait for it to finish.'
    }), {
      status: 409,
      headers: { 'Content-Type': 'application/json' }
    });
  }
  if (requestKey) inFlightMutationKeys.add(requestKey);

  // Proactively ensure valid token before dispatching request
  if (supabaseClient) {
    await ensureFreshSession();
  }

  if (currentAuthSession && currentAuthSession.access_token) {
    headers.set('Authorization', `Bearer ${currentAuthSession.access_token}`);
  }

  opts.headers = headers;

  try {
    let res = await fetch(url, opts);

    // If 401 received, attempt silent token refresh once and retry before declaring session expired
    if (res.status === 401 && authConfig.auth_required && supabaseClient && currentAuthSession) {
      console.warn('Received 401; attempting silent session refresh before invalidation...');
      try {
        const { data, error } = await supabaseClient.auth.refreshSession();
        if (!error && data?.session?.access_token) {
          currentAuthSession = data.session;
          headers.set('Authorization', `Bearer ${currentAuthSession.access_token}`);
          opts.headers = headers;
          // Retry the failed request once with the refreshed token
          res = await fetch(url, opts);
        }
      } catch (refreshErr) {
        console.warn('Silent session refresh retry error:', refreshErr);
      }

      // If still 401 after retry, then prompt re-authentication
      if (res.status === 401 && currentAuthSession) {
        console.warn('Session truly expired or revoked (401). Prompting re-authentication.');
        currentAuthSession = null;
        stopHeartbeat();
        setAppView('landing');
        openAuthModal('signin');
        setAuthFeedback('Your secure session has expired. Please sign in again.', 'error');
      }
    }

    return res;
  } catch (err) {
    throw err;
  } finally {
    if (requestKey) inFlightMutationKeys.delete(requestKey);
  }
}

let jobsAbortController = null;
let heartbeatIntervalId = null;
let searchDebounceTimer = null;
const copyTimeoutMap = new Map();
const activeToasts = [];
const inFlightMutationKeys = new Set();
const inFlightJobActions = new Set();

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

    if (appState.locationFilter && appState.locationFilter !== 'all') {
      url.searchParams.set('loc', appState.locationFilter);
    } else {
      url.searchParams.delete('loc');
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
  const countInterviewing = document.getElementById('count-interviewing');
  const countOffer = document.getElementById('count-offer');
  const countUnapplied = document.getElementById('count-unapplied');

  if (countAll) countAll.innerText = stats.tracked ?? 0;
  if (countShortlisted) countShortlisted.innerText = stats.shortlisted ?? 0;
  if (countApplied) countApplied.innerText = stats.applied ?? 0;
  if (countInterviewing) countInterviewing.innerText = stats.stages?.interviewing ?? 0;
  if (countOffer) countOffer.innerText = stats.stages?.offer ?? 0;
  if (countUnapplied) countUnapplied.innerText = stats.unapplied ?? 0;

  Storage.set(localStorage, STORAGE_KEYS.CACHED_STATS, {
    stats: stats,
    timestamp: Date.now()
  });
}

// Master Zero-Refresh Sync Engine: Checks version and reconciles data
async function syncDashboard(force = false) {
  if (!appState.authInitialized) return;
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
        if (data.pipeline.running && !appState.isCloudPollerActive) {
          startCloudPoller(data.pipeline.dispatched_at);
        }
      }

      if (data.user_profile) {
        activeProfileData = data.user_profile;
        renderCandidateSummary(data.user_profile);
        checkAndPromptOnboarding(data.user_profile);
      }

      // If version changed or force reload requested, update jobs & digest
      if (hasVersionChanged || force) {
        await fetchAndRenderJobs(false);
        refreshDigest(true);
      }

      if (!appState.pipelineRunning && (!data.pipeline || !data.pipeline.running)) {
        setSyncStatus('synced');
      }
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

let cloudPollerTimer = null;

// Persistent Cloud Pipeline Poller (GitHub Actions)
// Guarantees loading indicator stays active uninterrupted until GitHub Actions returns an error or an answer
function startCloudPoller(dispatchedAt = null) {
  if (dispatchedAt) {
    appState.cloudDispatchedAt = Number(dispatchedAt);
    try {
      sessionStorage.setItem('jobhunt_active_cloud_run', JSON.stringify({ dispatched_at: appState.cloudDispatchedAt }));
    } catch (_) {}
  } else if (!appState.cloudDispatchedAt) {
    try {
      const saved = JSON.parse(sessionStorage.getItem('jobhunt_active_cloud_run') || '{}');
      if (saved.dispatched_at && (Date.now() / 1000 - saved.dispatched_at) < 1200) {
        appState.cloudDispatchedAt = Number(saved.dispatched_at);
      }
    } catch (_) {}
  }

  appState.pipelineRunning = true;
  appState.isCloudPollerActive = true;

  const btn = document.getElementById('btn-run');
  const spinner = document.getElementById('run-spinner');
  const text = document.getElementById('run-text');

  if (btn) {
    btn.disabled = true;
    btn.classList.add('btn-inactive');
  }
  if (spinner) spinner.style.display = 'inline-block';
  if (text) text.innerText = 'Cloud Radar Running (GitHub Actions)...';
  setSyncStatus('syncing', 'Radar: Cloud Scan Active (GitHub Actions)');

  if (cloudPollerTimer) {
    clearTimeout(cloudPollerTimer);
    cloudPollerTimer = null;
  }

  let pollCount = 0;
  const poll = async () => {
    pollCount++;
    try {
      const q = appState.cloudDispatchedAt ? `?dispatched_at=${encodeURIComponent(appState.cloudDispatchedAt)}` : '';
      const syncRes = await authFetch(`/api/sync${q}`, { cache: 'no-store' });
      const syncData = await parseJsonResponse(syncRes);

      if (syncData && syncData.status === 'success') {
        const pipeline = syncData.pipeline;
        renderMetrics(syncData.stats);

        if (pipeline) {
          const isCompleted = pipeline.step === 'completed' && !pipeline.running;
          const isError = pipeline.step === 'error' && !pipeline.running;

          // Loading indicator stops ONLY when an answer or error is returned
          if (isCompleted || isError) {
            appState.pipelineRunning = false;
            appState.isCloudPollerActive = false;
            appState.cloudDispatchedAt = null;
            try { sessionStorage.removeItem('jobhunt_active_cloud_run'); } catch (_) {}

            if (isCompleted) {
              showToast('Autonomous Cloud Radar completed! Results synchronized.', 'success', 4000);
              await fetchAndRenderJobs(false);
              refreshDigest(true);
              broadcastSync('STATE_MUTATED');
            } else {
              showToast(pipeline.message || 'Cloud Radar encountered an error', 'error');
            }
            updatePipelineConsole(pipeline);
            updateJobSearchButtonState();
            setSyncStatus('synced');
            return;
          } else {
            updatePipelineConsole(pipeline);
          }
        }
      }
    } catch (e) {
      console.warn('Cloud radar poll check:', e);
    }

    if (appState.pipelineRunning && pollCount < 240) {
      cloudPollerTimer = setTimeout(poll, 5000);
    } else if (pollCount >= 240) {
      appState.pipelineRunning = false;
      appState.isCloudPollerActive = false;
      appState.cloudDispatchedAt = null;
      try { sessionStorage.removeItem('jobhunt_active_cloud_run'); } catch (_) {}
      showToast('Cloud Radar polling reached maximum timeout (20 minutes).', 'error');
      updateJobSearchButtonState();
      setSyncStatus('synced');
      await fetchAndRenderJobs(false);
    }
  };

  cloudPollerTimer = setTimeout(poll, 3000);
}

// Live Pipeline Console & Button State Updater
function updatePipelineConsole(pipeline) {
  const btn = document.getElementById('btn-run');
  const spinner = document.getElementById('run-spinner');
  const text = document.getElementById('run-text');
  const consoleBox = document.getElementById('run-console');
  const mainConsole = document.getElementById('main-run-console');

  if (!pipeline) {
    if (!appState.pipelineRunning && spinner) spinner.style.display = 'none';
    updateJobSearchButtonState();
    return;
  }

  if (pipeline.running) {
    const wasRunning = appState.pipelineRunning;
    appState.pipelineRunning = true;
    if (btn) {
      btn.disabled = true;
      btn.classList.add('btn-inactive');
    }
    if (spinner) spinner.style.display = 'inline-block';
    const isCloud = pipeline.mode === 'github_actions' || Boolean(pipeline.dispatched_at) || (pipeline.message && (pipeline.message.includes('GitHub Actions') || pipeline.message.includes('cloud')));
    if (text) text.innerText = isCloud ? 'Cloud Radar Running (GitHub Actions)...' : 'Hunting Jobs...';
    if (consoleBox && pipeline.message) {
      consoleBox.innerText = `Scanning in progress...\n${pipeline.message}`;
    }
    if (mainConsole && pipeline.message) {
      mainConsole.innerText = pipeline.message;
    }
    setSyncStatus('syncing', isCloud ? 'Radar: Cloud Scan Active (GitHub Actions)' : 'Radar: Scanning ATS...');
    if (!wasRunning) {
      fetchAndRenderJobs(false);
    }
  } else {
    // If the candidate initiated an active cloud dispatch, do NOT stop loading on premature idle states
    if (appState.cloudDispatchedAt && pipeline.step !== 'completed' && pipeline.step !== 'error') {
      return;
    }

    const wasRunning = appState.pipelineRunning;
    appState.pipelineRunning = false;
    appState.cloudDispatchedAt = null;
    appState.isCloudPollerActive = false;
    try { sessionStorage.removeItem('jobhunt_active_cloud_run'); } catch (_) {}

    if (spinner) spinner.style.display = 'none';
    if (text) text.innerText = 'Run Job Hunt Now';
    if (consoleBox && pipeline.message) {
      if (pipeline.step === 'error') {
        consoleBox.innerText = `Error: ${pipeline.message}`;
      } else {
        consoleBox.innerText = pipeline.message;
      }
    }
    updateJobSearchButtonState();
    setSyncStatus('synced');

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
    if (spinner) spinner.style.display = 'inline-block';
    if (text && (appState.cloudDispatchedAt || appState.isCloudPollerActive)) {
      text.innerText = 'Cloud Radar Running (GitHub Actions)...';
    }
    return;
  }

  const profile = activeProfileData || {};
  const isFilled = isCandidateProfileFilled(profile);

  if (!isFilled) {
    btn.disabled = true;
    btn.classList.add('btn-inactive');
    btn.setAttribute('aria-disabled', 'true');
    
    const missing = [];
    if (!profile.name || !profile.name.trim()) missing.push("Candidate Name");
    const hasSkills = Array.isArray(profile.skills) && profile.skills.length > 0;
    if (!hasSkills) missing.push("Skills");
    const hasTargets = Array.isArray(profile.target_keywords) && profile.target_keywords.length > 0;
    if (!hasTargets) missing.push("Target Job Titles");

    btn.title = `Profile incomplete. Missing: ${missing.join(', ')}`;
    if (spinner) spinner.style.display = 'none';
    if (text) text.innerText = 'Run Job Hunt Now';
    if (consoleBox) {
      consoleBox.innerText = `Radar setup incomplete: please configure ${missing.join(', ')} in Profile Settings to activate scanning.`;
    }
  } else {
    btn.disabled = false;
    btn.classList.remove('btn-inactive');
    btn.removeAttribute('aria-disabled');
    btn.title = 'Click to trigger job search across target ATS endpoints';
    if (spinner) spinner.style.display = 'none';
    if (text) text.innerText = 'Run Job Hunt Now';
    if (consoleBox && (consoleBox.innerText.includes('Radar setup incomplete') || consoleBox.innerText.includes('Candidate radar incomplete') || consoleBox.innerText.includes('System ready'))) {
      consoleBox.innerText = "System ready. Click 'Run Job Hunt Now' to start scanning target ATS endpoints.";
    }
  }
}

// Manual Sync Button Trigger
async function manualSync() {
  if (!checkAuthOrRedirect('synchronize dashboard data')) return;
  setSyncStatus('syncing', 'Syncing now...');
  await syncDashboard(true);
  showToast('Dashboard is fully synchronized!', 'success', 2000);
}

// Tab Switching with URL & LocalStorage Persistence
function switchTab(tab, fetchData = true) {
  if (fetchData && !checkAuthOrRedirect('access dashboard tabs')) {
    return;
  }

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
      initWorkflowGuideState();
      fetchAndRenderJobs(false);
    }
  } else if (tab === 'tracker') {
    initWorkflowGuideState();
  }
}

// Filter Pills with State Persistence
function setFilter(filter) {
  appState.filter = filter;
  appState.page = 1;
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
  const lowerUrl = url.toLowerCase();
  if (lowerUrl.startsWith('javascript:') || lowerUrl.startsWith('data:') || lowerUrl.startsWith('vbscript:')) {
    url = '';
  }
  if (url && url !== '#') {
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

// Highlight matching search query in strings safely without splitting HTML entities
function highlightText(text, query) {
  if (!text) return '';
  const escapedText = escapeHtml(text);
  if (!query || !query.trim()) return escapedText;

  const escapedQuery = escapeHtml(query.trim()).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  if (!escapedQuery) return escapedText;

  const regex = new RegExp(`(${escapedQuery})(?![^&]*;)`, 'gi');
  return escapedText.replace(regex, '<span class="highlight-match">$1</span>');
}

// Render HTML for single job item card
function renderJobCardHtml(j, isNew = false) {
  const score = j.score != null ? Number(j.score).toFixed(1) : 'N/A';
  const scoreClass = j.score >= 8.5 ? 'score-high' : (j.score >= 7.0 ? 'score-mid' : 'score-low');
  const stage = j.application_stage || (j.applied ? 'applied' : 'to_apply');
  const isApplied = Boolean(j.applied || stage === 'applied' || stage === 'interviewing' || stage === 'offer' || stage === 'rejected');
  const hasDraft = j.draft && (j.draft.cover_note || j.draft.fit_summary || j.draft.cold_outreach || j.draft.referral_request);
  const applyUrl = resolveJobUrl(j);
  const searchQuery = appState.search;
  const followupInfo = getElapsedAppliedInfo(j);
  const isIndia = isIndiaJob(j);
  const salaryBadge = formatSalaryBadge(j);

  return `
    <div class="job-item ${isNew ? 'job-item-new' : ''}" id="job-card-${escapeHtml(j.job_id)}">
      <div class="job-meta">
        <div class="job-header-row">
          <span class="job-title">${highlightText(j.title, searchQuery)}</span>
          <span class="ats-tag" title="Hosted on ${escapeHtml(j.ats || 'ATS')} public career API">${escapeHtml(j.ats || 'ats')}</span>
          ${isNew ? '<span class="badge-live-sync">New Discovery</span>' : ''}
              ${followupInfo ? `<button type="button" class="btn-followup-badge" data-action="open-followup-modal" data-job-id="${escapeHtml(j.job_id)}" title="Generate tailored follow-up note">${escapeHtml(followupInfo.badgeText)}</button>` : ''}
        </div>
        <div class="job-sub">
          <span class="job-sub-company"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>${highlightText(j.company, searchQuery)}</span>
          <span class="job-sub-location"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M12 2a8 8 0 0 0-8 8c0 5.25 8 12 8 12s8-6.75 8-12a8 8 0 0 0-8-8z"></path><circle cx="12" cy="10" r="3"></circle></svg>${highlightText(j.location || 'Remote/Unspecified', searchQuery)}</span>
          ${isIndia ? '<span class="badge-india-pill">🇮🇳 India</span>' : ''}
          ${salaryBadge}
          ${j.notes ? `<span class="badge-notes-pill" title="Private notes: ${escapeHtml(j.notes)}"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:2px; flex-shrink: 0;"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>Notes</span>` : ''}
          <span class="job-sub-id">(${escapeHtml(j.job_id)})</span>
        </div>
        ${j.reason ? `<div class="job-reason">${escapeHtml(j.reason)}</div>` : ''}
      </div>
      <div class="job-actions">
        <div class="job-score-row">
          <span class="score-badge ${scoreClass}" title="AI Candidate Match Score (${score}/10) — 8.5+ High Fit, 7.0–8.4 Moderate, <7.0 Low">${score}</span>
          <select class="job-stage-select" aria-label="Application Stage" title="Update application stage (To Apply, Applied, Interviewing, Offer, Archived)" data-change-action="update-job-stage" data-job-id="${escapeHtml(j.job_id)}">
            <option value="to_apply" ${stage === 'to_apply' ? 'selected' : ''}>To Apply</option>
            <option value="applied" ${stage === 'applied' ? 'selected' : ''}>Applied</option>
            <option value="interviewing" ${stage === 'interviewing' ? 'selected' : ''}>Interviewing</option>
            <option value="offer" ${stage === 'offer' ? 'selected' : ''}>Offer</option>
            <option value="rejected" ${stage === 'rejected' ? 'selected' : ''}>Archived</option>
          </select>
        </div>
        <div class="job-action-btn-row">
          ${isApplied
            ? `<button class="btn btn-secondary btn-sm btn-applied" id="btn-app-${escapeHtml(j.job_id)}" title="Application submitted — click to unmark" data-action="toggle-applied" data-job-id="${escapeHtml(j.job_id)}" data-mode="unmark"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><polyline points="20 6 9 17 4 12"></polyline></svg><span>Applied</span></button>`
            : `<button class="btn btn-secondary btn-sm" id="btn-app-${escapeHtml(j.job_id)}" title="Mark as applied to activate follow-up tracking" data-action="toggle-applied" data-job-id="${escapeHtml(j.job_id)}" data-mode="mark"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg><span>Mark Applied</span></button>`
          }
          <button class="btn btn-secondary btn-sm btn-danger" title="Delete job entry" data-action="delete-job" data-job-id="${escapeHtml(j.job_id)}"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg><span>Delete</span></button>
        </div>
        <div class="job-action-btn-row">
          <button class="btn btn-secondary btn-sm" title="${hasDraft ? 'View tailored cover note, cold outreach DM, matching bullets & questions' : 'View opportunity details and candidate notes'}" data-action="open-kit-modal" data-job-id="${escapeHtml(j.job_id)}"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg><span>${hasDraft ? 'Inspect Kit' : 'Kit & Notes'}</span></button>
          <a href="${escapeHtml(applyUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" title="Open original job posting directly on company career portal" style="text-decoration:none;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg><span>Open Link</span></a>
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
  const locFilterSelect = document.getElementById('tracker-location-filter') || document.getElementById('tracker-location-select');

  appState.search = searchInput ? searchInput.value.trim() : '';
  appState.ats = atsSelect ? atsSelect.value : 'all';
  appState.sort = sortSelect ? sortSelect.value : 'date';
  if (locFilterSelect) appState.locationFilter = locFilterSelect.value || 'all';

  Storage.set(sessionStorage, STORAGE_KEYS.SEARCH_QUERY, appState.search);
  Storage.set(localStorage, STORAGE_KEYS.ATS_FILTER, appState.ats);
  Storage.set(localStorage, STORAGE_KEYS.SORT_BY, appState.sort);
  Storage.set(localStorage, STORAGE_KEYS.LOCATION_FILTER, appState.locationFilter);
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
             <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>
          </div>
          <h3>Authentication Required</h3>
          <p>Sign in with your Supabase account to access your personal AI job match radar and pipeline controls.</p>
          <button class="btn btn-primary" data-action="open-auth-modal" data-mode="signin" style="margin-top: 14px;" type="button">
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
                <div class="empty-state-title">Autonomous Cloud Radar in Progress (GitHub Actions)...</div>
                <div class="empty-state-desc">
                  Scanning 114+ ATS company boards across 10,000+ job listings in the cloud and matching roles to your candidate profile with Gemini 3.5 Flash. Please wait (~1–2 minutes)!
                </div>
                <div class="console" id="main-run-console" style="margin-top: 15px; width: 100%; text-align: left; max-height: 100px; overflow-y: auto; white-space: pre-wrap;">Autonomous cloud runner active... Dispatching worker nodes and querying company boards...</div>
              </div>
            `;
          } else {
            const profileFilled = isCandidateProfileFilled(activeProfileData);
            if (!profileFilled) {
              container.innerHTML = `
                <div class="empty-state">
                  <div class="empty-state-icon" style="background:#fff1f2; color:#e11d48;">
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="10" r="3"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                  </div>
                  <div class="empty-state-title">Candidate Profile Required</div>
                  <div class="empty-state-desc">
                    Please fill out your candidate profile info (Name, Target Roles, and Skills) before running an autonomous job hunt scan across 114+ company boards.
                  </div>
                  <button class="btn btn-primary" data-action="open-profile-modal" style="margin-top:10px; gap:8px;">
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
                    No opportunities have been scanned for your profile yet. Click below to launch your first autonomous job hunt scan across 114+ company boards!
                  </div>
                  <button class="btn btn-primary" data-action="run-pipeline" style="margin-top:10px; gap:8px;">
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
              <button class="btn btn-secondary btn-sm" data-action="reset-filters-and-search" style="margin-top:6px;">
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
    } else if (['interviewing', 'offer'].includes(appState.filter)) {
      filteredJobs = filteredJobs.filter(j => (j.stage || '') === appState.filter);
    }

    if (appState.locationFilter === 'india') {
      filteredJobs = filteredJobs.filter(j => isIndiaJob(j));
    } else if (appState.locationFilter === 'remote') {
      filteredJobs = filteredJobs.filter(j => isRemoteJob(j));
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

function handleLocationFilterChange(val) {
  appState.locationFilter = val || 'all';
  Storage.set(localStorage, STORAGE_KEYS.LOCATION_FILTER, appState.locationFilter);
  syncUrlState();
  fetchAndRenderJobs(true);
}

function resetFiltersAndSearch() {
  const searchInput = document.getElementById('tracker-search-input');
  const atsSelect = document.getElementById('tracker-ats-select');
  const locSelect = document.getElementById('tracker-location-filter') || document.getElementById('tracker-location-select');
  const clearBtn = document.getElementById('search-clear-btn');

  if (searchInput) searchInput.value = '';
  if (clearBtn) clearBtn.style.display = 'none';
  if (atsSelect) atsSelect.value = 'all';
  if (locSelect) locSelect.value = 'all';

  appState.search = '';
  appState.ats = 'all';
  appState.locationFilter = 'all';
  Storage.set(localStorage, STORAGE_KEYS.LOCATION_FILTER, 'all');
  appState.page = 1;
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
  appState.page = 1;
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
  appState.page = 1;
  fetchAndRenderJobs(false);
}

function applySearchFilter(query) {
  const cleanQuery = (query || '').trim();
  switchTab('tracker');
  const input = document.getElementById('tracker-search-input');
  const clearBtn = document.getElementById('search-clear-btn');
  if (input) {
    input.value = cleanQuery;
    input.focus();
  }
  if (clearBtn) {
    clearBtn.style.display = cleanQuery ? 'flex' : 'none';
  }
  appState.search = cleanQuery;
  appState.page = 1;
  fetchAndRenderJobs(false);
}

// Robust cross-browser clipboard copy helper with legacy fallback
function copyTextSafely(text) {
  if (navigator.clipboard && window.isSecureContext && typeof navigator.clipboard.writeText === 'function') {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    try {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      textArea.setAttribute('readonly', '');
      textArea.style.opacity = '0';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      const successful = document.execCommand('copy');
      document.body.removeChild(textArea);
      if (successful) {
        resolve();
      } else {
        reject(new Error('Browser execCommand copy rejected'));
      }
    } catch (err) {
      reject(err);
    }
  });
}

// Copy section text helper
function copySectionText(textId, btnId) {
  const el = document.getElementById(textId);
  if (!el) return;
  const txt = el.innerText;
  
  copyTextSafely(txt).then(() => {
    const btn = document.getElementById(btnId);
    if (!btn) return;

    const type = btn.getAttribute('data-original');
    let originalHtml = '';
    if (type === 'outreach') {
      originalHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Outreach</span>`;
    } else if (type === 'referral') {
      originalHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Referral Note</span>`;
    } else if (type === 'cover') {
      originalHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Note</span>`;
    } else if (type === 'followup') {
      originalHtml = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 4px;"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Follow-Up</span>`;
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
  btn.setAttribute('data-action', 'toggle-modal-applied');
  btn.setAttribute('data-mode', isApplied ? 'unmark' : 'mark');
}

function toggleModalAppliedDirect() {
  const btn = document.getElementById('modal-applied-toggle-btn');
  if (!btn) return;
  const jobId = btn.getAttribute('data-job-id');
  const action = btn.getAttribute('data-mode') || 'mark';
  if (jobId) {
    toggleAppliedDirect(jobId, action);
  }
}

function openKitModal(jobId) {
  if (!checkAuthOrRedirect('inspect application kit')) return;
  const j = appState.jobsMap[jobId];
  if (!j) return;

  appState.activeKitId = jobId;
  Storage.set(sessionStorage, STORAGE_KEYS.ACTIVE_KIT, jobId);
  syncUrlState();

  const titleEl = document.getElementById('modal-job-title');
  const metaEl = document.getElementById('modal-job-meta');
  const bodyEl = document.getElementById('modal-body');

  if (titleEl) titleEl.innerText = j.title || 'Job Application Kit';
  if (metaEl) metaEl.innerText = `${j.company} · ${j.location || 'Remote/Unspecified'}`;

  updateModalAppliedButton(j);

  const d = j.draft || {};
  let html = '';

  const isIndia = isIndiaJob(j);
  const salaryBadge = formatSalaryBadge(j);
  const notice = activeProfileData?.notice_period;
  const expCtc = activeProfileData?.expected_ctc_lpa;

  html += `
    <div class="kit-context-strip">
      ${isIndia ? '<span class="badge-india-pill">🇮🇳 India-Based Opportunity</span>' : '<span style="color:var(--text-muted); font-size:12px; font-weight:600;">🌐 Global Opportunity</span>'}
      ${salaryBadge}
      ${notice ? `<span class="kit-meta-item"><strong>Notice:</strong> ${escapeHtml(notice.replace(/_/g, ' '))}</span>` : ''}
      ${expCtc != null && expCtc !== '' ? `<span class="kit-meta-item"><strong>Expected CTC:</strong> ₹${escapeHtml(String(expCtc))} LPA</span>` : ''}
    </div>
  `;

  const hasContent = Boolean(
    d.fit_summary ||
    d.cover_note ||
    d.cold_outreach ||
    d.referral_request ||
    (d.tailored_bullets && d.tailored_bullets.length) ||
    (d.followup && d.followup.email_body)
  );

  if (!hasContent) {
    html += `
      <div class="kit-section" style="padding: 18px 14px; background: var(--bg-subtle, #f8fafc); border-radius: 8px; border: 1px dashed var(--border, #e2e8f0); margin-bottom: 16px;">
        <div class="kit-label" style="margin-bottom: 6px;">Opportunity Details</div>
        <p style="font-size: 13px; line-height: 1.6; color: var(--text-body); margin: 0;">
          This role at <strong>${escapeHtml(j.company)}</strong> is tracked in your pipeline. Review details or open the official application posting below.
        </p>
        ${j.reason ? `<div class="job-reason" style="margin-top: 10px;">${escapeHtml(j.reason)}</div>` : ''}
      </div>
    `;
  } else if (d.fit_summary) {
    html += `<div class="kit-section"><div class="kit-label">Why It Fits</div><p style="font-size:13px; line-height:1.6; color:var(--text-body);">${escapeHtml(d.fit_summary)}</p></div>`;
  }

  const referralLabelSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Referral Note</span>`;
  const outreachLabelSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Outreach</span>`;
  const coverLabelSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Note</span>`;
  const followupLabelSvg = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg><span>Copy Follow-Up</span>`;

  if (d.referral_request) {
    html += `
      <div class="kit-section">
        <div class="kit-label">
          <span>LinkedIn Referral Request (&lt;60 words)</span>
          <button class="copy-btn" id="btn-copy-referral" data-original="referral" data-action="copy-section" data-target="referral-text" data-btn="btn-copy-referral">${referralLabelSvg}</button>
        </div>
        <div class="cover-box" id="referral-text" style="background:#f0fdf4; color:#166534; border-color:#bbf7d0; font-family:var(--font-mono, monospace); font-size:12.5px;">${escapeHtml(d.referral_request)}</div>
      </div>`;
  }

  if (d.followup && d.followup.email_body) {
    html += `
      <div class="kit-section">
        <div class="kit-label">
          <span>Smart Follow-Up Email Outreach</span>
          <button class="copy-btn" id="btn-copy-followup" data-original="followup" data-action="copy-section" data-target="followup-text" data-btn="btn-copy-followup">${followupLabelSvg}</button>
        </div>
        <div class="cover-box" id="followup-text" style="background:var(--accent-light, #f0f9ff); border-color:var(--accent, #0284c7);">${escapeHtml(d.followup.email_body)}</div>
      </div>`;
  }

  if (d.cold_outreach) {
    html += `
      <div class="kit-section">
        <div class="kit-label">
          <span>Cold Outreach (&lt;80 words)</span>
          <button class="copy-btn" id="btn-copy-outreach" data-original="outreach" data-action="copy-section" data-target="outreach-text" data-btn="btn-copy-outreach">${outreachLabelSvg}</button>
        </div>
        <div class="cover-box" id="outreach-text" style="background:var(--success-bg); color:var(--success-hover); border-color:var(--success-border); font-family:var(--font-mono, monospace);">${escapeHtml(d.cold_outreach)}</div>
      </div>`;
  }

  if (d.cover_note) {
    html += `
      <div class="kit-section">
        <div class="kit-label">
          <span>Tailored Cover Note</span>
          <button class="copy-btn" id="btn-copy-cover" data-original="cover" data-action="copy-section" data-target="cover-text" data-btn="btn-copy-cover">${coverLabelSvg}</button>
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

  const notesVal = j.notes || '';
  html += `
    <div class="kit-section" style="margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--border);">
      <div class="kit-label" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
        <span>Private Candidate Notes</span>
        <button class="btn btn-secondary btn-sm" id="btn-save-notes-${escapeHtml(j.job_id)}" data-action="save-job-notes" data-job-id="${escapeHtml(j.job_id)}" style="font-size:11px; padding:3px 10px; cursor:pointer;">
          Save Notes
        </button>
      </div>
      <textarea id="modal-candidate-notes-${escapeHtml(j.job_id)}" class="form-control" rows="3" placeholder="Add interview dates, recruiter contacts, salary discussions, or personal notes..." style="width:100%; box-sizing:border-box; font-size:12.5px; line-height:1.5; resize:vertical; border-radius:6px; border:1px solid var(--border); padding:8px 10px; background:var(--bg-subtle, #f8fafc); color:var(--text-body); font-family:inherit;">${escapeHtml(notesVal)}</textarea>
    </div>
  `;

  const modalApplyUrl = resolveJobUrl(j);
  html += `<div style="margin-top:16px; display:flex; justify-content:flex-end; width:100%;"><a href="${escapeHtml(modalApplyUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="display:inline-flex; align-items:center; justify-content:center; text-decoration:none;"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px; flex-shrink: 0;"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg><span>Open Posting Page</span></a></div>`;

  if (bodyEl) bodyEl.innerHTML = html;
  const modalEl = document.getElementById('kit-modal');
  if (modalEl) {
    modalEl.classList.add('active');
    activateModalFocus(modalEl, modalEl.querySelector('.modal-close'));
  }
}

function closeKitModal() {
  const modalEl = document.getElementById('kit-modal');
  if (modalEl) modalEl.classList.remove('active');

  const bodyEl = document.getElementById('modal-body');
  if (bodyEl) bodyEl.innerHTML = '';

  appState.activeKitId = null;
  Storage.remove(sessionStorage, STORAGE_KEYS.ACTIVE_KIT);
  syncUrlState();
  deactivateModalFocus();
}

async function saveJobNotes(jobId) {
  if (!checkAuthOrRedirect('save candidate notes')) return;
  const textarea = document.getElementById(`modal-candidate-notes-${jobId}`);
  if (!textarea) return;
  const btn = document.getElementById(`btn-save-notes-${jobId}`);
  const originalText = btn ? btn.innerText : 'Save Notes';
  const notes = textarea.value.trim();

  if (btn) {
    btn.disabled = true;
    btn.innerText = 'Saving...';
  }

  try {
    const res = await authFetch('/api/jobs/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: jobId, notes })
    });
    const data = await parseJsonResponse(res);
    if (res.ok && data.status === 'success') {
      if (appState.jobsMap[jobId]) {
        appState.jobsMap[jobId].notes = notes;
      }
      broadcastSync('STATE_MUTATED', { job_id: jobId, action: 'notes_updated' });
      showToast('Notes saved successfully', 'success', 2500);
      if (btn) btn.innerText = 'Saved!';

      const card = document.getElementById(`job-card-${jobId}`);
      if (card && appState.jobsList) {
        const container = document.getElementById('job-list-container');
        if (container) {
          container.innerHTML = renderJobsListHtml(appState.jobsList);
        }
      }

      setTimeout(() => {
        if (btn) {
          btn.innerText = originalText;
          btn.disabled = false;
        }
      }, 1500);
    } else {
      throw new Error(data.message || 'Failed to save notes');
    }
  } catch (err) {
    showToast('Failed to save notes: ' + err.message, 'error', 4000);
    if (btn) {
      btn.innerText = originalText;
      btn.disabled = false;
    }
  }
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
  const nameEl = document.getElementById('summary-candidate-name');
  const titleEl = document.getElementById('summary-candidate-title');
  const skillsContainer = document.getElementById('summary-skills-tags');
  const notifIndicator = document.getElementById('notif-badge-indicator');
  const authEmail = (currentAuthSession?.user?.email || '').trim();

  if (!profile) {
    activeProfileData = null;
    if (nameEl) {
      nameEl.innerText = authEmail || 'Email';
      nameEl.classList.add('profile-incomplete-label');
    }
    if (titleEl) {
      titleEl.innerText = 'Complete your profile to begin';
      titleEl.classList.add('profile-incomplete-label');
      titleEl.setAttribute('data-action', 'open-profile-modal');
      titleEl.removeAttribute('data-tag');
      titleEl.removeAttribute('title');
      titleEl.style.cursor = '';
    }
    if (skillsContainer) {
      skillsContainer.innerHTML = '<span class="studio-skill-tag studio-skill-placeholder">No skills yet</span>';
    }
    if (notifIndicator) {
      notifIndicator.className = 'notif-badge-off';
      notifIndicator.innerText = 'Email Alerts: Off';
    }
    updateJobSearchButtonState();
    return;
  }

  activeProfileData = { ...profile };
  Storage.set(localStorage, STORAGE_KEYS.CACHED_PROFILE, activeProfileData);

  const rawSavedName = (activeProfileData.name || '').trim();
  const savedName = (rawSavedName && rawSavedName !== 'Candidate') ? rawSavedName : '';
  const savedTitle = (activeProfileData.title || activeProfileData.current_title || '').trim();
  
  const rawSkills = Array.isArray(activeProfileData.skills) && activeProfileData.skills.length > 0
    ? activeProfileData.skills
    : (Array.isArray(activeProfileData.core_skills) ? activeProfileData.core_skills : []);
  const skillsList = rawSkills.map(s => String(s).trim()).filter(Boolean);

  if (nameEl) {
    // Privacy-first: if no explicit candidate name is saved, display user's authenticated email
    const displayEmail = authEmail || (activeProfileData.email || '').trim();
    nameEl.innerText = savedName || displayEmail || 'Email';
    nameEl.classList.toggle('profile-incomplete-label', !savedName);
  }

  if (titleEl) {
    titleEl.innerText = savedTitle || 'Complete your profile to begin';
    titleEl.classList.toggle('profile-incomplete-label', !savedTitle);
    if (savedTitle) {
      titleEl.setAttribute('data-action', 'search-tag');
      titleEl.setAttribute('data-tag', savedTitle);
      titleEl.setAttribute('title', `Filter jobs by ${savedTitle}`);
      titleEl.style.cursor = 'pointer';
    } else {
      titleEl.setAttribute('data-action', 'open-profile-modal');
      titleEl.removeAttribute('data-tag');
      titleEl.removeAttribute('title');
      titleEl.style.cursor = '';
    }
  }

  if (skillsContainer) {
    if (skillsList.length > 0) {
      skillsContainer.innerHTML = skillsList.slice(0, 10).map(s => 
        `<button type="button" class="studio-skill-tag clickable-skill-chip" data-action="search-tag" data-tag="${escapeHtml(s)}" title="Filter job board by ${escapeHtml(s)}">${escapeHtml(s)}</button>`
      ).join('');
    } else {
      skillsContainer.innerHTML = '<span class="studio-skill-tag studio-skill-placeholder">No skills yet</span>';
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
let lastParsedResumeText = '';

function isCandidateProfileFilled(profile) {
  if (!profile) return false;
  if (profile.onboarding_completed === true) return true;

  const hasName = (profile.name || '').trim().length > 0;
  const skills = Array.isArray(profile.skills) && profile.skills.length > 0
    ? profile.skills
    : (Array.isArray(profile.core_skills) ? profile.core_skills : []);
  const targets = Array.isArray(profile.target_keywords) && profile.target_keywords.length > 0
    ? profile.target_keywords
    : (Array.isArray(profile.target_titles) && profile.target_titles.length > 0 ? profile.target_titles : (profile.title ? [profile.title] : []));

  return Boolean(hasName && skills.length > 0 && targets.length > 0);
}

function isProfileIncomplete(profile) {
  return !isCandidateProfileFilled(profile);
}

function checkAndPromptOnboarding(profile) {
  // Initial setup wizard removed per user request. Profile configuration is handled on-demand via Settings modal.
  return;
}

function onboardingDismissedKey() {
  const userId = currentAuthSession?.user?.id || currentAuthSession?.user?.email || 'anonymous';
  return `onboarding_dismissed:${userId}`;
}

function openOnboardingModal() {
  openProfileModal();
}

function closeOnboardingModal(force = false) {
  const modalEl = document.getElementById('onboarding-modal');
  if (modalEl) modalEl.classList.remove('active');
  isOnboardingOpen = false;
}

// --------------------------------------------------------------------------
// Settings Modal & Preferences Manager
// --------------------------------------------------------------------------
async function openProfileModal(tab = 'resume') {
  if (!checkAuthOrRedirect('access candidate profile and radar settings')) return;
  const modalEl = document.getElementById('profile-modal');
  if (!modalEl) return;
  modalEl.classList.add('active');
  activateModalFocus(modalEl, modalEl.querySelector('.modal-close'));
  
  // Always start with Part 1 (Step 1: Resume & Text Context)
  profileWizardGoTo(1);

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

      if (nameInput) {
        const candidateName = (p.name && p.name !== 'Candidate') ? p.name.trim() : '';
        nameInput.value = candidateName;
      }
      if (resumeTextInput) resumeTextInput.value = p.resume_text || '';
      if (titleInput)    titleInput.value   = (p.title || p.current_title || '').trim();
      if (yearsInput) {
        const rawYoe = p.experience_years ?? p.years_experience;
        const numYoe = rawYoe != null && rawYoe !== '' ? Number(rawYoe) : NaN;
        yearsInput.value = (!isNaN(numYoe) && (numYoe > 0 || p.onboarding_completed === true)) ? String(rawYoe) : '';
      }
      if (eduInput)      eduInput.value     = (p.education || '').trim();
      if (skillsInput)   skillsInput.value  = Array.isArray(p.skills) ? p.skills.join(', ') : (Array.isArray(p.core_skills) ? p.core_skills.join(', ') : (typeof p.skills === 'string' ? p.skills : ''));

      // ── Step 3: Selectable Mail Mode (Default is unselected)
      if (p.email_notifications_enabled === true) {
        selectMailMode('daily');
      } else if (p.mail_mode === 'onetime') {
        selectMailMode('onetime');
      } else {
        selectMailMode('none');
      }

      if (notifEmail)  notifEmail.value    = p.notification_email || authEmail;
      if (notifScore)  notifScore.value    = (p.min_score_notification != null && p.min_score_notification !== '' && (p.onboarding_completed === true || p.email_notifications_enabled === true)) ? String(p.min_score_notification) : '';

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

      // ── Populate Section 2 fields from saved profile in a single pass
      populateSection2FromProfile(p, false);
    } else {
      const nameInput  = document.getElementById('prof-name');
      const titleInput = document.getElementById('prof-title');
      const notifEmail = document.getElementById('notif-target-email');
      const targetsInput = document.getElementById('prof-targets');
      const excludesInput= document.getElementById('prof-excludes');
      if (nameInput)  nameInput.value  = '';
      if (titleInput) titleInput.value = '';
      if (notifEmail && authEmail) notifEmail.value = authEmail;
      if (targetsInput)  targetsInput.value  = '';
      if (excludesInput) excludesInput.value = '';
      ['prof-phone', 'prof-linkedin', 'prof-github', 'prof-summary'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      selectMailMode('none');
    }
  } catch (err) {
    console.warn('Profile fetch notice:', err);
    const nameInput  = document.getElementById('prof-name');
    const titleInput = document.getElementById('prof-title');
    const notifEmail = document.getElementById('notif-target-email');
    const targetsInput = document.getElementById('prof-targets');
    const excludesInput= document.getElementById('prof-excludes');
    if (nameInput)  nameInput.value  = '';
    if (titleInput) titleInput.value = '';
    if (notifEmail && authEmail) notifEmail.value = authEmail;
    if (targetsInput)  targetsInput.value  = '';
    if (excludesInput) excludesInput.value = '';
    ['prof-phone', 'prof-linkedin', 'prof-github', 'prof-summary'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
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

// Comprehensive Section 2 Search Filters & Criteria Auto-Fill Helper
function populateSection2FromProfile(p, isAutoFill = false) {
  if (!p) return;

  // 1. Candidate Name (Privacy-first: never infer or prefill from email or OAuth metadata)
  const nameInput = document.getElementById('prof-name');
  const onbNameInput = document.getElementById('onboard-prof-name');
  const rawCandidateName = (p.name && p.name !== 'Candidate') ? p.name.trim() : '';
  const existingNameVal = nameInput ? nameInput.value.trim() : '';
  const finalName = rawCandidateName || existingNameVal || '';

  if (nameInput) nameInput.value = finalName;
  if (onbNameInput) onbNameInput.value = finalName;

  // 2. Core Skills (Support array or comma-separated string, deduplicate case-insensitively)
  const skillsInput = document.getElementById('prof-skills');
  const onbSkillsInput = document.getElementById('onboard-prof-skills');
  let rawSkills = p.skills || p.core_skills;
  let skl = [];
  if (Array.isArray(rawSkills)) {
    skl = rawSkills.map(s => String(s).trim()).filter(Boolean);
  } else if (typeof rawSkills === 'string' && rawSkills.trim()) {
    skl = rawSkills.split(',').map(s => s.trim()).filter(Boolean);
  }
  if (skl.length > 0) {
    const seenSkills = new Set();
    const dedupedSkills = [];
    for (const s of skl) {
      const lower = s.toLowerCase();
      if (!seenSkills.has(lower)) {
        seenSkills.add(lower);
        dedupedSkills.push(s);
      }
    }
    const skillsStr = dedupedSkills.join(', ');
    if (skillsInput && (isAutoFill || !skillsInput.value.trim())) skillsInput.value = skillsStr;
    if (onbSkillsInput && (isAutoFill || !onbSkillsInput.value.trim())) onbSkillsInput.value = skillsStr;
  }

  // 3. Years of Experience & Education
  const yearsInput = document.getElementById('prof-years');
  const onbYearsInput = document.getElementById('onboard-prof-years');
  if (yearsInput || onbYearsInput) {
    let yoeVal = '';
    if (p.experience_years != null || p.years_experience != null) {
      const numYoe = parseFloat(p.experience_years ?? p.years_experience);
      if (!isNaN(numYoe) && (isAutoFill || numYoe >= 0 || p.onboarding_completed === true)) {
        yoeVal = String(numYoe);
      }
    } else if (p.experience_level) {
      const expMap = { 'fresher': 0, '0-1': 1, '1-3': 2, '3-5': 4, '5+': 6 };
      if (p.experience_level in expMap) {
        yoeVal = String(expMap[p.experience_level]);
      }
    }
    if (yearsInput && (isAutoFill || yoeVal !== '' || !yearsInput.value.trim())) yearsInput.value = yoeVal;
    if (onbYearsInput && (isAutoFill || yoeVal !== '' || !onbYearsInput.value.trim())) onbYearsInput.value = yoeVal;
  }
  const eduInput = document.getElementById('prof-education');
  const onbEduInput = document.getElementById('onboard-prof-education');
  if (p.education) {
    const eduStr = p.education.trim();
    if (eduInput && (isAutoFill || !eduInput.value.trim())) eduInput.value = eduStr;
    if (onbEduInput && (isAutoFill || !onbEduInput.value.trim())) onbEduInput.value = eduStr;
  }

  // 4. Target Job Titles (Included) & Headline Title
  let rawTargets = p.target_keywords || p.target_titles;
  let targets = [];
  if (Array.isArray(rawTargets)) {
    targets = rawTargets.map(s => String(s).trim()).filter(Boolean);
  } else if (typeof rawTargets === 'string' && rawTargets.trim()) {
    targets = rawTargets.split(',').map(s => s.trim()).filter(Boolean);
  }
  const mainTitle = (p.title || p.current_title || '').trim();
  if (mainTitle && !targets.some(t => t.toLowerCase() === mainTitle.toLowerCase())) {
    targets.unshift(mainTitle);
  }
  if (targets.length === 0 && isAutoFill) {
    targets = mainTitle ? [mainTitle] : ['Professional'];
  }
  const seenTargets = new Set();
  const dedupedTargets = [];
  for (const t of targets) {
    const lower = t.toLowerCase();
    if (!seenTargets.has(lower)) {
      seenTargets.add(lower);
      dedupedTargets.push(t);
    }
  }
  const targetsStr = dedupedTargets.join(', ');
  const targetsInput = document.getElementById('prof-targets');
  const onbTargetsInput = document.getElementById('onboard-prof-targets');
  if (targetsInput && (isAutoFill || !targetsInput.value.trim())) targetsInput.value = targetsStr;
  if (onbTargetsInput && (isAutoFill || !onbTargetsInput.value.trim())) onbTargetsInput.value = targetsStr;

  const titleInput = document.getElementById('prof-title');
  const onbTitleInput = document.getElementById('onboard-prof-title');
  const chosenTitle = mainTitle || (dedupedTargets.length > 0 ? dedupedTargets[0] : (isAutoFill ? 'Professional' : ''));
  if (titleInput && (isAutoFill || !titleInput.value.trim() || mainTitle)) titleInput.value = chosenTitle;
  if (onbTitleInput && (isAutoFill || !onbTitleInput.value.trim() || mainTitle)) onbTitleInput.value = chosenTitle;

  // 5. Excluded Title Keywords
  let rawExcludes = p.exclude_keywords || p.exclude_titles || p.avoid_roles;
  let excludes = [];
  if (Array.isArray(rawExcludes)) {
    excludes = rawExcludes.map(s => String(s).trim()).filter(Boolean);
  } else if (typeof rawExcludes === 'string' && rawExcludes.trim()) {
    excludes = rawExcludes.split(',').map(s => s.trim()).filter(Boolean);
  } else if (isAutoFill) {
    excludes = [];
  }
  const seenExcludes = new Set();
  const dedupedExcludes = [];
  for (const ex of excludes) {
    const lower = ex.toLowerCase();
    if (!seenExcludes.has(lower)) {
      seenExcludes.add(lower);
      dedupedExcludes.push(ex);
    }
  }
  const excludesStr = dedupedExcludes.join(', ');
  const excludesInput = document.getElementById('prof-excludes');
  const onbExcludesInput = document.getElementById('onboard-prof-excludes');
  if (excludesInput && (isAutoFill || !excludesInput.value.trim())) excludesInput.value = excludesStr;
  if (onbExcludesInput && (isAutoFill || !onbExcludesInput.value.trim())) onbExcludesInput.value = excludesStr;

  // 6. Experience Level
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
  } else if (seniority.includes('senior') || seniority.includes('lead') || seniority.includes('staff') || seniority.includes('principal')) {
    expKey = '5+';
  } else if (seniority.includes('mid')) {
    expKey = '1-3';
  } else if (seniority.includes('intern') || seniority.includes('fresher') || seniority.includes('new-grad')) {
    expKey = 'fresher';
  } else if (years === 0 && (isAutoFill || p.onboarding_completed === true)) {
    expKey = '0-1';
  }

  ['prof-exp', 'onboard-exp'].forEach(nameAttr => {
    document.querySelectorAll(`input[name="${nameAttr}"]`).forEach(radio => {
      const isMatch = Boolean(expKey && radio.value === expKey);
      radio.checked = isMatch;
      const chip = radio.closest('.chip-radio');
      if (chip) chip.classList.toggle('active', isMatch);
    });
  });

  // 7. Job Type Preferences
  let rawJobTypes = p.job_types;
  let jobTypes = [];
  if (Array.isArray(rawJobTypes)) {
    jobTypes = rawJobTypes.map(s => String(s).trim()).filter(Boolean);
  } else if (typeof rawJobTypes === 'string' && rawJobTypes.trim()) {
    jobTypes = rawJobTypes.split(',').map(s => s.trim()).filter(Boolean);
  }
  if (jobTypes.length === 0 && isAutoFill) {
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

  // 8. Location Preference & Specific Cities Normalization
  let locPref = '';
  let citiesList = [];
  if (p.location_preference) {
    locPref = typeof p.location_preference === 'object' ? (p.location_preference.type || '') : String(p.location_preference);
    citiesList = Array.isArray(p.location_preference.locations) ? p.location_preference.locations : [];
  }
  if (!citiesList.length) {
    if (Array.isArray(p.preferred_locations)) {
      citiesList = p.preferred_locations.map(s => String(s).trim()).filter(Boolean);
    } else if (typeof p.preferred_locations === 'string' && p.preferred_locations.trim()) {
      citiesList = p.preferred_locations.split(',').map(s => s.trim()).filter(Boolean);
    }
  }

  const normLoc = locPref.toLowerCase().trim();
  if (normLoc.includes('remote')) {
    locPref = 'remote_only';
  } else if (normLoc.includes('specific') || normLoc.includes('cit') || citiesList.length > 0) {
    locPref = 'specific_cities';
  } else if (normLoc.includes('global') || normLoc.includes('world') || normLoc.includes('internat')) {
    locPref = 'global';
  } else if (isAutoFill || p.onboarding_completed === true || (normLoc === 'all_india' && (p.name || p.title || (p.skills && p.skills.length)))) {
    locPref = 'all_india';
  } else {
    locPref = '';
  }

  ['prof-location-pref', 'onboard-location-pref'].forEach(radioName => {
    document.querySelectorAll(`input[name="${radioName}"]`).forEach(r => {
      const isMatch = Boolean(locPref && r.value === locPref);
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

  // 9. Indian Context Preferences (Notice Period, Current & Expected CTC)
  const noticeInput = document.getElementById('prof-notice-period');
  if (noticeInput) {
    const rawNotice = String(p.notice_period || '').toLowerCase().trim();
    let normNotice = '30_days';
    if (rawNotice.includes('imm') || rawNotice === '0') {
      normNotice = 'immediate';
    } else if (rawNotice.includes('15') || rawNotice.includes('2 week')) {
      normNotice = '15_days';
    } else if (rawNotice.includes('60') || rawNotice.includes('2 month')) {
      normNotice = '60_days';
    } else if (rawNotice.includes('90') || rawNotice.includes('3 month')) {
      normNotice = '90_days';
    } else if (rawNotice.includes('30') || rawNotice.includes('1 month')) {
      normNotice = '30_days';
    } else if (['immediate', '15_days', '30_days', '60_days', '90_days'].includes(rawNotice)) {
      normNotice = rawNotice;
    }
    noticeInput.value = normNotice;
  }

  const currentCtcInput = document.getElementById('prof-current-ctc');
  if (currentCtcInput) {
    const curVal = parseFloat(p.current_ctc_lpa);
    currentCtcInput.value = (!isNaN(curVal) && curVal >= 0 && (isAutoFill || curVal > 0 || p.onboarding_completed === true)) ? String(curVal) : '';
  }

  const expectedCtcInput = document.getElementById('prof-expected-ctc');
  if (expectedCtcInput) {
    const expVal = parseFloat(p.expected_ctc_lpa != null ? p.expected_ctc_lpa : p.min_salary_lpa);
    expectedCtcInput.value = (!isNaN(expVal) && expVal >= 0 && (isAutoFill || expVal > 0 || p.onboarding_completed === true)) ? String(expVal) : '';
  }

  // 10. Contact Details, Social Profiles & Narrative Bio
  const phoneInput = document.getElementById('prof-phone');
  if (phoneInput && (isAutoFill || !phoneInput.value.trim())) {
    phoneInput.value = (p.phone || '').trim();
  }

  const linkedinInput = document.getElementById('prof-linkedin');
  if (linkedinInput && (isAutoFill || !linkedinInput.value.trim())) {
    linkedinInput.value = (p.linkedin || '').trim();
  }

  const githubInput = document.getElementById('prof-github');
  if (githubInput && (isAutoFill || !githubInput.value.trim())) {
    githubInput.value = (p.github || '').trim();
  }

  const summaryInput = document.getElementById('prof-summary');
  if (summaryInput && (isAutoFill || !summaryInput.value.trim())) {
    summaryInput.value = (p.summary || p.profile_text || '').trim();
  }

  // Update active state of Indian Tech Hub preset chips
  updateHubChipsActiveState();

  const onbEmailInput = document.getElementById('onboard-prof-email');
  if (onbEmailInput) {
    const authEmail = currentAuthSession?.user?.email || '';
    if (p.notification_email) {
      onbEmailInput.value = p.notification_email;
    } else if (!onbEmailInput.value.trim() && authEmail) {
      onbEmailInput.value = authEmail;
    }
  }
}

// Preset Indian tech hub chip toggles
function toggleCityPreset(city) {
  const profRadio = document.querySelector('input[name="prof-location-pref"][value="specific_cities"]');
  if (profRadio) {
    profRadio.checked = true;
    document.querySelectorAll('input[name="prof-location-pref"]').forEach(r => {
      r.closest('.radio-option')?.classList.toggle('active', r.checked);
    });
  }
  const profSpecificContainer = document.getElementById('prof-specific-cities-input');
  if (profSpecificContainer) profSpecificContainer.style.display = 'block';

  const input = document.getElementById('prof-specific-cities');
  if (!input) return;

  let currentCities = input.value.split(',').map(s => s.trim()).filter(Boolean);
  const cityLower = city.toLowerCase();
  const existingIdx = currentCities.findIndex(c => c.toLowerCase() === cityLower);

  if (existingIdx >= 0) {
    currentCities.splice(existingIdx, 1);
  } else {
    currentCities.push(city);
  }
  input.value = currentCities.join(', ');
  updateHubChipsActiveState();
}

function updateHubChipsActiveState() {
  const input = document.getElementById('prof-specific-cities');
  const val = (input ? input.value : '').toLowerCase();
  const currentCities = val.split(',').map(s => s.trim()).filter(Boolean);

  document.querySelectorAll('.hub-chip').forEach(chip => {
    const rawCity = chip.getAttribute('data-city') || chip.innerText.replace(/^[+✓]\s*/, '').trim();
    const isActive = currentCities.some(c => c.toLowerCase() === rawCity.toLowerCase());
    chip.classList.toggle('active', isActive);
    chip.innerHTML = (isActive ? '✓ ' : '+ ') + rawCity;
  });
}

async function autoFillRolesFromResume() {
  const resumeText = document.getElementById('prof-resume-text')?.value?.trim() || activeProfileData?.resume_text || '';

  if (!resumeText && !parsedResumeData) {
    showToast('Please upload or enter your resume text in Step 1 first.', 'info');
    profileWizardGoTo(1);
    return;
  }

  // If parsedResumeData already exists in memory for this exact resume text, populate Step 2 fields instantly
  const hasCachedParsedData = parsedResumeData && (
    (Array.isArray(parsedResumeData.skills) && parsedResumeData.skills.length) ||
    (Array.isArray(parsedResumeData.core_skills) && parsedResumeData.core_skills.length) ||
    (Array.isArray(parsedResumeData.target_keywords) && parsedResumeData.target_keywords.length) ||
    (Array.isArray(parsedResumeData.target_titles) && parsedResumeData.target_titles.length) ||
    parsedResumeData.name ||
    parsedResumeData.title ||
    parsedResumeData.current_title
  );
  if (hasCachedParsedData && lastParsedResumeText === resumeText) {
    // Populate form fields only — do NOT mutate activeProfileData or save until explicit save click
    populateSection2FromProfile(parsedResumeData, true);
    showToast('Criteria auto-filled from resume. Review and click "Save Profile" to apply.', 'success', 3500);
    return;
  }

  const btn = document.getElementById('btn-autofill-roles');
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
      lastParsedResumeText = resumeText;
      // Preserve candidate name if already entered in Step 1 or Step 2 and new profile doesn't have a valid name
      const currentName = document.getElementById('prof-name')?.value?.trim();
      if (currentName && (!p.name || p.name === 'Candidate')) {
        p.name = currentName;
      }

      // Populate form fields in modal. Do NOT mutate activeProfileData or renderCandidateSummary()
      // until user explicitly clicks "Save Profile" or "Save Changes"!
      populateSection2FromProfile(p, true);
      showToast('Criteria auto-filled into form. Review and click "Save Profile" to apply.', 'success', 3500);
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
  if (dropText) dropText.innerText = 'Click or drag & drop a resume PDF / TXT file for AI Auto-Fill';
  const fileInput = document.getElementById('resume-file-input');
  if (fileInput) fileInput.value = '';

  // If modal was closed without saving, re-populate modal inputs from confirmed activeProfileData
  if (activeProfileData) {
    populateSection2FromProfile(activeProfileData, false);
  }
  deactivateModalFocus();
}

async function flushUserProfileData() {
  if (!checkAuthOrRedirect('flush candidate profile')) return;
  const confirmMsg =
    "Are you sure you want to completely reset and wipe your profile data?\n\n" +
    "This will permanently clear:\n" +
    "• All extracted resume information & uploaded files\n" +
    "• Technical skills, experience, and education\n" +
    "• Target roles, salary, locations, and search criteria\n" +
    "• Job alert preferences\n\n" +
    "Your authenticated email account will remain intact.";
  if (!confirm(confirmMsg)) return;
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
    'prof-specific-cities', 'notif-min-score', 'prof-current-ctc', 'prof-expected-ctc',
    'prof-phone', 'prof-linkedin', 'prof-github', 'prof-summary',
    'onboard-prof-name', 'onboard-prof-title', 'onboard-prof-years',
    'onboard-prof-education', 'onboard-prof-skills', 'onboard-prof-targets',
    'onboard-prof-excludes', 'onboard-specific-cities', 'onboarding-paste-text',
    'resume-paste-text'
  ];
  fieldIds.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });

  const noticeInput = document.getElementById('prof-notice-period');
  if (noticeInput) noticeInput.value = '30_days';

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
  if (dropText) dropText.innerText = 'Click or drag & drop a resume PDF / TXT file for AI Auto-Fill';
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
  lastParsedResumeText = '';
  if (digestShadowRoot) {
    digestShadowRoot.innerHTML = '';
  }

  try {
    const res = await authFetch('/api/profile/reset', { method: 'POST' });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      activeProfileData = { ...(data.profile || {}) };
      Storage.set(localStorage, STORAGE_KEYS.CACHED_PROFILE, activeProfileData);
      renderCandidateSummary(activeProfileData);
      updateJobSearchButtonState();
      profileWizardGoTo(1);
      showToast('Candidate profile and search preferences reset successfully.', 'success', 3500);
    } else {
      showToast('Reset notice: ' + (data.message || 'local fields cleared'), 'info');
    }
  } catch (err) {
    showToast('Reset notice: ' + err.message, 'info');
  }
}


// Profile wizard step navigation
function profileWizardGoTo(step) {
  const subtitles = ['', 'Step 1 of 3 — Resume Upload', 'Step 2 of 3 — Profile & Criteria', 'Step 3 of 3 — Alert Settings'];
  const subtitle = document.getElementById('profile-wizard-subtitle');
  if (subtitle) subtitle.innerText = subtitles[step] || '';

  if (step === 2 && parsedResumeData) {
    const skillsVal = document.getElementById('prof-skills')?.value?.trim();
    if (!skillsVal) {
      populateSection2FromProfile(parsedResumeData, true);
    }
  }

  [1, 2, 3].forEach(s => {
    const stepEl = document.getElementById(`profile-step-${s}`);
    const nodeEl = document.getElementById(`pws-node-${s}`);
    const circleEl = nodeEl ? nodeEl.querySelector('.wizard-step-circle') : null;
    if (stepEl) stepEl.style.display = s === step ? 'block' : 'none';
    if (nodeEl) {
      nodeEl.classList.toggle('active', s === step);
      nodeEl.classList.toggle('completed', s < step);
      if (s === step) {
        nodeEl.setAttribute('aria-current', 'step');
      } else {
        nodeEl.removeAttribute('aria-current');
      }
    }
    if (circleEl) {
      circleEl.innerText = String(s);
    }
  });
  [1, 2].forEach(s => {
    const conn = document.getElementById(`pws-conn-${s}`);
    if (conn) conn.classList.toggle('active', s < step);
  });
}

function profileWizardNext(fromStep) {
  // If moving from Step 1 to Step 2 with parsed resume data, auto-fill Step 2 criteria
  if (fromStep === 1 && parsedResumeData) {
    populateSection2FromProfile(parsedResumeData, true);
  }
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

  const btn = document.getElementById('btn-parse-text-ai') || document.getElementById('btn-reparse-text');
  const spinner = document.getElementById('parse-text-spinner') || document.getElementById('reparse-text-spinner');
  const btnLabel = document.getElementById('parse-text-btn-label');
  if (btn) btn.disabled = true;
  if (spinner) spinner.style.display = 'inline-block';
  if (btnLabel) btnLabel.innerText = 'Extracting with AI...';

  try {
    const res = await authFetch('/api/resume/upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_text: rawText, filename: 'text_context.txt' })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      const p = data.profile || {};
      parsedResumeData = p;
      lastParsedResumeText = rawText;

      // Populate form inputs only — do NOT mutate activeProfileData until user saves
      populateSection2FromProfile(p, true);

      // Update Step 2 AI banner
      const bannerText = document.getElementById('studio-ai-banner-text');
      if (bannerText) {
        const skillCount = Array.isArray(p.skills) ? p.skills.length : (Array.isArray(p.core_skills) ? p.core_skills.length : 0);
        const candName = p.name || 'Candidate';
        const candTitle = p.title || p.current_title || 'Candidate';
        bannerText.innerText = `✨ Auto-filled by AI: ${candName} • ${candTitle} • ${skillCount} skills extracted.`;
      }

      showToast('Candidate profile auto-filled from resume text! Review details below.', 'success', 3500);
      setTimeout(() => profileWizardGoTo(2), 600);
    } else {
      showToast('Failed to extract profile: ' + (data.message || 'error'), 'error');
    }
  } catch (err) {
    showToast('Text parsing error: ' + err.message, 'error');
  } finally {
    if (btn) btn.disabled = false;
    if (spinner) spinner.style.display = 'none';
    if (btnLabel) btnLabel.innerText = '✨ Auto-Fill Profile from Text';
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

  if (dropText) dropText.innerText = `Extracting candidate profile with AI: ${file.name}...`;
  if (alertEl) { alertEl.style.display = 'none'; }
  if (nextBtn) nextBtn.disabled = false;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 45000);

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
      lastParsedResumeText = extractedText;

      // Update dropzone label and text context textarea in Step 1
      if (dropText) dropText.innerText = `Resume extracted: ${file.name}`;
      if (resumeTextInput && extractedText) resumeTextInput.value = extractedText;

      // Auto-fill Step 2 search criteria and preferences from the newly parsed profile
      populateSection2FromProfile(p, true);

      // Update Step 2 AI banner
      const bannerText = document.getElementById('studio-ai-banner-text');
      if (bannerText) {
        const skillCount = Array.isArray(p.skills) ? p.skills.length : (Array.isArray(p.core_skills) ? p.core_skills.length : 0);
        const candName = p.name || 'Candidate';
        const candTitle = p.title || p.current_title || 'Candidate';
        bannerText.innerText = `✨ Auto-filled by AI: ${candName} • ${candTitle} • ${skillCount} skills extracted.`;
      }

      // Inline status confirmation in Step 1
      if (alertEl) {
        alertEl.className = 'studio-alert success';
        alertEl.innerText = `✓ "${file.name}" parsed! Candidate details & search criteria auto-filled with AI. Opening Step 2...`;
        alertEl.style.display = 'block';
      }
      if (previewCard) {
        previewCard.style.display = 'none';
      }

      showToast('✓ Resume parsed! Candidate profile and search criteria auto-filled.', 'success', 3500);
      setTimeout(() => profileWizardGoTo(2), 700);
    } else {
      if (dropText) dropText.innerText = `${file.name} — parse notice, click to retry or edit text below`;
      if (alertEl) {
        alertEl.className = 'studio-alert info';
        alertEl.innerText = `Notice: ${data.message || 'Resume parsing completed with basic text extraction. You can review details below.'}`;
        alertEl.style.display = 'block';
      }
      showToast('Resume extraction notice: ' + (data.message || 'basic text extraction used'), 'info');
    }
  } catch (err) {
    clearTimeout(timeoutId);
    const isTimeout = err.name === 'AbortError';
    const msg = isTimeout ? 'Parsing took too long — you can enter details manually.' : err.message;
    if (dropText) dropText.innerText = `${file.name} — click to retry or enter details below`;
    if (alertEl) {
      alertEl.className = 'studio-alert info';
      alertEl.innerText = `${msg} Text extracted or entered below can be edited freely before saving.`;
      alertEl.style.display = 'block';
    }
    showToast(isTimeout ? 'Resume parse notice: you can enter details manually.' : 'Notice: ' + err.message, 'info');
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
      handleResumeFileSelectedAndParse({ target: { files: files } });
    }
  }, false);
}

async function submitResumeParse() {
  if (!checkAuthOrRedirect('parse resume')) return;
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
      showToast('Resume parsed and details populated into profile.', 'success');
      if (alertEl) {
        alertEl.className = 'studio-alert success';
        alertEl.innerText = data.message;
        alertEl.style.display = 'block';
      }
      const p = data.profile || {};
      const extractedText = data.resume_text || p.resume_text || pasteText || '';
      parsedResumeData = p;
      lastParsedResumeText = extractedText;
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
  if (!checkAuthOrRedirect('save candidate profile')) return;
  const nameInput = document.getElementById('prof-name');
  const name = nameInput ? nameInput.value.trim() : (activeProfileData?.name || '');

  const targetsInput = document.getElementById('prof-targets');
  const targets = targetsInput && targetsInput.value.trim() !== ''
    ? targetsInput.value.split(',').map(s => s.trim()).filter(Boolean)
    : (Array.isArray(activeProfileData?.target_keywords) && activeProfileData.target_keywords.length
        ? activeProfileData.target_keywords
        : (Array.isArray(activeProfileData?.target_titles) && activeProfileData.target_titles.length
            ? activeProfileData.target_titles
            : (Array.isArray(parsedResumeData?.target_keywords) && parsedResumeData.target_keywords.length
                ? parsedResumeData.target_keywords
                : (Array.isArray(parsedResumeData?.target_titles) ? parsedResumeData.target_titles : []))));

  const titleInput = document.getElementById('prof-title');
  const title = titleInput && titleInput.value.trim() !== ''
    ? titleInput.value.trim()
    : (targets.length > 0 ? targets[0] : (activeProfileData?.title || activeProfileData?.current_title || parsedResumeData?.title || parsedResumeData?.current_title || ''));

  const yearsInput = document.getElementById('prof-years');
  const years = yearsInput && yearsInput.value.trim() !== ''
    ? (parseFloat(yearsInput.value) || 0)
    : (activeProfileData?.experience_years ?? activeProfileData?.years_experience ?? parsedResumeData?.experience_years ?? parsedResumeData?.years_experience ?? 0);

  const eduInput = document.getElementById('prof-education');
  const education = eduInput && eduInput.value.trim() !== ''
    ? eduInput.value.trim()
    : (activeProfileData?.education || parsedResumeData?.education || '');

  const skillsInput = document.getElementById('prof-skills');
  const skills = skillsInput && skillsInput.value.trim() !== ''
    ? skillsInput.value.split(',').map(s => s.trim()).filter(Boolean)
    : (Array.isArray(activeProfileData?.skills) && activeProfileData.skills.length
        ? activeProfileData.skills
        : (Array.isArray(activeProfileData?.core_skills) && activeProfileData.core_skills.length
            ? activeProfileData.core_skills
            : (Array.isArray(parsedResumeData?.skills) && parsedResumeData.skills.length
                ? parsedResumeData.skills
                : (Array.isArray(parsedResumeData?.core_skills) ? parsedResumeData.core_skills : []))));

  const excludesInput = document.getElementById('prof-excludes');
  const excludes = excludesInput && excludesInput.value.trim() !== ''
    ? excludesInput.value.split(',').map(s => s.trim()).filter(Boolean)
    : (Array.isArray(activeProfileData?.exclude_keywords) ? activeProfileData.exclude_keywords : (Array.isArray(parsedResumeData?.exclude_keywords) ? parsedResumeData.exclude_keywords : []));

  if (!name) {
    showToast('Please enter your candidate name in Step 2.', 'warning');
    profileWizardGoTo(2);
    nameInput?.focus();
    return;
  }
  if (!targets.length) {
    showToast('Please specify at least one target job title in Step 2.', 'warning');
    profileWizardGoTo(2);
    targetsInput?.focus();
    return;
  }
  if (!skills.length) {
    showToast('Please enter your core skills in Step 2.', 'warning');
    profileWizardGoTo(2);
    skillsInput?.focus();
    return;
  }

  const dailyRadio = document.getElementById('radio-mode-daily');
  const notifEnabled = dailyRadio ? Boolean(dailyRadio.checked) : false;

  const onetimeRadio = document.getElementById('radio-mode-onetime');
  const onetimeSelected = onetimeRadio ? Boolean(onetimeRadio.checked) : false;
  const mailMode = notifEnabled ? 'daily' : (onetimeSelected ? 'onetime' : '');

  const notifEmailInput = document.getElementById('notif-target-email');
  const enteredNotifEmail = notifEmailInput ? notifEmailInput.value.trim() : '';
  const notifEmail = enteredNotifEmail || currentAuthSession?.user?.email || activeProfileData?.notification_email || '';

  if ((notifEnabled || onetimeSelected) && !notifEmail) {
    showToast('Please provide a destination email address for dispatch alerts.', 'warning');
    profileWizardGoTo(3);
    notifEmailInput?.focus();
    return;
  }
  if ((notifEnabled || onetimeSelected) && notifEmail && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(notifEmail)) {
    showToast('Please enter a valid email address for notifications.', 'warning');
    profileWizardGoTo(3);
    notifEmailInput?.focus();
    return;
  }

  const minScoreInput = document.getElementById('notif-min-score');
  const minScoreVal = minScoreInput ? minScoreInput.value.trim() : '';
  const notifScore = minScoreVal ? parseFloat(minScoreVal) : null;
  if (notifScore !== null && (isNaN(notifScore) || notifScore < 0 || notifScore > 10)) {
    showToast('Minimum match score must be between 0.0 and 10.0.', 'warning');
    profileWizardGoTo(3);
    minScoreInput?.focus();
    return;
  }

  const resumeTextInput = document.getElementById('prof-resume-text');
  const resumeText = resumeTextInput ? resumeTextInput.value.trim() : (activeProfileData?.resume_text || '');

  const jobTypes = getSelectedJobTypes('prof-job-types');
  const deriveExpLevel = (y) => {
    const num = Number(y) || 0;
    if (num <= 0) return 'fresher';
    if (num <= 1) return '0-1';
    if (num <= 3) return '1-3';
    if (num <= 5) return '3-5';
    return '5+';
  };
  const expLevel = getSelectedExpLevel('prof-exp') || deriveExpLevel(years) || activeProfileData?.experience_level || '0-1';
  const locationPref = getLocationPreference('prof-location-pref', 'prof-specific-cities');
  const preferredLocations = Array.isArray(locationPref?.locations) ? locationPref.locations : [];

  const noticeInput = document.getElementById('prof-notice-period');
  const noticePeriod = noticeInput ? noticeInput.value : (activeProfileData?.notice_period || 'immediate');

  const curCtcInput = document.getElementById('prof-current-ctc');
  const curCtc = (curCtcInput && curCtcInput.value.trim() !== '') ? parseFloat(curCtcInput.value) : (activeProfileData?.current_ctc_lpa ?? null);

  const expCtcInput = document.getElementById('prof-expected-ctc');
  const expCtc = (expCtcInput && expCtcInput.value.trim() !== '') ? parseFloat(expCtcInput.value) : (activeProfileData?.expected_ctc_lpa ?? null);

  const phoneInput = document.getElementById('prof-phone');
  const phone = phoneInput ? phoneInput.value.trim() : (activeProfileData?.phone || parsedResumeData?.phone || '');

  const linkedinInput = document.getElementById('prof-linkedin');
  const linkedin = linkedinInput ? linkedinInput.value.trim() : (activeProfileData?.linkedin || parsedResumeData?.linkedin || '');

  const githubInput = document.getElementById('prof-github');
  const github = githubInput ? githubInput.value.trim() : (activeProfileData?.github || parsedResumeData?.github || '');

  const summaryInput = document.getElementById('prof-summary');
  const summary = summaryInput ? summaryInput.value.trim() : (activeProfileData?.summary || activeProfileData?.profile_text || parsedResumeData?.summary || '');

  const payload = {
    name,
    title,
    current_title: title,
    experience_years: years,
    years_experience: years,
    education,
    skills,
    core_skills: skills,
    target_keywords: targets,
    target_titles: targets,
    exclude_keywords: excludes,
    resume_text: resumeText,
    resume_filename: selectedResumeFile?.name || activeProfileData?.resume_filename || '',
    email_notifications_enabled: notifEnabled,
    mail_mode: mailMode,
    notification_email: notifEmail,
    candidate_email: notifEmail || activeProfileData?.candidate_email || activeProfileData?.email || '',
    min_score_notification: notifScore,
    onboarding_completed: Boolean(name && skills.length > 0 && targets.length > 0),
    job_types: jobTypes,
    experience_level: expLevel,
    location_preference: locationPref,
    preferred_locations: preferredLocations,
    notice_period: noticePeriod,
    current_ctc_lpa: curCtc,
    expected_ctc_lpa: expCtc,
    min_salary_lpa: expCtc,
    phone,
    linkedin,
    github,
    summary,
    profile_text: summary,
    graduation_year: activeProfileData?.graduation_year || parsedResumeData?.graduation_year || null,
    preferred_sectors: activeProfileData?.preferred_sectors || [],
    domains: activeProfileData?.domains || parsedResumeData?.domains || [],
    notable_projects: activeProfileData?.notable_projects || parsedResumeData?.notable_projects || []
  };

  const saveBtns = [
    document.getElementById('btn-profile-save'),
    document.getElementById('btn-profile-save-step2')
  ].filter(Boolean);
  const spinners = [
    document.getElementById('profile-save-spinner'),
    document.getElementById('profile-save-spinner-2')
  ].filter(Boolean);
  const btnTexts = [
    document.getElementById('profile-save-btn-text'),
    document.getElementById('profile-save-btn-text-2')
  ].filter(Boolean);

  saveBtns.forEach(b => { b.disabled = true; });
  spinners.forEach(s => { s.style.display = 'inline-block'; });
  btnTexts.forEach(t => { t.innerText = 'Saving...'; });

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
      Storage.set(sessionStorage, onboardingDismissedKey(), true);
      appState.isSavingProfile = false;
      await syncDashboard(true);
    } else {
      showToast('Failed to save profile: ' + data.message, 'error');
    }
  } catch (err) {
    showToast('Failed to save profile: ' + err.message, 'error');
  } finally {
    appState.isSavingProfile = false;
    saveBtns.forEach(b => { b.disabled = false; });
    spinners.forEach(s => { s.style.display = 'none'; });
    btnTexts.forEach(t => { t.innerText = 'Save Profile'; });
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
  if (!checkAuthOrRedirect('trigger autonomous pipeline scans')) return;

  if (appState.pipelineRunning) {
    showToast('A pipeline scan is already running. Results will sync automatically.', 'info', 3000);
    return;
  }

  if (!isCandidateProfileFilled(activeProfileData)) {
    openProfileModal();
    showToast('Please configure your candidate profile (Name, Target Title, Skills) to activate your radar.', 'info', 4000);
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

    if (data.status === 'dispatched') {
      showToast('Autonomous Radar dispatched to GitHub Actions in the cloud! Results will auto-sync.', 'success', 5000);
      if (consoleBox) consoleBox.innerText = 'Live radar running in GitHub Actions cloud... Crawling 114+ company boards (~1-2 mins).';
      fetchAndRenderJobs(false);
      startCloudPoller(data.dispatched_at || (Date.now() / 1000));

    } else if (data.status === 'need_github_dispatch') {
      if (consoleBox) consoleBox.innerText = 'Opening GitHub Actions to run the full 114+ live board crawl in the cloud... Monitoring for results.';
      showToast('Opening GitHub Actions to run the live radar in the cloud... Loader will monitor until results arrive.', 'info', 5000);
      fetchAndRenderJobs(false);
      if (data.actions_url) {
        window.open(data.actions_url, '_blank', 'noopener,noreferrer');
      }
      startCloudPoller(Date.now() / 1000);

    } else if (data.status === 'success' || data.status === 'busy') {
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
      // Backend guard: profile not yet filled — redirect user to Settings
      if (data.message && data.message.includes('candidate profile')) {
        if (consoleBox) consoleBox.innerText = 'Candidate radar incomplete. Please configure your profile to activate autonomous job scouting.';
        showToast('Please complete your candidate profile to begin.', 'info', 4500);
        openProfileModal();
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
  if (!checkAuthOrRedirect('update application status')) return;
  if (inFlightJobActions.has(jobId)) {
    showToast('That opportunity is already being updated.', 'info', 2200);
    return;
  }
  inFlightJobActions.add(jobId);
  const btn = document.getElementById('btn-app-' + jobId);
  const isUnmark = action === 'unmark';
  const job = appState.jobsMap[jobId];

  // 1. Optimistic Local State Update
  if (job) {
    job.applied = !isUnmark;
    if (!isUnmark && (!job.application_stage || job.application_stage === 'to_apply')) {
      job.application_stage = 'applied';
    } else if (isUnmark && job.application_stage === 'applied') {
      job.application_stage = 'to_apply';
    }
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
    btn.setAttribute('data-action', 'toggle-applied');
    btn.setAttribute('data-mode', isUnmark ? 'mark' : 'unmark');
    btn.setAttribute('title', isUnmark ? 'Mark as applied to activate follow-up tracking' : 'Application submitted — click to unmark');
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
        if (container && !container.querySelector('.job-item')) {
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
  } finally {
    inFlightJobActions.delete(jobId);
  }
}

// Delete Job with Instant Optimistic Collapse
async function deleteJobDirect(jobId) {
  if (!checkAuthOrRedirect('delete job from tracker')) return;
  if (inFlightJobActions.has(jobId)) {
    showToast('That opportunity is already being updated.', 'info', 2200);
    return;
  }
  if (!confirm(`Are you sure you want to delete job '${jobId}' from tracking store?`)) {
    return;
  }
  inFlightJobActions.add(jobId);

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
  } finally {
    inFlightJobActions.delete(jobId);
  }
}





// Authenticated Digest Viewport Refresh (Shadow DOM Isolated Rendering — Zero about:srcdoc Subframe History Entries)
let digestShadowRoot = null;

async function refreshDigest(force = false) {
  const container = document.getElementById('digest-frame');
  if (!container) return;

  if (!appState.authInitialized) return;
  if (authConfig.auth_required && !currentAuthSession) {
    return;
  }

  if (appState.activeTab !== 'digest' && !force) return;
  if (appState.digestRefreshing) return;
  appState.digestRefreshing = true;

  try {
    const url = force ? ('/api/digest?force=1&t=' + Date.now()) : ('/api/digest?t=' + Date.now());
    const res = await authFetch(url, { cache: 'no-store' });
    if (!res.ok) {
      if (res.status === 401) {
        const unauthMarkup = '<div style="font-family:sans-serif; text-align:center; padding:60px 20px; color:#64748b;"><h3>Authentication Required</h3><p>Please sign in to view your career digest.</p></div>';
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
    let html = await res.text();
    // Sanitize any legacy tracker metrics from cached briefings
    html = html.replace(/<td[^>]*class=["'][^"']*meta-table-col[^"']*["'][^>]*>\s*Tracker:\s*<b>.*?<\/b>\s*total seen\s*<\/td>/gis, '')
               .replace(/<td[^>]*>\s*Tracker:\s*<b>.*?<\/b>\s*total seen\s*<\/td>/gis, '')
               .replace(/Tracker:\s*<b>\d+<\/b>\s*total seen/gi, '');
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
  } finally {
    appState.digestRefreshing = false;
  }
}

// HTML Escaper
function jsLiteral(value) {
  return JSON.stringify(String(value ?? ''));
}

function escapeJsLiteral(value) {
  return escapeHtml(jsLiteral(value));
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

// Adaptive Background Polling Heartbeat (60s cadence, pauses after 10m idle to minimize Vercel/Supabase usage)
const HEARTBEAT_INTERVAL_MS = 60000;
const HEARTBEAT_IDLE_TIMEOUT_MS = 10 * 60 * 1000;
let lastUserActivityAt = Date.now();
let heartbeatPausedForIdle = false;

function _markUserActive() {
  const now = Date.now();
  const wasIdle = heartbeatPausedForIdle;
  lastUserActivityAt = now;
  if (wasIdle && !document.hidden && navigator.onLine) {
    heartbeatPausedForIdle = false;
    syncDashboard(false);
  }
}

['pointerdown', 'keydown'].forEach((evt) => {
  window.addEventListener(evt, _markUserActive, { passive: true });
});

function startHeartbeat() {
  stopHeartbeat();
  heartbeatIntervalId = setInterval(() => {
    if (document.hidden || !navigator.onLine) return;
    if (Date.now() - lastUserActivityAt > HEARTBEAT_IDLE_TIMEOUT_MS) {
      heartbeatPausedForIdle = true;
      return;
    }
    heartbeatPausedForIdle = false;
    syncDashboard(false);
  }, HEARTBEAT_INTERVAL_MS);
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
    lastUserActivityAt = Date.now();
    heartbeatPausedForIdle = false;
    // When tab wakes up from sleep/background, refresh session first to prevent stale 401s
    ensureFreshSession().then(() => {
      syncDashboard(false);
      startHeartbeat();
    });
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
  const isTyping = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) || document.activeElement.isContentEditable;
  const activeOverlay = _getActiveModalOverlay();
  if (e.key === 'Tab' && activeOverlay) {
    const focusables = _getModalFocusableElements(activeOverlay);
    if (focusables.length > 0) {
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && (document.activeElement === first || !activeOverlay.contains(document.activeElement))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (document.activeElement === last || !activeOverlay.contains(document.activeElement))) {
        e.preventDefault();
        first.focus();
      }
    }
    return;
  }
  if (e.key === '/' && !isTyping) {
    e.preventDefault();
    if (!checkAuthOrRedirect('search tracked jobs')) return;
    switchTab('tracker');
    const input = document.getElementById('tracker-search-input');
    if (input) {
      input.focus();
      input.select();
    }
  } else if ((e.key === 'Enter' || e.key === ' ') && !isTyping) {
    if (document.activeElement?.getAttribute('role') === 'button') {
      e.preventDefault();
      document.activeElement.click();
    }
  } else if (e.key === 'Escape') {
    if (document.getElementById('add-job-modal')?.classList.contains('active')) {
      closeAddJobModal();
    } else if (document.getElementById('add-company-modal')?.classList.contains('active')) {
      closeAddCompanyModal();
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

// ==============================================================================
// CSP-Compliant Event Delegation (Click, Submit, Change, Input)
// ==============================================================================

document.addEventListener('click', (e) => {
  // 1. Click outside modal to close
  const addJobModal = document.getElementById('add-job-modal');
  if (addJobModal && e.target === addJobModal) {
    closeAddJobModal();
  }
  const addCompanyModal = document.getElementById('add-company-modal');
  if (addCompanyModal && e.target === addCompanyModal) {
    closeAddCompanyModal();
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

  // 2. Declarative Action Delegation
  const actionTarget = e.target.closest('[data-action]');
  if (!actionTarget) return;

  const action = actionTarget.getAttribute('data-action');
  switch (action) {
    case 'manual-sync':
      manualSync();
      break;
    case 'scroll-to-auth': {
      const mode = actionTarget.getAttribute('data-auth-mode') || 'signin';
      scrollToAuth(mode);
      break;
    }
    case 'open-profile-modal':
      openProfileModal();
      break;
    case 'close-profile-modal':
      closeProfileModal();
      break;
    case 'sign-out':
      handleSignOut();
      break;
    case 'switch-auth-tab': {
      const tab = actionTarget.getAttribute('data-tab') || 'signin';
      switchAuthTab(tab);
      break;
    }
    case 'forgot-password':
      handleForgotPassword();
      break;
    case 'google-sign-in':
      handleGoogleSignIn();
      break;
    case 'toggle-modal-applied':
      toggleModalAppliedDirect();
      break;
    case 'close-kit-modal':
      closeKitModal();
      break;
    case 'open-add-job-modal':
      openAddJobModal();
      break;
    case 'close-add-job-modal':
      closeAddJobModal();
      break;
    case 'open-add-company-modal':
      openAddCompanyModal();
      break;
    case 'close-add-company-modal':
      closeAddCompanyModal();
      break;
    case 'run-pipeline':
      runPipeline();
      break;
    case 'switch-tab': {
      const tab = actionTarget.getAttribute('data-tab') || 'digest';
      switchTab(tab);
      break;
    }
    case 'refresh-digest':
      refreshDigest(true);
      break;
    case 'dismiss-guide':
      dismissWorkflowGuide();
      break;
    case 'toggle-guide':
      toggleWorkflowGuide();
      break;
    case 'clear-search':
      clearSearch();
      break;
    case 'search-tag': {
      const tag = actionTarget.getAttribute('data-tag') || actionTarget.innerText.trim();
      if (tag) {
        applySearchFilter(tag);
      }
      break;
    }
    case 'set-filter': {
      const filter = actionTarget.getAttribute('data-filter') || 'all';
      setFilter(filter);
      break;
    }
    case 'wizard-goto': {
      const step = parseInt(actionTarget.getAttribute('data-step') || '1', 10);
      profileWizardGoTo(step);
      break;
    }
    case 'wizard-next': {
      const step = parseInt(actionTarget.getAttribute('data-step') || '1', 10);
      profileWizardNext(step);
      break;
    }
    case 'wizard-back': {
      const step = parseInt(actionTarget.getAttribute('data-step') || '1', 10);
      profileWizardBack(step);
      break;
    }
    case 'trigger-resume-input': {
      const fileInput = document.getElementById('resume-file-input');
      if (fileInput) fileInput.click();
      break;
    }
    case 'flush-profile-data':
      flushUserProfileData();
      break;
    case 'autofill-roles':
      autoFillRolesFromResume();
      break;
    case 'parse-text-ai':
      submitTextContextParse();
      break;
    case 'toggle-city': {
      const city = actionTarget.getAttribute('data-city');
      if (city) toggleCityPreset(city);
      break;
    }
    case 'select-mail-mode': {
      const mode = actionTarget.getAttribute('data-mode') || 'daily';
      selectMailMode(mode);
      break;
    }
    case 'save-profile-preferences':
      saveProfilePreferences();
      break;
    case 'set-page': {
      const page = parseInt(actionTarget.getAttribute('data-page') || '1', 10);
      setPage(page);
      break;
    }
    case 'reset-filters-and-search':
      resetFiltersAndSearch();
      break;
    case 'open-followup-modal': {
      e.stopPropagation();
      const jobId = actionTarget.getAttribute('data-job-id');
      if (jobId) openFollowupModal(jobId);
      break;
    }
    case 'toggle-applied': {
      e.stopPropagation();
      const jobId = actionTarget.getAttribute('data-job-id');
      const mode = actionTarget.getAttribute('data-mode') || 'mark';
      if (jobId) toggleAppliedDirect(jobId, mode);
      break;
    }
    case 'delete-job': {
      e.stopPropagation();
      const jobId = actionTarget.getAttribute('data-job-id');
      if (jobId) deleteJobDirect(jobId);
      break;
    }
    case 'open-kit-modal': {
      e.stopPropagation();
      const jobId = actionTarget.getAttribute('data-job-id');
      if (jobId) openKitModal(jobId);
      break;
    }
    case 'open-auth-modal': {
      const mode = actionTarget.getAttribute('data-mode') || 'signin';
      openAuthModal(mode);
      break;
    }
    case 'copy-section': {
      const targetId = actionTarget.getAttribute('data-target');
      const btnId = actionTarget.getAttribute('data-btn');
      if (targetId && btnId) copySectionText(targetId, btnId);
      break;
    }
    case 'delete-custom-company': {
      const ats = actionTarget.getAttribute('data-ats');
      const slug = actionTarget.getAttribute('data-slug');
      if (ats && slug) deleteCustomCompany(ats, slug);
      break;
    }
    case 'save-job-notes': {
      e.stopPropagation();
      const jobId = actionTarget.getAttribute('data-job-id');
      if (jobId) saveJobNotes(jobId);
      break;
    }
    default:
      break;
  }
});

// Central Form Submission Delegation
document.addEventListener('submit', (e) => {
  if (e.target && e.target.id === 'form-signin') {
    handleSignInSubmit(e);
  } else if (e.target && e.target.id === 'form-signup') {
    handleSignUpSubmit(e);
  } else if (e.target && e.target.id === 'form-add-job') {
    handleAddJobSubmit(e);
  } else if (e.target && e.target.id === 'form-add-company') {
    handleAddCompanySubmit(e);
  }
});

// Central Input Event Delegation
document.addEventListener('input', (e) => {
  if (e.target && e.target.id === 'tracker-search-input') {
    handleSearchInput();
  } else if (e.target && e.target.id === 'add-company-url') {
    handleCompanyUrlInput(e.target.value);
  } else if (e.target && e.target.id === 'signup-password') {
    if (typeof validateSignupPassword === 'function') {
      validateSignupPassword(e.target);
    }
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

  // Hard Security Boundary: force landing view if unauthenticated & auth is required
  if (authConfig.auth_required && !currentAuthSession) {
    view = 'landing';
  }

  if (view === 'dashboard') {
    if (landingView) {
      landingView.classList.add('app-view-hidden');
      landingView.style.setProperty('display', 'none', 'important');
    }
    if (landingNavLinks) {
      landingNavLinks.classList.add('app-view-hidden');
      landingNavLinks.style.setProperty('display', 'none', 'important');
    }
    if (dashboardView) {
      dashboardView.classList.remove('app-view-hidden');
      dashboardView.style.setProperty('display', 'flex', 'important');
    }
    if (headerMetrics) {
      headerMetrics.classList.remove('app-view-hidden');
      headerMetrics.style.setProperty('display', 'flex', 'important');
    }
    setSyncStatus('synced', 'Live Synced');
  } else {
    // Dismiss all active utility modals when transitioning to or remaining in landing view
    if (typeof closeAddJobModal === 'function') closeAddJobModal();
    if (typeof closeAddCompanyModal === 'function') closeAddCompanyModal();
    if (typeof closeProfileModal === 'function') closeProfileModal();
    if (typeof closeOnboardingModal === 'function') closeOnboardingModal(true);
    if (typeof closeKitModal === 'function') closeKitModal();

    if (landingView) {
      landingView.classList.remove('app-view-hidden');
      landingView.style.setProperty('display', 'flex', 'important');
    }
    if (landingNavLinks) {
      landingNavLinks.classList.remove('app-view-hidden');
      landingNavLinks.style.setProperty('display', 'flex', 'important');
    }
    if (dashboardView) {
      dashboardView.classList.add('app-view-hidden');
      dashboardView.style.setProperty('display', 'none', 'important');
    }
    if (headerMetrics) {
      headerMetrics.classList.add('app-view-hidden');
      headerMetrics.style.setProperty('display', 'none', 'important');
    }
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
    const email = session.user.email || 'User';
    if (userEmail) userEmail.innerText = email;
    if (userAvatar) userAvatar.innerText = email.charAt(0).toUpperCase();
  } else {
    if (userEmail) userEmail.innerText = '';
    if (userAvatar) userAvatar.innerText = '?';
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

function validateSignupPassword(inputEl) {
  const hint = document.getElementById('signup-pw-hint');
  if (!hint || !inputEl) return;
  const val = inputEl.value;
  if (!val) {
    hint.textContent = 'Min. 6 characters';
    hint.style.color = '';
  } else if (val.length < 6) {
    hint.textContent = `${val.length}/6 characters (too short)`;
    hint.style.color = 'var(--danger, #e11d48)';
  } else {
    hint.textContent = '✓ Password valid';
    hint.style.color = 'var(--success, #059669)';
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

  // Reset in-memory application state
  appState.jobsList = [];
  appState.jobsMap = {};
  appState.stats = { tracked: 0, emailed: 0, applied: 0, shortlisted: 0, unapplied: 0 };
  appState.activeKitId = null;
  activeProfileData = null;
  parsedResumeData = null;
  lastParsedResumeText = '';
  selectedResumeFile = null;

  // Clear rendered dashboard DOM containers (including Shadow DOM digest)
  const jobContainer = document.getElementById('job-list-container');
  if (jobContainer) jobContainer.innerHTML = '';
  const historyContainer = document.getElementById('activity-history-list');
  if (historyContainer) historyContainer.innerHTML = '';
  const customCompContainer = document.getElementById('custom-companies-list');
  if (customCompContainer) customCompContainer.innerHTML = '';
  const digestFrame = document.getElementById('digest-frame');
  if (digestShadowRoot) {
    digestShadowRoot.innerHTML = '';
  } else if (digestFrame?.shadowRoot) {
    digestFrame.shadowRoot.innerHTML = '';
  }

  // Reset header & studio metrics
  renderMetrics({ tracked: 0, emailed: 0, applied: 0 });
  renderCandidateSummary(null);

  // Purge sensitive data cached in localStorage and sessionStorage
  Storage.remove(localStorage, STORAGE_KEYS.CACHED_STATS);
  Storage.remove(localStorage, STORAGE_KEYS.CACHED_PROFILE);
  Storage.remove(localStorage, STORAGE_KEYS.CACHED_JOBS);
  Storage.remove(localStorage, STORAGE_KEYS.SEARCH_QUERY);
  Storage.remove(sessionStorage, STORAGE_KEYS.ACTIVE_KIT);
  Storage.remove(localStorage, STORAGE_KEYS.DRAFT_CUSTOM_JOB);
  Storage.remove(localStorage, STORAGE_KEYS.DRAFT_APPLIED_ID);

  // Transition to landing view and notify
  setAppView('landing');
  showToast('Signed out successfully', 'info');
}

async function initAuth() {
  try {
    const res = await fetch('/api/auth/config', { cache: 'no-store' });
      const cfg = await parseJsonResponse(res);
      if (!res.ok) {
        throw new Error(cfg.message || 'Authentication service is unavailable.');
      }

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
      let initialAuthSynced = false;
      supabaseClient.auth.onAuthStateChange((event, session) => {
        currentAuthSession = session;
        updateUserHeader(session);
        if (session) {
          setAppView('dashboard');
          if (!initialAuthSynced) {
            initialAuthSynced = true;
            syncDashboard(true);
          }
          startHeartbeat();
 
          // Clean up OAuth fragment from address bar if present
          if (window.location.hash && window.location.hash.includes('access_token')) {
            window.history.replaceState(null, '', window.location.pathname + window.location.search);
          }
        } else if (authConfig.auth_required) {
          stopHeartbeat();
          setAppView('landing');
        } else {
          setAppView('dashboard');
          if (!initialAuthSynced) {
            initialAuthSynced = true;
            syncDashboard(true);
          }
        }
      });
 
      // Initialize View based on restored session
      appState.authInitialized = true;
      if (currentAuthSession) {
        // Hydrate cached stats & profile only for confirmed authenticated session
        const cachedStats = Storage.get(localStorage, STORAGE_KEYS.CACHED_STATS, null);
        if (cachedStats && cachedStats.stats) {
          renderMetrics(cachedStats.stats);
        }
        const cachedProfile = Storage.get(localStorage, STORAGE_KEYS.CACHED_PROFILE, null);
        if (cachedProfile) {
          activeProfileData = cachedProfile;
          renderCandidateSummary(cachedProfile);
        }
        setAppView('dashboard');
        updateUserHeader(currentAuthSession);
        if (!initialAuthSynced) {
          initialAuthSynced = true;
          syncDashboard(true);
        }
        startHeartbeat();
      } else if (authConfig.auth_required) {
        renderMetrics({ tracked: 0, emailed: 0, applied: 0 });
        renderCandidateSummary(null);
        setAppView('landing');
        stopHeartbeat();
      } else {
        const cachedStats = Storage.get(localStorage, STORAGE_KEYS.CACHED_STATS, null);
        if (cachedStats && cachedStats.stats) {
          renderMetrics(cachedStats.stats);
        }
        const cachedProfile = Storage.get(localStorage, STORAGE_KEYS.CACHED_PROFILE, null);
        if (cachedProfile) {
          activeProfileData = cachedProfile;
          renderCandidateSummary(cachedProfile);
        }
        setAppView('dashboard');
        if (!initialAuthSynced) {
          initialAuthSynced = true;
          syncDashboard(true);
        }
      }
    } else {
      appState.authInitialized = true;
      if (!authConfig.auth_required) {
        const cachedStats = Storage.get(localStorage, STORAGE_KEYS.CACHED_STATS, null);
        if (cachedStats && cachedStats.stats) {
          renderMetrics(cachedStats.stats);
        }
        const cachedProfile = Storage.get(localStorage, STORAGE_KEYS.CACHED_PROFILE, null);
        if (cachedProfile) {
          activeProfileData = cachedProfile;
          renderCandidateSummary(cachedProfile);
        }
        setAppView('dashboard');
        syncDashboard(true);
      } else {
        renderMetrics({ tracked: 0, emailed: 0, applied: 0 });
        renderCandidateSummary(null);
        setAppView('landing');
        stopHeartbeat();
      }
    }
  } catch (err) {
    console.warn('Auth configuration init error:', err);
    showToast('Authentication is temporarily unavailable. Please try again later.', 'error', 7000);
    appState.authInitialized = true;
    renderMetrics({ tracked: 0, emailed: 0, applied: 0 });
    renderCandidateSummary(null);
    setAppView('landing');
    stopHeartbeat();
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
  const locParam = params.get('loc');

  appState.activeTab = tabParam || Storage.get(localStorage, STORAGE_KEYS.ACTIVE_TAB, 'digest');
  appState.filter = statusParam || Storage.get(localStorage, STORAGE_KEYS.STATUS_FILTER, 'all');
  appState.locationFilter = locParam || Storage.get(localStorage, STORAGE_KEYS.LOCATION_FILTER, 'all') || 'all';
  appState.ats = atsParam || Storage.get(localStorage, STORAGE_KEYS.ATS_FILTER, 'all');
  appState.sort = sortParam || Storage.get(localStorage, STORAGE_KEYS.SORT_BY, 'date');
  appState.search = searchParam || Storage.get(sessionStorage, STORAGE_KEYS.SEARCH_QUERY, '');

  if (kitParam) {
    appState.activeKitId = kitParam;
  }

  // Populate controls
  const searchInput = document.getElementById('tracker-search-input');
  const clearBtn = document.getElementById('search-clear-btn');
  const atsSelect = document.getElementById('tracker-ats-select');
  const sortSelect = document.getElementById('tracker-sort-select');
  const locFilterSelect = document.getElementById('tracker-location-filter') || document.getElementById('tracker-location-select');

  if (searchInput) {
    searchInput.value = appState.search;
    if (clearBtn) clearBtn.style.display = appState.search ? 'flex' : 'none';
  }
  if (atsSelect) atsSelect.value = appState.ats;
  if (sortSelect) sortSelect.value = appState.sort;
  if (locFilterSelect) locFilterSelect.value = appState.locationFilter;

  const profCitiesInput = document.getElementById('prof-specific-cities');
  if (profCitiesInput) {
    profCitiesInput.addEventListener('input', updateHubChipsActiveState);
  }

  // Set filter pill
  document.querySelectorAll('.filter-pills .pill').forEach(el => el.classList.remove('active'));
  const activePill = document.getElementById('pill-' + appState.filter);
  if (activePill) activePill.classList.add('active');

  // Set active tab without firing unauthenticated network requests
  switchTab(appState.activeTab, false);

  // Set default initial view to landing page for clean unauthenticated baseline render
  setAppView('landing');

  // Initialize draft saving & dropzones
  initDraftSaving();
  initDropzoneHandlers();

  // Initialize Supabase Authentication & start data sync
  initAuth();

  // Initial check on job search button activation state
  updateJobSearchButtonState();

  // Resume any in-flight cloud radar run across reloads
  try {
    const savedRun = JSON.parse(sessionStorage.getItem('jobhunt_active_cloud_run') || '{}');
    if (savedRun.dispatched_at && (Date.now() / 1000 - savedRun.dispatched_at) < 1200) {
      startCloudPoller(savedRun.dispatched_at);
    }
  } catch (_) {}

  // Brand logo error fallback handler
  const brandLogo = document.getElementById('brand-logo-img');
  if (brandLogo) {
    brandLogo.addEventListener('error', () => {
      brandLogo.style.display = 'none';
      const fallback = document.getElementById('brand-fallback');
      if (fallback) fallback.style.display = 'flex';
    });
  }
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

// Global UI listeners for chips, radios, select filters, and dynamic stages
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

  // Declarative Change Handlers
  if (e.target && e.target.id === 'tracker-ats-select') {
    fetchAndRenderJobs();
  } else if (e.target && (e.target.id === 'tracker-location-filter' || e.target.id === 'tracker-location-select')) {
    handleLocationFilterChange(e.target.value);
  } else if (e.target && e.target.id === 'tracker-sort-select') {
    fetchAndRenderJobs();
  } else if (e.target && e.target.id === 'resume-file-input') {
    handleResumeFileSelectedAndParse(e);
  } else if (e.target && e.target.id === 'pagination-page-size') {
    setPageSize(e.target.value);
  } else if (e.target && e.target.getAttribute('data-change-action') === 'update-job-stage') {
    const jobId = e.target.getAttribute('data-job-id');
    if (jobId) updateJobStageDirect(jobId, e.target.value);
  }
});

// Copy to Clipboard global helper
function copyToClipboard(text, btnEl) {
  copyTextSafely(text).then(() => {
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

// Add Custom Opportunity Modal Controller
function openAddJobModal() {
  if (!checkAuthOrRedirect('track custom job opportunity')) return;
  const modal = document.getElementById('add-job-modal');
  if (modal) {
    modal.classList.add('active');
    activateModalFocus(modal, document.getElementById('add-job-company'));
  }
}

function closeAddJobModal() {
  const modal = document.getElementById('add-job-modal');
  if (modal) {
    modal.classList.remove('active');
    document.getElementById('form-add-job')?.reset();
    const scoreInput = document.getElementById('add-job-score');
    if (scoreInput) scoreInput.value = '7.5';
    const aiCheckbox = document.getElementById('add-job-ai-eval');
    if (aiCheckbox) aiCheckbox.checked = true;
  }
  deactivateModalFocus();
}

async function handleAddJobSubmit(e) {
  e.preventDefault();
  if (!checkAuthOrRedirect('track custom job opportunity')) return;
  const company = document.getElementById('add-job-company')?.value.trim();
  const title = document.getElementById('add-job-title')?.value.trim();
  const location = document.getElementById('add-job-location')?.value.trim() || 'Remote/Unspecified';
  const url = document.getElementById('add-job-url')?.value.trim() || '#';
  const stage = document.getElementById('add-job-stage')?.value || 'to_apply';
  const score = parseFloat(document.getElementById('add-job-score')?.value || '7.5');
  const description = document.getElementById('add-job-description')?.value.trim() || '';
  const runAi = document.getElementById('add-job-ai-eval')?.checked;

  if (!company || !title) {
    showToast('Company name and job title are required.', 'error');
    return;
  }

  const spinner = document.getElementById('add-job-spinner');
  const btnText = document.getElementById('add-job-submit-text');
  const submitBtn = document.getElementById('btn-submit-add-job');

  if (spinner) spinner.style.display = 'inline-block';
  if (btnText) btnText.innerText = runAi && description ? 'Evaluating with AI...' : 'Saving Opportunity...';
  if (submitBtn) submitBtn.disabled = true;

  try {
    const payload = {
      company,
      title,
      location,
      url,
      stage,
      score,
      description,
      run_ai: runAi,
      applied: stage !== 'to_apply',
    };

    const res = await authFetch('/api/jobs/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      showToast(`Tracked '${title}' at ${company}!`, 'success');
      closeAddJobModal();

      // Trigger instant UI reload and multi-tab broadcast
      broadcastSync('STATE_MUTATED', { job_id: data.job_id });
      await syncDashboard(false);
      await fetchAndRenderJobs(false);

      if (data.job && data.job.draft && (data.job.draft.fit_summary || data.job.draft.cover_note)) {
        setTimeout(() => {
          openKitModal(data.job_id);
        }, 500);
      }
    } else {
      throw new Error(data.message || 'Failed to add job opportunity');
    }
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  } finally {
    if (spinner) spinner.style.display = 'none';
    if (btnText) btnText.innerText = 'Track Opportunity';
    if (submitBtn) submitBtn.disabled = false;
  }
}


// --------------------------------------------------------------------------
// Follow-Up Note Modal Orchestrator
// --------------------------------------------------------------------------
async function openFollowupModal(jobId) {
  if (!checkAuthOrRedirect('generate follow-up notes')) return;
  const j = appState.jobsMap[jobId];
  if (!j) return;
  showToast('Generating smart follow-up note...', 'info', 2000);
  try {
    const res = await authFetch('/api/jobs/followup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        job_id: jobId,
        title: j.title,
        company: j.company,
        applied_on: j.applied_on || j.first_seen || '',
        stage: j.application_stage || (j.applied ? 'applied' : 'to_apply')
      })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success' && data.followup) {
      if (!j.draft) j.draft = {};
      j.draft.followup = data.followup;
    }
  } catch (e) {
    console.warn('Followup generation notice:', e);
  }
  openKitModal(jobId);
}

// --------------------------------------------------------------------------
// Custom ATS Company Board Manager
// --------------------------------------------------------------------------
function openAddCompanyModal() {
  if (!checkAuthOrRedirect('manage custom company boards')) return;
  const modal = document.getElementById('add-company-modal');
  if (modal) {
    modal.classList.add('active');
    const urlInput = document.getElementById('add-company-url');
    if (urlInput) {
      urlInput.value = '';
    }
    activateModalFocus(modal, urlInput);
    const detectedCard = document.getElementById('add-company-detected');
    if (detectedCard) detectedCard.style.display = 'none';
    const alertBox = document.getElementById('add-company-status-alert');
    if (alertBox) alertBox.style.display = 'none';
    fetchAndRenderCustomCompanies();
  }
}

function closeAddCompanyModal() {
  const modal = document.getElementById('add-company-modal');
  if (modal) modal.classList.remove('active');
  deactivateModalFocus();
}

function handleCompanyUrlInput(rawUrl) {
  if (!rawUrl || !rawUrl.trim()) {
    const detectedCard = document.getElementById('add-company-detected');
    if (detectedCard) detectedCard.style.display = 'none';
    return;
  }

  const url = rawUrl.trim().toLowerCase();
  let ats = null;
  let slug = '';

  if (url.includes('greenhouse.io')) {
    ats = 'greenhouse';
    const parts = url.split('/');
    slug = parts[parts.length - 1] || parts[parts.length - 2] || '';
  } else if (url.includes('lever.co')) {
    ats = 'lever';
    const parts = url.split('/');
    slug = parts[parts.length - 1] || parts[parts.length - 2] || '';
  } else if (url.includes('ashbyhq.com')) {
    ats = 'ashby';
    const parts = url.split('/');
    slug = parts[parts.length - 1] || parts[parts.length - 2] || '';
  } else if (url.includes('workable.com')) {
    ats = 'workable';
    if (url.includes('apply.workable.com')) {
      const parts = url.split('/');
      slug = parts[parts.length - 1] || parts[parts.length - 2] || '';
    } else {
      slug = url.replace('https://', '').replace('http://', '').split('.')[0];
    }
  } else if (url.includes('smartrecruiters.com')) {
    ats = 'smartrecruiters';
    const parts = url.split('/');
    slug = parts[parts.length - 1] || parts[parts.length - 2] || '';
  } else if (url.includes('bamboohr.com')) {
    ats = 'bamboohr';
    slug = url.replace('https://', '').replace('http://', '').split('.')[0];
  } else if (url.includes('recruitee.com')) {
    ats = 'recruitee';
    slug = url.replace('https://', '').replace('http://', '').split('.')[0];
  } else if (url.includes('breezy.hr')) {
    ats = 'breezy';
    slug = url.replace('https://', '').replace('http://', '').split('.')[0];
  } else if (url.includes('pinpoint.work') || url.includes('pinpointhq.com')) {
    ats = 'pinpoint';
    slug = url.replace('https://', '').replace('http://', '').split('.')[0];
  }

  // Clean slug
  slug = slug.split('?')[0].split('#')[0].replace(/[^a-zA-Z0-9_\-]/g, '');

  const detectedCard = document.getElementById('add-company-detected');
  const badge = document.getElementById('detected-ats-badge');
  const slugEl = document.getElementById('detected-slug-text');
  const nameInput = document.getElementById('add-company-name');
  const overrideSelect = document.getElementById('add-company-ats-override');

  if (ats && slug) {
    if (detectedCard) detectedCard.style.display = 'block';
    if (badge) badge.innerText = ats.toUpperCase();
    if (slugEl) slugEl.innerText = `slug: ${slug}`;
    if (nameInput && !nameInput.value.trim()) {
      nameInput.value = slug.replace(/[-_]/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
    if (overrideSelect) overrideSelect.value = ats;
  }
}

async function handleAddCompanySubmit(event) {
  event.preventDefault();
  if (!checkAuthOrRedirect('manage custom company boards')) return;
  const urlInput = document.getElementById('add-company-url');
  const nameInput = document.getElementById('add-company-name');
  const atsSelect = document.getElementById('add-company-ats-override');
  const spinner = document.getElementById('save-company-spinner');
  const submitBtn = document.getElementById('btn-save-company');
  const alertBox = document.getElementById('add-company-status-alert');

  const url = urlInput ? urlInput.value.trim() : '';
  const name = nameInput ? nameInput.value.trim() : '';
  const ats = atsSelect ? atsSelect.value : '';

  if (!url) {
    showToast('Please provide a company career portal URL', 'error');
    return;
  }

  if (spinner) spinner.style.display = 'inline-block';
  if (submitBtn) submitBtn.disabled = true;
  if (alertBox) alertBox.style.display = 'none';

  try {
    const res = await authFetch('/api/companies/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, name, ats })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      showToast(data.message || 'Target company board added successfully!', 'success', 5000);
      if (urlInput) urlInput.value = '';
      const detectedCard = document.getElementById('add-company-detected');
      if (detectedCard) detectedCard.style.display = 'none';
      fetchAndRenderCustomCompanies();
      broadcastSync('STATE_MUTATED');
    } else {
      throw new Error(data.message || 'Could not verify company board URL');
    }
  } catch (err) {
    if (alertBox) {
      alertBox.style.display = 'block';
      alertBox.className = 'studio-alert studio-alert-error';
      alertBox.innerText = err.message;
    }
    showToast('Validation failed: ' + err.message, 'error');
  } finally {
    if (spinner) spinner.style.display = 'none';
    if (submitBtn) submitBtn.disabled = false;
  }
}

async function fetchAndRenderCustomCompanies() {
  if (authConfig.auth_required && !currentAuthSession) return;
  const container = document.getElementById('custom-companies-list');
  if (!container) return;

  try {
    const res = await authFetch('/api/companies/custom', { cache: 'no-store' });
    const data = await parseJsonResponse(res);
    if (data.status === 'success' && data.companies && data.companies.length > 0) {
      container.innerHTML = data.companies.map(c => `
        <div class="custom-company-chip" style="display:inline-flex; align-items:center; gap:6px; background:var(--card-bg, #fff); border:1px solid var(--border, #e2e8f0); padding:4px 10px; border-radius:20px; font-size:12px;">
          <span style="font-weight:600; color:var(--text);">${escapeHtml(c.name || c.slug)}</span>
          <span style="font-size:10px; text-transform:uppercase; color:var(--muted); background:var(--bg, #f8fafc); padding:1px 5px; border-radius:4px;">${escapeHtml(c.ats)}</span>
          <button type="button" data-action="delete-custom-company" data-ats="${escapeHtml(c.ats)}" data-slug="${escapeHtml(c.slug)}" style="background:none; border:none; cursor:pointer; color:var(--danger, #ef4444); font-size:13px; margin-left:2px;" title="Remove company board">×</button>
        </div>
      `).join('');
    } else {
      container.innerHTML = '<span style="font-size:12px; color:var(--muted);">No custom boards added yet. Paste a link above to add one!</span>';
    }
  } catch (e) {
    console.warn('Failed to load custom companies:', e);
  }
}

async function deleteCustomCompany(ats, slug) {
  if (!checkAuthOrRedirect('remove custom company board')) return;
  if (!confirm(`Remove ${slug} (${ats}) from your custom target boards?`)) return;
  try {
    const res = await authFetch('/api/companies/custom', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ats, slug })
    });
    const data = await parseJsonResponse(res);
    if (data.status === 'success') {
      showToast(data.message || 'Removed company board', 'success');
      fetchAndRenderCustomCompanies();
      broadcastSync('STATE_MUTATED');
    }
  } catch (err) {
    showToast('Failed to remove: ' + err.message, 'error');
  }
}

// ==============================================================================
// Window Global Exports (Zero-Regression Backwards Compatibility)
// ==============================================================================
if (typeof window !== 'undefined') {
  window.manualSync = manualSync;
  window.scrollToAuth = scrollToAuth;
  window.openProfileModal = openProfileModal;
  window.closeProfileModal = closeProfileModal;
  window.handleSignOut = handleSignOut;
  window.switchAuthTab = switchAuthTab;
  window.handleForgotPassword = handleForgotPassword;
  window.handleGoogleSignIn = handleGoogleSignIn;
  window.toggleModalAppliedDirect = toggleModalAppliedDirect;
  window.closeKitModal = closeKitModal;
  window.openAddJobModal = openAddJobModal;
  window.closeAddJobModal = closeAddJobModal;
  window.openAddCompanyModal = openAddCompanyModal;
  window.closeAddCompanyModal = closeAddCompanyModal;
  window.runPipeline = runPipeline;
  window.switchTab = switchTab;
  window.refreshDigest = refreshDigest;
  window.dismissWorkflowGuide = dismissWorkflowGuide;
  window.toggleWorkflowGuide = toggleWorkflowGuide;
  window.clearSearch = clearSearch;
  window.setFilter = setFilter;
  window.profileWizardGoTo = profileWizardGoTo;
  window.profileWizardNext = profileWizardNext;
  window.profileWizardBack = profileWizardBack;
  window.flushUserProfileData = flushUserProfileData;
  window.autoFillRolesFromResume = autoFillRolesFromResume;
  window.submitTextContextParse = submitTextContextParse;
  window.toggleCityPreset = toggleCityPreset;
  window.selectMailMode = selectMailMode;
  window.saveProfilePreferences = saveProfilePreferences;
  window.setPage = setPage;
  window.resetFiltersAndSearch = resetFiltersAndSearch;
  window.openFollowupModal = openFollowupModal;
  window.toggleAppliedDirect = toggleAppliedDirect;
  window.deleteJobDirect = deleteJobDirect;
  window.openKitModal = openKitModal;
  window.saveJobNotes = saveJobNotes;
  window.copySectionText = copySectionText;
  window.deleteCustomCompany = deleteCustomCompany;
  window.updateJobStageDirect = updateJobStageDirect;
  window.handleResumeFileSelectedAndParse = handleResumeFileSelectedAndParse;
  window.setPageSize = setPageSize;
  window.handleSearchInput = handleSearchInput;
  window.handleLocationFilterChange = handleLocationFilterChange;
  window.handleCompanyUrlInput = handleCompanyUrlInput;
  window.fetchAndRenderJobs = fetchAndRenderJobs;
  window.appState = appState;
}


