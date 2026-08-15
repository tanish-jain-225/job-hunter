# 🛠️ Complete Setup Guide — Job Hunter

Start here if you've never run a Python project before. Every step assumes you have nothing installed.

**Time:** about 20 minutes. **Cost:** ₹0 / $0 — the free tier of any provider covers this comfortably, because a full day of running is only ~10 API calls.

**What you end up with:** an email every weekday morning with the top engineering jobs worth your time, each with tailored resume bullets, honest gaps, and a draft cover note. You read it, edit it, and apply yourself. The tool never submits anything.

> 💡 *Looking for the database-free personal utility guide? See [GUIDE.md](GUIDE.md).*  
> 💡 *Want to contribute to development? See [CONTRIBUTING.md](CONTRIBUTING.md).*

---

## Step 1 — Install Python

You need **Python 3.10 or newer**.

- **Windows** — download from [python.org/downloads](https://www.python.org/downloads/). On the first screen of the installer, **tick "Add python.exe to PATH"** before clicking Install. Missing that checkbox is the single most common reason nothing works afterwards.
- **macOS** — `brew install python` if you have Homebrew, otherwise python.org.
- **Linux** — `sudo apt install python3 python3-venv python3-pip`

Check it worked. Open a fresh terminal (PowerShell on Windows, Terminal on Mac/Linux) and run:

```bash
python --version        # Windows
python3 --version       # macOS / Linux
```

You should see `Python 3.10.x` or higher. If you see "command not found", reinstall with the PATH box ticked.

> From here on, wherever you see `python`, use `python3` on macOS/Linux.

---

## Step 2 — Get the code

**If you just want to try it on your laptop:** click the green **Code** button on the repo → **Download ZIP** → unzip it. Or, if you have git:

```bash
git clone https://github.com/tanish-jain-225/job-hunter.git
cd job-hunter
```

**If you want it to email you automatically every morning** (this is the whole point of the project), click **Fork** at the top-right of the repo *first*, then clone your own fork instead.

---

## Step 3 — Create a virtual environment and install

A virtual environment keeps this project's packages separate from the rest of your system. Always do this.

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

If PowerShell refuses with *"running scripts is disabled on this system"*, run this once in the same window and try again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

You'll know it worked when your prompt starts with `(.venv)`. Re-activate it whenever you open a new terminal.

---

## Step 4 — Prove it works, with no API key at all

Before touching keys or resumes, check your install with mock data:

```bash
jobhunt run --mock --scorer keyword
```

You should see mock Greenhouse/Ashby boards fetch, filter, and output summary output.

---

## Step 5 — Configure your `.env` & Preferences

Create a `.env` file in your root folder:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_16_char_gmail_app_password
MAIL_TO=your_email@gmail.com
```

Extract your candidate profile from your resume:
```bash
jobhunt profile --resume resume.pdf
# or: python -m jobhunt profile --resume resume.pdf
```

---

## Step 6 — Launch Execution & Dashboard

Once configured, run the pipeline or launch the interactive dashboard:

- **1-Click Master Run**:
  ```bash
  python auto.py
  ```
  *Fetches jobs across all target ATS boards, screens candidates, drafts application kits, updates tracking CSV, and launches `digest.html` briefing in your default browser.*

- **Interactive Web Dashboard**:
  ```bash
  python app.py
  ```
  *Launches the Executive Web Dashboard on `http://localhost:5000` with 1-click CSV export, multi-ATS filtering, sorting, kit modal viewer with multi-copy buttons, and dark mode.*

---

## Step 7 — Next Steps & Useful Links

- **[GUIDE.md](GUIDE.md)** — Learn how to run as a 100% database-free personal utility or configure free GitHub Actions cloud execution.
- **[DASHBOARD.md](DASHBOARD.md)** — Explore the Flask-based web dashboard and REST API endpoints.
- **[ENGINE.md](ENGINE.md)** — Learn about the deterministic prefiltering and swappable LLM matching engine.
- **[MULTI_USER.md](MULTI_USER.md)** — Learn how to configure Job Hunter for multiple users (forking or centralized loop).
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Solutions for SMTP, GitHub Actions, and Gemini rate limits.
- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Developer instructions, test suite execution, and architecture principles.
- **[README.md](../README.md)** — Back to project homepage.
