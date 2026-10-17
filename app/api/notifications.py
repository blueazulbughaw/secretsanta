from flask import Blueprint, request, jsonify, g, current_app

from ..extensions import db
from ..models import Notification, PushSubscription
from ..middleware.auth import require_auth
from ..utils import json_body

bp = Blueprint("notifications", __name__)


@bp.get("/notifications")
@require_auth
def list_notifications():
    ns = (Notification.query.filter_by(user_id=g.user.id)
          .order_by(Notification.created_at.desc()).limit(50).all())
    unread = Notification.query.filter_by(user_id=g.user.id, is_read=False).count()
    return jsonify({"unread": unread, "items": [{
        "id": n.id, "type": n.type, "title": n.title, "body": n.body,
        "link_path": n.link_path, "is_read": n.is_read,
        "at": n.created_at.isoformat(),
    } for n in ns]})


@bp.post("/notifications/<int:notif_id>/read")
@require_auth
def mark_read(notif_id):
    n = Notification.query.filter_by(id=notif_id, user_id=g.user.id).first_or_404()
    n.is_read = True
    db.session.commit()
    return jsonify({"ok": True})


@bp.post("/notifications/read-all")
@require_auth
def read_all():
    Notification.query.filter_by(user_id=g.user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})


@bp.get("/push/key")
@require_auth
def push_key():
    """The public key a browser needs to turn on notifications (null = push is off here)."""
    return jsonify({"public_key": current_app.config.get("VAPID_PUBLIC_KEY") or None})


@bp.post("/push/unsubscribe")
@require_auth
def push_unsubscribe():
    """This device stops getting notifications (turned off, or signing out of it)."""
    endpoint = json_body().get("endpoint")
    if isinstance(endpoint, str) and endpoint:
        PushSubscription.query.filter_by(endpoint=endpoint[:500], user_id=g.user.id).delete()
        db.session.commit()
    return jsonify({"ok": True})


@bp.post("/push/test")
@require_auth
def push_test():
    """Profile & Security's "Send Me a Test": pushes to the signed-in person's own devices
    only (nothing goes in the bell), so they can see it arrive on their phone / watch."""
    from ..services.push_service import enabled, send_test
    if not enabled():
        return jsonify({"error": "Notifications aren't set up on this site yet."}), 400
    sent = send_test(g.user.id)
    if not sent:
        return jsonify({"error": "Couldn't reach this device. Turn notifications off and on again, then try again."}), 400
    return jsonify({"ok": True, "sent": sent})


@bp.post("/push/subscribe")
@require_auth
def push_subscribe():
    """Stores this device's push subscription, so notify() can reach it
    (services/push_service.py). A device belongs to whoever signed in on it last."""
    data = json_body()
    endpoint = data.get("endpoint") if isinstance(data.get("endpoint"), str) else ""
    keys = data.get("keys") if isinstance(data.get("keys"), dict) else {}
    if (not endpoint.startswith("https://") or len(endpoint) > 500
            or not all(isinstance(keys.get(k), str) and 0 < len(keys[k]) <= 255 for k in ("p256dh", "auth"))):
        return jsonify({"error": "Invalid subscription."}), 400
    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if existing and existing.user_id != g.user.id:
        existing.user_id = g.user.id   # someone else signed in on this device
        db.session.commit()
    if not existing:
        db.session.add(PushSubscription(
            user_id=g.user.id, endpoint=endpoint[:500],
            p256dh_key=keys["p256dh"][:255], auth_key=keys["auth"][:255],
            user_agent=(request.user_agent.string or "")[:255]))
        db.session.commit()
    return jsonify({"ok": True})
