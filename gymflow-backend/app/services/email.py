"""Transactional email: Resend (HTTP API) or plain SMTP. Without either, messages are logged (dev mode)."""
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.RESEND_API_KEY or settings.SMTP_HOST)


def send(to: str, subject: str, text: str, html: str | None = None) -> bool:
    """Send one email. Returns True when handed to a provider; never raises (callers stay idempotent)."""
    if settings.RESEND_API_KEY:
        try:
            r = httpx.post("https://api.resend.com/emails", timeout=15,
                           headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                           json={"from": settings.EMAIL_FROM, "to": [to], "subject": subject, "text": text,
                                 **({"html": html} if html else {})})
            if r.status_code < 300:
                return True
            logger.error("Resend error %s: %s", r.status_code, r.text[:300])
        except httpx.HTTPError:
            logger.exception("Resend request failed")
        return False
    if settings.SMTP_HOST:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = settings.EMAIL_FROM, to, subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
                smtp.starttls()
                if settings.SMTP_USER:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD or "")
                smtp.send_message(msg)
            return True
        except (OSError, smtplib.SMTPException):
            logger.exception("SMTP send failed")
            return False
    logger.info("[email dev-mode] to=%s subject=%s\n%s", to, subject, text)
    return False
