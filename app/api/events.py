from datetime import datetime, date

from flask import Blueprint, request, jsonify, g

from ..extensions import db
from ..models import Event, EventParticipant, FamilyMember
from ..middleware.auth import require_auth, require_family_member, require_family_admin

bp = Blueprint("events", __name__)


def _event_and_membership(event_id):
    ev = Event.query.get_or_404(event_id)
    m, err = require_family_member(ev.family_id)
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
    db.session.add(ev)
    db.session.commit()
    return jsonify({"ok": True, "event": ev.to_dict()}), 201


@bp.get("/families/<int:family_id>/events")
@require_auth
def list_events(family_id):
    _, err = require_family_member(family_id)
    if err:
        return err
    evs = (Event.query.filter_by(family_id=family_id)
           .order_by(Event.event_date.desc()).all())
    out = []
    for ev in evs:
        d = ev.to_dict()
        d["i_am_participating"] = EventParticipant.query.filter_by(
            event_id=ev.id, user_id=g.user.id, is_participating=True).first() is not None
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
    if ev.status == "matched":
        return jsonify({"error": "Names are already drawn. Re-draw to change rules."}), 400
    data = request.json or {}
    for field in ("name",):
        if data.get(field):
            setattr(ev, field, data[field][:120])
    if data.get("event_date"):
        ev.event_date = date.fromisoformat(data["event_date"])
    for field in ("budget_amount", "wishlist_limit"):
        if field in data:
            setattr(ev, field, data[field])
    for field in ("use_codenames", "allow_same_household"):
        if field in data:
            setattr(ev, field, bool(data[field]))
    db.session.commit()
    return jsonify({"ok": True, "event": ev.to_dict()})


@bp.get("/events/<int:event_id>/participants")
@require_auth
def list_participants(event_id):
    ev, m, err = _event_and_membership(event_id)
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
    db.session.commit()
    return jsonify({"ok": True, "count": len(user_ids)})


@bp.post("/events/<int:event_id>/participants/opt-out")
@require_auth
def opt_out(event_id):
    ev, _, err = _event_and_membership(event_id)
    if err:
        return err
    if ev.status == "matched":
        return jsonify({"error": "Names are already drawn — please talk to your organizer."}), 400
    p = EventParticipant.query.filter_by(event_id=ev.id, user_id=g.user.id).first()
    if p:
        p.is_participating = False
        p.opted_out_at = datetime.utcnow()
        db.session.commit()
    return jsonify({"ok": True})
