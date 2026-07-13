import re

from flask import current_app


def is_app_admin_phone(phone: str) -> bool:
    """Whether this phone number is allowed to create new families.
    If APP_ADMIN_PHONES isn't set, family creation is unrestricted
    (dev-friendly default, mirroring MAIL_SERVER/TWILIO_* conventions)."""
    allowed = current_app.config.get("APP_ADMIN_PHONES", [])
    return not allowed or phone in allowed


def normalize_us_phone(raw: str) -> str:
    """Normalizes a US phone number to E.164 (+1XXXXXXXXXX).

    Accepts common input shapes like "(555) 123-4567", "555-123-4567",
    "5551234567", or the same with a leading country code "1".
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError("Please enter a valid 10-digit US phone number.")
    return f"+1{digits}"
