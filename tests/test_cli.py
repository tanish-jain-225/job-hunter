"""Unit tests for jobhunt.cli commands and environment/config loading."""
from __future__ import annotations

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

    cli._load_env(str(env_file))
    assert os.environ.get("TEST_VAR_JOBHUNT") == "hello_world"
    assert os.environ.get("FOO") == "bar"


def test_cfg_raises_on_missing(tmp_path: Path):
    with pytest.raises(SystemExit):
        cli._cfg(tmp_path / "nonexistent.yaml")


def test_load_profile_fallback_sample(tmp_path: Path):
    cfg = {"profile_file": str(tmp_path / "profile.json")}
    # Allow sample should return sample profile if profile.json does not exist
    profile = cli._load_profile(cfg, allow_sample=True)
    assert profile is not None
    assert "core_skills" in profile or "name" in profile


def test_cmd_applied(tmp_path: Path):
    seen_file = tmp_path / "seen.json"
    seen_file.write_text(json.dumps({
        "greenhouse:acme:1": {"title": "Engineer", "applied": False}
    }), encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"seen_file: {seen_file.as_posix()}\n", encoding="utf-8")

    args = cli.argparse.Namespace(config=str(config_file), job_id="greenhouse:acme:1")
    exit_code = cli.cmd_applied(args)
    assert exit_code == 0

    updated = json.loads(seen_file.read_text(encoding="utf-8"))
    assert updated["greenhouse:acme:1"]["applied"] is True


def test_cmd_stats(tmp_path: Path, capsys: pytest.CaptureFixture):
    seen_file = tmp_path / "seen.json"
    seen_file.write_text(json.dumps({
        "greenhouse:acme:1": {"emailed": True, "applied": True}
    }), encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    tracker_csv = tmp_path / "out" / "tracker.csv"
    config_file.write_text(
        f"seen_file: {seen_file.as_posix()}\ntracker_csv: {tracker_csv.as_posix()}\n",
        encoding="utf-8"
    )

    args = cli.argparse.Namespace(config=str(config_file))
    exit_code = cli.cmd_stats(args)
    assert exit_code == 0
    captured = capsys.readouterr().out
    assert '"tracked": 1' in captured
    assert tracker_csv.exists()


def test_cmd_run_mock_keyword(tmp_path: Path):
    seen_file = tmp_path / "seen.json"
    digest_file = tmp_path / "out" / "digest.html"
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        f"seen_file: {seen_file.as_posix()}\n"
        f"digest_file: {digest_file.as_posix()}\n"
        f"filters:\n  include_titles: ['.*']\n",
        encoding="utf-8"
    )

    args = cli.argparse.Namespace(
        config=str(config_file),
        mock=True,
        scorer="keyword",
        no_draft=True,
        send=False,
        limit=5,
    )

    exit_code = cli.cmd_run(args)
    assert exit_code == 0
    assert digest_file.exists()
