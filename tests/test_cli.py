"""Unit tests for jobhunt.cli commands and environment/config loading."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pytest
from jobhunt import cli


def test_load_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_VAR_JOBHUNT=hello_world\n# Comment\nFOO=bar\n", encoding="utf-8")
    monkeypatch.delenv("TEST_VAR_JOBHUNT", raising=False)
    monkeypatch.delenv("FOO", raising=False)
    monkeypatch.chdir(tmp_path)

    cli._load_env()
    assert os.environ.get("TEST_VAR_JOBHUNT") == "hello_world"
    assert os.environ.get("FOO") == "bar"


def test_cfg_raises_on_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        cli._cfg()


def test_load_profile_fallback_sample(tmp_path: Path):
    cfg = {"profile_file": str(tmp_path / "nonexistent_profile.json")}
    profile = cli._load_profile(cfg)
    assert profile is not None
    assert "core_skills" in profile or "name" in profile


def test_cmd_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    seen_file = tmp_path / "seen.json"
    seen_file.write_text(json.dumps({
        "greenhouse:acme:1": {"title": "Engineer", "applied": False}
    }), encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"seen_file: {seen_file.as_posix()}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(job_id="greenhouse:acme:1")
    exit_code = cli.cmd_applied(args)
    assert exit_code == 0

    updated = json.loads(seen_file.read_text(encoding="utf-8"))
    assert updated["greenhouse:acme:1"]["applied"] is True


def test_cmd_stats(tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch):
    seen_file = tmp_path / "seen.json"
    seen_file.write_text(json.dumps({
        "greenhouse:acme:1": {"title": "Engineer", "applied": True}
    }), encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"seen_file: {seen_file.as_posix()}\n",
        encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace()
    exit_code = cli.cmd_stats(args)
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert "Total tracked jobs: 1" in captured
    assert "Total applied: 1" in captured


def test_cmd_run_mock_keyword(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    seen_file = tmp_path / "seen.json"
    digest_file = tmp_path / "out" / "digest.html"
    config_file = tmp_path / "config.yaml"
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps({"name": "Test User", "target_roles": ["Engineer"]}), encoding="utf-8")
    config_file.write_text(
        f"seen_file: {seen_file.as_posix()}\n"
        f"digest_file: {digest_file.as_posix()}\n"
        f"profile_file: {profile_file.as_posix()}\n"
        f"filters:\n  include_titles: ['.*']\n",
        encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(
        mock=True,
        scorer="keyword",
        send=False,
    )

    exit_code = cli.cmd_run(args)
    assert exit_code == 0
    assert digest_file.exists()


def test_cmd_run_custom_config_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    custom_cfg = tmp_path / "custom_config.yaml"
    seen_file = tmp_path / "seen.json"
    digest_file = tmp_path / "out" / "custom_digest.html"
    profile_file = tmp_path / "profile.json"
    profile_file.write_text(json.dumps({"name": "Custom User"}), encoding="utf-8")
    custom_cfg.write_text(
        f"seen_file: {seen_file.as_posix()}\n"
        f"digest_file: {digest_file.as_posix()}\n"
        f"profile_file: {profile_file.as_posix()}\n",
        encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(
        config=str(custom_cfg),
        mock=True,
        scorer="keyword",
        send=False,
    )
    assert cli.cmd_run(args) == 0
    assert digest_file.exists()


def test_cmd_profile_missing_file(tmp_path: Path):
    args = argparse.Namespace(resume=str(tmp_path / "nonexistent.pdf"), yaml=False)
    with pytest.raises(SystemExit, match="resume file .* not found"):
        cli.cmd_profile(args)


def test_cmd_profile_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    resume_file = tmp_path / "resume.txt"
    resume_file.write_text("Experienced Engineer with Python skills.", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def mock_build_profile(*args, **kwargs):
        return {"name": "Jane Doe", "core_skills": ["Python"]}

    monkeypatch.setattr(cli.llm, "build_profile", mock_build_profile)
    from jobhunt.providers import Provider
    monkeypatch.setattr(cli, "resolve", lambda stage: (Provider(), "mock-model"))

    args = argparse.Namespace(resume=str(resume_file), yaml=False)
    assert cli.cmd_profile(args) == 0
    assert (tmp_path / "profile.json").exists()


def test_main_cli_routing(monkeypatch: pytest.MonkeyPatch):
    calls = []
    monkeypatch.setattr(cli, "cmd_stats", lambda args: calls.append("stats") or 0)
    monkeypatch.setattr("sys.argv", ["jobhunt", "stats"])

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 0
    assert calls == ["stats"]
