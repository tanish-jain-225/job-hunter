"""JSON parsing, validation, and PDF resume processing utilities for LLM stages."""

from __future__ import annotations

import io
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Max PDF bytes (5 MB) and maximum page count (10 pages) for resource bounds
MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 10
MAX_RESUME_TEXT_CHARS = 50_000

_THINK_BLOCKS = re.compile(
    r"<(?:think|thought|thinking)>.*?</(?:think|thought|thinking)>",
    flags=re.DOTALL | re.IGNORECASE,
)
_FENCE_OPEN = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*", re.M)
_FENCE_CLOSE = re.compile(r"\s*```\s*$", re.M)


def strip_json_comments(text: str) -> str:
    """Safely strip single-line // and multi-line /* */ comments outside JSON string literals."""
    out: list[str] = []
    in_str = False
    esc = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            i += 1
        else:
            if c == '"':
                in_str = True
                out.append(c)
                i += 1
            elif c == "/" and i + 1 < n and text[i + 1] == "/":
                i += 2
                while i < n and text[i] != "\n":
                    i += 1
            elif c == "/" and i + 1 < n and text[i + 1] == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    i += 1
                i += 2
            else:
                out.append(c)
                i += 1
    return "".join(out)


def repair_truncated_json(text: str) -> Any | None:
    """Attempt to recover complete items from a truncated JSON list or object."""
    trimmed = text.strip()
    if not trimmed:
        return None

    # If it starts with [ but doesn't end with ]
    if trimmed.startswith("[") and not trimmed.endswith("]"):
        last_brace = trimmed.rfind("}")
        if last_brace != -1:
            candidate = trimmed[: last_brace + 1].strip()
            candidate = re.sub(r",\s*$", "", candidate) + "]"
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                pass

    # If it starts with { but doesn't end with }
    if trimmed.startswith("{") and not trimmed.endswith("}"):
        last_comma = trimmed.rfind(",")
        if last_comma != -1:
            candidate = trimmed[:last_comma].strip() + "}"
            try:
                return json.loads(candidate, strict=False)
            except Exception:
                pass
        for close_attempt in ['"}', '"]}', '}', ']']:
            try:
                return json.loads(trimmed + close_attempt, strict=False)
            except Exception:
                continue

    return None


def parse_json(raw: str) -> Any:
    """Parse a model reply that is *supposed* to be JSON with maximum resilience."""
    if raw is None:
        raise ValueError("empty model reply")
    raw_str = str(raw).strip()
    if not raw_str:
        raise ValueError("empty model reply")

    # Strip <think>...</think> reasoning blocks from thinking models
    cleaned = _THINK_BLOCKS.sub("", raw_str)
    # If an opening thought tag was cut off mid-thought without closing tag, strip up to first [ or {
    if re.search(r"<(?:think|thought|thinking)>", cleaned, re.IGNORECASE):
        first_bracket = min(
            (pos for pos in (cleaned.find("["), cleaned.find("{")) if pos != -1),
            default=-1,
        )
        if first_bracket != -1:
            cleaned = cleaned[first_bracket:]

    cleaned = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", cleaned)).strip()

    # Fast path: direct valid JSON
    try:
        return json.loads(cleaned, strict=False)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strip single-line & multi-line comments and sanitize trailing commas e.g. {"a": 1,} -> {"a": 1}
    comment_stripped = strip_json_comments(cleaned)
    sanitized = re.sub(r",\s*([\]}])", r"\1", comment_stripped).strip()
    try:
        return json.loads(sanitized, strict=False)
    except (json.JSONDecodeError, TypeError):
        pass

    # If the reply was an array cut off mid-output (starts with [ but missing closing ]),
    # prioritize repairing the array so we return a list rather than an isolated inner dict.
    if sanitized.startswith("[") and not sanitized.endswith("]"):
        repaired = repair_truncated_json(sanitized)
        if repaired is not None:
            return repaired

    # Extract bracketed / braced candidate substrings
    candidates = []
    for opener, closer in (("[", "]"), ("{", "}")):
        i, k = sanitized.find(opener), sanitized.rfind(closer)
        if i != -1 and k > i:
            candidates.append((i, sanitized[i : k + 1]))
    for _, blob in sorted(candidates):
        try:
            return json.loads(blob, strict=False)
        except (json.JSONDecodeError, TypeError):
            continue

    # Try converting Python literals outside quotes (True -> true, False -> false, None -> null)
    py_literal_fixed = re.sub(r"\bTrue\b", "true", sanitized)
    py_literal_fixed = re.sub(r"\bFalse\b", "false", py_literal_fixed)
    py_literal_fixed = re.sub(r"\bNone\b", "null", py_literal_fixed)
    try:
        return json.loads(py_literal_fixed, strict=False)
    except (json.JSONDecodeError, TypeError):
        pass

    # Safe fallback for Python dict/list literals with single quotes
    if (sanitized.startswith("{") and sanitized.endswith("}")) or (sanitized.startswith("[") and sanitized.endswith("]")):
        import ast

        try:
            val = ast.literal_eval(sanitized)
            if isinstance(val, (dict, list)):
                return val
        except Exception:
            pass

    # Attempt truncated JSON recovery for models cut off by max output token ceilings
    repaired = repair_truncated_json(sanitized)
    if repaired is not None:
        return repaired

    raise ValueError(f"could not parse JSON from model reply: {cleaned[:300]!r}")


