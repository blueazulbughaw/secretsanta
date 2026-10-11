from datetime import datetime

from flask import Blueprint, request, jsonify, make_response, g

from ..extensions import db
from ..models import User, FamilyMember, Family
from ..services import otp_service, sms_service
from ..services.photo_service import save_photo, remove_photo
from ..middleware.auth import (issue_token, set_auth_cookie, clear_auth_cookie,
                               require_auth, _current_user)
from ..utils import (normalize_phone, normalize_username, hash_password, verify_password,
                     check_new_password, clean_text, normalize_email, parse_colors, json_body)

bp = Blueprint("auth", __name__)


@bp.post("/auth/login-start")
def login_start():
    username = normalize_username(json_body().get("username"))
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"ok": True, "exists": False})
    # Only reports what sign-in options exist. It never sends a text: that only happens
    # when the person asks for one (POST /auth/send-code).
    if not user.phone and not user.password_hash:
        return jsonify({"error": "This account has no sign-in method set up yet. Contact an admin."}), 400
    return jsonify({"ok": True, "exists": True, "has_phone": bool(user.phone),
                    "has_password": bool(user.password_hash)})


NO_ACCOUNT_MESSAGE = "That phone number isn't on an account. Please contact your Clan Admin."
CODE_SENT_MESSAGE = "We've texted a sign-in code to that number."
# The IP-rate-limited branch below deliberately answers with this same message - see why
# in the enforce_ip_rate_limit() docstring and the function comment above.


@bp.post("/auth/send-code")
def send_code():
    """Texts a one-time sign-in code to whichever account has this phone number, on request.
    Phone-first by design (no username needed): a family member who's forgotten their
    password - the whole reason this exists - still remembers their own phone number, so
    this is the account-recovery-proof path, not gated behind recalling anything else.

    Does say whether the number matches an account (NO_ACCOUNT_MESSAGE vs. a real send) -
    a deliberate choice, not an oversight: this app is a small trusted family group, and
    "that number isn't on file, ask your Clan Admin" is worth more than the enumeration
    protection it costs. The IP rate limit below is the one case that still answers
    generically - whether a requester is being throttled is a separate, lower-stakes kind
    of information than whose phone numbers are in the system."""
    data = json_body()
    # A bad format is about their input, not account existence.
    phone = normalize_phone(data.get("phone"), data.get("phone_country", "US"))
    try:
        otp_service.enforce_ip_rate_limit(request.remote_addr or "unknown")
    except ValueError:
        return jsonify({"ok": True, "message": CODE_SENT_MESSAGE})  # never leak the limit
    user = User.query.filter_by(phone=phone).first()
    if not user:
        return jsonify({"error": NO_ACCOUNT_MESSAGE}), 404
    try:
        code = otp_service.request_code(phone)
        sms_service.send_otp_sms(phone, code)
    except ValueError as e:
        return jsonify({"error": str(e)}), 429  # phone-level rate limit (OTP_REQUESTS_PER_WINDOW)
    except sms_service.SmsSendError as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"ok": True, "message": CODE_SENT_MESSAGE})


@bp.post("/auth/register")
def register():
    data = json_body()
    username = normalize_username(data.get("username"))
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "That username is already taken."}), 409

    # The display name is what the clan sees, and only a clan admin can change it later,
    # so it has to be chosen here and can't just be the username.
    full_name = clean_text(data.get("full_name"), DISPLAY_NAME_MAX, "Display name")
    if not full_name:
        return jsonify({"error": "Please enter your display name."}), 400
    if full_name == username:
        return jsonify({"error": "Your display name should be different from your username."}), 400

    password = check_new_password(data.get("password"))

    email = normalize_email(data.get("email"))
    if email and User.query.filter(db.func.lower(User.email) == email).first():
        return jsonify({"error": "That email is already in use."}), 409

    phone = None
    if data.get("phone"):
        phone = normalize_phone(data.get("phone"), data.get("phone_country", "US"))
        if User.query.filter_by(phone=phone).first():
            return jsonify({"error": "That phone number is already in use."}), 409

    clan_name = clean_text(data.get("clan_name"), 120, "Clan name")

    user = User(username=username, email=email or None, phone=phone,
                password_hash=hash_password(password), full_name=full_name)
    db.session.add(user)
    db.session.flush()

    family = None
    if clan_name:
        from .families import _make_join_code
        family = Family(name=clan_name, join_code=_make_join_code(), created_by=user.id)
        db.session.add(family)
        db.session.flush()
        db.session.add(FamilyMember(family_id=family.id, user_id=user.id, role="admin"))

    db.session.commit()
    extra = {"family": {"id": family.id, "name": family.name,
                        "join_code": family.join_code}} if family else {}
    return _finish_login(user, **extra)


