from flask import Blueprint, jsonify, g

from ..models import Family, FamilyMember, Event
from ..middleware.auth import require_auth

bp = Blueprint("app_admin", __name__)


@bp.get("/app-admin/clans")
@require_auth
def all_clans():
    """The app admin's overview (User.is_app_admin, not a clan role): every clan with its
    members, who its clan admins are, and how many events it has. Read-only. It never
    includes anything about a draw - who drew whom stays secret from every admin."""
    if not g.user.is_app_admin:
        return jsonify({"error": "Only the app admin can see every clan."}), 403
    clans = []
    for fam in Family.query.order_by(Family.name).all():
        members = FamilyMember.query.filter_by(family_id=fam.id).all()
        people = sorted(({
            "user_id": m.user.id,
            "display_name": m.user.display_name or m.user.full_name,
            "username": m.user.username,
            "household_name": m.household.name if m.household else None,
            "role": m.role,
            "is_active": m.user.is_active,
        } for m in members), key=lambda p: (p["role"] != "admin", p["display_name"].lower()))
        clans.append({
            "id": fam.id,
            "name": fam.name,
            "join_code": fam.join_code,
            "created_at": fam.created_at.isoformat() if fam.created_at else None,
            "event_count": Event.query.filter_by(family_id=fam.id).count(),
            "members": people,
        })
    return jsonify(clans)
