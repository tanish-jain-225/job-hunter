"""Unit and integration tests for Supabase Authentication and protected API routes."""

import os
import time
from unittest import mock

import pytest
import jwt
from flask import Flask, g, jsonify

from jobhunt import auth
from jobhunt.auth import (
    clear_token_cache,
    extract_bearer_token,
    get_supabase_config,
    is_auth_required,
    require_auth,
    verify_token,
)
from app import app


@pytest.fixture(autouse=True)
def reset_env_and_cache():
    """Clear memory token cache and reset auth env vars before each test."""
    clear_token_cache()
    old_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(old_env)
    clear_token_cache()


def test_get_supabase_config_defaults():
    with mock.patch("jobhunt.auth._load_env_if_needed"):
        os.environ.pop("SUPABASE_URL", None)
        os.environ.pop("SUPABASE_ANON_KEY", None)
        os.environ.pop("SUPABASE_JWT_SECRET", None)
        os.environ.pop("AUTH_REQUIRED", None)

        cfg = get_supabase_config()
        assert cfg["supabase_url"] == ""
        assert cfg["supabase_anon_key"] == ""
        assert cfg["auth_required"] is False
        assert is_auth_required() is False


def test_load_env_failure_is_safe(monkeypatch):
    monkeypatch.setattr(auth, "_ENV_LOADED", False)
    monkeypatch.setattr("jobhunt.cli._load_env", mock.Mock(side_effect=RuntimeError("environment unavailable")))

    auth._load_env_if_needed()

    assert auth._ENV_LOADED is False


def test_get_supabase_config_configured():
    os.environ["SUPABASE_URL"] = "https://example.supabase.co/"
    os.environ["SUPABASE_ANON_KEY"] = "anon-key-123"
    os.environ["SUPABASE_JWT_SECRET"] = "secret-jwt-456"

    cfg = get_supabase_config()
    assert cfg["supabase_url"] == "https://example.supabase.co"
    assert cfg["supabase_anon_key"] == "anon-key-123"
    assert cfg["supabase_jwt_secret"] == "secret-jwt-456"
    assert cfg["auth_required"] is True
    assert is_auth_required() is True


def test_get_supabase_config_explicit_bypass():
    os.environ["SUPABASE_URL"] = "https://example.supabase.co"
    os.environ["SUPABASE_ANON_KEY"] = "anon-key-123"
    os.environ["AUTH_REQUIRED"] = "false"

    cfg = get_supabase_config()
    assert cfg["auth_required"] is False
    assert is_auth_required() is False


def test_extract_bearer_token():
    test_app = Flask(__name__)

    with test_app.test_request_context(headers={"Authorization": "Bearer sample-token-abc"}):
        assert extract_bearer_token() == "sample-token-abc"

    # Query string tokens are rejected for security (CWE-598)
    with test_app.test_request_context(query_string={"token": "query-token-xyz"}):
        assert extract_bearer_token() is None

    with test_app.test_request_context(query_string={"access_token": "access-token-123"}):
        assert extract_bearer_token() is None

    with test_app.test_request_context(headers={"Cookie": "sb_access_token=cookie-token-456"}):
        assert extract_bearer_token() == "cookie-token-456"

    with test_app.test_request_context():
        assert extract_bearer_token() is None


