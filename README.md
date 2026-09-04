<div align="center">

# 🏹 Job Hunter (`job-hunter`)

### *Autonomous AI-Powered Career Intelligence & Job Hunting Agent*

[![Python Version](https://img.shields.io/badge/python-3.9%20%7C%203.10%20%7C%203.11%20%7C%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![CI Status](https://img.shields.io/github/actions/workflow/status/tanish-jain-225/job-hunter/ci.yml?branch=main&style=for-the-badge&label=CI&color=success)](https://github.com/tanish-jain-225/job-hunter/actions/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-395%20passed-success?style=for-the-badge&logo=pytest&logoColor=white)](tests/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-black?style=for-the-badge&logo=ruff)](https://github.com/astral-sh/ruff)

</div>

---

## 📖 The Narrative: Why Job Hunter?

Modern job searching is broken. Engineers spend hours every week manually sifting through thousands of irrelevant job board postings, dealing with spam, guessing fit percentages, and writing repetitive cover letters. 

**Job Hunter (`job-hunter`)** is built to solve this. It is your personal, autonomous career intelligence agent that operates 24/7. Every morning while you sleep, **Job Hunter**:
1. 🌐 **Scouts Target Boards**: Polls public, unauthenticated ATS endpoints across 9 platforms (**Greenhouse**, **Lever**, **Ashby**, **Workable**, **SmartRecruiters**, **BambooHR**, **Recruitee**, **Breezy HR**, **Pinpoint**).
2. 🎯 **Filters the Noise**: Eliminates ~99% of irrelevant, out-of-scope, or outdated postings deterministically using regex rules at **$0 API cost**.
3. ⚡ **Screening & Intelligence**: High-throughput candidate screening (1.0 - 10.0) powered by **Google Gemini (`gemini-3.7-flash`, 1M tokens/day)** by default, with multi-key CSV rotation, automatic offline fallback, and optional support for Anthropic Claude, Groq, Ollama, and any OpenAI-compatible endpoint.
4. ✍️ **Drafts Application Kits & Follow-Up Notes**: Auto-generates tailored cover notes, 80-word cold outreach messages, matching resume bullets, and smart follow-up templates using **Google Gemini (`gemini-3.7-flash`)**.
5. 📊 **Visual Kanban, Live SSE Streaming & Daily Bounty**: Organizes opportunities across a visual Kanban Pipeline (*To Apply*, *Applied*, *Interviewing*, *Offer*, *Rejected*), streams real-time logs via Server-Sent Events (SSE), supports 1-click custom ATS career portal ingestion ("+ Add Board"), and delivers HTML briefings with brand logo thumbnails and live web board links.
6. 🔒 **Strict View State Isolation & Pure Flexbox Responsiveness**: Complete state separation between unauthenticated visitors (clean landing page) and authenticated candidates, with every utility guarded behind auth, and zero horizontal scrolling down to 300px mobile viewports.

> [!IMPORTANT]
> **The Golden Rule of Job Hunter**: *The Hunter never fires without manual authorization.* **Job Hunter** never auto-submits applications. It handles scouting, filtering, ranking, and drafting—leaving final application submission strictly under your control.

```text
┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
│ 1. Scout Postings   │ ───►  │ 2. Stealth Filter   │ ───►  │ 3. Precision Screen │ ───►  │ 4. Daily Bounty     │
│ ~5,000 ATS Roles    │       │ ~50 Matching Roles  │       │ ~5 Top Matches      │       │ Kanban Board & Mail │
└─────────────────────┘       └─────────────────────┘       └─────────────────────┘       └─────────────────────┘
  (9 Major ATS Engines)        (0 API Cost Filter)           (Google Gemini 3.7)           (Dashboard / Inbox)
```

> [!TIP]
> **First time setting up?** Check out **[SETUP.md](docs/SETUP.md)** for a beginner-friendly setup guide, **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** for 100% free multi-user cloud deployment, **[METRICS.md](METRICS.md)** for business metrics & scaling economics, or **[MULTI_USER.md](docs/MULTI_USER.md)** for architecture scaling details.

---

## 📋 Table of Contents

- [📖 The Narrative: Why Job Hunter?](#-the-narrative-why-job-hunter)
- [⚡ Quick Start (30-Second Dry Run)](#-quick-start-30-second-dry-run)
- [📦 Installation & Packaging](#-installation--packaging)
- [⚙️ Step-by-Step Setup Guide](#%EF%B8%8F-step-by-step-setup-guide)
  - [1. Configure Target Companies (`companies.yaml`)](#1-configure-target-companies-companiesyaml)
  - [2. Tune Deterministic Filters (`config.yaml`)](#2-tune-deterministic-filters-configyaml)
  - [3. Build Candidate Profile (`jobhunt profile`)](#3-build-candidate-profile-jobhunt-profile)
  - [4. Environment Variables (`.env`)](#4-environment-variables-env)
- [🤖 AI Engine: Google Gemini Flash — Default & Recommended](#-ai-engine-google-gemini-flash-gemini-37-flash--default--recommended)
- [💻 Complete CLI Command Reference](#-complete-cli-command-reference)
- [🚀 Daily Workflows](#-daily-workflows)
- [📊 Tracking & Deduplication (`seen.json` / Supabase)](#-tracking--deduplication-seenjson--supabase)
- [🤖 Automated Execution & GitHub Actions](#-automated-execution--github-actions)
- [🛡️ Continuous Integration (CI Pipeline)](#%EF%B8%8F-continuous-integration-ci-pipeline)
- [🏗️ Architecture & Codebase Layout](#%EF%B8%8F-architecture--codebase-layout)
- [⚡ ATS Quirks & Edge Case Handling](#-ats-quirks--edge-case-handling)
- [🧪 Automated Test Suite](#-automated-test-suite)
- [❓ Troubleshooting & FAQ](#-troubleshooting--faq)
- [📄 Contributing & License](#-contributing--license)

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
| `jobs.lever.co/meesho` | `lever` | `meesho` |
| `jobs.ashbyhq.com/openai` | `ashby` | `openai` |
| `apply.workable.com/vector` | `workable` | `vector` |
| `jobs.smartrecruiters.com/visa` | `smartrecruiters` | `visa` |
| `acme.bamboohr.com/careers` | `bamboohr` | `acme` |
| `bunq.recruitee.com` | `recruitee` | `bunq` |
| `breezy.hr/acme` | `breezy` | `acme` |
| `pinpoint.work/company` | `pinpoint` | `company` |

```yaml
companies:
  - {ats: greenhouse, slug: stripe, name: Stripe}
  - {ats: ashby, slug: openai, name: OpenAI}
  - {ats: lever, slug: meesho, name: Meesho}
  - {ats: workable, slug: vector, name: Vector}
  - {ats: smartrecruiters, slug: visa, name: Visa}
  - {ats: bamboohr, slug: acme, name: Acme}
  - {ats: recruitee, slug: bunq, name: Bunq}
  - {ats: greenhouse, slug: razorpaysoftwareprivatelimited, name: Razorpay}
  - {ats: ashby, slug: ramp, name: Ramp}
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
  max_age_days: 21

screen_batch_size: 8      # Jobs per screening LLM call (optimal for Gemini Flash)
screen_jd_chars: 1000     # Context truncation for precise evaluation
draft_jd_chars: 6000      # Full context for kit drafting
score_threshold: 7.0      # Score threshold (1.0 to 10.0 bar for shortlist)
max_per_digest: 7         # Maximum job kits per digest briefing
max_jobs_to_screen: 30    # Max unseen jobs evaluated per run (rate-limit guard)

# High-Performance Concurrency & Zero-Cost Rate Limits
fetch_max_workers: 16     # Parallel HTTP requests across ATS boards
llm_max_workers: 1        # Sequential batch workers to strictly prevent rate limit spikes
llm_delay_seconds: 6.0    # 6.0s = exactly 10 RPM (Gemini free tier ceiling)
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
# AI Intelligence Provider (Google Gemini Flash — 1M Tokens/Day per project)
# • GEMINI_API_KEY: High-throughput screening & tailored kit drafting (aistudio.google.com)
# Supports comma-separated keys for instant multi-key rotation: key1,key2,key3
GEMINI_API_KEY=AIzaSy_your_gemini_api_key_here

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

# GitHub Actions Workflow Dispatch (Cloud On-Demand Radar)
GH_TOKEN=github_pat_your_personal_access_token_here
GITHUB_REPOSITORY=your-github-username/job-hunter

# Optional: Static Flask secret key for serverless session stability
FLASK_SECRET_KEY=jobhunter-secure-prod-flask-key-2025

# Optional: Stage / Provider overrides
# LLM_PROVIDER=gemini
# SCREEN_MODEL=gemini-3.7-flash
# DRAFT_MODEL=gemini-3.7-flash
```

---

## 🤖 AI Engine: Google Gemini Flash (`gemini-3.7-flash`) — Default & Recommended

Job Hunter defaults to **Google Gemini Flash (`gemini-3.7-flash`)**, providing 1,000,000+ tokens per day free tier allowance per project, 1M token context windows, native Base64 PDF resume parsing, and multi-key CSV rotation. Alternative providers (Anthropic Claude, Groq, Ollama, any OpenAI-compatible endpoint) are fully supported via environment variable overrides.

```mermaid
flowchart LR
    A["Raw Crawled Postings"] --> B["Stage 1: Batch Screening<br/>⚡ Google Gemini (3.7 Flash)<br/>1M Tokens/Day per Key"]
    B --> C["Stage 2: Kit Drafting<br/>🧠 Google Gemini (3.7 Flash)<br/>Cover Note, Cold Message, Bullets"]
    C --> D["Daily Briefing & Web Kanban"]
```

| Provider | Default Model | Environment Key | Native PDF | Role in Job Hunter |
|---|---|---|:---:|---|
| **Google Gemini** ⭐ | `gemini-3.7-flash` | `GEMINI_API_KEY` | ✅ | **Default Engine:** Batch Fit Screening & Application Kit Drafting (1M Tokens/Day per key, CSV rotation) |
| **Anthropic Claude** | `claude-3-7-sonnet-20250219` | `ANTHROPIC_API_KEY` | ✅ | Optional drop-in (`pip install 'jobhunt[anthropic]'`; set `LLM_PROVIDER=anthropic`) |
| **Groq** | `llama-3.3-70b-versatile` | `GROQ_API_KEY` | ❌ | Optional ultra-fast inference (`LLM_PROVIDER=groq`) |
| **Ollama** | `llama3.1` | *(none — local)* | ❌ | Fully local / air-gapped (`LLM_PROVIDER=ollama`) |
| **OpenAI-compatible** | `gpt-4o` | `GROQ_API_KEY` / `LLM_BASE_URL` | ❌ | Any `/chat/completions` endpoint (`LLM_PROVIDER=openai-compatible`) |

> [!TIP]
> Override the active provider at any time via env vars: `LLM_PROVIDER=groq`, `SCREEN_PROVIDER=gemini`, `DRAFT_PROVIDER=anthropic`, `SCREEN_MODEL=...`, `DRAFT_MODEL=...`.

---

## 💻 Complete CLI Command Reference

The `jobhunt` CLI provides modular subcommands and master automation scripts:

| Subcommand | Flag / Argument | Default | Description |
|---|---|---|---|
| `jobhunt run` | `-c, --config <path>` | `config.yaml` | Run single-user career intelligence radar. |
| | `--mock` | `false` | Run offline using bundled ATS JSON mock fixtures. |
| | `--send` | `false` | Send HTML digest via SMTP email after generation. |
| | `--strict-llm` | `false` | Enforce 100% real AI execution (disables keyword fallback on rate limit). |
| | `--scorer {llm, keyword}` | `llm` | Select scoring engine (`llm` or offline `keyword` stub). |
| `jobhunt multi-run` | `-c, --config <path>` | `config.yaml` | **Single-Pass Multi-Tenant Engine**: Crawls all ATS boards once, screens per-candidate profiles, and dispatches individual email briefings. |
| | `--mock` | `false` | Run batch pipeline using offline mock fixtures. |
| | `--send` | `false` | Dispatch briefings to users with email notifications enabled. |
| | `--strict-llm` | `false` | Enforce 100% real AI execution for all candidate runs. |
| `jobhunt verify` | `--companies <path>` | `companies.yaml` | Audit target company career boards live against public ATS APIs. |
| | `--workers <count>` | `25` | Max parallel HTTP request worker threads. |
| `jobhunt clean` | `--dry-run` | `false` | Safely purge temporary test stores (`seen_*.json`) and transient artifacts from root. |
| `jobhunt profile` | `--resume <path>` | *(required)* | Parse resume (`.pdf`, `.txt`, `.md`) to build `profile.json`. |
| | `--yaml` | `false` | Output profile as YAML format instead of JSON. |
| `jobhunt applied` | `<job_id>` | *(required)* | Mark job ID (`ats:slug:id`) as applied in `seen.json`. |
| | `-c, --config <path>` | `config.yaml` | Path to custom config file. |
| `jobhunt stats` | `-c, --config <path>` | `config.yaml` | Print total tracked, emailed, and applied job metrics. |
| `jobhunt web` | `--host <host>, --port <port>` | `5000` | Launch the executive Flask Web Dashboard. |
| `python auto.py` | *(none)* | *(master)* | **1-Click Master Automation Pipeline**: verifies profile, searches ATS, screens, drafts, updates tracking CSV, and launches browser preview. |
| `python app.py` | *(none)* | `http://localhost:5000` | **Executive Web Dashboard & REST API**: Single-page Light Mode UI with zero-refresh sync, Kanban stage transitions (*To Apply*, *Applied*, *Interviewing*, *Offer*, *Rejected*), Resume Studio, CSV export, and kit modal viewer. |

---

## 🚀 Daily Workflows

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
- **Connection Resilience**: Supabase database queries and board scrapes employ pooled sessions configured with automatic exponential backoff retries (`Retry` adapter) to survive transient serverless cold starts or connection drops.
- **Gitignored & Security Guarded**: Keeps your private job search data secure and local. A Git staging check in the local runner warns you if your credential-loaded `.env` file is accidentally tracked in Git.

Export current tracking metrics to CSV at any time:
```bash
jobhunt stats
```
*(Generates `out/tracker.csv` compatible with Excel or Google Sheets).*

---

## 🤖 Automated Execution & GitHub Actions

The automated workflow [`.github/workflows/daily.yml`](.github/workflows/daily.yml) runs **automatically on every `push` to `main`** as well as on a schedule **every single day at 05:00 IST (23:30 UTC)**. State (`seen.json`) is maintained across runs using `actions/cache`.

### 🔑 Required Repository Secrets
Configure these under **Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**:

| Secret Name | Description |
|---|---|
| `GEMINI_API_KEY` | Free Google Gemini API key for candidate screening and kit drafting (aistudio.google.com). |
| `SMTP_USER` & `SMTP_PASS` | Gmail address + [App Password](https://myaccount.google.com/apppasswords). |
| `MAIL_TO` | Recipient email address for the daily digest (single-user mode). |
| `SUPABASE_URL` & `SUPABASE_ANON_KEY` | Supabase PostgreSQL credentials (for centralized multi-user mode). |
| `PROFILE_JSON` | Full text contents of your local `profile.json` (for single-user mode). |

---

## 🛡️ Continuous Integration (CI Pipeline)

The CI workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) triggers on every push and pull request:
- 🧹 **Linting**: Code formatting verification with Ruff.
- 📐 **Static Typing**: Comprehensive type check with Mypy.
- 🧪 **Unit Test Matrix**: Pytest runner across Python 3.9, 3.10, 3.11, and 3.12 (395 automated tests with $\ge 91\%$ coverage).
- ⚡ **Offline Smoke Test**: CLI dry run verification (`jobhunt run --mock --scorer keyword`).

---

## 🏗️ Architecture & Codebase Layout

```text
job-hunter/
├── jobhunt/
│   ├── __init__.py           # Package version (1.0.0) & public exports
│   ├── auth.py               # Supabase Auth, JWT verification, session caching & @require_auth
│   ├── clean.py              # Temporary file and test store cleanup utility
│   ├── cli.py                # Argparse subcommands (profile, run, multi-run, applied, stats, verify, clean, web)
│   ├── fetch.py              # Job dataclass & 9 ATS API parsers (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, Pinpoint)
│   ├── prefilter.py          # Safe regex compilation, deterministic location, and freshness filter
│   ├── providers.py          # Multi-provider AI clients: Gemini (default), Anthropic, Groq, Ollama, OpenAI-compat
│   ├── llm.py                # Screening, drafting, profile extraction & tolerant JSON parser
│   ├── store.py              # seen.json persistence, deduplication, atomic file writes & CSV export
│   ├── memory.py             # Supabase PostgreSQL client with strict tenant isolation (RLS) & in-memory caching
│   ├── multi.py              # Single-pass multi-tenant batch execution engine
│   ├── digest.py             # Responsive HTML digest generator with inline CSS & XSS escaping
│   ├── mailer.py             # SMTP client for email delivery
│   ├── mock.py               # Native ATS JSON fixtures for offline testing
│   ├── verify.py             # Live ATS career board auditor
│   └── web/                  # Modular Flask Web Dashboard & REST API
│       ├── __init__.py       # Application Factory (create_app), error handlers & security headers
│       ├── state.py          # Thread-safe pipeline execution state, SSE circular buffers & context resolution
│       └── routes/           # Domain-specific Flask Blueprints
│           ├── views.py      # Landing UI, dashboard, health check, logo, auth config
│           ├── jobs.py       # Jobs API, Kanban stage transitions, custom company additions, CSV export
│           ├── profile.py    # Candidate profile, notification settings & Resume Studio (30s AI ceiling + fallback parser)
│           └── pipeline.py   # Trigger run, SSE log streaming, sync heartbeat, execution history, HTML digest
├── templates/
│   └── index.html            # Web dashboard single-page HTML layout & auth modals
├── static/
│   ├── css/style.css         # Responsive design system down to 300px width, typography & glassmorphic tokens
│   └── js/app.js             # State persistence, Kanban stage drag/drop, Supabase client & live sync
├── supabase/
│   ├── schema.sql            # Multi-Tenant PostgreSQL schema with Row-Level Security (RLS)
│   └── teardown.sql          # Idempotent schema reset & companion teardown script
├── tests/                    # 395 comprehensive automated test cases (91%+ line coverage)
│   ├── conftest.py           # Pytest shared fixtures & test environment setup
│   ├── test_e2e_live_comprehensive.py # Comprehensive 14-suite live integration test matrix
│   ├── test_app.py           # Flask web dashboard, API routes & error handling tests
│   ├── test_web_factory.py   # Application Factory & Blueprint mounting tests
│   ├── test_api_kanban_stage.py # Kanban pipeline stage transitions & email test endpoint
│   ├── test_auth.py          # Supabase auth token verification & endpoint protection tests
│   ├── test_flow_perfection.py # URL auto-detection, custom company CRUD, SSE stream, follow-up tests
│   ├── test_resume_studio.py # Resume Studio PDF/TXT parsing & AI profile extraction tests
│   ├── test_memory.py        # Supabase PostgreSQL storage & tenant isolation tests
│   ├── test_resilience_scaling.py # Bounded memory, caching, safe regex & scaling tests
│   ├── test_multi_user_batch.py # Multi-user batch execution & candidate isolation tests
│   ├── test_multi_user_dynamic.py # Dynamic candidate prompts & store isolation tests
│   ├── test_auto.py          # Master automation script & fallback tests
│   ├── test_clean_and_verify.py # Clean and verify CLI subcommand tests
│   ├── test_cli.py           # CLI argument parsing & subcommand execution tests
│   ├── test_digest_mailer.py # HTML digest builder, XSS escaping, mail message tests
│   ├── test_fetch.py         # ATS network fetching, session pooling & concurrency tests
│   ├── test_llm.py           # LLM batching, truncation, JSON parsing & stub tests
│   ├── test_llm_resilience.py # LLM resilience and error recovery tests
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

Run the full test suite locally (395 unit & integration tests):
```bash
pytest
```


Run test suite with detailed 90%+ coverage reporting:
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
> **Zero API Costs?** Google Gemini Flash (`gemini-3.7-flash`) provides 1,000,000+ daily tokens per project at $0 cost (with multi-key CSV rotation: `GEMINI_API_KEY=key1,key2`), or run locally using Ollama (`OLLAMA_HOST`).

---

## 📄 Contributing & License

Contributions are welcome! Please refer to **[CONTRIBUTING.md](docs/CONTRIBUTING.md)** for developer instructions and code standards.

Distributed under the **[MIT License](LICENSE)**.
