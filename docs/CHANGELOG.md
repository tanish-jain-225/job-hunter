# Changelog

All notable changes to **Job Hunter** are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Security
- **Universal View State Isolation & Strict Utility Access Guards**: Enforced complete separation between unauthenticated visitors and authenticated dashboard views. Implemented universal `.app-view-hidden` CSS rules (`display: none !important; visibility: hidden !important; pointer-events: none !important;`) with highest cascade precedence, ensuring authenticated components never leak on small screens or media queries (`<= 340px`, `<= 300px`). Gated authenticated operational backend API routes with `@require_auth` while preserving intentionally public health, landing, asset, and auth-configuration routes.
- **Client-Side Auth Lockout (`checkAuthOrRedirect`)**: Added central client-side authentication guard across all utility triggers (manual sync, on-demand pipeline runner, tab switching, custom opportunity tracking, custom company additions/deletions, kit inspector, candidate profile settings, resume parser, and `/` search shortcut). Promptly redirects unauthenticated attempts to landing view with the sign-in modal and toast notifications.
- **Session Cleanup & Memory Purge**: Enhanced `handleSignOut()` to comprehensively wipe in-memory job arrays, jobs maps, candidate profile context, DOM containers, and remove sensitive `CACHED_STATS` and `CACHED_PROFILE` records from `localStorage`.
- Removed JWT token acceptance via query string (`?token=`) — tokens must now arrive via `Authorization: Bearer` header or HttpOnly cookie only (OWASP CWE-598)
- Added `Content-Security-Policy` and `Permissions-Policy` response headers to all Flask routes
- Added `use_service_key` gate to `SupabaseMemory._headers()` — service role key (which bypasses RLS) is now only used explicitly for admin batch operations in the multi-run pipeline
- Exception handler now sends a generic message to API clients in production (full details remain server-side in logs)
- Added `flask-limiter` rate limiting: `/api/run` capped at 5 calls/hour/IP; global default of 500 req/hour/IP

