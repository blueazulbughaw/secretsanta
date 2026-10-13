from flask import Blueprint, jsonify, g

from ..extensions import db
from ..models import (User, Family, FamilyMember, Household, Event, EventParticipant, Assignment,
                      EventDish, WishlistItem, Message, Announcement, Notification,
                      PushSubscription, OtpCode)
from ..middleware.auth import require_auth
from ..services.photo_service import remove_photo
from .events import purge_event

bp = Blueprint("app_admin", __name__)


def _require_app_admin():
    """The app admin (User.is_app_admin, not a clan role). Returns the response to send, or None."""
    if not g.user.is_app_admin:
        return jsonify({"error": "Only the app admin can do this."}), 403
    return None


def _person(user, membership=None):
    return {
        "user_id": user.id,
        "display_name": user.display_name or user.full_name,
        "username": user.username,
        "household_name": membership.household.name if membership and membership.household else None,
        "role": membership.role if membership else None,
        "is_active": user.is_active,
    }


@bp.get("/app-admin/clans")
@require_auth
def all_clans():
    """The app admin's overview: every clan with its members, who its clan admins are, and
    how many events it has, plus the accounts that aren't in any clan (e.g. left behind
    when a test clan was deleted). It never includes anything about a draw - who drew whom
    stays secret from every admin."""
    err = _require_app_admin()
    if err:
        return err
    clans = []
    for fam in Family.query.order_by(Family.name).all():
        members = FamilyMember.query.filter_by(family_id=fam.id).all()
        people = sorted((_person(m.user, m) for m in members),
                        key=lambda p: (p["role"] != "admin", p["display_name"].lower()))
        clans.append({
            "id": fam.id,
            "name": fam.name,
            "join_code": fam.join_code,
            "created_at": fam.created_at.isoformat() if fam.created_at else None,
            "event_count": Event.query.filter_by(family_id=fam.id).count(),
            "members": people,
        })
    in_a_clan = db.session.query(FamilyMember.user_id)
    no_clan = (User.query.filter(~User.id.in_(in_a_clan), User.is_app_admin.is_(False))
               .order_by(User.full_name).all())
    return jsonify({"clans": clans, "no_clan": [_person(u) for u in no_clan]})


@bp.delete("/app-admin/clans/<int:family_id>")
@require_auth
def delete_clan(family_id):
    """Permanently deletes a clan and everything in it: its events (draws, wishlists and
    photos, messages, dishes), announcements, households and memberships. The people's
    accounts stay; anyone left in no clan shows under "Not in any clan"."""
    err = _require_app_admin()
    if err:
        return err
    fam = Family.query.get_or_404(family_id)
    photos = []
    for ev in Event.query.filter_by(family_id=fam.id).all():
        photos += purge_event(ev)
    for model in (Announcement, FamilyMember, Household):
        model.query.filter_by(family_id=fam.id).delete()
    db.session.delete(fam)
    db.session.commit()
    for path in photos:
        remove_photo(path)
    return jsonify({"ok": True})


@bp.delete("/app-admin/users/<int:user_id>")
@require_auth
def delete_user(user_id):
    """Permanently deletes someone's account, from every clan they're in, with their
    wishlists, messages, dishes and profile photo. Refused while it would break something
    still going: a name draw they're in, or a clan they're the only clan admin of."""
    err = _require_app_admin()
    if err:
        return err
    user = User.query.get_or_404(user_id)
    name = user.display_name or user.full_name or user.username
    if user.is_app_admin:
        return jsonify({"error": "The app admin account can't be deleted here."}), 400

    drawn = (Event.query.join(EventParticipant, EventParticipant.event_id == Event.id)
             .filter(EventParticipant.user_id == user.id, EventParticipant.is_participating.is_(True),
                     Event.status == "matched").all())
    if drawn:
        return jsonify({"error": f"{name} is in the name draw for {', '.join(e.name for e in drawn)}. "
                                 "Delete or archive that event (or its whole clan) first."}), 400
    for m in FamilyMember.query.filter_by(user_id=user.id, role="admin").all():
        others = FamilyMember.query.filter(FamilyMember.family_id == m.family_id,
                                           FamilyMember.role == "admin",
                                           FamilyMember.user_id != user.id).count()
        if not others:
            fam = Family.query.get(m.family_id)
            return jsonify({"error": f"{name} is the only clan admin of {fam.name}. Delete that "
                                     "clan first, or make someone else its clan admin."}), 400

    # Things they made that belong to the clan, not to them, are handed to the app admin
    Family.query.filter_by(created_by=user.id).update({"created_by": g.user.id})
    Event.query.filter_by(created_by=user.id).update({"created_by": g.user.id})
    Event.query.filter_by(game_master_id=user.id).update({"game_master_id": None})
    WishlistItem.query.filter_by(purchased_by=user.id).update({"purchased_by": None})

    photos = [i.photo_path for i in WishlistItem.query.filter_by(user_id=user.id).all()]
    photos.append(user.photo_path)
    Message.query.filter((Message.sender_id == user.id) | (Message.recipient_id == user.id)).delete()
    Assignment.query.filter((Assignment.giver_id == user.id)
                            | (Assignment.receiver_id == user.id)).delete()
    for model in (WishlistItem, EventDish, EventParticipant, Notification, PushSubscription,
                  FamilyMember):
        model.query.filter_by(user_id=user.id).delete()
    Announcement.query.filter_by(author_id=user.id).delete()
    if user.phone:
        OtpCode.query.filter_by(phone=user.phone).delete()
    db.session.delete(user)
    db.session.commit()
    for path in photos:
        remove_photo(path)
    return jsonify({"ok": True})
