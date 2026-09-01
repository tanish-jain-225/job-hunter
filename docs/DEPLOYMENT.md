# 🚀 Production Deployment Guide (100% Free Stack)

Deploy **Job Hunter** as a multi-user, production-ready cloud application capable of supporting hundreds of concurrent candidates indefinitely at **$0 / ₹0 operational cost**.

---

## 🏛️ Free-Tier Cloud Architecture

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
│   Zero-Quota AI Intelligence   │       │       Daily Cron Engine         │
│ Groq + Gemini Split (Free)     │       │     GitHub Actions (Free)       │
│  - Groq 14,400 RPD Screening   │       │  - Scheduled 6:00 AM Run        │
│  - Gemini Rich Kit Drafting    │       │  - Single-Pass 9-ATS Crawl      │
│  - Automatic Keyword Fallback  │       │  - Daily Morning Email Briefing │
└────────────────────────────────┘       └─────────────────────────────────┘
```

---

## 📋 Free-Tier Resource Quotas

| Service | Free Plan Quotas | What Job Hunter Uses | Cost |
| :--- | :--- | :--- | :--- |
| **Vercel** | 100 GB Bandwidth, Unlimited Deployments | Web Dashboard & REST API Hosting | **$0 / mo** |
| **Supabase** | 500 MB Database, 50k MAU, 500k Edge Invocations | User profiles, auth sessions, tracked jobs | **$0 / mo** |
| **Groq API** | 30 RPM, 14,400 Requests/Day Free | Stage 1 candidate batch fit screening | **$0 / mo** |
| **Google Gemini API** | 15 RPM, 1,000,000 TPM, 1,500 Requests/Day | Stage 2 application kit drafting | **$0 / mo** |
| **GitHub Actions** | 2,000 runner minutes/month | Automated daily morning batch radar | **$0 / mo** |
| **Gmail SMTP / Resend** | 500 emails/day (Gmail) or 3,000 emails/mo (Resend) | Personalized daily career intelligence briefings | **$0 / mo** |

---

## 🛠️ Step 1: Set Up Supabase Database (2 Minutes)

1. Create a free account at [supabase.com](https://supabase.com) and create a new project (e.g. `job-hunter-prod`).
2. Go to **SQL Editor** in your Supabase dashboard.
3. Paste the contents of [`supabase/schema.sql`](../supabase/schema.sql) and click **Run**.
4. Go to **Project Settings > API Keys**:
   * Copy the **Project URL** (`https://xyzcompany.supabase.co`) -> `SUPABASE_URL`
   * Copy the **Public Anon Key** (`anon` `public`) -> `SUPABASE_ANON_KEY`
   * Copy the **Service Role Secret** (`service_role` `secret`) -> `SUPABASE_SERVICE_ROLE_KEY`
5. Go to **Authentication > URL Configuration**:
   * Add your production Vercel domain (e.g. `https://job-hunter.vercel.app`) to **Site URL** and **Redirect URLs**.

---

## 🔑 Step 2: Get Free AI API Keys (2 Minutes)

1. **Google Gemini Flash (Primary AI Engine)**: Visit [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) $\rightarrow$ Create API Key $\rightarrow$ `GEMINI_API_KEY`.
   *(Supports comma-separated keys for instant multi-key rotation: `key1,key2,key3`)*

---

## 📧 Step 3: Configure SMTP Email Delivery (Optional, 2 Minutes)

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
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
AUTH_REQUIRED=true

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-16-char-app-password

# Optional: GitHub Personal Access Token (for 1-click cloud on-demand radar from web UI)
GH_TOKEN=github_pat_...
GITHUB_REPOSITORY=your-username/job-hunter

# Optional: Static Flask secret key for serverless session stability
FLASK_SECRET_KEY=jobhunter-secure-prod-flask-key-2025
```

5. Click **Deploy**. Vercel will build and deploy your live dashboard at `https://your-project.vercel.app`!

---

## ⏰ Step 5: Configure Automated Daily 6:00 AM Cron (GitHub Actions)

Job Hunter automatically executes a centralized single-pass crawl across all active users every weekday morning via GitHub Actions.

1. Go to your GitHub repository > **Settings > Secrets and variables > Actions**.
2. Add the following **Repository Secrets**:
   * `GROQ_API_KEY`: Your Groq API Key
   * `GEMINI_API_KEY`: Your Google Gemini API Key
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

## 👥 Multi-User Candidate Experience

1. Any candidate visits `https://your-project.vercel.app`.
2. Signs in with email/password or Magic Link.
3. The **Onboarding Wizard** pops up:
   * Candidate picks a 1-click role preset (*Full Stack, Backend, Frontend, AI/ML, DevOps, Data, Product Lead*) or uploads a resume to extract skills in-memory.
   * Chooses their notification preference (*Instant On-Demand* or *Daily 6:00 AM Morning Briefing*).
   * Clicks **"Complete & Launch First Hunt"**.
4. The system immediately screens target boards, ranks opportunities, drafts custom cover notes and cold messages, and organizes everything onto their private Kanban tracker!

---

## 🔒 Security & Tenant Isolation Guarantee

* **Row-Level Security (RLS)**: PostgreSQL enforces that users can only view and update their own tracked jobs, application kits, and profiles.
* **No File Persistence**: Uploaded resumes are decoded in-memory for one-time text extraction; no candidate PDFs or binary documents are stored on disk or cloud buckets.
* **Service Role Access**: Automated GitHub Actions cron uses the Service Role key exclusively to query active profiles and deliver candidate-tailored briefings.

---

## 📚 Related Documentation

- **[SETUP.md](SETUP.md)** — Beginner installation and local quickstart guide.
- **[GUIDE.md](GUIDE.md)** — Personal utility & cloud automation workflows.
- **[DASHBOARD.md](DASHBOARD.md)** — Web dashboard and REST API reference.
- **[ENGINE.md](ENGINE.md)** — Scoring and matching engine specifications.
- **[MULTI_USER.md](MULTI_USER.md)** — Multi-user scaling architecture.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Setup troubleshooting and FAQs.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Developer instructions and test suite.
- **[README.md](../README.md)** — Project homepage.

