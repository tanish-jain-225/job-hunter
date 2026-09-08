<p align="center">
  <a href="https://job-hunter-web-board.vercel.app">
    <img src="assets/logo.png" alt="Job Hunter Logo" width="120" height="120" style="border-radius: 16px;">
  </a>
</p>

# Job Hunter

**Career Intelligence Engine & Job Discovery Platform**

Job Hunter discovers jobs directly from public ATS endpoints, eliminates irrelevant roles through deterministic prefiltering, evaluates fit using LLMs, drafts tailored application kits, and organizes opportunities in an interactive web dashboard.

Applications are never submitted automatically. The candidate always reviews materials and decides whether and where to apply.

---

## Features

* **Public ATS Integrations:** Direct unauthenticated JSON parsing for Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, and Pinpoint.
* **Deterministic Prefilter:** Fast regex filtering for title patterns, locations, employment types, and listing freshness before making any LLM requests.
* **AI Match Scoring:** Structured scoring (0.0 to 10.0) against the candidate's parsed resume and target roles using Google Gemini (default), Anthropic Claude, Groq, Ollama, or OpenAI-compatible endpoints.
* **Application Kit Drafting:** Generates tailored cover notes, networking outreach messages, resume alignment bullets, and interview prep questions for top matches (7.0+).
* **Interactive Dashboard:** Web dashboard with 5-stage pipeline tracking (To Apply, Applied, Interviewing, Offer, Archived), live search, ATS board filtering, notes, and follow-up alerts.
* **Multi-Tenant Cloud Mode:** Built on Flask with Supabase Authentication and PostgreSQL persistence with Row-Level Security (RLS) for cloud deployments.
* **Offline Local Mode:** Runs entirely locally with local JSON and CSV tracking (`seen.json`, `out/tracker.csv`) without requiring external database services.

---

## System Architecture

```text
[Public ATS Boards] (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, etc.)
        │
        ▼
[1. Fetch Engine] ── Concurrent HTTP requests with connection pooling
        │
        ▼
[2. Regex Prefilter] ── Title, location, job type, and 21-day freshness gate
        │
        ▼
[3. LLM Screening] ── Batched scoring against candidate resume context
        │
        ▼
[4. Kit Generation] ── Custom cover notes, outreach messages, and bullets
        │
        ▼
[5. Persistence] ── Local JSON / Supabase PostgreSQL with RLS
        │
        ▼
[6. Interfaces] ── Web Dashboard (Flask/Vercel) & Daily Email Briefing
```

---

## Quickstart

### Local Development (Zero External Keys Required)

You can test the entire pipeline locally using offline mock fixtures and the local keyword scorer without configuring any external API keys:

```bash
# Clone the repository
git clone https://github.com/tanish-jain-225/job-hunter.git
cd job-hunter

# Create and activate virtual environment
python -m venv .venv
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

# Install package in editable mode with development dependencies
pip install -e ".[dev]"

# Run offline mock pipeline
jobhunt run --mock --scorer keyword

# Start local web dashboard
python app.py
```

Open `http://localhost:5000` in your browser. The mock run will populate `out/digest.html` and local store files.

---

## Cloud Deployment

For multi-user cloud hosting, the platform uses:

1. **Vercel:** Hosts the Flask WSGI web application (`api/index.py`) and static dashboard assets.
2. **Supabase:** Manages user authentication and PostgreSQL storage with Row-Level Security (RLS).
3. **GitHub Actions:** Runs the scheduled daily batch crawler (`.github/workflows/daily.yml`) every morning at 05:00 AM IST (23:30 UTC).
4. **Google Gemini / AI Provider:** Handles fit evaluation and kit drafting.
5. **SMTP Provider (Optional):** Delivers email briefings if notifications are enabled.

### Deployment Sequence

1. **Database Setup:** Run [`supabase/schema.sql`](supabase/schema.sql) in your Supabase SQL Editor to initialize tables and RLS policies.
2. **Authentication Settings:** Under Supabase Auth settings, configure your Site URL and allowed redirect URLs for your deployment domain.
3. **Vercel Environment Variables:** In your Vercel Project Settings, add:
   * `SUPABASE_URL`
   * `SUPABASE_ANON_KEY`
   * `GEMINI_API_KEY`
   * `FLASK_SECRET_KEY`
   * `AUTH_REQUIRED=true`
   * `GH_TOKEN` and `GITHUB_REPOSITORY` (if enabling cloud on-demand radar triggers from the UI)
4. **GitHub Actions Secrets:** Under repository Settings &rarr; Secrets and variables &rarr; Actions, configure:
   * `SUPABASE_URL`
   * `SUPABASE_SERVICE_ROLE_KEY` (required for batch multi-user processing across tenant boundaries)
   * `GEMINI_API_KEY`
   * `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` (if email delivery is required)
5. **Deploy:** Push your repository to GitHub. Vercel automatically builds and serves the application.
6. **Verify:** Check `/api/health` and `/api/auth/config` on your production URL.

