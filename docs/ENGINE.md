# ⚙️ Job Matching & Scoring Engine Guide

The core power of **Job Hunter** lies in its deterministic filtering and two-stage LLM evaluation pipeline. The engine is optimized for **zero API costs**, **token efficiency**, and **high resilience** to network/API rate failures.

---

## 🏗️ Pipeline Phases

Each run executes a sequential funnel to filter down thousands of job postings into a few top matches.

```mermaid
graph TD
    A[Fetch Job Boards] --> B[Phase 1: Deterministic Prefilter]
    B -->|Passed include/exclude rules| C[Phase 2: LLM Screening]
    C -->|Score >= Threshold| D[Phase 3: LLM Drafting]
    C -->|Score < Threshold| E[Discarded]
    D --> F[Compile HTML Digest & Export CSV]
```

### Phase 1: Deterministic Prefiltering (Deterministic & Free)
Before any LLM token is spent, all fetched postings are run through quick regex and date matches defined in [config.yaml](../config.yaml):
* **Include Titles:** Matches target roles (e.g., `software engineer`, `backend`, `intern`).
* **Exclude Titles:** Drops invalid matches (e.g., `senior`, `lead`, `ios`, `devops`).
* **Location Gate:** Checks if the posting matches target regions (e.g., `mumbai`, `bengaluru`) or allows `remote`.
* **Employment Type & Negation Gate:** Detects `remote`, `hybrid`, `onsite`, and `internship` roles with negation awareness (filtering out *"not remote"*, *"no internships"* false positives).
* **Date Freshness:** Discards jobs published longer than `max_age_days` (default `21` days) ago.

*Typically, this phase drops ~98% of jobs, reducing a crawl of 2,000 listings down to ~40 candidates for LLM screening.*

---

## 🤖 Phase 2: LLM Screening & Scoring (Token Efficient)

For the surviving postings, Job Hunter performs a cheap, batched evaluation pass to score how well the job description aligns with your resume profile.

### High-Throughput Batching & Cost Reduction
Rather than sending job descriptions one-by-one, Job Hunter batches **8 jobs per LLM call** (configured via `screen_batch_size`). It truncates each job description to **1,000 characters** (configured via `screen_jd_chars`), keeping rich context for evaluation.

When `GEMINI_API_KEY` is configured (with single key or multi-key CSV rotation `key1,key2,key3`), Job Hunter routes all batch screening to **Google Gemini (`gemini-3.6-flash`)**, leveraging Gemini's massive 1M token context window and 1,000,000+ daily tokens per project allowance at zero cost.

### Evaluation Criteria
The LLM is prompted to assign a score from **`0.0` to `10.0`** based on:
1. **Core Skills Match:** Does the candidate possess the required stack?
2. **Seniority Alignment:** Does the job match the target seniority level (e.g. Intern/Junior vs. Principal)?
3. **Domain Match:** Does the job domain align with the candidate's experience?
4. **India & Remote Eligibility:** Evaluates location compatibility for Indian and remote-friendly roles.

The LLM returns a JSON list:
```json
[
  {
    "job_id": "greenhouse:stripe:4089201",
    "score": 8.5,
    "reason": "Uses Python/React. Fits graduation timeline."
  }
]
```

---

## ✍️ Phase 3: LLM Drafting (Application Kit Generation)

Only jobs that score at or above the **`score_threshold`** (default `5.0`–`7.0/10`) progress to this stage. Here, the system performs a detailed, single-job analysis.

### High-Context Evaluation
The engine sends the full job description (up to **8,000 characters**, configured via `draft_jd_chars`) along with your full candidate profile. It routes to **Google Gemini (`gemini-3.6-flash`)** or **Anthropic Claude (`claude-3-7-sonnet`)** to generate a complete application kit:

