# 🖥️ Web Dashboard & API Reference Guide

**Job Hunter** includes a built-in, local, interactive Flask-based web dashboard. It provides a visual interface to browse discovered job postings, track your application progress, launch tailored cover letters/resumes, and trigger job searches on demand.

---

## 🏃 How to Start the Dashboard

To launch the web server locally, activate your virtual environment and run:

```bash
python app.py
```

By default, the server starts on **`http://localhost:5000`**.

### Configuration Parameters
You can configure the host and port using environment variables or command-line arguments:
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

The dashboard is designed as a single-page application with a premium theme, supporting the following features:

### 1. 🌓 Light/Dark Mode
A toggle in the top navigation bar allows you to switch between a clean light workspace and a sleek midnight dark mode. Your preference is persisted in the browser's local storage.

### 2. 📊 Executive Metrics Panel
Four real-time metric cards summarize your job search metrics:
* **Discovered:** Total number of postings processed and matching the include/exclude filters.
* **Matches:** Number of jobs that scored above your configuration threshold (e.g., $\ge 7.0/10$).
* **Applied:** Number of roles you have officially marked as applied.
* **Success Rate:** Percentage of matched jobs that you successfully applied to.

### 3. 🔍 Search, Sort, and Status Filters
A control center lets you drill down into job listings:
* **Interactive Search Bar:** Query by company name, job title, locations, or specific technologies.
* **Status Filter:** Toggle between displaying *All Jobs*, *New Matches*, or *Applied Jobs*.
* **Crawl Source Filter:** Filter by ATS platform (*Greenhouse*, *Lever*, or *Ashby*).
* **Sorting Options:** Sort jobs by *Match Score (High to Low)*, *Date Found*, or *Salary/Compensation*.

### 4. 📄 Briefing Digest Reader
You can view the compiled daily responsive HTML digest directly inside the dashboard by clicking the **"View Latest Digest"** button, saving you from opening your email client.

### 5. 🤖 Live Pipeline Trigger
A **"Run Search Pipeline"** button in the header triggers a live crawl of all target job boards directly from the web UI. A modal showing execution logs displays progress in real time.

---

## 📡 REST API Reference

The dashboard web server exposes a clean REST API. You can use these endpoints to integrate Job Hunter with external tools or dashboards (like Notion, Slack, or custom scripts).

### 1. Retrieve Tracked Jobs
Returns a JSON list of all processed jobs matching search, source, and status queries.
* **Endpoint:** `GET /api/jobs`
* **Query Parameters:**
  * `query` (string): Text query to search titles/companies.
  * `status` (string): Filter by status (`all`, `matched`, `applied`).
  * `source` (string): Filter by ATS board (`all`, `greenhouse`, `lever`, `ashby`).
* **Response Output:**
  ```json
  [
    {
      "id": "greenhouse:stripe:4089201",
      "company": "Stripe",
      "title": "Software Engineer Intern - Backend",
      "location": "Bengaluru, India",
      "url": "https://boards.greenhouse.io/stripe/jobs/4089201",
      "score": 8.5,
      "reason": "Strong match with Python/REST API experience...",
      "status": "matched",
      "date_added": "2026-08-15"
    }
  ]
  ```

### 2. Mark Job as Applied
Updates the status of a job ID to `"applied"` in the state store and updates the tracker CSV file.
* **Endpoint:** `POST /api/applied`
* **Request Payload:**
  ```json
  {
    "job_id": "greenhouse:stripe:4089201"
  }
  ```
* **Response Output:**
  ```json
  {
    "success": true,
    "job_id": "greenhouse:stripe:4089201",
    "status": "applied"
  }
  ```

### 3. Trigger Live Crawl
Executes the scraping and scoring pipeline in a separate background thread.
* **Endpoint:** `POST /api/run`
* **Request Payload (Optional):**
  ```json
  {
    "mock": false,
    "scorer": "llm"
  }
  ```
* **Response Output:**
  ```json
  {
    "success": true,
    "message": "Pipeline started in background"
  }
  ```

### 4. Fetch Latest Digest
Returns the raw compiled HTML email briefing file (`out/digest.html`).
* **Endpoint:** `GET /api/digest`
* **Response Output:** Raw responsive HTML content.

### 5. Fetch Dashboard Metrics
Returns total and filtered metric counts.
* **Endpoint:** `GET /api/stats`
* **Response Output:**
  ```json
  {
    "total_tracked": 142,
    "total_matched": 18,
    "total_applied": 4,
    "success_rate_percent": 22.2
  }
  ```
