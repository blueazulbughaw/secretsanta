from datetime import datetime

from flask import Blueprint, request, jsonify, make_response, g

from ..extensions import db
from ..models import User, FamilyMember, Family
from ..services import otp_service, sms_service
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
        user = User(username=username, full_name="")
        db.session.add(user)
        db.session.commit()
        return _finish_login(user)

    if user.phone:
        try:
            code = otp_service.request_code(user.phone)
        except ValueError as e:
            return jsonify({"error": str(e)}), 429
        try:
            sms_service.send_otp_sms(user.phone, code)
        except sms_service.SmsSendError as e:
            return jsonify({"error": str(e)}), 502
        return jsonify({"ok": True, "method": "otp", "message": "We texted you a 6-digit code."})

    if user.password_hash:
        return jsonify({"ok": True, "method": "password"})

    return jsonify({"error": "This account has no sign-in method set up yet. Contact an admin."}), 400


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


def _finish_login(user):
    user.last_login_at = datetime.utcnow()
    db.session.commit()
    resp = make_response(jsonify({"ok": True, "user": user.to_dict()}))
    return set_auth_cookie(resp, issue_token(user.id))


@bp.get("/auth/me")
@require_auth
def me():
    memberships = FamilyMember.query.filter_by(user_id=g.user.id).all()
    fams = []
    for m in memberships:
        f = Family.query.get(m.family_id)
        fams.append({"id": f.id, "name": f.name, "role": m.role,
                     "join_code": f.join_code if m.role == "admin" else None})
    return jsonify({"user": g.user.to_dict(), "families": fams,
                    "can_create_family": g.user.is_app_admin,
                    "needs_security_setup": not g.user.password_hash and not g.user.phone})


@bp.patch("/auth/me")
@require_auth
def update_me():
    data = request.json or {}
    name = (data.get("full_name") or "").strip()
    if name:
        g.user.full_name = name[:120]
    if "display_name" in data:
        g.user.display_name = (data.get("display_name") or "").strip()[:60] or None
    db.session.commit()
    return jsonify({"ok": True, "user": g.user.to_dict()})


@bp.patch("/auth/security")
@require_auth
def update_security():
    data = request.json or {}
    if "password" in data:
        password = data.get("password") or ""
        if len(password) < 8:
            return jsonify({"error": "Password must be at least 8 characters."}), 400
        g.user.password_hash = hash_password(password)
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
