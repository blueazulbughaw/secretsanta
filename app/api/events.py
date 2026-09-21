from datetime import datetime, date, time

from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import (Event, EventParticipant, FamilyMember, Assignment, WishlistItem,
                      Message, Announcement, EventDish)
from ..services.photo_service import remove_photo
from ..middleware.auth import (require_auth, require_family_member, require_family_admin, archived_error,
                               require_event_access)

bp = Blueprint("events", __name__)

# Free-text details the clan admin fills in for everyone (max lengths). These
# stay editable after names are drawn; the matching rules below do not.
DETAIL_TEXT_LIMITS = {"location": 255, "theme": 120, "rules": 2000,
                      "what_to_bring": 2000, "other_info": 2000}


def _apply_details(ev, data):
    """Copies the event-details fields present in `data` onto `ev`. Returns an
    error message for a bad time, else None."""
    if "event_time" in data:
        raw = str(data.get("event_time") or "").strip()
        if not raw:
            ev.event_time = None
        else:
            try:
                ev.event_time = time.fromisoformat(raw)
            except ValueError:
                return "Please choose a valid time for the event."
    for field, limit in DETAIL_TEXT_LIMITS.items():
        if field in data:
            setattr(ev, field, str(data.get(field) or "").strip()[:limit] or None)
    return None


def _event_and_membership(event_id):
    ev = Event.query.get_or_404(event_id)
    m, err = require_event_access(ev)
    return ev, m, err


