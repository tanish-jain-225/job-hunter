<p align="center">
  <img src="../assets/logo.png" alt="Job Hunter Logo" width="100" height="100">
</p>

# Production Deployment Guide

Deploy **Job Hunter** as a monitored public-beta cloud application. Capacity, pricing, quotas, and availability depend on Vercel, Supabase, GitHub, AI-provider, ATS, and SMTP limits.

---

## Free-Tier Cloud Architecture

```text
┌────────────────────────────────┐       ┌─────────────────────────────────┐
│        Frontend & API          │       │       Database & Security       │
│    Vercel Serverless (Free)    │ ────► │     Supabase PostgreSQL (Free)  │
│  - Python Flask REST API       │       │  - Row-Level Security (RLS)     │
│  - Static Responsive Dashboard │       │  - Candidate Profiles & Kits    │
│  - Live Candidate Onboarding   │       │  - 50,000 Monthly Active Users  │
└────────────────────────────────┘       └─────────────────────────────────┘
                │                                         │
                ▼                                         ▼
┌────────────────────────────────┐       ┌─────────────────────────────────┐
│   Zero-Cost AI Intelligence    │       │       Daily Cron Engine         │
│ Google Gemini Flash (Free)     │       │     GitHub Actions (Free)       │
│  - 1M Tokens/Day Screening     │       │  - Scheduled 5:00 AM Run        │
│  - Gemini Rich Kit Drafting    │       │  - Single-Pass 9-ATS Crawl      │
│  - Automatic Keyword Fallback  │       │  - Daily Morning Email Briefing │
└────────────────────────────────┘       └─────────────────────────────────┘
```

---

## External Limits

The following limits are provider-plan examples, not guarantees. Verify current
limits and pricing with each provider before launch.

| Service | Free Plan Quotas | What Job Hunter Uses | Capacity Limit | Cost |
| :--- | :--- | :--- | :---: | :--- |
| **Google Gemini API** | 15 RPM, 1,000,000 TPM, 1,500 Requests/Day (gemini-3.5-flash) | Candidate batch fit screening & tailored application kit drafting | **300 Users / Key** | **$0 / mo** |
| **Gmail SMTP / Resend** | 500 emails/day (Gmail) or 3,000 emails/mo (Resend) | Personalized daily career intelligence briefings | **500 Users** | **$0 / mo** |
| **Supabase** | 500 MB Database, 50k MAU, 500k Edge Invocations | User profiles, auth sessions, tracked jobs (300-job rolling cap) | **1,040 Users** | **$0 / mo** |
| **GitHub Actions** | 2,000 runner minutes/month | Automated daily morning batch radar (25 min timeout) | **1,500 Users** | **$0 / mo** |
| **Vercel** | 100 GB Bandwidth, Unlimited Deployments | Web Dashboard & REST API Hosting | **6,600 Users** | **$0 / mo** |

---

## Step 1: Set Up Supabase Database (2 Minutes)

