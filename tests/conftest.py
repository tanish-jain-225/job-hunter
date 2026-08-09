"""Shared test fixtures and helpers for the jobhunt test suite."""
from __future__ import annotations


class DummyResponse:
    """Stub HTTP response for testing HTTP client code."""

    def __init__(self, status_code: int, json_data: dict | list | None = None,
                 text: str = ""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json_data


class DummySession:
    """Stub HTTP session that returns a canned response or raises."""

    def __init__(self, response: DummyResponse | None = None,
                 raise_exc: Exception | None = None):
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
