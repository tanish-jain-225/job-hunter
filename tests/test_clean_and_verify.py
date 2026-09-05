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

    stale_seen_1 = tmp_path / "seen_123456.json"
    stale_seen_1.write_text("{}", encoding="utf-8")

    stale_seen_2 = tmp_path / "seen_test_cli.json"
    stale_seen_2.write_text("{}", encoding="utf-8")

    tmp_file = tmp_path / "test.tmp"
    tmp_file.write_text("data", encoding="utf-8")

    cleanables = find_cleanable_files(tmp_path)
    cleanable_names = [p.name for p in cleanables]

    assert "seen.json" not in cleanable_names
    assert ".env" not in cleanable_names
    assert "seen_123456.json" in cleanable_names
    assert "seen_test_cli.json" in cleanable_names
    assert "test.tmp" in cleanable_names

    # Test dry run
    removed, freed = clean_workspace(tmp_path, dry_run=True)
    assert len(removed) == 3
    assert stale_seen_1.exists()

    # Test actual cleanup
    removed_real, freed_real = clean_workspace(tmp_path, dry_run=False)
    assert len(removed_real) == 3
    assert freed_real > 0
    assert not stale_seen_1.exists()
    assert not stale_seen_2.exists()
    assert protected_seen.exists()
    assert protected_env.exists()


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

    assert audit_company_boards([{"ats": "greenhouse"}, "not a company"])["total"] == 1


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
