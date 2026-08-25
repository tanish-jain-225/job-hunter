"""Unit tests for resilience, scaling, bounded memory, caching, and safe regex parsing."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
import pytest

from jobhunt.auth import _TOKEN_CACHE, _prune_token_cache, verify_token, clear_token_cache
from jobhunt.fetch import Job, _GLOBAL_ATS_CACHE, _prune_ats_cache, clear_ats_cache
from jobhunt.memory import (
    SupabaseMemory,
    _PROFILE_CACHE,
    _JOBS_CACHE,
    clear_memory_cache,
    invalidate_user_cache,
)
from jobhunt.prefilter import _safe_compile, prefilter
from jobhunt.store import Store, get_writable_path, _WRITABLE_DIR_CACHE
from jobhunt.web.state import (
    _USER_PIPELINE_STATES,
    _prune_pipeline_states_locked,
    set_user_pipeline_state,
    get_user_pipeline_state,
)


def test_safe_compile_with_special_characters():
    """Verify that regex special characters from user input don't crash regex compilation."""
    # Unescaped C++ would normally raise re.error (multiple repeat)
    p1 = _safe_compile("C++")
    assert p1.search("Senior C++ Developer") is not None
    assert p1.search("Python Developer") is None

    # Unclosed bracket / parenthesis that raises re.error
    p2 = _safe_compile("Dev [Backend")
    assert p2.search("Looking for Dev [Backend engineer") is not None

    p3 = _safe_compile("(Unclosed Group")
    assert p3.search("Title with (Unclosed Group") is not None

    # Blank/invalid input
    p_empty = _safe_compile("")
    assert p_empty is not None


    # Test within prefilter directly
    jobs = [
        Job(job_id="1", ats="lever", company="A", title="C++ Core Developer", location="Remote", url="#", description=""),
        Job(job_id="2", ats="lever", company="B", title="Frontend React Developer", location="Remote", url="#", description=""),
    ]
    filtered = prefilter(jobs, {"include_titles": ["C++"]})
    assert len(filtered) == 1
    assert filtered[0].title == "C++ Core Developer"


def test_token_cache_pruning():
    """Verify that token cache expires old items and caps size."""
    clear_token_cache()
    now = time.time()
    _TOKEN_CACHE["expired1"] = ({"id": "user1"}, now - 10)
    _TOKEN_CACHE["valid1"] = ({"id": "user2"}, now + 60)

    _prune_token_cache(now)
    assert "expired1" not in _TOKEN_CACHE
    assert "valid1" in _TOKEN_CACHE

    # Test max size bound
    for i in range(1100):
        _TOKEN_CACHE[f"token_{i}"] = ({"id": f"u_{i}"}, now + 100)

    _prune_token_cache(now)
    assert len(_TOKEN_CACHE) <= 1000
    clear_token_cache()


def test_ats_cache_pruning():
    """Verify that ATS cache expires old items and caps size."""
    clear_ats_cache()
    now = time.time()
    _GLOBAL_ATS_CACHE["ats:old"] = (now - 2000, [])
    _GLOBAL_ATS_CACHE["ats:fresh"] = (now - 100, [])

    _prune_ats_cache(now, ttl=1800.0)
    assert "ats:old" not in _GLOBAL_ATS_CACHE
    assert "ats:fresh" in _GLOBAL_ATS_CACHE

    for i in range(600):
        _GLOBAL_ATS_CACHE[f"ats:slug_{i}"] = (now, [])

    _prune_ats_cache(now)
    assert len(_GLOBAL_ATS_CACHE) <= 500
    clear_ats_cache()


def test_pipeline_states_pruning():
    """Verify that idle user pipeline states are pruned under memory limits."""
    with _prune_pipeline_states_locked.__globals__["_PIPELINE_LOCK"]:
        _USER_PIPELINE_STATES.clear()
        for i in range(600):
            _USER_PIPELINE_STATES[f"user_{i}@example.com"] = {
                "running": False,
                "step": "idle",
                "message": "ready",
                "last_run": None,
                "exit_code": 0,
            }
        _prune_pipeline_states_locked()
        assert len(_USER_PIPELINE_STATES) <= 500
        _USER_PIPELINE_STATES.clear()


def test_memory_cache_invalidation_lifecycle(monkeypatch):
    """Verify that memory read caching works and invalidates on mutations."""
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    clear_memory_cache()

    mem = SupabaseMemory()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [{"email": "test@user.com", "name": "Initial Name", "skills": ["Python"]}]

    with patch("requests.get", return_value=mock_resp) as mock_get:
        # First read hits Supabase
        p1 = mem.get_user_profile("test@user.com")
        assert p1["name"] == "Initial Name"
        assert mock_get.call_count == 1

        # Second read hits in-memory cache without HTTP call
        p2 = mem.get_user_profile("test@user.com")
        assert p2["name"] == "Initial Name"
        assert mock_get.call_count == 1

    # Invalidate cache on update
    invalidate_user_cache("test@user.com")
    mock_resp.json.return_value = [{"email": "test@user.com", "name": "Updated Name", "skills": ["Python"]}]
    with patch("requests.get", return_value=mock_resp) as mock_get:
        p3 = mem.get_user_profile("test@user.com")
        assert p3["name"] == "Updated Name"
        assert mock_get.call_count == 1

    clear_memory_cache()


def test_writable_path_caching(tmp_path):
    """Verify that directory writability cache prevents redundant disk probing."""
    _WRITABLE_DIR_CACHE.clear()
    target_file = tmp_path / "subdir" / "test.json"
    p1 = get_writable_path(target_file)
    assert p1 == target_file
    assert target_file.parent in _WRITABLE_DIR_CACHE

    # Second call returns cached path instantly
    p2 = get_writable_path(target_file)
    assert p2 == target_file


def test_store_add_job_schema_completeness(tmp_path):
    """Verify that Store.add_job initializes all schema fields consistently."""
    seen_path = tmp_path / "seen_test.json"
    st = Store(seen_path)
    job_id = st.add_job(
        title="Senior SRE",
        company="Datadog",
        location="Bengaluru, India",
        url="https://datadog.com/jobs/123",
        ats="greenhouse",
        score=9.1,
        applied=True,
    )
    assert job_id in st.data
    job = st.data[job_id]
    assert job["application_stage"] == "applied"
    assert job["applied"] is True
    assert job["notes"] == ""
    assert job["salary_range"] == ""
    assert job["first_seen"] is not None
    assert job["applied_on"] is not None
    assert job["ats"] == "greenhouse"
    assert "https://datadog.com/jobs/123" in job["url"]
