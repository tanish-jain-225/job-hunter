/**
 * DOM, formatting, text escaping, and localization utilities.
 */

export const INDIA_CITIES = [
  'bengaluru', 'bangalore', 'hyderabad', 'pune', 'delhi', 'ncr', 'noida', 'gurugram', 'gurgaon',
  'mumbai', 'chennai', 'kolkata', 'ahmedabad', 'india', 'ind'
];

export function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

export function escapeJsLiteral(str) {
  if (str === null || str === undefined) return "''";
  return JSON.stringify(String(str));
}

export function isIndiaJob(j) {
  if (!j) return false;
  const loc = (j.location || '').toLowerCase();
  if (INDIA_CITIES.some(c => loc.includes(c))) return true;
  if (/\b(in|ind|india)\b/i.test(loc)) return true;
  return false;
}

export function isRemoteJob(j) {
  if (!j) return false;
  const loc = (j.location || '').toLowerCase();
  const title = (j.title || '').toLowerCase();
  return ['remote', 'wfh', 'hybrid', 'anywhere', 'work from home'].some(k => loc.includes(k) || title.includes(k));
}

export function formatSalaryBadge(j) {
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
