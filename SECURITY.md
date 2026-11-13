<p align="center">
  <img src="assets/logo.png" alt="Job Hunter Logo" width="100" height="100">
</p>

# Security Policy & Architecture

## Supported Versions

Job Hunter actively maintains and supports the latest stable releases:

| Version | Supported          | Status |
| ------- | ------------------ | ------ |
| 1.2.4   | :white_check_mark: | Current Production Release |
| 1.2.3   | :white_check_mark: | Maintenance Release |
| 1.2.2   | :white_check_mark: | Maintenance Release |
| 1.2.1   | :white_check_mark: | Security Support |
| < 1.2.1 | :x:                | End of Life (Upgrade Recommended) |

---

## Reporting a Vulnerability

**Please do NOT open a public GitHub Issue for security vulnerabilities.**

To report a vulnerability:
1. **GitHub Security Advisory**: Open a private advisory report at [https://github.com/tanish-jain-225/job-hunter/security/advisories/new](https://github.com/tanish-jain-225/job-hunter/security/advisories/new)
2. **Email**: Contact `tanishjain020205@gmail.com` with subject `[SECURITY] Job Hunter Vulnerability Report`.

Please include: affected component, reproduction steps, proof-of-concept, and suggested remediation (if available).

### Response SLA

| Severity | Acknowledgement | Fix Target |
| :--- | :--- | :--- |
| **Critical** | Within 24 hours | 48 hours |
| **High** | Within 48 hours | 7 days |
| **Medium / Low** | Within 72 hours | 30 days |

---

## Security Scope & Component Audit

| Component | File(s) | Threat Vector & Hardening |
| :--- | :--- | :--- |
| **JWT Authentication** | `jobhunt/auth.py` | Token forgery, signature bypass, offline HMAC verification, cache timing attacks |
| **Supabase RLS Isolation** | `jobhunt/memory.py` | Multi-tenant cross-account data leakage, subquery RLS execution |
| **Flask API Endpoints** | `jobhunt/web/routes/` | Command injection, SSRF, unauthorized state mutation |
| **Credential Stripping** | `jobhunt/web/routes/profile.py` | Secret/key storage in candidate profile |
| **URL Protocol Sanitization**| `static/js/app.js` | Malicious pseudo-protocols (`javascript:`, `data:`, `vbscript:`) |
| **Entity-Safe Highlighting** | `static/js/app.js` | HTML entity corruption via regex lookahead `(?![^&]*;)` |
| **LLM Prompt Handling** | `jobhunt/llm.py` | Untrusted job description prompt breakout & prompt injection |
| **ATS HTTP Fetching** | `jobhunt/fetch.py` | SSRF via crafted company slugs & URL scheme filtering |

---

## Security Architecture & Defense-in-Depth

Job Hunter enforces rigorous security controls across every tier of the application stack:

### 1. ATS URL Sanitization & Protocol Whitelisting
- All candidate job application URLs are sanitized via `resolveJobUrl` (`static/js/app.js`), strictly enforcing `http://` and `https://` schemes.
- Malicious URI schemes (`javascript:`, `data:`, `vbscript:`) are rejected and stripped to prevent Cross-Site Scripting (XSS).
- Search input rendering enforces regex entity lookahead `(?![^&]*;)`, preventing search term queries from corrupting escaped HTML character entities.

### 2. Candidate Credential Stripping
- Any data ingested through `POST /api/profile` undergoes recursive parameter filtering.
- Sensitive credential markers (`api_key`, `token`, `secret`, `password`) are automatically stripped before writing to local or remote storage.

### 3. Supabase PostgreSQL Multi-Tenancy & Hardened RLS
- Isolates tenant rows via normalized email claims using subquery-optimized `(select auth.jwt())` checks and `service_role` bypass.
- All DDL executions in [`supabase/schema.sql`](supabase/schema.sql) and [`supabase/teardown.sql`](supabase/teardown.sql) are wrapped in atomic `BEGIN; ... COMMIT;` transaction blocks.
- The `handle_updated_at()` trigger function enforces `SET search_path = public, pg_temp` against search-path injection attacks.
- Foreign keys enforce `ON DELETE CASCADE` across all tables, and RLS policies are consolidated to eliminate redundant per-query evaluation overhead.
- The service-role key is reserved exclusively for the administrative batch worker.

### 4. Complete Endpoint Protection
- All authenticated operational REST API routes enforce `@require_auth`, rejecting unauthenticated requests with HTTP 401 (`UNAUTHORIZED`).
- Public health (`/health`), landing, static assets, and auth-configuration (`/api/auth/config`) routes remain intentionally unauthenticated.

### 5. Offline JWT Signature Verification & Fallback
- Validates Supabase JWT access tokens offline using PyJWT and `SUPABASE_JWT_SECRET` (HMAC-SHA256) with strict issuer (`iss`) and audience (`aud`) claims validation, providing sub-millisecond local verification with zero external network hops and complete immunity to third-party API rate limits on serverless environments.
- If `SUPABASE_JWT_SECRET` is not set, it securely falls back to validating with the Supabase Auth API (`GET /auth/v1/user`) backed by an in-memory TTL cache.

### 6. Resilient Client-Side Session Lifecycle
- Frontend `authFetch` ([`static/js/app.js`](static/js/app.js)) inspects token lifetime (`expires_at`), proactively refreshing nearing tokens (<90s remaining) before request dispatch, and silently retries on any transient 401s before session invalidation, avoiding session drops due to background tab timer throttling or wake-from-sleep.

### 7. Universal View State Isolation
- Unauthenticated visitors are strictly confined to the public landing page.
- Authenticated dashboards (`#dashboard-view`) and metrics (`#header-metrics`) are protected with `.app-view-hidden` (`display: none !important; visibility: hidden !important; pointer-events: none !important;`) with highest CSS precedence across all media queries down to 300px.

### 8. Client-Side Utility Lockout (`checkAuthOrRedirect`)
- All utility triggers (manual sync, on-demand radar runner, tab switching, custom opportunity tracking, custom company additions/deletions, kit inspector, candidate profile settings, resume parser, and `/` search focus) are locked until authenticated.

### 9. Zero-Bleed Session Teardown
- Signing out wipes all in-memory jobs, profile context, DOM elements, and removes cached stats/profiles from `localStorage`.

### 10. Defensive Prompt Injection Mitigation
- All job descriptions evaluated during screening and application kit drafting are sanitized—closing `</untrusted_job_description>` tags are actively stripped to neutralize breakout escape vectors—and encapsulated within `<untrusted_job_description>` XML tags.
- LLM system instructions explicitly command models to treat content within tags purely as evaluation data and ignore any embedded prompt overrides or instructions.

### 11. RFC-Compliant Email Deliverability & Anti-Spoofing
- Outbound career intelligence briefings inject RFC 8058 one-click unsubscribe headers (`List-Unsubscribe: <mailto:...>`, `List-Unsubscribe-Post: List-Unsubscribe=One-Click`), deterministic `Message-ID`, `Date`, `Auto-Submitted: auto-generated`, and `Precedence: bulk` to eliminate spam triggers and preserve inbox placement.

### 12. Dynamic Asset Hashing & Cache-Busting
- The web backend registers an `asset_hash(filename)` template context processor derived from static file modification timestamps, preventing clients from running stale JavaScript or CSS files following production deployments while maintaining HTTP cacheability.

### 13. Thread-Safe Multi-Tenant API Key Propagation
- Candidate-specific API keys are passed directly through function call stacks rather than mutating process-level `os.environ["GEMINI_API_KEY"]`, guaranteeing strict thread safety and eliminating cross-tenant key leakage during concurrent web worker requests.

### 14. Header-Based Secret Transport
- Google Gemini API requests transport credentials exclusively via HTTP request headers (`x-goog-api-key`) rather than URL query parameters, preventing secret exposure in proxy server logs, browser histories, or HTTP referrers.

### 15. Content Security Policy (CSP) & Hardened HTTP Headers
The Flask backend (`jobhunt/web/__init__.py`) enforces strict HTTP security headers on all responses:
- **Content-Security-Policy**: Restricts script sources; explicitly whitelists trusted CDNs and official preview endpoints (`https://job-hunter-web-board.vercel.app`).
- **X-Content-Type-Options**: `nosniff` prevents MIME confusion attacks.
- **X-Frame-Options**: `DENY` prevents UI redressing/clickjacking.
- **Strict-Transport-Security**: HSTS enforced in production.
- **Referrer-Policy**: `strict-origin-when-cross-origin`.

### 16. Cryptographic Reactive Store Versioning & Exception Masking
- `get_store_version()` computes deterministic SHA-256 tokens over application stages, candidate notes, fit scores, and timestamps for tamper-proof, zero-refresh multi-tab reactivity.
- In production environments (`VERCEL=1` or `FLASK_ENV=production`), unhandled runtime exceptions trigger generic error responses (`{"status": "error", "message": "An internal error occurred"}`), suppressing system internals and stack traces.

---

## Related Documentation

- **[Product Audit & Valuation](docs/PRODUCT_ANALYSIS_WALKTHROUGH.md)** — Definitive India-first product audit, 2026 hiring research, hackathon evaluation & SaaS valuation.
- **[System Architecture](docs/ARCHITECTURE.md)** — System architecture, module breakdown, and data pipelines.
- **[Setup Guide](docs/SETUP.md)** — Step-by-step local and production setup.
- **[Deployment Guide](docs/DEPLOYMENT.md)** — Free-tier cloud production deployment on Vercel and Supabase.
- **[REST API Reference](docs/API.md)** — Complete REST API reference.
- **[Changelog](CHANGELOG.md)** — Release history and notable changes.
- **[Release Notes](RELEASE_NOTES.md)** — Detailed v1.2.4 release notes.
- **[README.md](README.md)** — Project homepage.
