"""Unit tests for jobhunt.digest HTML generation and jobhunt.mailer SMTP message handling."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from jobhunt import digest, mailer
from jobhunt.fetch import Job


def test_badge_color_levels():
    j1 = Job("1", "gh", "Acme", "Dev", "Remote", "http://x", "desc", score=9.2)
    j2 = Job("2", "gh", "Acme", "Dev", "Remote", "http://x", "desc", score=7.5)
    j3 = Job("3", "gh", "Acme", "Dev", "Remote", "http://x", "desc", score=5.0)
    assert "#15803d" in digest._badge(j1)
    assert "#b45309" in digest._badge(j2)
    assert "#475569" in digest._badge(j3)


def test_digest_helpers_empty_branches():
    assert digest._bullets([]) == ""
    assert digest._section("Label", "") == ""
    assert digest._para("") == ""


def test_digest_build_escapes_xss():
    xss_job = Job(
        job_id="greenhouse:acme:1",
        ats="greenhouse",
        company="<script>alert('company')</script>",
        title="Backend Engineer <img src=x onerror=alert(1)>",
        location="Bangalore & Remote",
        url="https://example.com/job?a=1&b=2",
        description="description",
        score=9.2,
        reason="Good fit <script>",
        draft={
            "fit_summary": "Clean summary",
            "tailored_bullets": ["Bullet 1 <xss>"],
            "gaps": ["Gap 1"],
            "cover_note": "Cover note text",
            "questions_to_ask": ["Question 1?"],
        },
    )

    subject, html_doc = digest.build([xss_job], scanned=10, candidates=5, stats={"tracked": 1, "applied": 0})
    assert "<script>" not in html_doc
    assert "&lt;script&gt;" in html_doc
    assert "Remote Role" in subject


def test_digest_card_with_none_draft():
    job = Job("1", "gh", "Acme", "Dev", "Remote", "http://x", "desc")
    job.draft = None  # type: ignore[assignment]
    subject, html_doc = digest.build([job], 1, 1, {})
    assert "Dev" in html_doc


def test_digest_build_empty_list():
    subject, html_doc = digest.build([], scanned=50, candidates=0, stats={"tracked": 5, "applied": 1})
    assert "No new remote matches today" in subject
    assert "0 candidates cleared" in html_doc


def test_mailer_send(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "app_password_secret")
    monkeypatch.setenv("MAIL_TO", "recipient@example.com")

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_inst = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp_inst

        mailer.send("Test Digest Subject", "<p>Digest body</p>")

        mock_smtp_inst.starttls.assert_called_once()
        mock_smtp_inst.login.assert_called_once_with("user@example.com", "app_password_secret")
        mock_smtp_inst.send_message.assert_called_once()
        sent_msg = mock_smtp_inst.send_message.call_args[0][0]
        assert sent_msg["Subject"] == "Test Digest Subject"
        assert sent_msg["To"] == "recipient@example.com"


def test_mailer_missing_smtp_user(monkeypatch: pytest.MonkeyPatch):
    """SMTP_USER is accessed via os.environ[] — missing key raises KeyError."""
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.setenv("SMTP_PASS", "password")
    with pytest.raises(KeyError):
        mailer.send("Subject", "<p>body</p>")


def test_mailer_smtp_auth_failure(monkeypatch: pytest.MonkeyPatch):
    """SMTPAuthenticationError is re-raised after printing a diagnostic."""
    import smtplib

    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "wrong_password")

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_inst = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_smtp_inst
        mock_smtp_inst.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")

        with pytest.raises(smtplib.SMTPAuthenticationError):
            mailer.send("Subject", "<p>body</p>")


def test_mailer_generic_exception(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SMTP_USER", "user@example.com")
    monkeypatch.setenv("SMTP_PASS", "password")

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = RuntimeError("SMTP server down")
        with pytest.raises(RuntimeError, match="SMTP server down"):
            mailer.send("Subject", "<p>body</p>")


def test_digest_card_with_outreach_and_cover():
    job = Job(
        job_id="ashby:openai:1",
        ats="ashby",
        company="OpenAI",
        title="AI Engineer",
        location="Remote",
        url="https://jobs.ashbyhq.com/openai/1",
        description="Build LLM applications",
        score=8.5,
        reason="Direct stack fit",
        draft={
            "fit_summary": "Strong fit for Python and LLMs.",
            "india_eligibility": "Verified India-Friendly",
            "best_project": "Edvanta AI",
            "tailored_bullets": ["Engineered Flask backend."],
            "matching_skills": ["Python", "Flask", "Gemini API"],
            "gaps": ["None"],
            "cover_note": "Dear OpenAI team,\nI am writing to apply...",
            "cold_outreach": "Hi! I built Edvanta...",
            "questions_to_ask": ["What is the primary LLM infrastructure?"],
        },
    )
    card_html = digest._card(job)
    assert "Why It Fits" in card_html
    assert "Verified India-Friendly" in card_html
    assert "OpenAI" in card_html


def test_digest_write(tmp_path: Path):
    target = tmp_path / "out" / "custom_digest.html"
    res = digest.write("<html><body>Digest</body></html>", target)
    assert res.exists()
    assert "Digest" in res.read_text(encoding="utf-8")


def test_digest_build_with_custom_profile():
    job = Job("1", "gh", "Acme", "Dev", "Remote", "http://x", "desc", score=8.5)
    custom_profile = {"name": "Jane Doe", "education": "M.S. Computer Science, Stanford 2025"}
    subject, html_doc = digest.build([job], 10, 5, {"tracked": 10}, profile=custom_profile)
    assert "Matched for Jane Doe" in subject
    assert "Jane Doe" in html_doc
    assert "Stanford 2025" in html_doc


def test_digest_responsive_structure():
    job = Job(
        "greenhouse:stripe:1",
        "greenhouse",
        "Stripe",
        "Senior Backend Engineer",
        "Remote",
        "https://stripe.com/job/1",
        "desc",
        score=9.5,
        draft={
            "fit_summary": "Top match",
            "india_eligibility": "Verified India-Friendly",
            "best_project": "Payments Engine",
            "tailored_bullets": ["Built real-time payout pipeline."],
            "cold_outreach": "Hey team, check out my payment engine repo.",
            "cover_note": "I'd love to join Stripe.",
        },
    )
    subject, html_doc = digest.build([job], 20, 5, {"tracked": 20})
    assert "viewport" in html_doc
    assert "@media" in html_doc
    assert "box-sizing:border-box" in html_doc
    assert "overflow-wrap:anywhere" in html_doc or "word-break:break-word" in html_doc
    assert "digest-card" in html_doc
    # Ensure body does not have display:flex (which Gmail breaks into horizontal row)
    assert '<body style="margin:0;padding:16px 8px;background:' in html_doc
    assert "display:flex" not in html_doc.split("<body")[1].split('<div class="digest-wrap"')[0]