@bp.post("/auth/verify-otp")
def verify_otp():
    """Pairs with /auth/send-code: phone-based, not username-based."""
    data = json_body()
    phone = normalize_phone(data.get("phone"), data.get("phone_country", "US"))
    code = data.get("code") if isinstance(data.get("code"), str) else ""
    code = code.strip()
    user = User.query.filter_by(phone=phone).first()
    if not user or not otp_service.verify_code(phone, code):
        return jsonify({"error": "That code didn't work. Please check it and try again."}), 401
    return _finish_login(user)


LOGIN_FAILURES_PER_WINDOW = 20  # wrong passwords per IP per 15 minutes


@bp.post("/auth/login-password")
def login_password():
    data = json_body()
    username = normalize_username(data.get("username"))
    password = data.get("password")
    # Usernames are easy to guess (made from display names), so cap how many wrong
    # passwords one network can try. Only failures count: a family signing in from
    # one home network shouldn't lock itself out.
    ip = request.remote_addr or "unknown"
    try:
        otp_service.check_ip_rate_limit(ip, "login", LOGIN_FAILURES_PER_WINDOW)
    except ValueError as e:
        return jsonify({"error": str(e)}), 429
    user = User.query.filter_by(username=username).first()
    if not user or not verify_password(password, user.password_hash):
        otp_service.record_ip_hit(ip, "login")
        return jsonify({"error": "Wrong username or password."}), 401
    return _finish_login(user)


def _finish_login(user, **extra):
    user.last_login_at = datetime.utcnow()
    db.session.commit()
    resp = make_response(jsonify({"ok": True, "user": user.to_dict(), **extra}))
    return set_auth_cookie(resp, issue_token(user))


@bp.get("/auth/me")
def me():
    # Not @require_auth: the client polls this on every page load (logged in or not) to
    # learn whether there's a session, so an anonymous visitor is a normal 200 here, not a
    # 401. A 401 is technically correct REST but the browser logs every non-2xx fetch as a
    # console error regardless of whether the JS catches it, so every single anonymous page
    # load showed a "Failed to load resource: 401" the instant the page opened.
    user = _current_user()
    if not user or not user.is_active:
        return jsonify({"authenticated": False})
    memberships = FamilyMember.query.filter_by(user_id=user.id).all()
    fams = []
    for m in memberships:
        f = Family.query.get(m.family_id)
        fams.append({"id": f.id, "name": f.name, "role": m.role,
                     "household_id": m.household_id,
                     "household_name": m.household.name if m.household else None,
                     "join_code": f.join_code if m.role == "admin" else None})
    return jsonify({"authenticated": True, "user": user.to_dict(), "families": fams,
                    "can_create_family": user.is_app_admin,
                    "needs_security_setup": not user.password_hash and not user.phone,
                    "must_change_password": user.must_change_password})


DISPLAY_NAME_MAX = 120
# Free-text profile fields the clan sees on someone's profile card: max length, label
PROFILE_FIELDS = {"about_me": (1000, "About me"), "likes": (1000, "Likes"),
                  "avoid_gifts": (1000, "What not to give me")}


