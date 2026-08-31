"""Tests for LLM rate-limit resilience, multi-key API key rotation, and live provider switching."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from jobhunt.providers import Provider, GeminiProvider, OpenAICompatProvider, get_fallback_provider
from jobhunt.fetch import Job
from jobhunt import llm


def test_multi_api_key_parsing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "  key1 , key2,key3  ")
    keys = Provider._get_api_keys("GEMINI_API_KEY")
    assert keys == ["key1", "key2", "key3"]


def test_gemini_provider_multi_key_rotation(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key1,key2")
    provider = GeminiProvider()

    mock_response_429 = MagicMock()
    mock_response_429.status_code = 429
    mock_response_429.headers = {"Retry-After": "1"}

    mock_response_200 = MagicMock()
    mock_response_200.status_code = 200
    mock_response_200.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": '[{"job_id": "test:1", "score": 9.0}]'}]}}]
    }

    # First call returns 429 (key1), second returns 200 (key2)
    with patch("requests.post") as mock_post, patch("time.sleep"):
        mock_post.side_effect = [mock_response_429, mock_response_200]
        res = provider.complete("gemini-3.6-flash", "sys", "user", 100, json_mode=True)
        assert res == '[{"job_id": "test:1", "score": 9.0}]'
        assert mock_post.call_count == 2
        # Check that second request used key2
        second_call_params = mock_post.call_args_list[1][1].get("params")
        assert second_call_params["key"] == "key2"


def test_openai_compat_provider_multi_key_rotation(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq_key1,groq_key2")
    provider = OpenAICompatProvider()

    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.headers = {}

    mock_200 = MagicMock()
    mock_200.status_code = 200
    mock_200.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

    with patch("requests.post") as mock_post, patch("time.sleep"):
        mock_post.side_effect = [mock_429, mock_200]
        res = provider.complete("openai/gpt-oss-20b", "sys", "user", 100)
        assert res == "ok"
        second_call_headers = mock_post.call_args_list[1][1].get("headers")
        assert second_call_headers["Authorization"] == "Bearer groq_key2"


def test_get_fallback_provider(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "groq_key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini_key")

    with patch.object(Provider, "preflight", return_value=None):
        fallback = get_fallback_provider("groq", stage="screen")
        assert fallback is not None
        prov, model = fallback
        assert prov.name == "gemini"

        fallback_gemini = get_fallback_provider("gemini", stage="screen")
        assert fallback_gemini is not None
        prov2, model2 = fallback_gemini
        assert prov2.name == "groq"


def test_screen_live_failover_cascade(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "key1")
    monkeypatch.setenv("GEMINI_API_KEY", "key2")

    jobs = [
        Job(
            job_id="test:1",
            ats="test",
            company="Acme",
            title="Dev",
            location="Remote",
            url="http://x",
            description="text",
        )
    ]
    profile = {"name": "Test"}

    mock_primary_failing_provider = MagicMock()
    mock_primary_failing_provider.name = "groq"
    mock_primary_failing_provider.complete.side_effect = Exception("HTTP 429 Quota Exceeded")

    mock_gemini_provider = MagicMock()
    mock_gemini_provider.name = "gemini"
    mock_gemini_provider.complete.return_value = '[{"job_id": "test:1", "score": 8.5, "reason": "Good match"}]'

    with patch("jobhunt.llm.resolve", return_value=(mock_primary_failing_provider, "openai/gpt-oss-20b")):
        with patch("jobhunt.llm.get_fallback_provider") as mock_fallback:
            mock_fallback.return_value = (mock_gemini_provider, "gemini-3.6-flash")
            scored = llm.screen(jobs, profile)
            assert scored[0].score == 8.5
            assert scored[0].reason == "Good match"
