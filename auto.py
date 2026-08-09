"""One-click master automation script for jobhunt.

Run this single command:
    python auto.py

It will automatically:
1. Ensure .env is loaded.
2. Build/update profile.json from resume.pdf if needed.
3. Run the live job search agent across all ATS boards.
4. Screen and draft top candidate application kits (with automatic fallback).
5. Export tracker.csv and write out/digest.html.
6. Automatically open out/digest.html in your browser.
"""
from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from pathlib import Path

# Force UTF-8 stdout encoding on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from jobhunt import cli


def main() -> int:
    print("=" * 65)
    print(" JOBHUNT AUTOMATION: End-to-End Pipeline")
    print("=" * 65)

    # 1. Check profile.json
    profile_path = ROOT / "profile.json"
    resume_path = ROOT / "resume.pdf"

    if profile_path.exists():
        print("\n[1/3] Verified profile.json (ready)")
    elif resume_path.exists():
        print("\n[1/3] Generating profile.json from resume.pdf...")
        try:
            cli.cmd_profile(argparse.Namespace(resume=str(resume_path), yaml=False))
        except Exception as e:
            print(f"  ! Warning: Profile generation error ({e}). Continuing with existing settings...")
    else:
        print("\n[1/3] Warning: Neither profile.json nor resume.pdf found!")

    # 2. Run the main pipeline
    print("\n[2/3] Running job search pipeline...")
    cli._load_env()
    smtp_pass = os.environ.get("SMTP_PASS", "")
    send_email = bool(smtp_pass and "your-gmail" not in smtp_pass and "paste-your" not in smtp_pass)

    run_args = argparse.Namespace(
        config=None,
        mock=False,
        send=send_email,
        scorer="llm",
    )
    exit_code = cli.cmd_run(run_args)

    # If LLM run failed due to API quota/key error, run automatic offline fallback
    if exit_code != 0:
        print("\n  ! LLM provider unavailable/rate-limited. Running automatic keyword fallback...")
        fallback_args = argparse.Namespace(
            config=None,
            mock=False,
            send=send_email,
            scorer="keyword",
        )
        exit_code = cli.cmd_run(fallback_args)

    # 3. Launch digest in browser (skip in CI / headless)
    digest_path = ROOT / "out" / "digest.html"
    if digest_path.exists() and not os.environ.get("CI"):
        print(f"\n[3/3] Opening {digest_path} in your browser...")
        try:
            webbrowser.open(digest_path.as_uri())
        except Exception:
            pass

    print("\n" + "=" * 65)
    print(" AUTOMATION COMPLETE!")
    print("=" * 65)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
