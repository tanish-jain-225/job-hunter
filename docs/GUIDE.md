# 📖 Job Hunter — Personal Utility Setup & Usage Guide

**Job Hunter** is a 100% database-free, zero-cost, private personal utility designed to help individual job seekers discover, score, track, and apply for high-match engineering and tech roles across 9 major ATS platforms (**Greenhouse**, **Lever**, **Ashby**, **Workable**, **SmartRecruiters**, **BambooHR**, **Recruitee**, **Breezy HR**, **Pinpoint**).

---

> 💡 *For step-by-step beginner setup, see [SETUP.md](SETUP.md).*  
> 💡 *For the web dashboard and REST API endpoints, see [DASHBOARD.md](DASHBOARD.md).*  
> 💡 *For details on the job-matching LLM scoring system, see [ENGINE.md](ENGINE.md).*  
> 💡 *To run Job Hunter for multiple people, see [MULTI_USER.md](MULTI_USER.md).*  
> 💡 *For SMTP or action-running issues, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).*  
> 💡 *For developer guidelines & testing, see [CONTRIBUTING.md](CONTRIBUTING.md).*  
> 💡 *For architectural design specifications, see [JOB_HUNT.md](JOB_HUNT.md).*

---

## 🚀 Core Philosophy & Features

- **🔒 100% Data Privacy**: Your resume, job applications, scores, and notes remain completely local on your machine or inside your private repository.
- **💰 100% Free ($0/month)**: Operates using free-tier LLM providers (Google Gemini 3.5 Flash / Groq) and free email dispatches.
- **⚡ Zero-Database Architecture**: No mandatory SQL servers, Docker containers, or complex database migrations. Everything is persisted in clean JSON (`seen.json`) and CSV (`out/tracker.csv`), with optional Supabase PostgreSQL sync.
- **📊 Automatic Excel/Sheets Sync**: All tracked and applied jobs auto-export to `out/tracker.csv` on every action.
- **🤖 Automated Daily Email Digest**: Delivers personalized HTML career digests straight to your email inbox every morning.

---

## 📋 Prerequisites

Before setting up, ensure you have:
1. **Python 3.9+** (3.9, 3.10, 3.11, or 3.12) installed.
2. **Google Gemini API Key** (Free from [Google AI Studio](https://aistudio.google.com/)) or Anthropic / Groq keys.
3. *(Optional for email digests)* **Gmail App Password** (Generated via [Google Account Security](https://myaccount.google.com/apppasswords)).

---

## ⚡ Quickstart in 3 Steps

### Step 1: Clone & Install Dependencies
```bash
git clone https://github.com/tanish-jain-225/job-hunter.git
cd job-hunter
pip install -e .
```

### Step 2: Configure Personal Credentials & Profile

1. **Environment Configuration (`.env`)**:
   Create a `.env` file in the project root with your credentials:
   ```env
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=your_gemini_api_key_here
   SCREEN_MODEL=gemini-3.5-flash
   DRAFT_MODEL=gemini-3.5-flash

   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your_email@gmail.com
   SMTP_PASS=your_16_char_gmail_app_password

   SUPABASE_URL=https://your-project-ref.supabase.co
   SUPABASE_ANON_KEY=your_supabase_anon_key
   SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
   AUTH_REQUIRED=true
   ```

2. **Generate Profile from Resume**:
   Place your `resume.pdf` in the project root and run:
   ```bash
   jobhunt profile --resume resume.pdf
   ```
   *This automatically extracts your skills, experience, and target summary into `profile.json`.*

3. **Customize Preferences (`config.yaml`)**:
   Tune your target job titles, target locations (or remote), and score threshold in `config.yaml`:
   ```yaml
   filters:
     include_titles:
       - 'software engineer'
       - 'backend engineer'
       - 'full stack engineer'
     locations:
       - india
       - bengaluru
       - mumbai
     allow_remote: true
     max_age_days: 28

   score_threshold: 7.0
   ```

---

## 🏃 3 Flexible Running Modes

### Mode 1: 1-Click Local Execution & Interactive Dashboard

- **Run Full Pipeline** (Scan ATS boards, score candidates, build digest & send email):
  ```bash
  python auto.py
  ```
- **Launch Web Dashboard**:
  ```bash
  python app.py
  ```
  Open `http://localhost:5000` to view your Executive Light Glassmorphism dashboard, search tracked jobs, mark applied roles, and inspect application kits.

---

### Mode 2: Native Windows Daily Automated Task
To receive your email digest every morning at 9:00 AM automatically on your computer:
1. Open PowerShell or Command Prompt as **Administrator**.
2. Run `setup_daily_task.bat` (or double-click `setup_daily_task.bat`).
3. Windows Task Scheduler (`JobHunterDailyDigest`) will handle execution every morning in the background.

---

### Mode 3: 100% Free Cloud Automation via GitHub Actions (No Computer Turned On Required)
You can run Job Hunter completely in the cloud without leaving your computer on:

1. Push your repository to **GitHub** (keep it **Private** for data security).
2. Navigate to **Settings $\rightarrow$ Secrets and variables $\rightarrow$ Actions** in your GitHub repository.
3. Add the following repository secrets:
   - `GEMINI_API_KEY`: Your Gemini API Key
   - `SMTP_USER`: Your Gmail address
   - `SMTP_PASS`: Your Gmail 16-character App Password
   - `PROFILE_JSON`: Copy & paste the exact JSON content of your `profile.json`
4. **Done!** The included `.github/workflows/daily.yml` workflow will automatically run every weekday morning, scan ATS boards, email your daily briefing digest, and save your `seen.json` deduplication store using GitHub Actions Cache.

---

## 🛠️ Commands Reference

| Command | Description |
| :--- | :--- |
| `python auto.py` | Run complete end-to-end pipeline (fetch $\rightarrow$ prefilter $\rightarrow$ screen $\rightarrow$ draft $\rightarrow$ email). |
| `python app.py` | Start Flask Web Dashboard on `http://localhost:5000` (Vercel Serverless ready). |
| `jobhunt run` | Run job search CLI command (`--mock`, `--send`, `--scorer {llm,keyword}`). |
| `jobhunt profile` | Extract candidate profile from resume (`.pdf`, `.txt`, `.md`) to `profile.json`. |
| `jobhunt stats` | Output current tracking and application metrics in terminal. |
| `jobhunt applied <job_id>` | Mark job ID as applied via CLI. |
| `pytest` | Run the full test suite (191 unit and integration tests, 98%+ test coverage). |

---

## 💡 Frequently Asked Questions (FAQ)

#### Q: Where is my job tracking data stored?
All tracked jobs, match scores, and application statuses are stored in `seen.json` in the project root and auto-exported to `out/tracker.csv`.

#### Q: How do I backup my job application tracker?
Simply commit `seen.json` or copy `out/tracker.csv` to Google Drive or OneDrive.

#### Q: What happens if Gemini API rate limits occur?
Job Hunter includes automatic fallback logic — if LLM screening fails or hits quotas, it seamlessly falls back to an offline keyword matching engine without crashing.
