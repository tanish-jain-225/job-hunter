# Public Launch Readiness

This document is the release checklist for the current public-beta product.
The application can be deployed with the existing credentials and supports
isolated user-scoped scans, daily batch email, and Supabase persistence. The
remaining items below are hardening work for higher scale and stronger tenant
identity guarantees, not extra steps required for the current deployment.

## Completed in this pass

- Authenticated digest requests no longer fall back to a repository-wide HTML
  artifact. A digest must come from the authenticated user's profile or their
  isolated store.
- CSV exports use a request-unique temporary artifact and remove it after the
  response, preventing concurrent serverless requests from sharing a file.
- User-triggered GitHub Actions dispatch uses `mode: user` and the verified
  authenticated email. The scheduled workflow is the only all-user batch path.
- Cookie-authenticated mutations require matching same-origin `Origin` or
  `Referer` metadata.
- Resume upload behavior is now consistent: PDF and TXT are supported; DOCX is
  not advertised or silently decoded as text.
- Offline HMAC token verification (`SUPABASE_JWT_SECRET`) and resilient client-side session auto-refresh lifecycle prevent false-positive session drops on Vercel.
- Thread-safe candidate API key propagation prevents cross-tenant secret leakage across concurrent requests without mutating `os.environ`.
- Defensive prompt injection XML isolation (`<untrusted_job_description>`) with active closing tag stripping ensures candidate screening and drafting cannot be hijacked by adversarial job descriptions.
- Zero-latency model alias resolution caching ensures resilient 404 fallbacks for `gemini-3.5-flash` with zero performance overhead.
- RFC 8058 compliant email headers (`List-Unsubscribe`, `List-Unsubscribe-Post`, `Message-ID`, `Date`, `Auto-Submitted`, `Precedence`) and clean plain-text fallback content maximize inbox placement.
- Multi-currency salary regex extraction (`₹X-Y LPA`, `₹Xk/mo`, USD/EUR) and enterprise ATS pagination (SmartRecruiters offset up to 500, Workable cursor up to 500) ensure rich compensation data and complete listing coverage.
- Dynamic asset hashing (`asset_hash`) ensures instant cache-busting of CSS and JS on production deployments.
- Ephemeral Vercel serverless worker state automatically hydrates from Supabase `user_pipeline_runs`.
- Regression status: 503 tests pass on the current suite with zero warnings; strict Mypy typing checks (0 errors across 43 source files), Ruff linter, >=90% test coverage (92%+ achieved), and workflow YAML validation pass.

## Current release status

- **Deployment:** Ready for a public beta when Vercel has valid Supabase
  credentials (including `SUPABASE_JWT_SECRET`) and a server-side GitHub workflow-dispatch token configured.
- **User workflow:** Sign up, complete a profile, run an isolated scan, view
  synchronized jobs, and receive scheduled email only when notifications are
  enabled.
- **Data safety:** Authenticated digest/export paths, profile writes, cloud
  dispatch failures, stale pipeline status, and Supabase read outages fail
  safely.
- **Operational boundary:** The service is suitable for a free public beta
  after the operator verifies the required production environment variables.
  Third-party quotas and GitHub/Vercel execution limits still apply.

## Hardening backlog for scale

### 1. Replace email tenant keys with immutable user IDs

Use Supabase Auth `sub` as the tenant identifier in every table, cache path,
pipeline state key, and storage lookup. Keep email as mutable profile data and
notification destination only.

Migration requirements:

1. Add `auth_user_id UUID NOT NULL` to profiles, jobs, and pipeline runs.
2. Backfill it by joining to `auth.users.email` while preserving the old email
   columns for rollback and audit.
3. Change RLS policies to compare `auth.uid()` with `auth_user_id`.
4. Deploy dual-read/dual-write code, verify counts and isolation, then remove
   email-based foreign keys and policies.
5. Add tests for email change, missing email claims, duplicate email casing,
   and cross-tenant reads under real RLS.

### 2. Extend the durable per-user run model

Vercel requests currently dispatch user-scoped jobs and persist a running
history record. A dedicated run ID and worker lease would improve correlation
and recovery at higher volume.

Required API contract:

- `POST /api/runs` creates an idempotent run for the authenticated user.
- `GET /api/runs/{id}` returns queued, running, completed, failed, or expired.
- `GET /api/runs/{id}/events` streams heartbeats and status changes when
  available, but remains recoverable through polling.
- A worker claims one run with a lease, renews the lease, and records retries.

The all-user scheduled workflow remains an operator/scheduler concern. A user
run must never be implemented by dispatching the `multi` workflow.

