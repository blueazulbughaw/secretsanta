import logging

from flask import current_app
from twilio.rest import Client

logger = logging.getLogger(__name__)


class SmsSendError(Exception):
    """Raised when an SMS fails to send so callers can surface a
    plain-language error instead of a false 'ok'."""


def send_otp_sms(to_phone_e164: str, code: str):
    """Sends the sign-in code by text. In dev (no Twilio config), prints
    to console so you can test without a Twilio account."""
    sid = current_app.config.get("TWILIO_ACCOUNT_SID")
    token = current_app.config.get("TWILIO_AUTH_TOKEN")
    from_number = current_app.config.get("TWILIO_FROM_NUMBER")
    if not (sid and token and from_number):
        print(f"\n=== GiftCircle sign-in code for {to_phone_e164}: {code} ===\n")
        if not current_app.debug:
            logger.warning(
                "TWILIO_* is not configured; OTP code for %s was only "
                "printed to the app log, not texted.", to_phone_e164
            )
        return
    body = f"Your GiftCircle sign-in code is {code}. It works for 10 minutes."
    try:
        Client(sid, token).messages.create(to=to_phone_e164, from_=from_number, body=body)
    except Exception:
        logger.exception("Failed to send OTP SMS to %s", to_phone_e164)
        raise SmsSendError(
            "We couldn't send the sign-in text right now. Please try again in a moment."
        )
