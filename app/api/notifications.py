from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import Notification, PushSubscription
from ..middleware.auth import require_auth

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


@bp.post("/push/subscribe")
@require_auth
def push_subscribe():
    """Future-ready: stores the browser's push subscription. Sending comes later."""
    data = request.json or {}
    endpoint = (data.get("endpoint") or "").strip()
    keys = data.get("keys") or {}
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        return jsonify({"error": "Invalid subscription."}), 400
    existing = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if not existing:
        db.session.add(PushSubscription(
            user_id=g.user.id, endpoint=endpoint[:500],
            p256dh_key=keys["p256dh"][:255], auth_key=keys["auth"][:255],
            user_agent=(request.user_agent.string or "")[:255]))
        db.session.commit()
    return jsonify({"ok": True})
