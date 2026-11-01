# Security Policy

## Supported Versions

Only the latest release receives active security patches and updates.

| Version | Supported          |
| ------- | ------------------ |
| 1.1.8   | :white_check_mark: |
| 1.1.7   | :white_check_mark: |
| < 1.1.7 | :x:                |

---

## Security Architecture & Hardening in v1.1.8

Job Hunter implements defense-in-depth principles across all components:

### 1. ATS URL Sanitization & Protocol Whitelisting
- All job application URLs are sanitized via `resolveJobUrl` (`static/js/app.js`), strictly enforcing `http://` and `https://` schemas.
- Malicious URI schemes (`javascript:`, `data:`, `vbscript:`) are rejected and stripped to prevent Cross-Site Scripting (XSS).
- Search input rendering enforces regex entity lookahead `(?![^&]*;)`, preventing search term queries from corrupting escaped HTML character entities.

### 2. Candidate Credential Stripping
- Any data ingested through `/api/profile` undergoes recursive recursive parameter filtering.
- Sensitive credential markers (`api_key`, `token`, `secret`, `password`) are automatically stripped before writing to local or remote storage.

### 3. Content Security Policy (CSP) & Security Headers
The Flask backend (`jobhunt/web/__init__.py`) enforces strict security headers on every HTTP response:
- **Content-Security-Policy (CSP)**: Disallows untrusted inline scripts; explicitly whitelists trusted CDNs and official preview endpoints (`https://job-hunter-web-board.vercel.app`).
- **X-Content-Type-Options**: `nosniff` prevents MIME-type sniffing attacks.
- **X-Frame-Options**: `DENY` prevents clickjacking.
- **Strict-Transport-Security (HSTS)**: Mandates HTTPS transport in production.
- **Referrer-Policy**: `strict-origin-when-cross-origin`.

### 4. Supabase Row Level Security (RLS) & Authentication
- All multi-tenant queries enforce Supabase PostgreSQL Row Level Security (RLS) linked to `auth.uid()`.
- Unauthenticated or cross-tenant data access is blocked at the database engine level.

---

## Reporting a Vulnerability

We take the security of Job Hunter and its users seriously. If you discover a security issue or vulnerability, please **do not open a public issue on GitHub**.

Instead, please report vulnerabilities via:
1. **GitHub Security Advisory**: Submit a private advisory report at [https://github.com/tanish-jain-225/job-hunter/security/advisories/new](https://github.com/tanish-jain-225/job-hunter/security/advisories/new)
2. **Email**: Contact `tanishjain020205@gmail.com` with the subject `[SECURITY] Job Hunter Vulnerability Report`.

### What to Include in Your Report
- A detailed description of the vulnerability.
- Steps to reproduce or proof-of-concept (PoC) code/scripts.
- Potential impact and affected versions.
- Any suggested remediation or patches.

### Response Timeline
- **Initial Response**: Within 24-48 hours acknowledging receipt of report.
- **Triage & Assessment**: Within 3 business days.
- **Fix & Public Disclosure**: Coordinated release with CVE assignment where applicable.
