import logging

from flask import current_app
from flask_mail import Message as MailMessage

from ..extensions import mail

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """Raised when an email fails to send so callers can surface a
    plain-language error instead of a false 'ok'."""


def send_otp_email(to_email: str, code: str):
    """Sends the sign-in code. In dev (no MAIL_SERVER), prints to console
    so you can test without SMTP."""
    if not current_app.config.get("MAIL_SERVER"):
        print(f"\n=== GiftCircle sign-in code for {to_email}: {code} ===\n")
        if not current_app.debug:
            logger.warning(
                "MAIL_SERVER is not configured; OTP code for %s was only "
                "printed to the app log, not emailed.", to_email
            )
        return
    body = (
        "Hello!\n\n"
        f"Your GiftCircle sign-in code is:\n\n    {code}\n\n"
        "It works for 10 minutes. If you didn't ask for this, you can ignore this email.\n"
    )
    msg = MailMessage(subject=f"Your GiftCircle code: {code}",
                      recipients=[to_email], body=body)
    try:
        mail.send(msg)
    except Exception:
        logger.exception("Failed to send OTP email to %s", to_email)
        raise EmailSendError(
            "We couldn't send the sign-in email right now. Please try again in a moment."
        )


def send_plain_email(to_email: str, subject: str, body: str):
    if not current_app.config.get("MAIL_SERVER"):
        print(f"\n=== Email to {to_email} | {subject} ===\n{body}\n")
        return
    try:
        mail.send(MailMessage(subject=subject, recipients=[to_email], body=body))
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        raise EmailSendError(
            "We couldn't send that email right now. Please try again in a moment."
        )
