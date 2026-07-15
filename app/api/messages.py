from datetime import datetime

from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import Event, Message, Assignment, EventParticipant, User
from ..middleware.auth import require_auth, require_family_member
from ..services.notification_service import notify

bp = Blueprint("messages", __name__)


def _threads(event_id, user_id):
    """Returns (my_giftee_id, my_giver_id) for this event."""
    give = Assignment.query.filter_by(event_id=event_id, giver_id=user_id).first()
    get_ = Assignment.query.filter_by(event_id=event_id, receiver_id=user_id).first()
    return (give.receiver_id if give else None,
            get_.giver_id if get_ else None)


def _display_for(ev, viewer_id, other_id, relation):
    """How the other party is displayed. Givers stay anonymous."""
    if relation == "giver":  # the person giving TO the viewer — keep secret
        return "Your Secret Santa"
    u = User.query.get(other_id)
    name = u.display_name or u.full_name
    if ev.use_codenames:
        p = EventParticipant.query.filter_by(event_id=ev.id, user_id=other_id).first()
        if p and p.codename:
            name = p.codename
    return name


@bp.get("/events/<int:event_id>/messages")
@require_auth
def get_messages(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    giftee_id, giver_id = _threads(ev.id, g.user.id)
    out = {}
    for key, other in (("giftee", giftee_id), ("giver", giver_id)):
        if not other:
            out[key] = None
            continue
        msgs = (Message.query.filter(
            Message.event_id == ev.id,
            db.or_(
                db.and_(Message.sender_id == g.user.id, Message.recipient_id == other),
                db.and_(Message.sender_id == other, Message.recipient_id == g.user.id),
            )).order_by(Message.created_at).all())
        # mark incoming as read
        for m in msgs:
            if m.recipient_id == g.user.id and not m.read_at:
                m.read_at = datetime.utcnow()
        db.session.commit()
        out[key] = {
            "with_display_name": _display_for(ev, g.user.id, other, key),
            "messages": [{"id": m.id, "mine": m.sender_id == g.user.id,
                          "body": m.body, "at": m.created_at.isoformat()} for m in msgs],
        }
    return jsonify(out)


@bp.post("/events/<int:event_id>/messages")
@require_auth
def send_message(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    data = request.json or {}
    to = data.get("to")
    body = (data.get("body") or "").strip()
    if to not in ("giver", "giftee") or not body:
        return jsonify({"error": "Please write a message first."}), 400
    giftee_id, giver_id = _threads(ev.id, g.user.id)
    recipient = giftee_id if to == "giftee" else giver_id
    if not recipient:
        return jsonify({"error": "Names haven't been drawn yet."}), 400
    m = Message(event_id=ev.id, sender_id=g.user.id,
                recipient_id=recipient, body=body[:2000])
    db.session.add(m)
    db.session.commit()
    # Notification never reveals identity
    sender_label = ("Your Secret Santa" if to == "giftee"
                    else _display_for(ev, recipient, g.user.id, "giftee"))
    recipient_thread = "giver" if to == "giftee" else "giftee"
    notify(recipient, "message", f"New message from {sender_label} 💌",
           "Tap to read it.", link_path=f"/events/{ev.id}/messages/{recipient_thread}")
    return jsonify({"ok": True}), 201
