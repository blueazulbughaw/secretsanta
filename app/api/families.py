import secrets
import string

from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import Family, FamilyMember, Household
from ..middleware.auth import require_auth, require_family_member, require_family_admin
from ..utils import is_app_admin_phone

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
    if not is_app_admin_phone(g.user.phone):
        return jsonify({"error": "Ask the family organizer for a join code instead."}), 403
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
                return jsonify({"error": "A family needs at least one organizer."}), 400
        mem.role = data["role"]
    if "household_id" in data:
        hid = data["household_id"]
        if hid is not None:
            h = Household.query.filter_by(id=hid, family_id=family_id).first()
            if not h:
                return jsonify({"error": "That household doesn't exist in this family."}), 400
        mem.household_id = hid
    db.session.commit()
    return jsonify({"ok": True})


@bp.delete("/families/<int:family_id>/members/<int:membership_id>")
@require_auth
def remove_member(family_id, membership_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    mem = FamilyMember.query.filter_by(id=membership_id, family_id=family_id).first_or_404()
    if mem.user_id == g.user.id:
        return jsonify({"error": "You can't remove yourself. Ask another organizer."}), 400
    db.session.delete(mem)
    db.session.commit()
    return jsonify({"ok": True})
