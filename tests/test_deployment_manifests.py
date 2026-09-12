"""Automated validation test suite for deployment manifests and CI/CD workflow configurations.

Ensures that hosting configuration files, serverless function definitions,
environment templates, and GitHub Actions workflows adhere strictly to
production standards without broken action tags or missing parameters.
"""

import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent


def test_vercel_json_manifest_validity():
    """Verify vercel.json exists, parses, and defines valid Python WSGI serverless routing."""
    vercel_path = ROOT / "vercel.json"
    assert vercel_path.is_file(), "vercel.json manifest is missing from project root"

    content = json.loads(vercel_path.read_text(encoding="utf-8"))
    assert content.get("version") == 2, "vercel.json should specify version 2"
    assert "builds" in content, "vercel.json must define builds section"
    assert "routes" in content, "vercel.json must define routes section"

    builds = content["builds"]
    python_build = next((b for b in builds if b.get("src") == "api/index.py"), None)
    assert python_build is not None, "vercel.json must build api/index.py"
    assert python_build.get("use") == "@vercel/python", "api/index.py must use @vercel/python runtime"

    routes = content["routes"]
    catchall = next((r for r in routes if r.get("dest") == "api/index.py"), None)
    assert catchall is not None, "vercel.json must route requests to api/index.py"


def test_api_serverless_entrypoint_validity():
    """Verify api/index.py and api/requirements.txt are configured for serverless invocation."""
    index_path = ROOT / "api" / "index.py"
    req_path = ROOT / "api" / "requirements.txt"

    assert index_path.is_file(), "api/index.py entrypoint is missing"
    assert req_path.is_file(), "api/requirements.txt is missing"

    index_text = index_path.read_text(encoding="utf-8")
    assert "handler = app" in index_text or "handler" in index_text, "api/index.py must expose WSGI 'handler'"

    req_text = req_path.read_text(encoding="utf-8").lower()
    assert "flask" in req_text, "api/requirements.txt must include flask"
    assert "requests" in req_text, "api/requirements.txt must include requests"
    assert "pyyaml" in req_text, "api/requirements.txt must include pyyaml"


def test_env_example_completeness_and_safety():
    """Verify .env.example contains all required environment keys and no actual credentials."""
    env_example = ROOT / ".env.example"
    assert env_example.is_file(), ".env.example template is missing"

    text = env_example.read_text(encoding="utf-8")

    # Critical variables that must be documented
    required_keys = [
        "GEMINI_API_KEY",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASS",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "AUTH_REQUIRED",
        "GH_TOKEN",
        "GITHUB_REPOSITORY",
    ]
    for key in required_keys:
        assert f"{key}=" in text, f"Required configuration variable '{key}' missing from .env.example"

    # Verify no active live API keys or live credentials accidentally committed
    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            val = val.strip()
            # Ensure values are placeholder patterns
            assert any(
                marker in val.lower()
                for marker in (
                    "your",
                    "paste",
                    "replace",
                    "example",
                    "true",
                    "false",
                    "587",
                    "smtp.gmail.com",
                    "aizasy_paste",
                    "github_pat",
                )
            ), f"Suspected real secret or non-placeholder value in .env.example for {key}: {val}"


def test_github_actions_workflows_action_tags():
    """Verify GitHub Actions workflows use valid official marketplace tags and avoid broken future tags."""
    workflows_dir = ROOT / ".github" / "workflows"
    assert workflows_dir.is_dir(), ".github/workflows directory is missing"

    for yml_file in workflows_dir.glob("*.yml"):
        data = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{yml_file.name} must be a valid YAML dictionary"

        content = yml_file.read_text(encoding="utf-8")

        # actions/checkout: current stable release is v4 (v5 does not exist)
        assert "actions/checkout@v5" not in content, (
            f"{yml_file.name} uses nonexistent 'actions/checkout@v5'; must use stable 'actions/checkout@v4'"
        )
        assert "actions/checkout@v4" in content or "actions/checkout@" in content

        # actions/setup-python: current stable release is v5 (v6 does not exist)
        assert "actions/setup-python@v6" not in content, (
            f"{yml_file.name} uses nonexistent 'actions/setup-python@v6'; must use stable 'actions/setup-python@v5'"
        )

        # Disallow empty workflow files or broken syntax
        assert "jobs:" in content or "jobs" in data