@bp.post("/families/<int:family_id>/events")
@require_auth
def create_event(family_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    data = request.json or {}
    name = (data.get("name") or "").strip()
    try:
        event_date = date.fromisoformat(data.get("event_date", ""))
    except ValueError:
        return jsonify({"error": "Please choose a date for the event."}), 400
    if not name:
        return jsonify({"error": "Please give the event a name."}), 400
    ev = Event(
        family_id=family_id, name=name[:120], event_date=event_date,
        budget_amount=data.get("budget_amount"),
        budget_currency=(data.get("budget_currency") or "USD")[:3].upper(),
        wishlist_limit=int(data.get("wishlist_limit") or 5),
        use_codenames=bool(data.get("use_codenames")),
        allow_same_household=bool(data.get("allow_same_household")),
        status="open", created_by=g.user.id,
    )
    bad_time = _apply_details(ev, data)
    if bad_time:
        return jsonify({"error": bad_time}), 400
    db.session.add(ev)
    db.session.commit()
    return jsonify({"ok": True, "event": ev.to_dict()}), 201


@bp.get("/families/<int:family_id>/events")
@require_auth
def list_events(family_id):
    m, err = require_family_member(family_id)
    if err:
        return err
    evs = (Event.query.filter_by(family_id=family_id)
           .order_by(Event.event_date.desc()).all())
    out = []
    for ev in evs:
        d = ev.to_dict()
        d["i_am_participating"] = EventParticipant.query.filter_by(
            event_id=ev.id, user_id=g.user.id, is_participating=True).first() is not None
        if m.role != "admin" and not d["i_am_participating"]:
            continue  # members only see the events they're in; clan admins see them all
        # Each event has its own set of participants (and so its own giftee/gifter pairs)
        d["participant_count"] = EventParticipant.query.filter_by(
            event_id=ev.id, is_participating=True).count()
        out.append(d)
    return jsonify(out)


@bp.get("/events/<int:event_id>")
@require_auth
def get_event(event_id):
    ev, m, err = _event_and_membership(event_id)
    if err:
        return err
    d = ev.to_dict()
    d["my_role"] = m.role
    d["i_am_participating"] = EventParticipant.query.filter_by(
        event_id=ev.id, user_id=g.user.id, is_participating=True).first() is not None
    return jsonify(d)


@bp.patch("/events/<int:event_id>")
@require_auth
def update_event(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_admin(ev.family_id)
    if err:
        return err
    err = archived_error(ev)
    if err:
        return err
    data = request.json or {}
    # Once names are drawn the matching rules are locked; when/where/what to
    # bring and the rest of the details can still change.
    rule_fields = ("wishlist_limit", "use_codenames", "allow_same_household")
    if ev.status == "matched" and any(f in data for f in rule_fields):
        return jsonify({"error": "Names are already drawn. Re-draw to change rules."}), 400
    if data.get("name"):
        ev.name = data["name"][:120]
    if data.get("event_date"):
        try:
            ev.event_date = date.fromisoformat(data["event_date"])
        except ValueError:
            return jsonify({"error": "Please choose a date for the event."}), 400
    for field in ("budget_amount", "wishlist_limit"):
        if field in data:
            setattr(ev, field, data[field])
    for field in ("use_codenames", "allow_same_household"):
        if field in data:
            setattr(ev, field, bool(data[field]))
    bad_time = _apply_details(ev, data)
    if bad_time:
        return jsonify({"error": bad_time}), 400
    if "game_master_id" in data:
        # The game master is picked from the people joining, and can change after the draw.
        raw = data["game_master_id"]
        if raw in (None, ""):
            ev.game_master_id = None
        else:
            try:
                gm = int(raw)
            except (TypeError, ValueError):
                return jsonify({"error": "Please choose the game master from the list."}), 400
            if not EventParticipant.query.filter_by(event_id=ev.id, user_id=gm,
                                                    is_participating=True).first():
                return jsonify({"error": "The game master has to be someone who's joining "
                                         "this event."}), 400
            ev.game_master_id = gm
    db.session.commit()
    return jsonify({"ok": True, "event": ev.to_dict()})


@bp.delete("/events/<int:event_id>")
@require_auth
def delete_event(event_id):
    """Permanently removes an event, however old or archived, and everything scoped
    to it: who's joining, the name draw, wishlists (and their photos), messages,
    dishes and its announcements."""
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_admin(ev.family_id)
    if err:
        return err
    photos = [i.photo_path for i in WishlistItem.query.filter_by(event_id=ev.id).all()]
    for model in (Message, Assignment, WishlistItem, EventParticipant, Announcement, EventDish):
        model.query.filter_by(event_id=ev.id).delete()
    db.session.delete(ev)
    db.session.commit()
    for path in photos:
        remove_photo(path)
    return jsonify({"ok": True})


@bp.post("/events/<int:event_id>/complete")
@require_auth
def complete_event(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_admin(ev.family_id)
    if err:
        return err
    if ev.status == "completed":
        return jsonify({"error": "This event is already marked done."}), 400
    ev.status = "completed"
    db.session.commit()
    return jsonify({"ok": True, "event": ev.to_dict()})


@bp.get("/events/<int:event_id>/attendees")
@require_auth
def list_attendees(event_id):
    """Who's coming, for any clan member: profile-safe fields only (no phone or
    email), sorted by name."""
    ev, _, err = _event_and_membership(event_id)
    if err:
        return err
    parts = EventParticipant.query.filter_by(event_id=ev.id, is_participating=True).all()
    members = {m.user_id: m for m in FamilyMember.query.filter_by(family_id=ev.family_id).all()}
    people = []
    for p in parts:
        person = p.user.public_dict()
        m = members.get(p.user_id)
        person["household_name"] = m.household.name if m and m.household else ""
        people.append(person)
    return jsonify(sorted(people, key=lambda u: u["display_name"].lower()))


@bp.get("/events/<int:event_id>/participants")
@require_auth
def list_participants(event_id):
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_admin(ev.family_id)
    if err:
        return err
    members = FamilyMember.query.filter_by(family_id=ev.family_id).all()
    checked = {p.user_id: p for p in EventParticipant.query.filter_by(event_id=ev.id).all()}
    return jsonify([{
        "user": mem.user.to_dict(),
        "household_id": mem.household_id,
        "household_name": mem.household.name if mem.household else None,
        "is_participating": (checked.get(mem.user_id).is_participating
                             if mem.user_id in checked else False),
    } for mem in members])


@bp.put("/events/<int:event_id>/participants")
@require_auth
def set_participants(event_id):
    """The admin checkbox screen: send the full list of participating user_ids."""
    ev = Event.query.get_or_404(event_id)
    _, err = require_family_admin(ev.family_id)
    if err:
        return err
    err = archived_error(ev)
    if err:
        return err
    if ev.status == "matched":
        return jsonify({"error": "Names are already drawn. Re-draw to change who's in."}), 400
    user_ids = set((request.json or {}).get("user_ids", []))
    valid_ids = {m.user_id for m in FamilyMember.query.filter_by(family_id=ev.family_id).all()}
    bad = user_ids - valid_ids
    if bad:
        return jsonify({"error": "Some selected people are not in this family."}), 400

    existing = {p.user_id: p for p in EventParticipant.query.filter_by(event_id=ev.id).all()}
    for uid in user_ids:
        if uid in existing:
            existing[uid].is_participating = True
            existing[uid].opted_out_at = None
        else:
            db.session.add(EventParticipant(event_id=ev.id, user_id=uid))
    for uid, p in existing.items():
        if uid not in user_ids:
            p.is_participating = False
    if ev.game_master_id and ev.game_master_id not in user_ids:
        ev.game_master_id = None  # the game master must be someone who's joining
    db.session.commit()
    return jsonify({"ok": True, "count": len(user_ids)})


@bp.post("/events/<int:event_id>/participants/opt-out")
@require_auth
def opt_out(event_id):
    ev, _, err = _event_and_membership(event_id)
    if err:
        return err
    err = archived_error(ev)
    if err:
        return err
    if ev.status == "matched":
        return jsonify({"error": "Names are already drawn — please talk to your organizer."}), 400
    p = EventParticipant.query.filter_by(event_id=ev.id, user_id=g.user.id).first()
    if p:
        p.is_participating = False
        p.opted_out_at = datetime.utcnow()
        if ev.game_master_id == g.user.id:
            ev.game_master_id = None
        db.session.commit()
    return jsonify({"ok": True})
