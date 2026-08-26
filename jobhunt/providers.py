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


class Provider:
    name = "base"
    required_env: str | None = None

    def preflight(self) -> None:
        """Fail before the first call, not on batch 1 of 40."""
        if self.required_env:
            self._env(self.required_env)

    def complete(self, model: str, system: str, user: str, max_tokens: int,
                 json_mode: bool = False) -> str:
        raise NotImplementedError

    def complete_document(self, model: str, prompt: str, pdf: bytes,
                          max_tokens: int) -> str:
        raise UnsupportedDocument(
            f"{self.name} cannot read PDFs here - pass a .txt/.md resume instead"
        )

    @staticmethod
    def _env(key: str) -> str:
        from .auth import _load_env_if_needed
        _load_env_if_needed()
        value = (os.environ.get(key) or "").strip()
        if not value:
            raise LLMError(f"{key} is not set (see .env.example)")
        return value


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

    def complete(self, model: str, system: str, user: str, max_tokens: int,
                 json_mode: bool = False) -> str:
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
                    print(f"  ! anthropic rate limit/error ({e}) — retrying in {delay}s ({attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
                raise LLMError(f"anthropic error: {e}") from e
        raise LLMError("anthropic failed after maximum retries")

    def complete_document(self, model: str, prompt: str, pdf: bytes,
                           max_tokens: int) -> str:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                msg = self._client().messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": [
                        {"type": "document", "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": base64.b64encode(pdf).decode(),
                        }},
                        {"type": "text", "text": prompt},
                    ]}],
                )
                return self._text(msg)
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = 3 * (attempt + 1)
                    print(f"  ! anthropic document rate limit/error ({e}) — retrying in {delay}s ({attempt + 1}/{max_retries})...")
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
        max_retries = 4
        url = f"{self.BASE}/{model}:generateContent"
        key = self._env("GEMINI_API_KEY")
        for attempt in range(max_retries):
            try:
                r = requests.post(
                    url,
                    params={"key": key},
                    json=body,
                    timeout=TIMEOUT,
                )
                if r.status_code == 429 and attempt < max_retries - 1:
                    retry_after = r.headers.get("Retry-After")
                    delay = max(float(retry_after), 5.0) if (retry_after and retry_after.isdigit()) else 6.0 * (attempt + 1)
                    print(f"  ! gemini rate limit (HTTP 429) — cooling down for {delay}s ({attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
                elif r.status_code in (500, 502, 503, 504) and attempt < max_retries - 1:
                    delay = 3.0 * (attempt + 1)
                    print(f"  ! gemini HTTP {r.status_code} — retrying in {delay}s ({attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
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



    def complete(self, model: str, system: str, user: str, max_tokens: int,
                 json_mode: bool = False) -> str:
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

    def complete_document(self, model: str, prompt: str, pdf: bytes,
                          max_tokens: int) -> str:
        return self._post(model, {
            "contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": "application/pdf",
                                 "data": base64.b64encode(pdf).decode()}},
                {"text": prompt},
            ]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.2},
        })


class OpenAICompatProvider(Provider):
    """Anything speaking /chat/completions - Groq, Together, OpenRouter, vLLM."""

    name = "openai-compatible"
    required_env = "GROQ_API_KEY"
    default_base = "https://api.groq.com/openai/v1"
    key_env = "GROQ_API_KEY"

    def complete(self, model: str, system: str, user: str, max_tokens: int,
                 json_mode: bool = False) -> str:
        base = os.getenv("LLM_BASE_URL", self.default_base).rstrip("/")
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": user}]
        payload: dict[str, Any] = {"model": model, "messages": messages,
                                   "max_tokens": max_tokens, "temperature": 0.2}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        max_retries = 4
        for attempt in range(max_retries):
            try:
                r = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {self._env(self.key_env)}"},
                    json=payload,
                    timeout=TIMEOUT,
                )
                if r.status_code == 429 and attempt < max_retries - 1:
                    retry_after = r.headers.get("Retry-After")
                    if self.name in ("groq", "openai-compatible"):
                        delay = 62.0
                    elif retry_after and retry_after.isdigit():
                        delay = max(float(retry_after), 5.0)
                    else:
                        delay = 5.0 * (attempt + 1)
                    print(f"  ! {self.name} rate limit (HTTP 429) — cooling down for {delay:.1f}s ({attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
                elif r.status_code in (500, 502, 503, 504) and attempt < max_retries - 1:
                    delay = 3.0 * (attempt + 1)
                    print(f"  ! {self.name} HTTP {r.status_code} — retrying in {delay}s ({attempt + 1}/{max_retries})...")
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
                    print(f"  ! {self.name} network error ({e}) — retrying in {delay}s ({attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
                raise LLMError(f"{self.name} network error: {e}") from e
        raise LLMError(f"{self.name} failed after {max_retries} attempts")  # pragma: no cover




class GroqProvider(OpenAICompatProvider):
    name = "groq"


class OllamaProvider(Provider):
    """Fully local. No key, no cost, no rate limit - just a slower model."""

    name = "ollama"

    def complete(self, model: str, system: str, user: str, max_tokens: int,
                 json_mode: bool = False) -> str:
        base = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": user}]
        payload: dict[str, Any] = {
            "model": model, "messages": messages, "stream": False,
            "options": {"temperature": 0.2, "num_predict": max_tokens},
        }
        if json_mode:
            payload["format"] = "json"
        try:
            r = requests.post(
                f"{base}/api/chat", json=payload, timeout=TIMEOUT,
            )
        except requests.RequestException as e:
            raise LLMError(
                f"ollama unreachable at {base} - is `ollama serve` running?") from e
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
    "groq": {"screen": "openai/gpt-oss-20b", "draft": "openai/gpt-oss-120b"},
    "openai-compatible": {"screen": "gpt-4o-mini", "draft": "gpt-4o"},
    "ollama": {"screen": "llama3.1", "draft": "llama3.1"},
}


def get_provider(name: str) -> Provider:
    try:
        return PROVIDERS[name]()
    except KeyError:
        raise LLMError(
            f"unknown provider {name!r}; pick one of {', '.join(PROVIDERS)}"
        ) from None


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

    name = (os.getenv(f"{stage.upper()}_PROVIDER")
            or os.getenv("LLM_PROVIDER")
            or default_provider).strip().lower()

    provider = get_provider(name)
    explicit_model = (os.getenv(f"{stage.upper()}_MODEL") or "").strip()

    # Avoid provider-model mismatch (e.g. legacy SCREEN_MODEL=gemini-3.5-flash in .env when provider is groq)
    if explicit_model and name == "groq" and ("gemini" in explicit_model.lower() or "claude" in explicit_model.lower()):
        model = DEFAULT_MODELS.get(name, {}).get(stage)
    elif explicit_model and name == "gemini" and ("llama" in explicit_model.lower() or "gpt" in explicit_model.lower() or "claude" in explicit_model.lower()):
        model = DEFAULT_MODELS.get(name, {}).get(stage)
    else:
        model = explicit_model or DEFAULT_MODELS.get(name, {}).get(stage)

    if not model:
        raise LLMError(f"set {stage.upper()}_MODEL for provider {name!r}")
    if check:
        provider.preflight()
    return provider, model
