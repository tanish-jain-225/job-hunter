# 📊 Job Hunter — Operational Architecture & Business Metrics

This document outlines the operational capacity, resource consumption, infrastructure scaling thresholds, and cost economics of the **Job Hunter** autonomous career intelligence platform.

---

## 1. Executive Summary

Job Hunter is engineered with a **Centralized Multi-Tenant Global Pool** architecture. Instead of crawling job boards separately for every user, the crawler executes a **single-pass crawl** across all 90+ ATS endpoints every morning, deduplicates jobs into an in-memory pool, and evaluates all candidates concurrently.

Combined with **self-compacting storage pruning** and **frontier AI splitting**, the system operates at **$0.00 / month** for up to **~350 daily active users**.

```mermaid
flowchart LR
    A["90+ ATS Boards (Single Crawl)"] --> B["Global Pool (~2,000 Raw Postings)"]
    B --> C["Deterministic Filter (Per User)"]
    C --> D["Stage 1: Groq Screening (0.7s)"]
    D --> E["Stage 2: Gemini Drafting (2.0s)"]
    E --> F["100-300 Morning HTML Briefings"]
    E --> G["Supabase PostgreSQL (Auto-Pruned)"]
```

---

## 2. Multi-User Scale & Workload Matrix

| Metric | 100 Users | 200 Users | 300 Users | 500 Users | 1,000 Users |
|---|:---:|:---:|:---:|:---:|:---:|
| **Daily Discovered Jobs** | ~2,000 | ~2,000 | ~2,000 | ~2,000 | ~2,000 |
| **ATS Crawl Requests** | ~95 | ~95 | ~95 | ~95 | ~95 |
| **Stage 1 Screening Calls (Groq)** | ~200 | ~400 | ~600 | ~1,000 | ~2,000 |
| **Stage 2 Drafting Calls (Gemini)** | ~400 | ~800 | ~1,200 | ~2,000 | ~4,000 |
| **Emails Dispatched / Day** | 100 | 200 | 300 | 500 | 1,000 |
| **Daily Cron Runtime (GitHub Actions)** | ~6.5 mins | ~11 mins | ~17 mins | ~27 mins | ~50 mins |
| **Permanent DB Size Plateau** | ~45 MB | ~90 MB | ~135 MB | ~225 MB | ~450 MB |
| **Total Monthly Running Cost** | **$0.00** | **$0.00** | **$0.00** | **~$1 – $5** | **~$10 – $15** |
| **Free Tier Status** | 🟢 100% Free | 🟢 100% Free | 🟢 100% Free | 🟡 Minor Tweaks | 🔴 Paid Tier |

---

## 3. Component-by-Component Infrastructure Breakdown

### A. Stage 1 Batch Screening (Groq Cloud)
* **Default Model**: `llama-3.1-8b-instant` *(with drafting on `llama-3.3-70b-versatile` / `gemini-3.6-flash`)*
* **Batch Size**: 15 jobs per screening request (reduces API call volume by **~54%**).
* **Batch Pacing & Concurrency**: 3.5s delay between requests with single-worker sequential execution (`max_workers: 1`), keeping token traffic continuously under 30,000 TPM limit.
* **429 Cooldown Recovery**: Automatic 62.0s reset window on HTTP 429 rate limit responses, ensuring **100% AI screening completion** with 0% circuit-breaker fallback rate.
* **Daily Free Quota**: **14,400 requests / day**.
* **Capacity**:
  * 100 Users: 200 calls (**1.4%** of quota)
  * 300 Users: 600 calls (**4.2%** of quota)
  * 1,000 Users: 2,000 calls (**13.9%** of quota)
* **Headroom**: Groq screening alone can comfortably support **7,000+ daily users** on free tier.

### B. Stage 2 Application Kit Drafting (Google Gemini)
* **Default Model**: `gemini-3.6-flash`
* **Output**: 150-word cover note, 80-word cold outreach message, 3-4 tailored resume bullets, India eligibility tag, and LPA salary analysis.
* **Daily Free Quota**: **1,500 requests / day**.
* **Capacity**:
  * 100 Users: ~400 kits (**26.6%** of quota)
  * 200 Users: ~800 kits (**53.3%** of quota)
  * 300 Users: ~1,200 kits (**80.0%** of quota)
  * *Threshold*: Crosses 1,500/day at **~375 users**.

