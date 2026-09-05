<p align="center">
  <img src="../assets/logo.png" alt="Job Hunter Logo" width="100" height="100">
</p>

# 🛠️ Complete End-to-End Stepwise Setup Guide — Job Hunter

Welcome to the definitive setup guide for **Job Hunter**. This document walks you through every single step required to configure, test, run, and deploy the entire product from scratch—whether you want a 100% private, database-free desktop utility on your laptop, or a full-fledged, multi-tenant cloud SaaS deployment on Vercel and Supabase.

---

## 🧭 Architecture Pathways: Choose Your Setup Mode

Job Hunter supports two operating models that share the exact same core engine:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 JOB HUNTER SETUP MODES                                 │
├───────────────────────────────────────────┬────────────────────────────────────────────┤
│ 💻 PATH 1: Local Desktop Utility          │ ☁️ PATH 2: Full Cloud Multi-Tenant SaaS     │
│ • 100% Free ($0/mo)                       │ • 100% Free ($0/mo on free-tier stack)     │
│ • Zero database required (uses seen.json) │ • Vercel Serverless (Web Dashboard & API)  │
│ • Runs locally on your machine            │ • Supabase PostgreSQL (Auth & RLS Storage) │
│ • Daily Windows task or GitHub Actions    │ • GitHub Actions (Automated 05:00 AM Cron) │
│ • Private resume & tracking data on disk  │ • Multi-user candidate onboarding & kits   │
└───────────────────────────────────────────┴────────────────────────────────────────────┘
```

> 💡 *Both paths take about 15–20 minutes to set up from a completely fresh machine.*

---

## 📋 Table of Contents

- [Phase 1: Environment & Dependency Setup](#phase-1-environment--dependency-setup)
  - [Step 1.1: Install Python 3.9+](#step-11-install-python-39)
  - [Step 1.2: Clone the Repository](#step-12-clone-the-repository)
  - [Step 1.3: Create Virtual Environment & Install](#step-13-create-virtual-environment--install)
  - [Step 1.4: 5-Second Zero-Key Smoke Test](#step-14-5-second-zero-key-smoke-test)
- [Phase 2: Obtaining Free API Keys & Cloud Credentials](#phase-2-obtaining-free-api-keys--cloud-credentials)
  - [Step 2.1: Google Gemini Flash API Key (Primary AI Engine)](#step-21-google-gemini-flash-api-key-primary-ai-engine)
  - [Step 2.2: Gmail SMTP App Password (Daily Morning Briefings)](#step-22-gmail-smtp-app-password-daily-morning-briefings)
  - [Step 2.3: Supabase PostgreSQL & Auth Setup (For Cloud / Multi-User)](#step-23-supabase-postgresql--auth-setup-for-cloud--multi-user)
  - [Step 2.4: GitHub Personal Access Token (Cloud On-Demand Radar)](#step-24-github-personal-access-token-cloud-on-demand-radar)
- [Phase 3: Configuration & Profile Personalization](#phase-3-configuration--profile-personalization)
  - [Step 3.1: Configure Environment Variables (`.env`)](#step-31-configure-environment-variables-env)
  - [Step 3.2: Extract Candidate Profile from Resume (`jobhunt profile`)](#step-32-extract-candidate-profile-from-resume-jobhunt-profile)
  - [Step 3.3: Tune Deterministic Prefilters (`config.yaml`)](#step-33-tune-deterministic-prefilters-configyaml)
  - [Step 3.4: Configure Target Companies (`companies.yaml`)](#step-34-configure-target-companies-companiesyaml)
- [Phase 4: Running Locally (Web Dashboard & CLI Radar)](#phase-4-running-locally-web-dashboard--cli-radar)
  - [Step 4.1: Launch the Executive Web Dashboard](#step-41-launch-the-executive-web-dashboard)
  - [Step 4.2: Run the 1-Click Master Automation Pipeline](#step-42-run-the-1-click-master-automation-pipeline)
  - [Step 4.3: Tracking Applications & Follow-Ups](#step-43-tracking-applications--follow-ups)
- [Phase 5: Cloud Production Deployment (100% Free Stack)](#phase-5-cloud-production-deployment-100-free-stack)
  - [Step 5.1: Deploy Web Dashboard to Vercel](#step-51-deploy-web-dashboard-to-vercel)
  - [Step 5.2: Configure Automated Daily 05:00 AM Cron via GitHub Actions](#step-52-configure-automated-daily-0500-am-cron-via-github-actions)
  - [Step 5.3: (Alternative) Native Windows Daily Scheduled Task](#step-53-alternative-native-windows-daily-scheduled-task)
- [Phase 6: End-to-End Verification Matrix](#phase-6-end-to-end-verification-matrix)
- [Phase 7: Troubleshooting & Common Pitfalls](#phase-7-troubleshooting--common-pitfalls)

---

## Phase 1: Environment & Dependency Setup

### Step 1.1: Install Python 3.9+

Job Hunter is tested and verified across **Python 3.9, 3.10, 3.11, and 3.12**.

* **Windows**: Download the installer from [python.org/downloads](https://www.python.org/downloads/).
  > [!IMPORTANT]
  > On the very first installer screen, you **MUST check "Add python.exe to PATH"** before clicking **Install Now**.
* **macOS**: `brew install python` (Homebrew) or official installer from python.org.
* **Linux (Ubuntu/Debian)**: `sudo apt update && sudo apt install -y python3 python3-venv python3-pip git`

Verify your installation:
```bash
python --version   # Windows
python3 --version  # macOS / Linux
```

---

### Step 1.2: Clone the Repository

Clone the project to your local environment:
```bash
git clone https://github.com/tanish-jain-225/job-hunter.git
cd job-hunter
```

---

### Step 1.3: Create Virtual Environment & Install

Always use an isolated virtual environment to keep dependencies clean:

#### 💻 Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```
> [!TIP]
> If PowerShell throws a `PSSecurityException` ("running scripts is disabled on this system"), execute this command once and retry activating:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> ```

#### 🍏 macOS / 🐧 Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Your terminal prompt will now show `(.venv)`.

---

### Step 1.4: 5-Second Zero-Key Smoke Test

Prove that your environment, ATS parsers, and filter rules work before configuring any external API keys:

```bash
jobhunt run --mock --scorer keyword
```

**Expected Output**:
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
*(The generated `out/digest.html` briefing automatically opens in your default browser).*

---

## Phase 2: Obtaining Free API Keys & Cloud Credentials

All services used by Job Hunter operate within generous **$0 permanent free tiers**:

### Step 2.1: Google Gemini Flash API Key (Primary AI Engine)

Job Hunter uses **Google Gemini Flash (`gemini-3.5-flash`)** as its primary intelligence engine for candidate screening, fit scoring, application kit drafting, and PDF resume analysis.

1. Navigate to **[Google AI Studio](https://aistudio.google.com/app/apikey)**.
2. Sign in with your Google account.
3. Click **"Create API Key"** $
ightarrow$ **"Create API key in new project"**.
4. Copy the generated key (`AIzaSy...`).
5. *(Optional for scale)*: For multi-user deployments or heavy daily crawls, you can create a second key in a separate Google Cloud project and pass both as a comma-separated string: `GEMINI_API_KEY=key1,key2`. Job Hunter will automatically alternate requests between them round-robin.

---

### Step 2.2: Gmail SMTP App Password (Daily Morning Briefings)

To receive personalized HTML career digests in your email inbox every weekday morning:

1. Open your **[Google Account Security](https://myaccount.google.com/security)** page.
2. Ensure **2-Step Verification** is turned **ON**.
3. Go directly to **[Google App Passwords](https://myaccount.google.com/apppasswords)** (or search "App passwords" in the search box).
4. Enter an app name: `Job Hunter` and click **Create**.
5. Copy the generated **16-character password** (e.g. `abcd efgh ijkl mnop`).
   > [!WARNING]
   > Do not use your primary personal Gmail password. Google blocks direct SMTP access with regular account passwords.

---

### Step 2.3: Supabase PostgreSQL & Auth Setup (For Cloud / Multi-User)

> *Skip this step if you are running exclusively in local personal desktop mode (`seen.json`).*

1. Create a free account at **[supabase.com](https://supabase.com)** and click **"New Project"** (e.g. `job-hunter`).
2. Once provisioned, open the **SQL Editor** from the left sidebar.
3. Click **"New Query"**, paste the entire contents of [`supabase/schema.sql`](../supabase/schema.sql), and click **Run**.
   * *This creates the 3 multi-tenant tables (`user_profiles`, `user_tracked_jobs`, `user_pipeline_runs`), triggers, indexes, and activates Row-Level Security (RLS).*
4. Navigate to **Project Settings $
ightarrow$ API**:
   * Copy **Project URL** $
ightarrow$ `SUPABASE_URL`
   * Copy **Project API Keys $
ightarrow$ `anon` `public`** $
ightarrow$ `SUPABASE_ANON_KEY`
   * Copy **Project API Keys $
ightarrow$ `service_role` `secret`** $
ightarrow$ `SUPABASE_SERVICE_ROLE_KEY`
5. Navigate to **Authentication $
ightarrow$ URL Configuration**:
   * Set **Site URL** to your local dev URL `http://localhost:5000` (or production Vercel URL `https://your-app.vercel.app`).
   * Add the same URL under **Redirect URLs**.

