from datetime import datetime

from flask import Blueprint, request, jsonify, make_response, g

from ..extensions import db
from ..models import User, FamilyMember, Family
from ..services import otp_service, sms_service
from ..services.photo_service import save_photo, remove_photo
from ..middleware.auth import (issue_token, set_auth_cookie, clear_auth_cookie,
                               require_auth, _current_user)
from ..utils import normalize_phone, normalize_username, hash_password, verify_password

bp = Blueprint("auth", __name__)


@bp.post("/auth/login-start")
def login_start():
    try:
        username = normalize_username((request.json or {}).get("username", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"ok": True, "exists": False})
    # Only reports what sign-in options exist. It never sends a text: that only happens
    # when the person asks for one (POST /auth/send-code).
    if not user.phone and not user.password_hash:
        return jsonify({"error": "This account has no sign-in method set up yet. Contact an admin."}), 400
    return jsonify({"ok": True, "exists": True, "has_phone": bool(user.phone),
                    "has_password": bool(user.password_hash)})


NO_ACCOUNT_MESSAGE = "That phone number isn't on an account. Please contact your Clan Admin."
CODE_SENT_MESSAGE = "We've texted a sign-in code to that number."
# The IP-rate-limited branch below deliberately answers with this same message - see why
# in the enforce_ip_rate_limit() docstring and the function comment above.


@bp.post("/auth/send-code")
def send_code():
    """Texts a one-time sign-in code to whichever account has this phone number, on request.
    Phone-first by design (no username needed): a family member who's forgotten their
    password - the whole reason this exists - still remembers their own phone number, so
    this is the account-recovery-proof path, not gated behind recalling anything else.

    Does say whether the number matches an account (NO_ACCOUNT_MESSAGE vs. a real send) -
    a deliberate choice, not an oversight: this app is a small trusted family group, and
    "that number isn't on file, ask your Clan Admin" is worth more than the enumeration
    protection it costs. The IP rate limit below is the one case that still answers
    generically - whether a requester is being throttled is a separate, lower-stakes kind
    of information than whose phone numbers are in the system."""
    data = request.json or {}
    try:
        phone = normalize_phone(data.get("phone", ""), data.get("phone_country", "US"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400  # about their input's format, not account existence
    try:
        otp_service.enforce_ip_rate_limit(request.remote_addr or "unknown")
    except ValueError:
        return jsonify({"ok": True, "message": CODE_SENT_MESSAGE})  # never leak the limit
    user = User.query.filter_by(phone=phone).first()
    if not user:
        return jsonify({"error": NO_ACCOUNT_MESSAGE}), 404
    try:
        code = otp_service.request_code(phone)
        sms_service.send_otp_sms(phone, code)
    except ValueError as e:
        return jsonify({"error": str(e)}), 429  # phone-level rate limit (OTP_REQUESTS_PER_WINDOW)
    except sms_service.SmsSendError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"ok": True, "message": CODE_SENT_MESSAGE})


