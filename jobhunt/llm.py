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
SCREEN_MAX_TOKENS = 8000
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
  "target_titles": [str],      // roles this person should realistically aim at
  "seniority": str             // intern | new-grad | junior | mid | senior | staff
}"""


def build_profile(resume_bytes: bytes | None = None, resume_text: str | None = None,
                  is_pdf: bool = False, provider: Provider | None = None,
                  model: str | None = None) -> dict:
    """Resume (PDF or text) -> profile.json. Uses the draft-stage model."""
    if provider is None or model is None:
        provider, model = resolve("draft")

    if is_pdf and resume_bytes:
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
    return "Tanish Sanghvi"


def _build_screen_system(profile: dict | None = None) -> str:
    name = _get_candidate_name(profile)
    edu = (profile or {}).get("education", "")
    yoe = (profile or {}).get("years_experience")
    context = f"candidate {name}"
    details = []
    if edu:
        details.append(str(edu))
    if yoe is not None:
        details.append(f"{yoe} YoE")
    if details:
        context += f" ({', '.join(details)})"

    return f"""You screen job postings for {context}. You are strict.

Score 0-10 on genuine fit:
  9-10  strong match, candidate clears the bar (Full Stack, Backend, AI Engineer, 0-2 YoE / Intern)
  7-8   good match, worth applying
  5-6   plausible but real gaps or minor location ambiguity
  0-4   wrong seniority (Staff/Senior/Lead), restricted location (US/EU residency required), wrong stack, or missing core requirements

Check India / Timezone eligibility:
  - Is India explicitly allowed or Worldwide remote? Mark as Verified India-Friendly.
  - Does it require US/EU citizenship or local work authorization? If yes, score 0-3 and mark as Restricted.

