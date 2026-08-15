# 👥 Multi-User Configuration Guide

This guide explains how **Job Hunter** can be configured and run for multiple users (e.g., friends, classmates, or members of a recruitment/job-seeking group) who want to track different job roles, target locations, or skills.

There are two distinct architectural approaches to support multiple users:
1. **Method 1: Forking the Repository (Decentralized & Recommended)**
2. **Method 2: Single-Repository Execution Loop (Centralized)**

---

## 👥 Method 1: Forking the Repository (Recommended)

This is the cleanest, most secure, and most scalable method. Since Job Hunter runs as a serverless utility in the cloud, each user gets their own isolated instance.

### How It Works
Each user clicks the **Fork** button on the main repository (`tanish-jain-225/job-hunter`) to clone it to their personal GitHub account. They keep their repository **private** for security and data privacy.

### Setup Checklist for Each User
1. **Fork the repo** to their own GitHub account.
2. Go to **Settings → Secrets and variables → Actions** in their own fork.
3. Add their personal credentials as Secrets:
   - `PROFILE_JSON`: The JSON content of their personal resume/profile.
   - `SMTP_USER`: Their personal sender email (e.g., Gmail).
   - `SMTP_PASS`: Their Gmail 16-character App Password.
   - `MAIL_TO`: Their personal email address where they want the daily digest delivered.
   - `GEMINI_API_KEY`: Their own Gemini API Key (or shared key).

### Why This is the Best Approach
* **🔒 Privacy:** Resumes, job tracking data, email addresses, and API credentials are kept private.
* **⚡ Deduplication Isolation:** Each user has their own `seen.json` cache file. They will never miss a job because another user already saw it or applied to it.
* **🆓 Free GitHub Runner Minutes:** GitHub grants 2,000 free action runner minutes per month per GitHub account. Forking distributes the CPU usage, ensuring nobody runs out of minutes.
* **🛠️ No Code Modifications:** Works out-of-the-box with the current codebase.

---

## 🏗️ Method 2: Single-Repository Execution Loop (Centralized)

If you want to run the job hunter pipeline for multiple users from a **single repository run** (e.g., using one central email server and one API key), you can configure a centralized loop.

### 1. Store Multiple Profiles
Create a folder named `profiles/` in the project root containing a profile for each user:
* `profiles/tanish.json`
* `profiles/john.json`

*(Make sure to update `.gitignore` if you want to exclude these profiles from being pushed to a public repository, or keep the repo private).*

### 2. Create a Wrapper script (`multi_run.py`)
Create a python script in the root directory that overrides parameters dynamically for each user, maintains separate tracking databases, and dispatches separate emails:

```python
import os
import shutil
import subprocess
from pathlib import Path

# Define the users to run the pipeline for
USERS = [
    {
        "name": "tanish",
        "profile_file": "profiles/tanish.json",
        "seen_file": "seen_tanish.json",
        "mail_to": "tanishjain020205@gmail.com"
    },
    {
        "name": "john",
        "profile_file": "profiles/john.json",
        "seen_file": "seen_john.json",
        "mail_to": "john.doe@example.com"
    }
]

ROOT = Path(__file__).resolve().parent

def run_pipeline_for_user(user):
    print(f"\n==================================================")
    print(f"🚀 Running Job Hunter for: {user['name'].upper()}")
    print(f"==================================================")

    # 1. Setup their profile.json
    shutil.copy(ROOT / user["profile_file"], ROOT / "profile.json")

    # 2. Setup their seen.json (if it exists, restore it)
    user_seen_path = ROOT / user["seen_file"]
    active_seen_path = ROOT / "seen.json"
    if user_seen_path.exists():
        shutil.copy(user_seen_path, active_seen_path)
    elif active_seen_path.exists():
        os.remove(active_seen_path) # Clean start for new user

    # 3. Override recipient email
    os.environ["MAIL_TO"] = user["mail_to"]

    # 4. Execute the pipeline
    try:
        subprocess.run(["python", "auto.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Pipeline failed for {user['name']}: {e}")

    # 5. Save back their updated seen.json
    if active_seen_path.exists():
        shutil.copy(active_seen_path, user_seen_path)

if __name__ == "__main__":
    for user in USERS:
        run_pipeline_for_user(user)
    
    # Cleanup active files to avoid confusing local runs
    for temp_file in ["profile.json", "seen.json"]:
        if (ROOT / temp_file).exists():
            os.remove(ROOT / temp_file)
```

### 3. Update the GitHub Action Workflow
To support this centralized run in GitHub Actions:
1. Save each user's profile inside the repository (e.g. `profiles/user1.json`) or load them dynamically.
2. Update the caching block in `.github/workflows/daily.yml` to save all user-specific cache files (`seen_*.json`):
   ```yaml
         - name: Restore dedupe store
           uses: actions/cache@v6
           with:
             path: |
               seen_tanish.json
               seen_john.json
             key: jobhunt-seen-${{ runner.os }}-${{ github.run_number }}
             restore-keys: |
               jobhunt-seen-${{ runner.os }}-
               jobhunt-seen-
   ```
3. Change the execution run command in `daily.yml` from `python auto.py` to:
   ```yaml
   run: python multi_run.py
   ```

### Comparison Summary

| Feature | Method 1: Forking | Method 2: Single-Repo Loop |
| :--- | :--- | :--- |
| **Data Privacy** | 🟢 Absolute (Isolated repos) | 🔴 Shared (All profiles in one repo) |
| **API Costs/Limits**| 🟢 Distributed across accounts | 🟡 Higher (Single API Key limit risk) |
| **Maintenance** | 🟢 Automatic (Zero code changes) | 🟡 Manual (Need to maintain `multi_run.py`) |
| **Email Server** | 🟢 Individual SMTP credentials | 🟡 Single SMTP Server (Sends to all users) |
| **Setup Complexity**| 🟢 Low | 🟡 Medium |
