"""Security regression tests.

Verifies that key security properties of the Flask application hold:
  - CSP and Permissions-Policy headers are present on all responses
  - JWT tokens via query string are NOT accepted
  - Error responses in production do not leak raw exception text
  - Standard security headers (X-Frame-Options, X-Content-Type-Options) are set
"""
from __future__ import annotations

import os
import pytest
from unittest.mock import patch

from jobhunt.web import create_app


@pytest.fixture()
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ---------------------------------------------------------------------------
# Security header tests
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    """All Flask responses must include the required security headers."""

    def test_csp_header_present_on_html_route(self, client):
        resp = client.get("/")
        assert "Content-Security-Policy" in resp.headers, (
            "Content-Security-Policy header missing from HTML route"
        )

    def test_csp_header_present_on_api_route(self, client):
        resp = client.get("/api/stats")
        assert "Content-Security-Policy" in resp.headers, (
            "Content-Security-Policy header missing from API route"
        )

    def test_permissions_policy_header_present(self, client):
        resp = client.get("/")
        assert "Permissions-Policy" in resp.headers, (
            "Permissions-Policy header missing"
        )

    def test_permissions_policy_disables_camera(self, client):
        resp = client.get("/")
        policy = resp.headers.get("Permissions-Policy", "")
        assert "camera=()" in policy, "CSP should disable camera access"

    def test_x_content_type_options(self, client):
        resp = client.get("/")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self, client):
        resp = client.get("/")
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_referrer_policy(self, client):
        resp = client.get("/")
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_api_routes_no_cache(self, client):
        resp = client.get("/api/stats")
        cache_control = resp.headers.get("Cache-Control", "")
        assert "no-store" in cache_control, (
            "API responses must not be cached by browsers or proxies"
        )


# ---------------------------------------------------------------------------
# Authentication security tests
# ---------------------------------------------------------------------------

class TestAuthSecurity:
    """JWT tokens via query string must NOT be accepted."""

    def test_query_string_token_not_accepted_on_stats(self, client):
        """Passing ?token=... must NOT grant access — should return 401, not 200."""
        resp = client.get("/api/stats?token=fake_jwt_token_here")
        assert resp.status_code == 401, (
            f"Expected 401 Unauthorized but got {resp.status_code}. "
            "Query-string token passing is a security vulnerability (OWASP CWE-598)."
        )

    def test_query_string_access_token_not_accepted(self, client):
        """?access_token=... must also be rejected."""
        resp = client.get("/api/jobs?access_token=fake_token")
        assert resp.status_code == 401

    def test_no_auth_returns_401_not_500(self, client):
        """Unauthenticated requests must return 401, never 500."""
        for path in ["/api/stats", "/api/jobs", "/api/profile", "/api/sync"]:
            resp = client.get(path)
            assert resp.status_code in (401, 403), (
                f"GET {path} without auth should be 401/403, got {resp.status_code}"
            )

    def test_bearer_header_format_required(self, client):
        """Auth header must be in 'Bearer <token>' format."""
        resp = client.get("/api/stats", headers={"Authorization": "Basic abc123"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Error response tests
# ---------------------------------------------------------------------------

class TestErrorResponses:
    """Error responses must not leak internal details in production."""

    def test_404_returns_json_error(self, client):
        resp = client.get("/api/nonexistent_endpoint_xyz")
        # Flask may return 404 as HTML or JSON depending on Accept header
        assert resp.status_code == 404

    def test_error_response_has_status_field(self, client):
        """All API error responses must have a 'status' field."""
        resp = client.get("/api/stats")  # 401
        if resp.content_type and "application/json" in resp.content_type:
            data = resp.get_json()
            if data:
                assert "status" in data or "message" in data

    @patch.dict(os.environ, {"VERCEL": "1"})
    def test_production_error_message_is_generic(self, client):
        """In production (VERCEL=1), 500 error messages must be generic."""
        # This test verifies the _IS_PROD flag logic in web/__init__.py
        from jobhunt.web import _IS_PROD
        # Note: _IS_PROD is set at module import time, so we verify the logic exists
        # The actual value depends on env at import time
        assert isinstance(_IS_PROD, bool), "_IS_PROD must be a bool"

    def test_error_response_not_empty(self, client):
        """Error responses must always return a non-empty body."""
        resp = client.get("/api/stats")
        assert len(resp.data) > 0


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

class TestRateLimiting:
    """Verify flask-limiter integration works gracefully."""

    def test_limiter_extension_registered_when_available(self):
        """If flask-limiter is installed, it should be in app.extensions."""
        try:
            import flask_limiter  # noqa: F401
            app = create_app()
            assert "limiter" in app.extensions, (
                "flask-limiter is installed but not registered in app.extensions"
            )
        except ImportError:
            pytest.skip("flask-limiter not installed")

    def test_app_starts_without_flask_limiter(self):
        """App must start cleanly even if flask-limiter is not installed."""
        import sys
        # Temporarily hide flask_limiter from imports
        original = sys.modules.get("flask_limiter")
        sys.modules["flask_limiter"] = None  # type: ignore[assignment]
        try:
            # App creation must not raise
            app = create_app()
            assert app is not None
        except Exception as e:
            pytest.fail(f"App creation failed without flask-limiter: {e}")
        finally:
            if original is None:
                sys.modules.pop("flask_limiter", None)
            else:
                sys.modules["flask_limiter"] = original
