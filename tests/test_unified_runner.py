"""Automated unit tests for the unified test, quality, type & coverage runner (run_tests.py)."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import run_tests
from run_tests import GateResult, is_module_installed, print_summary_dashboard, run_mypy, run_pytest_and_coverage, run_ruff


def test_is_module_installed():
    """Verify is_module_installed detects existing and non-existing modules."""
    assert is_module_installed("sys") is True
    assert is_module_installed("pytest") is True
    assert is_module_installed("definitely_non_existent_module_xyz_123") is False


def test_run_ruff_success():
    """Verify run_ruff reports PASSED on exit code 0."""
    with patch("run_tests.is_module_installed", return_value=True):
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0)):
            res = run_ruff(fix=False)
            assert res.name == "Ruff Linting"
            assert res.status == "PASSED"
            assert "0 errors" in res.details


def test_run_ruff_failure():
    """Verify run_ruff reports FAILED on non-zero exit code."""
    with patch("run_tests.is_module_installed", return_value=True):
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=1)):
            res = run_ruff(fix=True)
            assert res.name == "Ruff Linting"
            assert res.status == "FAILED"
            assert "exit code 1" in res.details


def test_run_ruff_skipped_when_not_installed():
    """Verify run_ruff reports SKIPPED when ruff is not installed."""
    with patch("run_tests.is_module_installed", return_value=False):
        res = run_ruff()
        assert res.name == "Ruff Linting"
        assert res.status == "SKIPPED"


def test_run_mypy_success():
    """Verify run_mypy reports PASSED on exit code 0."""
    with patch("run_tests.is_module_installed", return_value=True):
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0)):
            res = run_mypy()
            assert res.name == "Mypy Typing"
            assert res.status == "PASSED"
            assert "0 type errors" in res.details


def test_run_mypy_failure():
    """Verify run_mypy reports FAILED on non-zero exit code."""
    with patch("run_tests.is_module_installed", return_value=True):
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=2)):
            res = run_mypy()
            assert res.name == "Mypy Typing"
            assert res.status == "FAILED"
            assert "exit code 2" in res.details


def test_run_mypy_skipped_when_not_installed():
    """Verify run_mypy reports SKIPPED when mypy is not installed."""
    with patch("run_tests.is_module_installed", return_value=False):
        res = run_mypy()
        assert res.name == "Mypy Typing"
        assert res.status == "SKIPPED"


def test_run_pytest_and_coverage_success():
    """Verify run_pytest_and_coverage handles test suite and coverage reporting."""
    with patch("run_tests.is_module_installed", side_effect=lambda mod: mod in ("pytest", "pytest_cov")):
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0)) as mock_run:
            py_res, cov_res = run_pytest_and_coverage(
                extra_pytest_args=["-k", "unit"],
                with_coverage=True,
                fail_under=90,
                html_report=True,
                xml_report=True,
            )
            assert py_res.status == "PASSED"
            assert cov_res.status == "PASSED"
            mock_run.assert_called_once()
            called_cmd = mock_run.call_args[0][0]
            assert "--cov=jobhunt" in called_cmd
            assert "--cov-fail-under=90" in called_cmd
            assert "--cov-report=html:htmlcov" in called_cmd
            assert "--cov-report=xml:coverage.xml" in called_cmd
            assert "-k" in called_cmd


def test_run_pytest_and_coverage_without_cov():
    """Verify run_pytest_and_coverage skips coverage when with_coverage is False."""
    with patch("run_tests.is_module_installed", return_value=True):
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=0)):
            py_res, cov_res = run_pytest_and_coverage(
                extra_pytest_args=[],
                with_coverage=False,
            )
            assert py_res.status == "PASSED"
            assert cov_res.status == "SKIPPED"


def test_run_pytest_and_coverage_pytest_missing():
    """Verify run_pytest_and_coverage handles missing pytest."""
    with patch("run_tests.is_module_installed", return_value=False):
        py_res, cov_res = run_pytest_and_coverage(extra_pytest_args=[])
        assert py_res.status == "FAILED"
        assert cov_res.status == "SKIPPED"


def test_run_pytest_and_coverage_failure():
    """Verify run_pytest_and_coverage captures failure returncode."""
    with patch("run_tests.is_module_installed", return_value=True):
        with patch("subprocess.run", return_value=subprocess.CompletedProcess(args=[], returncode=1)):
            py_res, cov_res = run_pytest_and_coverage(extra_pytest_args=[])
            assert py_res.status == "FAILED"
            assert cov_res.status == "FAILED"


def test_print_summary_dashboard_all_passed():
    """Verify dashboard returns exit code 0 when all gates pass."""
    results = [
        GateResult("Ruff Linting", "PASSED", 0.5, "0 errors"),
        GateResult("Mypy Typing", "PASSED", 1.2, "0 errors"),
        GateResult("Pytest Suite", "PASSED", 10.0, "All passed"),
        GateResult("Code Coverage", "PASSED", 10.0, "Coverage 92%"),
    ]
    code = print_summary_dashboard(results, 21.7)
    assert code == 0


def test_print_summary_dashboard_with_failures():
    """Verify dashboard returns exit code 1 when any gate fails."""
    results = [
        GateResult("Ruff Linting", "PASSED", 0.5, "0 errors"),
        GateResult("Mypy Typing", "FAILED", 1.2, "exit code 1"),
    ]
    code = print_summary_dashboard(results, 1.7)
    assert code == 1


def test_main_cli_routing():
    """Verify main() CLI flags correctly route to targeted gates."""
    with patch("run_tests.run_ruff", return_value=GateResult("Ruff Linting", "PASSED", 0.1)) as m_ruff:
        with patch("sys.argv", ["run_tests.py", "--ruff-only"]):
            code = run_tests.main()
            assert code == 0
            m_ruff.assert_called_once()

    with patch("run_tests.run_mypy", return_value=GateResult("Mypy Typing", "PASSED", 0.1)) as m_mypy:
        with patch("sys.argv", ["run_tests.py", "--mypy-only"]):
            code = run_tests.main()
            assert code == 0
            m_mypy.assert_called_once()

    with patch("run_tests.run_ruff", return_value=GateResult("Ruff Linting", "PASSED", 0.1)) as m_ruff:
        with patch("run_tests.run_mypy", return_value=GateResult("Mypy Typing", "PASSED", 0.1)) as m_mypy:
            with patch("sys.argv", ["run_tests.py", "--lint-only"]):
                code = run_tests.main()
                assert code == 0
                m_ruff.assert_called_once()
                m_mypy.assert_called_once()
