"""Security regression tests.

Verifies that key security properties of the Flask application hold:
  - CSP and Permissions-Policy headers are present on all responses
  - JWT tokens via query string are NOT accepted
  - Error responses in production do not leak raw exception text
  - Standard security headers (X-Frame-Options, X-Content-Type-Options) are set
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

from jobhunt.web import create_app, handle_exception
from jobhunt.web.state import sanitize_profile_for_response


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://mock.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "mock_anon_key")
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
        assert "Content-Security-Policy" in resp.headers, "Content-Security-Policy header missing from HTML route"

    def test_csp_header_present_on_api_route(self, client):
        resp = client.get("/api/stats")
        assert "Content-Security-Policy" in resp.headers, "Content-Security-Policy header missing from API route"

    def test_permissions_policy_header_present(self, client):
        resp = client.get("/")
        assert "Permissions-Policy" in resp.headers, "Permissions-Policy header missing"

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
        assert "no-store" in cache_control, "API responses must not be cached by browsers or proxies"

    def test_profile_response_sanitizer_removes_nested_credentials(self):
        profile = {
            "name": "Candidate",
            "GEMINI_API_KEY": "do-not-return",
            "profile_json": {"nested_token": "do-not-return", "latest_digest_html": "<p>ok</p>"},
        }
        safe = sanitize_profile_for_response(profile)
        assert safe == {"name": "Candidate", "profile_json": {"latest_digest_html": "<p>ok</p>"}}

    def test_csp_script_src_disallows_unsafe_inline(self, client):
        resp = client.get("/")
        csp = resp.headers.get("Content-Security-Policy", "")
        parts = {p.strip().split()[0]: p.strip() for p in csp.split(";") if p.strip()}
        script_src = parts.get("script-src", "")
        assert "'unsafe-inline'" not in script_src, "script-src in CSP must not permit 'unsafe-inline'"

    def test_no_inline_event_handlers_in_templates(self):
        import re
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / "templates"
        pattern = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
        offenders = []
        for html_file in root.rglob("*.html"):
            content = html_file.read_text(encoding="utf-8")
            matches = pattern.findall(content)
            if matches:
                offenders.append(f"{html_file.name}: {matches}")
        assert not offenders, f"Inline event handlers found in templates: {offenders}"


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
            assert resp.status_code in (401, 403), f"GET {path} without auth should be 401/403, got {resp.status_code}"

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
        assert resp.status_code == 404
        data = resp.get_json()
        assert data is not None
        assert data["status"] == "error"
        assert "not found" in data["message"].lower()

    def test_405_method_not_allowed_returns_json(self, client):
        resp = client.post("/api/digest")  # /api/digest is GET only
        assert resp.status_code == 405
        data = resp.get_json()
        assert data is not None
        assert data["status"] == "error"

    def test_error_response_has_status_field(self, client):
        """All API error responses must have a 'status' field."""
        resp = client.get("/api/stats")  # 401
        if resp.content_type and "application/json" in resp.content_type:
            data = resp.get_json()
            if data:
                assert "status" in data or "message" in data

    @patch.dict(os.environ, {"VERCEL": "1"})
    def test_production_error_message_is_generic(self, client):
        """In production (VERCEL=1), 500 error messages must be generic, not exposing internals."""
        with client.application.test_request_context():
            secret_leak = "FATAL: Postgres password=my_super_secret_pw! connection refused"
            resp, status_code = handle_exception(RuntimeError(secret_leak))
            assert status_code == 500
            data = resp.get_json()
            assert data["status"] == "error"
            assert data["message"] == "An internal error occurred. Please try again later."
            assert "my_super_secret_pw" not in data["message"]

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
        pytest.importorskip("flask_limiter")
        app = create_app()
        assert "limiter" in app.extensions, "flask-limiter is installed but not registered in app.extensions"

    def test_app_starts_without_flask_limiter(self):
        """App must start cleanly even if flask-limiter is not installed."""
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

    def test_enforce_rate_limit_invokes_limiter_when_not_testing(self):
        """enforce_rate_limit delegates to app limiter when TESTING is False."""
        from unittest.mock import MagicMock

        from jobhunt.web.state import enforce_rate_limit

        app = create_app()
        fake_decorator = MagicMock(return_value=lambda fn: fn)
        fake_limiter = MagicMock()
        fake_limiter.limit.return_value = fake_decorator
        app.extensions["limiter"] = fake_limiter
        app.testing = False
        with app.test_request_context("/api/run", method="POST"):
            enforce_rate_limit("5 per minute")
        fake_limiter.limit.assert_called_once_with("5 per minute")
        fake_decorator.assert_called_once()


class TestSSRFSafeUrlAndSlug:
    """Verify hardened SSRF protection, ATS URL host matching, slug checks, and security/ARIA headers."""

    @pytest.mark.parametrize(
        "unsafe_url",
        [
            "http://[::ffff:127.0.0.1]/admin",
            "https://user:pass@boards.greenhouse.io/stripe",
            "http://metadata.google.internal/computeMetadata/v1/",
            "https://10.0.0.1.arpa/foo",
        ],
    )
    def test_is_safe_url_blocks_advanced_ssrf_vectors(self, unsafe_url: str):
        from jobhunt.parsers import is_safe_url

        assert is_safe_url(unsafe_url) is False

    def test_detect_ats_from_url_rejects_lookalike_hosts_and_credentials(self):
        from jobhunt.parsers import detect_ats_from_url

        assert detect_ats_from_url("https://evil-greenhouse.io/acme") is None
        assert detect_ats_from_url("https://greenhouse.io.attacker.example/acme") is None
        assert detect_ats_from_url("https://user:pass@boards.greenhouse.io/acme") is None
        assert detect_ats_from_url("https://boards.greenhouse.io/..") is None
        assert detect_ats_from_url("https://boards.greenhouse.io/stripe") == {
            "ats": "greenhouse",
            "slug": "stripe",
            "name": "Stripe",
        }

    def test_slug_validation_blocks_traversal_across_fetch_verify_and_api(self):
        from unittest.mock import MagicMock, patch

        from jobhunt.fetch import fetch_board
        from jobhunt.parsers import is_valid_slug
        from jobhunt.verify import check_single_board

        assert is_valid_slug("stripe") is True
        assert is_valid_slug("open_ai-1.0") is True
        for bad_slug in ("", "   ", "../etc", "foo/bar", "a" * 101):
            assert is_valid_slug(bad_slug) is False

        assert fetch_board("greenhouse", "../etc") == []

        mock_sess = MagicMock()
        _, ok, status = check_single_board({"ats": "greenhouse", "slug": "../etc"}, session=mock_sess)
        assert ok is False
        assert status == "Invalid company slug"
        mock_sess.get.assert_not_called()

        app = create_app()
        client = app.test_client()
        with patch("jobhunt.auth.verify_token", return_value={"email": "user@test.com"}):
            res = client.post(
                "/api/companies/add",
                json={"ats": "greenhouse", "slug": "../etc", "name": "Evil"},
                headers={"Authorization": "Bearer tok"},
            )
            assert res.status_code == 400
            assert "Invalid company slug" in res.get_json()["message"]

    def test_coop_hsts_headers_and_modal_aria_semantics(self):
        app = create_app()
        client = app.test_client()

        resp_http = client.get("/")
        assert resp_http.headers.get("Cross-Origin-Opener-Policy") == "same-origin-allow-popups"
        assert "Strict-Transport-Security" not in resp_http.headers

        html = resp_http.get_data(as_text=True)
        for modal_id in ("profile-modal", "add-company-modal", "add-job-modal", "kit-modal"):
            assert f'id="{modal_id}"' in html
        assert html.count('role="dialog"') >= 4
        assert html.count('aria-modal="true"') >= 4
        assert 'id="toast-container"' in html and 'aria-live="polite"' in html
        assert 'id="resume-dropzone"' in html and 'tabindex="0"' in html

        resp_https = client.get("/", base_url="https://example.com")
        assert resp_https.headers.get("Strict-Transport-Security") == "max-age=31536000; includeSubDomains"
