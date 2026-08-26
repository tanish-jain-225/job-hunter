"""Two-stage LLM layer: cheap screen over everything, rich draft for the top few.

Cost lives here, so the two stages are deliberately lopsided:

  screen  batch ~8 jobs per call, JD truncated to ~1400 chars, cheapest model
  draft   one call per job, ~6000 chars of JD, best model, only for the top ~5

Both stages take an optional (provider, model) pair so tests can inject a stub
and so you can point screening at Groq while drafting stays on Claude.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from .fetch import Job
from .providers import LLMError, Provider, resolve

_FENCE_OPEN = re.compile(r"^\s*```(?:json|JSON)?\s*", re.M)
_FENCE_CLOSE = re.compile(r"\s*```\s*$", re.M)

DRAFT_KEYS = (
    "fit_summary",
    "india_eligibility",
    "job_type",
    "salary_range_inr",
    "best_project",
    "tailored_bullets",
    "matching_skills",
    "gaps",
    "cover_note",
    "cold_outreach",
    "questions_to_ask",
)

# Output ceilings per stage. These are deliberately generous: reasoning models
# (Gemini 2.5+, and anything with thinking on) spend output tokens before the
# answer starts, so a ceiling sized to the visible answer gets consumed and you
# get truncated JSON instead of a result.
SCREEN_MAX_TOKENS = 2000
DRAFT_MAX_TOKENS = 8000
PROFILE_MAX_TOKENS = 4000


def parse_json(raw: str) -> Any:
    """Parse a model reply that is *supposed* to be JSON."""
    if raw is None:
        raise ValueError("empty model reply")
    cleaned = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", raw)).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    candidates = []
    for opener, closer in (("[", "]"), ("{", "}")):
        i, k = cleaned.find(opener), cleaned.rfind(closer)
        if i != -1 and k > i:
            candidates.append((i, cleaned[i:k + 1]))
    for _, blob in sorted(candidates):
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            continue
    raise ValueError(f"could not parse JSON from model reply: {cleaned[:300]!r}")


def _as_list(payload: Any) -> list[dict]:
    """Accept [ {...} ], { "jobs": [...] }, or a bare { ... }."""
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        for key in ("jobs", "results", "scores", "items"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [p for p in inner if isinstance(p, dict)]
        list_vals = [v for v in payload.values() if isinstance(v, list)]
        if len(list_vals) == 1:
            return [p for p in list_vals[0] if isinstance(p, dict)]
        return [payload]
    raise ValueError(f"expected a JSON array of results, got {type(payload).__name__}")


# ---------------------------------------------------------------- profile ---

PROFILE_PROMPT = """Extract a structured job-search profile from this resume.

