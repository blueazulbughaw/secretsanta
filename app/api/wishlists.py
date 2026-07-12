from datetime import datetime

from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import Event, WishlistItem, Assignment, User, EventParticipant
from ..middleware.auth import require_auth, require_family_member, require_family_admin
from ..services.notification_service import notify

bp = Blueprint("wishlists", __name__)


def _my_giftee(event_id):
    a = Assignment.query.filter_by(event_id=event_id, giver_id=g.user.id).first()
    return a.receiver_id if a else None


@bp.get("/events/<int:event_id>/wishlists/mine")
@require_auth
def my_wishlist(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    items = (WishlistItem.query.filter_by(event_id=ev.id, user_id=g.user.id)
             .order_by(WishlistItem.priority).all())
    # Owner NEVER sees purchase status.
    return jsonify({"items": [i.to_dict(include_purchase=False) for i in items],
                    "limit": ev.wishlist_limit})


@bp.post("/events/<int:event_id>/wishlists")
@require_auth
def add_item(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    count = WishlistItem.query.filter_by(event_id=ev.id, user_id=g.user.id).count()
    if count >= ev.wishlist_limit:
        return jsonify({"error": f"Your list is full ({ev.wishlist_limit} gifts). "
                                 "Remove one to add another."}), 400
    data = request.json or {}
    name = (data.get("item_name") or "").strip()
    if not name:
        return jsonify({"error": "Please tell us what the gift is."}), 400
    item = WishlistItem(
        event_id=ev.id, user_id=g.user.id, item_name=name[:200],
        description=(data.get("description") or "").strip() or None,
        link_url=(data.get("link_url") or "").strip()[:500] or None,
        price_estimate=data.get("price_estimate"),
        priority=int(data.get("priority") or 3),
    )
    db.session.add(item)
    db.session.commit()
    # Nudge their Secret Santa if names are drawn
    giver = Assignment.query.filter_by(event_id=ev.id, receiver_id=g.user.id).first()
    if giver:
        notify(giver.giver_id, "wishlist", "Your person added a gift idea 🎁",
               "Take a look at their updated wishlist.",
               link_path=f"/events/{ev.id}/giftee")
    return jsonify({"ok": True, "item": item.to_dict()}), 201


@bp.patch("/wishlists/<int:item_id>")
@require_auth
def edit_item(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    if item.user_id != g.user.id:
        return jsonify({"error": "You can only edit your own list."}), 403
    data = request.json or {}
    if data.get("item_name"):
        item.item_name = data["item_name"].strip()[:200]
    for f in ("description", "link_url"):
        if f in data:
            setattr(item, f, (data.get(f) or "").strip() or None)
    if "price_estimate" in data:
        item.price_estimate = data["price_estimate"]
    if "priority" in data:
        item.priority = int(data["priority"])
    db.session.commit()
    return jsonify({"ok": True, "item": item.to_dict()})


@bp.delete("/wishlists/<int:item_id>")
@require_auth
def delete_item(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    if item.user_id != g.user.id:
        return jsonify({"error": "You can only edit your own list."}), 403
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True})


@bp.get("/events/<int:event_id>/wishlists/giftee")
@require_auth
def giftee_wishlist(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    giftee_id = _my_giftee(ev.id)
    if not giftee_id:
        return jsonify({"error": "Names haven't been drawn yet."}), 400
    items = (WishlistItem.query.filter_by(event_id=ev.id, user_id=giftee_id)
             .order_by(WishlistItem.priority).all())
    # Giver DOES see purchase status.
    return jsonify({"items": [i.to_dict(include_purchase=True) for i in items]})


@bp.post("/wishlists/<int:item_id>/purchase")
@require_auth
def mark_purchased(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    ev = Event.query.get_or_404(item.event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    if item.user_id == g.user.id:
        return jsonify({"error": "You can't mark your own wishlist."}), 403
    if _my_giftee(ev.id) != item.user_id:
        return jsonify({"error": "You can only mark gifts for your own person."}), 403
    item.is_purchased = not item.is_purchased
    item.purchased_by = g.user.id if item.is_purchased else None
    item.purchased_at = datetime.utcnow() if item.is_purchased else None
    db.session.commit()
    return jsonify({"ok": True, "is_purchased": item.is_purchased})


@bp.get("/events/<int:event_id>/wishlists")
@require_auth
def all_wishlists(event_id):
    """Admin: every participant's wishlist (still no purchase info — keeps surprises)."""
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_admin(ev.family_id)
    if err:
        return err
    parts = EventParticipant.query.filter_by(event_id=ev.id, is_participating=True).all()
    out = []
    for p in parts:
        items = (WishlistItem.query.filter_by(event_id=ev.id, user_id=p.user_id)
                 .order_by(WishlistItem.priority).all())
        out.append({"user": p.user.to_dict(),
                    "items": [i.to_dict(include_purchase=False) for i in items]})
    return jsonify(out)
