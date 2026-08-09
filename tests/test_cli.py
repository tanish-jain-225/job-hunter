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
    assert updated["greenhouse:acme:1"]["status"] == "applied"


def test_cmd_stats(tmp_path: Path, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch):
    seen_file = tmp_path / "seen.json"
    seen_file.write_text(json.dumps({
        "greenhouse:acme:1": {"title": "Engineer", "status": "applied"}
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
    config_file.write_text(
        f"seen_file: {seen_file.as_posix()}\n"
        f"digest_file: {digest_file.as_posix()}\n"
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
