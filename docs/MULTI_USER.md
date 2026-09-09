<p align="center">
  <img src="../assets/logo.png" alt="Job Hunter Logo" width="100" height="100">
</p>

# Multi-User Architecture and Operating Model

Job Hunter supports multi-user batch processing on a free-tier stack for development and monitored beta use. Capacity and cost depend on current provider limits and measured workload:

---

## System Architecture

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

## How Single-Pass Batch Processing Works

When running in multi-user mode (`python -m jobhunt multi-run`):

1. **Shared Board Fetching (`fetch_all`)**:
   - The engine aggregates both baseline company boards (`companies.yaml`) and all custom company boards added by registered candidates via the "+ Add Board" feature.
   - It crawls all target ATS boards across Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, and Pinpoint **exactly once**.
   - Postings are cached in a thread-safe in-memory cache with an 1800-second TTL.
   - This eliminates rate limits and redundant network I/O regardless of whether there are 5 or 500 users.

2. **Isolated Candidate Evaluation**:
   - For each active profile stored in Supabase PostgreSQL:
  - The authenticated candidate profile is the source of truth for preferences, resume context, scoring, drafting, notifications, and custom boards; a different user's local profile is never used.
     - Deterministic title/location pre-filtering narrows down candidate jobs.
     - Deduplication checks the user's private `user_tracked_jobs` table to prevent re-evaluating previously scored jobs.
     - Surviving new jobs are screened and application kits drafted.
   - **Shared Provider Configuration**: Pipeline provider credentials are loaded from deployment environment variables. Candidate profiles never persist or return provider API keys, so tenant profile data remains safe to expose through the authenticated application API.
     - Results are synchronized to their private Supabase partition.
     - A personalized HTML briefing is dispatched if email notifications are enabled.

---

## Zero-Cost Infrastructure Breakdown & Free Capacity

| Service | Free Tier Allocation | Per-User Consumption | Hard Free User Limit | Role in Job Hunter |
| :--- | :--- | :--- | :---: | :--- |
| **Google Gemini AI** | 1,500 RPD, 1M tokens/day per key | ~4.5 requests/day | **300 Users / Key** | Primary screening & tailored kit drafting |
| **Gmail SMTP** | 500 emails / 24 hours | 1 email digest / day | **500 Users** | Daily morning HTML career intelligence briefing |
| **Supabase PostgreSQL** | 500MB DB, 50,000 MAU | ~450 KB (300-job rolling window) | **1,040 Users** | Tenant-isolated profiles, tracking stores, and audit history |
| **GitHub Actions** | 2,000 free runner mins / month | ~1.0s / user in batch mode | **1,500 Users** | Automated scheduled morning radar execution (25m job timeout) |
| **Vercel** | 100GB bandwidth, serverless | ~15 MB / user / month | **6,600 Users** | Web Dashboard hosting and REST API |
| **9 ATS Board Crawlers** | Public JSON APIs (88+ boards) | 0 extra (single global pass) | **Unlimited** | Scouts Greenhouse, Lever, Ashby, Workable, SmartRecruiters, etc. |

> **Bottom Line:** Supports **300 Daily Active Users** out-of-the-box on 1 free Gemini key + 1 Gmail account, **500 Users** by supplying a 2nd free Gemini key (`GEMINI_API_KEY=key1,key2`), and up to **1,040 Users** on the Supabase 500 MB database free tier.

---

## Running Multi-User Batch Pipeline

### Via Command Line:
```bash
# Dry run with mock data
python -m jobhunt multi-run --mock --scorer keyword

# Live run across all active users
python -m jobhunt multi-run --send
```

### Via GitHub Actions:
- Trigger manually from the **Actions** tab by choosing `multi` mode.
- Automated daily schedule runs every day at 23:30 UTC (05:00 IST).

The current Supabase schema isolates user rows by normalized email claims. The
scheduled worker uses the service-role key to enumerate eligible profiles and
therefore has administrative access; this is not a claim that administrators
are technically unable to read tenant data. Migration to immutable Supabase
user IDs is documented in `LAUNCH_READINESS.md`.

---

## Related Documentation

- **[SETUP.md](SETUP.md)** — Beginner installation and local quickstart guide.
- **[GUIDE.md](GUIDE.md)** — Personal utility & cloud automation workflows.
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — Free-tier cloud production deployment guide.
- **[DASHBOARD.md](DASHBOARD.md)** — Web dashboard and REST API reference.
- **[ENGINE.md](ENGINE.md)** — Scoring and matching engine specifications.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Setup troubleshooting and FAQs.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Developer instructions and test suite.
- **[README.md](../README.md)** — Project homepage.

