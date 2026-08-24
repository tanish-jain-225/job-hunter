"""Send the digest over SMTP. Gmail: use an App Password, not your login."""
from __future__ import annotations

import os
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
    to_addr = (to_email or os.getenv("MAIL_TO") or user).strip()

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr
    msg.set_content("This digest is HTML. Open it in an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(host, port, timeout=30) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
        print(f"  mailed -> {to_addr}")
    except smtplib.SMTPAuthenticationError as e:
        print(f"::error::SMTP authentication failed: {e}. If using Gmail, make sure SMTP_PASS is a 16-character App Password (myaccount.google.com/apppasswords), not your login password.")
        raise
    except Exception as e:
        print(f"::error::SMTP sending failed ({type(e).__name__}): {e}")
        raise