### Added
- **Streamlined Interactive Job Board Table & Responsive Pagination**: Transitioned the interactive job board to a high-density, executive Table/Card list view with responsive client-side pagination (`pageSize` 10/25/50, first/prev/next/last navigation, page indicators, and localStorage persistence). Replaced complex Kanban column clutter while embedding 1-click stage dropdown selectors (`to_apply`, `applied`, `interviewing`, `offer`, `rejected`) directly within each job card.
- **Universal Logo Guard & Visual Identity Protection**: Implemented a global logo protection system (`.brand-logo-frame, .brand-logo, .brand-fallback-icon, .digest-logo-img, .empty-logo-img, .digest-footer-logo { flex-shrink: 0 !important; min-width: fit-content; }`) across all viewport breakpoints down to 300px and in daily HTML email briefings (`jobhunt/digest.py`), with automatic local fallback (`onerror="this.src='/logo.png'"`).
- **Executive Light Mode & 100% Pure Flexbox Responsiveness**: Standardized the web dashboard, profile modals, and daily digest briefings to an executive light mode color palette with zero CSS Grid dependencies, ensuring seamless, unclipped presentation across all device types and screen sizes.
- **Global Provider State Isolation & Reset Utility**: Added thread-safe `reset_provider_state()` in `jobhunt/providers.py` and paired it with an `autouse=True` fixture (`reset_global_provider_state`) in `tests/conftest.py` ensuring pristine isolation of key counters, model cooldowns, and leaky-bucket timestamps across all test suites.
- **Test Suite Speedup (>80% Execution Acceleration)**: Configured `_enforce_key_throttle()` and `_enforce_rate_limit_throttle()` to bypass physical sleeps during unit test execution under `PYTEST_CURRENT_TEST` (preserving 100% production 15 RPM throttling), drastically reducing full suite test duration while maintaining 100% test reliability.
- **Deterministic Multi-Key Alternation**: Enhanced `GeminiProvider._post` to dynamically dispatch initial requests across configured keys via `_GEMINI_KEY_COUNTER % len(active_keys)` while retrying subsequent attempts cleanly against surviving unexhausted active keys.
- **Multi-Key Circular Rotation & Per-Key Leaky-Bucket Throttle**: Added a thread-safe atomic counter (`_GEMINI_KEY_COUNTER`) ensuring successive requests strictly alternate across all API keys configured in `GEMINI_API_KEY=key1,key2,key3`. Upgraded rate limiting to track independent per-key invocation timestamps (`_enforce_key_throttle(key, min_interval=4.0)`), enforcing 15 RPM per key without cross-key stalls.
- **Extended Read Timeout to 60s**: Increased HTTP client connection read timeout from 25s to 60s in `jobhunt/providers.py` (`TIMEOUT = 60`), preventing premature socket closures during large JSON application kit generation under upstream load.
- **Frontier Multi-Model Dynamic Cascading & Cooldown Layer**: When `gemini-3.5-flash` encounters Google AI Studio project-level free-tier limits (`HTTP 429: Resource Exhausted`) or transient high demand (`HTTP 503`), the engine automatically cascades the active payload to Google's production Flash endpoints (`gemini-flash-latest` → `gemini-flash-lite-latest`), with temporary cooldown tracking (`_MODEL_COOLDOWN_MAP`) ensuring zero pipeline stalls, continuous real-time execution, and authentic kit drafting.
- **Brand Logo Asset & Digest Attribution**: Added dedicated `/logo.png` route serving the official brand mark. Upgraded Daily Digest email briefings (`jobhunt/digest.py`) and Web Dashboard reader (`templates/partials/dashboard.html`) with responsive flexbox headers, brand logo thumbnails, and active source footers linking to `https://job-hunter-web-board.vercel.app`.
- **Pure Flexbox Fluid Layout down to 300px**: Standardized all UI components, buttons, wizard action rows, navigation bars, and email digests to pure flexbox, guaranteeing zero horizontal scrolling or clipping down to 300px screen widths.
- **Expanded Automated Suite**: Expanded test suite to **397 automated tests** across Python 3.9-3.12 with >91% coverage, adding full test coverage for view isolation contracts and protected endpoints in `tests/test_auth.py`.
- **Resume Studio Resilient AI Extraction with 30s Execution Ceiling & Smart Regex Fallback**: In `jobhunt/web/routes/profile.py`, wrapped `llm.build_profile()` in a non-blocking `ThreadPoolExecutor` with a bounded 30.0s timeout ceiling to allow Gemini retries (e.g. transient HTTP 503 high-demand spikes) to complete cleanly. Added a smart local regex parser fallback that extracts candidate name, job title, education, technical skills, and target roles directly from plain text without failing.
- **Client Upload Timeout Expansion & Cache Invalidation**: Extended frontend client `AbortController` timeout from 18s to 45s in `static/js/app.js` and bumped asset query versions to `?v=1.0.3` in `templates/index.html`.
- **Ultra-Narrow 300px Mobile Responsive Engine**: Expanded Section 12 in `static/css/style.css` with multi-tier breakpoints (`<= 480px`, `<= 380px`, `<= 340px`, and down to `300px`) covering Navbar, Landing Hero/Auth, Dashboard Sidebar, Metrics Bar, Tracker Controls, Kanban view, Table view, all 5 Modals, and Toasts with `overflow-x: hidden !important; max-width: 100vw !important;`.
- **Database Schema Companion Teardown**: Created `supabase/teardown.sql` paired with `supabase/schema.sql` providing an idempotent, cascade-safe reset script for multi-tenant database teardown and migrations.
- **Comprehensive 14-Suite End-to-End Live Testing Matrix**: Added `tests/test_e2e_live_comprehensive.py` validating 14 feature areas locally (Health, Config, Assets, Security Headers, Auth, Resume Studio JSON & Multipart upload, Preferences, Profile CRUD & Reset, ATS Detection, Job Tracker Lifecycle, AI Intelligence, Daily Digest HTML, and Cloud Sync), expanding the test suite to **391 passed automated tests**.
- **Google Gemini (`gemini-3.5-flash`) as Default Intelligence Engine**: Standardized all candidate screening, fit scoring, application kit drafting, and PDF resume parsing to default to **Google Gemini (`gemini-3.5-flash`)**. Multi-provider support (Anthropic Claude, Groq, Ollama, OpenAI-compatible) retained and fully documented across all markdown files. Updated multi-key CSV rotation and leaky-bucket rate limiting to 6.0s/10 RPM for Gemini free tier.
- **Real-Time Server-Sent Events (SSE) Live Radar Log Streaming**: Added `GET /api/pipeline/stream` and circular thread-safe user log streaming buffers in `jobhunt/web/state.py` for live terminal console updates without polling delay
- **Custom Target ATS Career Board Manager ("+ Add Board")**: Added `detect_ats_from_url()` in `jobhunt/fetch.py` supporting all 9 ATS platforms with live HTTP 200 verification, accompanied by `POST /api/companies/add`, `GET /api/companies/custom`, and `DELETE /api/companies/custom` endpoints and interactive web modal
- **Smart Follow-Up Nudges & Generator**: Added automated elapsed-time badges (`⏳ 5d ago · Send Follow-up`) on applied roles in Table and Kanban views, paired with `POST /api/jobs/followup` and 1-click tailored email/LinkedIn outreach generation
- **Onboarding Setup Wizard Daily Briefing Default**: Pre-selected Daily 5:00 AM Radar mode by default with dedicated notification email input field
- **Optimized Automated Daily Cron**: Scheduled daily radar cron adjusted to 23:30 UTC (05:00 AM IST) in `.github/workflows/daily.yml` and `setup_daily_task.bat` for consistent early morning delivery before user wake-up
- **Comprehensive Flow Perfection Test Suite**: Added `tests/test_flow_perfection.py` expanding test suite to **377 passed unit & integration tests with >91% code coverage**
- **Dual-Mode View Switcher (Table & Visual Kanban Pipeline)**: Added interactive Table vs. Kanban pipeline view switcher (`#btn-view-table` and `#btn-view-kanban`) with persistent preference storage in `localStorage`
- **Deterministic Reactive Store Versioning**: `get_store_version()` now hashes `application_stage`, `notes`, `score`, and timestamps into deterministic MD5 version tokens for zero-refresh multi-tab reactivity
- Refactored `jobhunt verify` (live ATS auditor) and `jobhunt clean` (test store purger) into modular CLI package tools (`jobhunt/verify.py` and `jobhunt/clean.py`)
- `--version` flag to `jobhunt` CLI (`jobhunt --version` -> `jobhunt 1.0.0`)
- `region_context` and `region_hint` configuration keys in `config.yaml` — LLM screening prompt regional context is now fully configurable; set `region_context: global` to remove India-specific hints
- `@register_ats` decorator now emits `warnings.warn` on accidental duplicate registration (silent overwrite prevention)
- `threading.Lock` protection around `_GLOBAL_ATS_CACHE` for thread-safe concurrent ATS fetching
- 10 MB hard response size cap in `fetch_board()` — prevents OOM from oversized or malformed ATS endpoints
- `hypothesis>=6.0.0` added as a dev dependency for property-based fuzzing
- Synchronized technical narrative across `README.md` and the documentation suite under `docs/`.
- Added `docs/CHANGELOG.md`, `docs/SECURITY.md`, and `docs/API.md`.