1. Create a free account at [supabase.com](https://supabase.com) and create a new project (e.g. `job-hunter-prod`).
2. Go to **SQL Editor** in your Supabase dashboard.
3. Paste the contents of [`supabase/schema.sql`](../supabase/schema.sql) and click **Run**. *(To cleanly reset or tear down your tables at any point, use [`supabase/teardown.sql`](../supabase/teardown.sql))*.
4. Go to **Project Settings > API Keys**:
   * Copy the **Project URL** (`https://xyzcompany.supabase.co`) -> `SUPABASE_URL`
   * Copy the **Public Anon Key** (`anon` `public`) -> `SUPABASE_ANON_KEY`
   * Copy the **Service Role Secret** (`service_role` `secret`) -> `SUPABASE_SERVICE_ROLE_KEY`
5. Go to **Authentication > URL Configuration**:
   * Add your production Vercel domain (e.g. `https://job-hunter-web-board.vercel.app`) to **Site URL** and **Redirect URLs**.

Keep `SUPABASE_SERVICE_ROLE_KEY` only in GitHub Actions secrets for the
multi-user worker. Do not add it to Vercel unless a separately reviewed
server-side operation requires it, and never expose it to browser code.

---

## Step 2: Get Free AI API Keys (2 Minutes)

1. **Google Gemini Flash (Primary AI Engine)**: Visit [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) $\rightarrow$ Create API Key $\rightarrow$ `GEMINI_API_KEY`.
   *(Supports comma-separated keys for instant multi-key rotation: `key1,key2,key3`)*

---

## Step 3: Configure SMTP Email Delivery (Optional, 2 Minutes)

To send automated daily briefings and on-demand alerts:

### Option A: Gmail SMTP (Recommended)
1. Go to your Google Account > **Security** > **2-Step Verification**.
2. Scroll to the bottom and create an **App Password** (Named e.g. `JobHunter`).
3. Note the generated 16-character password:
   * `SMTP_HOST`: `smtp.gmail.com`
   * `SMTP_PORT`: `587`
   * `SMTP_USER`: `your-email@gmail.com`
   * `SMTP_PASS`: `your-16-char-app-password`

---

## ▲ Step 4: Deploy Web Dashboard to Vercel (3 Minutes)

1. Push your repository to GitHub.
2. Log into [vercel.com](https://vercel.com) and click **Add New > Project**.
3. Import your `job-hunter` repository.
4. In **Environment Variables**, add:

```ini
GEMINI_API_KEY=your-gemini-api-key

SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_ANON_KEY=your-supabase-anon-key
AUTH_REQUIRED=true

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-16-char-app-password

# Required for 1-click cloud on-demand radar from the web UI. Use a narrowly scoped
# server-side token with workflow dispatch permission; never expose it to the browser.
GH_TOKEN=github_pat_...
GITHUB_REPOSITORY=your-username/job-hunter

# Optional: Static Flask secret key for serverless session stability
FLASK_SECRET_KEY=jobhunter-secure-prod-flask-key-2025
```

5. Click **Deploy**. Vercel will build and deploy your live dashboard at `https://your-project.vercel.app`!

---

## Step 5: Configure Automated Daily 5:00 AM Cron (GitHub Actions)

Job Hunter executes a centralized single-pass crawl across eligible users every day at `23:30 UTC` (`05:00 IST`) via GitHub Actions.

1. Go to your GitHub repository > **Settings > Secrets and variables > Actions**.
2. Add the following **Repository Secrets**:
   * `GEMINI_API_KEY`: Your Google Gemini API Key (aistudio.google.com)
   * `SUPABASE_URL`: Your Supabase Project URL
   * `SUPABASE_ANON_KEY`: Your Supabase Anon Key
   * `SUPABASE_SERVICE_ROLE_KEY`: Your Supabase Service Role Key
   * `SMTP_HOST`: `smtp.gmail.com`
   * `SMTP_PORT`: `587`
   * `SMTP_USER`: Your Gmail address
   * `SMTP_PASS`: Your 16-character Gmail App Password
3. Go to the **Actions** tab in your repo:
   * Enable workflows if prompted.
   * Click **Daily Career Intelligence Digest** > **Run workflow** to test it immediately.

---

## Multi-User Candidate Experience

1. Any candidate visits `https://your-project.vercel.app`.
2. Signs in with email/password or Magic Link.
3. The candidate configures their profile and radar criteria:
   * **First-Time Setup**: The setup wizard guides initial role selection using 1-click presets (*Full Stack, Backend, Frontend, AI/ML, DevOps, Data, Product*) or in-memory resume extraction.
   * **Profile & Search Settings**: At any time, candidates can open Settings for a clean 3-step configuration:
     - *Step 1 (Resume & Raw Text Context)*: Upload `.pdf`/`.txt` resume with 100% in-memory extraction and an editable raw text context editor.
     - *Step 2 (Profile & Search Criteria)*: 1-click **Auto-Fill from Resume Context** with 3-tier fallback protection (AI cascade $\rightarrow$ smart local regex parser $\rightarrow$ client defaults), plus customizable target roles, skills, experience, excluded keywords, job types, and locations.
     - *Step 3 (Alert Settings)*: Match score threshold and notification preference (*Daily 5:00 AM Morning Briefing* or *Instant On-Demand Only*).
4. The system screens target boards, ranks opportunities, drafts custom cover notes and cold messages, and organizes everything onto their private interactive job tracker!

---

## Security & Tenant Isolation Guarantee

* **Row-Level Security (RLS)**: PostgreSQL enforces that users can only view and update their own tracked jobs, application kits, and profiles.
* **No File Persistence**: Uploaded resumes are decoded in-memory for one-time text extraction; no candidate PDFs or binary documents are stored on disk or cloud buckets.
* **Service Role Access**: Automated GitHub Actions cron uses the Service Role key exclusively to query active profiles and deliver candidate-tailored briefings.

---

## Related Documentation

- **[SETUP.md](SETUP.md)** — Beginner installation and local quickstart guide.
- **[GUIDE.md](GUIDE.md)** — Personal utility & cloud automation workflows.
- **[DASHBOARD.md](DASHBOARD.md)** — Web dashboard and REST API reference.
- **[ENGINE.md](ENGINE.md)** — Scoring and matching engine specifications.
- **[MULTI_USER.md](MULTI_USER.md)** — Multi-user scaling architecture.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Setup troubleshooting and FAQs.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Developer instructions and test suite.
- **[README.md](../README.md)** — Project homepage.

