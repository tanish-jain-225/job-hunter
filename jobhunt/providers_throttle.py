"""Throttling, model aliases, and key cooldown management for LLM providers."""

from __future__ import annotations

import os
import threading
import time

_RATE_LOCK = threading.Lock()
_KEY_COOLDOWN_MAP: dict[str, float] = {}
_DISABLED_KEYS: set[str] = set()
_LAST_CALL_MAP: dict[str, float] = {}
_KEY_LAST_CALL_MAP: dict[str, float] = {}
_KEY_ADAPTIVE_INTERVALS: dict[str, float] = {}
_KEY_SUCCESS_STREAK: dict[str, int] = {}
_KEY_ADAPTIVE_FLOOR: dict[str, float] = {}
_MODEL_COOLDOWN_MAP: dict[str, float] = {}
_MODEL_ALIAS_MAP: dict[str, str] = {}
_GEMINI_KEY_COUNTER: int = 0
_PROVIDER_KEY_COUNTERS: dict[str, int] = {}
_GEMINI_COUNTER_LOCK = threading.Lock()

MIN_CALL_INTERVALS: dict[str, float] = {
    "gemini": 5.0,  # 12 RPM (multiple of 5; safe 20% margin below 15 RPM ceiling)
    "groq": 2.0,  # 30 RPM (exact 30 RPM ceiling per Groq project)
    "anthropic": 1.2,
    "openai-compatible": 0.5,
    "ollama": 0.05,
}

ADAPTIVE_MIN_INTERVALS: dict[str, float] = {
    "gemini": 0.05,
    "groq": 0.05,
    "anthropic": 0.05,
    "openai-compatible": 0.05,
    "ollama": 0.02,
}


def _cooldown_slot(key: str, model: str | None = None) -> str:
    """Build scoped cooldown dictionary key for an API key and optional model."""
    return f"{key}::{model}" if model else key


def _record_model_cooldown(model: str, cooldown_seconds: float = 600.0) -> None:
    """Mark a model endpoint as cooling down / exhausted."""
    if model:
        with _RATE_LOCK:
            _MODEL_COOLDOWN_MAP[model] = max(
                _MODEL_COOLDOWN_MAP.get(model, 0.0),
                time.time() + cooldown_seconds,
            )


def _is_model_cooling_down(model: str) -> bool:
    """Check if a model endpoint is currently marked in cooldown."""
    if not model:
        return False
    with _RATE_LOCK:
        return time.time() < _MODEL_COOLDOWN_MAP.get(model, 0.0)


def _record_model_alias(from_model: str, to_model: str) -> None:
    """Cache working endpoint alias for a model name to eliminate subsequent 404 retries."""
    if from_model and to_model and from_model != to_model:
        with _RATE_LOCK:
            _MODEL_ALIAS_MAP[from_model] = to_model


def _resolve_model_alias(model: str) -> str:
    """Resolve model through any cached endpoint alias chain without cycles."""
    if not model:
        return model
    with _RATE_LOCK:
        cur = model
        seen: set[str] = set()
        while cur in _MODEL_ALIAS_MAP and cur not in seen:
            seen.add(cur)
            cur = _MODEL_ALIAS_MAP[cur]
        return cur


def reset_provider_state() -> None:
    """Thread-safely reset all provider global throttles, cooldown caches, and key rotation counters."""
    global _GEMINI_KEY_COUNTER
    with _RATE_LOCK:
        _KEY_COOLDOWN_MAP.clear()
        _DISABLED_KEYS.clear()
        _LAST_CALL_MAP.clear()
        _KEY_LAST_CALL_MAP.clear()
        _KEY_ADAPTIVE_INTERVALS.clear()
        _KEY_SUCCESS_STREAK.clear()
        _KEY_ADAPTIVE_FLOOR.clear()
        _MODEL_COOLDOWN_MAP.clear()
        _MODEL_ALIAS_MAP.clear()
    with _GEMINI_COUNTER_LOCK:
        _GEMINI_KEY_COUNTER = 0
        _PROVIDER_KEY_COUNTERS.clear()


def get_provider_key_index(provider_name: str) -> int:
    """Thread-safely fetch and increment round-robin key index for a provider."""
    global _GEMINI_KEY_COUNTER
    name = (provider_name or "gemini").strip().lower()
    with _GEMINI_COUNTER_LOCK:
        idx = _PROVIDER_KEY_COUNTERS.get(name, 0)
        _PROVIDER_KEY_COUNTERS[name] = idx + 1
        if name == "gemini":
            _GEMINI_KEY_COUNTER = idx + 1
        return idx


def get_gemini_key_index() -> int:
    """Thread-safely fetch and increment current Gemini round-robin key index."""
    return get_provider_key_index("gemini")


def _reserve_throttle_slot(slot_map: dict[str, float], slot_key: str, min_interval: float) -> None:
    """Reserve the next leaky-bucket timestamp inside _RATE_LOCK before sleeping outside it."""
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("TEST_THROTTLING"):
        return
    if min_interval <= 0:
        return
    with _RATE_LOCK:
        now = time.time()
        last_time = slot_map.get(slot_key, 0.0)
        scheduled = max(now, last_time + min_interval)
        slot_map[slot_key] = scheduled
        wait = scheduled - now
    if wait > 0:
        time.sleep(wait)


