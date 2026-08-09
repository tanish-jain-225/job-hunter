"""Unit tests for jobhunt.providers resolution, preflight checks, and error handling."""
from __future__ import annotations

import pytest
from jobhunt import providers
from jobhunt.providers import LLMError, Provider, get_provider, resolve


def test_get_provider_valid():
    p = get_provider("gemini")
    assert p.name == "gemini"
    assert p.required_env == "GEMINI_API_KEY"


def test_get_provider_unknown():
    with pytest.raises(LLMError, match="unknown provider"):
        get_provider("nonexistent_llm")


def test_preflight_missing_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = get_provider("anthropic")
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY is not set"):
        p.preflight()


def test_preflight_blank_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    p = get_provider("anthropic")
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY is not set"):
        p.preflight()


def test_resolve_with_stage_overrides(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SCREEN_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_gemini_key")
    monkeypatch.setenv("SCREEN_MODEL", "gemini-2.0-flash")

    provider, model = resolve("screen", check=True)
    assert provider.name == "gemini"
    assert model == "gemini-2.0-flash"


def test_unsupported_document_error():
    provider = Provider()
    with pytest.raises(providers.UnsupportedDocument):
        provider.complete_document("model", "prompt", b"pdf bytes", 100)
