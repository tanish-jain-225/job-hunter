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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Job Hunter Master Automation Pipeline.")
    parser.add_argument("-c", "--config", help="Path to config YAML file (default: config.yaml).")
    parser.add_argument("--mock", action="store_true", help="Use mock ATS data (no network).")
    parser.add_argument("--send", action="store_true", default=None, help="Send digest email via SMTP.")
    parser.add_argument("--scorer", choices=["llm", "keyword"], default="llm", help="Scoring engine.")
    parser.add_argument("--resume", help="Path to resume file (PDF or text) to generate profile.json.")

    raw_argv = argv if argv is not None else ([] if any("pytest" in a for a in sys.argv[:1]) else sys.argv[1:])
    parsed_args, _ = parser.parse_known_args(raw_argv)

    print("=" * 65)
    print(" JOBHUNT AUTOMATION: End-to-End Pipeline")
    print("=" * 65)

    os.chdir(ROOT)

    # Safety Check: Warn if credentials are committed in git
    if (ROOT / ".git").exists():
        import subprocess
        try:
            result = subprocess.run(
                ["git", "ls-files", "--error-unmatch", ".env"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(ROOT),
            )
            if result.returncode == 0:
                print("\n" + "!" * 65)
                print(" WARNING: Your sensitive .env file is currently tracked in Git!")
                print(" Storing API keys and passwords in Git is a critical security risk.")
                print(" Please untrack it immediately by running:")
                print("     git rm --cached .env")
                print("!" * 65)
        except Exception:
            pass

    # 1. Check profile.json
    profile_path = ROOT / "profile.json"
    resume_path = Path(parsed_args.resume) if parsed_args.resume else (ROOT / "resume.pdf")

    if profile_path.exists() and not parsed_args.resume:
        print("\n[1/3] Verified profile.json (ready)")
    elif resume_path.exists():
        print(f"\n[1/3] Generating profile.json from {resume_path}...")
        try:
            cli.cmd_profile(argparse.Namespace(resume=str(resume_path), yaml=False))
        except (Exception, SystemExit) as e:
            print(f"  ! Warning: Profile generation error ({e}). Continuing with existing settings...")
    else:
        print("\n[1/3] Warning: Neither profile.json nor resume.pdf found!")

    # 2. Run the main pipeline
    print("\n[2/3] Running job search pipeline...")
    cli._load_env()
    if not os.environ.get("LLM_PROVIDER") and os.environ.get("GEMINI_API_KEY") and not os.environ.get("GROQ_API_KEY"):
        os.environ["LLM_PROVIDER"] = "gemini"

    smtp_pass = os.environ.get("SMTP_PASS", "")
    if parsed_args.send is None:
        send_email = bool(smtp_pass and "your-gmail" not in smtp_pass and "paste-your" not in smtp_pass)
    else:
        send_email = bool(parsed_args.send)

    run_args = argparse.Namespace(
        config=parsed_args.config,
        mock=bool(parsed_args.mock),
        send=send_email,
        scorer=parsed_args.scorer,
    )
    exit_code = cli.cmd_run(run_args)

    # If LLM run failed due to API quota/key error, run automatic offline fallback
    if exit_code != 0 and parsed_args.scorer == "llm":
        print("\n  ! LLM provider unavailable/rate-limited. Running automatic keyword fallback...")
        fallback_args = argparse.Namespace(
            config=parsed_args.config,
            mock=bool(parsed_args.mock),
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
