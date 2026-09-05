<p align="center">
  <img src="../assets/logo.png" alt="Job Hunter Logo" width="100" height="100">
</p>

# 🌐 Multi-User Architecture & Zero-Cost Forever Scaling

Job Hunter is engineered to support hundreds of concurrent job seekers indefinitely on a **100% free-tier cloud stack**:

---

## 🏛️ System Architecture

```text
                               ┌────────────────────────────────┐
                               │  GitHub Actions / Local Cron   │
                               │  (Scheduled Daily at 05:00 IST)│
                               └───────────────┬────────────────┘
                                               │
                                               ▼
                              ┌──────────────────────────────────┐
                              │     Global Single-Pass Crawl     │
                              │ 9 ATS Engines -> In-Memory Pool │
                              └────────────────┬─────────────────┘
                                               │
               ┌───────────────────────────────┴───────────────────────────────┐
               ▼                               ▼                               ▼
    ┌────────────────────┐          ┌────────────────────┐          ┌────────────────────┐
    │  Candidate Alpha   │          │   Candidate Beta   │          │   Candidate Gamma  │
    ├────────────────────┤          ├────────────────────┤          ├────────────────────┤
    │  • User Filters    │          │  • User Filters    │          │  • User Filters    │
    │  • Private Store   │          │  • Private Store   │          │  • Private Store   │
    │  • Gemini Screen   │          │  • Gemini Screen   │          │  • Gemini Screen   │
    │  • Gemini Draft    │          │  • Gemini Draft    │          │  • Gemini Draft    │
    │  • Supabase Sync   │          │  • Supabase Sync   │          │  • Supabase Sync   │
    │  • HTML Digest     │          │  • HTML Digest     │          │  • HTML Digest     │
    └────────────────────┘          └────────────────────┘          └────────────────────┘
```

---

## 💡 How Single-Pass Batch Processing Works

When running in multi-user mode (`python -m jobhunt multi-run`):

1. **Shared Board Fetching (`fetch_all`)**:
   - The engine aggregates both baseline company boards (`companies.yaml`) and all custom company boards added by registered candidates via the "+ Add Board" feature.
   - It crawls all target ATS boards across Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, and Pinpoint **exactly once**.
   - Postings are cached in a thread-safe in-memory cache with an 1800-second TTL.
   - This eliminates rate limits and redundant network I/O regardless of whether there are 5 or 500 users.

2. **Isolated Candidate Evaluation**:
   - For each active profile stored in Supabase PostgreSQL:
     - Deterministic title/location pre-filtering narrows down candidate jobs.
     - Deduplication checks the user's private `user_tracked_jobs` table to prevent re-evaluating previously scored jobs.
     - Surviving new jobs are screened and application kits drafted.
     - **Dynamic API Key Isolation**: If configured in their settings, the pipeline executes using the candidate's private `GEMINI_API_KEY`. This completely isolates rate limits per candidate, protecting the system from shared quota bottlenecks and shifting all API costs to $0 for the platform owner. If custom keys are omitted, the pipeline falls back to the system's global keys.
     - Results are synchronized to their private Supabase partition.
     - A personalized HTML briefing is dispatched if email notifications are enabled.

---

## 📊 Zero-Cost Infrastructure Breakdown

| Service | Free Tier Allocation | Job Hunter Usage |
| :--- | :--- | :--- |
| **Vercel** | 100GB bandwidth, serverless functions | Web Dashboard hosting |
| **Supabase PostgreSQL** | 500MB database, 50,000 monthly active users | User profiles, private tracking stores, audit history |
| **Google Gemini API** | 1,000,000 TPM, 1,500 RPD (Supplied by Candidate / System Keys) | Candidate fit screening, resume tailoring, and application kit drafting |
| **GitHub Actions** | 2,000 free runner minutes / month | Scheduled daily radar execution |
| **Gmail SMTP** | 500 emails / day | Daily executive briefing email delivery |

---

## 🚀 Running Multi-User Batch Pipeline

### Via Command Line:
```bash
# Dry run with mock data
python -m jobhunt multi-run --mock --scorer keyword

# Live run across all active users
python -m jobhunt multi-run --send
```

### Via GitHub Actions:
- Trigger manually from the **Actions** tab by choosing `multi` mode.
- Automated daily schedule runs every single day at 23:30 UTC (05:00 IST).

---

## 📚 Related Documentation

- **[SETUP.md](SETUP.md)** — Beginner installation and local quickstart guide.
- **[GUIDE.md](GUIDE.md)** — Personal utility & cloud automation workflows.
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — Free-tier cloud production deployment guide.
- **[DASHBOARD.md](DASHBOARD.md)** — Web dashboard and REST API reference.
- **[ENGINE.md](ENGINE.md)** — Scoring and matching engine specifications.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Setup troubleshooting and FAQs.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Developer instructions and test suite.
- **[README.md](../README.md)** — Project homepage.

