# jobhunt

A personal, production-grade job-search agent. Every morning, it polls public ATS endpoints (Greenhouse, Lever, Ashby), filters out ~99% of non-matching roles using deterministic rules, scores surviving postings against your resume using LLMs, drafts tailored application kits for top matches, and emails you a clean HTML digest.

**It never submits an application.** It finds, filters, ranks, and drafts. You review the digest in your inbox or browser, refine the draft cover note if desired, and submit the application yourself.

```
2000 postings  →  40 candidates  →  5 in your inbox
   fetch          regex/location      LLM screen
                  /freshness gate     + draft
                  (free, no LLM)
```

> **New to Python?** Read **[SETUP.md](SETUP.md)** for a beginner-friendly 13-step setup guide. This README provides a comprehensive overview of every component, configuration, workflow, and architectural layer.

---

## Table of Contents

- [Quick Start (30-Second Dry Run)](#quick-start-30-second-dry-run)
- [Installation & Packaging](#installation--packaging)
- [Step-by-Step Setup Guide](#step-by-step-setup-guide)
  - [1. Configure Target Companies (`companies.yaml`)](#1-configure-target-companies-companiesyaml)
  - [2. Tune Deterministic Filters (`config.yaml`)](#2-tune-deterministic-filters-configyaml)
  - [3. Build Profile from Resume (`jobhunt profile`)](#3-build-profile-from-resume-jobhunt-profile)
  - [4. Environment Variables (`.env`)](#4-environment-variables-env)
- [Supported LLM Providers & Cost Matrix](#supported-llm-providers--cost-matrix)
- [Daily 2-Command Workflows](#daily-2-command-workflows)
- [Tracking & Deduplication (`seen.json`)](#tracking--deduplication-seenjson)
- [Automated Scheduling (GitHub Actions)](#automated-scheduling-github-actions)
- [Continuous Integration (CI Pipeline)](#continuous-integration-ci-pipeline)
- [Architecture & Codebase Layout](#architecture--codebase-layout)
- [ATS Quirks & Edge Case Handling](#ats-quirks--edge-case-handling)
- [Automated Test Suite](#automated-test-suite)
- [Troubleshooting & FAQ](#troubleshooting--faq)
- [Contributing & License](#contributing--license)

---

## Quick Start (30-Second Dry Run)

Run the full pipeline locally without an API key using bundled ATS fixtures and the dev keyword scorer:

### Windows:
```cmd
git clone <your-repo> && cd job-hunter
python -m venv .venv
.venv\Scripts\activate
pip install -e .

run.bat --mock --scorer keyword
```

### macOS / Linux:
```bash
git clone <your-repo> && cd job-hunter
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

./run.sh --mock --scorer keyword
```

### CLI Command:
```bash
jobhunt run --mock --scorer keyword
```

What happens during the dry run:
```
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
`out/digest.html` will automatically open in your default browser.

---

## Installation & Packaging

`jobhunt` complies with modern **PEP 621** packaging standards via [`pyproject.toml`](pyproject.toml). Installing it in editable mode exposes the global `jobhunt` CLI command:

```bash
pip install -e .
```

To install development dependencies (testing, linting, typing):
```bash
pip install -e ".[dev]"
```

You can execute commands via `jobhunt <subcommand>` or `python -m jobhunt <subcommand>`.

---

## Step-by-Step Setup Guide

### 1. Configure Target Companies (`companies.yaml`)

Edit [`companies.yaml`](companies.yaml) to point at companies you want to track. The `slug` is the final URL path segment of the public careers board:

| Board URL | `ats` | `slug` |
|---|---|---|
| `boards.greenhouse.io/stripe` | `greenhouse` | `stripe` |
| `jobs.lever.co/netlify` | `lever` | `netlify` |
| `jobs.ashbyhq.com/ramp` | `ashby` | `ramp` |

Example structure:
```yaml
companies:
  - {ats: greenhouse, slug: stripe, name: Stripe}
  - {ats: ashby, slug: openai, name: OpenAI}
  - {ats: lever, slug: fampay, name: FamPay}
```

> **Why no LinkedIn or Naukri?** Scraping gated sites violates ToS. Greenhouse, Lever, and Ashby provide unauthenticated, public API endpoints designed for consumption.

### 2. Tune Deterministic Filters (`config.yaml`)

[`config.yaml`](config.yaml) controls the free, deterministic filtering pass executed **before** any LLM call. This pass reduces ~2000 postings down to ~40 candidates for 0 rupees.

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

screen_batch_size: 7
screen_jd_chars: 1400
draft_jd_chars: 7000
score_threshold: 7.0
max_per_digest: 7

# Concurrency & Rate Limit Control
fetch_max_workers: 8      # parallel HTTP requests across ATS boards
llm_max_workers: 1        # concurrent LLM batch workers
llm_delay_seconds: 2.5    # delay between LLM calls
```


### 3. Build Profile from Resume (`jobhunt profile`)

Generate `profile.json` from your resume (`.pdf`, `.txt`, or `.md`):

```bash
jobhunt profile --resume resume.pdf
```

PDF resumes are sent natively as base64 document blocks to Anthropic or Gemini (no OCR required). This generates `profile.json` locally.

> `profile.json` is gitignored. Inspect it, verify extracted skills and target titles, and adjust manually if needed.

### 4. Environment Variables (`.env`)

Copy `.env.example` to `.env` and fill in your keys:

```ini
# LLM Providers
ANTHROPIC_API_KEY="sk-ant-..."
GEMINI_API_KEY="AIzaSy..."
GROQ_API_KEY="gsk_..."

# Model Overrides (Optional)
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

## Supported LLM Providers & Cost Matrix

Screening reads dozens of jobs and needs a fast/cheap model. Drafting runs ~5 times and needs high reasoning. You can configure them separately:

| Provider | `LLM_PROVIDER` | Env Key | Native PDF Support | Notes |
|---|---|---|---|---|
| **Anthropic** | `anthropic` | `ANTHROPIC_API_KEY` | Yes | Default; official SDK |
| **Google Gemini** | `gemini` | `GEMINI_API_KEY` | Yes | Generous free tier |
| **Groq** | `groq` | `GROQ_API_KEY` | No | Extremely fast, free tier |
| **OpenAI-compat** | `openai-compatible` | `GROQ_API_KEY` + `LLM_BASE_URL` | No | OpenRouter, Together, vLLM |
| **Ollama** | `ollama` | `OLLAMA_HOST` | No | Fully offline local model |

---

## Daily 2-Command Workflows

### Command 1 — Morning Run (Search + Screen + Draft + Email + Browser Preview)
- **Windows**: `run.bat`
- **macOS / Linux**: `./run.sh`
- **CLI**: `jobhunt auto`

### Command 2 — Mark Applied Jobs
- **Windows**: `apply.bat "greenhouse:stripe:5501001"`
- **macOS / Linux**: `./apply.sh "greenhouse:stripe:5501001"`
- **CLI**: `jobhunt applied "greenhouse:stripe:5501001"`

---

## Tracking & Deduplication (`seen.json`)

`seen.json` acts as both deduplication index and tracker store:
- Prevents emailing you the same job twice.
- Stores application status (`emailed`, `applied`, `applied_on`).
- `seen.json` is personal and gitignored.

Export current tracking metrics to CSV:
```bash
jobhunt stats
```
Generates `out/tracker.csv` readable by Excel or Google Sheets.

---

## Automated Execution & Live Digest (GitHub Actions)

Workflow [`.github/workflows/daily.yml`](.github/workflows/daily.yml) runs **automatically on every valid `push` to `main`** as well as **every weekday at 06:00 IST (00:30 UTC)**. `seen.json` is preserved seamlessly across runs using `actions/cache`.


### Required GitHub Repository Secrets (Settings → Secrets and variables → Actions):

1. `PROFILE_JSON` — Entire string content of your local `profile.json`.
2. `ANTHROPIC_API_KEY` (or `GEMINI_API_KEY` / `GROQ_API_KEY`).
3. `SMTP_USER` & `SMTP_PASS` — Gmail address + **App Password**.
4. `MAIL_TO` — Recipient email address.

---

## Continuous Integration (CI Pipeline)

Workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) triggers on every push and pull request:
- **Linting**: Ruff code formatting check.
- **Static Type Check**: Mypy verification across package.
- **Unit Tests**: Pytest execution on Python 3.9, 3.10, 3.11, and 3.12.
- **Smoke Test**: `jobhunt run --mock --scorer keyword` dry run.

---

## Architecture & Codebase Layout

```
job-hunter/
├── jobhunt/
│   ├── __init__.py      # Package version (1.0.0) & top-level exports
│   ├── cli.py           # Argparse subcommands (profile, run, applied, stats, auto)
│   ├── fetch.py         # Job dataclass & ATS API parsers (Greenhouse, Lever, Ashby)
│   ├── prefilter.py     # Deterministic regex, location, and age filter
│   ├── providers.py     # Provider interface + Anthropic/Gemini/Groq/OpenAI/Ollama clients
│   ├── llm.py           # Screen, draft, profile extraction & tolerant JSON parser
│   ├── store.py         # seen.json persistence, deduplication & CSV export
│   ├── digest.py        # Responsive HTML digest generator with inline CSS & XSS escaping
│   ├── mailer.py        # SMTP client for email delivery
│   └── mock.py          # Native ATS JSON fixtures for offline testing
├── tests/
│   ├── test_parsers.py  # Native fixture parsing & prefilter tests
│   ├── test_llm.py      # Stubbed LLM tests, batching, truncation, JSON parsing
│   ├── test_cli.py      # CLI subcommand & argument parsing tests
│   ├── test_store.py    # Store persistence, corrupt state recovery, CSV export tests
│   ├── test_providers.py# Provider resolution, env preflight, fallback tests
│   └── test_digest_mailer.py # HTML digest builder, XSS escaping, mail message tests
├── .github/workflows/
│   ├── ci.yml           # CI lint/type-check/test workflow
│   └── daily.yml        # Scheduled daily automated execution workflow
├── pyproject.toml       # PEP 621 packaging metadata & tool configurations
├── setup.py             # Setup fallback wrapper
├── MANIFEST.in          # Packaging manifest
├── LICENSE              # MIT License
├── auto.py              # Cross-platform master automation script
├── run.bat / run.sh     # Windows batch & Unix shell 1-click run launchers
├── apply.bat / apply.sh # Windows batch & Unix shell 1-click apply markers
├── config.yaml          # Pipeline thresholds & filter rules
├── companies.yaml       # Board targets
├── README.md            # Master documentation
├── SETUP.md             # 13-step guide for beginners
└── CONTRIBUTING.md      # Developer guide
```

---

## ATS Quirks & Edge Case Handling

1. **Greenhouse**:
   - `content` HTML field is HTML-entity-escaped HTML. `strip_html()` unescapes before and after tag stripping to avoid leaking `&amp;` into prompts.
2. **Lever**:
   - `createdAt` is epoch **milliseconds**. Converted cleanly to UTC dates.
   - Job description is split across `descriptionPlain`, `lists[].text`, `lists[].content`, and `additionalPlain`. All chunks are concatenated to preserve full requirements.
3. **Ashby**:
   - Draft jobs with `isListed: false` are automatically ignored.

---

## Automated Test Suite

Run unit tests locally:
```bash
pytest
```
Run unit tests with coverage reporting:
```bash
pytest --cov=jobhunt --cov-report=term-missing
```

---

## Troubleshooting & FAQ

#### Q: A company board reports `0 jobs` every day.
- The company slug in `companies.yaml` may be dead or migrated to another ATS. Check the public board URL in your browser.

#### Q: Gmail SMTP fails with Authentication Failed.
- You must generate a dedicated **App Password** at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords). Normal Gmail passwords fail when 2FA is active.

#### Q: How do I run completely free without API costs?
- Set `SCREEN_PROVIDER=groq` (or `gemini`) and `DRAFT_PROVIDER=gemini`, or use local Ollama models (`OLLAMA_HOST`).

---

## Contributing & License

- Developer guidelines: **[CONTRIBUTING.md](CONTRIBUTING.md)**
- License: **[MIT License](LICENSE)**
