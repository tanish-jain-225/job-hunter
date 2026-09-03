"""Property-based tests for ATS parsers using Hypothesis.

These tests verify that all 9 ATS parsers are robust against arbitrary input shapes —
they must never raise an exception regardless of what the ATS endpoint returns.
Hand-crafted fixtures miss edge cases; Hypothesis finds them in minutes.

Run with: pytest tests/test_parsers_hypothesis.py -v
"""

from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis", reason="hypothesis not installed — pip install hypothesis")
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from jobhunt.fetch import (
    parse_greenhouse,
    parse_lever,
    parse_ashby,
    parse_workable,
    parse_smartrecruiters,
    parse_bamboohr,
    parse_recruitee,
    parse_breezy,
    parse_pinpoint,
    Job,
)


# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

_text = st.text(min_size=0, max_size=200)
_opt_text = st.none() | _text
_opt_int = st.none() | st.integers(min_value=0, max_value=9_999_999)
_slug = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L",)))  # type: ignore[arg-type]

_greenhouse_job = st.fixed_dictionaries(
    {
        "id": st.integers() | _text,
        "title": _text,
        "location": st.none() | st.fixed_dictionaries({"name": _text}),
        "content": _opt_text,
        "absolute_url": _opt_text,
        "updated_at": _opt_text,
    }
)

_lever_job = st.fixed_dictionaries(
    {
        "id": _text,
        "text": _text,
        "categories": st.none()
        | st.fixed_dictionaries(
            {
                "location": _opt_text,
                "team": _opt_text,
            }
        ),
        "description": _opt_text,
        "descriptionPlain": _opt_text,
        "hostedUrl": _opt_text,
        "createdAt": st.none() | st.integers(),
    }
)

_ashby_job = st.fixed_dictionaries(
    {
        "id": _text,
        "title": _text,
        "location": st.none() | st.fixed_dictionaries({"name": _text}),
        "descriptionSafe": _opt_text,
        "jobUrl": _opt_text,
        "publishedDate": _opt_text,
    }
)

_workable_job = st.fixed_dictionaries(
    {
        "shortcode": _text,
        "title": _text,
        "city": _opt_text,
        "country": _opt_text,
        "description": _opt_text,
        "url": _opt_text,
        "published_on": _opt_text,
    }
)


# ---------------------------------------------------------------------------
# Per-parser fuzz tests
# ---------------------------------------------------------------------------