def test_verify_token_with_jwt_secret():
    secret = "my-test-secret-key-32-chars-long!"
    os.environ["SUPABASE_JWT_SECRET"] = secret
    os.environ["AUTH_REQUIRED"] = "true"

    payload = {
        "sub": "user_12345",
        "email": "candidate@example.com",
        "role": "authenticated",
        "exp": time.time() + 3600,
        "user_metadata": {"full_name": "Job Hunter Candidate"},
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    user_info = verify_token(token)
    assert user_info is not None
    assert user_info["id"] == "user_12345"
    assert user_info["email"] == "candidate@example.com"
    assert user_info["user_metadata"]["full_name"] == "Job Hunter Candidate"

    # Verify cached retrieval
    user_info_cached = verify_token(token)
    assert user_info_cached == user_info


def test_verify_token_expired_jwt():
    secret = "my-test-secret-key-32-chars-long!"
    os.environ["SUPABASE_JWT_SECRET"] = secret
    os.environ["AUTH_REQUIRED"] = "true"

    payload = {
        "sub": "user_12345",
        "email": "candidate@example.com",
        "exp": time.time() - 3600,  # Expired
    }
    token = jwt.encode(payload, secret, algorithm="HS256")

    user_info = verify_token(token)
    assert user_info is None


def test_verify_token_supabase_api_success():
    os.environ["SUPABASE_URL"] = "https://mock.supabase.co"
    os.environ["SUPABASE_ANON_KEY"] = "mock-anon-key"
    os.environ["AUTH_REQUIRED"] = "true"
    os.environ.pop("SUPABASE_JWT_SECRET", None)

    mock_resp = mock.Mock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "sb_user_789",
        "email": "user@supabase.test",
        "role": "authenticated",
        "user_metadata": {"role": "Engineer"},
    }

    with mock.patch("requests.get", return_value=mock_resp) as mock_get:
        user_info = verify_token("mock-supabase-access-token")
        assert user_info is not None
        assert user_info["id"] == "sb_user_789"
        assert user_info["email"] == "user@supabase.test"
        mock_get.assert_called_once_with(
            "https://mock.supabase.co/auth/v1/user",
            headers={
                "Authorization": "Bearer mock-supabase-access-token",
                "apikey": "mock-anon-key",
            },
            timeout=5,
        )


def test_verify_token_supabase_api_error():
    os.environ["SUPABASE_URL"] = "https://mock.supabase.co"
    os.environ["SUPABASE_ANON_KEY"] = "mock-anon-key"
    os.environ["AUTH_REQUIRED"] = "true"
    os.environ.pop("SUPABASE_JWT_SECRET", None)

    mock_resp = mock.Mock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"message": "Invalid JWT"}

    with mock.patch("requests.get", return_value=mock_resp):
        user_info = verify_token("bad-token")
        assert user_info is None


def test_require_auth_decorator():
    test_app = Flask(__name__)

    @test_app.route("/protected")
    @require_auth
    def protected():
        return jsonify({"status": "ok", "user": g.user})

    client = test_app.test_client()

    # 1. When AUTH_REQUIRED is false (local dev mode)
    os.environ["AUTH_REQUIRED"] = "false"
    res = client.get("/protected")
    assert res.status_code == 200
    assert res.json is not None
    assert res.json["status"] == "ok"
    assert res.json["user"]["id"] == "local_dev_user"

    # 2. When AUTH_REQUIRED is true and no token is provided
    os.environ["AUTH_REQUIRED"] = "true"
    os.environ["SUPABASE_URL"] = "https://mock.supabase.co"
    os.environ["SUPABASE_ANON_KEY"] = "key"
    res = client.get("/protected")
    assert res.status_code == 401
    assert res.json is not None
    assert res.json["code"] == "UNAUTHORIZED"

    # 3. When valid Bearer token is provided
    secret = "decorator-test-secret-key-32-chars"
    os.environ["SUPABASE_JWT_SECRET"] = secret
    token = jwt.encode({"sub": "admin_user", "email": "admin@career.org"}, secret, algorithm="HS256")
    res = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json is not None
    assert res.json["user"]["id"] == "admin_user"
    assert res.json["user"]["email"] == "admin@career.org"


def test_api_auth_config_route():
    client = app.test_client()
    os.environ["SUPABASE_URL"] = "https://test.supabase.co"
    os.environ["SUPABASE_ANON_KEY"] = "test-key"
    os.environ["AUTH_REQUIRED"] = "true"

    res = client.get("/api/auth/config")
    assert res.status_code == 200
    data = res.json
    assert data is not None
    assert data["status"] == "success"
    assert data["auth_required"] is True
    assert data["supabase_url"] == "https://test.supabase.co"
    assert data["supabase_anon_key"] == "test-key"


