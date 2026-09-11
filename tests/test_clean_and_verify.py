"""Tests for workspace cleanup (jobhunt clean) and company board verifier (jobhunt verify)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


from jobhunt.clean import find_cleanable_files, clean_workspace
from jobhunt.verify import check_single_board, audit_company_boards
from jobhunt import cli


def test_find_cleanable_files_and_clean_workspace(tmp_path: Path):
    # Create sample files in tmp_path
    protected_seen = tmp_path / "seen.json"
    protected_seen.write_text("{}", encoding="utf-8")

    protected_env = tmp_path / ".env"
    protected_env.write_text("GEMINI_API_KEY=test", encoding="utf-8")

    protected_profile = tmp_path / "profile.json"
    protected_profile.write_text("{}", encoding="utf-8")

    protected_profile_ex = tmp_path / "profile.example.json"
    protected_profile_ex.write_text("{}", encoding="utf-8")

    stale_seen_1 = tmp_path / "seen_123456.json"
    stale_seen_1.write_text("{}", encoding="utf-8")

    stale_seen_2 = tmp_path / "seen_test_cli.json"
    stale_seen_2.write_text("{}", encoding="utf-8")

    stale_profile = tmp_path / "profile_255921b9d80f.json"
    stale_profile.write_text("{}", encoding="utf-8")

    coverage_file = tmp_path / ".coverage"
    coverage_file.write_text("cov", encoding="utf-8")

    tmp_file = tmp_path / "test.tmp"
    tmp_file.write_text("data", encoding="utf-8")

    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    protected_tracker = out_dir / "tracker.csv"
    protected_tracker.write_text("id\n", encoding="utf-8")
    stale_tracker = out_dir / "tracker_123.csv"
    stale_tracker.write_text("id\n", encoding="utf-8")
    stale_tmp_tracker = out_dir / ".tracker-abc123.csv"
    stale_tmp_tracker.write_text("id\n", encoding="utf-8")

    cleanables = find_cleanable_files(tmp_path)
    cleanable_names = [p.name for p in cleanables]

    assert "seen.json" not in cleanable_names
    assert ".env" not in cleanable_names
    assert "profile.json" not in cleanable_names
    assert "profile.example.json" not in cleanable_names
    assert "tracker.csv" not in cleanable_names

    assert "seen_123456.json" in cleanable_names
    assert "seen_test_cli.json" in cleanable_names
    assert "profile_255921b9d80f.json" in cleanable_names
    assert ".coverage" in cleanable_names
    assert "test.tmp" in cleanable_names
    assert "tracker_123.csv" in cleanable_names
    assert ".tracker-abc123.csv" in cleanable_names

    # Test dry run
    removed, freed = clean_workspace(tmp_path, dry_run=True)
    assert len(removed) == 7
    assert stale_seen_1.exists()
    assert stale_profile.exists()
    assert stale_tracker.exists()

    # Test actual cleanup
    removed_real, freed_real = clean_workspace(tmp_path, dry_run=False)
    assert len(removed_real) == 7
    assert freed_real > 0
    assert not stale_seen_1.exists()
    assert not stale_seen_2.exists()
    assert not stale_profile.exists()
    assert not coverage_file.exists()
    assert not stale_tracker.exists()
    assert not stale_tmp_tracker.exists()

    assert protected_seen.exists()
    assert protected_env.exists()
    assert protected_profile.exists()
    assert protected_profile_ex.exists()
    assert protected_tracker.exists()


def test_verify_check_single_board():
    c_valid = {"ats": "greenhouse", "slug": "stripe", "name": "Stripe"}
    c_unknown = {"ats": "nonexistent_ats", "slug": "test"}

    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_sess = MagicMock()
    mock_sess.get.return_value = mock_resp

    c, ok, status = check_single_board(c_valid, session=mock_sess)
    assert ok is True
    assert status == 200

    c2, ok2, status2 = check_single_board(c_unknown, session=mock_sess)
    assert ok2 is False
    assert status2 == "Unknown ATS"

    c3, ok3, status3 = check_single_board({"ats": "greenhouse", "slug": "   "}, session=mock_sess)
    assert ok3 is False
    assert status3 == "Missing company slug"


def test_verify_check_single_board_failure_paths():
    c_invalid = {"ats": "greenhouse", "slug": "stripe", "name": "Stripe"}

    non_200_session = MagicMock()
    non_200_session.get.return_value.status_code = 503
    _, ok, status = check_single_board(c_invalid, session=non_200_session)
    assert ok is False
    assert status == 503

    error_session = MagicMock()
    error_session.get.side_effect = RuntimeError("connection failure while checking board")
    _, ok, status = check_single_board(c_invalid, session=error_session)
    assert ok is False
    assert status == "connection failure while checking board"


def test_audit_company_boards(tmp_path: Path):
    comp_file = tmp_path / "companies.yaml"
    comp_file.write_text(
        """
