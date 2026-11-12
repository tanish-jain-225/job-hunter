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
    _DISABLED_KEYS,
    _LAST_CALL_MAP,
    _KEY_LAST_CALL_MAP,
    _MODEL_COOLDOWN_MAP,
    _MODEL_ALIAS_MAP,
    _GEMINI_KEY_COUNTER,
    _GEMINI_COUNTER_LOCK,
    get_gemini_key_index,
    get_provider_key_index,
    MIN_CALL_INTERVALS,
    _record_model_cooldown,
    _is_model_cooling_down,
    _record_model_alias,
    _resolve_model_alias,
    reset_provider_state,
    _enforce_rate_limit_throttle,
    _enforce_key_throttle,
    _record_key_cooldown,
    _is_key_cooling_down,
    _record_key_disabled,
    _is_key_disabled,
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
    "GEMINI_FALLBACK_ORDER",
    "GROQ_FALLBACK_ORDER",
    "_RATE_LOCK",
    "_KEY_COOLDOWN_MAP",
    "_DISABLED_KEYS",
    "_LAST_CALL_MAP",
    "_KEY_LAST_CALL_MAP",
    "_MODEL_COOLDOWN_MAP",
    "_MODEL_ALIAS_MAP",
    "_GEMINI_KEY_COUNTER",
    "_GEMINI_COUNTER_LOCK",
    "get_provider_key_index",
    "MIN_CALL_INTERVALS",
    "_record_model_cooldown",
    "_is_model_cooling_down",
    "_record_model_alias",
    "_resolve_model_alias",
    "reset_provider_state",
    "_enforce_rate_limit_throttle",
    "_enforce_key_throttle",
    "_record_key_cooldown",
    "_is_key_cooling_down",
    "_record_key_disabled",
    "_is_key_disabled",
    "_get_active_api_keys",
]

GEMINI_FALLBACK_ORDER: tuple[str, ...] = (
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
)

GROQ_FALLBACK_ORDER: tuple[str, ...] = (
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
)


def _is_vercel_env() -> bool:
    """Return True inside live Vercel serverless execution (outside pytest)."""
    return os.environ.get("VERCEL") == "1" and not os.environ.get("PYTEST_CURRENT_TEST")


def _request_timeout() -> float:
    """Return HTTP timeout bounded safely below Vercel serverless walls."""
    return 6.5 if _is_vercel_env() else float(TIMEOUT)


def _sleep_bounded(seconds: float) -> None:
    """Sleep for retry backoff, capping duration in short-lived Vercel invocations."""
    if seconds <= 0:
        return
    delay = min(seconds, 0.5) if _is_vercel_env() else seconds
    time.sleep(delay)


def _rotate_cycle(items: list[str], start_index: int) -> list[str]:
    """Rotate a non-empty list so iteration begins at start_index % len(items)."""
    if not items:
        return []
    offset = start_index % len(items)
    return items[offset:] + items[:offset]


def _get_eligible_keys(
    configured_keys: list[str], model: str | None = None
) -> tuple[list[str], list[str]]:
    """Return (active_non_cooling_keys, all_non_disabled_keys) for a key list & model."""
    usable = [k for k in configured_keys if not _is_key_disabled(k)]
    active = [k for k in usable if not _is_key_cooling_down(k, model=model)]
    return active, usable


def _get_active_api_keys(key_env: str, model: str | None = None) -> list[str]:
    """Get list of API keys that are not disabled or in cooldown for the given model."""
    all_keys = Provider._get_api_keys(key_env)
    active, usable = _get_eligible_keys(all_keys, model=model)
    return active if active else usable


def _is_invalid_key_response(status_code: int, body_text: str) -> bool:
    """Detect HTTP errors caused by a bad, revoked, or unauthorized API key."""
    if status_code in (401, 403):
        return True
    if status_code == 400:
        low = (body_text or "").lower()
        return any(
            marker in low
            for marker in (
                "api_key_invalid",
                "api key not valid",
                "api key expired",
                "invalid api key",
                "invalid_api_key",
                "permission denied",
            )
        )
    return False


