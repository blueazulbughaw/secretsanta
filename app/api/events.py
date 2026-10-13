import re
from datetime import datetime, date, time

from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import (Event, EventParticipant, FamilyMember, Assignment, WishlistItem,
                      Message, Announcement, EventDish, Notification)
from ..services.photo_service import remove_photo
from ..utils import parse_amount, clean_text, parse_bool, parse_id, json_body, InputError
from ..middleware.auth import (require_auth, require_family_member, require_family_admin, archived_error,
                               require_event_access)

bp = Blueprint("events", __name__)

# Free-text details the clan admin fills in for everyone: max length, label. These
# stay editable after names are drawn; the matching rules below do not.
DETAIL_FIELDS = {"location": (255, "Where"), "theme": (120, "Theme"), "rules": (2000, "Rules"),
                 "what_to_bring": (2000, "What to bring"), "other_info": (2000, "Other info")}
EVENT_NAME_MAX = 120
WISHLIST_LIMIT_RANGE = (1, 20)  # matches the event form's min/max


def _parse_date(raw):
    try:
        d = date.fromisoformat(raw if isinstance(raw, str) else "")
    except ValueError:
        raise InputError("Please choose a date for the event.")
    if not 2000 <= d.year <= 2100:
        raise InputError("Please choose a date for the event.")
    return d


def _parse_currency(raw):
    cur = clean_text(raw, 3, "Currency").upper() or "USD"
    if not re.fullmatch(r"[A-Z]{3}", cur):
        raise InputError("Currency has to be a 3-letter code, like USD.")
    return cur


def _parse_wishlist_limit(raw):
    lo, hi = WISHLIST_LIMIT_RANGE
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)  # JSON 5.0
    try:
        limit = parse_id(raw, "The gift limit")
    except InputError:
        limit = None
    if limit is None or not lo <= limit <= hi:
        raise InputError(f"The gift limit has to be a number from {lo} to {hi}.")
    return limit


def _apply_details(ev, data):
    """Copies the event-details fields present in `data` onto `ev` (raises InputError)."""
    if "event_time" in data:
        raw = clean_text(data.get("event_time"), 8, "Time")
        try:
            ev.event_time = time.fromisoformat(raw) if raw else None
        except ValueError:
            raise InputError("Please choose a valid time for the event.")
    for field, (limit, label) in DETAIL_FIELDS.items():
        if field in data:
            multiline = limit > 255
            setattr(ev, field, clean_text(data.get(field), limit, label, multiline=multiline) or None)


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
    data = json_body()
    name = clean_text(data.get("name"), EVENT_NAME_MAX, "Event name")
    event_date = _parse_date(data.get("event_date"))
    if not name:
        return jsonify({"error": "Please give the event a name."}), 400
    raw_limit = data.get("wishlist_limit")
    ev = Event(
        family_id=family_id, name=name, event_date=event_date,
        budget_amount=parse_amount(data.get("budget_amount"), "gift amount"),
        budget_currency=_parse_currency(data.get("budget_currency")),
        wishlist_limit=5 if raw_limit in (None, "") else _parse_wishlist_limit(raw_limit),
        use_codenames=parse_bool(data.get("use_codenames"), "Codenames"),
        allow_same_household=parse_bool(data.get("allow_same_household"), "Same-household matches"),
        status="open", created_by=g.user.id,
    )
    _apply_details(ev, data)
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
    data = json_body()
    # Once names are drawn the matching rules are locked; when/where/what to
    # bring and the rest of the details can still change.
    rule_fields = ("wishlist_limit", "use_codenames", "allow_same_household")
    if ev.status == "matched" and any(f in data for f in rule_fields):
        return jsonify({"error": "Names are already drawn. Re-draw to change rules."}), 400
    if "name" in data:
        name = clean_text(data.get("name"), EVENT_NAME_MAX, "Event name")
        if not name:
            return jsonify({"error": "Please give the event a name."}), 400
        ev.name = name
    if "event_date" in data:
        ev.event_date = _parse_date(data.get("event_date"))
    if "budget_amount" in data:
        ev.budget_amount = parse_amount(data["budget_amount"], "gift amount")
    if "budget_currency" in data:
        ev.budget_currency = _parse_currency(data["budget_currency"])
    if "wishlist_limit" in data:
        ev.wishlist_limit = _parse_wishlist_limit(data["wishlist_limit"])
    if "use_codenames" in data:
        ev.use_codenames = parse_bool(data["use_codenames"], "Codenames")
    if "allow_same_household" in data:
        ev.allow_same_household = parse_bool(data["allow_same_household"], "Same-household matches")
    _apply_details(ev, data)
    if "game_master_id" in data:
        # The game master is picked from the people joining, and can change after the draw.
        gm = parse_id(data["game_master_id"], "That game master")
        if gm is None:
            ev.game_master_id = None
        else:
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
    photos = purge_event(ev)
    db.session.commit()
    for path in photos:
        remove_photo(path)
    return jsonify({"ok": True})


def purge_event(ev):
    """Deletes an event and everything scoped to it (not yet committed). Returns its gift
    photos' paths, to remove from disk once the commit has gone through. Also used when the
    app admin deletes a whole clan (api/app_admin.py)."""
    photos = [i.photo_path for i in WishlistItem.query.filter_by(event_id=ev.id).all()]
    for model in (Message, Assignment, WishlistItem, EventParticipant, Announcement, EventDish,
                  Notification):
        model.query.filter_by(event_id=ev.id).delete()
    db.session.delete(ev)
    return photos


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
    raw_ids = json_body().get("user_ids", [])
    if not isinstance(raw_ids, list):
        raise InputError("Please choose who's joining from the list.")
    user_ids = {parse_id(u, "That person") for u in raw_ids} - {None}
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
