"""Outgoing email. Standard library only (smtplib), so no extra dependency or vendor lock-in:
any SMTP service works (Gmail with an app password, Brevo, Mailgun, SES, ...).

EMAIL_PROVIDER=console logs the email instead of sending it (development), smtp sends it,
fake keeps it in `outbox` (tests).
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid

from app.core.config import settings

log = logging.getLogger("twin.email")

# Reserved for documentation and testing (RFC 2606 / 6761): mail there can never arrive.
# The demo accounts use them, so they are never sent to.
_UNDELIVERABLE = (".example", ".test", ".invalid", ".localhost")
_EXAMPLE_DOMAINS = {"example.com", "example.org", "example.net"}


class EmailError(Exception):
    pass


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


outbox: list[Email] = []  # the fake provider's sent mail


def deliverable(address: str) -> bool:
    domain = address.rsplit("@", 1)[-1].lower().rstrip(".")
    if any(domain == d or domain.endswith(f".{d}") for d in _EXAMPLE_DOMAINS):
        return False
    return not any(domain.endswith(tld) or domain == tld[1:] for tld in _UNDELIVERABLE)


def _message(email: Email) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = email.to
    msg["Subject"] = email.subject
    msg["Message-ID"] = make_msgid(domain="twin.local")
    for k, v in email.headers.items():
        msg[k] = v
    msg.set_content(email.text)
    if email.html:
        msg.add_alternative(email.html, subtype="html")
    return msg


def send(email: Email) -> None:
    """Send one email or raise EmailError."""
    provider = settings.email_provider
    if provider == "fake":
        outbox.append(email)
        return
    if provider == "console":
        log.info(
            "EMAIL (console, not sent) to=%s subject=%r\n%s", email.to, email.subject, email.text
        )
        return
    if not settings.smtp_host:
        raise EmailError("SMTP_HOST is not set")
    msg = _message(email)
    try:
        if settings.smtp_port == 465:  # implicit TLS
            server: smtplib.SMTP = smtplib.SMTP_SSL(
                settings.smtp_host, 465, timeout=20, context=ssl.create_default_context()
            )
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        with server:
            if settings.smtp_port != 465 and settings.smtp_starttls:
                server.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        # Never include the password; the exception text from smtplib doesn't contain it.
        raise EmailError(f"{type(exc).__name__}: {exc}"[:300]) from exc
