from datetime import datetime

from flask import Blueprint, jsonify, g

from ..extensions import db
from ..models import Event, Assignment, EventParticipant, User
from ..middleware.auth import require_auth, require_family_member, require_family_admin
from ..services.matching_service import generate_assignments, MatchingError

bp = Blueprint("assignments", __name__)


@bp.post("/events/<int:event_id>/assignments/generate")
@require_auth
def generate(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_admin(ev.family_id)
    if err:
        return err
    try:
        count = generate_assignments(ev)
    except MatchingError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "matched": count})


@bp.get("/events/<int:event_id>/assignments/mine")
@require_auth
def mine(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    a = Assignment.query.filter_by(event_id=ev.id, giver_id=g.user.id).first()
    if not a:
        return jsonify({"assigned": False,
                        "message": "Names haven't been drawn yet, or you're not in this exchange."})
    receiver = User.query.get(a.receiver_id)
    display = receiver.display_name or receiver.full_name
    if ev.use_codenames:
        p = EventParticipant.query.filter_by(event_id=ev.id, user_id=a.receiver_id).first()
        if p and p.codename:
            display = p.codename
    if not a.revealed_at:
        a.revealed_at = datetime.utcnow()
        db.session.commit()
    return jsonify({"assigned": True, "giftee_display_name": display,
                    "giftee_user_id": a.receiver_id,
                    "budget_amount": float(ev.budget_amount) if ev.budget_amount else None,
                    "budget_currency": ev.budget_currency})


@bp.delete("/events/<int:event_id>/assignments")
@require_auth
def reroll(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_admin(ev.family_id)
    if err:
        return err
    if ev.status == "completed":
        return jsonify({"error": "This event is finished and can't be re-drawn."}), 400
    Assignment.query.filter_by(event_id=ev.id).delete()
    ev.status = "open"
    ev.matched_at = None
    db.session.commit()
    return jsonify({"ok": True})


@bp.get("/events/<int:event_id>/assignments/status")
@require_auth
def status(event_id):
    """Admin progress view: counts only — never who drew whom."""
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_admin(ev.family_id)
    if err:
        return err
    total = Assignment.query.filter_by(event_id=ev.id).count()
    revealed = Assignment.query.filter(
        Assignment.event_id == ev.id, Assignment.revealed_at.isnot(None)).count()
    return jsonify({"matched": total, "revealed": revealed, "status": ev.status})
