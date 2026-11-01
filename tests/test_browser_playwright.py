"""End-to-End Headless Playwright Browser Tests for Job Hunter Web Dashboard."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import threading
from typing import Generator
import pytest
from werkzeug.serving import make_server

try:
    from playwright.sync_api import sync_playwright, Page, Error as PlaywrightError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    PlaywrightError = Exception  # type: ignore


def is_chromium_available() -> bool:
    """Check if Playwright is installed and the Chromium binary is present on disk without launching subprocess."""
    if not PLAYWRIGHT_AVAILABLE:
        return False
    try:
        import sys
        candidates: list[Path] = []
        if sys.platform == "win32":
            local_app = os.environ.get("LOCALAPPDATA", "")
            if local_app:
                candidates.append(Path(local_app) / "ms-playwright")
        elif sys.platform == "darwin":
            candidates.append(Path.home() / "Library" / "Caches" / "ms-playwright")
        else:
            candidates.append(Path.home() / ".cache" / "ms-playwright")

        custom = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        if custom and custom != "0":
            candidates.insert(0, Path(custom))

        for base in candidates:
            if base.is_dir():
                for exe in ("chrome.exe", "chrome", "chrome-headless-shell", "chrome-headless-shell.exe"):
                    if any(base.glob(f"**/{exe}")):
                        return True
        return False
    except Exception:
        return False


CHROMIUM_AVAILABLE = is_chromium_available()

pytestmark = [
    pytest.mark.skipif(
        not CHROMIUM_AVAILABLE,
        reason="playwright and chromium browser binary are required; run 'playwright install chromium'",
    ),
    pytest.mark.playwright,
]


def find_free_port() -> int:
    """Find a guaranteed free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server():
    """Spin up a live Flask test server in a background thread."""
    from jobhunt.web import create_app
    from jobhunt.clean import clean_workspace

    original_profile = Path("profile.json").read_text(encoding="utf-8") if Path("profile.json").is_file() else None
    clean_workspace(dry_run=False)

    os.environ["AUTH_REQUIRED"] = "false"
    os.environ["SUPABASE_URL"] = ""
    os.environ["SUPABASE_ANON_KEY"] = ""

    app = create_app()
    app.config["TESTING"] = True
    port = find_free_port()
    server = make_server("127.0.0.1", port, app)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{port}"

    yield base_url

    server.shutdown()
    thread.join(timeout=2.0)
    clean_workspace(dry_run=False)
    if original_profile is not None:
        Path("profile.json").write_text(original_profile, encoding="utf-8")


@pytest.fixture
def browser_page(live_server) -> Generator[tuple[Page, list[str], list[str]], None, None]:
    """Launch headless Chromium with external resource stubs and error collectors."""
    console_errors: list[str] = []
    page_errors: list[str] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()

            # Abort external resources to prevent network hangs in sandboxed or offline test runs
            page.route(
                "**/*",
                lambda route: route.abort()
                if any(h in route.request.url for h in ["fonts.googleapis.com", "fonts.gstatic.com", "jsdelivr.net"])
                else route.continue_()
            )

            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            yield page, console_errors, page_errors

            browser.close()
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip(f"Chromium binary not found: {exc}")
        raise


