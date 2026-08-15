# 📑 Job Hunter — Original Prompt & Specification

This document contains the foundational specification prompt for **Job Hunter**, detailing the system requirements, ATS endpoints, prefiltering logic, LLM stages, data schemas, and design constraints.

> 💡 *For user setup instructions, see [SETUP.md](SETUP.md).*  
> 💡 *For the personal utility usage guide, see [GUIDE.md](GUIDE.md).*  
> 💡 *For the web dashboard details, see [DASHBOARD.md](DASHBOARD.md).*  
> 💡 *For details on the job-matching engine, see [ENGINE.md](ENGINE.md).*  
> 💡 *For setting up multiple users, see [MULTI_USER.md](MULTI_USER.md).*  
> 💡 *For troubleshooting common issues, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).*  
> 💡 *For developer guidelines & testing, see [CONTRIBUTING.md](CONTRIBUTING.md).*

---

## 🎯 What it Does

One daily run performs the following automated funnel:

1. **Fetch** — pull open postings from public ATS APIs (no auth, no scraping)
2. **Prefilter** — deterministic regex/location/freshness gate, no LLM
3. **Screen** — cheap LLM pass scores each surviving job 0–10 against resume
4. **Draft** — detailed LLM pass writes an application kit for top candidates
5. **Digest** — build a responsive HTML email and dispatch it via SMTP
6. **Track** — record everything in a JSON store + CSV export

**It must never auto-submit an application.** The human presses submit; the agent handles finding, matching, drafting, and tracking.

---

## 📡 Data Sources (Exact ATS Endpoints)

- **Greenhouse**: `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true`
- **Lever**: `GET https://api.lever.co/v0/postings/{slug}?mode=json`
- **Ashby**: `GET https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true`
- **Workable**: `GET https://apply.workable.com/api/v2/accounts/{slug}/jobs`
- **SmartRecruiters**: `GET https://api.smartrecruiters.com/v1/companies/{slug}/postings`
- **BambooHR**: `GET https://{slug}.bamboohr.com/careers/list`

### Field Mapping
- **Greenhouse** $\rightarrow$ `jobs[]` with `id`, `title`, `location.name`, `absolute_url`, `updated_at`, `content` (HTML-entity-escaped HTML).
- **Lever** $\rightarrow$ top-level array with `id`, `text` (title), `categories.location`, `hostedUrl`, `descriptionPlain`, `createdAt` (epoch **ms**). Concatenate `descriptionPlain` + `lists[]` + `additionalPlain`.
- **Ashby** $\rightarrow$ `jobs[]` with `id`, `title`, `location`, `jobUrl`, `descriptionPlain`, `publishedAt`, `compensation`. Skip roles with `isListed: false`.
- **Workable** $\rightarrow$ `results[]` or `jobs[]` with `shortcode`, `title`, `location.city`, `url`, `description`, `published`.
- **SmartRecruiters** $\rightarrow$ `content[]` with `id`, `name`, `location.city`, `refNumber`, `jobAd.sections.jobDescription.text`, `releasedDate`.
- **BambooHR** $\rightarrow$ `result[]` or `jobs[]` with `id`, `jobOpeningName`, `location`, `description`, `datePosted`.

Normalize all ATS boards into one dataclass with a globally unique `job_id = "{ats}:{slug}:{id}"` for deduplication.

---

## 🏗️ Architecture

Keep HTTP separate from parsing — each ATS gets a pure `parse_x(slug, company, body) -> list[Job]` function that takes decoded JSON.

```
jobhunt/
  ├── fetch.py       # Job dataclass, strip_html, ATS parsers, fetch_all
  ├── prefilter.py   # title include/exclude regex, location, max_age_days
  ├── llm.py         # provider-agnostic screen() + draft() + build_profile()
  ├── digest.py      # HTML email digest builder
  ├── mailer.py      # SMTP email dispatcher
  ├── store.py       # seen.json dedupe + application tracker + CSV export
  ├── mock.py        # Native ATS fixtures for testing
  └── cli.py         # argparse: profile / run / applied / stats
```

---

## 🤖 LLM Layer

Two stages for token efficiency:

- **Screen** — batch ~8 jobs per call, truncate each JD to ~1400 chars, return JSON array of `{job_id, score, reason}`.
- **Draft** — only for jobs above the score threshold. Send ~6000 chars of JD, return `{fit_summary, tailored_bullets[], gaps[], cover_note, questions_to_ask[]}`.

### Provider Flexibility
Make provider swappable via environment variables (`LLM_PROVIDER`):
- Google Gemini (`gemini-3.5-flash`)
- Groq (`llama-3.3-70b-versatile`)
- Anthropic (`claude-3-5-sonnet`)
- OpenAI-compatible endpoints & local Ollama

---

## 🧪 Testing & Verification

- `--mock` flag runs fixtures through real parsers with zero network requests.
- `--scorer keyword` provides offline dev scoring without API keys.
- Comprehensive test suite in `tests/` covering batching, parsing, store persistence, and mock funnel assertions.

---

## 🔗 Documentation Links

- **[SETUP.md](SETUP.md)** — Beginner installation guide.
- **[GUIDE.md](GUIDE.md)** — Personal utility & cloud automation guide.
- **[DASHBOARD.md](DASHBOARD.md)** — Web dashboard and API reference.
- **[ENGINE.md](ENGINE.md)** — Job-matching engine details.
- **[MULTI_USER.md](MULTI_USER.md)** — Setting up multiple users.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Troubleshooting and FAQs.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Developer instructions.
- **[README.md](../README.md)** — Project homepage.
