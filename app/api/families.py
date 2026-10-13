import secrets
import string

import io

from flask import Blueprint, Response, request, jsonify, g, current_app

from ..extensions import db
from ..models import Family, FamilyMember, Household, User, Event, EventParticipant, JoinRequest
from ..middleware.auth import require_auth, require_family_member, require_family_admin
from ..services import otp_service
from ..services.notification_service import notify
from ..utils import (normalize_phone, normalize_username, hash_password, slugify_username_base,
                     clean_text, normalize_email, parse_id, json_body, InputError)

bp = Blueprint("families", __name__)


CLAN_NAME_MAX = 120
DISPLAY_NAME_MAX = 120


def _clean_join_code(raw):
    code = clean_text(raw, 20, "Clan code").replace(" ", "").upper()
    if not code.isalnum() or len(code) != 8:
        raise InputError("A clan code is 8 letters and numbers. Please check it and try again.")
    return code


def _household_id(raw, family_id):
    """A household choice for this clan: None for no household, else its id."""
    hid = parse_id(raw, "That household")
    if hid is not None and not Household.query.filter_by(id=hid, family_id=family_id).first():
        raise InputError("That household doesn't exist in this clan.")
    return hid


def _make_join_code():
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(secrets.choice(alphabet) for _ in range(8))
        if not Family.query.filter_by(join_code=code).first():
            return code


@bp.get("/families/lookup-code/<code>")
def lookup_join_code(code):
    """The one deliberately unauthenticated endpoint in this file - used by the "Join a
    Clan" screen before an account exists, so someone can see which clan a code belongs
    to and confirm it's the right one before creating an account tied to it. Only ever
    returns a name, never a member list or anything else, and the code space (8 random
    letters/digits, ~2.8 trillion combinations) makes it impractical to guess - but it's
    still reachable with zero prior knowledge, so it gets the same IP rate limit as
    /auth/send-code for the same reason (see enforce_ip_rate_limit's docstring)."""
    try:
        otp_service.enforce_ip_rate_limit(request.remote_addr or "unknown")
    except ValueError as e:
        return jsonify({"error": str(e)}), 429
    try:
        code = _clean_join_code(code)
    except InputError:
        code = ""
    fam = Family.query.filter_by(join_code=code).first() if code else None
    if not fam:
        return jsonify({"error": "That clan code isn't valid. Please check it and try again."}), 404
    return jsonify({"name": fam.name})


@bp.post("/families")
@require_auth
def create_family():
    has_family = FamilyMember.query.filter_by(user_id=g.user.id).first() is not None
    if has_family and not g.user.is_app_admin:
        return jsonify({"error": "Ask your clan admin for a join code instead."}), 403
    name = clean_text(json_body().get("name"), CLAN_NAME_MAX, "Clan name")
    if not name:
        return jsonify({"error": "Please give your family group a name."}), 400
    fam = Family(name=name, join_code=_make_join_code(), created_by=g.user.id)
    db.session.add(fam)
    db.session.flush()
    db.session.add(FamilyMember(family_id=fam.id, user_id=g.user.id, role="admin"))
    db.session.commit()
    return jsonify({"ok": True, "family": {"id": fam.id, "name": fam.name,
                                           "join_code": fam.join_code}}), 201


@bp.post("/families/join")
@require_auth
def join_family():
    code = _clean_join_code(json_body().get("join_code"))
    fam = Family.query.filter_by(join_code=code).first()
    if not fam:
        return jsonify({"error": "We couldn't find a family with that code."}), 404
    info = {"id": fam.id, "name": fam.name}
    if FamilyMember.query.filter_by(family_id=fam.id, user_id=g.user.id).first():
        return jsonify({"ok": True, "family": info, "pending": False,
                        "message": "You're already in this clan."})
    # A code alone doesn't let anyone in: a clan admin approves them first, so a code that
    # got passed around (or someone who picked the wrong clan) can't see the family.
    waiting = {"ok": True, "family": info, "pending": True,
               "message": f"You've asked to join {fam.name}. Your clan admin will let you in."}
    if JoinRequest.query.filter_by(family_id=fam.id, user_id=g.user.id).first():
        return jsonify(waiting)
    db.session.add(JoinRequest(family_id=fam.id, user_id=g.user.id))
    db.session.commit()
    who = g.user.display_name or g.user.full_name or g.user.username
    for admin in FamilyMember.query.filter_by(family_id=fam.id, role="admin").all():
        notify(admin.user_id, "join_request", f"{who} wants to join {fam.name}",
               "Approve or decline them on the Members page.", "/admin/members")
    return jsonify(waiting), 201


