"""Unit tests for jobhunt.cli commands and environment/config loading."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import pytest
from jobhunt import cli, providers
from jobhunt.fetch import Job
from jobhunt.providers import LLMError, Provider


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


def test_cfg_fallback_example(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "config.example.yaml").write_text("seen_file: seen.json\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    cfg = cli._cfg(None)
    assert cfg.get("seen_file") == "seen.json"


def test_load_profile_fallback_sample(tmp_path: Path):
    cfg = {"profile_file": str(tmp_path / "nonexistent_profile.json")}
    profile = cli._load_profile(cfg)
    assert profile is not None
    assert "core_skills" in profile or "name" in profile


def test_load_profile_missing_both(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    cfg = {"profile_file": str(tmp_path / "nonexistent_profile.json")}
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        cli._load_profile(cfg)


def test_fetch_jobs_real(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli, "fetch_all", lambda file, max_workers: [Job("1", "gh", "Acme", "Dev", "remote", "http://x", "desc")])
    args = argparse.Namespace(mock=False)
    cfg = {"companies_file": "companies.yaml", "filters": {}}
    raw, cand = cli._fetch_jobs(args, cfg)
    assert len(raw) == 1
    assert len(cand) == 1


def test_screen_jobs_llm_flow(monkeypatch: pytest.MonkeyPatch):
    dummy_prov = Provider()
    monkeypatch.setattr(cli, "resolve", lambda stage: (dummy_prov, "test-model"))

    called = []
    def mock_screen(jobs, profile, **kwargs):
        called.append(True)
        for j in jobs:
            j.score = 9.0

    monkeypatch.setattr(cli.llm, "screen", mock_screen)
    jobs = [Job("1", "gh", "Acme", "Dev", "remote", "http://x", "desc")]
    args = argparse.Namespace(scorer="llm")
    cfg: dict[str, Any] = {}
    cli._screen_jobs(jobs, {}, args, cfg)
    assert called == [True]


def test_screen_jobs_llm_fallback_to_keyword(monkeypatch: pytest.MonkeyPatch):
    dummy_prov = Provider()
    monkeypatch.setattr(cli, "resolve", lambda stage: (dummy_prov, "test-model"))

    def mock_screen(jobs, profile, **kwargs):
        pass  # Leaves job.score = None

    monkeypatch.setattr(cli.llm, "screen", mock_screen)
    jobs = [Job("1", "gh", "Acme", "Software Engineer", "remote", "http://x", "desc")]
    args = argparse.Namespace(scorer="llm")
    cfg: dict[str, Any] = {}
    cli._screen_jobs(jobs, {"target_roles": ["Software Engineer"]}, args, cfg)
    assert jobs[0].score is not None


def test_screen_jobs_llm_resolve_error(monkeypatch: pytest.MonkeyPatch):
    def mock_resolve(stage):
        raise LLMError("No API key")
    monkeypatch.setattr(cli, "resolve", mock_resolve)
    jobs = [Job("1", "gh", "Acme", "Dev", "remote", "http://x", "desc")]
    args = argparse.Namespace(scorer="llm")
    with pytest.raises(LLMError):
        cli._screen_jobs(jobs, {}, args, {})


def test_select_shortlist_unscored():
    jobs = [
        Job("1", "gh", "Acme", "Dev 1", "remote", "http://x", "desc"),
        Job("2", "gh", "Acme", "Dev 2", "remote", "http://x", "desc"),
    ]
    jobs[0].score = 8.0
    jobs[1].score = None
    cfg = {"score_threshold": 7.0, "max_per_digest": 5}
    scored, shortlist = cli._select_shortlist(jobs, cfg)
    assert len(scored) == 1
    assert len(shortlist) == 1


def test_draft_kits_llm_and_error(monkeypatch: pytest.MonkeyPatch):
    dummy_prov = Provider()
    monkeypatch.setattr(cli, "resolve", lambda stage: (dummy_prov, "test-model"))

    def mock_draft(jobs, profile, **kwargs):
        pass
    monkeypatch.setattr(cli.llm, "draft", mock_draft)

    shortlist = [Job("1", "gh", "Acme", "Dev", "remote", "http://x", "desc")]
    cli._draft_kits(shortlist, {}, "llm", {})

    def mock_resolve_error(stage):
        raise LLMError("Draft key missing")
    monkeypatch.setattr(cli, "resolve", mock_resolve_error)
    cli._draft_kits(shortlist, {}, "llm", {})


def test_build_and_send_digest_with_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    sent = []
    monkeypatch.setattr(cli.mailer, "send", lambda subj, body: sent.append(subj))
    monkeypatch.chdir(tmp_path)

    from jobhunt.store import Store
    st = Store(tmp_path / "seen.json")
    args = argparse.Namespace(send=True)
    cfg = {"digest_file": str(tmp_path / "out" / "digest.html"), "tracker_csv": str(tmp_path / "out" / "tracker.csv")}

    cli._build_and_send_digest([], [], [], [], st, args, cfg)
    assert len(sent) == 1


def test_cmd_run_no_jobs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "profile.json").write_text(json.dumps({"name": "Test User"}), encoding="utf-8")
    (tmp_path / "config.yaml").write_text(f"seen_file: {(tmp_path / 'seen.json').as_posix()}\n", encoding="utf-8")
    (tmp_path / "seen.json").write_text(json.dumps({"1": {"title": "Dev", "applied": False}}), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_fetch_jobs", lambda args, cfg: ([], [Job("1", "gh", "Acme", "Dev", "remote", "http://x", "desc")]))

    args = argparse.Namespace(config=None, mock=True, scorer="keyword", send=False)
    assert cli.cmd_run(args) == 0


def test_cmd_run_llm_error_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "profile.json").write_text(json.dumps({"name": "Test User"}), encoding="utf-8")
    (tmp_path / "config.yaml").write_text(f"seen_file: {(tmp_path / 'seen.json').as_posix()}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def mock_screen_error(jobs, profile, args, cfg):
        raise LLMError("API Error")
    monkeypatch.setattr(cli, "_screen_jobs", mock_screen_error)
    monkeypatch.setattr(cli, "_fetch_jobs", lambda args, cfg: ([Job("1", "gh", "Acme", "Dev", "remote", "http://x", "desc")], [Job("1", "gh", "Acme", "Dev", "remote", "http://x", "desc")]))

    args = argparse.Namespace(config=None, mock=True, scorer="llm", send=False)
    assert cli.cmd_run(args) == 1


def test_cmd_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    seen_file = tmp_path / "seen.json"
    seen_file.write_text(json.dumps({
        "greenhouse:acme:1": {"title": "Engineer", "applied": False}
    }), encoding="utf-8")

    config_file = tmp_path / "config.yaml"
    config_file.write_text(f"seen_file: {seen_file.as_posix()}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    args = argparse.Namespace(job_id="greenhouse:acme:1")
    assert cli.cmd_applied(args) == 0

    args_invalid = argparse.Namespace(job_id="unknown_id")
    assert cli.cmd_applied(args_invalid) == 1


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
    assert cli.cmd_stats(args) == 0
    captured = capsys.readouterr().out
    assert "Total tracked jobs: 1" in captured


def test_cmd_profile_llm_resolve_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    resume_file = tmp_path / "resume.txt"
    resume_file.write_text("Resume text", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def mock_resolve_err(stage):
        raise LLMError("Resolution error")
    monkeypatch.setattr(cli, "resolve", mock_resolve_err)

    args = argparse.Namespace(resume=str(resume_file), yaml=False)
    with pytest.raises(SystemExit, match="Error resolving LLM provider"):
        cli.cmd_profile(args)


def test_main_cli_routing_all(monkeypatch: pytest.MonkeyPatch):
    for cmd in ["run", "applied", "stats", "profile"]:
        called: list[str] = []
        def _mock_cmd(args, c=cmd):
            called.append(c)
            return 0
        monkeypatch.setattr(cli, f"cmd_{cmd}", _mock_cmd)
        argv = ["jobhunt", cmd]
        if cmd == "applied":
            argv.append("greenhouse:acme:1")
        elif cmd == "profile":
            argv.extend(["--resume", "resume.txt"])

        monkeypatch.setattr("sys.argv", argv)
        with pytest.raises(SystemExit) as exc_info:
            cli.main()
        assert exc_info.value.code == 0
        assert called == [cmd]


def test_cmd_profile_success_and_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    resume_file = tmp_path / "resume.txt"
    resume_file.write_text("Tanish Sanghvi Software Engineer Resume", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    mock_provider = providers.GroqProvider()
    monkeypatch.setattr(cli, "resolve", lambda stage: (mock_provider, "llama-3.3-70b"))
    monkeypatch.setattr(cli.llm, "build_profile", lambda **kw: {"name": "Tanish", "seniority": "intern"})

    args = argparse.Namespace(resume=str(resume_file), yaml=True)
    assert cli.cmd_profile(args) == 0
    assert (tmp_path / "profile.json").exists()


def test_cmd_profile_missing_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    args = argparse.Namespace(resume="nonexistent_resume.pdf", yaml=False)
    with pytest.raises(SystemExit, match="resume file nonexistent_resume.pdf not found"):
        cli.cmd_profile(args)


def test_cmd_run_no_jobs_with_send(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "profile.json").write_text(json.dumps({"name": "Test User"}), encoding="utf-8")
    (tmp_path / "config.yaml").write_text(f"seen_file: {(tmp_path / 'seen.json').as_posix()}\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_fetch_jobs", lambda args, cfg: ([], []))

    sent = []
    monkeypatch.setattr(cli.mailer, "send", lambda subj, body: sent.append(subj))

    args = argparse.Namespace(config=None, mock=True, scorer="keyword", send=True)
    assert cli.cmd_run(args) == 0
    assert len(sent) == 1


def test_cfg_and_profile_error_handling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)

    # _cfg non-existent with raise_on_error=False
    res_cfg = cli._cfg("nonexistent.yaml", raise_on_error=False)
    assert res_cfg == {}

    # _cfg invalid yaml
    bad_cfg = tmp_path / "bad_config.yaml"
    bad_cfg.write_text(":\n  - : : invalid yaml", encoding="utf-8")
    res_bad = cli._cfg(str(bad_cfg), raise_on_error=False)
    assert res_bad == {}

    with pytest.raises(SystemExit):
        cli._cfg(str(bad_cfg), raise_on_error=True)

    # _load_profile missing with raise_on_error=False
    res_prof = cli._load_profile({"profile_file": "missing.json"}, raise_on_error=False)
    assert res_prof == {}

    # _load_profile invalid format
    bad_prof = tmp_path / "bad_profile.json"
    bad_prof.write_text(":\n  - : : invalid format", encoding="utf-8")
    res_bad_prof = cli._load_profile({"profile_file": str(bad_prof)}, raise_on_error=False)
    assert res_bad_prof == {}

    with pytest.raises(SystemExit):
        cli._load_profile({"profile_file": str(bad_prof)}, raise_on_error=True)


def test_resolve_relative_vercel(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("VERCEL", "1")
    rel_path = cli._resolve_relative("config.example.yaml")
    assert rel_path is not None


def test_screen_jobs_keyword_scorer():
    jobs = [Job("1", "gh", "Acme", "Software Engineer", "remote", "http://x", "Python")]
    args = argparse.Namespace(scorer="keyword")
    cli._screen_jobs(jobs, {"core_skills": ["Python"]}, args, {})
    assert jobs[0].score is not None


def test_cmd_run_full_pipeline_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "profile.json").write_text(json.dumps({"name": "Test User", "core_skills": ["Go"]}), encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        f"seen_file: {(tmp_path / 'seen.json').as_posix()}\n"
        f"digest_file: {(tmp_path / 'out' / 'digest.html').as_posix()}\n"
        f"tracker_csv: {(tmp_path / 'out' / 'tracker.csv').as_posix()}\n"
        f"score_threshold: 6.0\n"
        f"max_per_digest: 5\n"
        f"screen_batch_size: 5\n",
        encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    # Use mock ATS data and keyword scorer
    args = argparse.Namespace(config=None, mock=True, scorer="keyword", send=False)
    exit_code = cli.cmd_run(args)
    assert exit_code == 0
    assert (tmp_path / "out" / "digest.html").exists()
    assert (tmp_path / "seen.json").exists()
    assert (tmp_path / "out" / "tracker.csv").exists()




