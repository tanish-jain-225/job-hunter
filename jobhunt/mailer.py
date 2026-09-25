"""Send the digest over SMTP. Gmail: use an App Password, not your login."""

from __future__ import annotations

import email.utils
import os
import re
import smtplib
from email.message import EmailMessage


def send(subject: str, html_body: str, to_email: str | None = None) -> None:
    from .auth import _load_env_if_needed

    _load_env_if_needed()
    host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    raw_port = (os.getenv("SMTP_PORT") or "587").strip()
    port = int(raw_port) if raw_port.isdigit() else 587
    user = os.environ["SMTP_USER"].strip()
    password = os.environ["SMTP_PASS"].strip()
    if not user or not password:
        raise ValueError("SMTP_USER and SMTP_PASS environment variables must not be empty.")
    to_addr = (to_email or os.getenv("MAIL_TO") or user).strip()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=user.split("@")[-1] if "@" in user else None)
    msg["Auto-Submitted"] = "auto-generated"
    msg["Precedence"] = "bulk"
    msg["X-Auto-Response-Suppress"] = "All"
    msg["List-Unsubscribe"] = f"<mailto:{user}?subject=Unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    # Provide clean plain-text fallback to maximize inbox deliverability and lower spam scoring
    plain_text = re.sub(r"<[^>]+>", " ", html_body)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()
    if not plain_text:
        plain_text = "Job Hunter Executive Digest. Please open in an HTML-capable email client."
    else:
        plain_text = plain_text[:2000]

    msg.set_content(plain_text)
    msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
        print(f"  mailed -> {to_addr}")
    except smtplib.SMTPAuthenticationError as e:
        print(
            f"::error::SMTP authentication failed: {e}. If using Gmail, make sure SMTP_PASS is a 16-character App Password (myaccount.google.com/apppasswords), not your login password."
        )
        raise
    except Exception as e:
        print(f"::error::SMTP sending failed ({type(e).__name__}): {e}")
        raise
