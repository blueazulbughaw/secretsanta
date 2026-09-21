from datetime import datetime

from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import Event, WishlistItem, Assignment, User, EventParticipant
from ..middleware.auth import require_auth, require_family_member, require_family_admin
from ..services.notification_service import notify
from ..services.photo_service import save_photo, remove_photo
from ..utils import normalize_link_url

bp = Blueprint("wishlists", __name__)


def _my_giftee(event_id):
    a = Assignment.query.filter_by(event_id=event_id, giver_id=g.user.id).first()
    return a.receiver_id if a else None


def _item_dict(item, include_purchase):
    """Like item.to_dict(), plus (when purchase info is included) whether the
    current viewer is the one who bought it - only the buyer can undo a
    purchase, everyone else just sees that it's already been claimed."""
    d = item.to_dict(include_purchase=include_purchase)
    if include_purchase:
        d["bought_by_me"] = item.purchased_by == g.user.id
    return d


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
    data = request.form if request.form else (request.get_json(silent=True) or {})
    name = (data.get("item_name") or "").strip()
    if not name:
        return jsonify({"error": "Please tell us what the gift is."}), 400

    try:
        link_url = normalize_link_url(data.get("link_url")) or None
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    photo_path = None
    photo = request.files.get("photo")
    if photo and photo.filename:
        try:
            photo_path = save_photo(photo, "wishlist")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    item = WishlistItem(
        event_id=ev.id, user_id=g.user.id, item_name=name[:200],
        description=(data.get("description") or "").strip() or None,
        link_url=link_url,
        price_estimate=data.get("price_estimate"),
        priority=int(data.get("priority") or 3),
        photo_path=photo_path,
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
    if item.is_purchased:
        return jsonify({"error": "This gift has already been claimed and can't be changed anymore."}), 403
    data = request.form if request.form else (request.get_json(silent=True) or {})
    if "item_name" in data and not (data.get("item_name") or "").strip():
        return jsonify({"error": "Please tell us what the gift is."}), 400
    link_url = item.link_url
    if "link_url" in data:
        try:
            link_url = normalize_link_url(data.get("link_url")) or None
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    old_photo = None
    photo = request.files.get("photo")
    if photo and photo.filename:
        try:
            new_photo = save_photo(photo, "wishlist")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        old_photo, item.photo_path = item.photo_path, new_photo
    if data.get("item_name"):
        item.item_name = data["item_name"].strip()[:200]
    item.link_url = link_url
    if "description" in data:
        item.description = (data.get("description") or "").strip() or None
    if "price_estimate" in data:
        item.price_estimate = data["price_estimate"]
    if "priority" in data:
        item.priority = int(data["priority"])
    db.session.commit()
    remove_photo(old_photo)  # replaced - drop the old file so uploads don't pile up
    return jsonify({"ok": True, "item": item.to_dict()})


@bp.delete("/wishlists/<int:item_id>")
@require_auth
def delete_item(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    if item.user_id != g.user.id:
        return jsonify({"error": "You can only edit your own list."}), 403
    if item.is_purchased:
        return jsonify({"error": "This gift has already been claimed and can't be removed anymore."}), 403
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
    return jsonify({"items": [_item_dict(i, True) for i in items]})


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
    if item.is_purchased and item.purchased_by != g.user.id:
        return jsonify({"error": "Only the person who bought this can undo it."}), 403
    item.is_purchased = not item.is_purchased
    item.purchased_by = g.user.id if item.is_purchased else None
    item.purchased_at = datetime.utcnow() if item.is_purchased else None
    db.session.commit()
    return jsonify({"ok": True, "is_purchased": item.is_purchased})


@bp.get("/events/<int:event_id>/wishlists/clan")
@require_auth
def clan_wishlists(event_id):
    """Every participating member's wishlist, for the whole family - not just
    the assigned Secret Santa. Purchase status is visible for everyone's
    items except your own, so the clan can coordinate on gifts beyond just
    the one drawn assignment. Owners still never see their own status."""
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_member(ev.family_id)
    if err:
        return err
    parts = EventParticipant.query.filter_by(event_id=ev.id, is_participating=True).all()
    out = []
    for p in parts:
        items = (WishlistItem.query.filter_by(event_id=ev.id, user_id=p.user_id)
                 .order_by(WishlistItem.priority).all())
        out.append({"user": p.user.to_dict(),
                    "items": [_item_dict(i, p.user_id != g.user.id) for i in items]})
    return jsonify(out)


@bp.get("/events/<int:event_id>/wishlists")
@require_auth
def all_wishlists(event_id):
    """Admin: every participant's wishlist. Purchase status visible the same
    way as My Clan (everyone except the item's own owner) so admins can also
    buy/coordinate gifts from here, not just view the lists."""
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
                    "items": [_item_dict(i, p.user_id != g.user.id) for i in items]})
    return jsonify(out)
