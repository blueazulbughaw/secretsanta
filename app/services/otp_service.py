import hashlib
import secrets
from datetime import datetime, timedelta

from flask import current_app

from ..extensions import db
from ..models import OtpCode


def _hash(code: str) -> str:
    pepper = current_app.config["OTP_PEPPER"]
    return hashlib.sha256(f"{code}{pepper}".encode()).hexdigest()


def request_code(email: str) -> str:
    """Create + store a 6-digit code. Raises ValueError if rate-limited.
    Returns the raw code so the caller can email it."""
    email = email.strip().lower()
    window_start = datetime.utcnow() - timedelta(
        minutes=current_app.config["OTP_WINDOW_MINUTES"])
    recent = OtpCode.query.filter(
        OtpCode.email == email, OtpCode.created_at >= window_start).count()
    if recent >= current_app.config["OTP_REQUESTS_PER_WINDOW"]:
        raise ValueError("Too many codes requested. Please wait a few minutes and try again.")

    code = f"{secrets.randbelow(1000000):06d}"
    otp = OtpCode(
        email=email,
        code_hash=_hash(code),
        expires_at=datetime.utcnow() + timedelta(
            minutes=current_app.config["OTP_TTL_MINUTES"]),
    )
    db.session.add(otp)
    db.session.commit()
    return code


def verify_code(email: str, code: str) -> bool:
    email = email.strip().lower()
    otp = (OtpCode.query
           .filter(OtpCode.email == email,
                   OtpCode.used_at.is_(None),
                   OtpCode.expires_at >= datetime.utcnow())
           .order_by(OtpCode.created_at.desc())
           .first())
    if not otp:
        return False
    if otp.attempts >= current_app.config["OTP_MAX_ATTEMPTS"]:
        return False
    otp.attempts += 1
    if otp.code_hash != _hash(code.strip()):
        db.session.commit()
        return False
    otp.used_at = datetime.utcnow()
    db.session.commit()
    return True
