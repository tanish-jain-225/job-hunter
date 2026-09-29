/**
 * Local & Session Storage management with safe JSON handling and error guards.
 */

export const STORAGE_KEYS = {
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

export const Storage = {
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