def _is_daily_quota_error(body_text: str) -> bool:
    """Heuristic check for daily RPD exhaustion vs short-term RPM/TPM limits."""
    low = (body_text or "").lower()
    return any(marker in low for marker in ("per day", "perday", "rpd", "daily"))


def _parse_retry_after(
    headers: Any, body_text: str = "", default: float = 20.0, minimum: float = 5.0
) -> float:
    """Safely parse Retry-After header or error body delay hint."""
    import re

    retry_after = headers.get("Retry-After") if headers else None
    if retry_after is not None:
        try:
            return max(float(str(retry_after).strip()), minimum)
        except (ValueError, TypeError):
            pass
    if body_text:
        m = re.search(r'(?:retryDelay["\s:]+|retry in\s+)(\d+(?:\.\d+)?)s', body_text, re.I)
        if m:
            try:
                return max(float(m.group(1)), minimum)
            except (ValueError, TypeError):
                pass
    return default


def _next_model_in_order(
    current_model: str, fallback_order: tuple[str, ...], tried_models: set[str]
) -> str | None:
    """Return the next untried fallback model in fallback_order without cycles."""
    for candidate in fallback_order:
        resolved = _resolve_model_alias(candidate)
        if resolved != current_model and candidate != current_model and resolved not in tried_models and candidate not in tried_models:
            return resolved
    return None


def _build_gemini_model_queue(requested_model: str) -> list[str]:
    """Build ordered, cycle-free Gemini model queue skipping models already in cooldown."""
    head = _resolve_model_alias(requested_model)
    ordered: list[str] = [head]
    for candidate in GEMINI_FALLBACK_ORDER:
        resolved = _resolve_model_alias(candidate)
        if resolved not in ordered:
            ordered.append(resolved)
    non_cooling = [m for m in ordered if not _is_model_cooling_down(m)]
    return non_cooling if non_cooling else [ordered[-1]]


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
    def _parse_api_keys(raw: str | None) -> list[str]:
        """Parse comma-separated API keys, deduplicating while preserving order."""
        if not raw or not str(raw).strip():
            return []
        seen: set[str] = set()
        out: list[str] = []
        for item in str(raw).split(","):
            k = item.strip()
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

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
        return Provider._parse_api_keys(os.environ.get(key))


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

    def _invoke_with_rotation(
        self,
        op_name: str,
        fn: Any,
        api_key: str | None = None,
    ) -> str:
        """Execute an Anthropic SDK call with multi-key rotation and retry backoff."""
        configured = (
            Provider._parse_api_keys(api_key)
            if (api_key and str(api_key).strip())
            else Provider._get_api_keys(self.required_env)
        )
        usable = [k for k in configured if not _is_key_disabled(k)]
        keys: list[str | None]
        if usable:
            keys = list(_rotate_cycle(usable, get_provider_key_index(self.name)))
        elif not configured:
            keys = [None]
        else:
            keys = []
        if configured and not usable:
            raise LLMError(f"{op_name} error: all configured API keys are invalid")

        max_attempts = max(3, len(keys))
        for attempt in range(max_attempts):
            cur_key = keys[attempt % len(keys)]
            _enforce_rate_limit_throttle(self.name, num_keys=max(1, len(usable)))
            try:
                try:
                    c = self._client(api_key=cur_key) if cur_key else self._client()
                except TypeError:
                    c = self._client()
                msg = fn(c)
                return self._text(msg)
            except Exception as e:
                err_low = str(e).lower()
                if cur_key and any(tok in err_low for tok in ("401", "403", "authentication", "invalid x-api-key", "invalid api key")):
                    if len(configured) > 1:
                        _record_key_disabled(cur_key)
                    if len(configured) == 1 or not [k for k in configured if not _is_key_disabled(k)]:
                        raise LLMError(f"{op_name} error: {e}") from e
                if cur_key and ("429" in err_low or "rate" in err_low):
                    _record_key_cooldown(cur_key, 30.0)
                if attempt < max_attempts - 1:
                    delay = 3 * (attempt + 1)
                    print(
                        f"  ! {op_name} rate limit/error ({e}) — retrying in {delay}s ({attempt + 1}/{max_attempts})..."
                    )
                    _sleep_bounded(delay)
                    continue
                raise LLMError(f"{op_name} error: {e}") from e
        raise LLMError(f"{op_name} failed after maximum retries")  # pragma: no cover

    def complete(
        self,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        json_mode: bool = False,
        api_key: str | None = None,
    ) -> str:
        return self._invoke_with_rotation(
            "anthropic",
            lambda c: c.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            ),
            api_key=api_key,
        )

    def complete_document(
        self,
        model: str,
        prompt: str,
        pdf: bytes,
        max_tokens: int,
        api_key: str | None = None,
    ) -> str:
        return self._invoke_with_rotation(
            "anthropic document",
            lambda c: c.messages.create(
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
            ),
            api_key=api_key,
        )


