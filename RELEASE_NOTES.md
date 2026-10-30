# Release Notes

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
