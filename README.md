<div align="center">

# 🏹 Job Hunter (`job-hunter`)

### *Autonomous AI-Powered Career Intelligence & Job Hunting Agent*

[![Python Version](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![CI Status](https://img.shields.io/github/actions/workflow/status/tanish-jain-225/job-hunter/ci.yml?branch=main&style=for-the-badge&label=CI&color=success)](https://github.com/tanish-jain-225/job-hunter/actions/workflows/ci.yml)
[![Daily Digest](https://img.shields.io/github/actions/workflow/status/tanish-jain-225/job-hunter/daily.yml?branch=main&style=for-the-badge&label=Daily%20Digest&color=blue)](https://github.com/tanish-jain-225/job-hunter/actions/workflows/daily.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-black?style=for-the-badge&logo=ruff)](https://github.com/astral-sh/ruff)

</div>

---

## 📖 The Narrative: Why Job Hunter?

Modern job searching is broken. Engineers spend hours every week manually sifting through thousands of irrelevant job board postings, dealing with spam, guessing fit percentages, and writing repetitive cover letters. 

**Job Hunter (`job-hunter`)** is built to solve this. It is your personal, autonomous career intelligence agent that operates 24/7. Every morning while you sleep, **Job Hunter**:
1. 🌐 **Scouts Target Boards**: Polls public, unauthenticated ATS endpoints across 9 platforms (**Greenhouse**, **Lever**, **Ashby**, **Workable**, **SmartRecruiters**, **BambooHR**, **Recruitee**, **Breezy HR**, **Pinpoint**).
2. 🎯 **Filters the Noise**: Eliminates ~99% of irrelevant, out-of-scope, or outdated postings deterministically using regex rules at **$0 API cost**.
3. 🧠 **Screening & Intelligence**: Scores surviving roles (1.0 - 10.0) against your candidate profile using **`gemini-3.5-flash`** (with automatic fallback).
4. ✍️ **Drafts Application Kits**: Auto-generates tailored cover notes, 80-word cold outreach messages, matching resume bullets, and interview questions.
5. 📊 **Visual Kanban & Daily Bounty**: Organizes opportunities across a visual Kanban Pipeline (*To Apply*, *Applied*, *Interviewing*, *Offer*, *Rejected*) and delivers responsive HTML email briefings.

> [!IMPORTANT]
> **The Golden Rule of Job Hunter**: *The Hunter never fires without manual authorization.* **Job Hunter** never auto-submits applications. It handles scouting, filtering, ranking, and drafting—leaving final application submission strictly under your control.

```text
┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
│ 1. Scout Postings   │ ───►  │ 2. Stealth Filter   │ ───►  │ 3. Precision Screen │ ───►  │ 4. Daily Bounty     │
│ ~5,000 ATS Roles    │       │ ~50 Matching Roles  │       │ ~5 Top Matches      │       │ Kanban Board & Mail │
└─────────────────────┘       └─────────────────────┘       └─────────────────────┘       └─────────────────────┘
  (9 Major ATS Engines)        (0 API Cost Filter)           (gemini-3.5-flash)            (Dashboard / Inbox)
```

> [!TIP]
> **First time setting up?** Check out **[SETUP.md](docs/SETUP.md)** for a beginner-friendly setup guide, **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** for 100% free multi-user cloud deployment, or **[MULTI_USER.md](docs/MULTI_USER.md)** for architecture scaling details.

---

## 📋 Table of Contents

- [📖 The Narrative: Why Job Hunter?](#-the-narrative-why-job-hunter)
- [⚡ Quick Start (30-Second Dry Run)](#-quick-start-30-second-dry-run)
- [🚀 100% Free-Tier Production Stack](#-100-free-tier-production-stack)
- [📦 Installation \& Packaging](#-installation--packaging)
- [⚙️ Step-by-Step Setup Guide](#%EF%B8%8F-step-by-step-setup-guide)
  - [1. Configure Target Companies (`companies.yaml`)](#1-configure-target-companies-companiesyaml)
  - [2. Tune Deterministic Filters (`config.yaml`)](#2-tune-deterministic-filters-configyaml)
  - [3. Build Candidate Profile (`jobhunt profile`)](#3-build-candidate-profile-jobhunt-profile)
  - [4. Environment Variables (`.env`)](#4-environment-variables-env)
- [🤖 Supported LLM Providers \& Cost Matrix](#-supported-llm-providers--cost-matrix)
- [💻 Complete CLI Command Reference](#-complete-cli-command-reference)
- [🚀 Daily Workflows & Dashboard](#-daily-workflows--dashboard)
- [📊 Tracking \& Deduplication (`seen.json`)](#-tracking--deduplication-seenjson)
- [🤖 Automated Execution \& GitHub Actions](#-automated-execution--github-actions)
- [🛡️ Continuous Integration (CI Pipeline)](#%EF%B8%8F-continuous-integration-ci-pipeline)
- [🏗️ Architecture \& Codebase Layout](#%EF%B8%8F-architecture--codebase-layout)
- [⚡ ATS Quirks \& Edge Case Handling](#-ats-quirks--edge-case-handling)
- [🧪 Automated Test Suite](#-automated-test-suite)
- [❓ Troubleshooting \& FAQ](#-troubleshooting--faq)
- [📄 Contributing \& License](#-contributing--license)

---

## ⚡ Quick Start (30-Second Dry Run)

Test the complete **Job Hunter** pipeline locally without any API keys using bundled ATS fixtures and the dev keyword scorer:

### 💻 Windows:
```cmd
git clone https://github.com/tanish-jain-225/job-hunter.git
cd job-hunter
python -m venv .venv
.venv\Scripts\activate
pip install -e .

run.bat --mock --scorer keyword
```

### 🍏 macOS / 🐧 Linux:
```bash
git clone https://github.com/tanish-jain-225/job-hunter.git
cd job-hunter
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

./run.sh --mock --scorer keyword
```

#### Expected Execution Output:
```text
[1/5] fetching boards (mock fixtures)
[2/5] filtering
  prefilter: 12 -> 5 (dropped title=5 location=1 stale=1)
[3/5] screening 5 jobs (keyword stub — DEV ONLY)
  3 scored >= 7.0
[4/5] drafting kits for 3
[5/5] digest
  wrote out/digest.html

funnel: 12 scanned -> 5 passed filters -> 5 new -> 3 in digest
```
*(The generated `out/digest.html` briefing will automatically open in your default browser).*

---

## 📦 Installation & Packaging

**Job Hunter** strictly complies with modern **PEP 621** packaging standards via [`pyproject.toml`](pyproject.toml). Installing it in editable mode exposes the global `jobhunt` CLI binary:

```bash
# Standard editable installation
pip install -e .

# Development installation (includes pytest, ruff, mypy, pytest-cov)
pip install -e ".[dev]"
```

Run CLI subcommands directly via `jobhunt <subcommand>` or module invocation `python -m jobhunt <subcommand>`.

---

## ⚙️ Step-by-Step Setup Guide

### 1. Configure Target Companies (`companies.yaml`)

Define target company career boards in [`companies.yaml`](companies.yaml). The `slug` corresponds to the final path segment of the public careers URL:

| Board URL | `ats` | `slug` |
|---|---|---|
| `boards.greenhouse.io/stripe` | `greenhouse` | `stripe` |
| `jobs.lever.co/netlify` | `lever` | `netlify` |
| `jobs.ashbyhq.com/ramp` | `ashby` | `ramp` |
| `apply.workable.com/vector` | `workable` | `vector` |
| `jobs.smartrecruiters.com/visa` | `smartrecruiters` | `visa` |
| `acme.bamboohr.com/careers` | `bamboohr` | `acme` |
| `careers.recruitee.com/hotjar` | `recruitee` | `hotjar` |
| `breezy.hr/acme` | `breezy` | `acme` |
| `pinpoint.work/company` | `pinpoint` | `company` |

```yaml
companies:
  - {ats: greenhouse, slug: stripe, name: Stripe}
  - {ats: ashby, slug: openai, name: OpenAI}
  - {ats: lever, slug: fampay, name: FamPay}
  - {ats: workable, slug: vector, name: Vector}
  - {ats: smartrecruiters, slug: visa, name: Visa}
  - {ats: bamboohr, slug: acme, name: Acme}
  - {ats: recruitee, slug: hotjar, name: Hotjar}
  - {ats: breezy, slug: automattic, name: Automattic}
  - {ats: pinpoint, slug: monzo, name: Monzo}
```

> [!NOTE]
> **Why public ATS boards instead of LinkedIn/Naukri?** Scraping auth-gated sites violates Terms of Service and breaks constantly. Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, and Pinpoint expose clean, unauthenticated JSON endpoints officially intended for public job listing retrieval.

---

### 2. Tune Deterministic Filters (`config.yaml`)

[`config.yaml`](config.yaml) manages the free regex-based filtering step executed **before** sending candidate jobs to LLMs. The default configuration is completely **open** (allowing all job titles, all Indian locations, remote, and global), with zero opinionated restrictions. Users customize their preferences dynamically via the Web Dashboard Setup Wizard or profile settings.

```yaml
filters:
  # Leave empty to accept ALL titles (users filter via UI or profile)
  include_titles: []

  # Exclude only universal noise (C-suite, HR noise)
  exclude_titles:
    - '\b(ceo|coo|cfo|cto|ciso|vp|svp|evp|c-suite)\b'
    - '\b(intern.*recruiter|talent.*acquisition|hr.*intern)\b'

  # Leave empty to accept All India (any city) + Remote + Worldwide
  locations: []
  allow_remote: true

  # Accept all employment types (fulltime, internship, remote, hybrid, onsite)
  job_types: []
  max_age_days: 60

screen_batch_size: 8      # Jobs per screening LLM call
screen_jd_chars: 1800     # Rich context truncation for screening
draft_jd_chars: 8000      # Full context for drafting
score_threshold: 5.0      # Score threshold (1.0 to 10.0 bar for shortlist)
max_per_digest: 10        # Maximum job kits per digest briefing

# High-Performance Concurrency
fetch_max_workers: 12     # Parallel HTTP requests across 260+ ATS boards
llm_max_workers: 3        # Concurrent LLM batch workers
llm_delay_seconds: 1.5    # Throttle delay between LLM calls
```

---

### 3. Build Candidate Profile (`jobhunt profile`)

Generate [`profile.json`](profile.example.json) directly from your resume (`.pdf`, `.txt`, or `.md`):

```bash
jobhunt profile --resume resume.pdf
```

> [!TIP]
> PDF resumes are submitted natively as base64 document blocks to Google Gemini or Anthropic Claude (no OCR required), or extracted via built-in `pypdf`. Inspect the generated `profile.json` locally and fine-tune your extracted skills, target titles, or experience summary if needed.

---

### 4. Environment Variables (`.env`)

Copy `.env.example` to `.env` and insert your credentials:

```ini
# AI Intelligence Provider (Google Gemini Free Tier)
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key
SCREEN_MODEL=gemini-3.5-flash
DRAFT_MODEL=gemini-3.5-flash

# Central Outbound SMTP Server (Gmail App Password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-16-char-gmail-app-password

# Supabase PostgreSQL Multi-Tenant Database & Authentication
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
AUTH_REQUIRED=true
```


---

## 🤖 Supported LLM Providers & Cost Matrix

Screening requires high throughput on dozens of postings (fast & cheap model), while drafting application kits requires strong reasoning (high-capability model). You can split providers for maximum cost efficiency:

| Provider | `LLM_PROVIDER` | Environment Key | Native PDF | Best Recommended Role |
|---|---|---|:---:|---|
| **Google Gemini** | `gemini` | `GEMINI_API_KEY` | ✅ | **Default:** Generous free tier screening & drafting (`gemini-3.5-flash`) |
| **Anthropic** | `anthropic` | `ANTHROPIC_API_KEY` | ✅ | Drafts & Complex Reasoning (Claude 3.7 / 3.5 Sonnet) |
| **Groq** | `groq` | `GROQ_API_KEY` | ❌ | Ultra-fast free screening (Llama 3.3 70B) |
| **OpenAI Compatible** | `openai-compatible` | `GROQ_API_KEY` + `LLM_BASE_URL` | ❌ | OpenRouter, Together AI, vLLM |
| **Ollama** | `ollama` | `OLLAMA_HOST` | ❌ | 100% Offline local models |

---

## 💻 Complete CLI Command Reference

The `jobhunt` CLI provides modular subcommands and master automation scripts:

| Subcommand | Flag / Argument | Default | Description |
|---|---|---|---|
| `jobhunt run` | `-c, --config <path>` | `config.yaml` | Run single-user career intelligence radar. |
| | `--mock` | `false` | Run offline using bundled ATS JSON mock fixtures. |
| | `--send` | `false` | Send HTML digest via SMTP email after generation. |
| | `--scorer {llm, keyword}` | `llm` | Select scoring engine (`llm` or offline `keyword` stub). |
| `jobhunt multi-run` | `-c, --config <path>` | `config.yaml` | **Single-Pass Multi-Tenant Engine**: Crawls all ATS boards once, screens per-candidate profiles, and dispatches individual email briefings. |
| | `--mock` | `false` | Run batch pipeline using offline mock fixtures. |
| | `--send` | `false` | Dispatch briefings to users with email notifications enabled. |
| `jobhunt profile` | `--resume <path>` | *(required)* | Parse resume (`.pdf`, `.txt`, `.md`) to build `profile.json`. |
| | `--yaml` | `false` | Output profile as YAML format instead of JSON. |
| `jobhunt applied` | `<job_id>` | *(required)* | Mark job ID (`ats:slug:id`) as applied in `seen.json`. |
| | `-c, --config <path>` | `config.yaml` | Path to custom config file. |
| `jobhunt stats` | `-c, --config <path>` | `config.yaml` | Print total tracked, emailed, and applied job metrics. |
| `jobhunt web` | `--host <host>, --port <port>` | `5000` | Launch the executive Flask Web Dashboard. |
| `python auto.py` | *(none)* | *(master)* | **1-Click Master Automation Pipeline**: verifies profile, searches ATS, screens, drafts, updates tracking CSV, and launches browser preview. |
| `python app.py` | *(none)* | `http://localhost:5000` | **Executive Web Dashboard & REST API**: Single-page Light Mode UI with zero-refresh sync, Kanban stage transitions (*To Apply*, *Applied*, *Interviewing*, *Offer*, *Rejected*), Resume Studio, CSV export, and kit modal viewer. |

---

## 🚀 Daily 2-Command Workflows

### ☀️ Command 1 — Morning Run (Search + Screen + Draft + Email + Browser Preview)
- **Windows**: `run.bat`
- **macOS / Linux**: `./run.sh`
- **CLI Direct**: `python auto.py`

### 📌 Command 2 — Mark Applied Jobs
- **Windows**: `apply.bat "greenhouse:stripe:5501001"`
- **macOS / Linux**: `./apply.sh "greenhouse:stripe:5501001"`
- **CLI Direct**: `jobhunt applied "greenhouse:stripe:5501001"`

---

## 📊 Tracking & Deduplication (`seen.json` / Supabase)

`seen.json` (and `user_tracked_jobs` in Supabase) acts as both a deduplication index and application pipeline tracker:
- **Deduplication**: Prevents sending duplicate job notifications across runs.
- **Kanban State Machine**: Tracks status transitions (`to_apply` $\rightarrow$ `applied` $\rightarrow$ `interviewing` $\rightarrow$ `offer` $\rightarrow$ `rejected`).
- **Resilience**: Unscored or rate-limited jobs are not written to seen storage and are automatically retried on the next run.
- **Gitignored**: Keeps your private job search data secure and local.

Export current tracking metrics to CSV at any time:
```bash
jobhunt stats
```
*(Generates `out/tracker.csv` compatible with Excel or Google Sheets).*

---

## 🤖 Automated Execution & GitHub Actions

The automated workflow [`.github/workflows/daily.yml`](.github/workflows/daily.yml) runs **automatically on every `push` to `main`** as well as on a schedule **every weekday at 09:00 IST (03:30 UTC)**. State (`seen.json`) is maintained across runs using `actions/cache`.

### 🔑 Required Repository Secrets
Configure these under **Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**:

| Secret Name | Description |
|---|---|
| `PROFILE_JSON` | Full text contents of your local `profile.json` (for single-user mode). |
| `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY` / `GROQ_API_KEY`) | API key for your chosen LLM provider. |
| `SMTP_USER` & `SMTP_PASS` | Gmail address + [App Password](https://myaccount.google.com/apppasswords). |
| `MAIL_TO` | Recipient email address for the daily digest. |
| `SUPABASE_URL` & `SUPABASE_ANON_KEY` | Supabase PostgreSQL credentials (for centralized multi-user mode). |

---

## 🛡️ Continuous Integration (CI Pipeline)

The CI workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) triggers on every push and pull request:
- 🧹 **Linting**: Code formatting verification with Ruff.
- 📐 **Static Typing**: Comprehensive type check with Mypy.
- 🧪 **Unit Test Matrix**: Pytest runner across Python 3.9, 3.10, 3.11, and 3.12 (262+ tests with $\ge 90\%$ coverage).
- ⚡ **Offline Smoke Test**: CLI dry run verification (`jobhunt run --mock --scorer keyword`).

---

## 🏗️ Architecture & Codebase Layout

```text
job-hunter/
├── jobhunt/
│   ├── __init__.py           # Package version (1.0.0) & public exports
│   ├── auth.py               # Supabase Auth, JWT verification, session caching & @require_auth
│   ├── cli.py                # Argparse subcommands (profile, run, multi-run, applied, stats, web)
│   ├── fetch.py              # Job dataclass & 9 ATS API parsers (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, Pinpoint)
│   ├── prefilter.py          # Deterministic regex, location, and freshness filter
│   ├── providers.py          # Provider interface + Gemini/Anthropic/Groq/OpenAI/Ollama clients
│   ├── llm.py                # Screening, drafting, profile extraction & tolerant JSON parser
│   ├── store.py              # seen.json persistence, deduplication, atomic file writes & CSV export
│   ├── memory.py             # Supabase PostgreSQL client with strict tenant isolation (RLS)
│   ├── multi.py              # Single-pass multi-tenant batch execution engine
│   ├── digest.py             # Responsive HTML digest generator with inline CSS & XSS escaping
│   ├── mailer.py             # SMTP client for email delivery
│   ├── mock.py               # Native ATS JSON fixtures for offline testing
│   └── web/                  # Modular Flask Web Dashboard & REST API
│       ├── __init__.py       # Application Factory (create_app), error handlers & security headers
│       ├── state.py          # Thread-safe pipeline execution state & context resolution
│       └── routes/           # Domain-specific Flask Blueprints
│           ├── views.py      # Landing UI, dashboard, health check, logo, auth config
│           ├── jobs.py       # Jobs API, Kanban stage transitions, custom job additions, CSV export
│           ├── profile.py    # Candidate profile, notification settings & Resume Studio PDF/TXT parser
│           └── pipeline.py   # Trigger run, sync heartbeat, execution history, HTML digest
├── templates/
│   └── index.html            # Web dashboard single-page HTML layout & auth modals
├── static/
│   ├── css/style.css         # Clean responsive design system, typography & glassmorphic tokens
│   └── js/app.js             # State persistence, Kanban stage drag/drop, Supabase client & live sync
├── supabase/
│   └── schema.sql            # Multi-Tenant PostgreSQL schema with Row-Level Security (RLS)
├── tests/                    # 262 comprehensive automated test cases (94%+ line coverage)
│   ├── conftest.py           # Pytest shared fixtures & test environment setup
│   ├── test_app.py           # Flask web dashboard, API routes & error handling tests
│   ├── test_web_factory.py   # Application Factory & Blueprint mounting tests
│   ├── test_api_kanban_stage.py # Kanban pipeline stage transitions & email test endpoint
│   ├── test_auth.py          # Supabase auth token verification & endpoint protection tests
│   ├── test_resume_studio.py # Resume Studio PDF/TXT parsing & AI profile extraction tests
│   ├── test_memory.py        # Supabase PostgreSQL storage & tenant isolation tests
│   ├── test_multi_user_batch.py # Multi-user batch execution & candidate isolation tests
│   ├── test_multi_user_dynamic.py # Dynamic candidate prompts & store isolation tests
│   ├── test_auto.py          # Master automation script & fallback tests
│   ├── test_cli.py           # CLI argument parsing & subcommand execution tests
│   ├── test_digest_mailer.py # HTML digest builder, XSS escaping, mail message tests
│   ├── test_fetch.py         # ATS network fetching, session pooling & concurrency tests
│   ├── test_llm.py           # LLM batching, truncation, JSON parsing & stub tests
│   ├── test_parsers.py       # 9 ATS JSON parsers & deterministic prefilter tests
│   ├── test_providers.py     # Provider resolution, env preflight, fallback tests
│   └── test_store.py         # Store persistence, corrupt state recovery, CSV export tests
├── api/
│   └── index.py              # Vercel Serverless Function entrypoint (WSGI adapter)
├── .github/workflows/
│   ├── ci.yml                # CI lint/type-check/test workflow
│   └── daily.yml             # Daily automated execution & digest workflow
├── pyproject.toml            # PEP 621 packaging metadata & tool configurations
├── config.yaml               # Pipeline thresholds & filter rules
├── companies.yaml            # Board targets across 9 ATS engines
├── app.py                    # Classic WSGI Entrypoint (create_app())
├── auto.py                   # Master cross-platform pipeline launcher script
├── run.bat / run.sh          # 1-Click execution scripts
├── apply.bat / apply.sh      # 1-Click apply status marker scripts
├── README.md                 # Master project documentation & narrative
└── docs/                     # End-to-End Documentation Suite
    ├── DEPLOYMENT.md         # 100% Free Production Cloud Deployment Guide
    ├── GUIDE.md              # Personal Utility & Setup Guide
    ├── SETUP.md              # Complete installation & setup guide
    ├── DASHBOARD.md          # Web dashboard & REST API Reference
    ├── ENGINE.md             # LLM Matcher & Scoring engine specifications
    ├── MULTI_USER.md         # Multi-tenant single-pass architecture guide
    ├── TROUBLESHOOTING.md    # Common errors & solutions guide
    ├── CONTRIBUTING.md       # Developer guidelines & testing
    └── JOB_HUNT.md           # System architecture specification prompt
```

---

## ⚡ ATS Quirks & Edge Case Handling

- **Greenhouse**: The `content` HTML field is double HTML-entity-escaped. `strip_html()` unescapes content before and after tag stripping to prevent leaking raw entities like `&amp;` into LLM prompts.
- **Lever**: The `createdAt` property uses epoch **milliseconds**. Converted to UTC datetime objects. Description fields span `descriptionPlain`, `lists[].text`, `lists[].content`, and `additionalPlain` — all concatenated to prevent missing job requirements.
- **Ashby**: Draft postings marked with `isListed: false` are filtered out automatically.
- **Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, Pinpoint**: Resilient field lookups accommodate varying JSON shapes, nested department/location objects, and alternative date fields (`releasedDate`, `published`, `datePosted`, `published_at`).

---

## 🧪 Automated Test Suite

Run the full test suite locally (262 unit & integration tests):
```bash
pytest
```

Run test suite with detailed 98%+ coverage reporting:
```bash
pytest --cov=jobhunt --cov=app --cov=auto --cov-report=term-missing
```

---

## ❓ Troubleshooting & FAQ

> [!WARNING]
> **Gmail Authentication Failed?** You must generate a 16-character **App Password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). Standard account passwords will fail when 2-Step Verification is active.

> [!TIP]
> **Zero jobs returned for a company?** The slug in `companies.yaml` may be invalid or migrated to a different ATS. Verify the company's public job board URL in your browser.

> [!NOTE]
> **Zero API Costs?** Set `SCREEN_PROVIDER=groq` (or `gemini`) and `DRAFT_PROVIDER=gemini`, or run locally using Ollama (`OLLAMA_HOST`).

---

## 📄 Contributing & License

Contributions are welcome! Please refer to **[CONTRIBUTING.md](docs/CONTRIBUTING.md)** for developer instructions and code standards.

Distributed under the **[MIT License](LICENSE)**.
