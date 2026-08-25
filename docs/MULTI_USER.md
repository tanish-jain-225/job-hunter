# 🌐 Multi-User Architecture & Zero-Cost Forever Scaling

Job Hunter is engineered to support hundreds of concurrent job seekers indefinitely on a **100% free-tier cloud stack**:

---

## 🏛️ System Architecture

```text
                               ┌────────────────────────────────┐
                               │  GitHub Actions / Local Cron   │
                               │  (Scheduled Daily at 09:00 IST)│
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
    │  • Groq Screen (⚡) │          │  • Groq Screen (⚡) │          │  • Groq Screen (⚡) │
    │  • Gemini Draft    │          │  • Gemini Draft    │          │  • Gemini Draft    │
    │  • Supabase Sync   │          │  • Supabase Sync   │          │  • Supabase Sync   │
    │  • HTML Digest     │          │  • HTML Digest     │          │  • HTML Digest     │
    └────────────────────┘          └────────────────────┘          └────────────────────┘
```

---

## 💡 How Single-Pass Batch Processing Works

When running in multi-user mode (`python -m jobhunt multi-run`):

1. **Shared Board Fetching (`fetch_all`)**:
   - The engine crawls all configured target company ATS boards across Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR, Recruitee, Breezy HR, and Pinpoint **exactly once**.
   - Postings are cached in a thread-safe in-memory cache with an 1800-second TTL.
   - This eliminates rate limits and redundant network I/O regardless of whether there are 5 or 500 users.

2. **Isolated Candidate Evaluation**:
   - For each active profile stored in Supabase PostgreSQL:
     - Deterministic title/location pre-filtering narrows down candidate jobs.
     - Deduplication checks the user's private `user_tracked_jobs` table to prevent re-evaluating previously scored jobs.
     - Surviving new jobs are screened via **Groq** (`llama-3.3-70b-versatile`, 14,400 RPD free) and application kits drafted using **Google Gemini** (`gemini-3.5-flash`).
     - Results are synchronized to their private Supabase partition.
     - A personalized HTML briefing is dispatched if email notifications are enabled.

---

## 📊 Zero-Cost Infrastructure Breakdown

| Service | Free Tier Allocation | Job Hunter Usage |
| :--- | :--- | :--- |
| **Vercel** | 100GB bandwidth, serverless functions | Web Dashboard hosting |
| **Supabase PostgreSQL** | 500MB database, 50,000 monthly active users | User profiles, private tracking stores, audit history |
| **Groq API** | 30 RPM, 14,400 RPD on `llama-3.3-70b-versatile` | Ultra-fast candidate fit screening |
| **Google Gemini API** | 15 RPM, 1M TPM, 1,500 RPD on `gemini-3.5-flash` | High-quality application kit drafting |
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
- Automated daily schedule runs Monday through Friday at 03:30 UTC (09:00 IST).

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