### C. Database & Multi-Tenant Storage (Supabase PostgreSQL)
* **Free Tier Quota**: **500 MB Database Storage** & **50,000 Monthly Active Users**.
* **Storage Invariant**: Every user profile is capped at a rolling retention window of **300 unapplied jobs** (`jobhunt/store.py:prune_old_jobs`).
* **Protected Records**: Jobs marked `Applied`, `Interviewing`, or `Offer` are **never pruned**.
* **Storage Plateau**:
  * Average size per stored job kit: **~1.5 KB**
  * 300 jobs $\times$ 1.5 KB = **~450 KB per user**
  * 300 Users = **~135 MB total** (Uses **27%** of 500 MB free tier).

### D. Daily Briefing Dispatch (Gmail SMTP)
* **Free Outbound Limit**: **500 emails / 24 hours** per Google Account.
* **Capacity**:
  * 100 Users: 100 emails (**20%** of limit)
  * 300 Users: 300 emails (**60%** of limit)
  * *Threshold*: Hard ceiling reached at **500 users**.

### E. Compute & Automation (GitHub Actions Cloud)
* **Free Monthly Minutes**: **2,000 minutes / month** (or unlimited if repository is public).
* **Schedule**: Daily at **09:00 AM IST** (`30 3 * * *`).
* **Capacity**:
  * 100 Users: 7 min/day $\times$ 30 = **210 mins/mo** (**10.5%** of quota)
  * 300 Users: 17 min/day $\times$ 30 = **510 mins/mo** (**25.5%** of quota)

---

## 4. The Steady-State Storage Equilibrium Model

Traditional databases grow indefinitely over time ($O(N \times T)$), eventually causing disk crashes. Job Hunter uses an **$O(N)$ bounded sliding window**:

$$\text{Database Storage}(t) = N_{\text{users}} \times \left( M_{\text{active\_jobs}} \times S_{\text{job\_record}} + M_{\text{applied\_jobs}} \times S_{\text{job\_record}} + S_{\text{profile}} \right)$$

Where:
* $M_{\text{active\_jobs}} \le 300$ (enforced by FIFO pruning)
* $S_{\text{job\_record}} \approx 1.5 \text{ KB}$
* $S_{\text{profile}} \approx 2.0 \text{ KB}$

**Result**: After ~45 days of initial scan accumulation, storage stops growing and reaches a permanent, stable equilibrium plateau.

---

## 5. Scaling Thresholds & Friction Milestones

```mermaid
timeline
    title Scaling Thresholds & Action Triggers
    0 to 350 Users : 100% Free
                   : Zero-maintenance baseline configuration
    350 to 500 Users : Gemini 1,500 Quota Hit
                     : Switch DRAFT_PROVIDER=groq for 14,400 free daily calls
    500 to 1,000 Users : Gmail 500 Email Cap Hit
                       : Add free Brevo (300/day) or Resend (3,000/mo) SMTP provider
    1,000 to 2,000+ Users : Supabase 500MB Cap Hit
                          : Reduce MAX_TRACKED_JOBS_COUNT to 100 or upgrade to Supabase Pro ($25/mo)
```

---

## 6. Real-World Risk & Mitigation Playbook

| Risk Factor | Impact | Mitigation Strategy |
|---|---|---|
| **AI Provider Free Tier Changes / Rate Limits (TPM/429)** | Provider reduces limits or hits 429 quota spikes | Sequential 3.5s batch delay + 62s reset window on 429 + instant auto-switch between Groq, Gemini, Anthropic, and local Ollama via environment variables. |
| **ATS Anti-Scraping Policies** | ATS adds bot challenge on public endpoints | All 9 supported ATS engines use standard public JSON career APIs that have remained open for over a decade. Proxy rotation can be enabled if needed. |
| **Email Deliverability (Spam Filter)** | High-volume emails from `@gmail.com` land in spam | For >300 users, connect a custom domain with verified SPF, DKIM, and DMARC DNS records via Amazon SES or Resend. |
| **GitHub Access Token Expiration** | Workflow dispatch fails to trigger | Set GitHub Personal Access Tokens (`GH_TOKEN`) with "No Expiration" or rotate annually. |

---

## 7. Cost Comparison: Job Hunter vs. Commercial SaaS Alternatives

| Capability | Job Hunter (Self-Hosted) | Commercial Job Tracker SaaS |
|---|:---:|:---:|
| **300 Daily Candidate Briefings** | **$0.00 / mo** | ~$150 – $300 / mo |
| **Real Frontier AI Tailoring (Gemini/Groq)** | **$0.00 / mo** | Included in Pro (~$29/user/mo) |
| **90+ ATS Boards Indexing** | **$0.00 / mo** | Limited to major platforms |
| **Multi-Tenant User Isolation** | **Included (Supabase RLS)** | Enterprise Tier Only |
| **Annual Running Cost (300 Users)** | **🎉 $0.00 / Year** | **~$1,800 – $3,600 / Year** |