@bp.post("/auth/register")
def register():
    data = request.json or {}
    try:
        username = normalize_username(data.get("username", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "That username is already taken."}), 409

    # The display name is what the clan sees, and only a clan admin can change it later,
    # so it has to be chosen here and can't just be the username.
    full_name = (data.get("full_name") or "").strip()[:120]
    if not full_name:
        return jsonify({"error": "Please enter your display name."}), 400
    if full_name == username:
        return jsonify({"error": "Your display name should be different from your username."}), 400

    password = data.get("password") or ""
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    email = (data.get("email") or "").strip()
    if email and User.query.filter_by(email=email).first():
        return jsonify({"error": "That email is already in use."}), 409

    phone = None
    if data.get("phone"):
        try:
            phone = normalize_phone(data.get("phone", ""), data.get("phone_country", "US"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if User.query.filter_by(phone=phone).first():
            return jsonify({"error": "That phone number is already in use."}), 409

    clan_name = (data.get("clan_name") or "").strip()[:120]

    user = User(username=username, email=email or None, phone=phone,
                password_hash=hash_password(password), full_name=full_name)
    db.session.add(user)
    db.session.flush()

    family = None
    if clan_name:
        from .families import _make_join_code
        family = Family(name=clan_name, join_code=_make_join_code(), created_by=user.id)
        db.session.add(family)
        db.session.flush()
        db.session.add(FamilyMember(family_id=family.id, user_id=user.id, role="admin"))

    db.session.commit()
    extra = {"family": {"id": family.id, "name": family.name,
                        "join_code": family.join_code}} if family else {}
    return _finish_login(user, **extra)


@bp.post("/auth/verify-otp")
def verify_otp():
    """Pairs with /auth/send-code: phone-based, not username-based."""
    data = request.json or {}
    try:
        phone = normalize_phone(data.get("phone", ""), data.get("phone_country", "US"))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    code = data.get("code", "").strip()
    user = User.query.filter_by(phone=phone).first()
    if not user or not otp_service.verify_code(phone, code):
        return jsonify({"error": "That code didn't work. Please check it and try again."}), 401
    return _finish_login(user)


@bp.post("/auth/login-password")
def login_password():
    data = request.json or {}
    try:
        username = normalize_username(data.get("username", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    password = data.get("password", "")
    user = User.query.filter_by(username=username).first()
    if not user or not verify_password(password, user.password_hash):
        return jsonify({"error": "Wrong username or password."}), 401
    return _finish_login(user)


def _finish_login(user, **extra):
    user.last_login_at = datetime.utcnow()
    db.session.commit()
    resp = make_response(jsonify({"ok": True, "user": user.to_dict(), **extra}))
    return set_auth_cookie(resp, issue_token(user.id))


@bp.get("/auth/me")
def me():
    # Not @require_auth: the client polls this on every page load (logged in or not) to
    # learn whether there's a session, so an anonymous visitor is a normal 200 here, not a
    # 401. A 401 is technically correct REST but the browser logs every non-2xx fetch as a
    # console error regardless of whether the JS catches it, so every single anonymous page
    # load showed a "Failed to load resource: 401" the instant the page opened.
    user = _current_user()
    if not user or not user.is_active:
        return jsonify({"authenticated": False})
    memberships = FamilyMember.query.filter_by(user_id=user.id).all()
    fams = []
    for m in memberships:
        f = Family.query.get(m.family_id)
        fams.append({"id": f.id, "name": f.name, "role": m.role,
                     "household_id": m.household_id,
                     "household_name": m.household.name if m.household else None,
                     "join_code": f.join_code if m.role == "admin" else None})
    return jsonify({"authenticated": True, "user": user.to_dict(), "families": fams,
                    "can_create_family": user.is_app_admin,
                    "needs_security_setup": not user.password_hash and not user.phone,
                    "must_change_password": user.must_change_password})


# Free-text profile fields the clan sees on My Clan, and their max lengths
PROFILE_FIELD_LIMITS = {"about_me": 1000, "likes": 1000, "favorite_color": 40, "avoid_gifts": 1000}


def _display_name_error(new_name):
    """Only a clan admin can change a display name (their own included; the one
    exception is a brand-new account with no name yet), and it has to differ from
    the username. Returns the response to send, or None."""
    is_admin = g.user.is_app_admin or FamilyMember.query.filter_by(
        user_id=g.user.id, role="admin").first() is not None
    if g.user.full_name and not is_admin:
        return jsonify({"error": "Only your clan admin can change your display name."}), 403
    if new_name and new_name == g.user.username:
        return jsonify({"error": "Your display name should be different from your username."}), 400
    return None


@bp.patch("/auth/me")
@require_auth
def update_me():
    data = request.json or {}
    name = (data.get("full_name") or "").strip()[:120]
    if name and name != g.user.full_name:
        err = _display_name_error(name)
        if err:
            return err
        g.user.full_name = name
    if "display_name" in data:
        shown = (data.get("display_name") or "").strip()[:60] or None
        if shown != g.user.display_name:
            err = _display_name_error(shown)
            if err:
                return err
            g.user.display_name = shown
    for field, limit in PROFILE_FIELD_LIMITS.items():
        if field in data:
            setattr(g.user, field, str(data.get(field) or "").strip()[:limit] or None)
    db.session.commit()
    return jsonify({"ok": True, "user": g.user.to_dict()})


@bp.post("/auth/me/photo")
@require_auth
def set_my_photo():
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"error": "Please choose a photo."}), 400
    try:
        new_path = save_photo(photo, "avatars", square=True)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    old_path, g.user.photo_path = g.user.photo_path, new_path
    db.session.commit()
    remove_photo(old_path)
    return jsonify({"ok": True, "user": g.user.to_dict()})


@bp.delete("/auth/me/photo")
@require_auth
def remove_my_photo():
    old_path, g.user.photo_path = g.user.photo_path, None
    db.session.commit()
    remove_photo(old_path)
    return jsonify({"ok": True, "user": g.user.to_dict()})


@bp.patch("/auth/security")
@require_auth
def update_security():
    data = request.json or {}
    if "password" in data:
        password = data.get("password") or ""
        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters."}), 400
        # Deliberately doesn't ask for the current password: this app's real users
        # routinely forget it (that's the actual problem the texted sign-in code solves
        # too), and reaching this endpoint at all already requires a valid session - that
        # bar is the same one every other change on this account goes through.
        if g.user.must_change_password and verify_password(password, g.user.password_hash):
            return jsonify({"error": "Please choose a different password than the one you were given."}), 400
        g.user.password_hash = hash_password(password)
        g.user.must_change_password = False
    if "phone" in data:
        try:
            phone = normalize_phone(data.get("phone", ""), data.get("phone_country", "US"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        existing = User.query.filter_by(phone=phone).first()
        if existing and existing.id != g.user.id:
            return jsonify({"error": "That phone number is already in use."}), 409
        g.user.phone = phone
    db.session.commit()
    return jsonify({"ok": True, "user": g.user.to_dict()})


@bp.post("/auth/logout")
@require_auth
def logout():
    return clear_auth_cookie(make_response(jsonify({"ok": True})))
