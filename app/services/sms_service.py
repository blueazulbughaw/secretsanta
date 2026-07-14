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
        print(f"\n=== Secret Santa sign-in code for {to_phone_e164}: {code} ===\n")
        if not current_app.debug:
            logger.warning(
                "TWILIO_* is not configured; OTP code for %s was only "
                "printed to the app log, not texted.", to_phone_e164
            )
        return
    body = f"Genri Labs: Your verification code is {code}. This code expires in 10 minutes. Do not share this code with anyone."
    # Also logged even on the success path: carriers can silently block A2P-unregistered
    # numbers (Twilio accepts the send, then delivery fails asynchronously), so this is
    # the fallback way to retrieve a code while registration is pending. Remove once
    # A2P 10DLC registration is approved and delivery is confirmed working end to end.
    logger.warning("OTP code for %s: %s (message also queued via Twilio)", to_phone_e164, code)
    try:
        Client(sid, token).messages.create(to=to_phone_e164, from_=from_number, body=body)
    except Exception:
        logger.exception("Failed to send OTP SMS to %s", to_phone_e164)
        raise SmsSendError(
            "We couldn't send the sign-in text right now. Please try again in a moment."
        )