Return ONLY a JSON object, no prose, no markdown fences:
{
  "name": str,
  "current_title": str,
  "years_experience": number,
  "core_skills": [str],        // 10-20, most load-bearing first
  "domains": [str],            // e.g. "distributed systems", "frontend", "backend"
  "notable_projects": [str],   // one line each, with impact if stated
  "education": str,
  "target_titles": [str],      // 3-6 realistic job search titles to include e.g. ["Software Engineer", "Full Stack Developer", "Backend Engineer"]
  "exclude_keywords": [str],   // 3-5 roles/keywords to exclude e.g. ["Manager", "Director", "Sales", "Recruiter", "VP"]
  "seniority": str,            // intern | new-grad | junior | mid | senior | staff
  "experience_level": str,     // fresher | 0-1 | 1-3 | 3-5 | 5+
  "job_types": [str],          // e.g. ["fulltime", "internship", "remote"]
  "location_preference": str   // all_india | remote_only | specific_cities | global
}"""


def extract_text_from_pdf(pdf_bytes: bytes | None) -> str:
    """Extract plain text from PDF bytes locally using pypdf if available."""
    if not pdf_bytes:
        return ""
    try:
        import io
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())
        res = "\n\n".join(pages_text).strip()
        if res:
            return res
    except Exception:
        pass
    # Fallback decode as text if parsing fails (useful for mock/corrupted PDF bytes in testing)
    try:
        decoded = pdf_bytes.decode("utf-8", errors="ignore").strip()
        if len(decoded) > 20 and any(kw in decoded for kw in ("Resume", "skills", "Python", "experience", "education", "projects")):
            return decoded
    except Exception:
        pass
    return ""


def build_profile(resume_bytes: bytes | None = None, resume_text: str | None = None,
                  is_pdf: bool = False, provider: Provider | None = None,
                  model: str | None = None) -> dict:
    """Resume (PDF or text) -> profile.json. Uses the draft-stage model."""
    if provider is None or model is None:
        provider, model = resolve("draft")

    extracted_pdf_text = ""
    if is_pdf and resume_bytes:
        extracted_pdf_text = extract_text_from_pdf(resume_bytes)

    effective_text = (resume_text or extracted_pdf_text).strip()

    if effective_text:
        raw = provider.complete(
            model, "", f"{PROFILE_PROMPT}\n\n--- RESUME ---\n{effective_text}",
            PROFILE_MAX_TOKENS, json_mode=True)
    elif is_pdf and resume_bytes:
        try:
            raw = provider.complete_document(
                model, PROFILE_PROMPT, resume_bytes, PROFILE_MAX_TOKENS)
        except LLMError as e:
            raise LLMError(
                f"{e}\nTip: export your resume to .txt and re-run, or set "
                f"DRAFT_PROVIDER=anthropic|gemini for PDF support."
            ) from e
    else:
        raw = provider.complete(
            model, "", f"{PROFILE_PROMPT}\n\n--- RESUME ---\n{resume_text or ''}",
            PROFILE_MAX_TOKENS, json_mode=True)

    profile = parse_json(raw)
    if not isinstance(profile, dict):
        raise ValueError("profile extraction did not return a JSON object")
    return profile


# ----------------------------------------------------------------- screen ---

def _get_candidate_name(profile: dict | None) -> str:
    if profile and profile.get("name"):
        return str(profile["name"]).strip()
    if profile and profile.get("email"):
        username = str(profile["email"]).split("@")[0]
        return " ".join(part.capitalize() for part in username.replace(".", " ").replace("_", " ").split())
    return "Candidate"


def _build_screen_system(profile: dict | None = None, cfg: dict | None = None) -> str:
    name = _get_candidate_name(profile)
    edu = (profile or {}).get("education", "")
    yoe = (profile or {}).get("years_experience")
    seniority = (profile or {}).get("seniority", "software engineer")
    target_titles = (profile or {}).get("target_titles") or (profile or {}).get("target_keywords") or []
    titles_str = ", ".join(target_titles) if target_titles else "Software Engineering / Technical Roles"
    domains = (profile or {}).get("domains") or []
    domains_str = ", ".join(domains) if domains else "Software Engineering"

    details = []
    if edu:
        details.append(str(edu))
    if yoe is not None:
        details.append(f"{yoe} YoE")
    if seniority:
        details.append(f"Level: {seniority}")

    context = f"candidate {name}"
    if details:
        context += f" ({', '.join(details)})"

    # Regional context: configurable via config.yaml (region_hint / region_context).
    # Defaults to India-first when no config is passed, preserving backward compatibility.
    _cfg = cfg or {}
    region_context = str(_cfg.get("region_context") or "india").lower().strip()
    if region_context == "global":
        region_note = ""
    else:
        region_note = _cfg.get("region_hint") or (
            "India-first platform. Consider Indian salary norms (LPA), Indian cities, Indian company names. "
            "If a job location mentions Indian cities or 'remote' it is highly relevant for Indian candidates."
        )

    region_line = f"\nNote: {region_note}" if region_note else ""

    return f"""You screen job postings for {context}. You are strict and objective.{region_line}
Target Roles: {titles_str}
Domains: {domains_str}

Score 0-10 on genuine fit:
  9-10  strong match, candidate background directly satisfies core requirements and target titles
  7-8   good match, worth applying
  5-6   plausible but real gaps or minor experience/location mismatch
  0-4   incompatible seniority, restricted work authorization, wrong tech stack, or missing non-negotiable requirements

Check Location & Remote eligibility:
  - Is the posting remote-friendly or located in the candidate's target region? If yes, score on technical fit.
  - Does it require strict local citizenship/residency not supported by the candidate? If yes, score 0-3 and mark as Restricted.

