"""Unit tests for jobhunt.digest HTML generation and jobhunt.mailer SMTP message handling."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from jobhunt import digest, mailer
from jobhunt.fetch import Job


def test_badge_color_levels():
    assert "#3fb950" in digest._badge(9.0)
    assert "#d29922" in digest._badge(7.5)
    assert "#8b949e" in digest._badge(5.0)


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
        }
    )

    subject, html_doc = digest.build([xss_job], scanned=10, candidates=5, stats={"tracked": 1, "applied": 0})
    assert "<script>" not in html_doc
    assert "&lt;script&gt;" in html_doc
    assert "1 job worth your time" in subject


def test_digest_build_empty_list():
    subject, html_doc = digest.build([], scanned=50, candidates=0, stats={"tracked": 5, "applied": 1})
    assert "No new matches today" in subject
    assert "nothing cleared the bar today" in html_doc


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
