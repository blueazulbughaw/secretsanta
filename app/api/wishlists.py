from datetime import datetime

from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import Event, WishlistItem, Assignment, User, EventParticipant, FamilyMember
from ..middleware.auth import require_auth, require_family_member, require_family_admin, archived_error, require_event_access
from ..services.notification_service import notify
from ..services.photo_service import save_photo, remove_photo
from ..utils import normalize_link_url, parse_amount, clean_text, json_body, parse_bool, InputError

bp = Blueprint("wishlists", __name__)


ITEM_NAME_MAX, DESCRIPTION_MAX = 200, 1000


def _form_or_json():
    """Gift forms come as multipart (with a photo) or plain JSON."""
    return request.form if request.form else json_body()


def _item_name(data):
    name = clean_text(data.get("item_name"), ITEM_NAME_MAX, "The gift's name")
    if not name:
        raise InputError("Please tell us what the gift is.")
    return name


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
    _, err = require_event_access(ev)
    if err:
        return err
    items = (WishlistItem.query.filter_by(event_id=ev.id, user_id=g.user.id)
             .order_by(WishlistItem.priority, WishlistItem.id).all())
    # Owner NEVER sees purchase status.
    return jsonify({"items": [i.to_dict(include_purchase=False) for i in items],
                    "limit": ev.wishlist_limit, "archived": ev.status == "completed"})


@bp.post("/events/<int:event_id>/wishlists")
@require_auth
def add_item(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_event_access(ev)
    if err:
        return err
    err = archived_error(ev)
    if err:
        return err
    count = WishlistItem.query.filter_by(event_id=ev.id, user_id=g.user.id).count()
    if count >= ev.wishlist_limit:
        return jsonify({"error": f"Your list is full ({ev.wishlist_limit} gifts). "
                                 "Remove one to add another."}), 400
    data = _form_or_json()
    name = _item_name(data)
    description = clean_text(data.get("description"), DESCRIPTION_MAX, "The description", multiline=True)
    link_url = normalize_link_url(data.get("link_url")) or None
    price = parse_amount(data.get("price_estimate"), "price")

    photo_path = None
    photo = request.files.get("photo")
    if photo and photo.filename:
        try:
            photo_path = save_photo(photo, "wishlist")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    # New gifts go to the bottom of the list; the owner reorders by dragging, and
    # the order is the priority everyone sees.
    last = (db.session.query(db.func.max(WishlistItem.priority))
            .filter_by(event_id=ev.id, user_id=g.user.id).scalar() or 0)
    item = WishlistItem(
        event_id=ev.id, user_id=g.user.id, item_name=name,
        description=description or None,
        link_url=link_url,
        price_estimate=price,
        priority=last + 1,
        photo_path=photo_path,
    )
    db.session.add(item)
    db.session.commit()
    # Nudge their Secret Santa if names are drawn
    giver = Assignment.query.filter_by(event_id=ev.id, receiver_id=g.user.id).first()
    if giver:
        # Their profile shows the wishlist; with codenames on it would name them, so
        # those events go to the reveal page (which shows the codename) instead.
        link = f"/events/{ev.id}/my-person" if ev.use_codenames else f"/events/{ev.id}/clan/{g.user.id}"
        who = g.user.display_name or g.user.full_name
        if ev.use_codenames:
            mine = EventParticipant.query.filter_by(event_id=ev.id, user_id=g.user.id).first()
            who = (mine.codename if mine and mine.codename else "someone")
        notify(giver.giver_id, "wishlist", f"Your giftee {who} added a gift idea",
               "Take a look at their updated wishlist.", link_path=link,
               family_id=ev.family_id, event_id=ev.id)
    return jsonify({"ok": True, "item": item.to_dict()}), 201


@bp.put("/events/<int:event_id>/wishlists/order")
@require_auth
def reorder_wishlist(event_id):
    """Sets the priority of the caller's gifts from the order of `item_ids`
    (first = most wanted). Must list every one of their gifts for this event."""
    ev = Event.query.get_or_404(event_id)
    _, err = require_event_access(ev)
    if err:
        return err
    err = archived_error(ev)
    if err:
        return err
    items = {i.id: i for i in WishlistItem.query.filter_by(event_id=ev.id, user_id=g.user.id).all()}
    ids = json_body().get("item_ids")
    if (not isinstance(ids, list) or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids)
            or len(ids) != len(set(ids)) or set(ids) != set(items)):
        return jsonify({"error": "That list doesn't match your gifts. Please refresh and try again."}), 400
    for position, item_id in enumerate(ids, start=1):
        items[item_id].priority = position
    db.session.commit()
    return jsonify({"ok": True})


