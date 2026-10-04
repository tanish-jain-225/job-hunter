"""Multi-provider AI client for Job Hunter.

Default engine: Google Gemini (gemini-3.5-flash) — used for candidate screening,
fit scoring, and tailored application kit drafting.

Optional providers selectable via LLM_PROVIDER / SCREEN_PROVIDER / DRAFT_PROVIDER:
  - gemini (default)    Google AI Studio REST API (1M tokens/day free, CSV key rotation)
  - anthropic           Claude via the official SDK  (`pip install 'jobhunt[anthropic]'`)
  - groq                Groq ultra-fast inference    (GROQ_API_KEY)
  - openai-compatible   Any /chat/completions endpoint (LLM_BASE_URL + GROQ_API_KEY)
  - ollama              Fully local, no key needed   (OLLAMA_HOST)

    complete(system, user)            -> str   (JSON / prose)
    complete_document(prompt, pdf)    -> str   (native PDF parsing — Gemini & Anthropic only)

Nothing here parses JSON or knows what a Job is. That lives in llm.py.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any

import requests

TIMEOUT = 60


class LLMError(RuntimeError):
    """Anything that came back wrong from a provider."""


class UnsupportedDocument(LLMError):
    """Provider cannot read a PDF; caller should fall back to plain text."""


from .providers_throttle import (
    _RATE_LOCK,
    _KEY_COOLDOWN_MAP,
    _LAST_CALL_MAP,
    _KEY_LAST_CALL_MAP,
    _MODEL_COOLDOWN_MAP,
    _MODEL_ALIAS_MAP,
    _GEMINI_KEY_COUNTER,
    _GEMINI_COUNTER_LOCK,
    get_gemini_key_index,
    MIN_CALL_INTERVALS,
    _record_model_cooldown,
    _is_model_cooling_down,
    _record_model_alias,
    _resolve_model_alias,
    reset_provider_state,
    _enforce_rate_limit_throttle,
    _enforce_key_throttle,
    _record_key_cooldown,
)

__all__ = [
    "LLMError",
    "UnsupportedDocument",
    "Provider",
    "AnthropicProvider",
    "GeminiProvider",
    "OpenAICompatProvider",
    "GroqProvider",
    "OllamaProvider",
    "get_provider",
    "resolve",
    "get_fallback_provider",
    "DEFAULT_MODELS",
    "_RATE_LOCK",
    "_KEY_COOLDOWN_MAP",
    "_LAST_CALL_MAP",
    "_KEY_LAST_CALL_MAP",
    "_MODEL_COOLDOWN_MAP",
    "_MODEL_ALIAS_MAP",
    "_GEMINI_KEY_COUNTER",
    "_GEMINI_COUNTER_LOCK",
    "MIN_CALL_INTERVALS",
    "_record_model_cooldown",
    "_is_model_cooling_down",
    "_record_model_alias",
    "_resolve_model_alias",
    "reset_provider_state",
    "_enforce_rate_limit_throttle",
    "_enforce_key_throttle",
    "_record_key_cooldown",
    "_get_active_api_keys",
]


def _get_active_api_keys(key_env: str) -> list[str]:
    """Get list of API keys that are not currently in cooldown reset period."""
    all_keys = Provider._get_api_keys(key_env)
    now = time.time()
    with _RATE_LOCK:
        active = [k for k in all_keys if now >= _KEY_COOLDOWN_MAP.get(k, 0.0)]
    return active if active else all_keys


class Provider:
    name = "base"
    required_env: str | None = None

    def preflight(self) -> None:
        """Fail before the first call, not on batch 1 of 40."""
        if self.required_env:
            self._env(self.required_env)

    def complete(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        json_mode: bool = False,
        api_key: str | None = None,
    ) -> str:
        raise NotImplementedError

    def complete_document(
        self,
        model: str,
        prompt: str,
        pdf: bytes,
        max_tokens: int,
        api_key: str | None = None,
    ) -> str:
        raise UnsupportedDocument(f"{self.name} cannot read PDFs here - pass a .txt/.md resume instead")

    @staticmethod
    def _env(key: str) -> str:
        keys = Provider._get_api_keys(key)
        if not keys:
            raise LLMError(f"{key} is not set (see .env.example)")
        return keys[0]

    @staticmethod
    def _get_api_keys(key: str) -> list[str]:
        from .auth import _load_env_if_needed

        _load_env_if_needed()
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            return []
        return [k.strip() for k in raw.split(",") if k.strip()]


class AnthropicProvider(Provider):
    """Claude via the official SDK."""

    name = "anthropic"
    required_env = "ANTHROPIC_API_KEY"
    _client_instance: Any = None

    def _client(self, api_key: str | None = None):
        if api_key and str(api_key).strip():
            try:
                from anthropic import Anthropic
            except ImportError:
                raise LLMError("pip install anthropic") from None
            return Anthropic(api_key=str(api_key).strip())
        if not hasattr(self, "_client_instance") or self._client_instance is None:
            try:
                from anthropic import Anthropic
            except ImportError:
                raise LLMError("pip install anthropic") from None
            self._client_instance = Anthropic(api_key=self._env("ANTHROPIC_API_KEY"))
        return self._client_instance

    @staticmethod
    def _text(msg) -> str:
        return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")

    def complete(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        json_mode: bool = False,
        api_key: str | None = None,
    ) -> str:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                try:
                    c = self._client(api_key=api_key) if api_key else self._client()
                except TypeError:
                    c = self._client()
                msg = c.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return self._text(msg)
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 3 * (attempt + 1)
                    print(
                        f"  ! anthropic rate limit/error ({e}) — retrying in {delay}s ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                    continue
                raise LLMError(f"anthropic error: {e}") from e
        raise LLMError("anthropic failed after maximum retries")

    def complete_document(
        self,
        model: str,
        prompt: str,
        pdf: bytes,
        max_tokens: int,
        api_key: str | None = None,
    ) -> str:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                try:
                    c = self._client(api_key=api_key) if api_key else self._client()
                except TypeError:
                    c = self._client()
                msg = c.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "application/pdf",
                                        "data": base64.b64encode(pdf).decode(),
                                    },
                                },
                                {"type": "text", "text": prompt},
                            ],
                        }
                    ],
                )
                return self._text(msg)
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 3 * (attempt + 1)
                    print(
                        f"  ! anthropic document rate limit/error ({e}) — retrying in {delay}s ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                    continue
                raise LLMError(f"anthropic document error: {e}") from e
        raise LLMError("anthropic document failed after maximum retries")


class GeminiProvider(Provider):
    """Google AI Studio REST API. Generous free tier, no card needed."""

    name = "gemini"
    required_env = "GEMINI_API_KEY"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def _post(self, model: str, body: dict, api_key: str | None = None) -> str:
        import random

        effective_model = _resolve_model_alias(model)
        if _is_model_cooling_down(effective_model):
            if effective_model in ("gemini-3.5-flash", "gemini-3.6-flash", "gemini-2.5-flash"):
                effective_model = _resolve_model_alias("gemini-flash-latest")
            elif effective_model == "gemini-flash-latest":
                effective_model = "gemini-flash-lite-latest"

        if api_key and str(api_key).strip():
            all_configured_keys = [str(api_key).strip()]
        else:
            all_configured_keys = Provider._get_api_keys("GEMINI_API_KEY")

        if not all_configured_keys:
            raise LLMError("GEMINI_API_KEY is not set (see .env.example)")
        max_retries = max(2, min(4, len(all_configured_keys)))
        url = f"{self.BASE}/{effective_model}:generateContent"

        req_idx = get_gemini_key_index()

        for attempt in range(max_retries):
            if api_key and str(api_key).strip():
                active_keys = all_configured_keys
            else:
                active_keys = _get_active_api_keys("GEMINI_API_KEY")
            if not active_keys:
                # All keys in temporary cooldown — wait briefly for key window reset
                time.sleep(1.0)
                active_keys = all_configured_keys
            if attempt == 0:
                key = active_keys[req_idx % len(active_keys)]
            else:
                key = active_keys[0]
            _enforce_key_throttle(key, min_interval=5.0)
            try:
                r = requests.post(
                    url,
                    params={"key": key},
                    headers={"x-goog-api-key": key},
                    json=body,
                    timeout=TIMEOUT,
                )
                if r.status_code == 429 and attempt < max_retries - 1:
                    retry_after = r.headers.get("Retry-After")
                    cooldown = 20.0
                    if retry_after:
                        try:
                            cooldown = max(float(str(retry_after).strip()), 5.0)
                        except (ValueError, TypeError):
                            pass
                    _record_key_cooldown(key, cooldown)
                    remaining_keys = [k for k in active_keys if k != key]
                    if remaining_keys:
                        print(
                            f"  ! gemini key rate limited (HTTP 429) — rotating to active API key ({len(remaining_keys)} fresh keys remaining)..."
                        )
                        time.sleep(0.1 + random.uniform(0.05, 0.15))
                        continue
                    total_delay = min(cooldown, 5.0) + random.uniform(0.1, 0.4)
                    print(
                        f"  ! gemini all keys rate limited (HTTP 429) — cooling down pool for {total_delay:.1f}s ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(total_delay)
                    continue
                elif r.status_code == 429 and attempt == max_retries - 1:
                    _record_model_cooldown(effective_model, 600.0)
                    if effective_model in ("gemini-3.5-flash", "gemini-3.6-flash", "gemini-2.5-flash"):
                        print(f"  ! {effective_model} quota exceeded across all keys — cascading to gemini-flash-latest...")
                        return self._post("gemini-flash-latest", body, api_key=api_key)
                    elif effective_model == "gemini-flash-latest":
                        print("  ! gemini-flash-latest quota exceeded — cascading to gemini-flash-lite-latest...")
                        return self._post("gemini-flash-lite-latest", body, api_key=api_key)

                elif r.status_code in (500, 502, 503, 504) and attempt < max_retries - 1:
                    delay = 1.0 * (attempt + 1) + random.uniform(0.1, 0.4)
                    print(
                        f"  ! gemini HTTP {r.status_code} — rotating key and retrying in {delay:.1f}s ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                    continue
                elif r.status_code in (500, 502, 503, 504) and attempt == max_retries - 1:
                    _record_model_cooldown(effective_model, 60.0)
                    if effective_model in ("gemini-3.5-flash", "gemini-3.6-flash", "gemini-2.5-flash"):
                        print(f"  ! {effective_model} high demand (HTTP {r.status_code}) — cascading to gemini-flash-latest...")
                        return self._post("gemini-flash-latest", body, api_key=api_key)
                    elif effective_model == "gemini-flash-latest":
                        print(f"  ! {effective_model} high demand (HTTP {r.status_code}) — cascading to gemini-flash-lite-latest...")
                        return self._post("gemini-flash-lite-latest", body, api_key=api_key)

                if r.status_code == 404:
                    _record_model_cooldown(effective_model, 86400.0)
                    target_fallback = "gemini-flash-latest" if effective_model != "gemini-flash-latest" else "gemini-flash-lite-latest"
                    _record_model_alias(model, target_fallback)
                    _record_model_alias(effective_model, target_fallback)
                    print(f"  ! {effective_model} HTTP 404 — cached alias -> {target_fallback}...")
                    return self._post(target_fallback, body, api_key=api_key)
                if r.status_code != 200:
                    raise LLMError(f"gemini HTTP {r.status_code}: {r.text[:300]}")
                try:
                    data = r.json()
                except (ValueError, TypeError) as e:
                    if attempt < max_retries - 1:
                        delay = 5 * (attempt + 1)
                        print(f"  ! gemini malformed JSON — retrying in {delay}s ({attempt + 1}/{max_retries})...")
                        time.sleep(delay)
                        continue
                    raise LLMError(f"gemini returned invalid JSON: {r.text[:300]}") from e
                try:
                    candidate = data["candidates"][0]
                except (KeyError, IndexError) as e:
                    raise LLMError(f"gemini returned no candidates: {r.text[:300]}") from e

                reason = candidate.get("finishReason")
                parts = (candidate.get("content") or {}).get("parts") or []
                text = "".join(p.get("text", "") for p in parts if "text" in p)
                if reason == "MAX_TOKENS" or (not text and reason not in (None, "STOP")):
                    raise LLMError(
                        f"gemini stopped early (finishReason={reason}) with "
                        f"{len(text)} chars of output — raise max_tokens for this stage"
                    )
                if not text:
                    raise LLMError(f"gemini returned no text: {r.text[:300]}")
                return text
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    delay = 2 * (attempt + 1)
                    print(f"  ! gemini network error/timeout ({e}) — retrying in {delay}s ({attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
                if effective_model in ("gemini-3.5-flash", "gemini-3.6-flash", "gemini-2.5-flash"):
                    _record_model_cooldown(effective_model, 180.0)
                    print(f"  ! {effective_model} network error/timeout across all keys — cascading to gemini-flash-latest...")
                    return self._post("gemini-flash-latest", body, api_key=api_key)
                elif effective_model == "gemini-flash-latest":
                    _record_model_cooldown(effective_model, 180.0)
                    print("  ! gemini-flash-latest network error/timeout — cascading to gemini-flash-lite-latest...")
                    return self._post("gemini-flash-lite-latest", body, api_key=api_key)
                raise LLMError(f"gemini network error: {e}") from e
        raise LLMError(f"gemini failed after {max_retries} attempts")  # pragma: no cover

    def complete(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        json_mode: bool = False,
        api_key: str | None = None,
    ) -> str:
        gen: dict[str, Any] = {"maxOutputTokens": max_tokens, "temperature": 0.2}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen,
        }
        if system:
            body["system_instruction"] = {"parts": [{"text": system}]}
        return self._post(model, body, api_key=api_key)

    def complete_document(
        self,
        model: str,
        prompt: str,
        pdf: bytes,
        max_tokens: int,
        api_key: str | None = None,
    ) -> str:
        return self._post(
            model,
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf).decode()}},
                            {"text": prompt},
                        ],
                    }
                ],
                "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2},
            },
            api_key=api_key,
        )


class OpenAICompatProvider(Provider):
    """Anything speaking /chat/completions - Groq, Together, OpenRouter, vLLM."""

    name = "openai-compatible"
    required_env = "GROQ_API_KEY"
    default_base = "https://api.groq.com/openai/v1"
    key_env = "GROQ_API_KEY"

    def complete(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        json_mode: bool = False,
        api_key: str | None = None,
    ) -> str:
        import random

        base = os.getenv("LLM_BASE_URL", self.default_base).rstrip("/")
        if api_key and str(api_key).strip():
            all_configured_keys = [str(api_key).strip()]
        else:
            all_configured_keys = Provider._get_api_keys(self.key_env)
        if not all_configured_keys:
            raise LLMError(f"{self.key_env} is not set (see .env.example)")

        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        payload: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        max_retries = max(6, len(all_configured_keys) * 3)
        for attempt in range(max_retries):
            if api_key and str(api_key).strip():
                active_keys = all_configured_keys
            else:
                active_keys = _get_active_api_keys(self.key_env)
            if not active_keys:
                time.sleep(3.0)
                active_keys = all_configured_keys
            key = active_keys[attempt % len(active_keys)]
            _enforce_rate_limit_throttle(self.name, num_keys=len(active_keys))
            try:
                r = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json=payload,
                    timeout=TIMEOUT,
                )
                if r.status_code == 429 and attempt < max_retries - 1:
                    retry_after = r.headers.get("Retry-After")
                    cooldown = 60.0
                    if retry_after:
                        try:
                            cooldown = max(float(str(retry_after).strip()), 10.0)
                        except (ValueError, TypeError):
                            pass
                    _record_key_cooldown(key, cooldown)
                    remaining_keys = [k for k in active_keys if k != key]
                    if remaining_keys:
                        print(
                            f"  ! {self.name} key rate limited (HTTP 429) — rotating to active API key ({len(remaining_keys)} fresh keys remaining)..."
                        )
                        time.sleep(0.1 + random.uniform(0.05, 0.15))
                        continue
                    total_delay = min(cooldown, 15.0) + random.uniform(0.2, 0.8)
                    print(
                        f"  ! {self.name} all keys rate limited (HTTP 429) — cooling down pool for {total_delay:.1f}s ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(total_delay)
                    continue

                elif r.status_code in (500, 502, 503, 504) and attempt < max_retries - 1:
                    delay = 3.0 * (attempt + 1) + random.uniform(0.1, 0.8)
                    print(
                        f"  ! {self.name} HTTP {r.status_code} — retrying in {delay:.1f}s ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                    continue
                if r.status_code != 200:
                    raise LLMError(f"{self.name} HTTP {r.status_code}: {r.text[:300]}")
                try:
                    return r.json()["choices"][0]["message"]["content"]
                except (KeyError, IndexError, ValueError) as e:
                    raise LLMError(f"{self.name} malformed reply: {r.text[:300]}") from e
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    delay = 3 * (attempt + 1)

                    print(
                        f"  ! {self.name} network error ({e}) — retrying in {delay}s ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                    continue
                raise LLMError(f"{self.name} network error: {e}") from e
        raise LLMError(f"{self.name} failed after {max_retries} attempts")  # pragma: no cover


class GroqProvider(OpenAICompatProvider):
    name = "groq"


class OllamaProvider(Provider):
    """Fully local. No key, no cost, no rate limit - just a slower model."""

    name = "ollama"

    def complete(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        json_mode: bool = False,
        api_key: str | None = None,
    ) -> str:
        base = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        try:
            r = requests.post(
                f"{base}/api/chat",
                json=payload,
                timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            raise LLMError(f"ollama unreachable at {base} - is `ollama serve` running?") from e
        if r.status_code != 200:
            raise LLMError(f"ollama HTTP {r.status_code}: {r.text[:300]}")
        try:
            return r.json()["message"]["content"]
        except (KeyError, ValueError) as e:
            raise LLMError(f"ollama malformed reply: {r.text[:300]}") from e


PROVIDERS = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "anthropic": AnthropicProvider,
    "openai-compatible": OpenAICompatProvider,
    "ollama": OllamaProvider,
}

DEFAULT_MODELS = {
    "gemini": {"screen": "gemini-3.5-flash", "draft": "gemini-3.5-flash"},
    "groq": {"screen": "llama-3.1-8b-instant", "draft": "llama-3.3-70b-versatile"},
    "anthropic": {"screen": "claude-3-5-haiku-20241022", "draft": "claude-3-7-sonnet-20250219"},
    "openai-compatible": {"screen": "gpt-4o-mini", "draft": "gpt-4o"},
    "ollama": {"screen": "llama3.1", "draft": "llama3.1"},
}


def get_provider(name: str = "gemini") -> Provider:
    clean_name = (name or "gemini").strip().lower()
    if clean_name in PROVIDERS:
        return PROVIDERS[clean_name]()
    if clean_name in ("google", "flash", "gemini-flash", "default"):
        return GeminiProvider()
    raise LLMError(f"unknown provider {name!r}; pick one of {', '.join(PROVIDERS)}")


def resolve(stage: str = "screen", check: bool = True) -> tuple[Provider, str]:
    """Which provider + model handles this stage?

    Precedence:
    1. Stage-specific env var (SCREEN_PROVIDER / DRAFT_PROVIDER)
    2. Global env var (LLM_PROVIDER)
    3. Default -> Google Gemini (gemini-3.5-flash)
    """
    from .auth import _load_env_if_needed

    _load_env_if_needed()

    default_provider = "gemini"
    name = (os.getenv(f"{stage.upper()}_PROVIDER") or os.getenv("LLM_PROVIDER") or default_provider).strip().lower()

    provider = get_provider(name)
    explicit_model = (os.getenv(f"{stage.upper()}_MODEL") or os.getenv("LLM_MODEL") or "").strip()
    model = explicit_model or DEFAULT_MODELS.get(name, {}).get(stage)
    if not model and name == "gemini":
        model = "gemini-3.5-flash"

    if not model:
        raise LLMError(f"set {stage.upper()}_MODEL for provider {name!r}")
    if check:
        provider.preflight()
    return provider, model


def get_fallback_provider(current_name: str, stage: str = "screen") -> tuple[Provider, str] | None:
    """Return an active live provider instance if available when primary provider quota is exhausted."""
    from .auth import _load_env_if_needed

    _load_env_if_needed()

    candidates = ["gemini", "groq", "anthropic", "openai-compatible"]
    current_clean = (current_name or "").strip().lower()

    for candidate in candidates:
        if candidate == current_clean:
            continue
        req_env = PROVIDERS[candidate].required_env
        if req_env and bool((os.getenv(req_env) or "").strip()):
            try:
                prov = get_provider(candidate)
                prov.preflight()
                model = DEFAULT_MODELS.get(candidate, {}).get(stage, "gemini-3.5-flash")
                return prov, model
            except Exception:
                continue

    if bool((os.getenv("GEMINI_API_KEY") or "").strip()):
        try:
            prov = get_provider("gemini")
            prov.preflight()
            return prov, "gemini-3.5-flash"
        except Exception:
            return None
    return None