@given(
    slug=_slug,
    body=st.fixed_dictionaries({"jobs": st.lists(_greenhouse_job, max_size=10)})
    | st.just({})
    | st.just({"jobs": None})
    | st.just(None),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_parse_greenhouse_never_raises(slug: str, body) -> None:
    """parse_greenhouse must never raise, regardless of body shape."""
    result = parse_greenhouse(slug, "TestCo", body)
    assert isinstance(result, list)
    for job in result:
        assert isinstance(job, Job)
        assert job.job_id.startswith("greenhouse:")
        assert isinstance(job.title, str)
        assert isinstance(job.location, str)


@given(
    slug=_slug,
    body=st.lists(_lever_job, max_size=10) | st.just([]) | st.just(None) | st.just({}),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_parse_lever_never_raises(slug: str, body) -> None:
    """parse_lever must never raise, regardless of body shape."""
    result = parse_lever(slug, "TestCo", body)
    assert isinstance(result, list)
    for job in result:
        assert isinstance(job, Job)
        assert job.job_id.startswith("lever:")


@given(
    slug=_slug,
    body=st.fixed_dictionaries({"jobPostings": st.lists(_ashby_job, max_size=10)}) | st.just({}) | st.just(None),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_parse_ashby_never_raises(slug: str, body) -> None:
    """parse_ashby must never raise, regardless of body shape."""
    result = parse_ashby(slug, "TestCo", body)
    assert isinstance(result, list)
    for job in result:
        assert isinstance(job, Job)
        assert job.job_id.startswith("ashby:")


@given(
    slug=_slug,
    body=st.fixed_dictionaries({"jobs": st.lists(_workable_job, max_size=10)}) | st.just({}) | st.just(None),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_parse_workable_never_raises(slug: str, body) -> None:
    """parse_workable must never raise, regardless of body shape."""
    result = parse_workable(slug, "TestCo", body)
    assert isinstance(result, list)
    for job in result:
        assert isinstance(job, Job)
        assert job.job_id.startswith("workable:")


@given(
    slug=_slug,
    body=st.fixed_dictionaries(
        {
            "content": st.lists(
                st.fixed_dictionaries(
                    {
                        "id": _text,
                        "name": _text,
                        "location": st.none() | st.fixed_dictionaries({"city": _opt_text, "country": _opt_text}),
                        "jobAd": st.none()
                        | st.fixed_dictionaries(
                            {
                                "sections": st.none()
                                | st.fixed_dictionaries(
                                    {"jobDescription": st.none() | st.fixed_dictionaries({"text": _opt_text})}
                                )
                            }
                        ),
                        "applyUrl": _opt_text,
                        "releasedDate": _opt_text,
                    }
                ),
                max_size=10,
            )
        }
    )
    | st.just({})
    | st.just(None),
)
@settings(max_examples=200, suppress_health_check=[HealthCheck.too_slow])
def test_parse_smartrecruiters_never_raises(slug: str, body) -> None:
    """parse_smartrecruiters must never raise, regardless of body shape."""
    result = parse_smartrecruiters(slug, "TestCo", body)
    assert isinstance(result, list)
    for job in result:
        assert isinstance(job, Job)
        assert job.job_id.startswith("smartrecruiters:")


@given(
    slug=_slug,
    body=st.just({}) | st.just(None) | st.just([]),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_parse_bamboohr_never_raises(slug: str, body) -> None:
    """parse_bamboohr must never raise even on degenerate inputs."""
    result = parse_bamboohr(slug, "TestCo", body)
    assert isinstance(result, list)


@given(
    slug=_slug,
    body=st.just({}) | st.just(None) | st.just([]),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_parse_breezy_never_raises(slug: str, body) -> None:
    """parse_breezy must never raise even on degenerate inputs."""
    result = parse_breezy(slug, "TestCo", body)
    assert isinstance(result, list)


@given(
    slug=_slug,
    body=st.just({}) | st.just(None) | st.just([]),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_parse_recruitee_never_raises(slug: str, body) -> None:
    """parse_recruitee must never raise even on degenerate inputs."""
    result = parse_recruitee(slug, "TestCo", body)
    assert isinstance(result, list)


@given(
    slug=_slug,
    body=st.just({}) | st.just(None) | st.just([]),
)
@settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
def test_parse_pinpoint_never_raises(slug: str, body) -> None:
    """parse_pinpoint must never raise even on degenerate inputs."""
    result = parse_pinpoint(slug, "TestCo", body)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Job dataclass invariants
# ---------------------------------------------------------------------------


def test_job_score_100_clamped() -> None:
    """Job.score_100 must always return a value in [0, 100]."""
    for score in [-99.0, 0.0, 5.5, 10.0, 10.1, 999.0, None]:
        job = Job(
            job_id="test:co:1",
            ats="test",
            company="Co",
            title="SWE",
            location="India",
            url="#",
            description="x",
            score=score,
        )
        assert 0 <= job.score_100 <= 100, f"score={score} -> score_100={job.score_100} out of range"


def test_job_to_dict_has_required_keys() -> None:
    """Job.to_dict must always include score_100 and queue_category."""
    job = Job(job_id="a:b:c", ats="a", company="B", title="T", location="L", url="U", description="D", score=8.5)
    d = job.to_dict()
    assert "score_100" in d
    assert "queue_category" in d
    assert d["score_100"] == 85
