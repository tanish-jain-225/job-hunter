# 🖥️ Web Dashboard & REST API Reference Guide

**Job Hunter** includes a built-in, local, interactive Flask-based web dashboard engineered with an **Application Factory Pattern** (`jobhunt.web.create_app`) and **Modular Blueprints**. It provides a visual interface to browse discovered job postings, manage a visual Kanban pipeline, extract candidate profiles with Resume Studio, launch tailored cover letters/resumes, and trigger job searches on demand.

---

## 🏃 How to Start the Dashboard

To launch the web server locally, activate your virtual environment and run:

```bash
# Standard entry point
python app.py

# Or via the global CLI
jobhunt web
```

By default, the server starts on **`http://localhost:5000`**.

### Configuration Parameters
You can configure the host and port using command-line arguments or environment variables:
* **Command Line:**
  ```bash
  python app.py --port 8080 --host 0.0.0.0
  ```
* **Environment Variables:**
  ```env
  PORT=8080
  HOST=0.0.0.0
  ```

---

## 🎨 User Interface Features

The dashboard is designed as a single-page application with a premium Light Mode theme, supporting the following features:

### 1. 📋 Dual-Mode View Switcher (Table & Visual Kanban Pipeline)
* **Table / List View**: High-density interactive table showing job match scores, ATS tags, company, location, applied toggle, and application kit inspector.
* **Visual Kanban Pipeline**: Organize opportunities across 5 interactive pipeline stages:
  * **To Apply** (`to_apply`)
  * **Applied** (`applied`)
  * **Interviewing** (`interviewing`)
  * **Offer** (`offer`)
  * **Rejected / Archived** (`rejected`)
* Instant 1-click stage dropdown selectors and seamless view switching with persistent preference stored in `localStorage`.

### 2. 📄 Resume Studio & AI Profile Extraction
* In-dashboard PDF and text resume uploader.
* Automatically parses uploaded resumes via **Google Gemini (`gemini-3.6-flash`)** / Claude document analysis into structured candidate skills, target titles, seniority, and notable projects.
* **11 One-Click Role Presets** (Full Stack, Backend, Frontend, AI/ML, DevOps, Data Eng, Mobile, QA, Security, Web3, Product) for instant zero-friction onboarding.

### 3. ⚡ Zero-Refresh Real-Time State Sync
* Changes made in any tab (stage updates, notes, manual additions, applied toggles) automatically sync across all open browser windows and devices via `/api/sync` heartbeat version hashing.
* Deterministic version tokens dynamically hash job stages, private notes, fit scores, and timestamps.
* A **Live Synced** status pill in the top header provides visual pulse indicators and one-click manual synchronization.

### 4. 📊 Executive Metrics Panel
* Real-time metric pills summarize your tracking status: **Tracked** (total database size), **Emailed** (matches dispatched), and **Applied** (jobs marked as submitted).
* Filter pills provide one-click status switching between *All Jobs*, *Shortlisted (7.0+)*, *Applied*, and *Unapplied* with live counts.

### 5. 🔍 Search, Sort, and Status Filters
* **Interactive Search Bar:** Query by company name, job title, locations, or specific technologies. Press `/` anywhere on the page to focus the search bar, with instant clearing via `Esc`.
* **Crawl Source Filter:** Filter by ATS platform (*Greenhouse*, *Lever*, *Ashby*, *Workable*, *SmartRecruiters*, *BambooHR*, *Recruitee*, *Breezy HR*, *Pinpoint*, or *Custom*).
* **Sorting Options:** Sort jobs by *Date*, *Match Score*, or *Company*.

### 6. 📄 Briefing Digest Reader & Kit Inspector
* View the compiled daily responsive HTML digest directly inside the dashboard preview frame, with quick links to open in a new tab or force a live rebuild.
* Click **"View Kit"** on any job card in the Interactive Job Board to open the **Application Kit Modal**, featuring 1-click copy buttons for tailored cold outreach messages and custom cover notes.

### 7. 🤖 Live Pipeline Trigger
* An **"On-Demand Pipeline Trigger"** button in the sidebar triggers a live crawl across all configured ATS job boards directly from the web UI. Real-time console logs display progress and stats.

### 8. 🔒 Supabase Authentication & Session Protection
* Enterprise-grade authentication via **Supabase Auth** protects confidential career intelligence, target match scores, application drafts, and pipeline trigger controls.
* When `AUTH_REQUIRED=true`, all private REST API endpoints enforce `Authorization: Bearer <token>` token validation with high-throughput in-memory TTL caching.

### 9. ➕ Manual Opportunity Tracking ("+ Add Opportunity")
* Click **"+ Add Opportunity"** directly on the Tracker toolbar to track external roles found via LinkedIn, company career portals, or personal referrals.
* Automatically scores fit and drafts an Application Kit on demand using your candidate profile.

---

## 📡 REST API Reference

The dashboard web server exposes a clean, authenticated REST API. When authentication is enabled, requests include the Bearer token header (case-insensitive):
```http
Authorization: Bearer <supabase_access_token>
```

