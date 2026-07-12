from flask import current_app
from flask_mail import Message as MailMessage

from ..extensions import mail


def send_otp_email(to_email: str, code: str):
    """Sends the sign-in code. In dev (no MAIL_SERVER), prints to console
    so you can test without SMTP."""
    if not current_app.config.get("MAIL_SERVER"):
        print(f"\n=== GiftCircle sign-in code for {to_email}: {code} ===\n")
        return
    body = (
        "Hello!\n\n"
        f"Your GiftCircle sign-in code is:\n\n    {code}\n\n"
        "It works for 10 minutes. If you didn't ask for this, you can ignore this email.\n"
    )
    msg = MailMessage(subject=f"Your GiftCircle code: {code}",
                      recipients=[to_email], body=body)
    mail.send(msg)


def send_plain_email(to_email: str, subject: str, body: str):
    if not current_app.config.get("MAIL_SERVER"):
        print(f"\n=== Email to {to_email} | {subject} ===\n{body}\n")
        return
    mail.send(MailMessage(subject=subject, recipients=[to_email], body=body))
