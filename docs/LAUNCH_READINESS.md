# Public Launch Readiness

This document is the execution plan for turning Job Hunter into a public,
multi-tenant product. The current application is a strong private beta, but it
must not be presented as fully production-ready until the items below are
complete.

## Completed in this pass

- Authenticated digest requests no longer fall back to a repository-wide HTML
  artifact. A digest must come from the authenticated user's profile or their
  isolated store.
- CSV exports use a request-unique temporary artifact and remove it after the
  response, preventing concurrent serverless requests from sharing a file.
- Production GitHub Actions dispatch is restricted to `PIPELINE_ADMIN_EMAILS`
  or an explicit `is_admin` claim. A normal user cannot trigger the all-user
  batch job.
- Cookie-authenticated mutations require matching same-origin `Origin` or
  `Referer` metadata.
- Resume upload behavior is now consistent: PDF and TXT are supported; DOCX is
  not advertised or silently decoded as text.
- Regression status: 397 tests pass; Ruff and whitespace checks pass.

## P0: Required before public sign-up

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

### 2. Introduce a durable per-user run model

Vercel requests must dispatch a job and return a durable run ID. They must not
execute crawling, LLM calls, or drafting synchronously in a serverless request.

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

Do not open public registration until all P0 items are complete and verified in
a production-like environment. The minimum release evidence is:

- Full test suite and blocking security checks are green.
- Two test accounts cannot read or export each other's data.
- Changing an account email does not move or expose tenant data.
- A user-triggered run cannot execute the all-user workflow.
- A worker restart does not lose a queued or running run.
- Account deletion removes all user-owned data within the documented period.