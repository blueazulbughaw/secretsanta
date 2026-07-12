from flask import Blueprint, request, jsonify

from ..extensions import db
from ..models import Household, FamilyMember
from ..middleware.auth import require_auth, require_family_member, require_family_admin

bp = Blueprint("households", __name__)


@bp.get("/families/<int:family_id>/households")
@require_auth
def list_households(family_id):
    _, err = require_family_member(family_id)
    if err:
        return err
    hs = Household.query.filter_by(family_id=family_id).all()
    return jsonify([{"id": h.id, "name": h.name} for h in hs])


@bp.post("/families/<int:family_id>/households")
@require_auth
def create_household(family_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    name = ((request.json or {}).get("name") or "").strip()
    if not name:
        return jsonify({"error": "Please give the household a name."}), 400
    if Household.query.filter_by(family_id=family_id, name=name).first():
        return jsonify({"error": "That household name is already used."}), 400
    h = Household(family_id=family_id, name=name[:120])
    db.session.add(h)
    db.session.commit()
    return jsonify({"ok": True, "household": {"id": h.id, "name": h.name}}), 201


@bp.delete("/households/<int:household_id>")
@require_auth
def delete_household(household_id):
    h = Household.query.get_or_404(household_id)
    _, err = require_family_admin(h.family_id)
    if err:
        return err
    FamilyMember.query.filter_by(household_id=h.id).update({"household_id": None})
    db.session.delete(h)
    db.session.commit()
    return jsonify({"ok": True})