def _enforce_rate_limit_throttle(provider_name: str, num_keys: int = 1) -> None:
    """Enforce leaky-bucket inter-call spacing per provider scaled by active API key count."""
    base_interval = MIN_CALL_INTERVALS.get(provider_name.lower(), 1.0)
    effective_keys = max(1, num_keys)
    min_interval = max(0.3, base_interval / effective_keys)
    _reserve_throttle_slot(_LAST_CALL_MAP, provider_name.lower(), min_interval)


def _enforce_key_throttle(key: str, min_interval: float = 5.0) -> None:
    """Ensure an individual API key is never invoked faster than min_interval (12 RPM safe pacing)."""
    _reserve_throttle_slot(_KEY_LAST_CALL_MAP, key, min_interval)


def _adaptive_slot(key: str, provider_name: str = "gemini") -> str:
    """Build per-provider, per-key AIMD tracking key."""
    prov = (provider_name or "gemini").strip().lower()
    return f"{prov}::{key or 'default'}"


def get_adaptive_key_interval(
    key: str,
    provider_name: str = "gemini",
    default_interval: float | None = None,
) -> float:
    """Return the current AIMD inter-call interval (seconds) for an API key."""
    prov = (provider_name or "gemini").strip().lower()
    base = float(default_interval) if default_interval is not None else MIN_CALL_INTERVALS.get(prov, 1.0)
    slot = _adaptive_slot(key, prov)
    with _RATE_LOCK:
        return _KEY_ADAPTIVE_INTERVALS.get(slot, base)


def _record_key_success(
    key: str,
    provider_name: str = "gemini",
    default_interval: float | None = None,
) -> float:
    """Gradually tighten pacing for keys proving higher RPM headroom (AIMD speedup)."""
    prov = (provider_name or "gemini").strip().lower()
    base = float(default_interval) if default_interval is not None else MIN_CALL_INTERVALS.get(prov, 1.0)
    min_floor = ADAPTIVE_MIN_INTERVALS.get(prov, 0.05)
    slot = _adaptive_slot(key, prov)
    with _RATE_LOCK:
        streak = _KEY_SUCCESS_STREAK.get(slot, 0) + 1
        _KEY_SUCCESS_STREAK[slot] = streak
        cur = _KEY_ADAPTIVE_INTERVALS.get(slot, base)
        if streak >= 25:
            # Sustained 429-free run permits lifting any earlier burst floor
            _KEY_ADAPTIVE_FLOOR.pop(slot, None)
        floor = max(min_floor, _KEY_ADAPTIVE_FLOOR.get(slot, min_floor))
        if streak >= 3:
            cur = max(floor, round(cur * 0.72, 4))
        _KEY_ADAPTIVE_INTERVALS[slot] = cur
        return cur


def _record_key_rate_limit(
    key: str,
    provider_name: str = "gemini",
    default_interval: float | None = None,
) -> float:
    """Back off pacing multiplicatively on HTTP 429 so free keys settle without sustained retries."""
    prov = (provider_name or "gemini").strip().lower()
    base = float(default_interval) if default_interval is not None else MIN_CALL_INTERVALS.get(prov, 1.0)
    slot = _adaptive_slot(key, prov)
    with _RATE_LOCK:
        _KEY_SUCCESS_STREAK[slot] = 0
        cur = _KEY_ADAPTIVE_INTERVALS.get(slot, base)
        backed_off = min(15.0, max(base, round(cur * 1.6, 4)))
        _KEY_ADAPTIVE_INTERVALS[slot] = backed_off
        _KEY_ADAPTIVE_FLOOR[slot] = max(_KEY_ADAPTIVE_FLOOR.get(slot, 0.0), max(0.5, base * 0.85))
        return backed_off


def _enforce_adaptive_key_throttle(
    key: str,
    provider_name: str = "gemini",
    default_interval: float | None = None,
) -> float:
    """Reserve the next leaky-bucket slot for key using its current AIMD adaptive interval."""
    interval = get_adaptive_key_interval(key, provider_name=provider_name, default_interval=default_interval)
    _reserve_throttle_slot(_KEY_LAST_CALL_MAP, _adaptive_slot(key, provider_name), interval)
    return interval


def _record_key_cooldown(key: str, cooldown_seconds: float = 30.0, model: str | None = None) -> None:
    """Mark an API key (optionally scoped to a specific model) as cooling down."""
    if not key:
        return
    until = time.time() + max(10.0, cooldown_seconds)
    slot = _cooldown_slot(key, model)
    with _RATE_LOCK:
        _KEY_COOLDOWN_MAP[slot] = max(_KEY_COOLDOWN_MAP.get(slot, 0.0), until)


def _is_key_cooling_down(key: str, model: str | None = None) -> bool:
    """Check if an API key is disabled or cooling down globally or for the given model."""
    if not key:
        return False
    now = time.time()
    with _RATE_LOCK:
        if key in _DISABLED_KEYS:
            return True
        if now < _KEY_COOLDOWN_MAP.get(key, 0.0):
            return True
        if model and now < _KEY_COOLDOWN_MAP.get(_cooldown_slot(key, model), 0.0):
            return True
        return False


def _record_key_disabled(key: str) -> None:
    """Mark an API key as invalid/unauthorized for the duration of the process."""
    if key:
        with _RATE_LOCK:
            _DISABLED_KEYS.add(key)


def _is_key_disabled(key: str) -> bool:
    """Return True if an API key was permanently rejected (HTTP 401/403/invalid)."""
    if not key:
        return False
    with _RATE_LOCK:
        return key in _DISABLED_KEYS