def test_landing_page_unauthenticated_render(live_server):
    """Verify landing page loads cleanly without JS errors when unauthenticated."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
            page = browser.new_page()
            page_errors = []
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            page.route(
                "**/*",
                lambda route: route.abort()
                if any(h in route.request.url for h in ["fonts.googleapis.com", "fonts.gstatic.com", "jsdelivr.net"])
                else route.continue_()
            )

            # Force unauthenticated landing view via auth config route mock
            def mock_auth_cfg(route):
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"status": "success", "auth_required": True, "supabase_url": "https://test.supabase.co", "supabase_anon_key": "test_anon_key"})
                )

            page.route("**/api/auth/config", mock_auth_cfg)
            page.goto(f"{live_server}/", wait_until="domcontentloaded")
            page.wait_for_timeout(600)

            # Landing view should be visible
            assert page.is_visible("#landing-view")
            assert page.is_visible("#landing-nav-links")
            assert not page.is_visible("#dashboard-view")

            # Verify hero elements
            title_text = page.inner_text(".landing-hero-title")
            assert "Stop sifting through job spam" in title_text

            # Verify auth tab switching
            page.click("#tab-signup")
            page.wait_for_timeout(200)
            assert page.is_visible("#form-signup")
            assert not page.is_visible("#form-signin")

            page.click("#tab-signin")
            page.wait_for_timeout(200)
            assert page.is_visible("#form-signin")

            assert len(page_errors) == 0, f"Page errors: {page_errors}"
            browser.close()
    except Exception as exc:
        if "Executable doesn't exist" in str(exc):
            pytest.skip(f"Chromium binary not found: {exc}")
        raise


def test_dashboard_flow_profile_wizard_and_save(browser_page, live_server):
    """Test opening profile modal, step transitions, autofill, and saving preferences."""
    page, console_errors, page_errors = browser_page

    # Mock resume upload to return deterministic parsed profile without LLM dependency
    def handle_resume_upload(route):
        mock_profile = {
            "name": "Jordan Lee",
            "title": "Lead Software Engineer",
            "experience_years": 7,
            "skills": ["Python", "Kubernetes", "FastAPI", "PostgreSQL", "Kafka"],
            "target_keywords": ["Lead Software Engineer", "Staff Backend Architect"],
            "exclude_keywords": ["Manager", "Recruiter", "Intern"],
            "location_preference": {"type": "specific_cities", "locations": ["Bengaluru", "Remote"]},
            "notice_period": "30_days",
            "current_ctc_lpa": 32.0,
            "expected_ctc_lpa": 48.0,
        }
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"status": "success", "profile": mock_profile})
        )

    page.route("**/api/resume/upload", handle_resume_upload)

    page.goto(f"{live_server}/", wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    assert page.is_visible("#dashboard-view"), "Dashboard should be visible in local dev mode"

    # 1. Open Profile & Search Settings Modal
    btn_settings = page.wait_for_selector("#btn-sidebar-settings")
    assert btn_settings is not None
    btn_settings.click()
    page.wait_for_timeout(300)

    assert page.is_visible("#profile-modal")
    assert page.is_visible("#profile-step-1")

    # 2. Add text context in Step 1
    page.fill("#prof-resume-text", "Jordan Lee. 7 years experience in Python, Kubernetes, FastAPI, PostgreSQL.")

    # 3. Transition to Step 2
    page.click("#profile-next-1")
    page.wait_for_timeout(300)
    assert page.is_visible("#profile-step-2")

    # 4. Clear and click Auto-Fill
    page.fill("#prof-name", "")
    page.click("#btn-autofill-roles")
    page.wait_for_timeout(400)

    assert page.input_value("#prof-name") == "Jordan Lee"
    assert "Lead Software Engineer" in page.input_value("#prof-title")
    assert "Kubernetes" in page.input_value("#prof-skills")
    # Verify save button is NOT present in Step 2
    assert not page.is_visible("#btn-profile-save")

    # 5. Transition to Step 3
    page.click("#profile-next-2")
    page.wait_for_timeout(300)
    assert page.is_visible("#profile-step-3")
    # Verify save button IS present at the end in Step 3
    assert page.is_visible("#btn-profile-save")

    # 6. Save Profile
    page.click("#btn-profile-save")
    page.wait_for_timeout(800)

    # 7. Verify modal closes
    if page.is_visible("#profile-modal"):
        page.click(".modal-close[data-action='close-profile-modal']")
        page.wait_for_timeout(300)
    assert not page.is_visible("#profile-modal")

    # 8. Verify candidate summary card on dashboard reflects saved profile
    summary_name = page.inner_text("#summary-candidate-name")
    assert "Jordan Lee" in summary_name

    assert len(page_errors) == 0, f"Page errors: {page_errors}"


def test_tracker_search_filter_and_chips(browser_page, live_server):
    """Test switching tabs, filtering via search input, clearing, and clicking chips."""
    page, console_errors, page_errors = browser_page

    page.goto(f"{live_server}/", wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    # 1. Switch to Tracker Tab
    page.click("#tab-btn-tracker")
    page.wait_for_timeout(400)
    assert page.is_visible("#tab-content-tracker")

    # 2. Type into Search Bar
    search_input = page.wait_for_selector("#tracker-search-input")
    assert search_input is not None
    search_input.fill("Senior")
    page.wait_for_timeout(300)

    # Clear button should be visible
    btn_clear = page.wait_for_selector("#search-clear-btn")
    assert btn_clear is not None and btn_clear.is_visible()

    # 3. Clear Search
    btn_clear.click()
    page.wait_for_timeout(200)
    assert search_input.input_value() == ""

    # 4. Test Keyboard shortcut '/'
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)
    page.keyboard.press("/")
    page.wait_for_timeout(100)
    is_focused = page.evaluate("document.activeElement.id === 'tracker-search-input'")
    assert is_focused, "Search input should receive focus on '/' keypress"

    # 5. Click a skill chip from Candidate Profile summary (if present)
    chip = page.query_selector(".clickable-skill-chip")
    if chip:
        tag_text = chip.inner_text()
        chip.click()
        page.wait_for_timeout(300)
        assert page.is_visible("#tab-content-tracker")
        assert search_input.input_value() == tag_text

    assert len(page_errors) == 0, f"Page errors: {page_errors}"


def test_modal_overlay_escape_behavior(browser_page, live_server):
    """Verify modals close cleanly on 'Escape' and do not leave blocking backdrops."""
    page, console_errors, page_errors = browser_page

    page.goto(f"{live_server}/", wait_until="domcontentloaded")
    page.wait_for_timeout(800)

    # Open Settings modal
    page.click("#btn-sidebar-settings")
    page.wait_for_timeout(300)
    assert page.is_visible("#profile-modal")

    # Press Escape to dismiss
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert not page.is_visible("#profile-modal")

    # Verify no persistent backdrop locks pointer events
    overlay = page.query_selector("#profile-modal")
    assert overlay is not None
    has_active = page.evaluate("document.getElementById('profile-modal').classList.contains('active')")
    assert not has_active

    assert len(page_errors) == 0, f"Page errors: {page_errors}"