### 0. Health & Service Monitoring
* **Endpoint:** `GET /api/health`
* **Response:**
  ```json
  {
    "status": "healthy",
    "service": "job-hunter",
    "version": "1.0.0",
    "environment": "local",
    "auth_required": false,
    "memory_connected": true,
    "timestamp": 1771587600.0,
    "utc_time": "2026-08-20 12:45:00Z"
  }
  ```

### 1. Authentication Configuration & Status
* **`GET /api/auth/config`**: Public endpoint returning `{ auth_required, supabase_url, supabase_anon_key }` for client initialization.
* **`GET /api/auth/user`**: Protected endpoint returning authenticated user profile details from session context.

### 2. Retrieve Tracked Jobs
Returns a JSON list of all processed jobs matching search, status, ATS board, and sorting queries.
* **Endpoint:** `GET /api/jobs`
* **Query Parameters:**
  * `search` (string): Text query to search titles, companies, or locations.
  * `status` (string): Filter by status (`all`, `shortlisted`, `applied`, `unapplied`).
  * `ats` (string): Filter by ATS board (`all`, `greenhouse`, `lever`, `ashby`, `workable`, `smartrecruiters`, `bamboohr`, `recruitee`, `breezy`, `pinpoint`, `custom`).
  * `min_score` (float): Minimum score threshold (e.g. `7.0`).
  * `sort` (string): Sort jobs by `date`, `score`, or `company`.

### 3. Update Kanban Pipeline Stage
Updates the application stage of a tracked role.
* **Endpoint:** `POST /api/jobs/stage`
* **Request Payload:**
  ```json
  {
    "job_id": "greenhouse:stripe:4089201",
    "stage": "interviewing"
  }
  ```

### 4. Save Candidate Job Notes
Updates private candidate notes for a specific tracked job.
* **Endpoint:** `POST /api/jobs/notes`
* **Request Payload:**
  ```json
  {
    "job_id": "greenhouse:stripe:4089201",
    "notes": "Recruiter screen scheduled for Friday 3 PM."
  }
  ```

### 5. Candidate Profile & Notification Preferences
Get or update candidate search profile, target skills, and email notification toggles.
* **Endpoint:** `GET /api/profile` | `POST /api/profile`
* **Request Payload (POST):**
  ```json
  {
    "name": "Sarah Connor",
    "title": "Senior Systems Engineer",
    "skills": ["Go", "Python", "Kubernetes", "PostgreSQL"],
    "target_keywords": ["Backend Engineer", "Infrastructure Engineer"],
    "exclude_keywords": ["Manager", "Director", "Sales"],
    "email_notifications_enabled": true,
    "notification_email": "sarah@cyberdyne.org",
    "min_score_notification": 7.5
  }
  ```

### 6. Resume Studio (PDF / TXT Parsing)
Upload and extract structured profile JSON from a resume document.
* **Endpoint:** `POST /api/resume/upload`
* **Payload:** Multipart `file` (`.pdf` or `.txt`) OR raw JSON payload `{ "resume_text": "..." }`.

### 7. Trigger Live Pipeline Execution
Executes the scraping, filtering, and scoring pipeline on demand.
* **Endpoint:** `POST /api/run`
* **Request Payload (Optional):**
  ```json
  {
    "mock": false,
    "scorer": "llm"
  }
  ```

### 8. High-Speed Synchronization Heartbeat
Returns live store version hash, stats breakdown, active pipeline state, and candidate profile.
* **Endpoint:** `GET /api/sync`

### 9. Pipeline Audit History
Returns recent pipeline execution runs and logs for the authenticated user.
* **Endpoint:** `GET /api/history`

### 10. Serve Briefing Digest
Returns the compiled HTML email briefing file (`out/digest.html`) or generates it dynamically.
* **Endpoint:** `GET /api/digest`

### 11. Send Live SMTP Test Briefing
Dispatches a live test career briefing email to verify SMTP credentials.
* **Endpoint:** `POST /api/email/test`

### 12. Export Job Tracking CSV
Serves raw job tracking data as a direct CSV download (`tracker.csv`).
* **Endpoint:** `GET /api/export/csv`

### 13. Mark / Unmark Job as Applied
Updates the status of a job ID to `"applied"` or unmarks it in the state store.
* **Endpoint:** `POST /api/applied`

### 14. Add Custom Job
Manually add an external job opening into the tracking store with optional on-demand AI scoring.
* **Endpoint:** `POST /api/add` or `POST /api/jobs/add`

### 15. Delete Job Entry
Removes a job entry completely from the tracking store.
* **Endpoint:** `POST /api/delete` or `DELETE /api/delete`

### 16. Fetch Dashboard Metrics & Config
* **`GET /api/stats`**: Returns total tracked, emailed, and applied metric counts.
* **`GET /api/config`**: Returns active filter rules, thresholds, and ATS company board counts.

---

## 📚 Related Documentation

- **[SETUP.md](SETUP.md)** — Beginner installation and local quickstart guide.
- **[GUIDE.md](GUIDE.md)** — Personal utility & cloud automation workflows.
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — Free-tier cloud production deployment guide.
- **[ENGINE.md](ENGINE.md)** — Scoring and matching engine specifications.
- **[MULTI_USER.md](MULTI_USER.md)** — Multi-user scaling architecture.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Setup troubleshooting and FAQs.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Developer instructions and test suite.
- **[README.md](../README.md)** — Project homepage.

