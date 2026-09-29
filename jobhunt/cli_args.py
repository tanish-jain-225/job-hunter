"""Command-line argument parser definitions for jobhunt."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build and configure the top-level argument parser for jobhunt."""
    from . import __version__

    parser = argparse.ArgumentParser(
        prog="jobhunt",
        description="Personal & Multi-User job search intelligence agent.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subparsers.add_parser("run", help="Fetch, filter, score, and draft digest for primary account.")
    p_run.add_argument("-c", "--config", help="Path to config YAML file (default: config.yaml).")
    p_run.add_argument("--mock", action="store_true", help="Use mock ATS data (no network).")
    p_run.add_argument("--send", action="store_true", help="Send digest email via SMTP.")
    p_run.add_argument(
        "--strict-llm", action="store_true", help="Enforce 100%% live LLM execution (no keyword fallback)."
    )
    p_run.add_argument("--scorer", choices=["llm", "keyword"], default="llm", help="Scorer to use (default: llm).")

    # multi-run
    p_multi = subparsers.add_parser(
        "multi-run", help="Single-pass batch run across all active multi-tenant user accounts."
    )
    p_multi.add_argument("-c", "--config", help="Path to config YAML file (default: config.yaml).")
    p_multi.add_argument("--mock", action="store_true", help="Use mock ATS data (no network).")
    p_multi.add_argument("--send", action="store_true", help="Force send digest emails via SMTP.")
    p_multi.add_argument(
        "--strict-llm", action="store_true", help="Enforce 100%% live LLM execution (no keyword fallback)."
    )
    p_multi.add_argument("--user-email", help="Process only this authenticated Supabase user.")
    p_multi.add_argument("--scorer", choices=["llm", "keyword"], default="llm", help="Scorer to use (default: llm).")

    # applied
    p_applied = subparsers.add_parser("applied", help="Mark a job ID as applied.")
    p_applied.add_argument("job_id", help="Exact job ID (e.g. greenhouse:acme:5501001).")
    p_applied.add_argument("-c", "--config", help="Path to config YAML file (default: config.yaml).")

    # stats
    p_stats = subparsers.add_parser("stats", help="Report stats on tracked jobs.")
    p_stats.add_argument("-c", "--config", help="Path to config YAML file (default: config.yaml).")

    # profile
    p_prof = subparsers.add_parser("profile", help="Extract profile from resume.")
    p_prof.add_argument("--resume", required=True, help="Path to resume file (PDF or text).")
    p_prof.add_argument("--yaml", action="store_true", help="Save as YAML instead of JSON.")

    # web
    p_web = subparsers.add_parser("web", help="Launch the Flask Web Dashboard & API server.")
    p_web.add_argument("--host", default="0.0.0.0", help="Host interface to bind to (default: 0.0.0.0).")
    p_web.add_argument("--port", type=int, default=5000, help="Port to listen on (default: 5000).")
    p_web.add_argument("--debug", action="store_true", help="Enable Flask debug mode.")

    # verify
    p_verify = subparsers.add_parser("verify", help="Audit company career boards live against public ATS APIs.")
    p_verify.add_argument("-c", "--config", help="Path to config YAML file (default: config.yaml).")
    p_verify.add_argument("--companies", help="Path to companies YAML file (default: companies.yaml).")
    p_verify.add_argument("--workers", type=int, default=25, help="Max parallel request workers (default: 25).")

    # clean
    p_clean = subparsers.add_parser("clean", help="Clean temporary test stores and scratch files from workspace root.")
    p_clean.add_argument("--dry-run", action="store_true", help="List cleanable files without removing them.")

    # check
    p_check = subparsers.add_parser("check", help="Run preflight diagnostic checks on configuration, files, and environment.")
    p_check.add_argument("-c", "--config", help="Path to config YAML file (default: config.yaml).")
    p_check.add_argument("--companies", help="Path to companies YAML file (default: companies.yaml).")

    return parser


__all__ = ["build_parser"]