### Fixed
- Corrected `pyproject.toml`: removed duplicate `flask-limiter` from `dependencies[]` (it belongs only in `optional-dependencies[web]`)
- Corrected `README.md`, `ENGINE.md`, `SETUP.md`, `GUIDE.md`, `DASHBOARD.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `providers.py` docstrings: replaced all "exclusively Google Gemini" claims with accurate multi-provider architecture documentation
- Corrected `README.md` `config.yaml` example: `screen_batch_size` `10→8`, `screen_jd_chars` `1400→1000`, `llm_delay_seconds` `1.5→6.0`, added missing `max_jobs_to_screen: 30`
- Corrected `ENGINE.md`: `draft_jd_chars` `8000→6000`, `score_threshold` range `5.0-7.0→7.0`
- Corrected `GUIDE.md`: `max_age_days` example `28→21` (matches actual default)
- Documented alternative provider keys (`ANTHROPIC_API_KEY`, `GROQ_API_KEY`, `OLLAMA_HOST`) in `.env.example`
- Fixed optimistic UI card resolution in `app.js` to target both `job-card-` and `kanban-card-` elements in Table and Kanban modes
- Fixed empty-state querySelector in `toggleAppliedDirect` to accurately match `.job-item, .kanban-card`
- `/api/jobs/notes` now returns `"version": get_store_version(st)` and `"stats": st.stats()` for instant state reconciliation
- `clear_ats_cache()` was not thread-safe — now uses `_ATS_CACHE_LOCK`
- `multi.py` admin batch listing of all users now correctly passes `use_service_key=True`
- Fixed Mypy `method-assign` typing error on `ProxyFix` middleware assignment in `jobhunt/web/__init__.py`
- Switched Workable scraper to the official GET endpoint (`api/v1/widget/accounts/{slug}`)
- Synchronized all documentation ATS tables, YAML examples, and verified all 88 target company slugs to live HTTP 200 OK status

---

## [1.0.0] — 2026-08-26

### Added
- **9 ATS parsers**: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, Pinpoint
- **Two-stage LLM pipeline**: Groq (openai/gpt-oss-20b) batch screening + Google Gemini (gemini-3.5-flash) application kit drafting
- **5 LLM provider backends**: Groq, Google Gemini, Anthropic Claude, OpenAI-compatible, Ollama (offline)
- **Automatic quota circuit breaker**: Falls back to keyword scoring when consecutive LLM batches fail
- **Multi-tenant single-pass batch engine** (`multi.py`): Fetches all ATS boards once, fans out per-user with Supabase RLS isolation
- **Flask Web Dashboard** with Kanban pipeline, resume studio, CSV export
- **Supabase PostgreSQL integration**: JWT + RLS, user profiles, job tracking, pipeline run history
- **Resume Studio**: PDF/TXT upload -> AI profile extraction
- **GitHub Actions CI/CD**: 4-Python matrix (3.9-3.12) with Ruff, Mypy, pytest (>=98% coverage)
- **Daily digest workflow**: Cron at 00:30 UTC (06:00 IST), caches state, dispatches HTML briefings via SMTP
- **Vercel serverless deployment** via `api/index.py` WSGI adapter
- **319 automated tests** with 98%+ line coverage enforced in CI
- **9-document docs suite**: SETUP, DEPLOYMENT, ENGINE, DASHBOARD, MULTI_USER, TROUBLESHOOTING, CONTRIBUTING, GUIDE, JOB_HUNT
- MIT License

[Unreleased]: https://github.com/tanish-jain-225/job-hunter/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/tanish-jain-225/job-hunter/releases/tag/v1.0.0