def test_api_auth_user_route():
    client = app.test_client()
    secret = "user-route-test-secret-32-chars-long"
    os.environ["SUPABASE_JWT_SECRET"] = secret
    os.environ["AUTH_REQUIRED"] = "true"

    token = jwt.encode({"sub": "user_42", "email": "dev@supabase.co"}, secret, algorithm="HS256")
    res = client.get("/api/auth/user", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json is not None
    assert res.json["status"] == "success"
    assert res.json["user"]["id"] == "user_42"
    assert res.json["user"]["email"] == "dev@supabase.co"


def test_protected_routes_deny_unauthenticated():
    client = app.test_client()
    os.environ["SUPABASE_URL"] = "https://test.supabase.co"
    os.environ["SUPABASE_ANON_KEY"] = "test-key"
    os.environ["AUTH_REQUIRED"] = "true"

    # All operational utility endpoints must reject unauthenticated requests
    endpoints = [
        ("GET", "/api/sync"),
        ("GET", "/api/stats"),
        ("GET", "/api/config"),
        ("GET", "/api/jobs"),
        ("POST", "/api/jobs/add"),
        ("POST", "/api/jobs/stage"),
        ("POST", "/api/jobs/followup"),
        ("POST", "/api/jobs/notes"),
        ("GET", "/api/digest"),
        ("GET", "/api/export/csv"),
        ("POST", "/api/run"),
        ("POST", "/api/applied"),
        ("POST", "/api/delete"),
        ("DELETE", "/api/delete"),
        ("GET", "/api/profile"),
        ("POST", "/api/profile"),
        ("POST", "/api/profile/reset"),
        ("POST", "/api/resume/upload"),
        ("GET", "/api/profile/preferences"),
        ("POST", "/api/profile/preferences"),
        ("GET", "/api/companies"),
        ("GET", "/api/companies/custom"),
        ("DELETE", "/api/companies/custom"),
        ("POST", "/api/companies/add"),
        ("GET", "/api/history"),
        ("POST", "/api/email/test"),
        ("GET", "/api/auth/user"),
    ]

    for method, path in endpoints:
        if method == "GET":
            res = client.get(path)
        elif method == "DELETE":
            res = client.delete(path, json={})
        else:
            res = client.post(path, json={})
        assert res.status_code == 401, f"Expected 401 for unauthenticated {method} {path}, got {res.status_code}"
        assert res.json is not None
        assert res.json["code"] in ("UNAUTHORIZED", "INVALID_TOKEN")


def test_public_routes_accessible_unauthenticated():
    client = app.test_client()
    os.environ["SUPABASE_URL"] = "https://test.supabase.co"
    os.environ["SUPABASE_ANON_KEY"] = "test-key"
    os.environ["AUTH_REQUIRED"] = "true"

    # Only public discovery routes are accessible without auth
    public_routes = ["/", "/api/auth/config", "/api/health", "/logo.png"]
    for path in public_routes:
        res = client.get(path)
        assert res.status_code == 200, f"Expected 200 for public route {path}, got {res.status_code}"


def test_unauthenticated_view_isolation_contract():
    client = app.test_client()
    res = client.get("/")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # 1. Unauthenticated landing view and navigation links must be present
    assert 'id="landing-view"' in html
    assert 'id="landing-nav-links"' in html

    # 2. Authenticated elements must have app-view-hidden and display:none
    assert 'id="dashboard-view"' in html
    assert 'dashboard-layout app-view-hidden' in html
    assert 'id="header-metrics"' in html
    assert 'nav-actions-cluster app-view-hidden' in html

    # 3. CSS stylesheet must contain the universal view state isolation rules
    css_res = client.get("/static/css/style.css")
    assert css_res.status_code == 200
    css_text = css_res.get_data(as_text=True)
    assert ".app-view-hidden" in css_text
    assert "display: none !important" in css_text
    assert "visibility: hidden !important" in css_text
    assert "pointer-events: none !important" in css_text

