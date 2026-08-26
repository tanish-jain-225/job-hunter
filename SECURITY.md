# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 1.0.x   | Yes (actively supported) |
| < 1.0   | No (end of life)    |

---

## Reporting a Vulnerability

**Please do NOT open a public GitHub Issue for security vulnerabilities.**

Open a GitHub Security Advisory: https://github.com/tanish-jain-225/job-hunter/security/advisories/new

Include: affected component, steps to reproduce, potential impact, suggested fix (optional).

### Response SLA

| Severity | Acknowledgement | Fix Target |
|----------|----------------|------------|
| Critical | 24 hours | 48 hours |
| High | 48 hours | 7 days |
| Medium/Low | 72 hours | 30 days |

---

## Security Scope

| Component | File(s) | Risk Area |
|-----------|---------|-----------|
| JWT Authentication | `jobhunt/auth.py` | Token forgery, bypass, cache timing |
| Supabase RLS Isolation | `jobhunt/memory.py` | Cross-tenant data leakage |
| Flask API Endpoints | `jobhunt/web/routes/` | Injection, auth bypass |
| Credential Loading | `jobhunt/cli.py` | Secret leakage |
| LLM Prompt Handling | `jobhunt/llm.py` | Prompt injection via JDs |
| ATS HTTP Fetching | `jobhunt/fetch.py` | SSRF via crafted company slugs |

---

## Security Architecture

- **JWT tokens** verified via local PyJWT (if `SUPABASE_JWT_SECRET` set) or Supabase Auth API. Cached 60s via SHA-256 hash.
- **Supabase RLS** ensures users only access their own rows. Service role key only used in admin multi-run batch, gated via `use_service_key=True`.
- **Tokens never accepted via query string** — only `Authorization: Bearer` headers and HttpOnly cookies.
- **Rate limiting** via `flask-limiter`: 5 calls/hour on `/api/run`, 500/hour global default.
- **XSS protection**: Digest content escaped via `html.escape()`. Jinja2 auto-escaping enabled.
- **Content-Security-Policy** headers applied to all responses.
