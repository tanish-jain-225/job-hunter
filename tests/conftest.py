"""Shared test fixtures and helpers for the jobhunt test suite."""

from __future__ import annotations

import pytest
from jobhunt.providers import reset_provider_state


@pytest.fixture(autouse=True)
def reset_memory_cache_state():
    """Ensure in-memory profile and jobs cache is cleanly isolated for every test."""
    from jobhunt.memory import clear_memory_cache
    clear_memory_cache()
    yield
    clear_memory_cache()


@pytest.fixture(autouse=True)
def reset_global_provider_state():
    """Ensure provider state (counters, cooldowns, throttles) is cleanly isolated for every test."""
    reset_provider_state()
    yield
    reset_provider_state()


@pytest.fixture(autouse=True)
def isolate_profile_file():
    """Ensure profile.json on disk is preserved and restored across test cases."""
    from pathlib import Path
    p = Path("profile.json")
    original = p.read_text(encoding="utf-8") if p.is_file() else None
    yield
    if original is not None:
        p.write_text(original, encoding="utf-8")
    elif p.is_file():
        p.unlink(missing_ok=True)



@pytest.fixture(scope="session", autouse=True)
def cleanup_transient_test_artifacts():
    """Ensure test artifacts are cleaned up when the pytest session completes."""
    yield
    from jobhunt.clean import clean_workspace
    clean_workspace(dry_run=False)


class DummyResponse:
    """Stub HTTP response for testing HTTP client code."""

    def __init__(self, status_code: int, json_data: dict | list | None = None, text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json_data

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")


class DummySession:
    """Stub HTTP session that returns a canned response or raises."""

    def __init__(self, response: DummyResponse | None = None, raise_exc: Exception | None = None):
        self.response = response
        self.raise_exc = raise_exc

    def get(self, url, headers=None, timeout=None):
        if self.raise_exc:
            raise self.raise_exc
        return self.response

    def post(self, url, **kwargs):
        if self.raise_exc:
            raise self.raise_exc
        return self.response
