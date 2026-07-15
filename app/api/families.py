import secrets
import string

from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import Family, FamilyMember, Household, User
from ..middleware.auth import require_auth, require_family_member, require_family_admin
from ..utils import normalize_us_phone, hash_password, slugify_username_base

bp = Blueprint("families", __name__)


def _make_join_code():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not Family.query.filter_by(join_code=code).first():
            return code


@bp.post("/families")
@require_auth
def create_family():
    has_family = FamilyMember.query.filter_by(user_id=g.user.id).first() is not None
    if has_family and not g.user.is_app_admin:
        return jsonify({"error": "Ask your clan admin for a join code instead."}), 403
    name = ((request.json or {}).get("name") or "").strip()
    if not name:
        return jsonify({"error": "Please give your family group a name."}), 400
    fam = Family(name=name[:120], join_code=_make_join_code(), created_by=g.user.id)
    db.session.add(fam)
    db.session.flush()
    db.session.add(FamilyMember(family_id=fam.id, user_id=g.user.id, role="admin"))
    db.session.commit()
    return jsonify({"ok": True, "family": {"id": fam.id, "name": fam.name,
                                           "join_code": fam.join_code}}), 201


@bp.post("/families/join")
@require_auth
def join_family():
    code = ((request.json or {}).get("join_code") or "").strip().upper()
    fam = Family.query.filter_by(join_code=code).first()
    if not fam:
        return jsonify({"error": "We couldn't find a family with that code."}), 404
    existing = FamilyMember.query.filter_by(family_id=fam.id, user_id=g.user.id).first()
    if existing:
        return jsonify({"ok": True, "family": {"id": fam.id, "name": fam.name},
                        "message": "You're already in this family."})
    db.session.add(FamilyMember(family_id=fam.id, user_id=g.user.id, role="member"))
    db.session.commit()
    return jsonify({"ok": True, "family": {"id": fam.id, "name": fam.name}}), 201


@bp.get("/families/<int:family_id>")
@require_auth
def get_family(family_id):
    m, err = require_family_member(family_id)
    if err:
        return err
    fam = Family.query.get_or_404(family_id)
    return jsonify({"id": fam.id, "name": fam.name, "my_role": m.role,
                    "join_code": fam.join_code if m.role == "admin" else None})


@bp.patch("/families/<int:family_id>")
@require_auth
def rename_family(family_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    fam = Family.query.get_or_404(family_id)
    name = ((request.json or {}).get("name") or "").strip()
    if not name:
        return jsonify({"error": "Please give your clan a name."}), 400
    fam.name = name[:120]
    db.session.commit()
    return jsonify({"ok": True, "family": {"id": fam.id, "name": fam.name}})


@bp.get("/families/<int:family_id>/members")
@require_auth
def list_members(family_id):
    m, err = require_family_member(family_id)
    if err:
        return err
    members = FamilyMember.query.filter_by(family_id=family_id).all()
    return jsonify([{
        "membership_id": mem.id,
        "user": mem.user.to_dict(),
        "role": mem.role,
        "household_id": mem.household_id,
        "household_name": mem.household.name if mem.household else None,
    } for mem in members])


@bp.post("/families/<int:family_id>/members")
@require_auth
def add_member(family_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    data = request.json or {}
    full_name = (data.get("full_name") or "").strip()[:120]
    if not full_name:
        return jsonify({"error": "Please enter their name."}), 400

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

    base = slugify_username_base(full_name)
    username = base
    n = 1
    while User.query.filter_by(username=username).first():
        n += 1
        username = f"{base}{n}"

    temp_password = secrets.token_urlsafe(6)
    user = User(username=username, full_name=full_name, email=email or None, phone=phone,
                password_hash=hash_password(temp_password), must_change_password=True)
    db.session.add(user)
    db.session.flush()
    mem = FamilyMember(family_id=family_id, user_id=user.id, role="member")
    db.session.add(mem)
    db.session.flush()
    db.session.commit()
    return jsonify({"ok": True, "user": user.to_dict(), "membership_id": mem.id,
                    "username": username, "temp_password": temp_password}), 201


@bp.patch("/families/<int:family_id>/members/<int:membership_id>")
@require_auth
def update_member(family_id, membership_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    mem = FamilyMember.query.filter_by(id=membership_id, family_id=family_id).first_or_404()
    data = request.json or {}
    if "role" in data:
        if data["role"] not in ("admin", "member"):
            return jsonify({"error": "Role must be admin or member."}), 400
        # Don't allow removing the last admin
        if mem.role == "admin" and data["role"] == "member":
            admins = FamilyMember.query.filter_by(family_id=family_id, role="admin").count()
            if admins <= 1:
                return jsonify({"error": "A family needs at least one clan admin."}), 400
        mem.role = data["role"]
    if "household_id" in data:
        hid = data["household_id"]
        if hid is not None:
            h = Household.query.filter_by(id=hid, family_id=family_id).first()
            if not h:
                return jsonify({"error": "That household doesn't exist in this family."}), 400
        mem.household_id = hid
    if "full_name" in data:
        name = (data.get("full_name") or "").strip()[:120]
        if not name:
            return jsonify({"error": "Name can't be empty."}), 400
        mem.user.full_name = name
    if "email" in data:
        email = (data.get("email") or "").strip()
        if email:
            existing = User.query.filter_by(email=email).first()
            if existing and existing.id != mem.user_id:
                return jsonify({"error": "That email is already in use."}), 409
        mem.user.email = email or None
    if "phone" in data:
        raw = data.get("phone") or ""
        if raw:
            try:
                phone = normalize_us_phone(raw)
            except ValueError as e:
                return jsonify({"error": str(e)}), 400
            existing = User.query.filter_by(phone=phone).first()
            if existing and existing.id != mem.user_id:
                return jsonify({"error": "That phone number is already in use."}), 409
        else:
            phone = None
        mem.user.phone = phone
    db.session.commit()
    return jsonify({"ok": True})


@bp.post("/families/<int:family_id>/members/<int:membership_id>/reset-password")
@require_auth
def reset_member_password(family_id, membership_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    mem = FamilyMember.query.filter_by(id=membership_id, family_id=family_id).first_or_404()
    temp_password = secrets.token_urlsafe(6)
    mem.user.password_hash = hash_password(temp_password)
    mem.user.must_change_password = True
    db.session.commit()
    return jsonify({"ok": True, "temp_password": temp_password})


@bp.delete("/families/<int:family_id>/members/<int:membership_id>")
@require_auth
def remove_member(family_id, membership_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    mem = FamilyMember.query.filter_by(id=membership_id, family_id=family_id).first_or_404()
    if mem.user_id == g.user.id:
        return jsonify({"error": "You can't remove yourself. Ask another clan admin."}), 400
    db.session.delete(mem)
    db.session.commit()
    return jsonify({"ok": True})
