"""Supabase Authentication & JWT Session Verification Module for Job Hunter.

Provides token extraction, Supabase Auth API / JWT signature validation,
caching, and a Flask @require_auth decorator to secure API endpoints.
"""

from __future__ import annotations

import functools
import hashlib
import os
import threading
import time
from typing import Any, Callable, Dict, Optional

import requests
from flask import g, jsonify, request

try:
    import jwt
except ImportError:
    jwt = None  # type: ignore

# In-memory token verification cache: token_hash -> (user_dict, expires_at_epoch)
_TOKEN_CACHE: Dict[str, tuple[Dict[str, Any], float]] = {}
_TOKEN_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 60.0
_MAX_TOKEN_CACHE_SIZE = 1000


def _prune_token_cache_locked(now: float) -> None:
    """Sweep expired tokens and cap maximum memory footprint (must be called with _TOKEN_CACHE_LOCK)."""
    expired = [h for h, (_, exp) in _TOKEN_CACHE.items() if now >= exp]
    for h in expired:
        _TOKEN_CACHE.pop(h, None)
    if len(_TOKEN_CACHE) > _MAX_TOKEN_CACHE_SIZE:
        # Evict oldest excess items
        excess = len(_TOKEN_CACHE) - _MAX_TOKEN_CACHE_SIZE
        for h in list(_TOKEN_CACHE.keys())[:excess]:
            _TOKEN_CACHE.pop(h, None)


def _prune_token_cache(now: float) -> None:
    """Sweep expired tokens with thread safety."""
    with _TOKEN_CACHE_LOCK:
        _prune_token_cache_locked(now)


_ENV_LOADED = False


