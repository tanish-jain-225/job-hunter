# 🚀 Release Notes — Job Hunter

<p align="center">
  <a href="https://github.com/tanish-jain-225/job-hunter/releases/tag/v1.2.0"><img src="https://img.shields.io/badge/Release-v1.2.0-0ea5e9?style=for-the-badge&logo=github&logoColor=white" alt="Latest Release v1.2.0"></a>
  <a href="https://github.com/tanish-jain-225/job-hunter/actions"><img src="https://img.shields.io/badge/tests-604%20passed-success?style=for-the-badge&logo=pytest&logoColor=white" alt="Tests"></a>
  <a href="https://github.com/tanish-jain-225/job-hunter"><img src="https://img.shields.io/badge/coverage-92%25-brightgreen?style=for-the-badge&logo=pytest&logoColor=white" alt="Coverage"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version"></a>
</p>

> **Current Production Version**: `v1.2.0` | **Release Date**: November 12, 2026
>
> **Quick Links**: [GitHub Release v1.2.0](https://github.com/tanish-jain-225/job-hunter/releases/tag/v1.2.0) &bull; [Changelog](CHANGELOG.md) &bull; [Product Audit & Valuation](docs/PRODUCT_ANALYSIS_WALKTHROUGH.md) &bull; [System Architecture](docs/ARCHITECTURE.md) &bull; [Live Demo](https://job-hunter-web-board.vercel.app)

---

## [v1.2.0] - 2026-11-12

### ♻️ 2,300-Job Anti-Repeat Memory (`seen_archive`) — Zero DB Schema Changes
* **Compact 2,000-Entry FIFO Digest Archive**: When unapplied jobs above the `300`-row UI cap (`MAX_TRACKED_JOBS_COUNT`) are pruned to keep free Supabase PostgreSQL compact, evicted `job_id`s are hashed into 12-hex-char SHA-1 digests inside existing `user_profiles.profile_json["seen_archive"]` (capped FIFO at `MAX_SEEN_ARCHIVE_COUNT=2000`, `<= 24 KB/user`) plus atomic local `_archive.txt` fallback.
* **Zero Extra DB Reads & Zero Idle Writes**: Pipeline callers (`multi.py`, `cli.py`, `pipeline.py`) pass already-loaded `seen_archive` via `extract_seen_archive()`, and `Store.save()` writes to Supabase **only when rows are evicted** (`purged > 0`), while `sanitize_profile_for_response` strips `seen_archive` from browser payloads.

### ⚡ Zero-Cost 300+ DAU & Codeless Autoscaling
* **Balanced Free-Tier Engineering**: Uses `45s` in-memory profile/job cache TTL, profile-first `/api/sync`, `60s` idle-aware UI heartbeat & `5s` cloud poller, `300`-row default unapplied cap (applied/interviewing/offer/rejected jobs preserved forever), pip-cached `daily.yml` with `JOBHUNT_ATS_DISK_CACHE=1` & `360m` runtime limit.
* **Automatic Paid-Tier Scale Without Code Edits**: AIMD adaptive per-key throttling (`5.0s -> 0.05s` on HTTP 200, backoff on HTTP 429), PostgREST >1,000-row pagination across `user_profiles` and `user_tracked_jobs`, concurrent multi-tenant batch workers with shared LLM/SMTP quota circuit breakers & BYOK isolation, and env-configurable `MAX_DAILY_SEND=50000`.
* **604 Passing Tests & Hardened Playwright E2E**: Expanded `tests/test_zero_cost_scaling.py` to 13 scaling/archive tests and hardened `tests/test_browser_playwright.py` with threaded WSGI servers, module-scoped Chromium reuse, and bounded timeouts (**604 passed**, **92%+ coverage**, 0 Ruff issues, 0 Mypy issues).

---

## [v1.1.8] - 2026-11-12

### 🌐 End-to-End Headless Playwright Browser Test Suite
* **Automated Browser Verification**: Added a dedicated Playwright Chromium browser test suite in `tests/test_browser_playwright.py` with 100% pass rate across 7 tests:
  - `test_landing_page_unauthenticated_render`: Verifies unauthenticated landing hero elements, seamless authentication tab switching (Sign In vs. Sign Up), and asserts zero browser console/page errors.
  - `test_dashboard_flow_profile_wizard_and_save`: Exercises the multi-step onboarding wizard end-to-end, filling candidate profile information, headline professional title, and verifying storage persistence and UI sync.
  - `test_tracker_search_filter_and_chips`: Tests reactive search query filtering, ATS source chips (`greenhouse`, `lever`), and search input clearing.
  - `test_modal_overlay_escape_behavior`: Validates modal accessibility, Escape keyboard dismissal, and backdrop click closures.
  - `test_jobs_search_filter_and_export_flow`: Validates live query filtering, ATS source tagging, and client CSV export triggering.
  - `test_onboarding_wizard_and_profile_sync`: Validates multi-step profile wizard navigation, live validation, and state sync.
  - `test_profile_and_settings_full_lifecycle`: Exercises the complete profile lifecycle, resume parsing integration, preference updates, and account reset.

### 🛡️ Security, Privacy & Protocol Hardening
* **Strict Blank-State Privacy & Supabase Isolation**: Enforced email-only initial and reset state via `create_blank_profile` (`jobhunt/memory_codec.py`), blocked local `profile.json` fallback during configured Supabase `POST /api/resume/upload` calls (`jobhunt/web/routes/profile.py`), removed email-prefix name synthesis (`jobhunt/digest.py`, `jobhunt/multi.py`), and consolidated credential-stripping & field normalization.
* **Network, Header & Database Hardening**: Added CRLF header injection guards in `jobhunt/mailer.py`, strict SSRF/URL/slug checks across `jobhunt/parsers/`, `jobhunt/fetch.py`, `jobhunt/verify.py`, and `jobhunt/web/routes/jobs.py`, COOP/HSTS headers in `jobhunt/web/__init__.py`, unified rate limiting via `enforce_rate_limit`, and 3 `lower(email)` RLS indexes in `supabase/schema.sql`.
* **Protocol Whitelisting**: Hardened `resolveJobUrl()` in `static/js/app.js` to strictly reject malicious `javascript:`, `data:`, and `vbscript:` pseudo-protocol URLs, shielding candidates from script injection when opening external application links.
* **HTML Entity-Safe Highlighting**: Updated `highlightText()` in `static/js/app.js` with regex entity lookahead `(?![^&]*;)`, preventing search term matches from corrupting escaped HTML character entities like `&amp;` and `&quot;`.
* **Content Security Policy (CSP)**: Enhanced CSP configuration in `jobhunt/web/__init__.py` to whitelist official preview assets from `https://job-hunter-web-board.vercel.app` without browser console warnings.
* **Credential Stripping**: Added automatic security filtering to `POST /api/profile` to strip sensitive credential keys (`api_key`, `token`, `secret`, `password`) before writing to persistent storage.

### 🧩 UI Stability, Accessibility & Modal Lifecycle Improvements
* **WCAG Modal Accessibility & Repo Cleanup**: Added dialog ARIA attributes and keyboard focus trapping (`activateModalFocus` / `deactivateModalFocus`) across all modal overlays, `prefers-reduced-motion` support in `static/css/style.css`, aligned `8.0s` Vercel / `14.0s` standard upload extraction timeouts, removed dead legacy `static/js/modules/` stubs, and synchronized all documentation cleanly.
* **Resolved Critical Script Deadlock**: Identified and fixed an unmatched brace syntax error in `static/js/app.js` (`populateSection2FromProfile`) that halted `DOMContentLoaded` compilation and froze the dashboard interface.
* **Clean 3-Step Profile Wizard Lifecycle**: Consolidated the profile save action strictly at the end of the 3-step setup flow (`#btn-profile-save` in Step 3: Alert Settings), removing redundant intermediary save triggers from Step 2 to guarantee a smooth, unambiguous candidate onboarding flow.
* **Form Button Explicit Typing**: Explicitly assigned `type="button"` and `id="profile-next-2"` to modal wizard buttons in `templates/partials/profile_settings.html`, preventing unintended form submission triggers.
* **Test Isolation via Conftest**: Added an autouse `isolate_profile_file` fixture in `tests/conftest.py` ensuring `profile.json` on disk is preserved and restored cleanly across test sessions.
* **Documentation Unification**: Eliminated redundant markdown files (`docs/CHANGELOG.md` and `docs/SECURITY.md`), consolidating canonical policies into root `CHANGELOG.md` and `SECURITY.md`, and verifying all 205 markdown cross-links with 0 broken references.

### 🧪 Diagnostic & Edge-Case Coverage Expansion
* **Preflight Diagnostics (100% Coverage)**: Added comprehensive unit tests in `tests/test_preflight.py` covering all healthy environments, missing or corrupt YAML, missing dependencies, Python version checks, and permission diagnostics.
* **Mailer Resilience (94% Coverage)**: Expanded `tests/test_digest_mailer.py` with SMTP session reconnection tests, connection reuse, daily rate-limit circuit breakers, and plain-text fallback generation.
* **Custom Target Companies & API Edge Cases**: Created `tests/test_custom_companies_and_edge_cases.py` testing URL detection, board accessibility validation, and store update error handling across `jobs.py` (92% coverage) and `profile.py` (86% coverage).
* **Model-First Multi-Key Rotation & 07:37 IST Schedule**: Hardened LLM resilience so each model rotates across all project API keys before cascading, scopes cooldowns cleanly per `(key, model)` without infinite provider failover loops, falls back to keyword scoring in multi-user runs when LLM pools exhaust, and runs the daily GitHub Actions cron at **07:37 AM IST**.
* **591 Passing Tests**: Expanded suite coverage to **591 automated tests** with **92% global statement coverage**, zero Ruff lint errors, and zero Mypy type issues.

---

## [v1.1.7] - 2026-10-30

### 🛡️ Profile & Search Criteria Autofill Save Isolation
* **Strict State Isolation**: Fixed premature dashboard and `localStorage` mutations where uploading or auto-filling a resume immediately overwrote the candidate profile card and cached data before the user clicked "Save Profile".
* **Unsaved Changes Cleanup**: If the settings modal is dismissed or canceled without saving, form fields automatically revert to confirmed saved state (`activeProfileData`), preventing unsaved edits from polluting the active session.
* **Single Authoritative Save Path**: `saveProfilePreferences()` is established as the sole authorized method to persist changes to Supabase PostgreSQL (`POST /api/profile`), write to `localStorage`, and update dashboard indicators.
* **Direct Step 2 Save Action**: Added a direct "Save Changes" button in Step 2 of the settings modal alongside "Next: Alert Settings", giving candidates the flexibility to save search criteria immediately.

### 👤 Visible Headline Professional Title & Clean Autofill Logic
* **Visible Headline Title Input**: Replaced the hidden `<input type="hidden" id="prof-title">` in `profile_settings.html` with a prominent, visible input arranged side-by-side with Candidate Name, followed by dedicated Target Job Titles. Candidates can now view, customize, and edit their primary headline title (e.g., "Senior Software Engineer").
* **Elimination of Speculative Role Injection**: Removed hardcoded heuristics in `populateSection2FromProfile` that forcefully injected generic roles (`Full Stack Developer`, `Frontend Engineer`, `Software Engineer`, `Backend Engineer`, `AI Engineer`) upon detecting any programming language keyword. The parser now preserves genuine, AI-extracted target titles.
* **Smart Fallback Name & YoE Parser**: Upgraded the local fallback parser in `profile.py` with regex experience extraction (`r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)"`) to accurately derive YoE, seniority (`entry`, `mid`, `senior`), and experience level (`0-1`, `1-3`, `3-5`, `5+`), avoiding default `0.0` years.
* **Clean Candidate Name Derivation**: Preserves existing profile names, eliminates digits from username fallbacks, and filters out resume header markers ("Resume", "CV", URLs, email addresses).

### 🎯 Candidate Profile & Interactive Search Bar Synchronization
* **Interactive Skill Chips**: Rendered skills on the Candidate Profile summary card with clickable styling (`clickable-skill-chip`) and hover states. Clicking any skill chip (or the headline title) instantly switches to the **Interactive Job Board**, fills the search bar, displays the clear button, and filters open listings.
* **Expanded Search Matching**: Upgraded `/api/jobs?search=` to search across **skills**, **fit reasons / match notes**, and **tags**, in addition to company name, title, location, and ATS provider.
* **Session-Scoped Search**: Migrated search persistence from permanent `localStorage` to `sessionStorage` (`STORAGE_KEYS.SEARCH_QUERY`), preventing stale queries from locking the job board across fresh browser sessions while retaining deep-link support (`?search=...`).

### ⚡ AI Parsing Resilience & Atomic Stage Persistence
* **Adaptive Serverless AI Extraction**: Resilient multi-tier JSON parser with comment stripping, unclosed brace repair, trailing comma correction, and Python literal parsing.
* **Atomic Job Lifecycle Mutations**: Atomic stage transitions (`to_apply` $\rightarrow$ `applied` $\rightarrow$ `interviewing` $\rightarrow$ `offer` $\rightarrow$ `rejected`) with rollbacks on remote failures and automatic CSV export sync.
* **Application Kit Notes & Outreach Sync**: Tailored cold outreach templates, referral messages, and cover notes seamlessly bound to each tracked job item.

### 🧪 Test Suite & Quality Assurance
* **525 Passing Tests**: Full test suite across CLI, store, API routes, security headers, hypothesis property testing, and E2E live mocks.
* **100% Code Quality Standards**: Zero Ruff linting errors and zero Mypy type issues across 43 source files.

---

## [v1.0.7] - 2026-10-29

### ⚡ Adaptive Serverless AI Extraction Timeouts
* **Zero 504 Gateway Timeouts on Vercel**: Dynamically bounds candidate resume AI extraction to 8.0s on Vercel serverless (`VERCEL=1`) and 14.0s on standard/local servers in `jobhunt/web/routes/profile.py`.
* **Graceful Deterministic Fallback**: Built-in deterministic local regex parser activates if upstream LLM experiences rate limits (HTTP 429), capacity errors (HTTP 503), or exceeds timeout ceilings.

### 🖼️ Multi-Location Static Asset Fallback Cascade
* **100% Asset Delivery Guarantee**: Upgraded `serve_logo()` and `serve_favicon()` in `jobhunt/web/routes/views.py` with a 4-tier directory search cascade (`static/assets/`, `assets/`, `static/`, root) and MIME type resolution (`image/png`, `image/x-icon`, `image/svg+xml`).
* Eliminates 404s for brand marks and favicons across local dev, Docker containers, and Vercel serverless deployments.

### ⚙️ Dynamic Multi-Provider GitHub Actions Daily Workflow
* **Multi-Provider Repository Secrets**: Enhanced `.github/workflows/daily.yml` to accept `GROQ_API_KEY`, `ANTHROPIC_API_KEY`, and custom model overrides (`SCREEN_MODEL`, `DRAFT_MODEL`).
* **Dynamic Secret Fallback**: Configured `${{ secrets.LLM_PROVIDER || 'gemini' }}`, allowing users to switch AI backends purely via repository secrets with zero code modifications.

---

## [v1.0.6] - 2026-10-28

* **Market Research Grounding**: Grounded documentation, ATS support list, and scoring methodology against 2026 production standards.
* **Dependency Synchronization**: Synchronized `uv.lock` and pinned `hypothesis` for Python 3.10+ compatibility.
