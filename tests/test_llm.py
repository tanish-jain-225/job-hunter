"""LLM layer with the provider stubbed out. No key, no network, no cost.

Asserts the four things that actually break in production:
  1. batching splits the way config says it does
  2. JD truncation really is applied before the text goes over the wire
  3. the JSON parser survives fences, preambles and object-or-array replies
  4. scores land on the right job, and a bad batch does not kill the run
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobhunt import llm
from jobhunt.fetch import Job
from jobhunt.providers import Provider

PROFILE = {"core_skills": ["Go", "Kubernetes"], "target_titles": ["Backend Engineer"],
           "seniority": "mid", "years_experience": 3}


class StubProvider(Provider):
    """Records every call and replays canned replies in order."""

    name = "stub"

    def __init__(self, replies: list[str] | None = None):
        self.replies = list(replies or [])
        self.calls: list[dict] = []

    def complete(self, model, system, user, max_tokens, json_mode=False):
        self.calls.append({"model": model, "system": system, "user": user,
                           "max_tokens": max_tokens, "json_mode": json_mode})
        if not self.replies:
            return "[]"
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    # convenience: the JOBS payload the stage actually sent
    def payload(self, i: int = 0) -> list[dict]:
        return json.loads(self.calls[i]["user"].split("JOBS:\n", 1)[1])


def make_jobs(n: int, desc: str = "Go and Kubernetes at scale.") -> list[Job]:
    return [Job(job_id=f"greenhouse:acme:{i}", ats="greenhouse", company="Acme",
                title=f"Backend Engineer {i}", location="Bangalore",
                url=f"https://example.com/{i}", description=desc)
            for i in range(n)]


def scores_reply(jobs, score=8.0, reason="fits"):
    return json.dumps([{"job_id": j.job_id, "score": score, "reason": reason}
                       for j in jobs])


# ------------------------------------------------------- tolerant JSON -----

@pytest.mark.parametrize("raw,expected", [
    ('[{"a": 1}]', [{"a": 1}]),
    ('```json\n[{"a": 1}]\n```', [{"a": 1}]),
    ('```\n[{"a": 1}]\n```', [{"a": 1}]),
    ('Here is the JSON you asked for:\n[{"a": 1}]', [{"a": 1}]),
    ('[{"a": 1}]\n\nLet me know if you need anything else!', [{"a": 1}]),
    ('```json\nSure —\n{"a": 1}\n```\nDone.', {"a": 1}),
    ('  {"a": 1}  ', {"a": 1}),
])
def test_parse_json_survives_real_model_habits(raw, expected):
    assert llm.parse_json(raw) == expected


@pytest.mark.parametrize("raw", ["", "no json at all", "{broken", None])
def test_parse_json_raises_on_garbage(raw):
    with pytest.raises(ValueError):
        llm.parse_json(raw)


def test_as_list_accepts_array_wrapped_object_and_bare_object():
    assert llm._as_list([{"job_id": "a"}]) == [{"job_id": "a"}]
    assert llm._as_list({"jobs": [{"job_id": "a"}]}) == [{"job_id": "a"}]
    assert llm._as_list({"job_id": "a"}) == [{"job_id": "a"}]


# ------------------------------------------------------------- batching ----

def test_screen_splits_into_batches_of_the_configured_size():
    jobs = make_jobs(20)
    stub = StubProvider([scores_reply(jobs[i:i + 8]) for i in (0, 8, 16)])

    llm.screen(jobs, PROFILE, batch_size=8, provider=stub, model="m")

    assert len(stub.calls) == 3
    assert [len(stub.payload(i)) for i in range(3)] == [8, 8, 4]


def test_screen_honours_batch_size_of_1():
    jobs = make_jobs(3)
    stub = StubProvider([scores_reply([jobs[i]]) for i in range(3)])

    llm.screen(jobs, PROFILE, batch_size=1, provider=stub, model="m")

    assert len(stub.calls) == 3
    assert [len(stub.payload(i)) for i in range(3)] == [1, 1, 1]


def test_screen_truncates_jd_to_the_configured_length():
    jobs = make_jobs(1, desc="X" * 5000)
    stub = StubProvider([scores_reply(jobs)])

    llm.screen(jobs, PROFILE, batch_size=8, jd_chars=1400, provider=stub, model="m")

    sent = stub.payload(0)[0]["description"]
    assert len(sent) == 1400


# ------------------------------------------------------------ resilience ----

def test_screen_assigns_scores_to_the_right_job():
    jobs = make_jobs(2)
    # Model returns results out of order
    reply = json.dumps([
        {"job_id": jobs[1].job_id, "score": 9.5, "reason": "strong"},
        {"job_id": jobs[0].job_id, "score": 4.0, "reason": "weak"},
    ])
    stub = StubProvider([reply])

    llm.screen(jobs, PROFILE, provider=stub, model="m")

    assert jobs[0].score == 4.0 and jobs[0].reason == "weak"
    assert jobs[1].score == 9.5 and jobs[1].reason == "strong"


def test_screen_survives_a_failed_batch_and_continues():
    jobs = make_jobs(16)
    # Batch 1 raises an exception, Batch 2 succeeds
    stub = StubProvider([RuntimeError("500 internal server error"), scores_reply(jobs[8:])])

    llm.screen(jobs, PROFILE, batch_size=8, provider=stub, model="m")

    # First batch is unscored, second batch scored normally
    assert all(j.score is None for j in jobs[:8])
    assert all(j.score == 8.0 for j in jobs[8:])


def test_screen_clamps_scores_to_0_10():
    jobs = make_jobs(2)
    reply = json.dumps([
        {"job_id": jobs[0].job_id, "score": 15.0},
        {"job_id": jobs[1].job_id, "score": -3.0},
    ])
    stub = StubProvider([reply])

    llm.screen(jobs, PROFILE, provider=stub, model="m")

    assert jobs[0].score == 10.0
    assert jobs[1].score == 0.0


# ----------------------------------------------------------------- draft ----

def test_draft_populates_every_key_the_digest_template_expects():
    jobs = make_jobs(1)
    kit = {
        "fit_summary": "Great match.",
        "tailored_bullets": ["Built X with Go."],
        "gaps": ["No K8s in production."],
        "cover_note": "Hi team, I built Go services.",
        "questions_to_ask": ["How big is the team?"],
    }
    stub = StubProvider([json.dumps(kit)])

    llm.draft(jobs, PROFILE, provider=stub, model="m")

    d = jobs[0].draft
    assert set(d.keys()) == set(llm.DRAFT_KEYS)
    assert d["fit_summary"] == "Great match."
    assert d["tailored_bullets"] == ["Built X with Go."]


def test_draft_falls_back_to_empty_kit_when_model_fails():
    jobs = make_jobs(1)
    stub = StubProvider([RuntimeError("rate limit")])

    llm.draft(jobs, PROFILE, provider=stub, model="m", delay_seconds=0)

    d = jobs[0].draft
    assert set(d.keys()) == set(llm.DRAFT_KEYS)
    assert d["fit_summary"] == "" and d["tailored_bullets"] == []


def test_screen_concurrency_and_delays():
    jobs = make_jobs(16)
    stub = StubProvider([scores_reply(jobs[:8]), scores_reply(jobs[8:])])

    llm.screen(jobs, PROFILE, batch_size=8, provider=stub, model="m",
               delay_seconds=0, max_workers=2)

    assert len(stub.calls) == 2
    assert all(j.score == 8.0 for j in jobs)


def test_enhanced_keyword_screen():
    profile = {
        "core_skills": ["Go", "Python"],
        "target_titles": ["Backend Engineer"],
        "domains": ["Distributed Systems"],
        "seniority": "junior"
    }

    matching_job = Job("greenhouse:a:1", "greenhouse", "Acme", "Backend Engineer", "Remote",
                       "http://ex.com", "Go Python Distributed Systems core engineering")
    staff_job = Job("greenhouse:a:2", "greenhouse", "Acme", "Staff Software Engineer", "Remote",
                    "http://ex.com", "Go Python Distributed Systems core engineering")

    jobs = [matching_job, staff_job]
    llm.keyword_screen(jobs, profile)

    assert matching_job.score > staff_job.score
    assert "skills matched" in matching_job.reason


def test_build_profile_text_and_pdf(monkeypatch: pytest.MonkeyPatch):
    class MockDocProvider(Provider):
        def complete(self, *a, **kw):
            return json.dumps({"name": "Jane", "core_skills": ["Go"]})

        def complete_document(self, *a, **kw):
            return json.dumps({"name": "Jane PDF", "core_skills": ["Python"]})

    p = MockDocProvider()

    prof_text = llm.build_profile(resume_text="Resume text", provider=p, model="m")
    assert prof_text["name"] == "Jane"

    prof_pdf = llm.build_profile(resume_bytes=b"%PDF...", is_pdf=True, provider=p, model="m")
    assert prof_pdf["name"] == "Jane PDF"


def test_build_profile_pdf_error(monkeypatch: pytest.MonkeyPatch):
    class ErrDocProvider(Provider):
        def complete_document(self, *a, **kw):
            from jobhunt.providers import LLMError
            raise LLMError("PDF error")

    p = ErrDocProvider()
    with pytest.raises(llm.LLMError, match="export your resume"):
        llm.build_profile(resume_bytes=b"%PDF...", is_pdf=True, provider=p, model="m")


def test_as_list_single_key_fallback():
    data = {"custom_key": [{"job_id": "1", "score": 9.0}]}
    assert llm._as_list(data) == [{"job_id": "1", "score": 9.0}]


def test_screen_concurrency_invalid_score(monkeypatch: pytest.MonkeyPatch):
    jobs = make_jobs(2)
    reply = json.dumps([
        {"job_id": jobs[0].job_id, "score": "invalid_score"},
        {"job_id": jobs[1].job_id, "score": 8.0},
    ])
    stub = StubProvider([reply])
    llm.screen(jobs, PROFILE, batch_size=2, provider=stub, model="m", max_workers=2)
    assert jobs[0].score == 0.0
    assert jobs[1].score == 8.0


def test_dynamic_prompt_builders():
    prof = {
        "name": "Jane Developer",
        "education": "M.S. Computer Science, Stanford 2025",
        "years_experience": 2,
        "core_skills": ["Rust", "Python", "System Design"],
        "notable_projects": ["Custom DB Engine — Rust key-value store"],
        "github": "https://github.com/janedev"
    }
    screen_sys = llm._build_screen_system(prof)
    assert "candidate Jane Developer" in screen_sys
    assert "M.S. Computer Science" in screen_sys

    draft_sys = llm._build_draft_system(prof)
    assert "Jane Developer" in draft_sys
    assert "Custom DB Engine" in draft_sys
    assert "https://github.com/janedev" in draft_sys


def test_build_profile_invalid_non_dict(monkeypatch: pytest.MonkeyPatch):
    class NonDictProvider(Provider):
        def complete(self, *a, **kw):
            return json.dumps(["not", "a", "dict"])

    p = NonDictProvider()
    with pytest.raises(ValueError, match="did not return a JSON object"):
        llm.build_profile(resume_text="Text", provider=p, model="m")



