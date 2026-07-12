from datetime import datetime, timedelta
from functools import wraps

import jwt
from flask import request, jsonify, g, current_app, make_response

from ..models import User, FamilyMember

COOKIE_NAME = "gc_token"


def issue_token(user_id):
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=current_app.config["JWT_DAYS"]),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def set_auth_cookie(resp, token):
    resp.set_cookie(
        COOKIE_NAME, token,
        httponly=True,
        secure=not current_app.debug,
        samesite="Lax",
        max_age=current_app.config["JWT_DAYS"] * 86400,
    )
    return resp


def clear_auth_cookie(resp):
    resp.delete_cookie(COOKIE_NAME)
    return resp


def _current_user():
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, current_app.config["JWT_SECRET"], algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    return User.query.get(int(payload["sub"]))


def require_auth(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = _current_user()
        if not user or not user.is_active:
            return jsonify({"error": "Please sign in first."}), 401
        g.user = user
        return fn(*args, **kwargs)
    return wrapper


def get_membership(family_id, user_id):
    return FamilyMember.query.filter_by(family_id=family_id, user_id=user_id).first()


def require_family_member(family_id):
    """Multi-tenant guard: 403 unless g.user belongs to this family."""
    m = get_membership(family_id, g.user.id)
    if not m:
        return None, (jsonify({"error": "You are not part of this family."}), 403)
    return m, None


def require_family_admin(family_id):
    m, err = require_family_member(family_id)
    if err:
        return None, err
    if m.role != "admin":
        return None, (jsonify({"error": "Only the family organizer can do this."}), 403)
    return m, None