@bp.get("/families/<int:family_id>/join-requests")
@require_auth
def list_join_requests(family_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    reqs = JoinRequest.query.filter_by(family_id=family_id).order_by(JoinRequest.created_at).all()
    return jsonify([{"id": r.id, "user": {"id": r.user.id, "username": r.user.username,
                                          "display_name": r.user.display_name or r.user.full_name},
                     "created_at": r.created_at.isoformat()} for r in reqs])


def _join_request(family_id, request_id):
    return JoinRequest.query.filter_by(id=request_id, family_id=family_id).first_or_404()


@bp.post("/families/<int:family_id>/join-requests/<int:request_id>/approve")
@require_auth
def approve_join_request(family_id, request_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    req = _join_request(family_id, request_id)
    fam = Family.query.get(family_id)
    user_id = req.user_id
    if not FamilyMember.query.filter_by(family_id=family_id, user_id=user_id).first():
        db.session.add(FamilyMember(family_id=family_id, user_id=user_id, role="member"))
    db.session.delete(req)
    db.session.commit()
    notify(user_id, "join_approved", f"You're in {fam.name}!", None, "/")
    return jsonify({"ok": True})


@bp.post("/families/<int:family_id>/join-requests/<int:request_id>/decline")
@require_auth
def decline_join_request(family_id, request_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    req = _join_request(family_id, request_id)
    db.session.delete(req)
    db.session.commit()
    return jsonify({"ok": True})


@bp.get("/families/<int:family_id>/join-qr.png")
@require_auth
def join_qr(family_id):
    """A QR code of the clan's registration link (/join/CODE), for the clan admin to share
    or print. Made fresh each time, so it always matches the current code."""
    _, err = require_family_admin(family_id)
    if err:
        return err
    import qrcode
    fam = Family.query.get_or_404(family_id)
    qr = qrcode.QRCode(border=2, box_size=12, error_correction=qrcode.constants.ERROR_CORRECT_M)
    base = request.host_url
    # The live site is HTTPS-only, but behind the host's web server Flask can see plain http
    if not (current_app.debug or current_app.testing):
        base = "https://" + base.split("://", 1)[1]
    qr.add_data(f"{base}join/{fam.join_code}")
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, "PNG")
    # Plain bytes, not send_file(): the live server's LiteSpeed WSGI tries to stream a
    # file-like body via fileno(), which an in-memory buffer doesn't have (500 there).
    return Response(buf.getvalue(), mimetype="image/png", headers={"Cache-Control": "no-store"})


@bp.post("/families/<int:family_id>/join-code")
@require_auth
def new_join_code(family_id):
    """Replaces the clan's code (e.g. it got passed around). The old code stops working;
    nobody already in the clan is affected."""
    _, err = require_family_admin(family_id)
    if err:
        return err
    fam = Family.query.get_or_404(family_id)
    fam.join_code = _make_join_code()
    db.session.commit()
    return jsonify({"ok": True, "join_code": fam.join_code})


@bp.get("/families/<int:family_id>")
@require_auth
def get_family(family_id):
    m, err = require_family_member(family_id)
    if err:
        return err
    fam = Family.query.get_or_404(family_id)
    return jsonify({"id": fam.id, "name": fam.name, "my_role": m.role,
                    "join_code": fam.join_code if m.role == "admin" else None})


@bp.patch("/families/<int:family_id>/my-household")
@require_auth
def update_my_household(family_id):
    """Self-service: unlike every other field on a membership (role, name, username...),
    which household someone's in is fine for them to set themselves - it's not sensitive
    and the clan admin already can't see anything about a member they couldn't already.
    Everything else on the Members table stays admin-only (see update_member)."""
    m, err = require_family_member(family_id)
    if err:
        return err
    m.household_id = _household_id(json_body().get("household_id"), family_id)
    db.session.commit()
    return jsonify({"ok": True, "household_id": m.household_id,
                    "household_name": m.household.name if m.household else None})


@bp.patch("/families/<int:family_id>")
@require_auth
def rename_family(family_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    fam = Family.query.get_or_404(family_id)
    name = clean_text(json_body().get("name"), CLAN_NAME_MAX, "Clan name")
    if not name:
        return jsonify({"error": "Please give your clan a name."}), 400
    fam.name = name
    db.session.commit()
    return jsonify({"ok": True, "family": {"id": fam.id, "name": fam.name}})


@bp.get("/families/<int:family_id>/members")
@require_auth
def list_members(family_id):
    m, err = require_family_member(family_id)
    if err:
        return err
    members = FamilyMember.query.filter_by(family_id=family_id).all()
    # Phone, email and username are for the clan admin's Members page only.
    is_admin = m.role == "admin"
    return jsonify([{
        "membership_id": mem.id,
        "user": mem.user.to_dict() if is_admin else mem.user.clan_dict(),
        "role": mem.role,
        "household_id": mem.household_id,
        "household_name": mem.household.name if mem.household else None,
    } for mem in members])


@bp.post("/families/<int:family_id>/members")
@require_auth
def add_member(family_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    data = json_body()
    full_name = clean_text(data.get("full_name"), DISPLAY_NAME_MAX, "Display name")
    if not full_name:
        return jsonify({"error": "Please enter their name."}), 400

    email = normalize_email(data.get("email"))
    if email and User.query.filter(db.func.lower(User.email) == email).first():
        return jsonify({"error": "That email is already in use."}), 409

    phone = None
    if data.get("phone"):
        phone = normalize_phone(data.get("phone"), data.get("phone_country", "US"))
        if User.query.filter_by(phone=phone).first():
            return jsonify({"error": "That phone number is already in use."}), 409

    wanted = clean_text(data.get("username"), 60, "Username")
    if wanted:
        username = normalize_username(wanted)
        if User.query.filter_by(username=username).first():
            return jsonify({"error": "That username is already taken."}), 409
        if username == full_name:
            return jsonify({"error": "The display name should be different from the username."}), 400
    else:
        # No username given: make one from the display name (never identical to it)
        base = slugify_username_base(full_name)
        username = base
        n = 1
        while username == full_name or User.query.filter_by(username=username).first():
            n += 1
            username = f"{base}{n}"

    household_id = _household_id(data.get("household_id"), family_id)
    role = data.get("role") or "member"
    if role not in ("admin", "member"):
        return jsonify({"error": "Role must be admin or member."}), 400

    temp_password = secrets.token_urlsafe(6)
    user = User(username=username, full_name=full_name, email=email or None, phone=phone,
                password_hash=hash_password(temp_password), must_change_password=True)
    db.session.add(user)
    db.session.flush()
    mem = FamilyMember(family_id=family_id, user_id=user.id, role=role, household_id=household_id)
    db.session.add(mem)
    db.session.flush()
    db.session.commit()
    return jsonify({"ok": True, "user": user.to_dict(), "membership_id": mem.id,
                    "role": mem.role, "household_id": mem.household_id,
                    "username": username, "temp_password": temp_password}), 201


@bp.patch("/families/<int:family_id>/members/<int:membership_id>")
@require_auth
def update_member(family_id, membership_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    mem = FamilyMember.query.filter_by(id=membership_id, family_id=family_id).first_or_404()
    data = json_body()
    if "role" in data:
        if data["role"] not in ("admin", "member"):
            return jsonify({"error": "Role must be admin or member."}), 400
        # Don't allow removing the last admin
        if mem.role == "admin" and data["role"] == "member":
            admins = FamilyMember.query.filter_by(family_id=family_id, role="admin").count()
            if admins <= 1:
                return jsonify({"error": "A family needs at least one clan admin."}), 400
        mem.role = data["role"]
    if "household_id" in data:
        mem.household_id = _household_id(data["household_id"], family_id)
    new_name, new_username = mem.user.full_name, mem.user.username
    if "full_name" in data:
        new_name = clean_text(data.get("full_name"), DISPLAY_NAME_MAX, "Display name")
        if not new_name:
            return jsonify({"error": "Name can't be empty."}), 400
    if "username" in data:
        new_username = normalize_username(data.get("username"))
        if new_username != mem.user.username and User.query.filter_by(username=new_username).first():
            return jsonify({"error": "That username is already taken."}), 409
    # A display name can't just be the username - checked whenever either one changes, so an
    # older account that already has them equal can still be saved untouched.
    if (new_name != mem.user.full_name or new_username != mem.user.username) and new_name == new_username:
        return jsonify({"error": "A display name should be different from the username."}), 400
    mem.user.full_name, mem.user.username = new_name, new_username
    if "email" in data:
        email = normalize_email(data.get("email"))
        if email:
            existing = User.query.filter(db.func.lower(User.email) == email).first()
            if existing and existing.id != mem.user_id:
                return jsonify({"error": "That email is already in use."}), 409
        mem.user.email = email or None
    if "phone" in data:
        raw = data.get("phone") or ""
        if raw:
            phone = normalize_phone(raw, data.get("phone_country", "US"))
            existing = User.query.filter_by(phone=phone).first()
            if existing and existing.id != mem.user_id:
                return jsonify({"error": "That phone number is already in use."}), 409
        else:
            phone = None
        mem.user.phone = phone
    db.session.commit()
    return jsonify({"ok": True})


@bp.post("/families/<int:family_id>/members/<int:membership_id>/reset-password")
@require_auth
def reset_member_password(family_id, membership_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    mem = FamilyMember.query.filter_by(id=membership_id, family_id=family_id).first_or_404()
    temp_password = secrets.token_urlsafe(6)
    mem.user.password_hash = hash_password(temp_password)
    mem.user.must_change_password = True
    mem.user.session_version = (mem.user.session_version or 0) + 1  # sign out their devices
    db.session.commit()
    return jsonify({"ok": True, "temp_password": temp_password})


@bp.delete("/families/<int:family_id>/members/<int:membership_id>")
@require_auth
def remove_member(family_id, membership_id):
    _, err = require_family_admin(family_id)
    if err:
        return err
    mem = FamilyMember.query.filter_by(id=membership_id, family_id=family_id).first_or_404()
    if mem.user_id == g.user.id:
        return jsonify({"error": "You can't remove yourself. Ask another clan admin."}), 400
    # Someone in a draw that's still going can't just vanish: their giftee would be left
    # with no Secret Santa, and their Santa with nobody to give to.
    joining = (EventParticipant.query.join(Event, Event.id == EventParticipant.event_id)
               .filter(Event.family_id == family_id, Event.status != "completed",
                       EventParticipant.user_id == mem.user_id,
                       EventParticipant.is_participating.is_(True)).all())
    drawn = [Event.query.get(p.event_id) for p in joining]
    drawn = [ev for ev in drawn if ev.status == "matched"]
    if drawn:
        name = mem.user.display_name or mem.user.full_name
        return jsonify({"error": f"{name} is in the name draw for {', '.join(ev.name for ev in drawn)}. "
                                 "Start over (re-draw names) without them, or archive the event, "
                                 "before removing them."}), 400
    for p in joining:  # events that haven't drawn names yet: just take them off the list
        p.is_participating = False
        ev = Event.query.get(p.event_id)
        if ev.game_master_id == mem.user_id:
            ev.game_master_id = None
    mem.user.session_version = (mem.user.session_version or 0) + 1  # sign them out
    db.session.delete(mem)
    db.session.commit()
    return jsonify({"ok": True})
