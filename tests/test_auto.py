"""Unit tests for auto.py master automation script."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auto
from jobhunt import cli


def test_auto_with_existing_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When profile.json exists, auto.py skips generation and runs pipeline."""
    monkeypatch.setattr(auto, "ROOT", tmp_path)
    (tmp_path / "profile.json").write_text('{"name": "Test"}', encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        f"seen_file: {(tmp_path / 'seen.json').as_posix()}\n"
        f"digest_file: {(tmp_path / 'out' / 'digest.html').as_posix()}\n"
        f"profile_file: {(tmp_path / 'profile.json').as_posix()}\n"
        f"filters:\n  include_titles: ['.*']\n",
        encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SMTP_PASS", raising=False)

    def mock_cmd_run(args: argparse.Namespace) -> int:
        return 0

    monkeypatch.setattr(cli, "cmd_run", mock_cmd_run)

    with patch.object(auto, "webbrowser", create=True) as mock_wb:
        mock_wb.open = lambda *a: None
        exit_code = auto.main()

    assert exit_code == 0


def test_auto_fallback_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When first cmd_run fails, auto.py falls back to keyword scorer."""
    monkeypatch.setattr(auto, "ROOT", tmp_path)
    (tmp_path / "profile.json").write_text('{"name": "Test"}', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SMTP_PASS", raising=False)

    call_count = [0]
    def mock_cmd_run(args: argparse.Namespace) -> int:
        call_count[0] += 1
        if call_count[0] == 1:
            return 1  # First call fails
        return 0      # Fallback succeeds

    monkeypatch.setattr(cli, "cmd_run", mock_cmd_run)

    with patch.object(auto, "webbrowser", create=True) as mock_wb:
        mock_wb.open = lambda *a: None
        exit_code = auto.main()

    assert exit_code == 0
    assert call_count[0] == 2  # Called twice: initial + fallback


def test_auto_no_profile_no_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """When neither profile.json nor resume.pdf exists, auto prints a warning."""
    monkeypatch.setattr(auto, "ROOT", tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SMTP_PASS", raising=False)

    monkeypatch.setattr(cli, "cmd_run", lambda args: 0)

    with patch.object(auto, "webbrowser", create=True) as mock_wb:
        mock_wb.open = lambda *a: None
        auto.main()

    out = capsys.readouterr().out
    assert "Warning" in out


def test_auto_profile_from_resume_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When resume.pdf exists and profile.json does not, auto.py generates profile."""
    monkeypatch.setattr(auto, "ROOT", tmp_path)
    (tmp_path / "resume.pdf").write_bytes(b"%PDF-1.4...")
    (tmp_path / "out").mkdir(parents=True, exist_ok=True)
    (tmp_path / "out" / "digest.html").write_text("<p>digest</p>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_gemini_key")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("CI", raising=False)

    called_profile = []
    def mock_cmd_profile(args):
        called_profile.append(True)
        (tmp_path / "profile.json").write_text('{"name": "Auto"}', encoding="utf-8")
        return 0

    monkeypatch.setattr(cli, "cmd_profile", mock_cmd_profile)
    monkeypatch.setattr(cli, "cmd_run", lambda args: 0)

    opened = []
    with patch.object(auto.webbrowser, "open", lambda url: opened.append(url)):
        exit_code = auto.main()

    assert exit_code == 0
    assert called_profile == [True]
    assert len(opened) == 1


def test_auto_profile_generation_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """When cmd_profile raises error during auto run, it logs warning and continues."""
    monkeypatch.setattr(auto, "ROOT", tmp_path)
    (tmp_path / "resume.pdf").write_bytes(b"%PDF-1.4...")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SMTP_PASS", raising=False)

    def mock_cmd_profile_err(args):
        raise RuntimeError("PDF parse failure")

    monkeypatch.setattr(cli, "cmd_profile", mock_cmd_profile_err)
    monkeypatch.setattr(cli, "cmd_run", lambda args: 0)

    with patch.object(auto, "webbrowser", create=True) as mock_wb:
        mock_wb.open = lambda *a: None
        auto.main()

    out = capsys.readouterr().out
    assert "Profile generation error" in out


def test_auto_browser_open_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When webbrowser.open raises exception, auto.py suppresses it and finishes."""
    monkeypatch.setattr(auto, "ROOT", tmp_path)
    (tmp_path / "profile.json").write_text('{"name": "Auto"}', encoding="utf-8")
    (tmp_path / "out").mkdir(parents=True, exist_ok=True)
    (tmp_path / "out" / "digest.html").write_text("<p>digest</p>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(cli, "cmd_run", lambda args: 0)

    def mock_open_err(url):
        raise OSError("No browser available")

    with patch.object(auto.webbrowser, "open", mock_open_err):
        exit_code = auto.main()
    assert exit_code == 0


