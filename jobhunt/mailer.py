"""Send the digest over SMTP. Gmail: use an App Password, not your login."""

from __future__ import annotations

import email.utils
import os
import re
import smtplib
from email.message import EmailMessage

# Harmonic operational limits (multiples of 5 & 10)
MAX_DAILY_SEND: int = 450
SMTP_TIMEOUT: int = 30

_sent_counter: int = 0


def get_sent_count() -> int:
    """Return total number of emails dispatched in this runtime process."""
    global _sent_counter
    return _sent_counter


def reset_sent_count() -> None:
    """Reset the dispatch counter (useful for unit tests)."""
    global _sent_counter
    _sent_counter = 0


def build_message(subject: str, html_body: str, to_addr: str, from_addr: str) -> EmailMessage:
    """Construct an RFC-compliant EmailMessage with plain-text fallback and deliverability headers."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=from_addr.split("@")[-1] if "@" in from_addr else None)
    msg["Auto-Submitted"] = "auto-generated"
    msg["Precedence"] = "bulk"
    msg["X-Auto-Response-Suppress"] = "All"
    msg["List-Unsubscribe"] = f"<mailto:{from_addr}?subject=Unsubscribe>"
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
    return msg


class SMTPSession:
    """Manages a persistent, reusable SMTP connection across multi-user batches.

    Prevents repeated connection handshakes and TLS negotiations that can trigger
    SMTP rate-limiting or anti-abuse throttling (e.g. Gmail 421 4.7.0).
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        timeout: int = SMTP_TIMEOUT,
    ):
        from .auth import _load_env_if_needed

        _load_env_if_needed()

        self.host = (host or os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
        raw_port = str(port or os.getenv("SMTP_PORT") or "587").strip()
        self.port = int(raw_port) if raw_port.isdigit() else 587
        self.user = (user or os.environ.get("SMTP_USER", "")).strip()
        self.password = (password or os.environ.get("SMTP_PASS", "")).strip()
        self.timeout = timeout
        self.server: smtplib.SMTP | None = None

    def connect(self) -> SMTPSession:
        """Connect and authenticate to SMTP server."""
        if not self.user or not self.password:
            raise ValueError("SMTP_USER and SMTP_PASS environment variables must not be empty.")
        if self.server is not None:
            try:
                status = self.server.noop()[0]
                if status == 250:
                    return self
            except Exception:
                self.close()

        try:
            self.server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            self.server.starttls()
            self.server.login(self.user, self.password)
        except smtplib.SMTPAuthenticationError as e:
            print(
                f"::error::SMTP authentication failed: {e}. If using Gmail, make sure SMTP_PASS is a 16-character App Password (myaccount.google.com/apppasswords), not your login password."
            )
            self.server = None
            raise
        except Exception as e:
            print(f"::error::SMTP connection failed ({type(e).__name__}): {e}")
            self.server = None
            raise
        return self

    def send_message(self, msg: EmailMessage) -> None:
        """Send an EmailMessage through the persistent connection with auto-reconnect."""
        global _sent_counter
        if _sent_counter >= MAX_DAILY_SEND:
            print(
                f"  [Circuit Breaker] Daily send limit ({MAX_DAILY_SEND}) reached. Skipping dispatch to {msg.get('To')}."
            )
            return

        if self.server is None:
            self.connect()

        try:
            assert self.server is not None
            self.server.send_message(msg)
            _sent_counter += 1
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPResponseException):
            # Attempt one reconnection and retry
            self.connect()
            assert self.server is not None
            self.server.send_message(msg)
            _sent_counter += 1

    def close(self) -> None:
        """Safely close the SMTP connection."""
        if self.server is not None:
            try:
                self.server.quit()
            except Exception:
                pass
            finally:
                self.server = None

    def __enter__(self) -> SMTPSession:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def send(
    subject: str,
    html_body: str,
    to_email: str | None = None,
    session: SMTPSession | None = None,
) -> None:
    global _sent_counter
    from .auth import _load_env_if_needed

    _load_env_if_needed()
    user = os.environ["SMTP_USER"].strip()
    password = os.environ["SMTP_PASS"].strip()
    if not user or not password:
        raise ValueError("SMTP_USER and SMTP_PASS environment variables must not be empty.")
    to_addr = (to_email or os.getenv("MAIL_TO") or user).strip()

    if _sent_counter >= MAX_DAILY_SEND:
        print(f"  [Circuit Breaker] Daily send limit ({MAX_DAILY_SEND}) reached. Skipping dispatch to {to_addr}.")
        return

    msg = build_message(subject, html_body, to_addr, user)

    if session is not None:
        session.send_message(msg)
        print(f"  mailed -> {to_addr}")
        return

    host = (os.getenv("SMTP_HOST") or "smtp.gmail.com").strip()
    raw_port = (os.getenv("SMTP_PORT") or "587").strip()
    port = int(raw_port) if raw_port.isdigit() else 587

    try:
        with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
        _sent_counter += 1
        print(f"  mailed -> {to_addr}")
    except smtplib.SMTPAuthenticationError as e:
        print(
            f"::error::SMTP authentication failed: {e}. If using Gmail, make sure SMTP_PASS is a 16-character App Password (myaccount.google.com/apppasswords), not your login password."
        )
        raise
    except Exception as e:
        print(f"::error::SMTP sending failed ({type(e).__name__}): {e}")
        raise
