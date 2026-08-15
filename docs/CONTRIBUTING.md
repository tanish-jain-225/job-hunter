# 🤝 Contributing to Job Hunter

Thank you for your interest in contributing to `jobhunt`! This guide covers local development setup, test execution, code quality standards, and architectural conventions.

> 💡 *For user setup instructions, see [SETUP.md](SETUP.md).*  
> 💡 *For the personal utility usage guide, see [GUIDE.md](GUIDE.md).*  
> 💡 *For the web dashboard and REST API, see [DASHBOARD.md](DASHBOARD.md).*  
> 💡 *For the scoring and matching engine, see [ENGINE.md](ENGINE.md).*  
> 💡 *For multi-user settings, see [MULTI_USER.md](MULTI_USER.md).*  
> 💡 *For troubleshooting guidelines, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).*  
> 💡 *For architectural design specifications, see [JOB_HUNT.md](JOB_HUNT.md).*

---

## 💻 Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/tanish-jain-225/job-hunter.git
   cd job-hunter
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   
   # Windows
   .venv\Scripts\activate

   # macOS/Linux
   source .venv/bin/activate
   ```

3. **Install editable package with development dependencies**:
   ```bash
   pip install -e ".[dev]"
   ```

---

## 🧪 Running Tests & Quality Checks

### 1. Test Suite (pytest)
Run the full test suite without any network requests or API keys (189 tests with 99%+ coverage):
```bash
pytest
```
Run with complete coverage:
```bash
pytest --cov=jobhunt --cov=app --cov=auto --cov-report=term-missing
```

### 2. Linting & Code Style (Ruff)
```bash
ruff check .
```

### 3. Static Type Checking (Mypy)
```bash
mypy jobhunt app.py auto.py
```

### 4. Dry Run Verification
Validate the pipeline offline using bundled fixtures:
```bash
jobhunt run --mock --scorer keyword
```

---

## 🏗️ Architecture & Layout

```
jobhunt/
  ├── __init__.py       # Package version & public symbols
  ├── fetch.py          # Job dataclass & ATS parsers (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR)
  ├── prefilter.py      # Pre-LLM deterministic title/location/age filtering
  ├── providers.py      # Swappable LLM clients (Anthropic, Gemini, Groq, OpenAI-compat, Ollama)
  ├── llm.py            # Screening, drafting, profile generation & forgiving JSON parser
  ├── store.py          # seen.json state management & CSV exporter
  ├── digest.py         # Responsive HTML email digest generator
  ├── mailer.py         # SMTP email delivery
  ├── mock.py           # Native ATS fixtures for testing & offline dry runs
  └── cli.py            # Argument parsing and main entry point
```

---

## 📏 Code Guidelines & Principles

1. **Separation of Parsing and I/O**:
   - HTTP fetching must be kept separate from ATS response parsing.
   - Parsers in `fetch.py` take decoded JSON data structures (`dict`/`list`) and return `list[Job]`. This allows offline testing via `mock.py`.

2. **Cost & Rate Guardrails**:
   - Never call an LLM before passing deterministic regex and location filtering in `prefilter.py`.
   - Screening batches jobs together to minimize tokens.

3. **Error Resilience**:
   - Network errors or bad responses from a single board or LLM batch must never crash the entire run.
   - Parse functions handle malformed JSON and model preamble noise forgivingly (`llm.parse_json`).

4. **Adding an ATS Adapter**:
   - Implement `parse_<ats_name>(slug: str, company: str, body: Any) -> list[Job]` in `fetch.py`.
   - Add endpoint mapping in `ENDPOINTS` dictionary in `fetch.py`.
   - Add fixtures in `mock.py`.
   - Write tests in `tests/test_parsers.py`.

---

## 🔗 Documentation Links

- **[SETUP.md](SETUP.md)** — Beginner installation guide.
- **[GUIDE.md](GUIDE.md)** — Personal utility & cloud automation guide.
- **[DASHBOARD.md](DASHBOARD.md)** — Web dashboard and REST API.
- **[ENGINE.md](ENGINE.md)** — Scoring and matching engine details.
- **[MULTI_USER.md](MULTI_USER.md)** — Multi-user setup strategies.
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Setup troubleshooting.
- **[JOB_HUNT.md](JOB_HUNT.md)** — Original prompt & technical requirements specification.
- **[README.md](../README.md)** — Project homepage.
