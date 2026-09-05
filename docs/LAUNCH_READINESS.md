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
- Regression status: 397 tests pass on the current suite; affected release
  tests, Ruff, coverage, and workflow YAML validation pass.

## Current release status

- **Deployment:** Ready to launch with the existing Vercel, Supabase, GitHub,
  Gemini, and SMTP credentials.
- **User workflow:** Sign up, complete a profile, run an isolated scan, view
  synchronized jobs, and receive scheduled email when notifications are enabled.
- **Data safety:** Authenticated digest/export paths, profile writes, cloud
  dispatch failures, stale pipeline status, and Supabase read outages fail
  safely.
- **Operational boundary:** The service is suitable for a free public beta.
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
- Make workflow security checks blocking in CI.
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