# Job Hunter — REST API Reference

All endpoints require authentication via `Authorization: Bearer <token>` header
or `sb_access_token` HttpOnly cookie.

---

## Pipeline

### GET /api/sync
Returns current pipeline state, live job stats, and user profile summary.

**Auth:** Required  
**Response:**
```json
{
  "status": "success",
  "version": 42,
  "stats": {"tracked": 120, "applied": 5, "shortlisted": 18, "emailed": 12},
  "ats_counts": {"greenhouse": 40, "lever": 22, ...},
  "pipeline": {"running": false, "step": "completed", "message": "..."},
  "user_email": "user@example.com",
  "user_profile": {...},
  "memory_connected": true,
  "timestamp": 1724645093.4
}
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

---

## Jobs

### GET /api/jobs
Returns all tracked jobs with filtering and sorting.

**Auth:** Required  
**Query params:**
| Param | Values | Default |
|-------|--------|---------|
| `status` | `all` / `shortlisted` / `applied` / `unapplied` | `all` |
| `ats` | `greenhouse` / `lever` / ... / `all` | `all` |
| `search` | free text | — |
| `min_score` | float | — |
| `sort` | `date` / `score` / `company` | `date` |

**Response:** `{"status": "success", "count": 18, "jobs": [...]}`

### POST /api/jobs/stage
Update the Kanban application stage for a job.

**Auth:** Required  
**Body:** `{"job_id": "greenhouse:acme:1234", "stage": "interviewing"}`  
**Stages:** `to_apply` | `applied` | `interviewing` | `offer` | `rejected`

### POST /api/jobs/notes
Update private candidate notes for a tracked job.

**Auth:** Required  
**Body:** `{"job_id": "lever:company:abc", "notes": "Great culture fit, ask about remote"}`

### POST /api/applied
Mark or unmark a job as applied.

**Auth:** Required  
**Body:** `{"job_id": "...", "action": "mark"}` — action: `mark` | `unmark`

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

### GET /api/export/csv
Download tracked jobs as a CSV file attachment.

**Auth:** Required  
**Response:** `text/csv` attachment

### GET /api/stats
Returns a summary of job tracking stats.

**Auth:** Required  
**Response:** `{"tracked": 120, "applied": 5, "shortlisted": 18, "emailed": 12, "version": 42}`

### GET /api/config
Returns active configuration summary (company count, filters, score threshold).

**Auth:** Required

### GET /api/companies
Returns the parsed company list with filtering by name or ATS type.

**Auth:** Required  
**Query params:** `?search=stripe&ats=greenhouse`

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
Upload and parse a candidate resume (PDF or plain text).

**Auth:** Required  
**Content-Type:** `multipart/form-data` (file field: `file`) OR `application/json` (`{"resume_text": "..."}`)  
**Response:** Parsed profile + extracted resume text

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