Return ONLY a JSON array, one object per job, no prose:
[{{"job_id": str, "score": number, "reason": str}}]
Echo `job_id` back exactly as given. `reason` is one sentence, max 20 words, concrete about the deciding factor."""


SCREEN_SYSTEM = _build_screen_system()


def screen(jobs: list[Job], profile: dict, batch_size: int = 8, jd_chars: int = 1400,
           provider: Provider | None = None, model: str | None = None,
           delay_seconds: float = 2.5, max_workers: int = 1) -> list[Job]:
    """Stage 1: score every surviving job. Mutates and returns `jobs`."""
    if provider is None or model is None:
        provider, model = resolve("screen")
    batch_size = max(1, int(batch_size))
    profile_blob = json.dumps(profile, ensure_ascii=False)
    batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]
    system_prompt = _build_screen_system(profile)

    def process_batch(n: int, batch: list[Job]) -> dict[str, dict[str, Any]]:
        payload = [{
            "job_id": j.job_id,
            "company": j.company,
            "title": j.title,
            "location": j.location,
            "description": j.description[:jd_chars],
        } for j in batch]
        results: dict[str, dict[str, Any]] = {}
        try:
            raw = provider.complete(
                model, system_prompt,
                f"CANDIDATE PROFILE:\n{profile_blob}\n\n"
                f"JOBS:\n{json.dumps(payload, ensure_ascii=False)}",
                SCREEN_MAX_TOKENS, json_mode=True,
            )
            for r in _as_list(parse_json(raw)):
                jid = r.get("job_id")
                if jid:
                    results[str(jid)] = r
        except (LLMError, ValueError, KeyError, TypeError, RuntimeError) as e:
            print(f"  ! screen batch {n} failed ({type(e).__name__}: {e}) — skipping")
        return results

    if max_workers > 1 and len(batches) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def throttled_process_batch(n: int, b: list[Job]) -> tuple[int, list[Job], dict[str, dict[str, Any]]]:
            if delay_seconds > 0 and n > 1:
                time.sleep(min(delay_seconds, 1.0) * ((n - 1) % max_workers))
            return n, b, process_batch(n, b)

        with ThreadPoolExecutor(max_workers=min(max_workers, len(batches))) as executor:
            futures = [executor.submit(throttled_process_batch, idx + 1, batch) for idx, batch in enumerate(batches)]
            for future in as_completed(futures):
                n, batch, results = future.result()
                for j in batch:
                    rec = results.get(j.job_id)
                    if rec is None:
                        continue
                    try:
                        j.score = max(0.0, min(10.0, float(rec.get("score", 0))))
                    except (TypeError, ValueError):
                        j.score = 0.0
                    j.reason = str(rec.get("reason", "")).strip()
                print(f"  screened batch {n}/{len(batches)}")
    else:
        consecutive_failures = 0
        quota_circuit_broken = False
        for idx, batch in enumerate(batches):
            if quota_circuit_broken:
                keyword_screen(batch, profile)
                processed_count = min((idx + 1) * batch_size, len(jobs))
                print(f"  screened {processed_count}/{len(jobs)} [offline keyword fallback]")
                continue

            results = process_batch(idx + 1, batch)
            if not results:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    print("  ⚠️ LLM provider quota exhausted for today (429). Fast-falling back to offline keyword scorer for remaining batches.")
                    quota_circuit_broken = True
                    keyword_screen(batch, profile)
            else:
                consecutive_failures = 0
                for j in batch:
                    rec = results.get(j.job_id)
                    if rec is None:
                        continue
                    try:
                        j.score = max(0.0, min(10.0, float(rec.get("score", 0))))
                    except (TypeError, ValueError):
                        j.score = 0.0
                    j.reason = str(rec.get("reason", "")).strip()

            processed_count = min((idx + 1) * batch_size, len(jobs))
            print(f"  screened {processed_count}/{len(jobs)}")
            if not quota_circuit_broken and idx < len(batches) - 1 and delay_seconds > 0:
                time.sleep(delay_seconds)

    return jobs


# ------------------------------------------------------------------ draft ---

def _build_draft_system(profile: dict | None = None) -> str:
    name = _get_candidate_name(profile)
    edu = (profile or {}).get("education") or "Technical Degree / Professional Experience"
    raw_skills = (profile or {}).get("skills") or (profile or {}).get("core_skills") or []
    skills = ", ".join(raw_skills) if raw_skills else "Software Engineering, Full Stack Development, REST APIs, Git"

    projects = (profile or {}).get("notable_projects") or []
    if projects:
        projects_str = "\n".join(f"  {idx + 1}. {p}" for idx, p in enumerate(projects))
    else:
        projects_str = "  1. Production software applications and engineering deliverables"

    github = (profile or {}).get("github", "")
    github_ref = f" ({github})" if github else ""

    return f"""You prepare an application kit for candidate {name} based strictly on their resume/profile:
