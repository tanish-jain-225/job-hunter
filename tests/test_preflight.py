"""Comprehensive tests for jobhunt.preflight diagnostics."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

from jobhunt.preflight import run_preflight_checks


def test_preflight_all_healthy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify preflight passes all checks when environment and files are pristine."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("llm:\n  provider: gemini\n", encoding="utf-8")
    comp = tmp_path / "companies.yaml"
    comp.write_text("companies:\n  - name: TestCo\n    ats: greenhouse\n", encoding="utf-8")

    monkeypatch.setenv("GEMINI_API_KEY", "test_key")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test_anon")
    monkeypatch.setenv("SMTP_USER", "test@test.com")
    monkeypatch.setenv("SMTP_PASS", "test_pass")

    res = run_preflight_checks(config_path=cfg, companies_path=comp)
    assert res["all_ok"] is True
    assert isinstance(res["checks"], list)
    assert len(res["remediations"]) == 0


def test_preflight_missing_config_with_example_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify missing config falls back to config.example.yaml if present."""
    cfg = tmp_path / "nonexistent_config.yaml"
    example_cfg = tmp_path / "config.example.yaml"
    example_cfg.write_text("llm:\n  provider: gemini\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    res = run_preflight_checks(config_path=cfg)
    cfg_checks = [c for c in res["checks"] if "Configuration File" in c["name"]]
    assert any(c["passed"] for c in cfg_checks)


def test_preflight_corrupt_config_yaml(tmp_path: Path):
    """Verify invalid YAML in config produces a critical failure and remediation."""
    cfg = tmp_path / "corrupt_config.yaml"
    cfg.write_text("llm: [unclosed yaml", encoding="utf-8")

    res = run_preflight_checks(config_path=cfg)
    assert res["all_ok"] is False
    assert any("Fix YAML syntax errors" in r for r in res["remediations"])


def test_preflight_missing_config_and_missing_example(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify missing config without example triggers critical failure."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.chdir(empty_dir)

    res = run_preflight_checks(config_path=empty_dir / "missing.yaml")
    assert res["all_ok"] is False
    assert any("Copy config.example.yaml" in r for r in res["remediations"])


def test_preflight_corrupt_companies_yaml(tmp_path: Path):
    """Verify invalid YAML in companies.yaml produces a non-critical check failure."""
    comp = tmp_path / "corrupt_companies.yaml"
    comp.write_text("companies: [unclosed", encoding="utf-8")

    res = run_preflight_checks(companies_path=comp)
    assert any("Fix YAML syntax errors in" in r for r in res["remediations"])


def test_preflight_missing_companies_file(tmp_path: Path):
    """Verify missing companies.yaml triggers an informational remediation."""
    comp = tmp_path / "missing_companies.yaml"
    res = run_preflight_checks(companies_path=comp)
    assert any("Ensure companies.yaml exists" in r for r in res["remediations"])


def test_preflight_empty_companies_list(tmp_path: Path):
    """Verify companies file with 0 companies triggers notice."""
    comp = tmp_path / "empty_companies.yaml"
    comp.write_text("companies: []\n", encoding="utf-8")

    res = run_preflight_checks(companies_path=comp)
    check = next(c for c in res["checks"] if "Company Targets" in c["name"])
    assert check["passed"] is False


def test_preflight_missing_api_keys_and_services(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify missing optional env vars trigger helpful guidance without failing critical gate."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("llm:\n  provider: gemini\n", encoding="utf-8")
    comp = tmp_path / "companies.yaml"
    comp.write_text("companies:\n  - name: TestCo\n    ats: greenhouse\n", encoding="utf-8")

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)

    res = run_preflight_checks(config_path=cfg, companies_path=comp)
    assert res["all_ok"] is True
    rems = " ".join(res["remediations"])
    assert "GEMINI_API_KEY is not set" in rems
    assert "Supabase cloud sync is disabled" in rems
    assert "SMTP email credentials not set" in rems


def test_preflight_missing_dependency_package(monkeypatch: pytest.MonkeyPatch):
    """Verify missing required core package triggers critical failure."""
    real_import = __import__

    def mock_import(name, *args, **kwargs):
        if name == "flask_limiter":
            raise ImportError("Simulated missing package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("importlib.import_module", mock_import)
    res = run_preflight_checks()
    assert res["all_ok"] is False
    assert any("flask-limiter" in r for r in res["remediations"])


def test_preflight_python_version_check(monkeypatch: pytest.MonkeyPatch):
    """Verify Python < 3.9 triggers critical failure."""
    from collections import namedtuple

    VersionInfo = namedtuple("VersionInfo", ["major", "minor", "micro", "releaselevel", "serial"])
    fake_version = VersionInfo(3, 8, 10, "final", 0)
    monkeypatch.setattr(sys, "version_info", fake_version)

    res = run_preflight_checks()
    assert res["all_ok"] is False
    assert any("Upgrade to Python 3.9+" in r for r in res["remediations"])


def test_preflight_output_directory_permission_failure(monkeypatch: pytest.MonkeyPatch):
    """Verify failure to write to output directory triggers critical check failure."""
    def mock_touch(self, *args, **kwargs):
        raise PermissionError("Simulated write permission denied")

    monkeypatch.setattr(Path, "touch", mock_touch)
    res = run_preflight_checks()
    assert res["all_ok"] is False
    assert any("Ensure local directory permissions" in r for r in res["remediations"])
