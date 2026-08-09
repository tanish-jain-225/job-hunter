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
        value = (os.environ.get(key) or "").strip()
        if not value:
            raise LLMError(f"{key} is not set (see .env.example)")
        return value


class AnthropicProvider(Provider):
    """Claude via the official SDK."""

    name = "anthropic"
    required_env = "ANTHROPIC_API_KEY"

    def _client(self):
        try:
            from anthropic import Anthropic
        except ImportError:
            raise LLMError("pip install anthropic") from None
        return Anthropic(api_key=self._env("ANTHROPIC_API_KEY"))

    @staticmethod
    def _text(msg) -> str:
        return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")

    def complete(self, model: str, system: str, user: str, max_tokens: int,
                 json_mode: bool = False) -> str:
        msg = self._client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return self._text(msg)

    def complete_document(self, model: str, prompt: str, pdf: bytes,
                          max_tokens: int) -> str:
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


class GeminiProvider(Provider):
    """Google AI Studio REST API. Generous free tier, no card needed."""

    name = "gemini"
    required_env = "GEMINI_API_KEY"
    BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def _post(self, model: str, body: dict) -> str:
        max_retries = 3
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
                if r.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    delay = 3 * (attempt + 1)
                    print(f"  ! gemini HTTP {r.status_code} — retrying in {delay}s ({attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
                if r.status_code != 200:
                    raise LLMError(f"gemini HTTP {r.status_code}: {r.text[:300]}")
                try:
                    candidate = r.json()["candidates"][0]
                except (KeyError, IndexError, ValueError) as e:
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
                    delay = 3 * (attempt + 1)
                    print(f"  ! gemini network error ({e}) — retrying in {delay}s ({attempt + 1}/{max_retries})...")
                    time.sleep(delay)
                    continue
                raise LLMError(f"gemini network error: {e}") from e
        raise LLMError("gemini max retries reached")

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
        max_retries = 3
        for attempt in range(max_retries):
            try:
                r = requests.post(
                    f"{base}/chat/completions",
                    headers={"Authorization": f"Bearer {self._env(self.key_env)}"},
                    json=payload,
                    timeout=TIMEOUT,
                )
                if r.status_code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                    delay = 3 * (attempt + 1)
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
        raise LLMError(f"{self.name} max retries reached")


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
    "gemini": {"screen": "gemini-2.0-flash", "draft": "gemini-2.0-flash"},
    "groq": {"screen": "llama-3.3-70b-versatile", "draft": "llama-3.3-70b-versatile"},
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

    Precedence: stage-specific env var -> global env var -> auto-detected API key -> built-in default.
    """
    default_provider = "anthropic"
    if os.getenv("GEMINI_API_KEY"):
        default_provider = "gemini"
    elif os.getenv("GROQ_API_KEY"):
        default_provider = "groq"
    elif os.getenv("ANTHROPIC_API_KEY"):
        default_provider = "anthropic"

    name = (os.getenv(f"{stage.upper()}_PROVIDER")
            or os.getenv("LLM_PROVIDER")
            or default_provider).strip().lower()

    provider = get_provider(name)
    model = (os.getenv(f"{stage.upper()}_MODEL") or "").strip() \
        or DEFAULT_MODELS.get(name, {}).get(stage)
    if not model:
        raise LLMError(f"set {stage.upper()}_MODEL for provider {name!r}")
    if check:
        provider.preflight()
    return provider, model