def _display_name_error(new_name):
    """Only a clan admin can change a display name (their own included; the one
    exception is a brand-new account with no name yet), and it has to differ from
    the username. Returns the response to send, or None."""
    is_admin = g.user.is_app_admin or FamilyMember.query.filter_by(
        user_id=g.user.id, role="admin").first() is not None
    if g.user.full_name and not is_admin:
        return jsonify({"error": "Only your clan admin can change your display name."}), 403
    if new_name and new_name == g.user.username:
        return jsonify({"error": "Your display name should be different from your username."}), 400
    return None


@bp.patch("/auth/me")
@require_auth
def update_me():
    data = json_body()
    name = clean_text(data.get("full_name"), DISPLAY_NAME_MAX, "Display name")
    if name and name != g.user.full_name:
        err = _display_name_error(name)
        if err:
            return err
        g.user.full_name = name
    if "display_name" in data:
        shown = clean_text(data.get("display_name"), 60, "Display name") or None
        if shown != g.user.display_name:
            err = _display_name_error(shown)
            if err:
                return err
            g.user.display_name = shown
    for field, (limit, label) in PROFILE_FIELDS.items():
        if field in data:
            setattr(g.user, field, clean_text(data.get(field), limit, label, multiline=True) or None)
    if "favorite_colors" in data:
        g.user.favorite_colors = parse_colors(data.get("favorite_colors"))
    db.session.commit()
    return jsonify({"ok": True, "user": g.user.to_dict()})


@bp.post("/auth/me/photo")
@require_auth
def set_my_photo():
    photo = request.files.get("photo")
    if not photo or not photo.filename:
        return jsonify({"error": "Please choose a photo."}), 400
    try:
        new_path = save_photo(photo, "avatars", square=True)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    old_path, g.user.photo_path = g.user.photo_path, new_path
    db.session.commit()
    remove_photo(old_path)
    return jsonify({"ok": True, "user": g.user.to_dict()})


@bp.delete("/auth/me/photo")
@require_auth
def remove_my_photo():
    old_path, g.user.photo_path = g.user.photo_path, None
    db.session.commit()
    remove_photo(old_path)
    return jsonify({"ok": True, "user": g.user.to_dict()})


@bp.patch("/auth/security")
@require_auth
def update_security():
    data = json_body()
    signed_out_others = False
    if "password" in data:
        password = check_new_password(data.get("password"))
        # Deliberately doesn't ask for the current password: this app's real users
        # routinely forget it (that's the actual problem the texted sign-in code solves
        # too), and reaching this endpoint at all already requires a valid session - that
        # bar is the same one every other change on this account goes through.
        if g.user.must_change_password and verify_password(password, g.user.password_hash):
            return jsonify({"error": "Please choose a different password than the one you were given."}), 400
        g.user.password_hash = hash_password(password)
        g.user.must_change_password = False
        # A new password signs out every other device (this one gets a fresh cookie below).
        g.user.session_version = (g.user.session_version or 0) + 1
        signed_out_others = True
    if "phone" in data:
        phone = normalize_phone(data.get("phone"), data.get("phone_country", "US"))
        existing = User.query.filter_by(phone=phone).first()
        if existing and existing.id != g.user.id:
            return jsonify({"error": "That phone number is already in use."}), 409
        g.user.phone = phone
    db.session.commit()
    resp = make_response(jsonify({"ok": True, "user": g.user.to_dict()}))
    return set_auth_cookie(resp, issue_token(g.user)) if signed_out_others else resp


@bp.post("/auth/sign-out-others")
@require_auth
def sign_out_others():
    """Ends every other session on this account (a lost phone, a shared computer),
    keeping this one signed in."""
    g.user.session_version = (g.user.session_version or 0) + 1
    db.session.commit()
    return set_auth_cookie(make_response(jsonify({"ok": True})), issue_token(g.user))


@bp.post("/auth/logout")
def logout():
    # No @require_auth: signing out has to work even with an expired or revoked cookie.
    return clear_auth_cookie(make_response(jsonify({"ok": True})))