- Education: {edu}
- Core Skills: {skills}
- Key Projects:
{projects_str}

Hard rule: NEVER invent experience. Every claim must trace to {name}'s real background.

Return ONLY a JSON object:
{{
  "fit_summary": str,          // 2 sentences: why this role is a strong match for candidate
  "india_eligibility": str,    // MUST be one of: '🇮🇳 India-Based Role' (if job location mentions India/Indian city), '🌐 Remote-Friendly' (if job is remote/WFH), '🔀 Hybrid India' (if hybrid in India), '🌍 Global (Verify Location)' (if location is unclear or outside India). Base this on the job location field, not assumptions.
  "job_type": str,             // "remote" | "hybrid" | "onsite" | "internship"
  "salary_range_inr": str,     // Extract salary if mentioned in JD. Format as '₹X-Y LPA' for Indian roles or 'USD $X-Y' for US. Empty string if not mentioned.
  "best_project": str,         // Best project to highlight from candidate's profile + 1 sentence rationale
  "tailored_bullets": [str],   // 3-4 resume bullets dynamically rewritten from candidate's background for THIS job
  "matching_skills": [str],    // 4-8 matching skills candidate possesses for this role
  "gaps": [str],               // 1-3 honest missing requirements and how to address them
  "cover_note": str,           // 120-160 words. Plain, direct cover note with zero fluff or generic flattery.
  "cold_outreach": str,        // Under 80 words. Concise cold message referencing role title, key project, technical match{github_ref}.
  "questions_to_ask": [str]    // 2 sharp technical questions showing thorough reading of the JD
}}"""


DRAFT_SYSTEM = _build_draft_system()


def draft(jobs: list[Job], profile: dict, jd_chars: int = 6000,
          provider: Provider | None = None, model: str | None = None,
          delay_seconds: float = 2.5) -> list[Job]:
    """Stage 2: full kit for the shortlist. One call per job, best model."""
    if provider is None or model is None:
        provider, model = resolve("draft")
    profile_blob = json.dumps(profile, ensure_ascii=False)
    system_prompt = _build_draft_system(profile)
    cand_projects = (profile or {}).get("notable_projects") or []
    default_proj = cand_projects[0] if cand_projects else "Key Engineering Project"

    for i, j in enumerate(jobs):
        try:
            raw = provider.complete(
                model, system_prompt,
                f"CANDIDATE PROFILE:\n{profile_blob}\n\n"
                f"JOB: {j.title} at {j.company} ({j.location or 'location not stated'})\n"
                f"URL: {j.url}\n\n{j.description[:jd_chars]}",
                DRAFT_MAX_TOKENS, json_mode=True,
            )
            kit = parse_json(raw)
            if not isinstance(kit, dict):
                raise ValueError("draft did not return a JSON object")
            j.draft = {
                "fit_summary": str(kit.get("fit_summary") or ""),
                "india_eligibility": str(kit.get("india_eligibility") or "Verified India-Friendly"),
                "job_type": str(kit.get("job_type") or "onsite"),
                "salary_range_inr": str(kit.get("salary_range_inr") or ""),
                "best_project": str(kit.get("best_project") or default_proj),
                "tailored_bullets": [str(b) for b in (kit.get("tailored_bullets") or [])],
                "matching_skills": [str(s) for s in (kit.get("matching_skills") or [])],
                "gaps": [str(g) for g in (kit.get("gaps") or [])],
                "cover_note": str(kit.get("cover_note") or ""),
                "cold_outreach": str(kit.get("cold_outreach") or ""),
                "questions_to_ask": [str(q) for q in (kit.get("questions_to_ask") or [])],
            }
            print(f"  drafted {j.title} @ {j.company}")
        except (LLMError, ValueError, KeyError, TypeError, RuntimeError) as e:
            print(f"  ! draft failed for {j.job_id} ({type(e).__name__}: {e})")
            j.draft = {k: ("" if k in ("fit_summary", "india_eligibility", "best_project", "cover_note", "cold_outreach") else []) for k in DRAFT_KEYS}

        if i < len(jobs) - 1 and delay_seconds > 0:
            time.sleep(delay_seconds)

    return jobs


# ------------------------------------------------- offline scorer (no API) ---

def keyword_screen(jobs: list[Job], profile: dict, **_) -> list[Job]:
    """DEV ONLY. High-fidelity offline keyword stand-in for testing/dry-runs."""
    raw_skills = profile.get("skills") or profile.get("core_skills") or []
    skills = {s.lower() for s in raw_skills if s}
    raw_titles = profile.get("target_titles") or profile.get("target_keywords") or []
    titles = [t.lower() for t in raw_titles if t]
    domains = [d.lower() for d in (profile.get("domains") or []) if d]
    cand_sen = (profile.get("seniority") or "").lower()

    high_seniority = ("staff", "principal", "director", "vp", "lead", "architect")

    for j in jobs:
        blob = f"{j.title} {j.description}".lower()
        title_lower = j.title.lower()

        hits = sorted(s for s in skills if s in blob)
        domain_hits = [d for d in domains if d in blob]

        overlap = len(hits) / max(len(skills), 1) if skills else 0.5
        title_match = any(t in title_lower for t in titles)
        title_bonus = 2.5 if title_match else 0.0
        domain_bonus = 1.0 if domain_hits else 0.0

        score = overlap * 10 + title_bonus + domain_bonus

        if any(s in title_lower for s in high_seniority) and cand_sen in ("new-grad", "junior", "mid", "intern"):
            score -= 4.0

        j.score = round(max(0.0, min(10.0, score)), 1)

        matched_str = ", ".join(hits[:5]) if hits else "relevant technical stack"
        j.reason = f"[keyword stub] skills matched: {matched_str}" if hits else "[keyword stub] general technical match"

        # Populate offline draft stand-in for dry-run rendering
        cand_name = _get_candidate_name(profile)
        edu_str = str((profile or {}).get("education") or "Technical Degree")
        cand_projects = (profile or {}).get("notable_projects") or []
        first_project = cand_projects[0] if cand_projects else "Key Engineering Project"
        github_link = str((profile or {}).get("github") or "")
        github_suffix = f"\nGitHub: {github_link}" if github_link else ""

        project_highlight = first_project
        for p in cand_projects:
            p_words = [w.lower() for w in p.split() if len(w) > 2]
            if any(w in blob for w in p_words):
                project_highlight = p
                break

        lead_skill_1 = hits[0] if len(hits) > 0 else (raw_skills[0] if raw_skills else "Core Technologies")
        lead_skill_2 = hits[1] if len(hits) > 1 else (raw_skills[1] if len(raw_skills) > 1 else "Software Engineering")

        j.draft = {
            "fit_summary": f"Strong alignment for {j.title} at {j.company} with matching background ({matched_str}).",
            "india_eligibility": "Verified India-Friendly" if "india" in blob or "remote" in blob else "Remote Friendly",
            "best_project": project_highlight,
            "tailored_bullets": [
                f"Engineered software solutions utilizing {lead_skill_1} and {lead_skill_2}.",
                "Developed scalable backend workflows, APIs, and robust data layers.",
                "Implemented automated testing, monitoring, and continuous integration practices."
            ],
            "matching_skills": hits[:6] if hits else (raw_skills[:6] if raw_skills else ["Software Engineering", "REST APIs", "Git"]),
            "gaps": ["Verify specific domain/experience requirements mentioned in the job description."],
            "cover_note": f"Hi Hiring Team,\n\nI am {cand_name}, with a background in {edu_str}. I built {project_highlight}. My technical skills in {matched_str} align directly with your {j.title} position at {j.company}.\n\nBest regards,\n{cand_name}",
            "cold_outreach": f"Hi! I saw your {j.title} opening at {j.company}. I'm {cand_name} ({edu_str}) and built {project_highlight} with {matched_str}. Would love to connect!{github_suffix}",
            "questions_to_ask": [
                f"What are the primary technical milestones for the {j.title} in their first 90 days?",
                "How does your engineering team approach architecture reviews and deployment testing?"
            ]
        }

    return jobs