---

## Configuration Reference

Copy `.env.example` to `.env` for local configuration. Never commit `.env` or any secret keys.

| Variable | Scope | Description |
|---|---|---|
| `GEMINI_API_KEY` | Web / Worker | Google AI Studio key for screening and kit drafting. Supports comma-separated keys for rotation. |
| `SUPABASE_URL` | Web / Worker | Supabase project URL (`https://your-project.supabase.co`). |
| `SUPABASE_ANON_KEY` | Web / Browser | Public Supabase anonymous key used for client authentication. |
| `SUPABASE_JWT_SECRET` | Web | Optional secret for local PyJWT token validation. |
| `SUPABASE_SERVICE_ROLE_KEY` | Worker Only | Administrative key used strictly in GitHub Actions batch runs to process active users. Never expose to client. |
| `FLASK_SECRET_KEY` | Web | Random 32-character string for Flask session management. |
| `AUTH_REQUIRED` | Web | Set to `true` to require authentication for dashboard access. |
| `GH_TOKEN` | Web | GitHub Personal Access Token with `actions:write` scope for on-demand cloud radar dispatch. |
| `GITHUB_REPOSITORY` | Web | Target repository (`owner/repo`) for workflow dispatch. |
| `SMTP_HOST`, `SMTP_PORT` | Worker | SMTP server configuration (e.g. `smtp.gmail.com`, `587`). |
| `SMTP_USER`, `SMTP_PASS` | Worker | SMTP authentication credentials. |
| `MAIL_TO` | Worker | Recipient email address for single-user local runs. |

---

## CLI Reference

The package provides the `jobhunt` command-line utility:

```text
jobhunt run         Run single-user search, filter, and score pipeline
jobhunt multi-run   Run batch multi-user pipeline across registered profiles
jobhunt profile     Extract candidate profile from a PDF, TXT, or MD resume
jobhunt applied     Mark a job ID as applied in the local tracking store
jobhunt stats       Display tracking statistics and export out/tracker.csv
jobhunt verify      Audit configured ATS company boards for HTTP reachability
jobhunt clean       Remove temporary local test stores and transient files
jobhunt web         Launch the local Flask web dashboard
```

### Common Commands

```bash
# Run dry-run test with mock data
jobhunt run --mock --scorer keyword

# Parse resume to create local profile
jobhunt profile --resume resume.pdf

# Verify active company boards in companies.yaml
jobhunt verify --companies companies.yaml

# Run batch multi-user pipeline locally in mock mode
jobhunt multi-run --mock --scorer keyword

# Launch web server locally
python app.py
```

---

## Security and Privacy

* **Tenant Isolation:** In cloud mode, all user data (profiles, tracked jobs, pipeline status) is protected by Supabase Row-Level Security policies.
* **Secret Separation:** The administrative `SUPABASE_SERVICE_ROLE_KEY` is reserved exclusively for the scheduled GitHub Actions worker and is never returned by API routes or included in frontend assets.
* **Memory-Only Processing:** Uploaded resumes are parsed in-memory; raw binary files are not persisted to disk. Extracted text context is stored within the candidate's account.
* **No Automated Submissions:** The engine drafts materials and generates direct links, leaving actual job application submission in the hands of the candidate.

---

## Testing and Quality Verification

The test suite includes unit tests, integration tests, property-based tests via Hypothesis, and security header checks:

```bash
# Run full test suite
pytest

# Run tests with terminal coverage report
pytest --cov=jobhunt --cov-report=term-missing

# Run type checker
mypy jobhunt app.py auto.py

# Run linter
ruff check .
```

---

## Documentation

* [Setup Guide](docs/SETUP.md): Detailed local and cloud setup instructions.
* [Deployment Guide](docs/DEPLOYMENT.md): Production deployment on Vercel and Supabase.
* [REST API Reference](docs/API.md): Endpoint specifications, request formats, and response codes.
* [Architecture Overview](docs/ARCHITECTURE.md): Component diagrams and lifecycle workflows.
* [Engine Documentation](docs/ENGINE.md): Prefilter logic, ATS parsers, and LLM resolution.
* [Dashboard Guide](docs/DASHBOARD.md): Features and usage of the web dashboard.
* [Multi-User Operations](docs/MULTI_USER.md): Multi-tenant architecture and batch runner details.
* [Security Policy](docs/SECURITY.md): Threat model, authentication flows, and data protections.
* [Troubleshooting](docs/TROUBLESHOOTING.md): Solutions for common setup and operational issues.
* [Metrics & Limits](docs/METRICS.md): System capacity, provider rate limits, and cost projections.
* [Contributing Guidelines](docs/CONTRIBUTING.md): Guidelines for code contributions.
* [Changelog](docs/CHANGELOG.md): Version history and release notes.

---

## License

This project is open source and available under the [MIT License](LICENSE).