def _ensure_list(val: Any) -> list[str]:
    """Safely convert list or newline-separated string into a list of non-empty strings."""
    if isinstance(val, (list, tuple, set)):
        result = []
        for x in val:
            if isinstance(x, dict):
                v = x.get("text") or x.get("name") or x.get("skill") or x.get("value") or (next(iter(x.values())) if x else "")
                if str(v).strip():
                    result.append(str(v).strip())
            elif str(x).strip():
                result.append(str(x).strip())
        return result
    if isinstance(val, dict):
        return _ensure_list(list(val.values()))
    if isinstance(val, str):
        lines = [line.strip().lstrip("-*•1234567890. ") for line in val.split("\n") if line.strip()]
        if len(lines) == 1 and "," in lines[0] and not lines[0].startswith("http"):
            parts = [p.strip().lstrip("-*•1234567890. ") for p in lines[0].split(",") if p.strip()]
            if len(parts) > 1:
                return parts
        return [l for l in lines if l]
    return []


def _as_list(payload: Any) -> list[dict]:
    """Accept [ {...} ], { "jobs": [...] }, or a bare { ... }."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("jobs", "results", "scores", "items", "data", "candidates", "matches", "evaluations", "output"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [p for p in inner if isinstance(p, dict)]
        list_vals = [v for v in payload.values() if isinstance(v, list)]
        if len(list_vals) == 1:
            return [p for p in list_vals[0] if isinstance(p, dict)]
        return [payload]
    raise ValueError(f"expected a JSON array of results, got {type(payload).__name__}")


def extract_text_from_pdf(pdf_bytes: bytes | None) -> str:
    """Extract plain text from PDF bytes locally using pypdf with bounds safety."""
    if not pdf_bytes or not isinstance(pdf_bytes, (bytes, bytearray)):
        return ""

    if len(pdf_bytes) > MAX_PDF_BYTES:
        logger.warning("PDF exceeds maximum allowed size (%d bytes); skipping.", len(pdf_bytes))
        return ""

    try:
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_text: list[str] = []
        for page in reader.pages[:MAX_PDF_PAGES]:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())
        res = "\n\n".join(pages_text).strip()
        if res:
            return res[:MAX_RESUME_TEXT_CHARS]
    except Exception as e:
        logger.debug("pypdf parsing failed: %s", e)

    # Fallback decode as text if parsing fails (useful for mock/corrupted PDF bytes in testing)
    try:
        decoded = pdf_bytes[:MAX_PDF_BYTES].decode("utf-8", errors="ignore").strip()
        if len(decoded) > 20 and any(
            kw in decoded for kw in ("Resume", "skills", "Python", "experience", "education", "projects")
        ):
            return decoded[:MAX_RESUME_TEXT_CHARS]
    except Exception:
        pass
    return ""


__all__ = [
    "parse_json",
    "strip_json_comments",
    "repair_truncated_json",
    "_ensure_list",
    "_as_list",
    "extract_text_from_pdf",
    "parse_month_year",
    "calculate_timeline_yoe",
    "normalize_technical_skills",
    "synthesize_headline_and_targets",
    "sanitize_candidate_name",
    "MAX_PDF_BYTES",
    "MAX_PDF_PAGES",
    "MAX_RESUME_TEXT_CHARS",
]


_CANONICAL_SKILL_MAP: dict[str, str] = {
    "react.js": "React",
    "reactjs": "React",
    "react js": "React",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "next js": "Next.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "node js": "Node.js",
    "express.js": "Express.js",
    "expressjs": "Express.js",
    "express js": "Express.js",
    "vue.js": "Vue.js",
    "vuejs": "Vue.js",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "psql": "PostgreSQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "python3": "Python",
    "python 3": "Python",
    "golang": "Go",
    "go lang": "Go",
    "typescript": "TypeScript",
    "javascript": "JavaScript",
    "js": "JavaScript",
    "es6": "JavaScript",
    "es6+": "JavaScript",
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "GCP",
    "google cloud": "GCP",
    "google cloud platform": "GCP",
    "ci/cd": "CI/CD",
    "ci cd": "CI/CD",
    "ci/cd pipelines": "CI/CD",
    "github actions": "GitHub Actions",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "redis": "Redis",
    "graphql": "GraphQL",
    "rest": "REST APIs",
    "rest api": "REST APIs",
    "rest apis": "REST APIs",
    "restful api": "REST APIs",
    "restful apis": "REST APIs",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "pydantic": "Pydantic",
    "supabase": "Supabase",
    "firebase": "Firebase",
    "firestore": "Firebase Firestore",
    "firebase firestore": "Firebase Firestore",
    "pytest": "Pytest",
    "jest": "Jest",
    "playwright": "Playwright",
    "cypress": "Cypress",
    "selenium": "Selenium",
    "postman": "Postman",
    "git": "Git",
    "github": "GitHub",
    "jwt": "JWT",
    "rbac": "RBAC",
    "numpy": "NumPy",
    "pandas": "Pandas",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "scikit-learn": "scikit-learn",
    "sklearn": "scikit-learn",
    # Design & Product
    "figma": "Figma",
    "sketch": "Sketch",
    "adobe xd": "Adobe XD",
    "adobexd": "Adobe XD",
    "wireframing": "Wireframing",
    "prototyping": "Prototyping",
    "user research": "User Research",
    "usability testing": "Usability Testing",
    "design systems": "Design Systems",
    "design system": "Design Systems",
    "interaction design": "Interaction Design",
    "visual design": "Visual Design",
    "product management": "Product Management",
    "prd": "PRDs",
    "prds": "PRDs",
    "product roadmap": "Product Roadmapping",
    "roadmapping": "Product Roadmapping",
    "user stories": "User Stories",
    "a/b testing": "A/B Testing",
    "ab testing": "A/B Testing",
    "jira": "Jira",
    "confluence": "Confluence",
    "linear": "Linear",
    "mixpanel": "Mixpanel",
    "amplitude": "Amplitude",
    # Data & Analytics
    "sql": "SQL",
    "tableau": "Tableau",
    "power bi": "Power BI",
    "powerbi": "Power BI",
    "looker": "Looker",
    "looker studio": "Looker Studio",
    "metabase": "Metabase",
    "dbt": "dbt",
    "snowflake": "Snowflake",
    "bigquery": "BigQuery",
    "excel": "Excel",
    "advanced excel": "Advanced Excel",
    # Marketing & Growth
    "seo": "SEO",
    "sem": "SEM",
    "google ads": "Google Ads",
    "google analytics": "Google Analytics",
    "ga4": "Google Analytics",
    "hubspot": "HubSpot",
    "marketo": "Marketo",
    "content strategy": "Content Strategy",
    "copywriting": "Copywriting",
    "email marketing": "Email Marketing",
    "meta ads": "Meta Ads",
    # Sales & BD
    "salesforce": "Salesforce",
    "b2b sales": "B2B Sales",
    "lead generation": "Lead Generation",
    "cold outreach": "Cold Outreach",
    "crm": "CRM",
    "pipeline management": "Pipeline Management",
    # Finance & Accounting
    "financial modeling": "Financial Modeling",
    "valuation": "Valuation",
    "quickbooks": "QuickBooks",
    "tally": "Tally",
    "sap": "SAP",
    "budgeting": "Budgeting",
    "forecasting": "Financial Forecasting",
    "auditing": "Auditing",
    "ifrs": "IFRS",
    "gaap": "GAAP",
    # HR & People
    "talent acquisition": "Talent Acquisition",
    "recruiting": "Recruiting",
    "technical recruiting": "Technical Recruiting",
    "hris": "HRIS",
    "workday": "Workday",
    "bamboohr": "BambooHR",
    "people operations": "People Operations",
    "employee relations": "Employee Relations",
    # Operations & Project Management
    "supply chain": "Supply Chain",
    "logistics": "Logistics",
    "operations management": "Operations Management",
    "process optimization": "Process Optimization",
    "asana": "Asana",
    "monday.com": "Monday.com",
    "pmp": "PMP",
    # Legal & Compliance
    "contract management": "Contract Management",
    "compliance": "Regulatory Compliance",
    "regulatory compliance": "Regulatory Compliance",
    "gdpr": "GDPR",
    "due diligence": "Due Diligence",
}

_SOFT_SKILLS_BLACKLIST: set[str] = {
    "problem solving",
    "communication",
    "communication skills",
    "leadership",
    "leadership skills",
    "team work",
    "teamwork",
    "team player",
    "hard working",
    "hardworking",
    "critical thinking",
    "time management",
    "adaptability",
    "agile",
    "scrum",
    "collaboration",
    "active listening",
    "multitasking",
    "work ethic",
    "attention to detail",
    "presentation skills",
    "analytical skills",
    "creative thinking",
}


def parse_month_year(s: str) -> tuple[int, int] | None:
    """Parse month and year from common date strings like 'Aug 2024', '08/2024', '2024', 'Present'."""
    if not s or not isinstance(s, str):
        return None
    cleaned = s.strip().lower()
    # Fixed base year for 2026/2027 context
    if any(k in cleaned for k in ("present", "current", "now", "ongoing")):
        return (2026, 11)
    month_map = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        "january": 1, "february": 2, "march": 3, "april": 4, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }
    m1 = re.search(r"([a-z]+)[\s,.-]+(20\d\d|19\d\d)", cleaned)
    if m1 and m1.group(1) in month_map:
        return (int(m1.group(2)), month_map[m1.group(1)])
    m2 = re.search(r"(20\d\d|19\d\d)[\s,.-]+([a-z]+)", cleaned)
    if m2 and m2.group(2) in month_map:
        return (int(m2.group(1)), month_map[m2.group(2)])
    m3 = re.search(r"(\d{1,2})[\s/.-]+(20\d\d|19\d\d)", cleaned)
    if m3 and 1 <= int(m3.group(1)) <= 12:
        return (int(m3.group(2)), int(m3.group(1)))
    m4 = re.search(r"(20\d\d|19\d\d)[\s/.-]+(\d{1,2})", cleaned)
    if m4 and 1 <= int(m4.group(2)) <= 12:
        return (int(m4.group(1)), int(m4.group(2)))
    m_yr = re.search(r"\b(20\d\d|19\d\d)\b", cleaned)
    if m_yr:
        return (int(m_yr.group(1)), 6)
    return None


def calculate_timeline_yoe(
    work_history: Any,
    graduation_year: Any = None,
    resume_text: str | None = None,
) -> float:
    """Calculate grounded full-time professional software experience in years with overlap deduplication.

    Excludes student internships and academic projects from full-time tenure, and clamps recent
    graduates / freshers (graduation year >= 2024 with no full-time stints) to 0.0 or 0.5.
    """
    grad_yr: int | None = None
    if graduation_year is not None:
        try:
            m_g = re.search(r"\b(20\d\d)\b", str(graduation_year))
            if m_g:
                grad_yr = int(m_g.group(1))
        except Exception:
            pass

    if grad_yr is None and resume_text:
        m_edu = re.search(
            r"(?i)(?:expected|graduation|graduating|batch\s*of|class\s*of|b\.?e\.?|b\.?tech|m\.?s\.?|bachelor|master)[\s\w,()'-]*?\b(202[4-9]|203\d)\b",
            resume_text,
        )
        if m_edu:
            grad_yr = int(m_edu.group(1))

    full_time_intervals: list[tuple[int, int]] = []
    has_full_time = False

    if isinstance(work_history, list):
        for entry in work_history:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "").lower()
            stint_type = str(entry.get("type") or "").lower()

            is_internship = (
                "intern" in stint_type
                or "intern" in role
                or "trainee" in role
                or "apprentice" in role
                or "academic" in stint_type
                or "project" in stint_type
            )
            if is_internship:
                continue

            start_t = parse_month_year(str(entry.get("start") or ""))
            end_t = parse_month_year(str(entry.get("end") or ""))
            if start_t and end_t:
                s_idx = start_t[0] * 12 + start_t[1]
                e_idx = end_t[0] * 12 + end_t[1]
                if e_idx >= s_idx:
                    full_time_intervals.append((s_idx, e_idx))
                    has_full_time = True

    if not has_full_time and resume_text:
        is_student = bool(
            re.search(r"(?i)\b(?:final[- ]year|student|undergraduate|fresher|pre[- ]final)\b", resume_text)
            and grad_yr and grad_yr >= 2025
        )
        if is_student:
            return 0.0

        yoe_m = re.search(
            r"(?i)(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s*(?:of\s+)?(?:total\s+)?(?:experience|exp|industry\s+experience|work\s+experience|software\s+experience)",
            resume_text,
        )
        if yoe_m:
            try:
                claimed = float(yoe_m.group(1))
                if grad_yr and grad_yr >= 2025 and claimed > 1.0:
                    claimed = 0.5
                return round(claimed, 1)
            except ValueError:
                pass

    if not full_time_intervals:
        return 0.0

    sorted_ivs = sorted(full_time_intervals, key=lambda x: (x[0], x[1]))
    merged = [sorted_ivs[0]]
    for cur_s, cur_e in sorted_ivs[1:]:
        prev_s, prev_e = merged[-1]
        if cur_s <= prev_e:
            merged[-1] = (prev_s, max(prev_e, cur_e))
        else:
            merged.append((cur_s, cur_e))

    total_months = sum(e - s + 1 for s, e in merged)
    yoe = round(total_months / 12.0, 1)

    if grad_yr and grad_yr >= 2026:
        yoe = min(yoe, 1.0)

    return max(0.0, yoe)


def normalize_technical_skills(skills: Any) -> list[str]:
    """Normalize tech skills into canonical forms and strip soft skills and buzzwords."""
    raw_list = _ensure_list(skills)
    seen_lower = set()
    cleaned_skills: list[str] = []

    for item in raw_list:
        token = str(item).strip()
        if not token or len(token) > 40:
            continue
        token_lower = token.lower()
        if token_lower in _SOFT_SKILLS_BLACKLIST:
            continue

        canonical = _CANONICAL_SKILL_MAP.get(token_lower, token)
        can_lower = canonical.lower()
        if can_lower not in seen_lower:
            seen_lower.add(can_lower)
            cleaned_skills.append(canonical)

    return cleaned_skills


def synthesize_headline_and_targets(
    title: str | None,
    skills: list[str],
    yoe: float = 0.0,
    domains: list[str] | None = None,
) -> tuple[str, list[str]]:
    """Synthesize a professional role title and tailored search keywords across all industries and professions.

    Dynamically identifies professional domains (Product Management, UI/UX Design, Data & BI,
    Growth & Marketing, Sales & BD, Finance & Accounting, HR & Talent, Operations & PM,
    Legal & Compliance, and Engineering) without rigid single-sector hardcoding.
    """
    clean_title = (title or "").strip()
    non_professional_keywords = (
        "student", "fresher", "intern", "candidate", "graduate",
        "undergraduate", "b.tech", "b.e.", "bachelor", "master",
    )
    is_invalid = not clean_title or any(np in clean_title.lower() for np in non_professional_keywords)

    skills_lower = [s.lower() for s in skills]
    domains_lower = [d.lower() for d in (domains or [])]
    combined_context = " ".join([clean_title.lower()] + skills_lower + domains_lower)

    # 1. Multi-domain signal detection
    domain_weights: dict[str, int] = {
        "design": 0,
        "product": 0,
        "data_analytics": 0,
        "ai_ml": 0,
        "marketing": 0,
        "sales": 0,
        "finance": 0,
        "hr": 0,
        "operations": 0,
        "legal": 0,
        "engineering": 0,
    }

    # Signal catalogs
    design_kws = ("figma", "sketch", "adobe xd", "wireframing", "prototyping", "user research", "usability testing", "design systems", "interaction design", "visual design", "ui/ux", "designer")
    product_kws = ("product management", "prd", "prds", "product roadmapping", "user stories", "a/b testing", "feature prioritization", "linear", "mixpanel", "amplitude", "product manager", "product owner")
    data_kws = ("tableau", "power bi", "powerbi", "looker", "metabase", "data analysis", "business intelligence", "snowflake", "bigquery", "dbt", "bi analyst", "data analyst")
    aiml_kws = ("pytorch", "tensorflow", "machine learning", "deep learning", "nlp", "computer vision", "scikit-learn", "data scientist", "ai/ml", "artificial intelligence")
    marketing_kws = ("seo", "sem", "google ads", "meta ads", "hubspot", "marketo", "google analytics", "copywriting", "content strategy", "email marketing", "growth marketing", "digital marketing")
    sales_kws = ("salesforce", "b2b sales", "lead generation", "cold outreach", "crm", "pipeline management", "account executive", "business development", "inside sales")
    finance_kws = ("financial modeling", "valuation", "quickbooks", "tally", "sap", "auditing", "budgeting", "financial forecasting", "ifrs", "gaap", "accounting", "financial analyst")
    hr_kws = ("talent acquisition", "technical recruiting", "recruiting", "hris", "workday", "bamboohr", "people operations", "employee relations", "human resources")
    ops_kws = ("supply chain", "logistics", "operations management", "process optimization", "asana", "monday.com", "pmp", "project manager", "program manager", "scrum master")
    legal_kws = ("contract management", "regulatory compliance", "gdpr", "due diligence", "compliance", "legal counsel", "corporate law")

    has_frontend = any(k in skills_lower for k in ("react", "vue", "angular", "next.js", "tailwind css", "html5", "css3", "javascript", "typescript"))
    has_backend = any(k in skills_lower for k in ("python", "fastapi", "flask", "django", "node.js", "express.js", "go", "golang", "postgresql", "mongodb", "rest apis", "sql", "java", "c++", "rust"))
    has_devops = any(k in skills_lower for k in ("docker", "kubernetes", "aws", "gcp", "azure", "ci/cd", "github actions", "terraform"))

    for kw in design_kws:
        if kw in combined_context:
            domain_weights["design"] += 2 if (clean_title and kw in clean_title.lower()) else 1
    for kw in product_kws:
        if kw in combined_context:
            domain_weights["product"] += 2 if (clean_title and kw in clean_title.lower()) else 1
    for kw in data_kws:
        if kw in combined_context:
            domain_weights["data_analytics"] += 2 if (clean_title and kw in clean_title.lower()) else 1
    for kw in aiml_kws:
        if kw in combined_context:
            domain_weights["ai_ml"] += 2 if (clean_title and kw in clean_title.lower()) else 1
    for kw in marketing_kws:
        if kw in combined_context:
            domain_weights["marketing"] += 2 if (clean_title and kw in clean_title.lower()) else 1
    for kw in sales_kws:
        if kw in combined_context:
            domain_weights["sales"] += 2 if (clean_title and kw in clean_title.lower()) else 1
    for kw in finance_kws:
        if kw in combined_context:
            domain_weights["finance"] += 2 if (clean_title and kw in clean_title.lower()) else 1
    for kw in hr_kws:
        if kw in combined_context:
            domain_weights["hr"] += 2 if (clean_title and kw in clean_title.lower()) else 1
    for kw in ops_kws:
        if kw in combined_context:
            domain_weights["operations"] += 2 if (clean_title and kw in clean_title.lower()) else 1
    for kw in legal_kws:
        if kw in combined_context:
            domain_weights["legal"] += 2 if (clean_title and kw in clean_title.lower()) else 1

    if has_frontend or has_backend or has_devops or any(k in combined_context for k in ("engineer", "developer", "sde", "software")):
        domain_weights["engineering"] += 2
        if has_frontend:
            domain_weights["engineering"] += 1
        if has_backend:
            domain_weights["engineering"] += 1
        if has_devops:
            domain_weights["engineering"] += 1

    # Detect primary domain
    sorted_domains = sorted(domain_weights.items(), key=lambda x: x[1], reverse=True)
    top_domain, top_score = sorted_domains[0]
    detected_domain = top_domain if top_score > 0 else "engineering"

    # 2. Derive headline title
    if is_invalid:
        if detected_domain == "design":
            derived_title = "Product Designer"
        elif detected_domain == "product":
            derived_title = "Associate Product Manager" if yoe <= 1.0 else "Product Manager"
        elif detected_domain == "data_analytics":
            derived_title = "Data Analyst"
        elif detected_domain == "ai_ml":
            derived_title = "AI/ML Engineer"
        elif detected_domain == "marketing":
            derived_title = "Growth Marketer"
        elif detected_domain == "sales":
            derived_title = "Business Development Representative" if yoe <= 1.5 else "Account Executive"
        elif detected_domain == "finance":
            derived_title = "Financial Analyst"
        elif detected_domain == "hr":
            derived_title = "Talent Acquisition Specialist"
        elif detected_domain == "operations":
            derived_title = "Project Manager"
        elif detected_domain == "legal":
            derived_title = "Legal Counsel"
        else:
            # Engineering fallback hierarchy
            if has_frontend and has_backend:
                derived_title = "Full Stack Developer"
            elif domain_weights["ai_ml"] > 0 and has_backend:
                derived_title = "AI/ML Software Engineer"
            elif has_backend:
                derived_title = "Backend Engineer"
            elif has_frontend:
                derived_title = "Frontend Developer"
            elif has_devops:
                derived_title = "DevOps Engineer"
            else:
                derived_title = "Software Engineer"
    else:
        derived_title = clean_title

    # 3. Generate tailored target titles for the detected domain
    target_titles: list[str] = [derived_title]

    def _add_target(t: str) -> None:
        if t.lower() not in [x.lower() for x in target_titles] and len(target_titles) < 5:
            target_titles.append(t)

    if detected_domain == "design":
        for t in ["Product Designer", "UI/UX Designer", "UX Designer", "Visual Designer", "Lead Product Designer"]:
            _add_target(t)
    elif detected_domain == "product":
        for t in ["Product Manager", "Associate Product Manager", "Technical Product Manager", "Product Owner", "Product Lead"]:
            _add_target(t)
    elif detected_domain == "data_analytics":
        for t in ["Data Analyst", "Business Intelligence Analyst", "Analytics Engineer", "BI Analyst", "Data Specialist"]:
            _add_target(t)
    elif detected_domain == "ai_ml":
        for t in ["AI/ML Engineer", "Machine Learning Engineer", "Data Scientist", "AI Engineer", "Deep Learning Engineer"]:
            _add_target(t)
    elif detected_domain == "marketing":
        for t in ["Growth Marketer", "Digital Marketing Specialist", "Content Marketing Manager", "Marketing Manager", "Growth Lead"]:
            _add_target(t)
    elif detected_domain == "sales":
        for t in ["Account Executive", "Business Development Representative", "Sales Development Representative", "Inside Sales Specialist", "Sales Manager"]:
            _add_target(t)
    elif detected_domain == "finance":
        for t in ["Financial Analyst", "Finance Associate", "Accountant", "Senior Financial Analyst", "Financial Planning & Analysis (FP&A)"]:
            _add_target(t)
    elif detected_domain == "hr":
        for t in ["Talent Acquisition Specialist", "Technical Recruiter", "HR Generalist", "People Operations Specialist", "HR Specialist"]:
            _add_target(t)
    elif detected_domain == "operations":
        for t in ["Operations Manager", "Project Manager", "Program Manager", "Operations Specialist", "Scrum Master"]:
            _add_target(t)
    elif detected_domain == "legal":
        for t in ["Legal Counsel", "Compliance Specialist", "Corporate Counsel", "Legal Analyst", "Regulatory Specialist"]:
            _add_target(t)
    elif detected_domain == "engineering":
        if has_backend and "python" in skills_lower:
            _add_target("Python Developer")
            _add_target("Backend Engineer")
            _add_target("Software Engineer")
        if has_frontend and ("react" in skills_lower or "next.js" in skills_lower):
            _add_target("Full Stack Developer")
            _add_target("React Developer")
        if domain_weights["ai_ml"] > 0:
            _add_target("AI/ML Engineer")
        if has_devops:
            _add_target("DevOps Engineer")
        for fallback in ["Software Engineer", "Software Development Engineer", "Full Stack Developer"]:
            _add_target(fallback)
    else:
        # Universal fallback for unique custom professions
        for variant in [f"Senior {derived_title}", f"Lead {derived_title}", f"Associate {derived_title}", f"{derived_title} Specialist"]:
            _add_target(variant)

    return derived_title, target_titles[:5]


def sanitize_candidate_name(raw_name: str | None, text_lines: list[str] | None = None) -> str:
    """Validate and clean candidate name, stripping document titles, contact info, and noise."""
    name_skip_terms = {
        "resume", "curriculum vitae", "cv", "portfolio", "github", "linkedin",
        "contact", "email", "phone", "summary", "professional summary",
        "executive summary", "objective", "career objective", "about me",
        "profile", "personal profile", "experience", "work experience",
        "skills", "technical skills", "education", "projects", "certifications",
        "software engineer", "developer", "student", "candidate", "dombivli", "mumbai", "india",
        "product manager", "product designer", "data analyst", "account executive", "marketing manager",
        "financial analyst", "recruiter", "operations manager",
    }
    if raw_name:
        cand = str(raw_name).strip("•-*| \t()[]{}#_")
        cand = re.sub(
            r"(?i)^(?:resume\s*[-:]\s*|candidate(?:\s+name)?\s*[:\-]\s*|full\s+name\s*[:\-]\s*|name\s*[:\-]\s*)",
            "",
            cand,
        ).strip()
        cand_lower = cand.lower()
        if (
            2 <= len(cand) <= 45
            and not re.search(r"[@:/0-9]", cand)
            and cand_lower not in name_skip_terms
        ):
            words = cand.split()
            if 1 <= len(words) <= 5:
                return cand.title() if (cand.islower() or cand.isupper()) else cand

    if text_lines:
        line_skip_headers = {
            "curriculum vitae", "resume", "cv", "portfolio", "summary",
            "professional summary", "executive summary", "objective",
            "career objective", "about me", "experience", "work experience",
            "education", "skills", "technical skills", "projects", "certifications",
        }
        for line in text_lines[:6]:
            line_str = line.strip()
            if not line_str or line_str.lower() in line_skip_headers:
                continue
            segments = re.split(r"[|•·,\t/]+", line_str)
            for seg in segments:
                clean_seg = seg.strip("•-*| \t()[]{}#_")
                clean_lower = clean_seg.lower()
                if (
                    2 <= len(clean_seg) <= 35
                    and not re.search(r"[@:/0-9\+]", clean_seg)
                    and not any(term in clean_lower for term in name_skip_terms)
                ):
                    words = clean_seg.split()
                    if 1 <= len(words) <= 4:
                        return clean_seg.title() if (clean_seg.islower() or clean_seg.isupper()) else clean_seg
    return ""
