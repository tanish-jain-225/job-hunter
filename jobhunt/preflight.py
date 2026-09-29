"""Automated preflight self-check module (`jobhunt check`).

Validates the local environment, configuration files, directories,
optional cloud services, and dependency packages without making external
network calls that would fail in an offline environment.
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def run_preflight_checks(
    config_path: Path | str | None = None,
    companies_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run non-network preflight diagnostics.

    Returns a dict with 'all_ok' (bool), 'checks' (list of check dicts),
    and 'remediations' (list of user-friendly recommendations).
    """
    checks: list[dict[str, Any]] = []
    remediations: list[str] = []

    # 1. Python runtime
    py_ver = sys.version_info
    py_ok = py_ver >= (3, 9)
    checks.append({
        "name": f"Python Runtime (>=3.9, active: {py_ver.major}.{py_ver.minor}.{py_ver.micro})",
        "passed": py_ok,
        "critical": True,
    })
    if not py_ok:
        remediations.append("Upgrade to Python 3.9+ for full typing and runtime compatibility.")

    # 2. Required core packages
    core_packages = [
        ("requests", "requests"),
        ("PyYAML", "yaml"),
        ("Flask", "flask"),
        ("pypdf", "pypdf"),
        ("PyJWT", "jwt"),
        ("flask-limiter", "flask_limiter"),
    ]
    for pkg_name, mod_name in core_packages:
        try:
            importlib.import_module(mod_name)
            checks.append({"name": f"Package: {pkg_name}", "passed": True, "critical": True})
        except ImportError:
            checks.append({"name": f"Package: {pkg_name}", "passed": False, "critical": True})
            remediations.append(f"Install required package '{pkg_name}': pip install -e .")

    # 3. Configuration files
    cfg_file = Path(config_path or "config.yaml")
    if not cfg_file.is_file() and Path("config.example.yaml").is_file():
        cfg_file = Path("config.example.yaml")
    if cfg_file.is_file():
        try:
            yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
            checks.append({"name": f"Configuration File ({cfg_file.name})", "passed": True, "critical": True})
        except Exception as e:
            checks.append({"name": f"Configuration File ({cfg_file.name}): {e}", "passed": False, "critical": True})
            remediations.append(f"Fix YAML syntax errors in {cfg_file}.")
    else:
        checks.append({"name": "Configuration File (config.yaml)", "passed": False, "critical": True})
        remediations.append("Copy config.example.yaml to config.yaml and customize your filters.")

    # 4. Companies targets
    comp_file = Path(companies_path or "companies.yaml")
    if comp_file.is_file():
        try:
            data = yaml.safe_load(comp_file.read_text(encoding="utf-8")) or {}
            comps = data.get("companies", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            comp_ok = len(comps) > 0
            checks.append({
                "name": f"Company Targets ({comp_file.name}: {len(comps)} companies configured)",
                "passed": comp_ok,
                "critical": False,
            })
        except Exception as e:
            checks.append({"name": f"Company Targets ({comp_file.name}): {e}", "passed": False, "critical": False})
            remediations.append(f"Fix YAML syntax errors in {comp_file}.")
    else:
        checks.append({"name": "Company Targets (companies.yaml)", "passed": False, "critical": False})
        remediations.append("Ensure companies.yaml exists with target ATS boards.")

    # 5. Environment Secrets & Services (Non-fatal, informational)
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    checks.append({
        "name": "Gemini AI API Key (GEMINI_API_KEY)",
        "passed": has_gemini,
        "critical": False,
    })
    if not has_gemini:
        remediations.append(
            "GEMINI_API_KEY is not set. For offline runs use: 'jobhunt run --mock --scorer keyword'. "
            "To enable Gemini 3.5 Flash, get a free key at https://aistudio.google.com and set GEMINI_API_KEY in .env."
        )

    has_supabase = bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_ANON_KEY"))
    checks.append({
        "name": "Supabase Cloud Database (SUPABASE_URL & ANON_KEY)",
        "passed": has_supabase,
        "critical": False,
    })
    if not has_supabase:
        remediations.append(
            "Supabase cloud sync is disabled. Operating in local JSON mode (seen.json). "
            "To enable cloud multi-tenancy, configure SUPABASE_URL and SUPABASE_ANON_KEY in .env."
        )

    has_smtp = bool(os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASS"))
    checks.append({
        "name": "SMTP Email Digest Dispatch (SMTP_USER & SMTP_PASS)",
        "passed": has_smtp,
        "critical": False,
    })
    if not has_smtp:
        remediations.append(
            "SMTP email credentials not set. Daily briefings will be saved locally to out/digest.html."
        )

    # 6. Writable paths
    writable_dir = Path("out")
    try:
        writable_dir.mkdir(parents=True, exist_ok=True)
        test_file = writable_dir / ".preflight_write_test"
        test_file.touch()
        test_file.unlink()
        checks.append({"name": "Output Directory Permissions (out/)", "passed": True, "critical": True})
    except Exception as e:
        checks.append({"name": f"Output Directory Permissions (out/): {e}", "passed": False, "critical": True})
        remediations.append("Ensure local directory permissions allow creating out/ and writing files.")

    all_critical_ok = all(c["passed"] for c in checks if c.get("critical", False))

    return {
        "all_ok": all_critical_ok,
        "checks": checks,
        "remediations": remediations,
    }
