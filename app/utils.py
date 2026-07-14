import re

from werkzeug.security import generate_password_hash, check_password_hash


def normalize_username(raw: str) -> str:
    """Lowercases and strips a username; enforces a simple safe charset."""
    username = (raw or "").strip().lower()
    if not re.match(r"^[a-z0-9._-]{3,60}$", username):
        raise ValueError(
            "Username must be 3-60 characters: letters, numbers, dots, "
            "dashes, or underscores only."
        )
    return username


def hash_password(raw: str) -> str:
    return generate_password_hash(raw)


def verify_password(raw: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return check_password_hash(password_hash, raw)


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
