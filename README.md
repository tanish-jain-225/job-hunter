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
1. 🌐 **Scouts Target Boards**: Polls public, unauthenticated ATS endpoints (**Greenhouse**, **Lever**, **Ashby**) across target companies.
2. 🎯 **Filters the Noise**: Eliminates ~99% of irrelevant, out-of-scope, or outdated postings deterministically using regex rules at **$0 API cost**.
3. 🧠 **Screening & Intelligence**: Scores surviving roles (1.0 - 10.0) against your candidate profile using high-throughput LLMs.
4. ✍️ **Drafts Application Kits**: Auto-generates tailored cover notes, matching resume bullets, and gap analyses for top-ranked matches.
5. 📬 **Delivers Daily Bounty**: Transmits a crisp, interactive HTML digest to your inbox and opens a local browser briefing.

> [!IMPORTANT]
> **The Golden Rule of Job Hunter**: *The Hunter never fires without manual authorization.* **Job Hunter** never auto-submits applications. It handles scouting, filtering, ranking, and drafting—leaving final application submission strictly under your control.

```text
┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐       ┌─────────────────────┐
│ 1. Scout Postings   │ ───►  │ 2. Stealth Filter   │ ───►  │ 3. Precision Screen │ ───►  │ 4. Daily Bounty     │
│ ~2,000 ATS Roles    │       │ ~40 Matching Roles  │       │ ~5 Top Matches      │       │ HTML Digest & Email │
└─────────────────────┘       └─────────────────────┘       └─────────────────────┘       └─────────────────────┘
  (Greenhouse/Lever/Ashby)     (0 API Cost Filter)           (Anthropic/Gemini/Groq)        (Inbox / Browser)
```

> [!TIP]
> **First time setting up?** Check out **[SETUP.md](SETUP.md)** for a beginner-friendly 13-step setup guide.

---

## 📋 Table of Contents