---

### Step 2.4: GitHub Personal Access Token (Cloud On-Demand Radar)

To enable the **"Run Radar"** button on the web dashboard to trigger a real cloud crawl via GitHub Actions:

1. Open **[GitHub Personal Access Tokens](https://github.com/settings/tokens/new)**.
2. Note name: `Job Hunter Cloud Dispatch`.
3. Expiration: 90 days or No expiration.
4. Select scope: **`workflow`** (or `repo` for private repositories).
5. Click **Generate token** and copy it $
ightarrow$ `GH_TOKEN`.

---

## Phase 3: Configuration & Profile Personalization

### Step 3.1: Configure Environment Variables (`.env`)

In your project root, copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```ini
# ==============================================================================
# Job Hunter Configuration
# ==============================================================================

# 1. AI Intelligence Provider (Google Gemini Flash — 1M Tokens/Day per project)
# Supports comma-separated keys for instant zero-downtime rotation: key1,key2
GEMINI_API_KEY=AIzaSy_your_gemini_api_key_here

# 2. Central Outbound SMTP Server (Gmail App Password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-16-char-gmail-app-password
MAIL_TO=your-email@gmail.com

# 3. Supabase PostgreSQL (use AUTH_REQUIRED=false only for local single-user mode)
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
AUTH_REQUIRED=false

# 4. GitHub Actions Workflow Dispatch (For cloud on-demand radar from web UI)
GH_TOKEN=github_pat_your_personal_access_token_here
GITHUB_REPOSITORY=your-username/job-hunter

# 5. Session Security
FLASK_SECRET_KEY=generate-any-random-32-character-string-here
```

---

### Step 3.2: Extract Candidate Profile from Resume (`jobhunt profile`)

Place your resume (`resume.pdf`, `resume.txt`, or `resume.md`) in the project root:

```bash
jobhunt profile --resume resume.pdf
```

The AI engine automatically analyzes your work history, technologies, education, and target titles, generating [`profile.json`](../profile.example.json). Open `profile.json` in your editor to inspect or fine-tune your target roles. In the authenticated web application, each user's profile is loaded from Supabase and never falls back to another user's local profile.

---

### Step 3.3: Tune Deterministic Prefilters (`config.yaml`)

[`config.yaml`](../config.yaml) controls the free pre-filter gate that drops irrelevant roles before LLM scoring:

```yaml
filters:
  # Target job titles (leave empty to accept ALL engineering/tech titles)
  include_titles:
    - 'software engineer'
    - 'backend'
    - 'full.?stack'
    - 'ai engineer'

  # Excluded noise (C-suite, non-tech, HR)
  exclude_titles:
    - '\b(ceo|coo|cfo|cto|ciso|vp|svp|evp|c-suite)\b'
    - '\b(sales|marketing|recruiter|talent.*acquisition)\b'

  # Locations (leave empty to accept ALL worldwide + India + Remote)
  locations: []
  allow_remote: true
  max_age_days: 21

# Scoring thresholds & batching
screen_batch_size: 8      # 8 jobs per LLM request (optimal for Gemini Flash)
score_threshold: 7.0      # Minimum fit score (0.0 to 10.0) required to draft kit
max_per_digest: 7         # Max top application kits per daily briefing
```

---

### Step 3.4: Configure Target Companies (`companies.yaml`)

[`companies.yaml`](../companies.yaml) holds your target company career boards across 9 ATS engines:

```yaml
companies:
  - {ats: greenhouse, slug: stripe, name: Stripe}
  - {ats: ashby, slug: openai, name: OpenAI}
  - {ats: lever, slug: meesho, name: Meesho}
  - {ats: workable, slug: vector, name: Vector}
  - {ats: smartrecruiters, slug: visa, name: Visa}
  - {ats: bamboohr, slug: acme, name: Acme}
  - {ats: recruitee, slug: bunq, name: Bunq}
  - {ats: breezy, slug: acme, name: Acme}
  - {ats: pinpoint, slug: company, name: Pinpoint Co}
```

> [!TIP]
> You can also add custom company boards directly from the web dashboard using the **"+ Add Board"** button—it auto-detects the ATS platform from any career URL!

---

## Phase 4: Running Locally (Web Dashboard & CLI Radar)

### Step 4.1: Launch the Executive Web Dashboard

Start the Flask server locally:

```bash
python app.py
```
Open **`http://localhost:5000`** in your browser.

**Features Available in the Web Dashboard**:
* **Interactive Job Board**: Table/Card list with responsive client-side pagination (10, 25, or 50 opportunities per page) and in-card 5-stage dropdown selectors.
* **Resume Studio**: Drag-and-drop PDF resume parser with AI skill extraction and 11 one-click role presets.
* **Application Kit Inspector**: Tailored cover notes, 80-word cold outreach messages, and matching resume bullets with 1-click clipboard copy.
* **Smart Follow-Up Nudges**: Automated elapsed-time badges (`⏳ 5d ago · Follow Up`) on applied roles.
* **Live SSE Radar Console**: Live streaming crawl execution logs.

---

### Step 4.2: Run the 1-Click Master Automation Pipeline

To run an end-to-end live radar pass (scouting ATS boards $
ightarrow$ filtering $
ightarrow$ screening $
ightarrow$ drafting $
ightarrow$ exporting CSV $
ightarrow$ opening browser preview):

```bash
python auto.py
```

To send an email briefing via SMTP as well:
```bash
python auto.py --send
```

---

### Step 4.3: Tracking Applications & Follow-Ups

When you submit an application, update its stage either:
1. **Directly on the Web Board**: Select **"Applied"** from the 5-stage dropdown on the job card.
2. **Via Command Line**:
   ```bash
   jobhunt applied "greenhouse:stripe:4089201"
   ```

Export your complete tracking history to CSV at any time:
```bash
jobhunt stats
# Generates out/tracker.csv (compatible with Excel and Google Sheets)
```

---

## Phase 5: Cloud Production Deployment (100% Free Stack)

Deploy Job Hunter to the cloud so it runs 24/7 without needing your laptop powered on:

### Step 5.1: Deploy Web Dashboard to Vercel

1. Push your repository to GitHub.
2. Visit **[vercel.com](https://vercel.com)** $
ightarrow$ **Add New $
ightarrow$ Project** $
ightarrow$ Import your `job-hunter` repository.
3. In **Settings $
ightarrow$ Environment Variables**, configure:
   * `GEMINI_API_KEY`: Your Gemini API key
   * `SUPABASE_URL`: `https://your-project.supabase.co`
   * `SUPABASE_ANON_KEY`: Your Supabase anon public key
   * `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase service role secret key
   * `AUTH_REQUIRED`: `true`
   * `FLASK_SECRET_KEY`: Random 32-char string
   * `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` (Optional, for test emails)
   * `GH_TOKEN`, `GITHUB_REPOSITORY` (Optional, for cloud on-demand radar triggers)
4. Click **Deploy**. Vercel will build and serve your app at `https://your-project.vercel.app`!

---

### Step 5.2: Configure Automated Daily 05:00 AM Cron via GitHub Actions

Job Hunter includes a scheduled cloud cron job in [`.github/workflows/daily.yml`](../.github/workflows/daily.yml) that crawls ATS boards, screens matches, and dispatches briefings every weekday morning:

1. Open your GitHub repository $
ightarrow$ **Settings $
ightarrow$ Secrets and variables $
ightarrow$ Actions**.
2. Add the following **Repository Secrets**:
   * `GEMINI_API_KEY`
   * `SMTP_USER` & `SMTP_PASS`
   * `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
   * `MAIL_TO` (For single-user mode)
   * `PROFILE_JSON` (Contents of your `profile.json` for single-user mode)
3. Navigate to the **Actions** tab in your repository:
   * Select **Daily Career Intelligence Digest** $
ightarrow$ Click **"Run workflow"** to test it immediately.
   * By default, it will execute automatically every morning at **05:00 AM IST (23:30 UTC)**.

---

### Step 5.3: (Alternative) Native Windows Daily Scheduled Task

If you prefer to run automated morning crawls locally on your Windows PC instead of GitHub Actions:

1. Open PowerShell or Command Prompt as **Administrator**.
2. Run:
   ```cmd
  scripts\\setup_daily_task.bat
   ```
3. Windows Task Scheduler registers `JobHunterDailyDigest` to execute the root `auto.py --send` every morning at 05:00 AM in the background.

---

## Phase 6: End-to-End Verification Matrix

Run these diagnostic commands to verify each subsystem of the product:

| Verification Gate | Command | Expected Result | Status |
|---|---|---|:---:|
| **1. Offline Smoke Test** | `jobhunt run --mock --scorer keyword` | Scans 12 mock jobs, writes `out/digest.html` | ✅ Verified |
| **2. Live ATS Board Auditor** | `jobhunt verify --workers 10` | Verifies live HTTP connectivity across `companies.yaml` | ✅ Verified |
| **3. Live Gemini Screening** | `jobhunt run --strict-llm` | Screens top live postings with Google Gemini 3.5 Flash | ✅ Verified |
| **4. Web Server & API** | `python app.py` (visit `/api/health`) | Returns `{"status": "healthy", "service": "job-hunter"}` | ✅ Verified |
| **5. Full Automated Test Suite**| `pytest -q` | **401 passed tests** with 100% success rate | ✅ Verified |
| **6. Static Type Checker** | `mypy jobhunt` | Zero type errors across 23 source files | ✅ Verified |
| **7. Code Style & Linter** | `ruff check .` | All checks passed (0 errors) | ✅ Verified |

---

## Phase 7: Troubleshooting & Common Pitfalls

### Issue 1: `python` or `pip` is not recognized on Windows
* **Fix**: Re-run the Python Windows installer, select **Modify**, and tick **"Add python.exe to PATH"**.

### Issue 2: PowerShell script execution disabled
* **Fix**: Run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in the current terminal window.

### Issue 3: Gmail SMTP Authentication Error (`535 5.7.8`)
* **Fix**: Ensure 2-Step Verification is active on your Google account and generate a 16-character **App Password** from [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

### Issue 4: Gemini Rate Limits (`HTTP 429: Resource Exhausted`)
* **Fix**: Pass multiple free Gemini keys separated by commas in `GEMINI_API_KEY=key1,key2`. Job Hunter automatically alternates between keys round-robin. In addition, Job Hunter's dynamic fallback cascading automatically routes requests through `gemini-flash-latest` $
ightarrow$ `gemini-flash-lite-latest` with cooldown tracking.

### Issue 5: Supabase RLS Permission Denied on API routes
* **Fix**: Ensure you ran [`supabase/schema.sql`](../supabase/schema.sql) in your Supabase SQL Editor to grant table and sequence permissions to `authenticated` and `service_role`.

---

## 📚 Related Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Comprehensive architecture diagrams, design patterns, and state machine.
- **[DASHBOARD.md](DASHBOARD.md)** — Web dashboard features and REST API reference.
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — Production cloud deployment guide.
- **[ENGINE.md](ENGINE.md)** — LLM scoring, batching, and resilience mechanics.
- **[MULTI_USER.md](MULTI_USER.md)** — Multi-tenant single-pass architecture.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — In-depth diagnostic guide and FAQs.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Development guidelines and PR workflows.
- **[README.md](../README.md)** — Main repository homepage.
