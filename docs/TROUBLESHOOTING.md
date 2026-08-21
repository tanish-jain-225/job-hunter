# 🔍 Troubleshooting & FAQ Guide

This guide covers solutions to common errors, configurations, and questions encountered when setting up or running **Job Hunter**.

---

## 📧 Email & SMTP Authentication Issues

### Error: `SMTPAuthenticationError` or "Gmail Authentication Failed"
* **Why it happens:** Standard Gmail accounts block direct SMTP logins with your primary account password for security, especially when 2-Step Verification is enabled.
* **The Solution:** You must create an **App Password**:
  1. Go to your [Google Account Security settings](https://myaccount.google.com/apppasswords).
  2. Select **App Passwords** (if you don't see it, search for "App Passwords" in the search bar at the top).
  3. Enter a custom name like `Job Hunter` and click **Create**.
  4. Copy the generated **16-character password** (e.g., `abcd efgh ijkl mnop`).
  5. Paste this 16-character password without spaces as your `SMTP_PASS` value in your `.env` or GitHub Secrets.

### Error: Emails are sent but land in Spam/Junk folder
* **Why it happens:** Custom automated emails sent via raw SMTP are sometimes marked suspicious by receiving mail servers.
* **The Solution:** 
  * Add your sender email address (`SMTP_USER`) to the contacts list of your recipient email address (`MAIL_TO`).
  * Open the first email in your email client and click **"Not Spam"** or **"Move to Inbox"**.

---

## 🤖 GitHub Actions Issues

### Warning: `Node.js 20 is deprecated... being forced to run on Node.js 24`
* **Why it happens:** Legacy versions of standard workflows target Node.js 20, which is deprecated.
* **The Solution:** Ensure you are using the latest Node 24-native action versions in your workflow files (`.github/workflows/daily.yml` and `ci.yml`):
  * `actions/checkout@v7`
  * `actions/cache@v6`
  * `actions/setup-python@v7`
  * `actions/upload-artifact@v7`

### Warning: `PROFILE_JSON secret not set — using profile.example.json fallback`
* **Why it happens:** The workflow cannot read your local `profile.json` because it is git-ignored. It fallback to `profile.example.json`.
* **The Solution:** Add your profile as a GitHub Action Secret:
  1. Copy the JSON contents of your local `profile.json`.
  2. Go to your GitHub repository $\rightarrow$ **Settings** $\rightarrow$ **Secrets and variables** $\rightarrow$ **Actions**.
  3. Click **New repository secret**.
  4. Name: `PROFILE_JSON`.
  5. Secret: *Paste your copied JSON*.
  6. Click **Add secret**.

### Issue: The daily cron workflow is delayed or runs late
* **Why it happens:** GitHub Actions runs scheduled cron jobs on a shared queue. On free tiers, scheduled runs can be delayed anywhere from 10 minutes to over an hour depending on global runner load.
* **The Solution:** This is normal and expected. If you need immediate results, you can always trigger it manually:
  * Click the **Actions** tab $\rightarrow$ select **daily job digest** $\rightarrow$ click **Run workflow**.

---

## ⚡ API Quotas & Rate Limiting

### Error: `429 Too Many Requests` or Gemini Quota Limit Exceeded
* **Why it happens:** You are using the Google Gemini free tier API (15 RPM ceiling) and high-concurrency requests or multiple fast runs exceeded the rate limit.
* **The Solution:** 
  * Job Hunter includes automatic parallel worker pacing (`min(delay_seconds, 1.0) * worker_idx`) to prevent burst collisions.
  * In `config.yaml`, set `llm_max_workers` to `1` or `2` for free-tier keys.
  * Increase `llm_delay_seconds` (e.g., `3.0` or `4.0`) to insert a larger pause between batches.
  * Increase `screen_batch_size` (e.g., to `8` or `10`) to evaluate more jobs per API call and save overall requests.

---

## 📋 Data & Caching Questions

### Issue: How do I backup or export my job tracker?
* **Answer:** All job tracking data is saved in a simple text-based format in your project root:
  * `seen.json` contains raw statuses, scores, cover letters, and timestamps.
  * `out/tracker.csv` is updated on every run and can be double-clicked to open in **Microsoft Excel**, **Google Sheets**, or **LibreOffice Calc**.
  * Keep your backups safe by committing `seen.json` or uploading it to cloud drives.

### Question: Why did the same job show up again in my feed?
* **Answer:** Some recruiters delete and re-post the same listing on Greenhouse or Lever. When they do, the ATS assigns it a **new unique job ID**. Because the ID changed, Job Hunter treats it as a fresh posting. You can filter duplicates out manually on your web dashboard by clicking **Mark Applied** or ignoring it.

---

## 🔗 Documentation Links

- **[SETUP.md](SETUP.md)** — Complete step-by-step setup guide.
- **[GUIDE.md](GUIDE.md)** — Personal utility & cloud automation guide.
- **[DASHBOARD.md](DASHBOARD.md)** — Web dashboard and REST API reference.
- **[ENGINE.md](ENGINE.md)** — Job-matching engine details.
- **[MULTI_USER.md](MULTI_USER.md)** — Setting up multiple users.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Developer instructions and test suite.
- **[JOB_HUNT.md](JOB_HUNT.md)** — Original prompt & technical requirements specification.
- **[README.md](../README.md)** — Project homepage.