Return ONLY a JSON array, one object per job, no prose:
[{{\"job_id\": str, \"score\": number, \"reason\": str}}]
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
        with ThreadPoolExecutor(max_workers=min(max_workers, len(batches))) as executor:
            future_to_batch = {
                executor.submit(process_batch, idx + 1, batch): (idx + 1, batch)
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(future_to_batch):
                n, batch = future_to_batch[future]
                results = future.result()
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
        for idx, batch in enumerate(batches):
            results = process_batch(idx + 1, batch)
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
            if idx < len(batches) - 1 and delay_seconds > 0:
                time.sleep(delay_seconds)

    return jobs


# ------------------------------------------------------------------ draft ---

def _build_draft_system(profile: dict | None = None) -> str:
    name = _get_candidate_name(profile)
    edu = (profile or {}).get("education", "B.E. Automation & Robotics Engineering, VESIT Mumbai (2027 Grad, CGPA 7.33)")
    skills = ", ".join(profile.get("core_skills", [])) if (profile and profile.get("core_skills")) else (
        "React.js, Next.js, Node.js, Express.js, Python, Flask, MongoDB, Firestore, REST APIs, Firebase Auth, Gemini AI API, Jest, Playwright, Tailwind CSS"
    )
    projects = profile.get("notable_projects", []) if (profile and profile.get("notable_projects")) else [
        "Edvanta — AI-Powered Educational Platform (33 Flask/MongoDB API routes, Gemini AI integration, Hack Celestial 2.0 National Finalist)",
        "Department Ledger Portal — Academic Record System (Next.js, Firebase Auth/Firestore, Gemini API, 77 Jest tests, 5 Playwright E2E gates, rate limiting)",
        "DineEase — Full-Stack Menu & Order System (React, Node.js, Express, MongoDB, 14 REST APIs)",
    ]
    projects_str = "\n".join(f"  {idx + 1}. {p}" for idx, p in enumerate(projects))
    github = (profile or {}).get("github", "https://github.com/tanish-jain-225")

    return f"""You prepare an application kit for candidate {name} based strictly on their resume/profile:
- Education: {edu}
- Core Skills: {skills}
- Key Projects:
{projects_str}

Hard rule: NEVER invent experience. Every claim must trace to {name}'s real background.

Return ONLY a JSON object:
{{
  "fit_summary": str,          // 2 sentences: why this role is a strong match for candidate
  "india_eligibility": str,    // "Verified India-Friendly" | "Asia Remote / IST Overlap" | "India Eligibility Unverified"
  "best_project": str,         // Best project to highlight from candidate's profile + 1 sentence rationale
  "tailored_bullets": [str],   // 3-4 resume bullets dynamically rewritten from candidate's background for THIS job
  "matching_skills": [str],    // 4-8 matching skills candidate possesses for this role
  "gaps": [str],               // 1-3 honest missing requirements and how to address them
  "cover_note": str,           // 120-160 words. Plain, direct cover note with zero fluff or generic flattery.
  "cold_outreach": str,        // Under 80 words. Concise cold message referencing role title, key project, technical match, and GitHub link ({github}).
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
                "best_project": str(kit.get("best_project") or "Edvanta (AI-Powered Educational Platform)"),
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
    skills = {s.lower() for s in profile.get("core_skills", []) if s}
    titles = [t.lower() for t in profile.get("target_titles", []) if t]
    domains = [d.lower() for d in profile.get("domains", []) if d]
    cand_sen = (profile.get("seniority") or "").lower()

    high_seniority = ("staff", "principal", "director", "vp", "lead", "architect")

    for j in jobs:
        blob = f"{j.title} {j.description}".lower()
        title_lower = j.title.lower()

        hits = sorted(s for s in skills if s in blob)
        domain_hits = [d for d in domains if d in blob]

        overlap = len(hits) / max(len(skills), 1)
        title_match = any(t in title_lower for t in titles)
        title_bonus = 2.5 if title_match else 0.0
        domain_bonus = 1.0 if domain_hits else 0.0

        score = overlap * 10 + title_bonus + domain_bonus

        if any(s in title_lower for s in high_seniority) and cand_sen in ("new-grad", "junior", "mid", "intern"):
            score -= 4.0

        j.score = round(max(0.0, min(10.0, score)), 1)

        matched_str = ", ".join(hits[:5]) if hits else "none"
        j.reason = f"[keyword stub] skills matched: {matched_str}" if hits else "[keyword stub] no skill overlap"

        # Populate offline draft stand-in for dry-run rendering
        cand_name = _get_candidate_name(profile)
        edu_str = str((profile or {}).get("education") or "VESIT 2027 Grad")
        cand_projects = (profile or {}).get("notable_projects") or []
        first_project = cand_projects[0] if cand_projects else "Edvanta (AI Platform)"
        github_link = str((profile or {}).get("github") or "https://github.com/tanish-jain-225")

        project_highlight = first_project
        if any(p for p in cand_projects if "ai" in p.lower() or "python" in p.lower()) and ("ai" in blob or "python" in blob):
            project_highlight = next(p for p in cand_projects if "ai" in p.lower() or "python" in p.lower())
        elif any(p for p in cand_projects if "next" in p.lower() or "test" in p.lower()) and ("next" in blob or "test" in blob):
            project_highlight = next(p for p in cand_projects if "next" in p.lower() or "test" in p.lower())

        lead_skill_1 = hits[0] if len(hits) > 0 else (profile.get("core_skills", ["React.js"])[0] if profile.get("core_skills") else "React.js")
        lead_skill_2 = hits[1] if len(hits) > 1 else (profile.get("core_skills", ["", "Node.js"])[1] if len(profile.get("core_skills", [])) > 1 else "Node.js")

        j.draft = {
            "fit_summary": f"Strong alignment for {j.title} at {j.company} with core stack match ({matched_str}).",
            "india_eligibility": "Verified India-Friendly" if "india" in blob or "remote" in blob else "India Eligibility Unverified",
            "best_project": project_highlight,
            "tailored_bullets": [
                f"Built scalable web applications utilizing {lead_skill_1} and {lead_skill_2}.",
                "Developed RESTful backend API routes with robust authentication and structured data stores.",
                "Integrated automated testing pipelines and modern software engineering workflows."
            ],
            "matching_skills": hits[:6] if hits else (profile.get("core_skills", ["React.js", "Node.js", "Python", "REST APIs"])[:6]),
            "gaps": ["Verify specific domain/experience requirements mentioned in the job description."],
            "cover_note": f"Hi Hiring Team,\n\nI am {cand_name}, with background in {edu_str}. I built {project_highlight}. My technical skills in {matched_str} align directly with your {j.title} position at {j.company}.\n\nBest regards,\n{cand_name}",
            "cold_outreach": f"Hi! I saw your {j.title} opening at {j.company}. I'm {cand_name} ({edu_str}) and built {project_highlight} using {matched_str}. Would love to connect!\nGitHub: {github_link}",
            "questions_to_ask": [
                f"What are the primary technical milestones for the {j.title} in their first 90 days?",
                "How does your engineering team approach architecture reviews and deployment testing?"
            ]
        }

    return jobs


