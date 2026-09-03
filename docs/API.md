# Job Hunter — REST API Reference

All endpoints require authentication via `Authorization: Bearer <token>` header
or `sb_access_token` HttpOnly cookie.

---

## Pipeline

### GET /api/sync
Returns current pipeline state, live job stats, and user profile summary for real-time zero-refresh synchronization.

**Auth:** Required  
**Response:**
```json
{
  "status": "success",
  "version": "a1b2c3d4e5f60718",
  "stats": {"tracked": 120, "applied": 5, "shortlisted": 18, "emailed": 12, "unapplied": 115},
  "ats_counts": {"greenhouse": 40, "lever": 22, "ashby": 30, "smartrecruiters": 15, "workable": 8, "bamboohr": 5},
  "pipeline": {"running": false, "step": "completed", "message": "Pipeline completed successfully!"},
  "user_email": "user@example.com",
  "user_profile": {...},
  "memory_connected": true,
  "timestamp": 1724645093.4
}
```

### GET /api/pipeline/stream
Stream real-time log execution events from active background crawls to the connected browser client using Server-Sent Events (SSE).

**Auth:** Required  
**Content-Type:** `text/event-stream`  
**Payload Shape:**
```json
data: {"type": "log", "log": "Step 1/5: Scanning Ashby boards...", "step": "running", "running": true}
data: {"type": "done", "pipeline": {"running": false, "step": "completed", "message": "Pipeline completed successfully!"}}
```

### POST /api/run
Triggers the full job intelligence radar pipeline for the authenticated user.

**Auth:** Required  
**Rate limit:** 5 per hour per IP  
**Body (JSON):**
```json
{"mock": false, "send": false, "scorer": "llm"}
```
**Response:** `{"status": "success", "message": "Pipeline dispatched", "mode": "cloud"}`

### GET /api/digest
Returns the latest digest as an HTML document.

**Auth:** Required  
**Query params:** `?force` or `?live` to force a live rebuild  
**Response:** `text/html`

### POST /api/email/test
Dispatches a live test career briefing email to verify SMTP delivery credentials.

**Auth:** Required  
**Response:** `{"status": "success", "message": "Test briefing successfully sent to user@example.com!", "target_email": "user@example.com"}`

---

## Jobs

### GET /api/jobs
Returns all tracked jobs with filtering and sorting.

**Auth:** Required  
**Query params:**
| Param | Values | Default |
|-------|--------|---------|
| `status` | `all` / `shortlisted` / `applied` / `unapplied` | `all` |
| `ats` | `greenhouse` / `lever` / `ashby` / `workable` / `smartrecruiters` / `bamboohr` / `recruitee` / `breezy` / `pinpoint` / `all` | `all` |
| `search` | free text | — |
| `min_score` | float | — |
| `sort` | `date` / `score` / `company` | `date` |

**Response:** `{"status": "success", "count": 18, "jobs": [...]}`

### POST /api/jobs/stage
Update the Kanban application stage for a job.

**Auth:** Required  
**Body:** `{"job_id": "greenhouse:stripe:4089201", "stage": "interviewing"}`  
**Stages:** `to_apply` | `applied` | `interviewing` | `offer` | `rejected`  
**Response:** `{"status": "success", "message": "...", "job_id": "...", "stage": "interviewing", "version": "a1b2c3d4e5f60718", "stats": {...}}`

### POST /api/jobs/notes
Update private candidate notes for a tracked job.

**Auth:** Required  
**Body:** `{"job_id": "lever:company:abc", "notes": "Great culture fit, ask about remote"}`  
**Response:** `{"status": "success", "message": "Notes saved.", "job_id": "...", "notes": "...", "version": "a1b2c3d4e5f60718", "stats": {...}}`

### POST /api/applied
Mark or unmark a job as applied.

**Auth:** Required  
**Body:** `{"job_id": "...", "action": "mark"}` — action: `mark` | `unmark`  
**Response:** `{"status": "success", "applied": true, "version": "a1b2c3d4e5f60718", "stats": {...}}`

### POST /api/jobs/add (alias: POST /api/add)
Manually add a custom job entry with optional AI scoring.

**Auth:** Required  
**Body:**
```json
{
  "title": "Software Engineer",
  "company": "Acme Corp",
  "location": "Bangalore, India",
  "url": "https://acme.com/jobs/123",
  "description": "Full JD text...",
  "run_ai": true
}
```

