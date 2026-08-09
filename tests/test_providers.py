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


def test_resolve_auto_detect_gemini(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SCREEN_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_gemini_key")
    provider, model = resolve("screen", check=False)
    assert provider.name == "gemini"


def test_unsupported_document_error():
    provider = Provider()
    with pytest.raises(providers.UnsupportedDocument):
        provider.complete_document("model", "prompt", b"pdf bytes", 100)


def test_gemini_provider_complete_success(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")

    class DummyResponse:
        status_code = 200

        def json(self):
            return {
                "candidates": [{
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": '{"result": "ok"}'}]}
                }]
            }

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: DummyResponse())
    p = providers.GeminiProvider()
    res = p.complete("gemini-2.0-flash", "sys", "user", 100, json_mode=True)
    assert res == '{"result": "ok"}'


def test_gemini_provider_complete_document_success(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")

    class DummyResponse:
        status_code = 200

        def json(self):
            return {
                "candidates": [{
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": "Extracted text"}]}
                }]
            }

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: DummyResponse())
    p = providers.GeminiProvider()
    res = p.complete_document("gemini-2.0-flash", "prompt", b"%PDF...", 100)
    assert res == "Extracted text"


def test_gemini_provider_error_status(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")

    class DummyResponse:
        status_code = 400
        text = "Bad Request"

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: DummyResponse())
    p = providers.GeminiProvider()
    with pytest.raises(LLMError, match="gemini HTTP 400"):
        p.complete("gemini-2.0-flash", "sys", "user", 100)


def test_openai_compat_provider_complete_success(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy_groq_key")

    class DummyResponse:
        status_code = 200

        def json(self):
            return {
                "choices": [{
                    "message": {"content": "Groq reply"}
                }]
            }

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: DummyResponse())
    p = providers.GroqProvider()
    res = p.complete("llama-3.3-70b", "sys", "user", 100, json_mode=True)
    assert res == "Groq reply"


def test_ollama_provider_complete_success(monkeypatch: pytest.MonkeyPatch):
    class DummyResponse:
        status_code = 200

        def json(self):
            return {
                "message": {"content": "Ollama reply"}
            }

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: DummyResponse())
    p = providers.OllamaProvider()
    res = p.complete("llama3.1", "sys", "user", 100, json_mode=True)
    assert res == "Ollama reply"


def test_ollama_provider_unreachable(monkeypatch: pytest.MonkeyPatch):
    def mock_post(*a, **kw):
        raise providers.requests.RequestException("Connection refused")

    monkeypatch.setattr(providers.requests, "post", mock_post)
    p = providers.OllamaProvider()
    with pytest.raises(LLMError, match="ollama unreachable"):
        p.complete("llama3.1", "sys", "user", 100)
