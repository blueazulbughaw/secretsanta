import re
from datetime import datetime

from flask import Blueprint, request, jsonify, make_response, g

from ..extensions import db
from ..models import User, FamilyMember, Family
from ..services import otp_service, mail_service
from ..middleware.auth import (issue_token, set_auth_cookie, clear_auth_cookie,
                               require_auth)

bp = Blueprint("auth", __name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@bp.post("/auth/request-otp")
def request_otp():
    email = (request.json or {}).get("email", "").strip().lower()
    if not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address."}), 400
    try:
        code = otp_service.request_code(email)
    except ValueError as e:
        return jsonify({"error": str(e)}), 429
    try:
        mail_service.send_otp_email(email, code)
    except mail_service.EmailSendError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"ok": True, "message": "We emailed you a 6-digit code."})


@bp.post("/auth/verify-otp")
def verify_otp():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    code = data.get("code", "").strip()
    if not otp_service.verify_code(email, code):
        return jsonify({"error": "That code didn't work. Please check it and try again."}), 401

    user = User.query.filter_by(email=email).first()
    is_new = user is None
    if is_new:
        user = User(email=email, full_name="")
        db.session.add(user)
    user.last_login_at = datetime.utcnow()
    db.session.commit()

    resp = make_response(jsonify({"ok": True, "is_new": is_new or not user.full_name,
                                  "user": user.to_dict()}))
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
    return jsonify({"user": g.user.to_dict(), "families": fams})


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


@bp.post("/auth/logout")
@require_auth
def logout():
    return clear_auth_cookie(make_response(jsonify({"ok": True})))
