<p align="center">
  <img src="../assets/logo.png" alt="Job Hunter Logo" width="100" height="100">
</p>

# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | Yes (actively supported) |
| < 1.0   | No (end of life)    |

---

## Reporting a Vulnerability

**Please do NOT open a public GitHub Issue for security vulnerabilities.**

Open a GitHub Security Advisory: https://github.com/tanish-jain-225/job-hunter/security/advisories/new

Include: affected component, steps to reproduce, potential impact, suggested fix (optional).

### Response SLA

| Severity | Acknowledgement | Fix Target |
|----------|----------------|------------|
| Critical | 24 hours | 48 hours |
| High | 48 hours | 7 days |
| Medium/Low | 72 hours | 30 days |

---

## Security Scope

| Component | File(s) | Risk Area |
|-----------|---------|-----------|
| JWT Authentication | `jobhunt/auth.py` | Token forgery, bypass, cache timing |
| Supabase RLS Isolation | `jobhunt/memory.py` | Cross-tenant data leakage |
| Flask API Endpoints | `jobhunt/web/routes/` | Injection, auth bypass |
| Credential Loading | `jobhunt/cli.py` | Secret leakage |
| LLM Prompt Handling | `jobhunt/llm.py` | Prompt injection via JDs |
| ATS HTTP Fetching | `jobhunt/fetch.py` | SSRF via crafted company slugs |

---

## Security Architecture

- **Supabase PostgreSQL Multi-Tenancy & Hardened RLS**: Isolates tenant rows via normalized email claims using subquery-optimized `(select auth.jwt())` checks and `service_role` bypass. All DDL executions in [`supabase/schema.sql`](../supabase/schema.sql) and [`supabase/teardown.sql`](../supabase/teardown.sql) are wrapped in atomic `BEGIN; ... COMMIT;` transaction blocks. The `handle_updated_at()` trigger function enforces `SET search_path = public, pg_temp` against search-path injection attacks. Foreign keys enforce `ON DELETE CASCADE` across all tables, and RLS policies are consolidated to eliminate redundant per-query evaluation overhead. The service-role key is reserved exclusively for the admin batch worker.
- **Complete Endpoint Protection**: All authenticated operational REST API routes enforce `@require_auth`, rejecting unauthenticated requests with HTTP 401 (`UNAUTHORIZED`). Public health, landing, asset, and auth-configuration routes remain intentionally unauthenticated.
- **Universal View State Isolation**: Unauthenticated visitors are confined to the public landing page. Authenticated dashboards (`#dashboard-view`) and metrics (`#header-metrics`) are protected with `.app-view-hidden` (`display: none !important; visibility: hidden !important; pointer-events: none !important;`) with highest CSS precedence across all media queries down to 300px.
- **Client-Side Utility Lockout (`checkAuthOrRedirect`)**: All utility triggers (manual sync, on-demand radar runner, tab switching, custom opportunity tracking, custom company additions/deletions, kit inspector, candidate profile settings, resume parser, and `/` search focus) are locked until authenticated.
- **Zero-Bleed Session Teardown**: Signing out wipes all in-memory jobs, profile context, DOM elements, and removes cached stats/profiles from `localStorage`.
- **Header-Based Secret Transport**: Google Gemini API requests transport credentials exclusively via HTTP request headers (`x-goog-api-key`) rather than URL query parameters, preventing secret exposure in proxy server logs, browser histories, or HTTP referrers.
- **Cryptographic Reactive Store Versioning**: `get_store_version()` computes deterministic SHA-256 tokens over application stages, candidate notes, fit scores, and timestamps for tamper-proof, zero-refresh multi-tab reactivity and state cache validation.
- **Production Exception Masking**: In production environments (`VERCEL=1` or `FLASK_ENV=production`), unhandled runtime exceptions trigger a generic error response (`{"status": "error", "message": "An internal error occurred"}`), completely suppressing runtime tracebacks and system internals from client-facing responses.
- **Tokens never accepted via query string** — accepted through `Authorization: Bearer` headers or supported Supabase cookies. The browser Supabase client currently persists its session in browser storage, so a strong CSP and trusted frontend dependencies remain important.
- **Rate limiting** via `flask-limiter`: 5 calls/hour on `/api/run`, 500/hour global default when installed. The default in-memory limiter is per process, not a distributed quota system.
- **Cookie mutation protection**: State-changing requests authenticated through cookies are checked against the same-origin `Origin` or `Referer`.
- **Upload validation**: Production PDF uploads must begin with the `%PDF-` signature and remain bounded by Flask's 16 MB request limit.
- **XSS protection**: Digest content escaped via `html.escape()`. Jinja2 auto-escaping enabled.
- **Content-Security-Policy** headers applied to all responses.
