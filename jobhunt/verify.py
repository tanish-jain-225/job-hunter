"""Company career board live verification module (`jobhunt verify`).

Audits target company career boards live against public ATS APIs to verify HTTP accessibility
and check endpoint validity across Greenhouse, Lever, Ashby, Workable, SmartRecruiters, BambooHR,
Recruitee, Breezy, and Pinpoint.
"""

from __future__ import annotations

import concurrent.futures
import logging
from pathlib import Path
from typing import Any

import requests
import yaml

from .fetch import REGISTERED_ATS

logger = logging.getLogger(__name__)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) jobhunt-verifier/1.0"}


def check_single_board(
    company: dict, timeout: int = 7, session: requests.Session | None = None
) -> tuple[dict, bool, Any]:
    """Check a single company's ATS board endpoint."""
    ats = str(company.get("ats", "")).lower()
    slug = str(company.get("slug", ""))

    if ats not in REGISTERED_ATS:
        return company, False, "Unknown ATS"

    url_template, _ = REGISTERED_ATS[ats]
    url = url_template.format(slug=slug)
    sess = session or requests

    try:
        r = sess.get(url, headers=UA, timeout=timeout)
        if r.status_code == 200:
            return company, True, 200
        return company, False, r.status_code
    except Exception as e:
        return company, False, str(e)[:40]


def audit_company_boards(
    companies_input: list[dict] | Path | str | None = None,
    max_workers: int = 25,
    timeout: int = 7,
) -> dict[str, Any]:
    """Audit company career boards concurrently.

    Returns:
        dict containing 'total', 'valid_count', 'invalid_count', 'valid', and 'invalid' lists.
    """
    company_list: list[dict] = []

    if companies_input is None:
        companies_input = Path("companies.yaml")

    if isinstance(companies_input, (str, Path)):
        p = Path(companies_input)
        if p.is_file():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                company_list = (
                    data.get("companies", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
                )
            except Exception as e:
                logger.error(f"Failed to load companies file {p}: {e}")
    elif isinstance(companies_input, list):
        company_list = [c for c in companies_input if isinstance(c, dict)]

    if not company_list:
        return {
            "total": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "valid": [],
            "invalid": [],
        }

    valid: list[tuple[dict, Any]] = []
    invalid: list[tuple[dict, Any]] = []

    with requests.Session() as session:
        workers = min(max_workers, max(1, len(company_list)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(check_single_board, c, timeout=timeout, session=session) for c in company_list]
            for future in concurrent.futures.as_completed(futures):
                try:
                    c, ok, status = future.result()
                    if ok:
                        valid.append((c, status))
                    else:
                        invalid.append((c, status))
                except Exception as e:
                    logger.warning(f"Error checking company board: {e}")

    return {
        "total": len(company_list),
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "valid": valid,
        "invalid": invalid,
    }