class GeminiProvider(Provider):
    """Google AI Studio REST API. Generous free tier, no card needed."""

    name = "gemini"
    required_env = "GEMINI_API_KEY"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def _post(self, model: str, body: dict, api_key: str | None = None) -> str:
        import random

        if api_key and str(api_key).strip():
            configured_keys = Provider._parse_api_keys(api_key)
        else:
            configured_keys = Provider._get_api_keys("GEMINI_API_KEY")

        if not configured_keys:
            raise LLMError("GEMINI_API_KEY is not set (see .env.example)")

        model_queue = _build_gemini_model_queue(model)
        tried_models: set[str] = set()
        last_error: LLMError | None = None
        last_cause: Exception | None = None
        q_idx = 0

        while q_idx < len(model_queue):
            effective_model = _resolve_model_alias(model_queue[q_idx])
            q_idx += 1
            if effective_model in tried_models:
                continue
            tried_models.add(effective_model)

            active_keys, usable_keys = _get_eligible_keys(configured_keys, model=effective_model)
            if not usable_keys:
                raise last_error or LLMError("gemini: all configured API keys are invalid or disabled")

            if not active_keys:
                nxt = _next_model_in_order(effective_model, GEMINI_FALLBACK_ORDER, tried_models)
                if q_idx < len(model_queue) or nxt:
                    if nxt and nxt not in model_queue[q_idx:]:
                        model_queue.append(nxt)
                    continue
                _sleep_bounded(1.0)
                active_keys = usable_keys

            url = f"{self.BASE}/{effective_model}:generateContent"
            req_idx = get_gemini_key_index()
            ordered_keys = _rotate_cycle(active_keys, req_idx)
            tier_attempts = max(2, len(ordered_keys)) if len(usable_keys) == 1 else len(ordered_keys)

            for attempt_idx in range(tier_attempts):
                key = ordered_keys[attempt_idx % len(ordered_keys)]
                _enforce_key_throttle(key, min_interval=5.0)
                try:
                    r = requests.post(
                        url,
                        params={"key": key},
                        headers={"x-goog-api-key": key},
                        json=body,
                        timeout=_request_timeout(),
                    )
                    raw_text = getattr(r, "text", "")
                    body_text = raw_text if isinstance(raw_text, str) else ""

                    if r.status_code == 429:
                        cooldown = _parse_retry_after(getattr(r, "headers", None), body_text, default=20.0, minimum=5.0)
                        _record_key_cooldown(key, cooldown, model=effective_model)
                        last_error = LLMError(f"gemini HTTP 429: {body_text[:300]}")

                        remaining_active = [
                            k for k in ordered_keys[attempt_idx + 1 :] if not _is_key_cooling_down(k, model=effective_model)
                        ]
                        if remaining_active:
                            print(
                                f"  ! gemini key rate limited on {effective_model} (HTTP 429) — rotating to active API key ({len(remaining_active)} fresh keys remaining)..."
                            )
                            _sleep_bounded(0.1 + random.uniform(0.05, 0.15))
                            continue

                        if len(usable_keys) == 1 and attempt_idx < tier_attempts - 1:
                            total_delay = min(cooldown, 5.0) + random.uniform(0.1, 0.4)
                            print(
                                f"  ! gemini all keys rate limited (HTTP 429) — cooling down pool for {total_delay:.1f}s ({attempt_idx + 1}/{tier_attempts})..."
                            )
                            _sleep_bounded(total_delay)
                            continue

                        model_cooldown = 600.0 if _is_daily_quota_error(body_text) else 90.0
                        _record_model_cooldown(effective_model, model_cooldown)
                        nxt = _next_model_in_order(effective_model, GEMINI_FALLBACK_ORDER, tried_models)
                        if nxt:
                            if nxt not in model_queue[q_idx:]:
                                model_queue.append(nxt)
                            print(
                                f"  ! {effective_model} quota exceeded across all keys — cascading to {nxt}..."
                            )
                        break

                    if _is_invalid_key_response(r.status_code, body_text):
                        if len(configured_keys) > 1:
                            _record_key_disabled(key)
                        last_error = LLMError(f"gemini HTTP {r.status_code}: {body_text[:300]}")
                        still_usable = [k for k in ordered_keys[attempt_idx + 1 :] if not _is_key_disabled(k)]
                        if still_usable:
                            print(
                                f"  ! gemini key unauthorized/invalid (HTTP {r.status_code}) — disabling key and rotating ({len(still_usable)} keys remaining)..."
                            )
                            continue
                        if len(configured_keys) == 1 or not any(not _is_key_disabled(k) for k in configured_keys):
                            raise last_error
                        break

                    if r.status_code in (500, 502, 503, 504):
                        last_error = LLMError(f"gemini HTTP {r.status_code}: {body_text[:300]}")
                        if attempt_idx < tier_attempts - 1:
                            delay = 1.0 * (attempt_idx + 1) + random.uniform(0.1, 0.4)
                            print(
                                f"  ! gemini HTTP {r.status_code} — rotating key and retrying in {delay:.1f}s ({attempt_idx + 1}/{tier_attempts})..."
                            )
                            _sleep_bounded(delay)
                            continue
                        _record_model_cooldown(effective_model, 60.0)
                        nxt = _next_model_in_order(effective_model, GEMINI_FALLBACK_ORDER, tried_models)
                        if nxt:
                            if nxt not in model_queue[q_idx:]:
                                model_queue.append(nxt)
                            print(
                                f"  ! {effective_model} high demand (HTTP {r.status_code}) — cascading to {nxt}..."
                            )
                        break

                    if r.status_code == 404:
                        _record_model_cooldown(effective_model, 86400.0)
                        last_error = LLMError(f"gemini HTTP 404: {body_text[:300]}")
                        nxt = _next_model_in_order(effective_model, GEMINI_FALLBACK_ORDER, tried_models)
                        if nxt:
                            _record_model_alias(model, nxt)
                            _record_model_alias(effective_model, nxt)
                            if nxt not in model_queue[q_idx:]:
                                model_queue.append(nxt)
                            print(f"  ! {effective_model} HTTP 404 — cached alias -> {nxt}...")
                            break
                        raise last_error

                    if r.status_code != 200:
                        raise LLMError(f"gemini HTTP {r.status_code}: {body_text[:300]}")

                    try:
                        data = r.json()
                    except (ValueError, TypeError) as e:
                        if attempt_idx < tier_attempts - 1:
                            delay = 5 * (attempt_idx + 1)
                            print(
                                f"  ! gemini malformed JSON — retrying in {delay}s ({attempt_idx + 1}/{tier_attempts})..."
                            )
                            _sleep_bounded(delay)
                            continue
                        raise LLMError(f"gemini returned invalid JSON: {body_text[:300]}") from e

                    try:
                        candidate = data["candidates"][0]
                    except (KeyError, IndexError) as e:
                        raise LLMError(f"gemini returned no candidates: {body_text[:300]}") from e

                    reason = candidate.get("finishReason")
                    parts = (candidate.get("content") or {}).get("parts") or []
                    text = "".join(p.get("text", "") for p in parts if "text" in p)
                    if reason == "MAX_TOKENS" or (not text and reason not in (None, "STOP")):
                        raise LLMError(
                            f"gemini stopped early (finishReason={reason}) with "
                            f"{len(text)} chars of output — raise max_tokens for this stage"
                        )
                    if not text:
                        raise LLMError(f"gemini returned no text: {body_text[:300]}")
                    return text

                except requests.RequestException as e:
                    last_error = LLMError(f"gemini network error: {e}")
                    last_cause = e
                    if attempt_idx < tier_attempts - 1:
                        delay = 2 * (attempt_idx + 1)
                        print(
                            f"  ! gemini network error/timeout ({e}) — retrying in {delay}s ({attempt_idx + 1}/{tier_attempts})..."
                        )
                        _sleep_bounded(delay)
                        continue
                    _record_model_cooldown(effective_model, 180.0)
                    nxt = _next_model_in_order(effective_model, GEMINI_FALLBACK_ORDER, tried_models)
                    if nxt:
                        if nxt not in model_queue[q_idx:]:
                            model_queue.append(nxt)
                        print(
                            f"  ! {effective_model} network error/timeout across all keys — cascading to {nxt}..."
                        )
                    break

        if last_error is not None:
            if last_cause is not None:
                raise last_error from last_cause
            raise last_error
        raise LLMError("gemini failed after exhausting all keys and fallback models")  # pragma: no cover

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
        json_mode: bool = False,
    ) -> str:
        gen: dict[str, Any] = {"maxOutputTokens": max_tokens, "temperature": 0.1}
        if json_mode or "json" in prompt.lower():
            gen["responseMimeType"] = "application/json"
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
                "generationConfig": gen,
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
            configured_keys = Provider._parse_api_keys(api_key)
        else:
            configured_keys = Provider._get_api_keys(self.key_env)
        if not configured_keys:
            raise LLMError(f"{self.key_env} is not set (see .env.example)")

        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        model_queue: list[str] = [model]
        if base == self.default_base:
            for alt_m in GROQ_FALLBACK_ORDER:
                if alt_m not in model_queue:
                    model_queue.append(alt_m)
        non_cooling = [m for m in model_queue if not _is_model_cooling_down(m)]
        effective_queue = non_cooling if non_cooling else [model_queue[-1]]

        tried_models: set[str] = set()
        last_error: LLMError | None = None
        last_cause: Exception | None = None

        for cur_model in effective_queue:
            if cur_model in tried_models:
                continue
            tried_models.add(cur_model)

            active_keys, usable_keys = _get_eligible_keys(configured_keys, model=cur_model)
            if not usable_keys:
                raise last_error or LLMError(f"{self.name}: all configured API keys are invalid")
            if not active_keys:
                active_keys = usable_keys

            payload: dict[str, Any] = {
                "model": cur_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.2,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            req_idx = get_provider_key_index(self.name)
            ordered_keys = _rotate_cycle(active_keys, req_idx)
            tier_attempts = max(3, len(ordered_keys) * 2) if len(usable_keys) == 1 else max(len(ordered_keys), 2)

            for attempt_idx in range(tier_attempts):
                key = ordered_keys[attempt_idx % len(ordered_keys)]
                _enforce_rate_limit_throttle(self.name, num_keys=max(1, len(ordered_keys)))
                try:
                    r = requests.post(
                        f"{base}/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json=payload,
                        timeout=_request_timeout(),
                    )
                    raw_text = getattr(r, "text", "")
                    body_text = raw_text if isinstance(raw_text, str) else ""

                    if r.status_code == 429:
                        cooldown = _parse_retry_after(getattr(r, "headers", None), body_text, default=60.0, minimum=10.0)
                        _record_key_cooldown(key, cooldown, model=cur_model)
                        last_error = LLMError(f"{self.name} HTTP 429: {body_text[:300]}")
                        remaining = [k for k in ordered_keys[attempt_idx + 1 :] if not _is_key_cooling_down(k, model=cur_model)]
                        if remaining:
                            print(
                                f"  ! {self.name} key rate limited (HTTP 429) — rotating to active API key ({len(remaining)} fresh keys remaining)..."
                            )
                            _sleep_bounded(0.1 + random.uniform(0.05, 0.15))
                            continue
                        if len(usable_keys) == 1 and attempt_idx < tier_attempts - 1:
                            total_delay = min(cooldown, 15.0) + random.uniform(0.2, 0.8)
                            print(
                                f"  ! {self.name} all keys rate limited (HTTP 429) — cooling down pool for {total_delay:.1f}s ({attempt_idx + 1}/{tier_attempts})..."
                            )
                            _sleep_bounded(total_delay)
                            continue
                        _record_model_cooldown(cur_model, 120.0)
                        break

                    if _is_invalid_key_response(r.status_code, body_text):
                        if len(configured_keys) > 1:
                            _record_key_disabled(key)
                        last_error = LLMError(f"{self.name} HTTP {r.status_code}: {body_text[:300]}")
                        still_usable = [k for k in ordered_keys[attempt_idx + 1 :] if not _is_key_disabled(k)]
                        if still_usable:
                            continue
                        if len(configured_keys) == 1 or not any(not _is_key_disabled(k) for k in configured_keys):
                            raise last_error
                        break

                    if r.status_code == 404:
                        _record_model_cooldown(cur_model, 86400.0)
                        last_error = LLMError(f"{self.name} HTTP 404: {body_text[:300]}")
                        break

                    if r.status_code in (500, 502, 503, 504):
                        last_error = LLMError(f"{self.name} HTTP {r.status_code}: {body_text[:300]}")
                        if attempt_idx < tier_attempts - 1:
                            delay = 3.0 * (attempt_idx + 1) + random.uniform(0.1, 0.8)
                            print(
                                f"  ! {self.name} HTTP {r.status_code} — retrying in {delay:.1f}s ({attempt_idx + 1}/{tier_attempts})..."
                            )
                            _sleep_bounded(delay)
                            continue
                        _record_model_cooldown(cur_model, 60.0)
                        break

                    if r.status_code != 200:
                        raise LLMError(f"{self.name} HTTP {r.status_code}: {body_text[:300]}")
                    try:
                        return r.json()["choices"][0]["message"]["content"]
                    except (KeyError, IndexError, ValueError) as e:
                        raise LLMError(f"{self.name} malformed reply: {body_text[:300]}") from e
                except requests.RequestException as e:
                    last_error = LLMError(f"{self.name} network error: {e}")
                    last_cause = e
                    if attempt_idx < tier_attempts - 1:
                        delay = 3 * (attempt_idx + 1)
                        print(
                            f"  ! {self.name} network error ({e}) — retrying in {delay}s ({attempt_idx + 1}/{tier_attempts})..."
                        )
                        _sleep_bounded(delay)
                        continue
                    raise last_error from e

        if last_error is not None:
            if last_cause is not None:
                raise last_error from last_cause
            raise last_error
        raise LLMError(f"{self.name} failed after exhausting keys and models")  # pragma: no cover


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


def get_fallback_provider(
    current_name: str,
    stage: str = "screen",
    excluded: set[str] | list[str] | tuple[str, ...] | None = None,
) -> tuple[Provider, str] | None:
    """Return a distinct configured fallback provider when primary provider exhausts, avoiding cycles."""
    from .auth import _load_env_if_needed

    _load_env_if_needed()

    current_clean = (current_name or "").strip().lower()
    blocked = {current_clean} | {str(x).strip().lower() for x in (excluded or ()) if str(x).strip()}
    custom_base = (os.getenv("LLM_BASE_URL") or "").strip().rstrip("/")
    has_custom_openai_base = bool(custom_base and custom_base != OpenAICompatProvider.default_base)

    candidates = ["gemini", "groq", "anthropic", "openai-compatible"]
    for candidate in candidates:
        if candidate in blocked:
            continue
        if candidate == "openai-compatible" and not has_custom_openai_base and "groq" in blocked:
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

    return None