def _load_env_if_needed() -> None:
    """Ensure .env is loaded via jobhunt.cli helper."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from jobhunt import cli

        cli._load_env()
        _ENV_LOADED = True
    except Exception:
        pass


def get_supabase_config() -> dict[str, Any]:
    """Return Supabase configuration dictionary from environment variables."""
    _load_env_if_needed()
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    anon_key = (os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    jwt_secret = (os.environ.get("SUPABASE_JWT_SECRET") or "").strip()
    auth_req_env = (os.environ.get("AUTH_REQUIRED") or "").strip().lower()

    if auth_req_env in ("0", "false", "no", "off"):
        auth_required = False
    elif auth_req_env in ("1", "true", "yes", "on"):
        auth_required = True
    else:
        # If credentials exist, default to requiring auth; otherwise false for local dev
        auth_required = bool(url and anon_key)

    return {
        "supabase_url": url,
        "supabase_anon_key": anon_key,
        "supabase_jwt_secret": jwt_secret,
        "auth_required": auth_required,
    }


def is_auth_required() -> bool:
    """Check if authentication is active and required for API access."""
    cfg = get_supabase_config()
    return bool(cfg["auth_required"])


def extract_bearer_token() -> Optional[str]:
    """Extract Bearer access token from Authorization header or HttpOnly cookie."""
    # 1. Authorization header: "Bearer <token>" (case-insensitive, preferred)
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    # 2. HttpOnly cookie fallback (supports standard and Supabase SSR formats)
    for c_name in ("sb_access_token", "supabase_token"):
        cookie_token = request.cookies.get(c_name)
        if cookie_token and cookie_token.strip():
            return cookie_token.strip()

    for k, v in request.cookies.items():
        if k.startswith("sb-") and k.endswith("-auth-token"):
            try:
                import json
                import urllib.parse

                raw_val = urllib.parse.unquote(v)
                c_data = json.loads(raw_val)
                if isinstance(c_data, dict) and c_data.get("access_token"):
                    return c_data["access_token"]
                elif isinstance(c_data, list) and len(c_data) > 0 and isinstance(c_data[0], str):
                    return c_data[0]
            except Exception:
                pass

    return None


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate a Supabase JWT token and return user profile information dict or None."""
    if not token or not isinstance(token, str):
        return None

    cfg = get_supabase_config()
    url = cfg["supabase_url"]
    anon_key = cfg["supabase_anon_key"]
    jwt_secret = cfg["supabase_jwt_secret"]

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.time()

    # Check memory cache (thread-safe)
    with _TOKEN_CACHE_LOCK:
        if token_hash in _TOKEN_CACHE:
            user_info, expires_at = _TOKEN_CACHE[token_hash]
            if now < expires_at:
                return user_info
            else:
                _TOKEN_CACHE.pop(token_hash, None)

    # 1. Try local PyJWT verification if SUPABASE_JWT_SECRET is configured
    if jwt and jwt_secret:
        try:
            decoded = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_signature": True, "verify_exp": True, "verify_aud": False},
            )
            user_data = {
                "id": decoded.get("sub"),
                "email": decoded.get("email"),
                "role": decoded.get("role", "authenticated"),
                "user_metadata": decoded.get("user_metadata", {}),
                "app_metadata": decoded.get("app_metadata", {}),
            }
            jwt_exp = decoded.get("exp")
            cache_exp = min(now + _CACHE_TTL_SECONDS, float(jwt_exp)) if jwt_exp else now + _CACHE_TTL_SECONDS
            with _TOKEN_CACHE_LOCK:
                _prune_token_cache_locked(now)
                _TOKEN_CACHE[token_hash] = (user_data, cache_exp)
            return user_data
        except Exception:
            # Fall through to Supabase Auth API verification
            pass

    # 2. Verify with Supabase Auth endpoint (GET /auth/v1/user)
    if url and anon_key:
        try:
            endpoint = f"{url}/auth/v1/user"
            headers = {
                "Authorization": f"Bearer {token}",
                "apikey": anon_key,
            }
            resp = requests.get(endpoint, headers=headers, timeout=5)
            if resp.status_code == 200:
                user_obj = resp.json()
                user_data = {
                    "id": user_obj.get("id"),
                    "email": user_obj.get("email"),
                    "role": user_obj.get("role", "authenticated"),
                    "user_metadata": user_obj.get("user_metadata", {}),
                    "app_metadata": user_obj.get("app_metadata", {}),
                    "created_at": user_obj.get("created_at"),
                }
                with _TOKEN_CACHE_LOCK:
                    _prune_token_cache_locked(now)
                    _TOKEN_CACHE[token_hash] = (user_data, now + _CACHE_TTL_SECONDS)
                return user_data
        except Exception as e:
            print(f"[Auth] Supabase verification request failed: {e}")
            return None

    # 3. If no secret and no Supabase URL configured, fallback decode without signature if in dev mode
    if jwt and not is_auth_required():
        try:
            decoded = jwt.decode(token, options={"verify_signature": False})
            return {
                "id": decoded.get("sub", "dev_user"),
                "email": decoded.get("email", "dev@example.com"),
                "role": "authenticated",
            }
        except Exception:
            pass

    return None


def clear_token_cache() -> None:
    """Clear in-memory token cache (useful for testing)."""
    with _TOKEN_CACHE_LOCK:
        _TOKEN_CACHE.clear()


def require_auth(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to require valid Supabase JWT authentication on Flask route."""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not is_auth_required():
            # In dev mode with auth disabled, still extract token identity if passed
            tok = extract_bearer_token()
            user_info = verify_token(tok) if tok else None
            g.user = user_info or {"id": "local_dev_user", "email": "developer@local", "role": "authenticated"}
            return fn(*args, **kwargs)

        token = extract_bearer_token()
        if not token:
            return jsonify(
                {
                    "status": "error",
                    "message": "Authentication required. Missing Bearer access token in Authorization header.",
                    "code": "UNAUTHORIZED",
                }
            ), 401

        user = verify_token(token)
        if not user:
            return jsonify(
                {
                    "status": "error",
                    "message": "Invalid or expired Supabase authentication session. Please sign in again.",
                    "code": "INVALID_TOKEN",
                }
            ), 401

        g.user = user
        return fn(*args, **kwargs)

    return wrapper