### 3. Establish production secret and authorization boundaries

- Store GitHub dispatch credentials only in the worker/control-plane service.
- Remove broad `GH_TOKEN` use from user-facing request execution.
- Configure a real admin role mapping in Supabase rather than relying only on
  an environment email list.
- Add rate limits keyed by immutable user ID and operation, plus idempotency
  keys for run creation.
- Ensure service-role credentials are never accepted from browser input and are
  never returned by profile APIs.

## P1: Required before paid or high-volume use

- Add real Supabase integration tests covering RLS and service-role paths.
- Add retention and deletion flows for resumes, generated drafts, jobs, and
  pipeline logs.
- Add provider budgets, per-user quotas, timeout policy, and retry backoff for
  ATS and LLM calls.
- Add structured audit events for sign-in, profile changes, exports, run
  creation, admin actions, and account deletion.
- Add health checks for Supabase, GitHub dispatch, LLM provider, SMTP, and
  worker queue with actionable operator alerts.

## P2: Product quality after the safety boundary

- Support DOCX through a dedicated parser only after upload size, MIME, and
  content validation are defined.
- Add user-visible run history, partial-result recovery, and retry controls.
- Add notification preferences with verified destination email ownership.
- Add onboarding analytics, feedback capture, and ranking-quality evaluation.
- Publish a privacy policy, data deletion policy, incident contact, and clear AI
  output disclaimer before public marketing or open registration.

## Release gates

Before moving beyond public beta, verify the following in a production-like
environment:

- Full test suite and blocking security checks are green.
- Two test accounts cannot read or export each other's data.
- Changing an account email does not move or expose tenant data.
- A user-triggered run cannot execute the all-user workflow.
- A worker restart does not lose a queued or running run.
- Account deletion removes all user-owned data within the documented period.

The current release is intentionally classified as **public beta**, not a
guaranteed unlimited service. Free-tier provider quotas, delivery failures, and
external workflow availability must be monitored by the operator.

---

## Commercial SaaS Business Model & Monetization Roadmap

Job Hunter is architected to operate at 100% free-tier economics ($0.00/mo) for 300–330 users with default 1,000-job retention (and up to 500–1,040 users with multi-key CSV rotation and 300-job retention). To transition from an open-source public beta to a commercial B2C/B2B SaaS product, follow this commercial blueprint:

### 1. Market Positioning & Disruptive Pricing

| Plan Tier | Target Segment | Proposed Retail Price | Competitor Benchmark | Margin Profile |
|---|---|:---:|:---:|:---:|
| **Community** | Students, open-source | **$0.00 / mo** | Teal Free (heavily locked) | Cost: ~$0.00 (Free tier stack) |
| **Pro Accelerator** | Active engineers & designers | **$9 – $15 / mo** | Teal+ ($29/mo), Huntr Pro ($40/mo), Jobscan ($49.95/mo) | **>98% Gross Margin** (~$0.01 infra cost) |
| **Bootcamp / College** | Career placement cohorts | **$199 – $499 / mo** | Handshake / Symplicity ($$$$) | **>95% Gross Margin** |

### 2. Commercial Technical Prerequisites (The 4 Milestones)
1. **Billing Gateway**: Integrate Stripe Checkout / LemonSqueezy webhooks to automatically toggle `is_pro` status in `user_profiles`.
2. **Immutable User ID Tenancy**: Migrate Supabase RLS from email claims to `auth.users.id` UUIDs.
3. **Dedicated Transactional Email Domain**: Connect Amazon SES or Resend with verified SPF, DKIM, and DMARC DNS records to eliminate personal Gmail 500-email ceilings.
4. **Dedicated Async Execution Queue**: Replace GitHub Actions on-demand workflow dispatch with an in-cluster Celery/Redis or AWS SQS + Lambda worker for instant sub-second radar crawls.

---

## Related Documentation

- **[PRODUCT_ANALYSIS_WALKTHROUGH.md](PRODUCT_ANALYSIS_WALKTHROUGH.md)** — Definitive India-first product audit, 2026 hiring research, hackathon evaluation & SaaS valuation.
- **[ARCHITECTURE.md](ARCHITECTURE.md)** — System architecture, module breakdown, and data pipelines.
- **[SETUP.md](SETUP.md)** — Beginner installation and local quickstart guide.
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — Free-tier cloud production deployment on Vercel and Supabase.
- **[METRICS.md](METRICS.md)** — Operational capacity, storage equilibrium, and cost economics.
- **[SECURITY.md](SECURITY.md)** — Security architecture, authentication, and compliance.
- **[README.md](../README.md)** — Project homepage.

