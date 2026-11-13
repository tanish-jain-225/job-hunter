"""Job Hunter — Unified All-in-One Quality, Type, Test & Coverage Runner.

Runs every verification gate in one single command:
  1. Code Quality & Linting: Ruff (`ruff check .`)
  2. Static Type Analysis: Mypy (`mypy jobhunt` across all 43 source files)
  3. Full Test Suite: Pytest (all unit, integration, security, and API tests)
  4. Code Coverage Analysis: pytest-cov (`--cov=jobhunt --cov-report=term-missing`)

Usage:
    python run_tests.py                       # Run all 4 gates (Ruff + Mypy + Pytest + Coverage)
    python run_tests.py --tests-only          # Run only Pytest + Coverage (skip lint/type gates)
    python run_tests.py --lint-only           # Run only Ruff linting and Mypy typing
    python run_tests.py --mypy-only           # Run only Mypy static type analysis
    python run_tests.py --ruff-only           # Run only Ruff linter
    python run_tests.py --no-cov              # Run Pytest without coverage report
    python run_tests.py --cov-fail-under=90   # Enforce strict 90%+ code coverage threshold
    python run_tests.py --cov-html            # Generate interactive HTML report in htmlcov/
    python run_tests.py tests/test_resume_accuracy.py  # Run on targeted test file
    python run_tests.py -k "resume"           # Run tests matching an expression
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import time
from typing import NamedTuple


class GateResult(NamedTuple):
    name: str
    status: str  # "PASSED", "FAILED", "SKIPPED"
    duration: float
    details: str = ""


def is_module_installed(mod_name: str) -> bool:
    """Check if a Python module is available in the current virtual environment."""
    try:
        return importlib.util.find_spec(mod_name) is not None
    except Exception:
        return False


def run_ruff(fix: bool = False) -> GateResult:
    """Run Ruff linter and code hygiene gate."""
    t0 = time.time()
    print("\n" + "=" * 78)
    print(" [1/4] Code Quality & Style Hygiene: Ruff")
    print("=" * 78)

    if not is_module_installed("ruff"):
        msg = "ruff is not installed (install via: pip install ruff)"
        print(f"  ℹ SKIPPED: {msg}")
        return GateResult("Ruff Linting", "SKIPPED", time.time() - t0, msg)

    cmd = [sys.executable, "-m", "ruff", "check", "."]
    if fix:
        cmd.append("--fix")

    print(f"  Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd)
    duration = time.time() - t0

    if res.returncode == 0:
        print("  ✓ Ruff linting passed cleanly with 0 errors.")
        return GateResult("Ruff Linting", "PASSED", duration, "0 errors across repository")
    else:
        print(f"  ❌ Ruff detected linting errors (exit code {res.returncode}).")
        return GateResult("Ruff Linting", "FAILED", duration, f"exit code {res.returncode}")


def run_mypy(target_pkg: str = "jobhunt") -> GateResult:
    """Run Mypy static type checking gate across all package source files."""
    t0 = time.time()
    print("\n" + "=" * 78)
    print(f" [2/4] Static Type Analysis: Mypy (`{target_pkg}`)")
    print("=" * 78)

    if not is_module_installed("mypy"):
        msg = "mypy is not installed (install via: pip install mypy)"
        print(f"  ℹ SKIPPED: {msg}")
        return GateResult("Mypy Typing", "SKIPPED", time.time() - t0, msg)

    cmd = [sys.executable, "-m", "mypy", target_pkg]
    print(f"  Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd)
    duration = time.time() - t0

    if res.returncode == 0:
        print("  ✓ Mypy static type analysis passed cleanly across all source files.")
        return GateResult("Mypy Typing", "PASSED", duration, "0 type errors across all files")
    else:
        print(f"  ❌ Mypy detected static type errors (exit code {res.returncode}).")
        return GateResult("Mypy Typing", "FAILED", duration, f"exit code {res.returncode}")


def run_pytest_and_coverage(
    extra_pytest_args: list[str],
    with_coverage: bool = True,
    fail_under: int | None = None,
    html_report: bool = False,
    xml_report: bool = False,
) -> tuple[GateResult, GateResult]:
    """Run Pytest test suite and code coverage measurement gate."""
    t0 = time.time()
    print("\n" + "=" * 78)
    print(" [3/4 & 4/4] Full Test Suite & Coverage Analysis: Pytest + Coverage")
    print("=" * 78)

    if not is_module_installed("pytest"):
        msg = "pytest is not installed (install via: pip install pytest)"
        print(f"  ❌ FAILED: {msg}")
        duration = time.time() - t0
        return (
            GateResult("Pytest Suite", "FAILED", duration, msg),
            GateResult("Code Coverage", "SKIPPED", 0.0, "pytest missing"),
        )

    cmd = [sys.executable, "-m", "pytest"]

    # Coverage flags
    has_cov = with_coverage and is_module_installed("pytest_cov")
    if with_coverage and not has_cov:
        print("  ℹ pytest-cov not installed; running tests without coverage reporting.")
        print("    (Install via: pip install pytest-cov)")

    if has_cov:
        cmd.extend([
            "--cov=jobhunt",
            "--cov-report=term-missing",
        ])
        if fail_under is not None:
            cmd.append(f"--cov-fail-under={fail_under}")
        if html_report:
            cmd.append("--cov-report=html:htmlcov")
        if xml_report:
            cmd.append("--cov-report=xml:coverage.xml")

    # If no specific tests or markers specified, run the test suite
    if extra_pytest_args:
        cmd.extend(extra_pytest_args)
    else:
        cmd.append("-v")

    print(f"  Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd)
    duration = time.time() - t0

    if res.returncode == 0:
        pytest_res = GateResult("Pytest Suite", "PASSED", duration, "All tests passed successfully")
        cov_res = (
            GateResult("Code Coverage", "PASSED", duration, "Coverage report generated")
            if has_cov
            else GateResult("Code Coverage", "SKIPPED", 0.0, "Coverage disabled or pytest-cov missing")
        )
    else:
        pytest_res = GateResult("Pytest Suite", "FAILED", duration, f"exit code {res.returncode}")
        cov_res = (
            GateResult("Code Coverage", "FAILED", duration, f"exit code {res.returncode}")
            if has_cov
            else GateResult("Code Coverage", "SKIPPED", 0.0, "Tests failed")
        )

    return pytest_res, cov_res


def print_summary_dashboard(results: list[GateResult], total_duration: float) -> int:
    """Print an executive summary dashboard showing all verification gates."""
    print("\n" + "=" * 78)
    print("                     PIPELINE VERIFICATION SUMMARY")
    print("=" * 78)
    print(f" {'GATE':<24} | {'STATUS':<10} | {'DURATION':<10} | {'DETAILS'}")
    print("-" * 78)

    all_passed = True
    for r in results:
        status_symbol = {
            "PASSED": "✓ PASSED",
            "FAILED": "❌ FAILED",
            "SKIPPED": "ℹ SKIPPED",
        }.get(r.status, r.status)

        if r.status == "FAILED":
            all_passed = False

        duration_str = f"{r.duration:.2f}s" if r.duration > 0 else "-"
        print(f" {r.name:<24} | {status_symbol:<10} | {duration_str:<10} | {r.details}")

    print("=" * 78)
    print(f" Total Pipeline Runtime: {total_duration:.2f}s")
    if all_passed:
        print(" 🎉 OVERALL STATUS: ALL GATES PASSED (100% SUCCESS)")
        print("=" * 78 + "\n")
        return 0
    else:
        print(" ❌ OVERALL STATUS: ONE OR MORE GATES FAILED")
        print("=" * 78 + "\n")
        return 1


def main() -> int:
    """Main entrypoint for the unified test and quality pipeline."""
    t_start = time.time()

    parser = argparse.ArgumentParser(
        description="Unified All-in-One Quality, Type, Test & Coverage Runner for Job Hunter.",
        add_help=True,
    )
    parser.add_argument("--tests-only", action="store_true", help="Run only Pytest + Coverage (skip Ruff & Mypy)")
    parser.add_argument("--lint-only", action="store_true", help="Run only Ruff and Mypy (skip Pytest)")
    parser.add_argument("--mypy-only", action="store_true", help="Run only Mypy static type analysis")
    parser.add_argument("--ruff-only", action="store_true", help="Run only Ruff linter")
    parser.add_argument("--fix", action="store_true", help="Auto-fix safe lint issues with Ruff")
    parser.add_argument("--no-cov", action="store_true", help="Run tests without coverage analysis")
    parser.add_argument("--cov-fail-under", type=int, default=None, help="Fail if total coverage is below N%%")
    parser.add_argument("--cov-html", action="store_true", help="Generate HTML coverage report in htmlcov/")
    parser.add_argument("--cov-xml", action="store_true", help="Generate XML coverage report in coverage.xml")

    # Separate known runner args from passthrough args to pytest
    known, passthrough_args = parser.parse_known_args()

    results: list[GateResult] = []

    print("=" * 78)
    print(" Job Hunter — Unified Quality, Type, Test & Coverage Pipeline")
    print("=" * 78)

    # 1. Ruff-only mode
    if known.ruff_only:
        results.append(run_ruff(fix=known.fix))
        return print_summary_dashboard(results, time.time() - t_start)

    # 2. Mypy-only mode
    if known.mypy_only:
        results.append(run_mypy())
        return print_summary_dashboard(results, time.time() - t_start)

    # 3. Lint-only mode (Ruff + Mypy)
    if known.lint_only:
        results.append(run_ruff(fix=known.fix))
        results.append(run_mypy())
        return print_summary_dashboard(results, time.time() - t_start)

    # 4. Standard / Unified mode:
    # Run Ruff unless tests-only
    if not known.tests_only:
        results.append(run_ruff(fix=known.fix))
        results.append(run_mypy())

    # Run Pytest + Coverage
    py_res, cov_res = run_pytest_and_coverage(
        extra_pytest_args=passthrough_args,
        with_coverage=not known.no_cov,
        fail_under=known.cov_fail_under,
        html_report=known.cov_html,
        xml_report=known.cov_xml,
    )
    results.append(py_res)
    results.append(cov_res)

    return print_summary_dashboard(results, time.time() - t_start)


if __name__ == "__main__":
    sys.exit(main())
