from datetime import datetime

from flask import Blueprint, request, jsonify, make_response, g

from ..extensions import db
from ..models import User, FamilyMember, Family
from ..services import otp_service, sms_service
from ..services.photo_service import save_photo, remove_photo
from ..middleware.auth import (issue_token, set_auth_cookie, clear_auth_cookie,
                               require_auth)
from ..utils import normalize_us_phone, normalize_username, hash_password, verify_password

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


@bp.post("/auth/send-code")
def send_code():
    """Texts a one-time sign-in code to the phone number on the account, on request."""
    try:
        username = normalize_username((request.json or {}).get("username", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "We couldn't find that username."}), 404
    if not user.phone:
        return jsonify({"error": "This account doesn't have a phone number yet, so please use your "
                                 "password. Your clan admin can add your phone number."}), 400
    try:
        code = otp_service.request_code(user.phone)
    except ValueError as e:
        return jsonify({"error": str(e)}), 429
    try:
        sms_service.send_otp_sms(user.phone, code)
    except sms_service.SmsSendError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"ok": True, "phone_hint": f"••• {user.phone[-4:]}"})


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
            phone = normalize_us_phone(data.get("phone", ""))
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
    data = request.json or {}
    try:
        username = normalize_username(data.get("username", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    code = data.get("code", "").strip()
    user = User.query.filter_by(username=username).first()
    if not user or not user.phone or not otp_service.verify_code(user.phone, code):
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
@require_auth
def me():
    memberships = FamilyMember.query.filter_by(user_id=g.user.id).all()
    fams = []
    for m in memberships:
        f = Family.query.get(m.family_id)
        fams.append({"id": f.id, "name": f.name, "role": m.role,
                     "household_name": m.household.name if m.household else None,
                     "join_code": f.join_code if m.role == "admin" else None})
    return jsonify({"user": g.user.to_dict(), "families": fams,
                    "can_create_family": g.user.is_app_admin,
                    "needs_security_setup": not g.user.password_hash and not g.user.phone,
                    "must_change_password": g.user.must_change_password})


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
        # Resetting an existing password needs the current one. Not when it's a
        # temporary password the person just signed in with, or when none is set yet.
        if g.user.password_hash and not g.user.must_change_password and \
                not verify_password(data.get("current_password") or "", g.user.password_hash):
            return jsonify({"error": "Your current password isn't right."}), 400
        if g.user.must_change_password and verify_password(password, g.user.password_hash):
            return jsonify({"error": "Please choose a different password than the one you were given."}), 400
        g.user.password_hash = hash_password(password)
        g.user.must_change_password = False
    if "phone" in data:
        try:
            phone = normalize_us_phone(data.get("phone", ""))
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
