"""Throttling, model aliases, and key cooldown management for LLM providers."""

from __future__ import annotations

import os
import threading
import time

_RATE_LOCK = threading.Lock()
_KEY_COOLDOWN_MAP: dict[str, float] = {}
_LAST_CALL_MAP: dict[str, float] = {}
_KEY_LAST_CALL_MAP: dict[str, float] = {}
_MODEL_COOLDOWN_MAP: dict[str, float] = {}
_MODEL_ALIAS_MAP: dict[str, str] = {}
_GEMINI_KEY_COUNTER: int = 0
_GEMINI_COUNTER_LOCK = threading.Lock()

MIN_CALL_INTERVALS: dict[str, float] = {
    "gemini": 5.0,  # 12 RPM (multiple of 5; safe 20% margin below 15 RPM ceiling)
    "groq": 2.0,  # 30 RPM (exact 30 RPM ceiling per Groq project)
    "anthropic": 1.2,
    "openai-compatible": 0.5,
    "ollama": 0.05,
}


def _record_model_cooldown(model: str, cooldown_seconds: float = 600.0) -> None:
    """Mark a model endpoint as cooling down / exhausted."""
    if model:
        with _RATE_LOCK:
            _MODEL_COOLDOWN_MAP[model] = time.time() + cooldown_seconds


def _is_model_cooling_down(model: str) -> bool:
    """Check if a model endpoint is currently marked in cooldown."""
    if not model:
        return False
    with _RATE_LOCK:
        return time.time() < _MODEL_COOLDOWN_MAP.get(model, 0.0)


def _record_model_alias(from_model: str, to_model: str) -> None:
    """Cache working endpoint alias for a model name to eliminate subsequent 404 retries."""
    if from_model and to_model:
        with _RATE_LOCK:
            _MODEL_ALIAS_MAP[from_model] = to_model


def _resolve_model_alias(model: str) -> str:
    """Resolve model through any cached endpoint alias."""
    if not model:
        return model
    with _RATE_LOCK:
        return _MODEL_ALIAS_MAP.get(model, model)


def reset_provider_state() -> None:
    """Thread-safely reset all provider global throttles, cooldown caches, and key rotation counters."""
    global _GEMINI_KEY_COUNTER
    with _RATE_LOCK:
        _KEY_COOLDOWN_MAP.clear()
        _LAST_CALL_MAP.clear()
        _KEY_LAST_CALL_MAP.clear()
        _MODEL_COOLDOWN_MAP.clear()
        _MODEL_ALIAS_MAP.clear()
    with _GEMINI_COUNTER_LOCK:
        _GEMINI_KEY_COUNTER = 0


def get_gemini_key_index() -> int:
    """Thread-safely fetch and increment current Gemini round-robin key index."""
    global _GEMINI_KEY_COUNTER
    with _GEMINI_COUNTER_LOCK:
        idx = _GEMINI_KEY_COUNTER
        _GEMINI_KEY_COUNTER += 1
        return idx


def _enforce_rate_limit_throttle(provider_name: str, num_keys: int = 1) -> None:
    """Enforce leaky-bucket inter-call spacing per provider scaled by active API key count."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("TEST_THROTTLING"):
        return
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


def _enforce_key_throttle(key: str, min_interval: float = 5.0) -> None:
    """Ensure an individual API key is never invoked faster than min_interval (12 RPM safe pacing)."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("TEST_THROTTLING"):
        return
    with _RATE_LOCK:
        last_time = _KEY_LAST_CALL_MAP.get(key, 0.0)
        now = time.time()
        elapsed = now - last_time
    if elapsed < min_interval:
        time.sleep(min_interval - elapsed)
    with _RATE_LOCK:
        _KEY_LAST_CALL_MAP[key] = time.time()


def _record_key_cooldown(key: str, cooldown_seconds: float = 30.0) -> None:
    """Mark an API key as cooling down until time.time() + cooldown_seconds."""
    if key:
        with _RATE_LOCK:
            _KEY_COOLDOWN_MAP[key] = time.time() + max(10.0, cooldown_seconds)
