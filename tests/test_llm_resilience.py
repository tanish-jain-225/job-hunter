"""Tests for Google Gemini LLM rate-limit resilience and multi-key API key rotation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from jobhunt.fetch import Job
from jobhunt.providers import (
    GeminiProvider,
    GroqProvider,
    LLMError,
    Provider,
    UnsupportedDocument,
    _is_key_cooling_down,
    _is_key_disabled,
    _record_model_cooldown,
    get_fallback_provider,
    reset_provider_state,
)
from jobhunt import llm, multi


def test_multi_api_key_parsing(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "  key1 , key2,key3  ")
    keys = Provider._get_api_keys("GEMINI_API_KEY")
    assert keys == ["key1", "key2", "key3"]


def test_gemini_provider_multi_key_rotation(monkeypatch):
    from jobhunt.providers import reset_provider_state
    reset_provider_state()

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

    # First call returns 429 (rate limited), second returns 200 after rotating keys
    with patch("requests.post") as mock_post, patch("time.sleep"):
        mock_post.side_effect = [mock_response_429, mock_response_200]
        res = provider.complete("gemini-3.5-flash", "sys", "user", 100, json_mode=True)
        assert res == '[{"job_id": "test:1", "score": 9.0}]'
        assert mock_post.call_count == 2
        # Check that request rotated to the other key
        first_call_key = mock_post.call_args_list[0][1].get("params")["key"]
        second_call_key = mock_post.call_args_list[1][1].get("params")["key"]
        assert first_call_key != second_call_key
        assert {first_call_key, second_call_key} == {"key1", "key2"}


def test_get_fallback_provider(monkeypatch):
    for var in (
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "ANTHROPIC_API_KEY",
        "LLM_BASE_URL",
        "SCREEN_PROVIDER",
        "DRAFT_PROVIDER",
        "LLM_PROVIDER",
    ):
        monkeypatch.delenv(var, raising=False)

    with patch("jobhunt.auth._load_env_if_needed"), patch.object(Provider, "preflight", return_value=None):
        monkeypatch.setenv("GEMINI_API_KEY", "gemini_key")
        assert get_fallback_provider("gemini", stage="screen") is None

        monkeypatch.setenv("GROQ_API_KEY", "groq_key")
        fallback = get_fallback_provider("gemini", stage="screen")
        assert fallback is not None
        prov, model = fallback
        assert prov.name == "groq"
        assert model == "llama-3.1-8b-instant"

        # Prevent gemini <-> groq ping-pong and skip redundant openai-compatible default URL
        assert get_fallback_provider("gemini", stage="screen", excluded={"groq"}) is None
        assert get_fallback_provider("groq", stage="screen", excluded={"gemini"}) is None

        # Custom OpenAI-compatible base URL remains available even when groq is excluded
        monkeypatch.setenv("LLM_BASE_URL", "https://openrouter.example/api/v1")
        custom_fb = get_fallback_provider("gemini", stage="screen", excluded={"groq"})
        assert custom_fb is not None
        assert custom_fb[0].name == "openai-compatible"
        assert custom_fb[1] == "gpt-4o-mini"


def test_screen_live_failover_cascade(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "key1")

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

    mock_failing_provider = MagicMock()
    mock_failing_provider.name = "gemini"
    mock_failing_provider.complete.side_effect = Exception("HTTP 429 Quota Exceeded")

    mock_gemini_fallback = MagicMock()
    mock_gemini_fallback.name = "gemini"
    mock_gemini_fallback.complete.return_value = '[{"job_id": "test:1", "score": 8.5, "reason": "Good match"}]'

    with patch("jobhunt.llm.resolve", return_value=(mock_failing_provider, "gemini-3.5-flash")):
        with patch("jobhunt.llm.get_fallback_provider") as mock_fallback:
            mock_fallback.return_value = (mock_gemini_fallback, "gemini-3.5-flash")
            scored = llm.screen(jobs, profile)
            assert scored[0].score == 8.5
            assert scored[0].reason == "Good match"


def _gemini_ok(text: str = "ok") -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.text = text
    r.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return r


def _gemini_err(status: int, text: str = "", headers: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.text = text
    r.headers = headers or {}
    return r


def test_gemini_model_first_three_keys_and_scoped_cooldown(monkeypatch):
    reset_provider_state()
    monkeypatch.setenv("GEMINI_API_KEY", "k1,k2,k3")
    provider = GeminiProvider()

    calls: list[tuple[str, str]] = []

    def fake_post(url, **kwargs):
        key = kwargs["params"]["key"]
        calls.append((url, key))
        if "gemini-3.5-flash:generateContent" in url:
            return _gemini_err(429, "Quota exceeded", {"Retry-After": "30"})
        return _gemini_ok("model2-ok")

    with patch("requests.post", side_effect=fake_post), patch("time.sleep"):
        out = provider.complete("gemini-3.5-flash", "sys", "usr", 100)

    assert out == "model2-ok"
    assert len(calls) == 4
    first_tier = calls[:3]
    assert all("gemini-3.5-flash:generateContent" in u for u, _ in first_tier)
    assert {k for _, k in first_tier} == {"k1", "k2", "k3"}
    assert "gemini-flash-latest:generateContent" in calls[3][0]

    # Cooldown must include ALL 3 keys (including 3rd/last) and stay scoped to model 1
    for k in ("k1", "k2", "k3"):
        assert _is_key_cooling_down(k, model="gemini-3.5-flash") is True
        assert _is_key_cooling_down(k, model="gemini-flash-latest") is False


def test_gemini_rotates_keys_on_5xx_network_and_malformed_json(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k1,k2,k3")
    provider = GeminiProvider()

    # 1. HTTP 503 rotates key on the same model
    reset_provider_state()
    seen_503: list[str] = []

    def post_503(url, **kwargs):
        seen_503.append(kwargs["params"]["key"])
        if len(seen_503) == 1:
            return _gemini_err(503, "High demand")
        return _gemini_ok("ok-503")

    with patch("requests.post", side_effect=post_503), patch("time.sleep"):
        assert provider.complete("gemini-3.5-flash", "s", "u", 50) == "ok-503"
    assert len(seen_503) == 2 and seen_503[0] != seen_503[1]

    # 2. RequestException (timeout) rotates key on the same model
    reset_provider_state()
    seen_net: list[str] = []

    def post_net(url, **kwargs):
        seen_net.append(kwargs["params"]["key"])
        if len(seen_net) == 1:
            raise requests.Timeout("timed out")
        return _gemini_ok("ok-net")

    with patch("requests.post", side_effect=post_net), patch("time.sleep"):
        assert provider.complete("gemini-3.5-flash", "s", "u", 50) == "ok-net"
    assert len(seen_net) == 2 and seen_net[0] != seen_net[1]

    # 3. Malformed JSON rotates key on the same model
    reset_provider_state()
    seen_json: list[str] = []

    def post_bad_json(url, **kwargs):
        seen_json.append(kwargs["params"]["key"])
        if len(seen_json) == 1:
            bad = MagicMock()
            bad.status_code = 200
            bad.text = "{broken"
            bad.json.side_effect = ValueError("bad json")
            return bad
        return _gemini_ok("ok-json")

    with patch("requests.post", side_effect=post_bad_json), patch("time.sleep"):
        assert provider.complete("gemini-3.5-flash", "s", "u", 50) == "ok-json"
    assert len(seen_json) == 2 and seen_json[0] != seen_json[1]


def test_gemini_disables_invalid_key_and_rotates(monkeypatch):
    reset_provider_state()
    monkeypatch.setenv("GEMINI_API_KEY", "bad_400,bad_403,good_key")
    provider = GeminiProvider()

    calls_req1: list[str] = []
    calls_req2: list[str] = []

    def post_req1(url, **kwargs):
        key = kwargs["params"]["key"]
        calls_req1.append(key)
        if key == "bad_400":
            return _gemini_err(400, '{"error":{"status":"INVALID_ARGUMENT","message":"API_KEY_INVALID"}}')
        if key == "bad_403":
            return _gemini_err(403, "Permission denied")
        return _gemini_ok("good-ok")

    with patch("requests.post", side_effect=post_req1), patch("time.sleep"):
        assert provider.complete("gemini-3.5-flash", "s", "u", 50) == "good-ok"

    assert "good_key" in calls_req1
    assert _is_key_disabled("bad_400") or _is_key_disabled("bad_403")

    def post_req2(url, **kwargs):
        calls_req2.append(kwargs["params"]["key"])
        return _gemini_ok("req2-ok")

    with patch("requests.post", side_effect=post_req2), patch("time.sleep"):
        assert provider.complete("gemini-3.5-flash", "s", "u", 50) == "req2-ok"

    for bad_k in ("bad_400", "bad_403"):
        if _is_key_disabled(bad_k):
            assert bad_k not in calls_req2


def test_gemini_five_keys_without_four_key_cap(monkeypatch):
    reset_provider_state()
    monkeypatch.setenv("GEMINI_API_KEY", "k1,k2,k3,k4,k5")
    provider = GeminiProvider()
    seen: list[str] = []

    def post_five(url, **kwargs):
        seen.append(kwargs["params"]["key"])
        if len(seen) < 5:
            return _gemini_err(429, "Quota exceeded", {"Retry-After": "15"})
        return _gemini_ok("fifth-ok")

    with patch("requests.post", side_effect=post_five), patch("time.sleep"):
        assert provider.complete("gemini-3.5-flash", "s", "u", 50) == "fifth-ok"

    assert seen == ["k2", "k3", "k4", "k5", "k1"] or set(seen) == {"k1", "k2", "k3", "k4", "k5"}
    assert len(seen) == 5


def test_gemini_chained_cooldown_skip_and_terminal_404(monkeypatch):
    reset_provider_state()
    monkeypatch.setenv("GEMINI_API_KEY", "k1,k2")
    provider = GeminiProvider()

    _record_model_cooldown("gemini-3.5-flash", 60.0)
    _record_model_cooldown("gemini-flash-latest", 60.0)

    urls: list[str] = []

    def post_skip(url, **kwargs):
        urls.append(url)
        return _gemini_ok("lite-ok")

    with patch("requests.post", side_effect=post_skip), patch("time.sleep"):
        assert provider.complete("gemini-3.5-flash", "s", "u", 50) == "lite-ok"

    assert len(urls) == 1
    assert "gemini-flash-lite-latest:generateContent" in urls[0]

    # Terminal 404 across fallback models must stop cleanly without RecursionError
    reset_provider_state()
    with patch("requests.post", return_value=_gemini_err(404, "Not found")), patch("time.sleep"):
        with pytest.raises(LLMError, match="gemini HTTP 404"):
            provider.complete("gemini-flash-lite-latest", "s", "u", 50)


def test_groq_round_robin_and_model_fallback(monkeypatch):
    reset_provider_state()
    monkeypatch.setenv("GROQ_API_KEY", "gk1,gk2")
    provider = GroqProvider()

    auths: list[str] = []

    def post_rr(url, **kwargs):
        auths.append(kwargs["headers"]["Authorization"])
        r = MagicMock()
        r.status_code = 200
        r.text = "ok"
        r.json.return_value = {"choices": [{"message": {"content": "groq-ok"}}]}
        return r

    with patch("requests.post", side_effect=post_rr), patch("time.sleep"):
        assert provider.complete("llama-3.1-8b-instant", "s", "u", 50) == "groq-ok"
        assert provider.complete("llama-3.1-8b-instant", "s", "u", 50) == "groq-ok"

    assert len(auths) == 2
    assert auths[0] != auths[1]
    assert set(auths) == {"Bearer gk1", "Bearer gk2"}

    # Model fallback on 429 across all keys
    reset_provider_state()
    models_used: list[tuple[str, str]] = []

    def post_fallback(url, **kwargs):
        cur_m = kwargs["json"]["model"]
        auth = kwargs["headers"]["Authorization"]
        models_used.append((cur_m, auth))
        if cur_m == "llama-3.1-8b-instant":
            r429 = MagicMock()
            r429.status_code = 429
            r429.headers = {"Retry-After": "12"}
            r429.text = "rate limit"
            return r429
        r200 = MagicMock()
        r200.status_code = 200
        r200.text = "ok"
        r200.json.return_value = {"choices": [{"message": {"content": "groq-70b-ok"}}]}
        return r200

    with patch("requests.post", side_effect=post_fallback), patch("time.sleep"):
        out = provider.complete("llama-3.1-8b-instant", "s", "u", 50)

    assert out == "groq-70b-ok"
    m1_calls = [auth for m, auth in models_used if m == "llama-3.1-8b-instant"]
    assert set(m1_calls) == {"Bearer gk1", "Bearer gk2"}
    assert models_used[-1][0] == "llama-3.3-70b-versatile"


def test_llm_build_profile_screen_parallel_and_draft_failover(monkeypatch):
    # 1. build_profile failover without leaking Gemini api_key into Groq
    prim_prof = MagicMock()
    prim_prof.name = "gemini"
    prim_prof.complete.side_effect = LLMError("gemini 429 exhausted")

    fb_prof = MagicMock()
    fb_prof.name = "groq"
    seen_fb_key: list[str | None] = []

    def fb_complete(model, system, user, max_tokens, json_mode=False, api_key=None):
        seen_fb_key.append(api_key)
        return '{"name": "Ada", "skills": ["Python"]}'

    fb_prof.complete.side_effect = fb_complete

    with (
        patch("jobhunt.llm.resolve", return_value=(prim_prof, "gemini-3.5-flash")),
        patch("jobhunt.llm.get_fallback_provider", return_value=(fb_prof, "llama-3.1-8b-instant")) as mock_get_fb,
    ):
        prof = llm.build_profile(resume_text="Ada Lovelace - Python", api_key="gemini_secret_key")

    assert prof["name"] == "Ada"
    assert seen_fb_key == [None]
    mock_get_fb.assert_called_once()

    # 2. build_profile PDF unsupported fallback to extracted text
    pdf_prov = MagicMock()
    pdf_prov.name = "groq"
    pdf_prov.complete_document.side_effect = UnsupportedDocument("no pdf")
    pdf_prov.complete.return_value = '{"name": "Grace", "skills": ["Compilers"]}'

    with (
        patch("jobhunt.llm.resolve", return_value=(pdf_prov, "llama-3.1-8b-instant")),
        patch("jobhunt.llm.extract_text_from_pdf", side_effect=["", "Grace Hopper resume"]),
    ):
        prof2 = llm.build_profile(resume_bytes=b"%PDF-1.4", is_pdf=True)
    assert prof2["name"] == "Grace"

    # 3. Parallel screen (max_workers=2) failover without leaking Gemini api_key into Groq
    jobs = [
        Job(job_id="t:1", ats="t", company="A", title="Eng", location="R", url="http://1", description="Python"),
        Job(job_id="t:2", ats="t", company="B", title="Eng", location="R", url="http://2", description="Go"),
    ]
    prim_scr = MagicMock()
    prim_scr.name = "gemini"
    prim_scr.complete.side_effect = LLMError("429 exhausted")

    fb_scr = MagicMock()
    fb_scr.name = "groq"
    scr_keys: list[str | None] = []

    def fb_screen(model, system, user, max_tokens, json_mode=False, api_key=None):
        scr_keys.append(api_key)
        if "t:1" in user:
            return '[{"job_id": "t:1", "score": 8.0, "reason": "fit"}]'
        return '[{"job_id": "t:2", "score": 7.5, "reason": "fit"}]'

    fb_scr.complete.side_effect = fb_screen

    with patch("jobhunt.llm.get_fallback_provider", return_value=(fb_scr, "llama-3.1-8b-instant")):
        res_jobs = llm.screen(
            jobs,
            {"name": "Dev"},
            batch_size=1,
            provider=prim_scr,
            model="gemini-3.5-flash",
            delay_seconds=0.0,
            max_workers=2,
            api_key="gemini_secret_key",
        )

    assert [j.score for j in res_jobs] == [8.0, 7.5]
    assert scr_keys == [None, None]

    # 4. draft failover without ping-pong
    jobs[0].score = 9.0
    prim_draft = MagicMock()
    prim_draft.name = "gemini"
    prim_draft.complete.side_effect = LLMError("gemini down")

    fb_draft = MagicMock()
    fb_draft.name = "groq"
    draft_keys: list[str | None] = []

    def fb_draft_fn(model, system, user, max_tokens, json_mode=False, api_key=None):
        draft_keys.append(api_key)
        return '{"fit_summary": "Strong Python fit", "cold_outreach": "Hello team, excited to apply!"}'

    fb_draft.complete.side_effect = fb_draft_fn

    with patch("jobhunt.llm.get_fallback_provider", side_effect=[(fb_draft, "llama-3.3-70b-versatile"), None]):
        drafted = llm.draft(
            [jobs[0]],
            {"name": "Dev"},
            provider=prim_draft,
            model="gemini-3.5-flash",
            delay_seconds=0.0,
            api_key="gemini_secret_key",
        )

    assert drafted[0].draft["cold_outreach"] == "Hello team, excited to apply!"
    assert draft_keys == [None]


def test_multi_user_pipeline_keyword_fallback_and_daily_schedule(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.delenv("STRICT_LLM", raising=False)

    mock_users = [
        {
            "email": "user_fallback@test.com",
            "name": "Fallback User",
            "onboarding_completed": True,
            "skills": ["Python", "AI"],
            "target_keywords": ["AI Engineer"],
            "email_notifications_enabled": False,
            "min_score_notification": 6.0,
        }
    ]
    unscored_job = Job(
        job_id="ashby:co:99",
        ats="ashby",
        company="AI Corp",
        title="AI Engineer",
        location="Remote",
        url="https://jobs.ashbyhq.com/co/99",
        description="Python AI Engineer building systems",
        score=None,
    )

    def fake_get(url, **kwargs):
        resp = MagicMock(status_code=200)
        resp.json.return_value = mock_users if "user_profiles" in str(url) else []
        return resp

    mock_prov = MagicMock()
    mock_prov.name = "gemini"

    with (
        patch("requests.get", side_effect=fake_get),
        patch("jobhunt.multi.fetch_all", return_value=[unscored_job]),
        patch("jobhunt.multi.resolve", return_value=(mock_prov, "gemini-3.5-flash")),
        patch("jobhunt.multi.llm.screen", return_value=None) as spy_screen,
        patch("jobhunt.multi.llm.keyword_screen", wraps=llm.keyword_screen) as spy_kw,
        patch("jobhunt.multi.llm.draft", return_value=None),
        patch("jobhunt.multi.mailer.send", return_value=True),
        patch("requests.post", return_value=MagicMock(status_code=201)),
    ):
        res = multi.run_multi_user_pipeline(mock=False, scorer="llm")

    assert res["status"] == "success"
    spy_screen.assert_called_once()
    assert spy_screen.call_args.kwargs["provider"] is mock_prov
    assert spy_screen.call_args.kwargs["model"] == "gemini-3.5-flash"
    spy_kw.assert_called_once()
    assert unscored_job.score is not None

    # Verify daily workflow cron timing matches 7:37 AM IST (02:07 UTC)
    daily_yml = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "daily.yml"
    content = daily_yml.read_text(encoding="utf-8")
    assert "cron: '7 2 * * *'" in content

