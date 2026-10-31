"""Optional real email delivery. Off unless SMTP_HOST is set in .env.
Every sent email always lands in the candidate's portal inbox; SMTP is an extra copy."""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("hiremate.mail")


def enabled() -> bool:
    return bool(os.getenv("SMTP_HOST"))


def send(to: str | None, subject: str, body: str) -> bool:
    if not enabled() or not to or to.endswith("@example.com"):  # never mail the synthetic demo addresses
        return False
    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "hiring@example.com"))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=15) as s:
            s.starttls()
            if os.getenv("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.getenv("SMTP_PASSWORD", ""))
            s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Email not sent by SMTP: %s", e)
        return False
