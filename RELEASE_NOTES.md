# 🚀 Release Notes — Job Hunter

<p align="center">
  <a href="https://github.com/tanish-jain-225/job-hunter/releases/tag/v1.1.8"><img src="https://img.shields.io/badge/Release-v1.1.8-0ea5e9?style=for-the-badge&logo=github&logoColor=white" alt="Latest Release v1.1.8"></a>
  <a href="https://github.com/tanish-jain-225/job-hunter/actions"><img src="https://img.shields.io/badge/tests-583%20passed-success?style=for-the-badge&logo=pytest&logoColor=white" alt="Tests"></a>
  <a href="https://github.com/tanish-jain-225/job-hunter"><img src="https://img.shields.io/badge/coverage-92%25-brightgreen?style=for-the-badge&logo=pytest&logoColor=white" alt="Coverage"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version"></a>
</p>

> **Current Production Version**: `v1.1.8` | **Release Date**: November 1, 2026
>
> **Quick Links**: [GitHub Release v1.1.8](https://github.com/tanish-jain-225/job-hunter/releases/tag/v1.1.8) &bull; [Changelog](CHANGELOG.md) &bull; [Product Audit & Valuation](docs/PRODUCT_ANALYSIS_WALKTHROUGH.md) &bull; [System Architecture](docs/ARCHITECTURE.md) &bull; [Live Demo](https://job-hunter-web-board.vercel.app)

---

## [v1.1.8] - 2026-11-01

### 🌐 End-to-End Headless Playwright Browser Test Suite
* **Automated Browser Verification**: Added a dedicated Playwright Chromium browser test suite in `tests/test_browser_playwright.py` with 100% pass rate across 7 tests:
  - `test_landing_page_unauthenticated_render`: Verifies unauthenticated landing hero elements, seamless authentication tab switching (Sign In vs. Sign Up), and asserts zero browser console/page errors.
  - `test_dashboard_flow_profile_wizard_and_save`: Exercises the multi-step onboarding wizard end-to-end, filling candidate profile information, headline professional title, and verifying storage persistence and UI sync.
  - `test_tracker_search_filter_and_chips`: Tests reactive search query filtering, ATS source chips (`greenhouse`, `lever`), and search input clearing.
  - `test_modal_overlay_escape_behavior`: Validates modal accessibility, Escape keyboard dismissal, and backdrop click closures.
  - `test_jobs_search_filter_and_export_flow`: Validates live query filtering, ATS source tagging, and client CSV export triggering.
  - `test_onboarding_wizard_and_profile_sync`: Validates multi-step profile wizard navigation, live validation, and state sync.
  - `test_profile_and_settings_full_lifecycle`: Exercises the complete profile lifecycle, resume parsing integration, preference updates, and account reset.

### 🛡️ Security Hardening & Protocol Sanitization
* **Protocol Whitelisting**: Hardened `resolveJobUrl()` in `static/js/app.js` to strictly reject malicious `javascript:`, `data:`, and `vbscript:` pseudo-protocol URLs, shielding candidates from script injection when opening external application links.
* **HTML Entity-Safe Highlighting**: Updated `highlightText()` in `static/js/app.js` with regex entity lookahead `(?![^&]*;)`, preventing search term matches from corrupting escaped HTML character entities like `&amp;` and `&quot;`.
* **Content Security Policy (CSP)**: Enhanced CSP configuration in `jobhunt/web/__init__.py` to whitelist official preview assets from `https://job-hunter-web-board.vercel.app` without browser console warnings.
* **Credential Stripping**: Added automatic security filtering to `POST /api/profile` to strip sensitive credential keys (`api_key`, `token`, `secret`, `password`) before writing to persistent storage.

### 🧩 UI Stability & Modal Lifecycle Improvements
* **Resolved Critical Script Deadlock**: Identified and fixed an unmatched brace syntax error in `static/js/app.js` (`populateSection2FromProfile`) that halted `DOMContentLoaded` compilation and froze the dashboard interface.
* **Clean 3-Step Profile Wizard Lifecycle**: Consolidated the profile save action strictly at the end of the 3-step setup flow (`#btn-profile-save` in Step 3: Alert Settings), removing redundant intermediary save triggers from Step 2 to guarantee a smooth, unambiguous candidate onboarding flow.
* **Form Button Explicit Typing**: Explicitly assigned `type="button"` and `id="profile-next-2"` to modal wizard buttons in `templates/partials/profile_settings.html`, preventing unintended form submission triggers.
* **Test Isolation via Conftest**: Added an autouse `isolate_profile_file` fixture in `tests/conftest.py` ensuring `profile.json` on disk is preserved and restored cleanly across test sessions.
* **Documentation Unification**: Eliminated redundant markdown files (`docs/CHANGELOG.md` and `docs/SECURITY.md`), consolidating canonical policies into root `CHANGELOG.md` and `SECURITY.md`, and verifying all 205 markdown cross-links with 0 broken references.

### 🧪 Diagnostic & Edge-Case Coverage Expansion
* **Preflight Diagnostics (100% Coverage)**: Added comprehensive unit tests in `tests/test_preflight.py` covering all healthy environments, missing or corrupt YAML, missing dependencies, Python version checks, and permission diagnostics.
* **Mailer Resilience (94% Coverage)**: Expanded `tests/test_digest_mailer.py` with SMTP session reconnection tests, connection reuse, daily rate-limit circuit breakers, and plain-text fallback generation.
* **Custom Target Companies & API Edge Cases**: Created `tests/test_custom_companies_and_edge_cases.py` testing URL detection, board accessibility validation, and store update error handling across `jobs.py` (92% coverage) and `profile.py` (86% coverage).
* **583 Passing Tests**: Codebase test count expanded to **583 automated tests** (576 unit/integration + 7 browser E2E) with **92% global statement coverage**, zero Ruff lint errors, and zero Mypy type issues across 43 source files.

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