companies:
  - {ats: greenhouse, slug: stripe, name: Stripe}
  - {ats: lever, slug: meesho, name: Meesho}
""",
        encoding="utf-8",
    )

    with patch("jobhunt.verify.check_single_board") as mock_check:
        mock_check.side_effect = [
            ({"ats": "greenhouse", "slug": "stripe"}, True, 200),
            ({"ats": "lever", "slug": "meesho"}, False, 404),
        ]
        res = audit_company_boards(comp_file, max_workers=2)
        assert res["total"] == 2
        assert res["valid_count"] == 1
        assert res["invalid_count"] == 1


def test_audit_company_boards_empty_and_invalid_files(tmp_path: Path):
    missing = tmp_path / "missing.yaml"
    assert audit_company_boards(missing)["total"] == 0

    malformed = tmp_path / "malformed.yaml"
    malformed.write_text("companies: [", encoding="utf-8")
    assert audit_company_boards(malformed)["total"] == 0

    non_mapping = tmp_path / "list.yaml"
    non_mapping.write_text("- one\n- two\n", encoding="utf-8")
    list_result = audit_company_boards(non_mapping)
    assert list_result["total"] == 2
    assert list_result["invalid_count"] == 0

    assert audit_company_boards([{"ats": "greenhouse"}, "not a company"])["total"] == 1  # type: ignore[list-item]


def test_cli_clean_and_verify_commands(capsys):
    with patch("sys.argv", ["jobhunt", "clean", "--dry-run"]):
        with pytest.raises(SystemExit):
            cli.main()
        out = capsys.readouterr().out
        assert "Cleaning temporary" in out

    with patch("jobhunt.verify.audit_company_boards") as mock_audit:
        mock_audit.return_value = {
            "total": 1,
            "valid_count": 1,
            "invalid_count": 0,
            "valid": [({"name": "Test"}, 200)],
            "invalid": [],
        }
        with patch("sys.argv", ["jobhunt", "verify"]):
            with pytest.raises(SystemExit):
                cli.main()
            out = capsys.readouterr().out
            assert "AUDIT RESULTS" in out

    with patch("sys.argv", ["jobhunt", "clean"]), patch("jobhunt.clean.clean_workspace", return_value=([], 0)):
        with pytest.raises(SystemExit):
            cli.main()
        out = capsys.readouterr().out
        assert "Workspace is clean!" in out

    with patch("jobhunt.verify.audit_company_boards") as mock_audit_invalid:
        mock_audit_invalid.return_value = {
            "total": 1,
            "valid_count": 0,
            "invalid_count": 1,
            "valid": [],
            "invalid": [({"ats": "greenhouse", "slug": "broken", "name": "Broken"}, 404)],
        }
        with patch("sys.argv", ["jobhunt", "verify"]):
            with pytest.raises(SystemExit):
                cli.main()
            out = capsys.readouterr().out
            assert "Non-200 / Unreachable entries:" in out


def test_clean_workspace_and_find_cleanable_errors():
    with patch.object(Path, "iterdir", side_effect=PermissionError("Permission denied")):
        cleanables = find_cleanable_files()
        assert cleanables == []

    fake_file = MagicMock(spec=Path)
    fake_file.exists.return_value = True
    fake_file.stat.return_value = MagicMock(st_size=100)
    fake_file.unlink.side_effect = PermissionError("Cannot delete")
    with patch("jobhunt.clean.find_cleanable_files", return_value=[fake_file]):
        removed, freed = clean_workspace(dry_run=False)
        assert removed == []
        assert freed == 0


def test_audit_company_boards_default_none():
    with patch("jobhunt.verify.Path.is_file", return_value=False):
        res = audit_company_boards(None)
        assert res["total"] == 0
