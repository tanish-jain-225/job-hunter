"""Provider-agnostic LLM clients.

One tiny interface, five backends. Screening and drafting each pick their own
provider from env vars, so you can point the cheap pass at Groq or Gemini and
keep Claude for the expensive drafting pass - or run the whole thing on a free
tier with no card on file.

    complete(system, user)            -> str   (every provider)
    complete_document(prompt, pdf)    -> str   (Anthropic + Gemini only)

Nothing here parses JSON or knows what a Job is. That lives in llm.py.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any

import requests

TIMEOUT = 120


class LLMError(RuntimeError):
    """Anything that came back wrong from a provider."""


class UnsupportedDocument(LLMError):
    """Provider cannot read a PDF; caller should fall back to plain text."""


# ---------------------------------------------------------------------------


import threading

_RATE_LOCK = threading.Lock()
_KEY_COOLDOWN_MAP: dict[str, float] = {}
_LAST_CALL_MAP: dict[str, float] = {}
MIN_CALL_INTERVALS: dict[str, float] = {
    "gemini": 6.0,  # 10 RPM (exact 10 RPM free tier ceiling per Google AI Studio project)
    "groq": 2.0,  # 30 RPM (exact 30 RPM ceiling per Groq project)
    "anthropic": 1.2,
    "openai-compatible": 0.5,
    "ollama": 0.05,
}


def _enforce_rate_limit_throttle(provider_name: str, num_keys: int = 1) -> None:
    """Enforce leaky-bucket inter-call spacing per provider scaled by active API key count."""
    base_interval = MIN_CALL_INTERVALS.get(provider_name.lower(), 1.0)
    effective_keys = max(1, num_keys)
    min_interval = max(0.3, base_interval / effective_keys)
    with _RATE_LOCK:
        last_time = _LAST_CALL_MAP.get(provider_name.lower(), 0.0)
        now = time.time()
        elapsed = now - last_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    with _RATE_LOCK:
        _LAST_CALL_MAP[provider_name.lower()] = time.time()


def _record_key_cooldown(key: str, cooldown_seconds: float = 30.0) -> None:
    """Mark an API key as cooling down until time.time() + cooldown_seconds."""
    if key:
        with _RATE_LOCK:
            _KEY_COOLDOWN_MAP[key] = time.time() + max(10.0, cooldown_seconds)


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

    def complete(self, model: str, system: str, user: str, max_tokens: int, json_mode: bool = False) -> str:
        raise NotImplementedError

    def complete_document(self, model: str, prompt: str, pdf: bytes, max_tokens: int) -> str:
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

    def _client(self):
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

    def complete(self, model: str, system: str, user: str, max_tokens: int, json_mode: bool = False) -> str:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                msg = self._client().messages.create(
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

    def complete_document(self, model: str, prompt: str, pdf: bytes, max_tokens: int) -> str:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                msg = self._client().messages.create(
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

    def _post(self, model: str, body: dict) -> str:
        import random

        all_configured_keys = Provider._get_api_keys("GEMINI_API_KEY")
        if not all_configured_keys:
            raise LLMError("GEMINI_API_KEY is not set (see .env.example)")
        max_retries = max(6, len(all_configured_keys) * 3)
        url = f"{self.BASE}/{model}:generateContent"

        for attempt in range(max_retries):
            active_keys = _get_active_api_keys("GEMINI_API_KEY")
            if not active_keys:
                # All keys in temporary cooldown — wait briefly for key window reset
                time.sleep(3.0)
                active_keys = all_configured_keys
            key = active_keys[attempt % len(active_keys)]
            _enforce_rate_limit_throttle(self.name, num_keys=len(active_keys))
            try:
                r = requests.post(
                    url,
                    params={"key": key},
                    json=body,
                    timeout=TIMEOUT,
                )
                if r.status_code == 429 and attempt < max_retries - 1:
                    retry_after = r.headers.get("Retry-After")
                    cooldown = 60.0
                    if retry_after:
                        try:
                            cooldown = max(float(str(retry_after).strip()), 15.0)
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
                    total_delay = min(cooldown, 15.0) + random.uniform(0.2, 0.8)
                    print(
                        f"  ! gemini all keys rate limited (HTTP 429) — cooling down pool for {total_delay:.1f}s ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(total_delay)
                    continue

                elif r.status_code in (500, 502, 503, 504) and attempt < max_retries - 1:
                    delay = 3.0 * (attempt + 1) + random.uniform(0.1, 0.8)
                    print(
                        f"  ! gemini HTTP {r.status_code} — retrying in {delay:.1f}s ({attempt + 1}/{max_retries})..."
                    )
                    time.sleep(delay)
                    continue
                if r.status_code == 404 and model == "gemini-3.6-flash":
                    print("  ! gemini-3.6-flash HTTP 404 — retrying with model fallback gemini-1.5-flash...")
                    return self._post("gemini-1.5-flash", body)
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
                    delay = 5 * (attempt + 1)
                    print(f"  ! gemini network error ({e}) — retrying in {delay}s ({attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
                raise LLMError(f"gemini network error: {e}") from e
        raise LLMError(f"gemini failed after {max_retries} attempts")  # pragma: no cover

    def complete(self, model: str, system: str, user: str, max_tokens: int, json_mode: bool = False) -> str:
        gen: dict[str, Any] = {"maxOutputTokens": max_tokens, "temperature": 0.2}
        if json_mode:
            gen["responseMimeType"] = "application/json"
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": gen,
        }
        if system:
            body["system_instruction"] = {"parts": [{"text": system}]}
        return self._post(model, body)

    def complete_document(self, model: str, prompt: str, pdf: bytes, max_tokens: int) -> str:
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
        )


class OpenAICompatProvider(Provider):
    """Anything speaking /chat/completions - Groq, Together, OpenRouter, vLLM."""

    name = "openai-compatible"
    required_env = "GROQ_API_KEY"
    default_base = "https://api.groq.com/openai/v1"
    key_env = "GROQ_API_KEY"

    def complete(self, model: str, system: str, user: str, max_tokens: int, json_mode: bool = False) -> str:
        import random

        base = os.getenv("LLM_BASE_URL", self.default_base).rstrip("/")
        all_configured_keys = Provider._get_api_keys(self.key_env)
        if not all_configured_keys:
            raise LLMError(f"{self.key_env} is not set (see .env.example)")

        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        payload: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        max_retries = max(6, len(all_configured_keys) * 3)
        for attempt in range(max_retries):
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

    def complete(self, model: str, system: str, user: str, max_tokens: int, json_mode: bool = False) -> str:
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
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "openai-compatible": OpenAICompatProvider,
    "ollama": OllamaProvider,
}

DEFAULT_MODELS = {
    "anthropic": {"screen": "claude-3-5-haiku-20241022", "draft": "claude-3-7-sonnet-20250219"},
    "gemini": {"screen": "gemini-3.6-flash", "draft": "gemini-3.6-flash"},
    "groq": {"screen": "llama-3.1-8b-instant", "draft": "llama-3.3-70b-versatile"},
    "openai-compatible": {"screen": "gpt-4o-mini", "draft": "gpt-4o"},
    "ollama": {"screen": "llama3.1", "draft": "llama3.1"},
}


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise LLMError(f"unknown provider {name!r}; pick one of {', '.join(PROVIDERS)}") from None


def resolve(stage: str, check: bool = True) -> tuple[Provider, str]:
    """Which provider + model handles this stage ("screen" or "draft")?

    Precedence:
    1. Stage-specific env var (SCREEN_PROVIDER / DRAFT_PROVIDER)
    2. Global env var (LLM_PROVIDER)
    3. Auto-detected API key with intelligent pipeline stage splitting:
       - If GROQ_API_KEY is present:
         - stage == "screen" -> "groq" (fast high-throughput batch screening, 14,400 RPD)
         - stage == "draft"  -> "gemini" if GEMINI_API_KEY else "groq"
       - If only GEMINI_API_KEY is present -> "gemini"
       - If only ANTHROPIC_API_KEY is present -> "anthropic"
       - Fallback -> "gemini"
    """
    from .auth import _load_env_if_needed

    _load_env_if_needed()

    has_groq = bool((os.getenv("GROQ_API_KEY") or "").strip())
    has_gemini = bool((os.getenv("GEMINI_API_KEY") or "").strip())
    has_anthropic = bool((os.getenv("ANTHROPIC_API_KEY") or "").strip())

    if stage.lower() == "screen":
        if has_groq:
            default_provider = "groq"
        elif has_gemini:
            default_provider = "gemini"
        elif has_anthropic:
            default_provider = "anthropic"
        else:
            default_provider = "gemini"
    else:  # draft
        if has_gemini:
            default_provider = "gemini"
        elif has_groq:
            default_provider = "groq"
        elif has_anthropic:
            default_provider = "anthropic"
        else:
            default_provider = "gemini"

    name = (os.getenv(f"{stage.upper()}_PROVIDER") or os.getenv("LLM_PROVIDER") or default_provider).strip().lower()

    provider = get_provider(name)
    explicit_model = (os.getenv(f"{stage.upper()}_MODEL") or "").strip()

    # Avoid provider-model mismatch (e.g. legacy SCREEN_MODEL=gemini-3.5-flash in .env when provider is groq)
    if explicit_model and name == "groq" and ("gemini" in explicit_model.lower() or "claude" in explicit_model.lower()):
        model = DEFAULT_MODELS.get(name, {}).get(stage)
    elif (
        explicit_model
        and name == "gemini"
        and ("llama" in explicit_model.lower() or "gpt" in explicit_model.lower() or "claude" in explicit_model.lower())
    ):
        model = DEFAULT_MODELS.get(name, {}).get(stage)
    else:
        model = explicit_model or DEFAULT_MODELS.get(name, {}).get(stage)

    if not model:
        raise LLMError(f"set {stage.upper()}_MODEL for provider {name!r}")
    if check:
        provider.preflight()
    return provider, model


def get_fallback_provider(current_name: str, stage: str = "screen") -> tuple[Provider, str] | None:
    """Find the next available configured live provider when primary provider quota is exhausted."""
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
                model = DEFAULT_MODELS.get(candidate, {}).get(stage, "gemini-3.6-flash")
                return prov, model
            except Exception:
                continue

    return None
