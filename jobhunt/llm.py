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

DRAFT_KEYS = ("fit_summary", "tailored_bullets", "gaps", "cover_note", "questions_to_ask")

# Output ceilings per stage. These are deliberately generous: reasoning models
# (Gemini 2.5+, and anything with thinking on) spend output tokens before the
# answer starts, so a ceiling sized to the visible answer gets consumed and you
# get truncated JSON instead of a result.
SCREEN_MAX_TOKENS = 8000
DRAFT_MAX_TOKENS = 8000
PROFILE_MAX_TOKENS = 4000


def parse_json(raw: str) -> Any:
    """Parse a model reply that is *supposed* to be JSON.

    Models wrap JSON in ```fences```, open with "Here is the JSON:", or return
    an object where you asked for an array. All three show up in practice, so
    this is deliberately forgiving: strip fences, try straight, then fall back
    to the outermost bracketed span.
    """
    if raw is None:
        raise ValueError("empty model reply")
    cleaned = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", raw)).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    # Preamble before the payload, or trailing commentary after it.
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
        # Check known keys first, then fall back to any list-valued key.
        for key in ("jobs", "results", "scores", "items"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return [p for p in inner if isinstance(p, dict)]
        # Fallback: if the dict has exactly one list-valued key, use it.
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
  "domains": [str],            // e.g. "distributed systems", "CDN", "frontend"
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

SCREEN_SYSTEM = """You screen job postings for one candidate. You are strict.

Score 0-10 on genuine fit:
  9-10  strong match, candidate clears the bar and the role is a step up
  7-8   good match, worth applying
  5-6   plausible but real gaps
  0-4   wrong seniority, wrong stack, or a hard requirement the candidate lacks

Seniority mismatch is the most common failure: a 3-year engineer scoring an 8
on a Staff role is wrong. Penalise it hard, in both directions — a senior
engineer does not want an internship either. Do the same for hard requirements
the candidate plainly does not meet: security clearance, a specific degree, a
named technology with a year count they cannot hit, or a country they cannot
work in.

Do not inflate scores to be encouraging. Most postings are a 4.

Return ONLY a JSON array, one object per job, no prose:
[{"job_id": str, "score": number, "reason": str}]
Echo `job_id` back exactly as given. `reason` is one sentence, max 20 words,
concrete about the deciding factor."""


def screen(jobs: list[Job], profile: dict, batch_size: int = 8, jd_chars: int = 1400,
           provider: Provider | None = None, model: str | None = None,
           delay_seconds: float = 2.5, max_workers: int = 1) -> list[Job]:
    """Stage 1: score every surviving job. Mutates and returns `jobs`.

    A batch that fails to parse logs a warning and is skipped — one bad reply
    must not take down the whole run.
    """
    if provider is None or model is None:
        provider, model = resolve("screen")
    batch_size = max(1, int(batch_size))
    profile_blob = json.dumps(profile, ensure_ascii=False)
    batches = [jobs[i:i + batch_size] for i in range(0, len(jobs), batch_size)]

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
                model, SCREEN_SYSTEM,
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

DRAFT_SYSTEM = """You prepare an application kit for one job.

Hard rule: never invent experience. Every claim must trace to something in the
candidate profile. If the profile does not support a claim, it goes in `gaps`,
not in a bullet.

Return ONLY a JSON object, no prose:
{
  "fit_summary": str,          // 2 sentences: why this is worth their time
  "tailored_bullets": [str],   // 3-4 resume bullets rewritten for THIS job,
                               // using only real experience from the profile,
                               // each with a concrete artefact or number
  "gaps": [str],               // 1-3 honest gaps, each with how to address it
  "cover_note": str,           // 120-160 words. Plain. No "I am writing to
                               // express my interest", no "I am excited to",
                               // no flattery about the company's mission.
                               // Open with a concrete reason they fit this role.
  "questions_to_ask": [str]    // 2 sharp questions that show they read the JD
}"""


def draft(jobs: list[Job], profile: dict, jd_chars: int = 6000,
          provider: Provider | None = None, model: str | None = None,
          delay_seconds: float = 2.5) -> list[Job]:
    """Stage 2: full kit for the shortlist. One call per job, best model."""
    if provider is None or model is None:
        provider, model = resolve("draft")
    profile_blob = json.dumps(profile, ensure_ascii=False)

    for i, j in enumerate(jobs):
        try:
            raw = provider.complete(
                model, DRAFT_SYSTEM,
                f"CANDIDATE PROFILE:\n{profile_blob}\n\n"
                f"JOB: {j.title} at {j.company} ({j.location or 'location not stated'})\n"
                f"URL: {j.url}\n\n{j.description[:jd_chars]}",
                DRAFT_MAX_TOKENS, json_mode=True,
            )
            kit = parse_json(raw)
            if not isinstance(kit, dict):
                raise ValueError("draft did not return a JSON object")
            # Normalise so the digest template never has to guess.
            j.draft = {
                "fit_summary": str(kit.get("fit_summary") or ""),
                "tailored_bullets": [str(b) for b in (kit.get("tailored_bullets") or [])],
                "gaps": [str(g) for g in (kit.get("gaps") or [])],
                "cover_note": str(kit.get("cover_note") or ""),
                "questions_to_ask": [str(q) for q in (kit.get("questions_to_ask") or [])],
            }
            print(f"  drafted {j.title} @ {j.company}")
        except (LLMError, ValueError, KeyError, TypeError, RuntimeError) as e:
            print(f"  ! draft failed for {j.job_id} ({type(e).__name__}: {e})")
            j.draft = {k: ("" if k in ("fit_summary", "cover_note") else []) for k in DRAFT_KEYS}

        if i < len(jobs) - 1 and delay_seconds > 0:
            time.sleep(delay_seconds)

    return jobs


# ------------------------------------------------- offline scorer (no API) ---

def keyword_screen(jobs: list[Job], profile: dict, **_) -> list[Job]:
    """DEV ONLY. High-fidelity offline keyword stand-in for testing/dry-runs.

    Evaluates skill matches, target titles, domain matches, and penalizes
    seniority mismatches so offline digests mimic production LLM outputs.
    """
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

        # Seniority penalty if role is staff/principal/director but candidate is junior/mid/new-grad
        if any(s in title_lower for s in high_seniority) and cand_sen in ("new-grad", "junior", "mid", "intern"):
            score -= 4.0

        j.score = round(max(0.0, min(10.0, score)), 1)

        matched_str = ", ".join(hits[:5]) if hits else "none"
        j.reason = f"[keyword stub] skills matched: {matched_str}" if hits else "[keyword stub] no skill overlap"

    return jobs