### POST /api/delete
Delete a job from the tracking store.

**Auth:** Required  
**Body:** `{"job_id": "..."}`  
**Response:** `{"status": "success", "job_id": "...", "version": "a1b2c3d4e5f60718", "stats": {...}}`

### GET /api/export/csv
Download tracked jobs as a CSV file attachment.

**Auth:** Required  
**Response:** `text/csv` attachment

### GET /api/stats
Returns a summary of job tracking stats.

**Auth:** Required  
**Response:** `{"tracked": 120, "applied": 5, "shortlisted": 18, "emailed": 12, "unapplied": 115, "version": "a1b2c3d4e5f60718"}`

### GET /api/config
Returns active configuration summary (company count, filters, score threshold).

**Auth:** Required

### GET /api/companies
Returns the parsed default company list with filtering by name or ATS type.

**Auth:** Required  
**Query params:** `?search=stripe&ats=greenhouse`

### GET /api/companies/custom
Returns the list of custom added target company boards configured by the candidate.

**Auth:** Required  
**Response:** `{"status": "success", "count": 2, "companies": [{"ats": "lever", "slug": "meesho", "name": "Meesho"}]}`

### POST /api/companies/add
Auto-detects ATS platform from an arbitrary career URL, validates live HTTP accessibility, and registers the company board under the candidate's profile.

**Auth:** Required  
**Body:** `{"url": "https://jobs.lever.co/meesho", "name": "Meesho"}` or `{"ats": "lever", "slug": "meesho"}`  
**Response:** `{"status": "success", "message": "Successfully registered and verified Meesho (lever)!", "company": {...}}`

### DELETE /api/companies/custom
Removes a custom ATS target board from the candidate's radar.

**Auth:** Required  
**Body:** `{"ats": "lever", "slug": "meesho"}`  
**Response:** `{"status": "success", "message": "Removed lever:meesho from custom companies"}`

### POST /api/jobs/followup
Generates a tailored follow-up outreach note (email and LinkedIn DM) for an applied job posting based on candidate profile and elapsed application days.

**Auth:** Required  
**Body:** `{"title": "Senior Engineer", "company": "Stripe", "applied_on": "2026-08-25", "stage": "applied"}`  
**Response:** `{"status": "success", "followup": {"subject": "...", "email_body": "...", "linkedin_dm": "..."}}`

---

## Profile

### GET /api/profile
Returns the authenticated user's candidate profile.

**Auth:** Required

### POST /api/profile
Update candidate profile and search preferences.

**Auth:** Required  
**Body:** Partial or full profile JSON (merged with existing profile in Supabase)

### POST /api/profile/reset
Flush out the candidate profile, resume text, and notification preferences.

**Auth:** Required

### POST /api/resume/upload
Upload and extract structured candidate profile data from a resume document (PDF or plain text).

**Auth:** Required  
**Content-Type:** `multipart/form-data` (file field: `file`) OR `application/json` (`{"resume_text": "...", "filename": "resume.pdf"}`)  
**Timeout & Resilience:** 30.0s backend execution ceiling with automatic fallback to high-speed smart local regex parser during upstream AI provider load spikes (e.g. HTTP 503).  
**Response:**
```json
{
  "status": "success",
  "message": "Resume text successfully extracted. You can review and alter your text context before saving.",
  "resume_text": "...",
  "profile": {
    "name": "Tanish Sanghvi",
    "title": "Full-Stack Developer",
    "education": "B.E. in Automation & Robotics Engineering",
    "experience_years": 0.0,
    "skills": ["JavaScript", "Python", "React.js", "Node.js", "Express.js", "Next.js", "MongoDB"],
    "target_keywords": ["Full Stack Developer", "Software Engineer"],
    "resume_text": "..."
  },
  "parsed_profile": {...}
}
```

### GET /api/profile/preferences
Returns search preference settings (locations, job types, salary floor).

**Auth:** Required

### POST /api/profile/preferences
Update search preference settings.

**Auth:** Required

---

## Error Responses

All errors follow this shape:
```json
{"status": "error", "message": "Human-readable description"}
```

| HTTP Code | Meaning |
|-----------|---------|
| 400 | Bad request (missing required field) |
| 401 | Unauthenticated (missing or invalid token) |
| 404 | Resource not found (job_id does not exist) |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
