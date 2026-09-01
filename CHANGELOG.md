# Changelog

All notable changes to **Job Hunter** are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Security
- Removed JWT token acceptance via query string (`?token=`) — tokens must now arrive via `Authorization: Bearer` header or HttpOnly cookie only (OWASP CWE-598)
- Added `Content-Security-Policy` and `Permissions-Policy` response headers to all Flask routes
- Added `use_service_key` gate to `SupabaseMemory._headers()` — service role key (which bypasses RLS) is now only used explicitly for admin batch operations in the multi-run pipeline
- Exception handler now sends a generic message to API clients in production (full details remain server-side in logs)
- Added `flask-limiter` rate limiting: `/api/run` capped at 5 calls/hour/IP; global default of 500 req/hour/IP

### Added
- Expanded automated test suite from 319 to 357 unit & integration test cases with 98%+ line coverage
- Refactored `jobhunt verify` (live ATS auditor) and `jobhunt clean` (test store purger) into modular CLI package tools (`jobhunt/verify.py` and `jobhunt/clean.py`)
- `--version` flag to `jobhunt` CLI (`jobhunt --version` -> `jobhunt 1.0.0`)
- `region_context` and `region_hint` configuration keys in `config.yaml` — LLM screening prompt regional context is now fully configurable; set `region_context: global` to remove India-specific hints
- `@register_ats` decorator now emits `warnings.warn` on accidental duplicate registration (silent overwrite prevention)
- `threading.Lock` protection around `_GLOBAL_ATS_CACHE` for thread-safe concurrent ATS fetching
- 10 MB hard response size cap in `fetch_board()` — prevents OOM from oversized or malformed ATS endpoints
- `hypothesis>=6.0.0` added as a dev dependency for property-based fuzzing
- Synchronized technical narrative across all markdown documentation files (`README.md`, `METRICS.md`, `docs/`)
- `CHANGELOG.md`, `SECURITY.md`, `docs/API.md` added

### Changed
- `seen_file` path moved from root-level `seen.json` to `state/seen.json` — all `seen_*.json` state files relocated to `state/` subdirectory
- `anthropic` moved from required core dependencies to optional `[anthropic]` extra — `pip install jobhunt[anthropic]`
- `flask-limiter` added as optional `[web]` extra — `pip install jobhunt[web]`
- `_build_screen_system()` now accepts optional `cfg` dict to read regional context at call time

### Fixed
- `clear_ats_cache()` was not thread-safe — now uses `_ATS_CACHE_LOCK`
- `multi.py` admin batch listing of all users now correctly passes `use_service_key=True`

---

## [1.0.0] — 2026-08-26

### Added
- **9 ATS parsers**: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, Pinpoint
- **Two-stage LLM pipeline**: Groq (openai/gpt-oss-20b) batch screening + Google Gemini (gemini-3.6-flash) application kit drafting
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
