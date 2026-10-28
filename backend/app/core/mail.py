"""Outgoing mail: a log backend for development, SMTP for production.

Only password resets send mail today. The log backend writes the reset link
to the application log, which is enough locally; in production it is refused
so that a visitor is told reset is unavailable rather than silently receiving
nothing.
"""
from dataclasses import dataclass
from email.message import EmailMessage
import logging
import smtplib
from typing import Optional

from app.core.config import _get_setting


logger = logging.getLogger("triptogether")
BACKENDS = ("log", "smtp")


class MailConfigurationError(ValueError):
    pass


class MailDeliveryError(Exception):
    pass


@dataclass(frozen=True)
class SmtpSettings:
    host: str
    port: int
    username: Optional[str]
    password: Optional[str]
    sender: str
    starttls: bool


def mail_backend(environment: Optional[str] = None) -> str:
    value = (_get_setting("MAIL_BACKEND", "log") or "log").strip().lower()
    if value not in BACKENDS:
        raise MailConfigurationError("MAIL_BACKEND must be log or smtp.")
    environment = environment or _get_setting("APP_ENV", "development")
    if value == "log" and environment == "production":
        # Logging a reset link in production would mean nobody ever receives it.
        raise MailConfigurationError("MAIL_BACKEND=log is for development only.")
    return value


def smtp_settings() -> SmtpSettings:
    host = (_get_setting("SMTP_HOST") or "").strip()
    sender = (_get_setting("SMTP_FROM") or "").strip()
    if not host or not sender:
        raise MailConfigurationError("SMTP_HOST and SMTP_FROM are required for MAIL_BACKEND=smtp.")
    try:
        port = int(_get_setting("SMTP_PORT", "587") or "587")
    except ValueError:
        raise MailConfigurationError("SMTP_PORT must be an integer.") from None
    starttls = str(_get_setting("SMTP_STARTTLS", "1") or "1").strip().lower() in ("1", "true", "yes")
    return SmtpSettings(host=host, port=port, username=_get_setting("SMTP_USERNAME"),
                        password=_get_setting("SMTP_PASSWORD"), sender=sender, starttls=starttls)


def send_mail(to: str, subject: str, body: str) -> None:
    """Deliver one plain-text message, or raise MailDeliveryError; never logs the body in production."""
    if mail_backend() == "log":
        logger.info("Mail to %s: %s\n%s", to, subject, body)
        return
    settings = smtp_settings()
    message = EmailMessage()
    message["From"] = settings.sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.host, settings.port, timeout=10) as smtp:
            if settings.starttls:
                smtp.starttls()
            if settings.username:
                smtp.login(settings.username, settings.password or "")
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError):
        logger.error("Mail delivery failed")
        raise MailDeliveryError() from None
