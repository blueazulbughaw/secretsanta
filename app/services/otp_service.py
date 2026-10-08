import hashlib
import secrets
from datetime import datetime, timedelta

from flask import current_app

from ..extensions import db
from ..models import OtpCode


def _hash(code: str) -> str:
    pepper = current_app.config["OTP_PEPPER"]
    return hashlib.sha256(f"{code}{pepper}".encode()).hexdigest()


def request_code(phone: str) -> str:
    """Create + store a 6-digit code. Raises ValueError if rate-limited.
    Returns the raw code so the caller can text it."""
    phone = phone.strip()
    window_start = datetime.utcnow() - timedelta(
        minutes=current_app.config["OTP_WINDOW_MINUTES"])
    recent = OtpCode.query.filter(
        OtpCode.phone == phone, OtpCode.created_at >= window_start).count()
    if recent >= current_app.config["OTP_REQUESTS_PER_WINDOW"]:
        raise ValueError("Too many codes requested. Please wait a few minutes and try again.")

    code = f"{secrets.randbelow(1000000):06d}"
    otp = OtpCode(
        phone=phone,
        code_hash=_hash(code),
        expires_at=datetime.utcnow() + timedelta(
            minutes=current_app.config["OTP_TTL_MINUTES"]),
    )
    db.session.add(otp)
    db.session.commit()
    return code


_ip_hits: dict = {}


def enforce_ip_rate_limit(ip: str, limit: int = 10, window_minutes: int = 15):
    """A second, lighter guard on top of the per-phone limit above, specifically for the
    phone-first sign-in code request: that endpoint takes no username, so (unlike every
    other endpoint in this app) it can be hit with no prior knowledge of who's even in the
    system. The per-phone limit alone caps damage to one real account at a time; this caps
    how many DIFFERENT numbers one requester can try in a window, regardless of whether any
    of them match a real account (a non-match costs nothing to send, but still costs a DB
    query, and a determined requester could otherwise walk through many real numbers one
    each). In-memory, so it resets if the app process restarts and is tracked separately
    per worker process under a multi-process deployment - a real but acceptable limitation
    for this app's scale; the per-phone limit is still the primary, DB-backed defense."""
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=window_minutes)
    hits = [t for t in _ip_hits.get(ip, []) if t >= window_start]
    if len(hits) >= limit:
        _ip_hits[ip] = hits
        raise ValueError("Too many requests from this network. Please wait a few minutes and try again.")
    hits.append(now)
    _ip_hits[ip] = hits


def verify_code(phone: str, code: str) -> bool:
    phone = phone.strip()
    otp = (OtpCode.query
           .filter(OtpCode.phone == phone,
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