* **Fit Summary:** A brief 2-sentence summary of why this role is a strong match.
* **Tailored Resume Bullets:** 3 high-impact bullet points demonstrating skills matching the job requirements that you can insert into your resume.
* **Gaps Analysis:** An honest assessment of missing requirements and how to address them.
* **Cover Note:** A direct, professional outreach letter tailored directly to the hiring team.
* **Cold Outreach:** A concise (<80 words) direct message for LinkedIn/email networking.
* **Interview Questions:** 2 sharp technical questions showing thorough reading of the JD.

---

## ⏳ Phase 4: Smart Follow-Up Outreach Engine

For jobs in `applied` or `interviewing` stages, Job Hunter calculates the elapsed time since application date. If more than 4 days have elapsed without response:

* **Automated Nudges**: Injects `⏳ Xd ago · Follow Up` badges across both Table and visual Kanban cards.
* **On-Demand Generation (`jobhunt.llm.generate_followup_note`)**: Produces context-aware follow-up templates:
  * **Email Subject & Body**: References the exact job title, company name, submission date, and reiterates enthusiasm without being pushy.
  * **LinkedIn Networking DM**: Compact (<80 words) direct message to connect with recruiters or hiring team members.
* **1-Click Copy**: Integrated into the Application Kit modal for instant clipboard copy.

---

## 🔌 Swappable Providers & Zero-Quota Split Architecture

The system is provider-agnostic and auto-routes tasks intelligently when keys are set:

```env
GROQ_API_KEY=gsk_...       # Routes screening to Groq (30 RPM, 14,400 RPD)
GEMINI_API_KEY=AIzaSy_...  # Routes drafting to Gemini (rich context window)
```

### Supported Configurations

| Provider | Default Model | Config Key | Role in Split Architecture |
| :--- | :--- | :--- | :--- |
| **Groq** | `openai/gpt-oss-20b` | `GROQ_API_KEY` | **Screening:** Ultra-fast high-throughput batch evaluation (14,400 RPD free). |
| **Google Gemini** | `gemini-3.6-flash` | `GEMINI_API_KEY` | **Drafting:** Rich context window for personalized application kits. |
| **Anthropic** | `claude-3-7-sonnet` | `ANTHROPIC_API_KEY` | High-reasoning drafting and native PDF resume analysis. |
| **OpenAI Compatible** | `gpt-4o-mini` / `gpt-4o` | `GROQ_API_KEY` + `LLM_BASE_URL` | OpenAI-compatible endpoint provider. |
| **Ollama** | Local model (`llama3.1`) | `OLLAMA_HOST` | Run locally on your machine for 100% free, offline inference. |

---

## 🛡️ Resilience & Fallback Mechanics

Job Hunter is built to ensure a scheduled crawl never fails due to network hiccups, API outages, or rate limits.

### 1. Offline Keyword Scorer Fallback
If your LLM provider is down, hits rate limits, or is not configured, the engine automatically falls back to the **Keyword Scorer** (defined in `jobhunt.llm`). 
* It scans the job text for keywords matching your `core_skills` (from `profile.json`).
* It assigns a score based on skill density.
* This allows the digest to still build and send with basic relevance matching, entirely offline!

### 2. Forgiving JSON Parser (`llm.parse_json`)
LLMs often wrap JSON outputs in Markdown code blocks (````json ... ````) or include conversational preambles/conversations. Job Hunter uses an intelligent, regex-backed parser that extracts only the valid JSON substring and handles missing brackets or commas gracefully, preventing model parsing errors from crashing runs.

---

## 🔗 Documentation Links

- **[SETUP.md](SETUP.md)** — Complete step-by-step setup guide.
- **[GUIDE.md](GUIDE.md)** — Personal utility & cloud automation guide.
- **[DEPLOYMENT.md](DEPLOYMENT.md)** — Free-tier cloud production deployment guide.
- **[DASHBOARD.md](DASHBOARD.md)** — Web dashboard and REST API reference.
- **[MULTI_USER.md](MULTI_USER.md)** — Setting up multiple users.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Troubleshooting and FAQs.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Developer instructions and test suite.
- **[JOB_HUNT.md](JOB_HUNT.md)** — Original prompt & technical requirements specification.
- **[README.md](../README.md)** — Project homepage.


