from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import Event, EventDish, EventParticipant, User
from ..middleware.auth import require_auth, require_family_member

bp = Blueprint("dishes", __name__)

MAX_DISHES_PER_PERSON = 10
MAX_DISH_NAME = 120


def _entries(event_id):
    """Everyone's sign-up: [{user, dishes:[{id, name}]}], sorted by name."""
    rows = EventDish.query.filter_by(event_id=event_id).order_by(EventDish.id).all()
    by_user = {}
    for r in rows:
        by_user.setdefault(r.user_id, []).append({"id": r.id, "name": r.name})
    users = {u.id: u for u in User.query.filter(User.id.in_(by_user)).all()} if by_user else {}
    out = [{"user": users[uid].public_dict(), "dishes": dishes}
           for uid, dishes in by_user.items() if uid in users]
    return sorted(out, key=lambda e: e["user"]["display_name"].lower())


def _my_signup_error(ev):
    """Why the caller can't change their dishes for this event right now, or None."""
    joining = EventParticipant.query.filter_by(
        event_id=ev.id, user_id=g.user.id, is_participating=True).first()
    if not joining:
        return jsonify({"error": "Only people joining this gift exchange can add dishes."}), 403
    if ev.status == "completed":
        return jsonify({"error": "This gift exchange is finished."}), 400
    if ev.status != "matched":
        return jsonify({"error": "Dish sign-up opens once names are drawn."}), 400
    return None


@bp.get("/events/<int:event_id>/dishes")
@require_auth
def list_dishes(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    return jsonify(_entries(ev.id))


@bp.put("/events/<int:event_id>/dishes/mine")
@require_auth
def set_my_dishes(event_id):
    """Replaces the caller's single entry with `dishes` (a list of names). An
    empty list removes the entry."""
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    err = _my_signup_error(ev)
    if err:
        return err
    raw = (request.get_json(silent=True) or {}).get("dishes")
    if not isinstance(raw, list):
        return jsonify({"error": "Please list the dishes you're bringing."}), 400
    names, seen = [], set()
    for item in raw:
        name = str(item or "").strip()[:MAX_DISH_NAME]
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    if len(names) > MAX_DISHES_PER_PERSON:
        return jsonify({"error": f"You can add up to {MAX_DISHES_PER_PERSON} dishes."}), 400
    EventDish.query.filter_by(event_id=ev.id, user_id=g.user.id).delete()
    for name in names:
        db.session.add(EventDish(event_id=ev.id, user_id=g.user.id, name=name))
    db.session.commit()
    return jsonify(_entries(ev.id))


@bp.delete("/events/<int:event_id>/dishes/mine")
@require_auth
def remove_my_dishes(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    err = _my_signup_error(ev)
    if err:
        return err
    EventDish.query.filter_by(event_id=ev.id, user_id=g.user.id).delete()
    db.session.commit()
    return jsonify(_entries(ev.id))