- [📖 The Narrative: Why Job Hunter?](#-the-narrative-why-job-hunter)
- [⚡ Quick Start (30-Second Dry Run)](#-quick-start-30-second-dry-run)
- [📦 Installation \& Packaging](#-installation--packaging)
- [⚙️ Step-by-Step Setup Guide](#%EF%B8%8F-step-by-step-setup-guide)
  - [1. Configure Target Companies (`companies.yaml`)](#1-configure-target-companies-companiesyaml)
  - [2. Tune Deterministic Filters (`config.yaml`)](#2-tune-deterministic-filters-configyaml)
  - [3. Build Candidate Profile (`jobhunt profile`)](#3-build-candidate-profile-jobhunt-profile)
  - [4. Environment Variables (`.env`)](#4-environment-variables-env)
- [🤖 Supported LLM Providers \& Cost Matrix](#-supported-llm-providers--cost-matrix)
- [💻 Complete CLI Command Reference](#-complete-cli-command-reference)
- [🚀 Daily 2-Command Workflows](#-daily-2-command-workflows)
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

```yaml
companies:
  - {ats: greenhouse, slug: stripe, name: Stripe}
  - {ats: ashby, slug: openai, name: OpenAI}
  - {ats: lever, slug: fampay, name: FamPay}
```

> [!NOTE]
> **Why public ATS boards instead of LinkedIn/Naukri?** Scraping auth-gated sites violates Terms of Service and breaks constantly. Greenhouse, Lever, and Ashby expose clean, unauthenticated JSON endpoints officially intended for public job listing retrieval.

---

### 2. Tune Deterministic Filters (`config.yaml`)

[`config.yaml`](config.yaml) manages the free regex-based filtering step executed **before** sending candidate jobs to LLMs. This pre-filter reduces ~2000 raw postings down to ~40 candidates at zero API cost.

```yaml
filters:
  include_titles:
    - 'software engineer'
    - '\bsde\b'
    - '\bsde\s*-?\s*(i{1,3}|[123])\b'
    - '\b(backend|full.?stack|frontend)\b.*\bengineer\b'
  exclude_titles:
    - '\b(staff|principal|architect|director|vp|head of)\b'
    - '\bsenior\b'
    - '\b(intern|internship|apprentice)\b'
  locations:
    - bangalore
    - bengaluru
    - mumbai
    - pune
    - remote
  allow_remote: true
  max_age_days: 28

screen_batch_size: 7      # Jobs per screening LLM call
screen_jd_chars: 1400     # Job description truncation length for screening
draft_jd_chars: 7000      # Job description truncation length for drafting
score_threshold: 7.0      # Score threshold (1.0 to 10.0 bar for shortlist)
max_per_digest: 7         # Maximum job kits per digest email

# Concurrency & Rate Control
fetch_max_workers: 8      # Parallel HTTP requests across ATS boards
llm_max_workers: 1        # Concurrent LLM batch workers
llm_delay_seconds: 2.5    # Throttle delay between LLM calls
```

---

### 3. Build Candidate Profile (`jobhunt profile`)

Generate [`profile.json`](profile.example.json) directly from your resume (`.pdf`, `.txt`, or `.md`):

```bash
jobhunt profile --resume resume.pdf
```

> [!TIP]
> PDF resumes are submitted natively as base64 document blocks to Anthropic Claude or Google Gemini (no OCR required). Inspect the generated `profile.json` locally and fine-tune your extracted skills, target titles, or experience summary if needed.

---

### 4. Environment Variables (`.env`)

Copy `.env.example` to `.env` and insert your credentials:

```ini
# LLM Provider Keys
ANTHROPIC_API_KEY="sk-ant-..."
GEMINI_API_KEY="AIzaSy..."
GROQ_API_KEY="gsk_..."

# Model Selection & Provider Overrides
LLM_PROVIDER="anthropic"
SCREEN_PROVIDER="groq"
DRAFT_PROVIDER="anthropic"
SCREEN_MODEL="llama-3.3-70b-versatile"
DRAFT_MODEL="claude-3-7-sonnet-20250219"

# Email SMTP Settings (Gmail)
SMTP_HOST="smtp.gmail.com"
SMTP_PORT=587
SMTP_USER="your-email@gmail.com"
SMTP_PASS="your-gmail-app-password"
MAIL_TO="your-email@gmail.com"
```

---

## 🤖 Supported LLM Providers & Cost Matrix

Screening requires high throughput on dozens of postings (fast & cheap model), while drafting application kits requires strong reasoning (high-capability model). You can split providers for maximum cost efficiency:

| Provider | `LLM_PROVIDER` | Environment Key | Native PDF | Best Recommended Role |
|---|---|---|:---:|---|
| **Anthropic** | `anthropic` | `ANTHROPIC_API_KEY` | ✅ | Drafts & Complex Reasoning (Claude 3.7 / 3.5) |
| **Google Gemini** | `gemini` | `GEMINI_API_KEY` | ✅ | Free tier screening & drafting (Gemini 1.5/2.0) |
| **Groq** | `groq` | `GROQ_API_KEY` | ❌ | Ultra-fast free screening (Llama 3.3 70B) |
| **OpenAI Compatible** | `openai-compatible` | `GROQ_API_KEY` + `LLM_BASE_URL` | ❌ | OpenRouter, Together AI, vLLM |
| **Ollama** | `ollama` | `OLLAMA_HOST` | ❌ | 100% Offline local models |

---

## 💻 Complete CLI Command Reference

The `jobhunt` CLI provides 4 main subcommands and 1 master automation script:

| Subcommand | Flag / Argument | Default | Description |
|---|---|---|---|
| `jobhunt run` | `-c, --config <path>` | `config.yaml` | Path to custom YAML configuration file. |
| | `--mock` | `false` | Run offline using bundled ATS JSON mock fixtures. |
| | `--send` | `false` | Send HTML digest via SMTP email after generation. |
| | `--scorer {llm, keyword}` | `llm` | Select scoring engine (`llm` or offline `keyword` stub). |
| `jobhunt profile` | `--resume <path>` | *(required)* | Parse resume (`.pdf`, `.txt`, `.md`) to build `profile.json`. |
| | `--yaml` | `false` | Output profile as YAML format instead of JSON. |
| `jobhunt applied` | `<job_id>` | *(required)* | Mark job ID (`ats:slug:id`) as applied in `seen.json`. |
| | `-c, --config <path>` | `config.yaml` | Path to custom config file. |
| `jobhunt stats` | `-c, --config <path>` | `config.yaml` | Print total tracked, emailed, and applied job metrics. |
| `python auto.py` | *(none)* | *(master)* | **1-Click End-to-End Pipeline**: verifies profile, searches ATS, screens, drafts, updates tracking CSV, and launches browser preview. |

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

## 📊 Tracking & Deduplication (`seen.json`)

`seen.json` acts as both a deduplication index and application status tracker:
- **Deduplication**: Prevents sending duplicate job notifications across runs.
- **State Machine**: Tracks status transitions (`emailed` $\rightarrow$ `applied` with timestamp `applied_on`).
- **Resilience**: Unscored or rate-limited jobs are not written to `seen.json` and are automatically retried on the next run.
- **Gitignored**: Keeps your private job search data local.

Export current tracking metrics to CSV at any time:
```bash
jobhunt stats
```
*(Generates `out/tracker.csv` compatible with Excel or Google Sheets).*

---

## 🤖 Automated Execution & GitHub Actions

The automated workflow [`.github/workflows/daily.yml`](.github/workflows/daily.yml) runs **automatically on every `push` to `main`** as well as on a schedule **every weekday at 06:00 IST (00:30 UTC)**. State (`seen.json`) is maintained across runs using `actions/cache`.

### 🔑 Required Repository Secrets
Configure these under **Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions**:

| Secret Name | Description |
|---|---|
| `PROFILE_JSON` | Full text contents of your local `profile.json`. |
| `ANTHROPIC_API_KEY` (or `GEMINI_API_KEY` / `GROQ_API_KEY`) | API key for your chosen LLM provider. |
| `SMTP_USER` & `SMTP_PASS` | Gmail address + [App Password](https://myaccount.google.com/apppasswords). |
| `MAIL_TO` | Recipient email address for the daily digest. |

---

## 🛡️ Continuous Integration (CI Pipeline)

The CI workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) triggers on every push and pull request:
- 🧹 **Linting**: Code formatting verification with Ruff.
- 📐 **Static Typing**: Comprehensive type check with Mypy.
- 🧪 **Unit Test Matrix**: Pytest runner across Python 3.9, 3.10, 3.11, and 3.12.
- ⚡ **Offline Smoke Test**: CLI dry run verification (`jobhunt run --mock --scorer keyword`).

---

## 🏗️ Architecture & Codebase Layout

```text
job-hunter/
├── jobhunt/
│   ├── __init__.py           # Package version (1.0.0) & public exports
│   ├── cli.py                # Argparse subcommands (profile, run, applied, stats, auto)
│   ├── fetch.py              # Job dataclass & ATS API parsers (Greenhouse, Lever, Ashby)
│   ├── prefilter.py          # Deterministic regex, location, and age filter
│   ├── providers.py          # Provider interface + Anthropic/Gemini/Groq/OpenAI/Ollama clients
│   ├── llm.py                # Screen, draft, profile extraction & tolerant JSON parser
│   ├── store.py              # seen.json persistence, deduplication & CSV export
│   ├── digest.py             # Responsive HTML digest generator with inline CSS & XSS escaping
│   ├── mailer.py             # SMTP client for email delivery
│   └── mock.py               # Native ATS JSON fixtures for offline testing
├── tests/
│   ├── test_parsers.py       # ATS JSON parsing & prefilter test suite
│   ├── test_llm.py           # LLM batching, truncation, JSON parsing & stub tests
│   ├── test_cli.py           # CLI argument parsing & subcommand execution tests
│   ├── test_store.py         # Store persistence, corrupt state recovery, CSV export tests
│   ├── test_providers.py     # Provider resolution, env preflight, fallback tests
│   └── test_digest_mailer.py # HTML digest builder, XSS escaping, mail message tests
├── .github/workflows/
│   ├── ci.yml                # CI lint/type-check/test workflow
│   └── daily.yml             # Daily automated execution & digest workflow
├── pyproject.toml            # PEP 621 packaging metadata & tool configurations
├── config.yaml               # Pipeline thresholds & filter rules
├── companies.yaml            # Board targets
├── auto.py                   # Master cross-platform pipeline launcher script
├── run.bat / run.sh          # 1-Click execution scripts
├── apply.bat / apply.sh      # 1-Click apply status marker scripts
├── README.md                 # Master project documentation & narrative
├── SETUP.md                  # 13-step beginner setup guide
└── CONTRIBUTING.md           # Developer guidelines
```

---

## ⚡ ATS Quirks & Edge Case Handling

- **Greenhouse**: The `content` HTML field is double HTML-entity-escaped. `strip_html()` unescapes content before and after tag stripping to prevent leaking raw entities like `&amp;` into LLM prompts.
- **Lever**: The `createdAt` property uses epoch **milliseconds**. Converted to UTC datetime objects. Description fields span `descriptionPlain`, `lists[].text`, `lists[].content`, and `additionalPlain` — all concatenated to prevent missing job requirements.
- **Ashby**: Draft postings marked with `isListed: false` are filtered out automatically.

---

## 🧪 Automated Test Suite

Run unit tests locally:
```bash
pytest
```

Run test suite with detailed coverage reporting:
```bash
pytest --cov=jobhunt --cov-report=term-missing
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

Contributions are welcome! Please refer to **[CONTRIBUTING.md](CONTRIBUTING.md)** for developer instructions and code standards.

Distributed under the **[MIT License](LICENSE)**.