@bp.patch("/wishlists/<int:item_id>")
@require_auth
def edit_item(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    if item.user_id != g.user.id:
        return jsonify({"error": "You can only edit your own list."}), 403
    err = archived_error(Event.query.get(item.event_id))
    if err:
        return err
    if item.is_purchased:
        return jsonify({"error": "This gift has already been claimed and can't be changed anymore."}), 403
    data = _form_or_json()
    name = _item_name(data) if "item_name" in data else item.item_name
    description = item.description
    if "description" in data:
        description = clean_text(data.get("description"), DESCRIPTION_MAX, "The description",
                                 multiline=True) or None
    link_url = normalize_link_url(data.get("link_url")) or None if "link_url" in data else item.link_url
    price = parse_amount(data.get("price_estimate"), "price") if "price_estimate" in data else item.price_estimate
    old_photo = None
    photo = request.files.get("photo")
    if photo and photo.filename:
        try:
            new_photo = save_photo(photo, "wishlist")
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        old_photo, item.photo_path = item.photo_path, new_photo
    item.item_name, item.description, item.link_url, item.price_estimate = name, description, link_url, price
    db.session.commit()
    remove_photo(old_photo)  # replaced - drop the old file so uploads don't pile up
    return jsonify({"ok": True, "item": item.to_dict()})


@bp.delete("/wishlists/<int:item_id>")
@require_auth
def delete_item(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    if item.user_id != g.user.id:
        return jsonify({"error": "You can only edit your own list."}), 403
    err = archived_error(Event.query.get(item.event_id))
    if err:
        return err
    if item.is_purchased:
        return jsonify({"error": "This gift has already been claimed and can't be removed anymore."}), 403
    photo = item.photo_path
    db.session.delete(item)
    db.session.commit()
    remove_photo(photo)
    return jsonify({"ok": True})


@bp.post("/wishlists/<int:item_id>/purchase")
@require_auth
def mark_purchased(item_id):
    item = WishlistItem.query.get_or_404(item_id)
    ev = Event.query.get_or_404(item.event_id)
    _, err = require_event_access(ev)
    if err:
        return err
    err = archived_error(ev)
    if err:
        return err
    if item.user_id == g.user.id:
        return jsonify({"error": "You can't mark your own wishlist."}), 403
    # `purchased` says which state the caller wants, so a repeat (double-tap, two tabs)
    # is a no-op rather than flipping it back. No body = toggle, for older cached pages.
    data = json_body()
    want = parse_bool(data["purchased"], "Bought") if "purchased" in data else not item.is_purchased
    if want == item.is_purchased and (not want or item.purchased_by == g.user.id):
        return jsonify({"ok": True, "is_purchased": item.is_purchased})
    if item.is_purchased and item.purchased_by != g.user.id:
        if want:
            return jsonify({"error": "Someone else already bought this one."}), 409
        return jsonify({"error": "Only the person who bought this can undo it."}), 403
    item.is_purchased = want
    item.purchased_by = g.user.id if want else None
    item.purchased_at = datetime.utcnow() if want else None
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
    _, err = require_event_access(ev)
    if err:
        return err
    parts = EventParticipant.query.filter_by(event_id=ev.id, is_participating=True).all()
    households = {m.user_id: (m.household.name if m.household else "")
                  for m in FamilyMember.query.filter_by(family_id=ev.family_id).all()}
    out = []
    for p in parts:
        items = (WishlistItem.query.filter_by(event_id=ev.id, user_id=p.user_id)
                 .order_by(WishlistItem.priority, WishlistItem.id).all())
        out.append({"user": p.user.clan_dict(), "household_name": households.get(p.user_id, ""),
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
    households = {m.user_id: (m.household.name if m.household else "")
                  for m in FamilyMember.query.filter_by(family_id=ev.family_id).all()}
    out = []
    for p in parts:
        items = (WishlistItem.query.filter_by(event_id=ev.id, user_id=p.user_id)
                 .order_by(WishlistItem.priority, WishlistItem.id).all())
        out.append({"user": p.user.clan_dict(), "household_name": households.get(p.user_id, ""),
                    "items": [_item_dict(i, p.user_id != g.user.id) for i in items]})
    return jsonify(out)
