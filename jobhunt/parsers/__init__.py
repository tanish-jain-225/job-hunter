"""Modular ATS Parsers Package for Job Hunter."""

from __future__ import annotations

from .models import Job, ParserFunc
from .registry import REGISTERED_ATS, register_ats
from .utils import strip_html, extract_salary_hint, is_safe_url

# Import individual parsers to trigger registration in REGISTERED_ATS
from .greenhouse import parse_greenhouse
from .lever import parse_lever
from .ashby import parse_ashby
from .workable import parse_workable
from .smartrecruiters import parse_smartrecruiters
from .bamboohr import parse_bamboohr
from .recruitee import parse_recruitee
from .breezy import parse_breezy
from .pinpoint import parse_pinpoint
from .detector import detect_ats_from_url

__all__ = [
    "Job",
    "ParserFunc",
    "REGISTERED_ATS",
    "register_ats",
    "strip_html",
    "extract_salary_hint",
    "is_safe_url",
    "parse_greenhouse",
    "parse_lever",
    "parse_ashby",
    "parse_workable",
    "parse_smartrecruiters",
    "parse_bamboohr",
    "parse_recruitee",
    "parse_breezy",
    "parse_pinpoint",
    "detect_ats_from_url",
]
