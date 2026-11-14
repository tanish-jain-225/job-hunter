# 🚀 Release Notes — Job Hunter

<p align="center">
  <a href="https://github.com/tanish-jain-225/job-hunter/releases/tag/v1.2.5"><img src="https://img.shields.io/badge/Release-v1.2.5-0ea5e9?style=for-the-badge&logo=github&logoColor=white" alt="Latest Release v1.2.5"></a>
  <a href="https://github.com/tanish-jain-225/job-hunter/actions"><img src="https://img.shields.io/badge/tests-650%20passed-success?style=for-the-badge&logo=pytest&logoColor=white" alt="Tests"></a>
  <a href="https://github.com/tanish-jain-225/job-hunter"><img src="https://img.shields.io/badge/coverage-92%25-brightgreen?style=for-the-badge&logo=pytest&logoColor=white" alt="Coverage"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version"></a>
</p>

> **Current Production Version**: `v1.2.5` | **Release Date**: November 14, 2026
>
> **Quick Links**: [GitHub Release v1.2.5](https://github.com/tanish-jain-225/job-hunter/releases/tag/v1.2.5) &bull; [Changelog](CHANGELOG.md) &bull; [Product Audit & Valuation](docs/PRODUCT_ANALYSIS_WALKTHROUGH.md) &bull; [System Architecture](docs/ARCHITECTURE.md) &bull; [Live Demo](https://job-hunter-web-board.vercel.app)

---

## [v1.2.5] - 2026-11-14

### 🏹 Optimized Cloud Radar Automation & 24-Hour Quota Synchronization (`.github/workflows/daily.yml`)
* **Synchronized 01:47 PM IST Execution (`cron: '17 8 * * *'`)**:
  - Re-scheduled daily automated radar workflow to **`08:17 UTC` (`01:47 PM IST`)**, executing 17 minutes after the Google Gemini API daily 1,500 RPD quota reset at Midnight US Pacific Time (`08:00 UTC` / `01:30 PM IST` PST).
  - Guarantees 100% fresh daily quota allocations across all third-party services (Gemini AI Studio, Gmail SMTP 24h rolling send window, and UTC cloud quotas).
  - Utilizes eccentric prime minute offset (`:17`) to evade GitHub Actions runner queue spikes at `:00`, `:15`, and `:30`, ensuring instant runner provisioning.
  - Aligns digest delivery with Indian recruiter active afternoon review windows (02:00 PM – 04:00 PM IST) for maximum application response rates.

### 💾 Profile Settings State Preservation & Multi-Tenant Persistence
* **Complete Narrative & Contact Field Persistence (`jobhunt/memory.py`, `jobhunt/memory_codec.py`, `jobhunt/web/routes/profile.py`)**:
  - Full persistence of candidate contact and narrative fields: Phone, Candidate Email, LinkedIn, GitHub, Profile Summary, Profile Text, and Graduation Year across sessions.
  - Bidirectional serialization in both local storage (`profile.json`) and cloud database (`Supabase`), guaranteeing that settings are permanently preserved across reloads and multi-day visits.
* **Smart AI Extraction & Regex Fallbacks (`jobhunt/llm.py`, `jobhunt/llm_utils.py`)**:
  - Regex fallbacks for Indian CTC representations (`14 LPA`, `Fixed CTC: 12 Lacs`) and notice periods (`immediate`, `15_days`, `30_days`, `60_days`, `90_days`) when LLMs return 0 or unparsed values.
  - Relaxed Indian phone regex supporting formatted and hyphenated numbers (e.g. `+91 70213 41948`, `+91-98765-43210`).
  - Single-line education parser extracting degree, college name, and graduation year with high fidelity.
  - Accurate calculation of timeline Years of Experience (YoE) treating Graduate Engineer Trainees as salaried full-time experience.
* **Modernized Settings UI (`templates/partials/profile_settings.html`, `static/js/app.js`)**:
  - Dedicated Step 2 input controls for Phone (`#prof-phone`), LinkedIn (`#prof-linkedin`), GitHub (`#prof-github`), and Summary (`#prof-summary`).
  - Consolidated single Save action (`#btn-profile-save`) strictly on the final step (Step 3: Alert Settings), guaranteeing unambiguous, atomic persistence.
  - Accurate form hydration preserving fresher values (`0` YoE and `0` CTC) and eliminating unwanted title exclusions.

### 🌐 Universal Multi-Domain Career Intelligence Engine (India-First & Global)
* **Universal Multi-Domain Role Synthesis (`jobhunt/llm_utils.py`)**: Dynamically identifies professional domains across 10 major career disciplines without hardcoded single-domain limitations:
  - Product Management, UI/UX Design, Data & Business Intelligence, AI & Machine Learning, Growth & Marketing, Sales & BD, Finance & Accounting, HR & Talent, Operations & Project Management, Legal & Compliance, and Engineering.
* **CI Preflight Hardening**:
  - Mocked external LLM preflight requirements in CI unit tests (`test_build_profile_ctc_and_notice_period_fallback`) ensuring 100% green builds across GitHub Actions runners.
  - Non-blocking Playwright test execution with automatic environment detection.
* **Automated Test Suite Certified**:
  - **650 passed tests** (643 unit/integration + 7 Playwright E2E) with 92% statement coverage, 0 Ruff violations, and 0 Mypy type errors across 43 source files.

---

## [v1.2.4] - 2026-11-13

### 🌟 Unified All-in-One Quality, Type, Test & Coverage Pipeline (`run_tests.py`)
* **Single-Command Pipeline**: Runs all 4 quality verification gates in one command (`python run_tests.py` or `scripts/test.bat` / `scripts/test.sh`):
  1. **Gate 1 (Ruff)**: Strict code quality and style linting (`ruff check .`) with 0 errors across repository.
  2. **Gate 2 (Mypy)**: Exhaustive static type analysis (`mypy jobhunt`) across all 43 core source files with 0 type errors.
  3. **Gate 3 (Pytest)**: Full automated test suite (**650 passed tests**: 643 unit/integration + 7 Playwright E2E).
  4. **Gate 4 (Code Coverage)**: Complete line coverage calculation with `pytest-cov` reporting missing lines and supporting `--cov-fail-under=90`, `--cov-html`, and `--cov-xml`.
* **Verification Dashboard**: Generates an executive terminal summary table displaying real-time duration and status per gate.
* **Runner Unit Tests (`tests/test_unified_runner.py`)**: Added 14 unit tests validating the runner CLI flags, error propagation, and reporting.

### 💾 Profile Settings State Preservation & Multi-Tenant Persistence
* **Complete Narrative & Contact Field Persistence (`jobhunt/memory.py`, `jobhunt/memory_codec.py`, `jobhunt/web/routes/profile.py`)**:
  - Full persistence of candidate contact and narrative fields: Phone, Candidate Email, LinkedIn, GitHub, Profile Summary, Profile Text, and Graduation Year across sessions.
  - Bidirectional serialization in both local storage (`profile.json`) and cloud database (`Supabase`), guaranteeing that settings are permanently preserved across reloads and multi-day visits.
* **Smart AI Extraction & Regex Fallbacks (`jobhunt/llm.py`, `jobhunt/llm_utils.py`)**:
  - Regex fallbacks for Indian CTC representations (`14 LPA`, `Fixed CTC: 12 Lacs`) and notice periods (`immediate`, `15_days`, `30_days`, `60_days`, `90_days`) when LLMs return 0 or unparsed values.
  - Relaxed Indian phone regex supporting formatted and hyphenated numbers (e.g. `+91 70213 41948`, `+91-98765-43210`).
  - Single-line education parser extracting degree, college name, and graduation year with high fidelity.
  - Accurate calculation of timeline Years of Experience (YoE) treating Graduate Engineer Trainees as salaried full-time experience.
* **Modernized Settings UI (`templates/partials/profile_settings.html`, `static/js/app.js`)**:
  - Dedicated Step 2 input controls for Phone (`#prof-phone`), LinkedIn (`#prof-linkedin`), GitHub (`#prof-github`), and Summary (`#prof-summary`).
  - Consolidated single Save action (`#btn-profile-save`) strictly on the final step (Step 3: Alert Settings), guaranteeing unambiguous, atomic persistence.
  - Accurate form hydration preserving fresher values (`0` YoE and `0` CTC) and eliminating unwanted title exclusions.
* **CI Preflight Hardening & Cloud Scheduler Optimization**:
  - Re-scheduled daily GitHub Actions automated radar (`.github/workflows/daily.yml`) to **`08:17 UTC` (`01:47 PM IST`)** via `cron: '17 8 * * *'`, optimizing for the 24-hour Gemini API quota renewal window (1:30 PM IST) and evading runner queue congestion.
  - Mocked external LLM preflight requirements in CI unit tests (`test_build_profile_ctc_and_notice_period_fallback`) ensuring 100% green builds across GitHub Actions runners.
  - Non-blocking Playwright test execution with automatic environment detection.

### 🎯 High-Precision Resume Parsing & Smart Profile Ingestion Engine
* **PDF Annotation Hyperlink Extraction (`jobhunt/llm_utils.py`)**: Inspects PDF `/Annots` dictionaries to capture hyperlinks (GitHub, LinkedIn, Portfolio demos) that text extractors discard.
* **Bounded Degree Matching (`parse_education_smart`)**: Enforces word boundaries and clean tokens to prevent false positives (e.g., `mba` false positive matching `Mumbai`). Extracts degree, institution, graduation year, and CGPA accurately.
* **Smart Project Extraction (`parse_projects_smart`)**: Isolates project titles, tech stack keywords, and quantifiable deliverables directly from resume bodies.
* **Corridor Location Detection (`detect_preferred_locations_smart`)**: Maps sub-metro tech corridors into primary metros (Dombivli $\rightarrow$ Mumbai, Whitefield $\rightarrow$ Bengaluru, Hinjewadi $\rightarrow$ Pune, Cyberabad $\rightarrow$ Hyderabad, Noida $\rightarrow$ Delhi-NCR).
* **Smart Contact & Token Cleaning**: Unglues glued tokens, spaces bullet symbols, cleans telephone/email formats, and extracts user profiles from URLs.

### 🌐 Universal Multi-Domain Career Intelligence Engine (India-First & Global)
* **Universal Multi-Domain Role Synthesis (`jobhunt/llm_utils.py`)**: Dynamically identifies professional domains across 10 major career disciplines without hardcoded single-domain limitations:
  - **Product Management**: PRDs, Roadmapping, User Stories, A/B Testing $\rightarrow$ `Product Manager`, `Associate Product Manager`, `Product Owner`
  - **UI/UX & Product Design**: Figma, Wireframing, User Research, Prototyping $\rightarrow$ `Product Designer`, `UI/UX Designer`, `Visual Designer`
  - **Data & Business Intelligence**: SQL, Tableau, Power BI, Snowflake $\rightarrow$ `Data Analyst`, `BI Analyst`, `Analytics Engineer`
  - **AI & Machine Learning**: PyTorch, TensorFlow, LLMs, NLP $\rightarrow$ `AI/ML Engineer`, `Data Scientist`
  - **Growth & Marketing**: SEO, SEM, Google Ads, HubSpot, GA4 $\rightarrow$ `Growth Marketer`, `Digital Marketing Specialist`
  - **Sales & Business Development**: Salesforce, B2B Sales, Lead Generation $\rightarrow$ `Account Executive`, `Business Development Representative`
  - **Finance & Accounting**: Financial Modeling, Valuation, QuickBooks, Auditing $\rightarrow$ `Financial Analyst`, `Accountant`
  - **Human Resources & Talent**: Talent Acquisition, Technical Recruiting, HRIS, Workday $\rightarrow$ `Talent Acquisition Specialist`, `HR Specialist`
  - **Operations & Project Management**: Supply Chain, Logistics, PMP, Scrum Master $\rightarrow$ `Operations Manager`, `Project Manager`
  - **Legal & Compliance**: Contract Management, Regulatory Compliance, GDPR $\rightarrow$ `Legal Counsel`, `Compliance Specialist`
  - **Engineering**: Preserves existing high-precision synthesis across Full Stack, Backend, Frontend, and DevOps.
* **Domain Search Isolation**: Guarantees that non-tech candidates (Product Managers, Designers, Marketers, Sales Reps, Accountants) are never polluted with software engineering titles or tech stack keywords.
* **Cross-Domain Canonical Skills & Catalog (`jobhunt/llm_utils.py`, `jobhunt/web/routes/profile.py`)**: Expanded canonical mappings and section heuristics to 150+ universal tools and methodologies (Figma, PRDs, Tableau, Power BI, Salesforce, HubSpot, QuickBooks, Workday, PMP, Agile, Scrum).
* **Domain-Agnostic LLM Prompts & Seniority Calibration (`jobhunt/llm.py`)**: Universalized `PROFILE_SYSTEM_PROMPT` to analyze talent across all industries and disciplines, replacing hardcoded functional exclusions (*"Sales"*, *"Manager"*, *"Recruiter"*) with dynamic seniority-level calibration.
* **Universal Application Drafting & Follow-Up Notes**: Universalized draft kit system prompts, offline scorer stand-ins, and follow-up templates for any professional deliverable or discipline.
* **Test Suite Expansion (`tests/test_resume_accuracy.py`, `tests/test_unified_runner.py`)**: Added dedicated integration tests validating Product Management, UI/UX Design, Data Analytics, Marketing, Sales, Finance resumes, and the unified test runner, expanding the repository test suite to **650 passed tests** (**92%+ statement coverage**, **0 Ruff errors**, **0 Mypy errors**).

---

## [v1.2.3] - 2026-11-13

### 🎯 Deterministic Resume Intelligence Accuracy Engine
* **Interval-Based Timeline YoE (`jobhunt/llm_utils.py`)**: Merges overlapping professional stints to eliminate double-counted tenure, and strictly excludes student internships from full-time professional experience.
* **Student & Fresher Clamping**: Explicitly detects graduation year $\ge 2025$ and student labels, clamping YoE to `0.0` to eliminate hallucinated years from degree dates.
* **Canonical Skill Normalization**: Maps fragmented synonyms (`React.js` $\rightarrow$ `React`, `Postgres` $\rightarrow$ `PostgreSQL`, `Python3` $\rightarrow$ `Python`, `Golang` $\rightarrow$ `Go`) while purging 22+ soft-skill buzzwords (*"Problem Solving"*, *"Teamwork"*, etc.).
* **Dynamic Headline Role & Target Synthesis**: Synthesizes engineering titles (`Full Stack Developer`, `Backend Engineer`, `AI/ML Software Engineer`) from validated skill sets, eliminating raw `"Student"` or `"Fresher"` tags.
* **Header-Bounded Candidate Name Extraction**: Strips document titles and contact metadata, capturing clean candidate names from header delimiters.
* **Default Headless Chromium Playwright Runner (`tests/test_browser_playwright.py`)**: Configured Chromium launch flags (`--no-sandbox`, `--disable-setuid-sandbox`) for clean, default browser testing across local and CI environments.
* **Test Suite Expansion (`tests/test_resume_accuracy.py`)**: Added 9 dedicated accuracy unit and integration tests, expanding the repository test suite to **616 passed tests** (**92%+ statement coverage**).

---

## [v1.2.2] - 2026-11-12

### 🐛 Hotfix: GitHub Actions Batch User Query & Schema Drift Guardrail
* **Supabase Batch Profile Projection (`jobhunt/multi.py`)**: Removed non-existent `location` column from `_BATCH_PROFILE_COLUMNS` (which triggered PostgreSQL error `42703: column user_profiles.location does not exist` during `jobhunt multi-run`), added `min_salary_lpa` and `preferred_sectors`, and printed explicit HTTP/candidate error diagnostics before returning `user_not_found`.
* **Schema Alignment Tests (`tests/test_schema_sql.py`, `tests/test_multi_user_batch.py`)**: Verified every `select` column in `multi.py` and `memory.py` against `supabase/schema.sql`, expanding the suite to **607 passing tests** (**92%+ statement coverage**).

---

## [v1.2.1] - 2026-11-12

### 🔄 End-to-End Template & Ground-Truth Sync
* **Dynamic Template Release Tag Injection**: `views.py` now injects `app_version` directly from `jobhunt.__version__` into `dashboard.html` and `landing.html`, eliminating hardcoded version drift across deployments.
* **Ground-Truth Documentation & Valuation Sync**: Updated `SECURITY.md`, `README.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, and `docs/PRODUCT_ANALYSIS_WALKTHROUGH.md` to exact measured repository counts (`114` ATS targets, `43` source files / `12,326` LOC, `36` test files / `13,898` LOC, `605` tests / `92%+` coverage, 2026 INR/USD valuation benchmarks).

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
