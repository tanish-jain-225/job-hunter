"""Unit tests for jobhunt.providers resolution, preflight checks, and error handling."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
import requests
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
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_gemini_key")
    provider, model = resolve("screen", check=False)
    assert provider.name == "gemini"


def test_resolve_default_gemini(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SCREEN_PROVIDER", raising=False)
    monkeypatch.delenv("DRAFT_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_gemini_key")

    screen_p, screen_m = resolve("screen", check=False)
    assert screen_p.name == "gemini"
    assert screen_m == "gemini-3.5-flash"

    draft_p, draft_m = resolve("draft", check=False)
    assert draft_p.name == "gemini"
    assert draft_m == "gemini-3.5-flash"


def test_resolve_missing_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "custom")
    monkeypatch.delenv("SCREEN_MODEL", raising=False)
    monkeypatch.setattr(providers, "PROVIDERS", {"custom": Provider})
    with pytest.raises(LLMError, match="set SCREEN_MODEL"):
        resolve("screen", check=False)


def test_unsupported_document_error():
    provider = Provider()
    with pytest.raises(providers.UnsupportedDocument):
        provider.complete_document("model", "prompt", b"pdf bytes", 100)


def test_anthropic_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy_anthropic_key")

    mock_msg = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = "Anthropic reply"
    mock_msg.content = [block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_msg

    p = providers.AnthropicProvider()
    monkeypatch.setattr(p, "_client", lambda: mock_client)

    res = p.complete("claude-3-5-haiku", "sys", "user", 100)
    assert res == "Anthropic reply"

    res_doc = p.complete_document("claude-3-5-haiku", "prompt", b"%PDF...", 100)
    assert res_doc == "Anthropic reply"


def test_gemini_provider_complete_success(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": '{"result": "ok"}'}]}}]}

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: DummyResponse())
    p = providers.GeminiProvider()
    res = p.complete("gemini-2.0-flash", "sys", "user", 100, json_mode=True)
    assert res == '{"result": "ok"}'


def test_gemini_provider_complete_document_success(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")

    class DummyResponse:
        status_code = 200

        def json(self):
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Extracted text"}]}}]}

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: DummyResponse())
    p = providers.GeminiProvider()
    res = p.complete_document("gemini-2.0-flash", "prompt", b"%PDF...", 100)
    assert res == "Extracted text"


def test_gemini_provider_retries_and_errors(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr(providers.time, "sleep", lambda x: None)

    # Retry on 500 then succeed
    attempts = [0]

    class RetryResponse:
        def __init__(self, code):
            self.status_code = code
            self.text = "server error"

        def json(self):
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "OK"}]}}]}

    def mock_post_retry(*a, **kw):
        attempts[0] += 1
        if attempts[0] == 1:
            return RetryResponse(500)
        return RetryResponse(200)

    monkeypatch.setattr(providers.requests, "post", mock_post_retry)
    p = providers.GeminiProvider()
    assert p.complete("gemini-2.0-flash", "sys", "user", 100) == "OK"

    # Malformed JSON
    class MalformedResponse:
        status_code = 200
        text = "invalid json"

        def json(self):
            raise ValueError("bad json")

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: MalformedResponse())
    with pytest.raises(LLMError, match="invalid JSON"):
        p.complete("gemini-2.0-flash", "sys", "user", 100)

    # Max tokens finish reason
    class MaxTokensResponse:
        status_code = 200
        text = "stopped"

        def json(self):
            return {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "trunc"}]}}]}

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: MaxTokensResponse())
    with pytest.raises(LLMError, match="gemini stopped early"):
        p.complete("gemini-2.0-flash", "sys", "user", 100)

    # Network exception
    def mock_post_network(*a, **kw):
        raise requests.RequestException("Conn error")

    monkeypatch.setattr(providers.requests, "post", mock_post_network)
    with pytest.raises(LLMError, match="gemini network error"):
        p.complete("gemini-2.0-flash", "sys", "user", 100)


def test_openai_compat_provider_retries_and_errors(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy_groq_key")
    monkeypatch.setattr(providers.time, "sleep", lambda x: None)

    p = providers.GroqProvider()

    # HTTP 400 error
    class ErrorResponse:
        status_code = 400
        text = "Bad Request"

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: ErrorResponse())
    with pytest.raises(LLMError, match="groq HTTP 400"):
        p.complete("llama-3.3-70b", "sys", "user", 100)

    # Malformed reply
    class MalformedResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {}

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: MalformedResponse())
    with pytest.raises(LLMError, match="groq malformed reply"):
        p.complete("llama-3.3-70b", "sys", "user", 100)

    # Network exception
    def mock_post_net(*a, **kw):
        raise requests.RequestException("Net timeout")

    monkeypatch.setattr(providers.requests, "post", mock_post_net)
    with pytest.raises(LLMError, match="groq network error"):
        p.complete("llama-3.3-70b", "sys", "user", 100)


def test_ollama_provider_errors(monkeypatch: pytest.MonkeyPatch):
    p = providers.OllamaProvider()

    # Non 200
    class BadResponse:
        status_code = 500
        text = "Internal error"

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: BadResponse())
    with pytest.raises(LLMError, match="ollama HTTP 500"):
        p.complete("llama3.1", "sys", "user", 100)

    # Malformed reply
    class MalformedResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {}

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: MalformedResponse())
    with pytest.raises(LLMError, match="ollama malformed reply"):
        p.complete("llama3.1", "sys", "user", 100)


def test_anthropic_provider_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy_key")
    p = providers.AnthropicProvider()
    try:
        client = p._client()
        assert client is not None
    except LLMError as e:
        assert "pip install anthropic" in str(e)


def test_gemini_provider_no_candidates_and_empty_text(monkeypatch: pytest.MonkeyPatch):
    p = providers.GeminiProvider()
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")

    # No candidates key
    class NoCandidatesResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {}

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: NoCandidatesResponse())
    with pytest.raises(LLMError, match="gemini returned no candidates"):
        p.complete("gemini-2.0-flash", "sys", "user", 100)

    # Empty text response
    class EmptyTextResponse:
        status_code = 200
        text = "empty text"

        def json(self):
            return {"candidates": [{"finishReason": "STOP", "content": {"parts": []}}]}

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: EmptyTextResponse())
    with pytest.raises(LLMError, match="gemini returned no text"):
        p.complete("gemini-2.0-flash", "sys", "user", 100)


def test_openai_compat_retry_loop(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy_groq_key")
    monkeypatch.setattr(providers.time, "sleep", lambda x: None)

    p = providers.GroqProvider()
    attempts = [0]

    class RetryResponse:
        def __init__(self, code):
            self.status_code = code
            self.text = "server error"

        def json(self):
            return {"choices": [{"message": {"content": "OK"}}]}

    def mock_post_retry(*a, **kw):
        attempts[0] += 1
        if attempts[0] == 1:
            return RetryResponse(500)
        return RetryResponse(200)

    monkeypatch.setattr(providers.requests, "post", mock_post_retry)
    assert p.complete("llama-3.3-70b", "sys", "user", 100, json_mode=True) == "OK"


def test_base_provider_not_implemented():
    p = Provider()
    with pytest.raises(NotImplementedError):
        p.complete("model", "sys", "user", 100)


def test_ollama_provider_success(monkeypatch: pytest.MonkeyPatch):
    p = providers.OllamaProvider()

    class OllamaOkResponse:
        status_code = 200
        text = "ok"

        def json(self):
            return {"message": {"content": "Ollama OK"}}

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: OllamaOkResponse())
    res = p.complete("llama3", "sys", "user", 100, json_mode=True)
    assert res == "Ollama OK"


def test_anthropic_import_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy_key")
    p = providers.AnthropicProvider()

    import builtins

    orig_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named anthropic")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    with pytest.raises(LLMError, match="pip install anthropic"):
        p._client()


def test_gemini_max_retries_and_non_200(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    p = providers.GeminiProvider()

    # Immediate non-retryable error (e.g. 403 Forbidden)
    class ForbiddenResponse:
        status_code = 403
        text = "Forbidden"

    monkeypatch.setattr(providers.requests, "post", lambda *a, **kw: ForbiddenResponse())
    with pytest.raises(LLMError, match="gemini HTTP 403"):
        p.complete("gemini-2.0-flash", "sys", "user", 100)

    # Permanent network error reaching max retries
    def mock_post_err(*a, **kw):
        raise requests.RequestException("Network timeout after retries")

    monkeypatch.setattr(providers.requests, "post", mock_post_err)
    with pytest.raises(LLMError, match="gemini network error"):
        p.complete("gemini-2.0-flash", "sys", "user", 100)


def test_openai_compat_max_retries_error(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GROQ_API_KEY", "dummy_key")
    monkeypatch.setattr(providers.time, "sleep", lambda s: None)
    p = providers.GroqProvider()

    # Permanent network error reaching max retries
    def mock_post_net_err(*a, **kw):
        raise requests.RequestException("Groq network down")

    monkeypatch.setattr(providers.requests, "post", mock_post_net_err)
    with pytest.raises(LLMError, match="groq network error"):
        p.complete("llama-3.3-70b", "sys", "user", 100)


def test_ollama_connection_error(monkeypatch: pytest.MonkeyPatch):
    p = providers.OllamaProvider()

    def mock_post_err(*a, **kw):
        raise requests.RequestException("Connection refused")

    monkeypatch.setattr(providers.requests, "post", mock_post_err)
    with pytest.raises(LLMError, match="ollama unreachable"):
        p.complete("llama3.1", "sys", "user", 100)


def test_resolve_prefers_gemini(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("SCREEN_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_gemini_key")

    provider, model = resolve("screen", check=False)
    assert provider.name == "gemini"
    assert model == "gemini-3.5-flash"


def test_gemini_35_flash_default_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy_key")
    monkeypatch.delenv("SCREEN_MODEL", raising=False)
    monkeypatch.delenv("DRAFT_MODEL", raising=False)

    p_screen, m_screen = resolve("screen", check=True)
    assert p_screen.name == "gemini"
    assert m_screen == "gemini-3.5-flash"

    p_draft, m_draft = resolve("draft", check=True)
    assert p_draft.name == "gemini"
    assert m_draft == "gemini-3.5-flash"
