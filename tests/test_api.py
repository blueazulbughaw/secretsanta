import re
import pytest

from app import create_app
from app.extensions import db

ADMIN_USER = "admin"
BOB_USER = "bob"
CARA_USER = "cara"
PASSWORD = "correct-horse-battery"

def make_image(name, size=(64, 48), fmt="PNG", color=(200, 30, 30)):
    """A real (tiny) image as a (file, filename) tuple, ready for a multipart upload."""
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    buf.seek(0)
    return (buf, name)


def join_everyone(users, ev):
    """Everyone in the clan joins the event: members only see the events they're in."""
    fam, admin = users["_family"], users[ADMIN_USER]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": [m["user"]["id"] for m in members]})


def future_date(days=30):
    from datetime import date, timedelta
    return (date.today() + timedelta(days=days)).isoformat()



class TestConfig:
    TESTING = True
    SECRET_KEY = "t"
    JWT_SECRET = "t"
    OTP_PEPPER = "t"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAIL_SERVER = ""
    JWT_DAYS = 7
    OTP_TTL_MINUTES = 10
    OTP_MAX_ATTEMPTS = 5
    OTP_REQUESTS_PER_WINDOW = 10
    OTP_WINDOW_MINUTES = 15


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture()
def users(app):
    """Registers admin (self-service clan creation) + two members, returns logged-in clients."""
    clients = {}
    admin_client = app.test_client()
    r = admin_client.post("/api/auth/register", json={
        "username": ADMIN_USER, "password": PASSWORD, "full_name": "Ana", "clan_name": "Test Fam",
    })
    assert r.status_code == 200
    fam = r.get_json()["family"]
    clients[ADMIN_USER] = admin_client

    for username, name in [(BOB_USER, "Bob"), (CARA_USER, "Cara")]:
        c = app.test_client()
        r = c.post("/api/auth/register",
                    json={"username": username, "password": PASSWORD, "full_name": name})
        assert r.status_code == 200
        c.post("/api/families/join", json={"join_code": fam["join_code"]})
        clients[username] = c
    clients["_family"] = fam
    return clients


def setup_family(users):
    return users["_family"]


def test_login_start_signals_new_username(app):
    c = app.test_client()
    r = c.post("/api/auth/login-start", json={"username": "brandnew"})
    assert r.status_code == 200
    assert r.get_json()["exists"] is False


def test_register_requires_unique_username(app):
    c = app.test_client()
    assert c.post("/api/auth/register",
                   json={"username": "taken", "password": PASSWORD, "full_name": "T"}).status_code == 200
    c2 = app.test_client()
    assert c2.post("/api/auth/register",
                    json={"username": "taken", "password": PASSWORD, "full_name": "T"}).status_code == 409


def test_register_needs_a_display_name_that_isnt_just_the_username(app):
    c = app.test_client()
    r = c.post("/api/auth/register", json={"username": "noname", "password": PASSWORD})
    assert r.status_code == 400 and "display name" in r.get_json()["error"]
    r = c.post("/api/auth/register", json={"username": "same", "password": PASSWORD, "full_name": "same"})
    assert r.status_code == 400 and "different from your username" in r.get_json()["error"]
    r = c.post("/api/auth/register", json={"username": "fine", "password": PASSWORD, "full_name": "Fine Person"})
    assert r.status_code == 200 and r.get_json()["user"]["full_name"] == "Fine Person"


def test_register_requires_password(app):
    c = app.test_client()
    r = c.post("/api/auth/register",
               json={"username": "shortpw", "password": "short", "full_name": "T"})
    assert r.status_code == 400


def test_password_login_flow(app):
    c = app.test_client()
    c.post("/api/auth/register",
           json={"username": "pwuser", "password": PASSWORD, "full_name": "T"})
    c.post("/api/auth/logout")

    c2 = app.test_client()
    r = c2.post("/api/auth/login-start", json={"username": "pwuser"})
    assert r.status_code == 200
    assert (r.get_json()["has_password"], r.get_json()["has_phone"]) == (True, False)

    assert c2.post("/api/auth/login-password",
                    json={"username": "pwuser", "password": "wrong"}).status_code == 401
    r2 = c2.post("/api/auth/login-password", json={"username": "pwuser", "password": PASSWORD})
    assert r2.status_code == 200


def test_phone_sign_in_code_flow(app, capsys):
    c = app.test_client()
    c.post("/api/auth/register",
           json={"username": "phoneuser", "password": PASSWORD, "full_name": "T",
                 "phone": "5551234567"})

    # checking the username reports the options but never sends a text
    c2 = app.test_client()
    r = c2.post("/api/auth/login-start", json={"username": "phoneuser"})
    assert r.get_json()["has_phone"] is True and r.get_json()["has_password"] is True
    assert "sign-in code" not in capsys.readouterr().out

    # a text is sent only when asked for, and only the last 4 digits are shown back
    r = c2.post("/api/auth/send-code", json={"username": "phoneuser"})
    assert r.status_code == 200 and r.get_json()["phone_hint"].endswith("4567")
    assert "+15551234567" not in r.get_data(as_text=True)
    code = re.search(r"code for \+15551234567: (\d{6})", capsys.readouterr().out).group(1)

    assert c2.post("/api/auth/verify-otp",
                    json={"username": "phoneuser", "code": "000000"}).status_code == 401
    r2 = c2.post("/api/auth/verify-otp", json={"username": "phoneuser", "code": code})
    assert r2.status_code == 200
    assert c2.get("/api/auth/me").status_code == 200
    # a used code doesn't work twice
    assert app.test_client().post("/api/auth/verify-otp",
                                  json={"username": "phoneuser", "code": code}).status_code == 401
    # the password still works for the same account
    assert app.test_client().post("/api/auth/login-password",
                                  json={"username": "phoneuser", "password": PASSWORD}).status_code == 200


def test_send_code_needs_a_known_username_with_a_phone(app, users):
    c = app.test_client()
    assert c.post("/api/auth/send-code", json={"username": "nobody"}).status_code == 404
    assert c.post("/api/auth/send-code", json={"username": "no spaces!"}).status_code == 400
    r = c.post("/api/auth/send-code", json={"username": BOB_USER})          # bob has no phone
    assert r.status_code == 400 and "password" in r.get_json()["error"]


def test_send_code_is_rate_limited_per_phone(app, capsys):
    c = app.test_client()
    c.post("/api/auth/register", json={"username": "spammed", "password": PASSWORD,
                                       "full_name": "S", "phone": "5559990000"})
    codes = [c.post("/api/auth/send-code", json={"username": "spammed"}).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and set(codes[10:]) == {429}


def test_privacy_and_terms_are_real_pages_reachable_without_signing_in(app):
    c = app.test_client()
    for path, must in [("/privacy", ["Privacy Policy", "mobile phone number", "do not share, sell, rent"]),
                       ("/terms", ["SMS Terms", "Reply STOP", "HELP", "Message and data rates may apply",
                                   "Text Me a Sign-In Code"]),
                       ("/privacy_terms", ["Privacy Policy", "SMS Terms"])]:
        r = c.get(path)
        page = r.get_data(as_text=True)
        assert r.status_code == 200 and "<title>" in page and 'id="app"' not in page, path   # not the JS shell
        for text in must:
            assert text in page, (path, text)
    # every page links to the others and back to sign-in
    page = c.get("/privacy").get_data(as_text=True)
    assert 'href="/terms"' in page and 'href="/privacy"' in page and 'href="/"' in page



def test_register_with_clan_name_creates_family_and_makes_admin(app):
    c = app.test_client()
    r = c.post("/api/auth/register", json={
        "username": "founder", "password": PASSWORD, "full_name": "Founder", "clan_name": "New Clan",
    })
    assert r.status_code == 200
    body = r.get_json()
    assert body["family"]["name"] == "New Clan"
    me = c.get("/api/auth/me").get_json()
    assert len(me["families"]) == 1 and me["families"][0]["role"] == "admin"


def test_first_family_creation_free_for_any_user(app):
    # A user who registered without a clan_name (no family yet) can still
    # create their first family later via POST /families without needing
    # is_app_admin - only a *second* family requires that flag.
    c = app.test_client()
    c.post("/api/auth/register",
           json={"username": "latebloomer", "password": PASSWORD, "full_name": "Late"})
    r = c.post("/api/families", json={"name": "My First Clan"})
    assert r.status_code == 201
    assert c.post("/api/families", json={"name": "My Second Clan"}).status_code == 403


def test_additional_family_creation_still_restricted_to_app_admins(app, users):
    # POST /families (creating a *second* family later) is a separate, rarer
    # action still gated by the platform-level is_app_admin flag - distinct
    # from the self-service clan creation at registration time.
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    assert admin.post("/api/families", json={"name": "Second clan"}).status_code == 403
    from app.models import User
    User.query.filter_by(username=ADMIN_USER).first().is_app_admin = True
    db.session.commit()
    assert admin.post("/api/families", json={"name": "Second clan"}).status_code == 201
    assert bob.post("/api/families", json={"name": "Not allowed"}).status_code == 403


def test_household_rename_and_delete(users):
    fam = setup_family(users)
    admin = users[ADMIN_USER]
    h = admin.post(f"/api/families/{fam['id']}/households",
                    json={"name": "Original"}).get_json()["household"]
    r = admin.patch(f"/api/households/{h['id']}", json={"name": "Renamed"})
    assert r.status_code == 200 and r.get_json()["household"]["name"] == "Renamed"
    assert admin.delete(f"/api/households/{h['id']}").status_code == 200


def test_clan_admin_can_rename_family(users):
    fam = setup_family(users)
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    assert bob.patch(f"/api/families/{fam['id']}", json={"name": "Nope"}).status_code == 403
    r = admin.patch(f"/api/families/{fam['id']}", json={"name": "The Real Clan Name"})
    assert r.status_code == 200
    assert r.get_json()["family"]["name"] == "The Real Clan Name"
    me = admin.get("/api/auth/me").get_json()
    assert me["families"][0]["name"] == "The Real Clan Name"


def test_household_cannot_be_deleted_while_someone_assigned(users):
    fam = setup_family(users)
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    h = admin.post(f"/api/families/{fam['id']}/households",
                    json={"name": "Occupied"}).get_json()["household"]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    bob_membership = next(m for m in members if m["user"]["username"] == BOB_USER)
    admin.patch(f"/api/families/{fam['id']}/members/{bob_membership['membership_id']}",
                json={"household_id": h["id"]})

    r = admin.delete(f"/api/households/{h['id']}")
    assert r.status_code == 400
    assert "still assigned" in r.get_json()["error"]

    # unassign, then deletion works
    admin.patch(f"/api/families/{fam['id']}/members/{bob_membership['membership_id']}",
                json={"household_id": None})
    assert admin.delete(f"/api/households/{h['id']}").status_code == 200


def test_admin_can_add_edit_and_remove_member(app, users):
    fam = setup_family(users)
    admin, bob = users[ADMIN_USER], users[BOB_USER]

    # non-admin can't add members
    assert bob.post(f"/api/families/{fam['id']}/members",
                     json={"full_name": "Nope"}).status_code == 403

    r = admin.post(f"/api/families/{fam['id']}/members", json={
        "full_name": "Tito Ben", "phone": "5559998888", "email": "ben@example.com",
    })
    assert r.status_code == 201
    body = r.get_json()
    assert body["username"] and body["temp_password"]
    assert body["user"]["phone"] == "+15559998888"
    membership_id = body["membership_id"]

    # the generated account can log in with the returned credentials
    newc = app.test_client()
    login = newc.post("/api/auth/login-password",
                       json={"username": body["username"], "password": body["temp_password"]})
    assert login.status_code == 200

    # admin can edit name/phone/email
    r2 = admin.patch(f"/api/families/{fam['id']}/members/{membership_id}",
                      json={"full_name": "Uncle Ben", "email": "uncle@example.com"})
    assert r2.status_code == 200
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    edited = next(m for m in members if m["membership_id"] == membership_id)
    assert edited["user"]["full_name"] == "Uncle Ben"
    assert edited["user"]["email"] == "uncle@example.com"

    # admin can remove the member
    assert admin.delete(f"/api/families/{fam['id']}/members/{membership_id}").status_code == 200
    members2 = admin.get(f"/api/families/{fam['id']}/members").get_json()
    assert all(m["membership_id"] != membership_id for m in members2)


def test_full_flow_and_privacy(app, users):
    fam = setup_family(users)
    admin, bob, cara = (users[ADMIN_USER], users[BOB_USER], users[CARA_USER])

    # households
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    for i, m in enumerate(members):
        h = admin.post(f"/api/families/{fam['id']}/households",
                       json={"name": f"House {i}"}).get_json()["household"]
        admin.patch(f"/api/families/{fam['id']}/members/{m['membership_id']}",
                    json={"household_id": h["id"]})

    # event + participants
    ev = admin.post(f"/api/families/{fam['id']}/events",
                    json={"name": "Xmas", "event_date": "2026-12-25"}).get_json()["event"]
    uids = [m["user"]["id"] for m in members]
    admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": uids})

    # members can't draw names
    assert bob.post(f"/api/events/{ev['id']}/assignments/generate").status_code == 403
    # admin can
    r = admin.post(f"/api/events/{ev['id']}/assignments/generate")
    assert r.status_code == 200 and r.get_json()["matched"] == 3
    # double-draw blocked
    assert admin.post(f"/api/events/{ev['id']}/assignments/generate").status_code == 400

    # everyone has a giftee, nobody has themselves
    for c in (admin, bob, cara):
        mine = c.get(f"/api/events/{ev['id']}/assignments/mine").get_json()
        assert mine["assigned"] is True

    # wishlist privacy: owner never sees purchase status
    bob.post(f"/api/events/{ev['id']}/wishlists", json={"item_name": "Slippers"})
    bobs_view = bob.get(f"/api/events/{ev['id']}/wishlists/mine").get_json()
    assert "is_purchased" not in bobs_view["items"][0]

    # bob's santa sees + can mark purchased
    santa = next(c for c in (admin, cara)
                 if c.get(f"/api/events/{ev['id']}/assignments/mine")
                     .get_json()["giftee_user_id"] == bobs_view["items"][0]["user_id"])
    giftee_view = next(e for e in santa.get(f"/api/events/{ev['id']}/wishlists/clan").get_json()
                       if e["user"]["id"] == bobs_view["items"][0]["user_id"])
    assert giftee_view["items"][0]["is_purchased"] is False
    item_id = giftee_view["items"][0]["id"]
    assert santa.post(f"/api/wishlists/{item_id}/purchase").status_code == 200
    # owner STILL can't see it
    assert "is_purchased" not in bob.get(
        f"/api/events/{ev['id']}/wishlists/mine").get_json()["items"][0]

    # messaging: bob writes to his santa without knowing who they are
    r = bob.post(f"/api/events/{ev['id']}/messages",
                 json={"to": "giver", "body": "Hi! I like blue."})
    assert r.status_code == 201
    threads = santa.get(f"/api/events/{ev['id']}/messages").get_json()
    assert any(m["body"] == "Hi! I like blue." for m in threads["giftee"]["messages"])


def test_outsider_cannot_touch_family(app, users):
    fam = setup_family(users)
    outsider = app.test_client()
    # unauthenticated
    assert outsider.get(f"/api/families/{fam['id']}/members").status_code == 401


def test_wishlist_edit_via_form_replaces_photo_and_locks_when_bought(app, users, tmp_path):
    import io, os
    app.static_folder = str(tmp_path)  # keep test uploads out of the real static dir
    fam = users["_family"]
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    ev = admin.post(f"/api/families/{fam['id']}/events",
                    json={"name": "Xmas", "event_date": "2026-12-25"}).get_json()["event"]
    join_everyone(users, ev)
    url = f"/api/events/{ev['id']}/wishlists"

    def png(name):
        return make_image(name)

    item = bob.post(url, data={"item_name": "Slippers", "photo": png("a.png")},
                    content_type="multipart/form-data").get_json()["item"]
    old_file = tmp_path / item["photo_url"].removeprefix("/static/")
    assert old_file.exists()

    r = bob.patch(f"/api/wishlists/{item['id']}",
                  data={"item_name": "Warm slippers", "description": "size 7",
                        "link_url": "https://example.com", "photo": png("b.png")},
                  content_type="multipart/form-data")
    assert r.status_code == 200
    edited = r.get_json()["item"]
    assert (edited["item_name"], edited["description"]) == ("Warm slippers", "size 7")
    assert edited["photo_url"] != item["photo_url"]
    assert not old_file.exists()                      # replaced photo is cleaned up
    assert (tmp_path / edited["photo_url"].removeprefix("/static/")).exists()

    # editing without a photo keeps the current one; blank name is rejected
    r = bob.patch(f"/api/wishlists/{item['id']}", data={"item_name": "Warm slippers"},
                  content_type="multipart/form-data")
    assert r.get_json()["item"]["photo_url"] == edited["photo_url"]
    assert bob.patch(f"/api/wishlists/{item['id']}", data={"item_name": "  "},
                     content_type="multipart/form-data").status_code == 400

    # once someone buys it, the owner can no longer edit or delete it
    assert users[ADMIN_USER].post(f"/api/wishlists/{item['id']}/purchase").status_code == 200
    assert bob.patch(f"/api/wishlists/{item['id']}", json={"item_name": "x"}).status_code == 403
    assert bob.delete(f"/api/wishlists/{item['id']}").status_code == 403


def test_events_have_separate_participants_and_can_be_edited(users):
    fam = users["_family"]
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    uid = {m["user"]["username"]: m["user"]["id"] for m in members}
    for i, m in enumerate(members):  # drawing needs everyone in a household
        h = admin.post(f"/api/families/{fam['id']}/households",
                       json={"name": f"House {i}"}).get_json()["household"]
        admin.patch(f"/api/families/{fam['id']}/members/{m['membership_id']}",
                    json={"household_id": h["id"]})

    def make(name):
        return admin.post(f"/api/families/{fam['id']}/events",
                          json={"name": name, "event_date": "2026-12-25"}).get_json()["event"]

    xmas, bday = make("Xmas"), make("Birthday")
    admin.put(f"/api/events/{xmas['id']}/participants", json={"user_ids": list(uid.values())})
    admin.put(f"/api/events/{bday['id']}/participants", json={"user_ids": [uid[ADMIN_USER], uid[BOB_USER]]})

    listed = {e["name"]: e for e in admin.get(f"/api/families/{fam['id']}/events").get_json()}
    assert (listed["Xmas"]["participant_count"], listed["Birthday"]["participant_count"]) == (3, 2)

    # draws are per event, made only from that event's participants
    assert admin.post(f"/api/events/{bday['id']}/assignments/generate").status_code == 400  # only 2 joining
    assert admin.post(f"/api/events/{xmas['id']}/assignments/generate").get_json()["matched"] == 3
    assert bob.get(f"/api/events/{bday['id']}/assignments/mine").get_json()["assigned"] is False

    # editing the still-open Birthday event: rules + who's joining
    r = admin.patch(f"/api/events/{bday['id']}", json={
        "name": "Birthday Bash", "event_date": "2026-12-24", "budget_amount": None,
        "wishlist_limit": 3, "use_codenames": True})
    assert r.status_code == 200
    ev = r.get_json()["event"]
    assert (ev["name"], ev["event_date"], ev["wishlist_limit"], ev["use_codenames"]) ==         ("Birthday Bash", "2026-12-24", 3, True)
    assert admin.patch(f"/api/events/{bday['id']}", json={"event_date": "nope"}).status_code == 400
    # members can't edit; a drawn event can't be edited
    assert bob.patch(f"/api/events/{bday['id']}", json={"name": "x"}).status_code == 403
    # a drawn event keeps its matching rules locked (details are covered below)
    assert admin.patch(f"/api/events/{xmas['id']}", json={"use_codenames": True}).status_code == 400
    assert admin.patch(f"/api/events/{xmas['id']}", json={"wishlist_limit": 9}).status_code == 400


def test_profile_photo_upload_replace_remove(app, users, tmp_path):
    import io
    app.static_folder = str(tmp_path)
    bob = users[BOB_USER]

    def png(name):
        return make_image(name)

    assert bob.get("/api/auth/me").get_json()["user"]["photo_url"] is None
    r = bob.post("/api/auth/me/photo", data={"photo": png("me.png")}, content_type="multipart/form-data")
    assert r.status_code == 200
    first = r.get_json()["user"]["photo_url"]
    first_file = tmp_path / first.removeprefix("/static/")
    assert first.startswith("/static/uploads/avatars/") and first_file.exists()
    assert bob.get("/api/auth/me").get_json()["user"]["photo_url"] == first

    # replacing deletes the old file; the clan sees the new photo
    second = bob.post("/api/auth/me/photo", data={"photo": png("me2.jpg")},
                      content_type="multipart/form-data").get_json()["user"]["photo_url"]
    assert second != first and not first_file.exists()
    members = users[ADMIN_USER].get(f"/api/families/{users['_family']['id']}/members").get_json()
    assert {m["user"]["username"]: m["user"]["photo_url"] for m in members}[BOB_USER] == second

    # bad type / missing file are rejected
    assert bob.post("/api/auth/me/photo", data={"photo": (io.BytesIO(b"x"), "evil.exe")},
                    content_type="multipart/form-data").status_code == 400
    assert bob.post("/api/auth/me/photo", data={}, content_type="multipart/form-data").status_code == 400

    r = bob.delete("/api/auth/me/photo")
    assert r.get_json()["user"]["photo_url"] is None
    assert not (tmp_path / second.removeprefix("/static/")).exists()


def test_profile_details_saved_and_visible_to_clan(users):
    bob, admin = users[BOB_USER], users[ADMIN_USER]
    fam = users["_family"]["id"]
    blank = bob.get("/api/auth/me").get_json()["user"]
    assert (blank["about_me"], blank["likes"], blank["favorite_color"], blank["avoid_gifts"]) == ("", "", "", "")

    r = bob.patch("/api/auth/me", json={"about_me": "  Loves hiking ", "likes": "Coffee, books",
                                        "favorite_color": "Sage green", "avoid_gifts": "Candles"})
    assert r.status_code == 200
    u = r.get_json()["user"]
    assert (u["about_me"], u["likes"], u["favorite_color"], u["avoid_gifts"]) == \
        ("Loves hiking", "Coffee, books", "Sage green", "Candles")

    # partial update leaves the other fields alone; empty string clears one
    bob.patch("/api/auth/me", json={"likes": ""})
    u = bob.get("/api/auth/me").get_json()["user"]
    assert u["likes"] == "" and u["about_me"] == "Loves hiking"

    # too-long values are trimmed to their limits
    u = bob.patch("/api/auth/me", json={"favorite_color": "x" * 100}).get_json()["user"]
    assert len(u["favorite_color"]) == 40

    # the rest of the family sees them
    members = admin.get(f"/api/families/{fam}/members").get_json()
    bob_row = next(m["user"] for m in members if m["user"]["username"] == BOB_USER)
    assert bob_row["about_me"] == "Loves hiking" and bob_row["avoid_gifts"] == "Candles"


def test_event_details_editable_after_draw_and_shown_to_members(users):
    fam = users["_family"]
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    r = admin.post(f"/api/families/{fam['id']}/events", json={
        "name": "Xmas", "event_date": "2026-12-25", "event_time": "18:30",
        "location": " Lola's house ", "theme": "Ugly sweaters", "budget_amount": 25,
        "rules": "No re-gifting", "what_to_bring": "A dish to share", "other_info": "Parking on the left"})
    assert r.status_code == 201
    ev = r.get_json()["event"]
    join_everyone(users, ev)
    assert (ev["event_time"], ev["location"], ev["theme"]) == ("18:30", "Lola's house", "Ugly sweaters")
    assert (ev["rules"], ev["what_to_bring"], ev["other_info"]) ==         ("No re-gifting", "A dish to share", "Parking on the left")

    # members read the details but can't change them
    assert bob.get(f"/api/events/{ev['id']}").get_json()["what_to_bring"] == "A dish to share"
    assert bob.patch(f"/api/events/{ev['id']}", json={"location": "x"}).status_code == 403

    # bad time is rejected; an empty time/text clears the field
    assert admin.patch(f"/api/events/{ev['id']}", json={"event_time": "25:99"}).status_code == 400
    cleared = admin.patch(f"/api/events/{ev['id']}", json={"event_time": "", "theme": ""}).get_json()["event"]
    assert cleared["event_time"] is None and cleared["theme"] == ""

    # after the draw the details (and date/name) can still change, the matching rules can't
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    for i, m in enumerate(members):
        h = admin.post(f"/api/families/{fam['id']}/households", json={"name": f"H{i}"}).get_json()["household"]
        admin.patch(f"/api/families/{fam['id']}/members/{m['membership_id']}", json={"household_id": h["id"]})
    admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": [m["user"]["id"] for m in members]})
    assert admin.post(f"/api/events/{ev['id']}/assignments/generate").status_code == 200
    r = admin.patch(f"/api/events/{ev['id']}", json={"location": "The park", "event_time": "12:00",
                                                     "event_date": "2026-12-26", "name": "Xmas Party"})
    assert r.status_code == 200
    got = r.get_json()["event"]
    assert (got["location"], got["event_time"], got["event_date"], got["name"]) ==         ("The park", "12:00", "2026-12-26", "Xmas Party")
    assert admin.patch(f"/api/events/{ev['id']}", json={"wishlist_limit": 2}).status_code == 400


def test_attendees_visible_to_the_people_joining_without_private_contact_info(app, users):
    fam = users["_family"]
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    ev = admin.post(f"/api/families/{fam['id']}/events",
                    json={"name": "Xmas", "event_date": future_date()}).get_json()["event"]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    uid = {m["user"]["username"]: m["user"]["id"] for m in members}
    admin.put(f"/api/events/{ev['id']}/participants",
              json={"user_ids": [uid[CARA_USER], uid[ADMIN_USER], uid[BOB_USER]]})
    bob.patch("/api/auth/security", json={"phone": "(555) 010-1234"})
    admin.patch("/api/auth/me", json={"likes": "Tea", "favorite_color": "Green"})

    # household names come with them (blank until someone is in one), sorted by name
    h = admin.post(f"/api/families/{fam['id']}/households", json={"name": "Cruz House"}).get_json()["household"]
    ana_membership = next(m for m in members if m["user"]["username"] == ADMIN_USER)["membership_id"]
    admin.patch(f"/api/families/{fam['id']}/members/{ana_membership}", json={"household_id": h["id"]})
    people = bob.get(f"/api/events/{ev['id']}/attendees").get_json()
    assert [(p["display_name"], p["household_name"]) for p in people] == \
        [("Ana", "Cruz House"), ("Bob", ""), ("Cara", "")]
    assert (people[0]["likes"], people[0]["favorite_color"]) == ("Tea", "Green")
    assert all(not ({"phone", "email", "username", "avoid_gifts"} & set(p)) for p in people)

    # outsiders can't
    outsider = app.test_client()
    outsider.post("/api/auth/register", json={"username": "zed", "password": PASSWORD, "full_name": "Zed"})
    assert outsider.get(f"/api/events/{ev['id']}/attendees").status_code == 403


def test_only_clan_admin_can_change_names(app, users):
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    fam = users["_family"]
    r = bob.patch("/api/auth/me", json={"full_name": "Robert"})
    assert r.status_code == 403
    assert bob.get("/api/auth/me").get_json()["user"]["full_name"] == "Bob"
    # sending the unchanged name, or only other profile fields, is fine
    assert bob.patch("/api/auth/me", json={"full_name": "Bob", "likes": "Tea"}).status_code == 200
    # the admin can rename themselves and any member
    assert admin.patch("/api/auth/me", json={"full_name": "Ana C"}).get_json()["user"]["full_name"] == "Ana C"
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    bob_m = next(m for m in members if m["user"]["username"] == BOB_USER)
    assert admin.patch(f"/api/families/{fam['id']}/members/{bob_m['membership_id']}",
                       json={"full_name": "Robert"}).status_code == 200
    assert bob.get("/api/auth/me").get_json()["user"]["full_name"] == "Robert"
    # an account that has no name yet can still pick one
    from app.models import User
    User.query.filter_by(username=CARA_USER).first().full_name = ""
    db.session.commit()
    assert users[CARA_USER].patch("/api/auth/me", json={"full_name": "Cara"}).status_code == 200


def test_password_reset_needs_current_password(app, users):
    bob = users[BOB_USER]
    assert bob.patch("/api/auth/security", json={"password": "another-long-pass"}).status_code == 400
    assert bob.patch("/api/auth/security", json={"password": "another-long-pass",
                                                 "current_password": "wrong-password"}).status_code == 400
    assert bob.patch("/api/auth/security", json={"password": "another-long-pass",
                                                 "current_password": PASSWORD}).status_code == 200
    fresh = app.test_client()
    assert fresh.post("/api/auth/login-password",
                      json={"username": BOB_USER, "password": "another-long-pass"}).status_code == 200
    assert app.test_client().post("/api/auth/login-password",
                                  json={"username": BOB_USER, "password": PASSWORD}).status_code == 401

    # an account with no password yet sets one without a current password
    from app.models import User
    User.query.filter_by(username=CARA_USER).first().password_hash = None
    db.session.commit()
    assert users[CARA_USER].patch("/api/auth/security", json={"password": "brand-new-pass"}).status_code == 200


def test_temporary_password_can_be_replaced_without_retyping_it(users):
    admin, fam = users[ADMIN_USER], users["_family"]
    added = admin.post(f"/api/families/{fam['id']}/members", json={"full_name": "Dee Dee"}).get_json()
    assert added["user"]["username"]
    c = app_client_for(admin, added)
    assert c.patch("/api/auth/security", json={"password": "my-own-password"}).status_code == 200


def app_client_for(admin, added):
    """Signs in as a member the admin just added, using the temporary password."""
    c = admin.application.test_client()
    r = c.post("/api/auth/login-password", json={
        "username": added["user"]["username"], "password": added["temp_password"]})
    assert r.status_code == 200
    return c


def test_admin_can_delete_event_and_everything_in_it(app, users, tmp_path):
    import io
    app.static_folder = str(tmp_path)
    fam = users["_family"]
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    uid = [m["user"]["id"] for m in members]
    for i, m in enumerate(members):
        h = admin.post(f"/api/families/{fam['id']}/households", json={"name": f"D{i}"}).get_json()["household"]
        admin.patch(f"/api/families/{fam['id']}/members/{m['membership_id']}", json={"household_id": h["id"]})

    def make(name):
        ev = admin.post(f"/api/families/{fam['id']}/events",
                        json={"name": name, "event_date": future_date()}).get_json()["event"]
        admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": uid})
        return ev

    doomed, kept = make("Doomed"), make("Kept")
    for ev in (doomed, kept):
        assert admin.post(f"/api/events/{ev['id']}/assignments/generate").status_code == 200
        r = bob.post(f"/api/events/{ev['id']}/wishlists", data={
            "item_name": "Slippers", "photo": make_image("s.png")},
            content_type="multipart/form-data")
        assert r.status_code == 201
    doomed_photo = tmp_path / bob.get(f"/api/events/{doomed['id']}/wishlists/mine").get_json()["items"][0]["photo_url"].removeprefix("/static/")
    assert doomed_photo.exists()
    admin.post(f"/api/families/{fam['id']}/announcements",
               json={"title": "Party", "body": "Soon", "event_id": doomed["id"]})

    # members can't delete; the admin can
    assert bob.delete(f"/api/events/{doomed['id']}").status_code == 403
    assert admin.delete(f"/api/events/{doomed['id']}").status_code == 200
    assert admin.get(f"/api/events/{doomed['id']}").status_code == 404
    assert admin.delete(f"/api/events/{doomed['id']}").status_code == 404
    assert not doomed_photo.exists()

    from app.models import Assignment, EventParticipant, WishlistItem
    assert Assignment.query.filter_by(event_id=doomed["id"]).count() == 0
    assert EventParticipant.query.filter_by(event_id=doomed["id"]).count() == 0
    assert WishlistItem.query.filter_by(event_id=doomed["id"]).count() == 0
    # the other event is untouched
    assert Assignment.query.filter_by(event_id=kept["id"]).count() == 3
    assert WishlistItem.query.filter_by(event_id=kept["id"]).count() == 1
    assert [e["name"] for e in admin.get(f"/api/families/{fam['id']}/events").get_json()] == ["Kept"]


def test_any_event_can_be_deleted_old_archived_or_upcoming(users):
    fam, admin, bob = users["_family"], users[ADMIN_USER], users[BOB_USER]

    def make(name, when):
        return admin.post(f"/api/families/{fam['id']}/events",
                          json={"name": name, "event_date": when}).get_json()["event"]

    from datetime import date, timedelta
    past = make("Last year", (date.today() - timedelta(days=400)).isoformat())
    today = make("Today", date.today().isoformat())
    archived = make("Archived", future_date())
    admin.post(f"/api/events/{archived['id']}/complete")

    assert bob.delete(f"/api/events/{past['id']}").status_code == 403       # only the clan admin
    for ev in (past, archived, today):
        assert admin.delete(f"/api/events/{ev['id']}").status_code == 200
    assert admin.get(f"/api/families/{fam['id']}/events").get_json() == []


def test_photos_are_resized_and_profile_photos_cropped_square(app, users, tmp_path):
    import io
    from PIL import Image
    app.static_folder = str(tmp_path)
    fam, bob = users["_family"], users[BOB_USER]
    ev = users[ADMIN_USER].post(f"/api/families/{fam['id']}/events",
                                json={"name": "Xmas", "event_date": future_date()}).get_json()["event"]
    join_everyone(users, ev)

    def stored(photo_url):
        return Image.open(tmp_path / photo_url.removeprefix("/static/"))

    # a big gift photo is shrunk to fit 1200px, keeping its shape
    big = make_image("big.png", size=(3000, 2000))
    item = bob.post(f"/api/events/{ev['id']}/wishlists", data={"item_name": "Bike", "photo": big},
                    content_type="multipart/form-data").get_json()["item"]
    assert stored(item["photo_url"]).size == (1200, 800)

    # profile photos become a square, whatever shape they arrived as
    r = bob.post("/api/auth/me/photo", data={"photo": make_image("wide.jpg", size=(1000, 400), fmt="JPEG")},
                 content_type="multipart/form-data")
    assert stored(r.get_json()["user"]["photo_url"]).size == (512, 512)
    r = bob.post("/api/auth/me/photo", data={"photo": make_image("tall.png", size=(300, 900))},
                 content_type="multipart/form-data")
    assert stored(r.get_json()["user"]["photo_url"]).size == (512, 512)

    # too big, or not really an image, is refused with a plain message
    huge = (io.BytesIO(b"0" * (9 * 1024 * 1024)), "huge.jpg")
    r = bob.post("/api/auth/me/photo", data={"photo": huge}, content_type="multipart/form-data")
    assert r.status_code == 400 and "smaller than 8MB" in r.get_json()["error"]
    fake = (io.BytesIO(b"this is not a picture"), "fake.png")
    r = bob.post("/api/auth/me/photo", data={"photo": fake}, content_type="multipart/form-data")
    assert r.status_code == 400 and "doesn't look like a photo" in r.get_json()["error"]


def test_link_urls_are_checked_and_made_absolute(users):
    from app.utils import normalize_link_url
    fam, bob = users["_family"], users[BOB_USER]
    ok = {"": "", "  ": "", "amazon.com/dp/B0123": "https://amazon.com/dp/B0123",
          "www.target.com": "https://www.target.com", "http://example.com/a?b=1": "http://example.com/a?b=1",
          "//shop.example.org/x": "https://shop.example.org/x", "HTTPS://Example.com": "HTTPS://Example.com",
          "amazon.com:443/x": "https://amazon.com:443/x"}
    for raw, want in ok.items():
        assert normalize_link_url(raw) == want, raw
    for raw in ["hello", "not a url", "javascript:alert(1)", "mailto:a@b.com", "ftp://example.com",
                "https://", "https://nodot", "https://exa mple.com", "http://example.c", "data:text/html,hi",
                "https://example.com:notaport", "x" * 501]:
        try:
            normalize_link_url(raw)
        except ValueError:
            continue
        raise AssertionError(f"should have been rejected: {raw!r}")

    ev = users[ADMIN_USER].post(f"/api/families/{fam['id']}/events",
                                json={"name": "Xmas", "event_date": future_date()}).get_json()["event"]
    join_everyone(users, ev)
    url = f"/api/events/{ev['id']}/wishlists"
    r = bob.post(url, json={"item_name": "Lamp", "link_url": "ikea.com/lamp"})
    assert r.status_code == 201 and r.get_json()["item"]["link_url"] == "https://ikea.com/lamp"
    item_id = r.get_json()["item"]["id"]
    bad = bob.post(url, json={"item_name": "Rug", "link_url": "javascript:alert(1)"})
    assert bad.status_code == 400 and "valid web link" in bad.get_json()["error"]
    assert bob.patch(f"/api/wishlists/{item_id}", json={"link_url": "nope"}).status_code == 400
    assert bob.patch(f"/api/wishlists/{item_id}", json={"link_url": "target.com/x"}).get_json()["item"]["link_url"] == "https://target.com/x"
    assert bob.patch(f"/api/wishlists/{item_id}", json={"link_url": ""}).get_json()["item"]["link_url"] is None


def _drawn_event(users, days=30):
    """An event with everyone joining and names drawn; returns the event dict."""
    fam, admin = users["_family"], users[ADMIN_USER]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    for i, m in enumerate(members):
        if m.get("household_id"):
            continue
        h = admin.post(f"/api/families/{fam['id']}/households", json={"name": f"Hh{i}"}).get_json()["household"]
        admin.patch(f"/api/families/{fam['id']}/members/{m['membership_id']}", json={"household_id": h["id"]})
    ev = admin.post(f"/api/families/{fam['id']}/events",
                    json={"name": "Potluck", "event_date": future_date(days)}).get_json()["event"]
    admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": [m["user"]["id"] for m in members]})
    assert admin.post(f"/api/events/{ev['id']}/assignments/generate").status_code == 200
    return ev


def test_wishlist_order_is_the_priority(users):
    fam, admin, bob = users["_family"], users[ADMIN_USER], users[BOB_USER]
    ev = admin.post(f"/api/families/{fam['id']}/events",
                    json={"name": "Xmas", "event_date": future_date()}).get_json()["event"]
    join_everyone(users, ev)
    url = f"/api/events/{ev['id']}/wishlists"
    ids = [bob.post(url, json={"item_name": n, "priority": 1}).get_json()["item"]["id"]
           for n in ("Socks", "Book", "Lamp")]
    names = lambda: [i["item_name"] for i in bob.get(f"{url}/mine").get_json()["items"]]
    assert names() == ["Socks", "Book", "Lamp"]            # new gifts go to the bottom, priority input ignored

    assert bob.put(f"{url}/order", json={"item_ids": [ids[2], ids[0], ids[1]]}).status_code == 200
    assert names() == ["Lamp", "Socks", "Book"]
    # everyone else sees the same order
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": [m["user"]["id"] for m in members]})
    clan = admin.get(f"/api/events/{ev['id']}/wishlists/clan").get_json()
    bob_items = next(e for e in clan if e["user"]["username"] == BOB_USER)["items"]
    assert [i["item_name"] for i in bob_items] == ["Lamp", "Socks", "Book"]

    # a gift added later lands last, and editing never changes the order
    ids.append(bob.post(url, json={"item_name": "Mug"}).get_json()["item"]["id"])
    bob.patch(f"/api/wishlists/{ids[0]}", json={"item_name": "Wool socks", "priority": 1})
    assert names() == ["Lamp", "Wool socks", "Book", "Mug"]

    # the list must be exactly the caller's gifts
    assert bob.put(f"{url}/order", json={"item_ids": ids[:3]}).status_code == 400
    assert bob.put(f"{url}/order", json={"item_ids": ids + [999999]}).status_code == 400
    assert bob.put(f"{url}/order", json={"item_ids": ids + [ids[0]]}).status_code == 400
    assert bob.put(f"{url}/order", json={"item_ids": "nope"}).status_code == 400
    other = users[CARA_USER].post(url, json={"item_name": "Cara's"}).get_json()["item"]["id"]
    assert bob.put(f"{url}/order", json={"item_ids": ids[:3] + [other]}).status_code == 400
    assert names() == ["Lamp", "Wool socks", "Book", "Mug"]


def test_description_keeps_line_breaks(users):
    fam, admin, bob = users["_family"], users[ADMIN_USER], users[BOB_USER]
    ev = admin.post(f"/api/families/{fam['id']}/events",
                    json={"name": "Xmas", "event_date": future_date()}).get_json()["event"]
    join_everyone(users, ev)
    text = "Size 9\nNo laces please\nBlack"
    item = bob.post(f"/api/events/{ev['id']}/wishlists",
                    json={"item_name": "Boots", "description": text}).get_json()["item"]
    assert item["description"] == text


def test_dish_signup_opens_after_the_draw_one_entry_many_dishes(app, users):
    fam, admin, bob, cara = users["_family"], users[ADMIN_USER], users[BOB_USER], users[CARA_USER]
    open_ev = admin.post(f"/api/families/{fam['id']}/events",
                         json={"name": "Later", "event_date": future_date(60)}).get_json()["event"]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    admin.put(f"/api/events/{open_ev['id']}/participants", json={"user_ids": [m["user"]["id"] for m in members]})
    r = bob.put(f"/api/events/{open_ev['id']}/dishes/mine", json={"dishes": ["Pancit"]})
    assert r.status_code == 400 and "opens once names are drawn" in r.get_json()["error"]

    ev = _drawn_event(users)
    url = f"/api/events/{ev['id']}/dishes"
    assert bob.get(url).get_json() == []
    # one entry, several dishes: blanks and repeats are dropped, order is kept
    r = bob.put(f"{url}/mine", json={"dishes": [" Pancit ", "", "Lumpia", "pancit", "Leche flan"]})
    assert r.status_code == 200
    entries = r.get_json()
    assert len(entries) == 1
    assert [d["name"] for d in entries[0]["dishes"]] == ["Pancit", "Lumpia", "Leche flan"]
    assert "phone" not in entries[0]["user"] and "email" not in entries[0]["user"]

    # editing replaces the entry (still one entry); everyone sees it
    bob.put(f"{url}/mine", json={"dishes": ["Lumpia", "Salad"]})
    cara.put(f"{url}/mine", json={"dishes": ["Rice"]})
    seen = admin.get(url).get_json()
    assert [(e["user"]["display_name"], [d["name"] for d in e["dishes"]]) for e in seen] == \
        [("Bob", ["Lumpia", "Salad"]), ("Cara", ["Rice"])]

    # limits
    assert bob.put(f"{url}/mine", json={"dishes": [f"Dish {i}" for i in range(11)]}).status_code == 400
    assert bob.put(f"{url}/mine", json={"dishes": "Rice"}).status_code == 400

    # removing: an empty list or DELETE
    bob.put(f"{url}/mine", json={"dishes": []})
    assert [e["user"]["display_name"] for e in admin.get(url).get_json()] == ["Cara"]
    assert cara.delete(f"{url}/mine").status_code == 200
    assert admin.get(url).get_json() == []

    # outsiders can't see or add
    outsider = app.test_client()
    outsider.post("/api/auth/register", json={"username": "zed", "password": PASSWORD, "full_name": "Zed"})
    assert outsider.get(url).status_code == 403
    assert outsider.put(f"{url}/mine", json={"dishes": ["x"]}).status_code == 403

    # finished events are read-only
    bob.put(f"{url}/mine", json={"dishes": ["Lumpia"]})
    admin.post(f"/api/events/{ev['id']}/complete")
    assert bob.put(f"{url}/mine", json={"dishes": ["More"]}).status_code == 400
    assert [d["name"] for d in bob.get(url).get_json()[0]["dishes"]] == ["Lumpia"]


def test_only_joiners_add_dishes_and_deleting_an_event_removes_them(users):
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    fam = users["_family"]
    ev = _drawn_event(users)
    # someone who isn't joining a drawn event can't add dishes to it
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    from app.models import EventParticipant
    EventParticipant.query.filter_by(event_id=ev["id"], user_id=next(
        m["user"]["id"] for m in members if m["user"]["username"] == CARA_USER)).update({"is_participating": False})
    from app.extensions import db as _db
    _db.session.commit()
    r = users[CARA_USER].put(f"/api/events/{ev['id']}/dishes/mine", json={"dishes": ["x"]})
    assert r.status_code == 403

    bob.put(f"/api/events/{ev['id']}/dishes/mine", json={"dishes": ["Lumpia"]})
    from app.models import EventDish
    assert EventDish.query.filter_by(event_id=ev["id"]).count() == 1
    assert admin.delete(f"/api/events/{ev['id']}").status_code == 200
    assert EventDish.query.filter_by(event_id=ev["id"]).count() == 0


def test_game_master_is_chosen_from_attendees(users):
    fam, admin, bob, cara = users["_family"], users[ADMIN_USER], users[BOB_USER], users[CARA_USER]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    ids = {m["user"]["username"]: m["user"]["id"] for m in members}
    ev = admin.post(f"/api/families/{fam['id']}/events",
                    json={"name": "Party", "event_date": future_date()}).get_json()["event"]
    assert ev["game_master_id"] is None
    admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": [ids[ADMIN_USER], ids[BOB_USER]]})

    # only someone who's joining; only the clan admin sets it
    assert admin.patch(f"/api/events/{ev['id']}", json={"game_master_id": ids[CARA_USER]}).status_code == 400
    assert admin.patch(f"/api/events/{ev['id']}", json={"game_master_id": "abc"}).status_code == 400
    assert bob.patch(f"/api/events/{ev['id']}", json={"game_master_id": ids[BOB_USER]}).status_code == 403
    r = admin.patch(f"/api/events/{ev['id']}", json={"game_master_id": ids[BOB_USER]})
    assert r.status_code == 200 and r.get_json()["event"]["game_master_id"] == ids[BOB_USER]
    assert bob.get(f"/api/events/{ev['id']}").get_json()["game_master_id"] == ids[BOB_USER]

    # taking them off the guest list clears it; it can also be cleared directly
    admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": [ids[ADMIN_USER]]})
    assert admin.get(f"/api/events/{ev['id']}").get_json()["game_master_id"] is None
    admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": list(ids.values())})
    admin.patch(f"/api/events/{ev['id']}", json={"game_master_id": ids[CARA_USER]})
    cleared = admin.patch(f"/api/events/{ev['id']}", json={"game_master_id": None}).get_json()["event"]
    assert cleared["game_master_id"] is None

    # can be changed after names are drawn (the draw rules stay locked)
    drawn = _drawn_event(users)
    r = admin.patch(f"/api/events/{drawn['id']}", json={"game_master_id": ids[CARA_USER]})
    assert r.status_code == 200 and r.get_json()["event"]["game_master_id"] == ids[CARA_USER]


def test_announcements_newest_first_and_only_published_shown_to_members(users):
    fam, admin, bob = users["_family"], users[ADMIN_USER], users[BOB_USER]
    url = f"/api/families/{fam['id']}/announcements"
    admin.post(url, json={"title": "First", "body": "one"})
    admin.post(url, json={"title": "Hidden", "body": "draft", "is_published": False, "is_pinned": True})
    admin.post(url, json={"title": "Third", "body": "three", "is_pinned": True})   # pinning no longer exists

    seen = bob.get(url).get_json()
    assert [a["title"] for a in seen] == ["Third", "First"]           # newest first, unpublished hidden
    assert all("is_pinned" not in a for a in seen)
    assert [a["title"] for a in admin.get(f"{url}?scope=all").get_json()] == ["Third", "Hidden", "First"]



def test_archived_event_is_view_only_but_everything_stays_readable(app, users, tmp_path):
    app.static_folder = str(tmp_path)
    fam, admin, bob, cara = users["_family"], users[ADMIN_USER], users[BOB_USER], users[CARA_USER]
    ev = _drawn_event(users)
    eid = ev["id"]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    ids = {m["user"]["username"]: m["user"]["id"] for m in members}

    # some history while the event is live
    item = bob.post(f"/api/events/{eid}/wishlists", json={"item_name": "Boots"}).get_json()["item"]
    second = bob.post(f"/api/events/{eid}/wishlists", json={"item_name": "Hat"}).get_json()["item"]
    bob.put(f"/api/events/{eid}/dishes/mine", json={"dishes": ["Lumpia"]})
    mine = bob.get(f"/api/events/{eid}/assignments/mine").get_json()
    assert bob.post(f"/api/events/{eid}/messages", json={"to": "giftee", "body": "hello"}).status_code == 201
    assert cara.post(f"/api/wishlists/{item['id']}/purchase").status_code == 200

    assert admin.post(f"/api/events/{eid}/complete").status_code == 200

    # ---- nothing can change any more
    err = lambda r: r.status_code == 400 and "archived" in r.get_json()["error"]
    assert err(bob.post(f"/api/events/{eid}/messages", json={"to": "giftee", "body": "again"}))
    assert err(bob.post(f"/api/events/{eid}/messages", json={"to": "giver", "body": "again"}))
    assert err(bob.post(f"/api/events/{eid}/wishlists", json={"item_name": "Scarf"}))
    assert err(bob.patch(f"/api/wishlists/{second['id']}", json={"item_name": "Cap"}))
    assert err(bob.delete(f"/api/wishlists/{second['id']}"))
    assert err(bob.put(f"/api/events/{eid}/wishlists/order", json={"item_ids": [second["id"], item["id"]]}))
    assert err(cara.post(f"/api/wishlists/{item['id']}/purchase"))       # can't undo a purchase either
    assert err(bob.put(f"/api/events/{eid}/dishes/mine", json={"dishes": ["Rice"]}))
    assert err(bob.delete(f"/api/events/{eid}/dishes/mine"))
    assert err(admin.patch(f"/api/events/{eid}", json={"location": "Elsewhere"}))
    assert err(admin.patch(f"/api/events/{eid}", json={"game_master_id": ids[CARA_USER]}))
    assert err(admin.put(f"/api/events/{eid}/participants", json={"user_ids": [ids[ADMIN_USER]]}))
    assert err(bob.post(f"/api/events/{eid}/participants/opt-out"))
    assert admin.delete(f"/api/events/{eid}/assignments").status_code == 400   # no re-draw

    # ---- but all of it can still be looked at
    threads = bob.get(f"/api/events/{eid}/messages").get_json()
    assert [m["body"] for m in threads["giftee"]["messages"]] == ["hello"]
    listed = bob.get(f"/api/events/{eid}/wishlists/mine").get_json()
    assert listed["archived"] is True and [i["item_name"] for i in listed["items"]] == ["Boots", "Hat"]
    clan = cara.get(f"/api/events/{eid}/wishlists/clan").get_json()
    boots = next(i for e in clan if e["user"]["username"] == BOB_USER for i in e["items"] if i["item_name"] == "Boots")
    assert boots["is_purchased"] is True
    assert [d["name"] for d in admin.get(f"/api/events/{eid}/dishes").get_json()[0]["dishes"]] == ["Lumpia"]
    assert admin.get(f"/api/events/{eid}").get_json()["status"] == "completed"
    assert len(admin.get(f"/api/events/{eid}/attendees").get_json()) == 3
    assert mine["assigned"] is True
    assert cara.get(f"/api/events/{eid}/assignments/mine").get_json()["assigned"] is True

    # an active event next to it is unaffected
    other = _drawn_event(users, days=50)
    assert bob.post(f"/api/events/{other['id']}/wishlists", json={"item_name": "Scarf"}).status_code == 201
    assert bob.post(f"/api/events/{other['id']}/messages", json={"to": "giftee", "body": "hi"}).status_code == 201


def test_announcement_notification_title(users):
    fam, admin, bob = users["_family"], users[ADMIN_USER], users[BOB_USER]
    admin.post(f"/api/families/{fam['id']}/announcements",
               json={"title": "Party time", "body": "Potluck at 6pm, bring a dish!"})
    first = bob.get("/api/notifications").get_json()["items"][0]
    assert first["title"] == "New Announcement posted by Admin"
    assert first["body"] == "Party time: Potluck at 6pm, bring a dish!"
    assert first["link_path"] == "/announcements"
    # a draft (not shown on the dashboard) tells nobody
    admin.post(f"/api/families/{fam['id']}/announcements",
               json={"title": "Draft", "body": "later", "is_published": False})
    assert len(bob.get("/api/notifications").get_json()["items"]) == 1


def test_new_gift_notification_opens_the_owners_profile(users):
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    ev = _drawn_event(users)
    bob_id = bob.get("/api/auth/me").get_json()["user"]["id"]
    santa = next(c for c in (admin, users[CARA_USER])
                 if c.get(f"/api/events/{ev['id']}/assignments/mine").get_json()["giftee_user_id"] == bob_id)
    bob.post(f"/api/events/{ev['id']}/wishlists", json={"item_name": "Boots"})
    latest = santa.get("/api/notifications").get_json()["items"][0]
    assert latest["link_path"] == f"/events/{ev['id']}/clan/{bob_id}"

    # with codenames on, the profile would name them, so it opens the reveal page instead
    fam = users["_family"]
    coded = admin.post(f"/api/families/{fam['id']}/events",
                       json={"name": "Coded", "event_date": future_date(45), "use_codenames": True}).get_json()["event"]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    admin.put(f"/api/events/{coded['id']}/participants", json={"user_ids": [m["user"]["id"] for m in members]})
    assert admin.post(f"/api/events/{coded['id']}/assignments/generate").status_code == 200
    santa = next(c for c in (admin, users[CARA_USER])
                 if c.get(f"/api/events/{coded['id']}/assignments/mine").get_json()["giftee_user_id"] == bob_id)
    bob.post(f"/api/events/{coded['id']}/wishlists", json={"item_name": "Hat"})
    assert santa.get("/api/notifications").get_json()["items"][0]["link_path"] == f"/events/{coded['id']}/my-person"

    # the old giver-only list endpoint is gone
    gone = santa.get(f"/api/events/{ev['id']}/wishlists/giftee")
    assert "items" not in (gone.get_json(silent=True) or {})


def test_each_gift_exchange_has_its_own_giver_giftee_pairs(app, users):
    fam, admin = users["_family"], users[ADMIN_USER]
    clients = {ADMIN_USER: admin, BOB_USER: users[BOB_USER], CARA_USER: users[CARA_USER]}
    for name in ("dan", "eve", "fay"):
        c = app.test_client()
        c.post("/api/auth/register", json={"username": name, "password": PASSWORD, "full_name": name.title()})
        c.post("/api/families/join", json={"join_code": fam["join_code"]})
        clients[name] = c
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    for m in members:
        h = admin.post(f"/api/families/{fam['id']}/households",
                       json={"name": f"Home of {m['user']['username']}"}).get_json()["household"]
        admin.patch(f"/api/families/{fam['id']}/members/{m['membership_id']}", json={"household_id": h["id"]})
    everyone = [m["user"]["id"] for m in members]

    seen = []                                        # (event, {giver: giftee})
    for n in range(4):
        ev = admin.post(f"/api/families/{fam['id']}/events",
                        json={"name": f"Event {n}", "event_date": future_date(30 + n)}).get_json()["event"]
        admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": everyone})
        r = admin.post(f"/api/events/{ev['id']}/assignments/generate")
        assert r.status_code == 200 and r.get_json()["repeated"] == 0
        draw = {}
        for c in clients.values():
            me = c.get("/api/auth/me").get_json()["user"]["id"]
            draw[me] = c.get(f"/api/events/{ev['id']}/assignments/mine").get_json()["giftee_user_id"]
        assert len(draw) == 6 and all(g != r for g, r in draw.items())
        seen.append(draw)

    # nobody drew the same person twice across the four events
    for giver in seen[0]:
        giftees = [draw[giver] for draw in seen]
        assert len(set(giftees)) == 4, giftees

    # and their conversations stay separate even though it's the same clan
    first, second = (admin.get(f"/api/families/{fam['id']}/events").get_json()[i] for i in (1, 0))
    admin.post(f"/api/events/{first['id']}/messages", json={"to": "giftee", "body": "only in the first"})
    thread = admin.get(f"/api/events/{second['id']}/messages").get_json()["giftee"]
    assert thread["messages"] == []


def test_gift_idea_notification_names_the_giftee(users):
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    ev = _drawn_event(users)
    bob_id = bob.get("/api/auth/me").get_json()["user"]["id"]
    santa = next(c for c in (admin, users[CARA_USER])
                 if c.get(f"/api/events/{ev['id']}/assignments/mine").get_json()["giftee_user_id"] == bob_id)
    bob.post(f"/api/events/{ev['id']}/wishlists", json={"item_name": "Boots"})
    assert santa.get("/api/notifications").get_json()["items"][0]["title"] == "Your giftee Bob added a gift idea"

    # with codenames on, it uses their codename instead of their real name
    fam = users["_family"]
    coded = admin.post(f"/api/families/{fam['id']}/events",
                       json={"name": "Coded", "event_date": future_date(45), "use_codenames": True}).get_json()["event"]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    admin.put(f"/api/events/{coded['id']}/participants", json={"user_ids": [m["user"]["id"] for m in members]})
    assert admin.post(f"/api/events/{coded['id']}/assignments/generate").status_code == 200
    santa = next(c for c in (admin, users[CARA_USER])
                 if c.get(f"/api/events/{coded['id']}/assignments/mine").get_json()["giftee_user_id"] == bob_id)
    bob.post(f"/api/events/{coded['id']}/wishlists", json={"item_name": "Hat"})
    title = santa.get("/api/notifications").get_json()["items"][0]["title"]
    assert title.startswith("Your giftee ") and title.endswith(" added a gift idea") and "Bob" not in title


def test_display_name_is_admin_only_however_it_is_sent(users):
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    fam = users["_family"]
    # a member can't change it through either field
    assert bob.patch("/api/auth/me", json={"display_name": "Bobby"}).status_code == 403
    assert bob.patch("/api/auth/me", json={"full_name": "Bobby"}).status_code == 403
    assert bob.get("/api/auth/me").get_json()["user"]["display_name"] == "Bob"
    # sending the current value back (the profile form does) is harmless
    assert bob.patch("/api/auth/me", json={"display_name": "", "likes": "Tea"}).status_code == 200

    # an admin can, but not to the username
    r = admin.patch("/api/auth/me", json={"full_name": "Ana Cruz"})
    assert r.status_code == 200 and r.get_json()["user"]["display_name"] == "Ana Cruz"
    r = admin.patch("/api/auth/me", json={"full_name": ADMIN_USER})
    assert r.status_code == 400 and "different from your username" in r.get_json()["error"]

    # same rule when the admin renames someone on the Members page; unchanged names still save
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    bob_m = next(m for m in members if m["user"]["username"] == BOB_USER)
    url = f"/api/families/{fam['id']}/members/{bob_m['membership_id']}"
    assert admin.patch(url, json={"full_name": BOB_USER}).status_code == 400
    assert admin.patch(url, json={"full_name": "Bob"}).status_code == 200
    assert admin.patch(url, json={"full_name": "Bob Reyes"}).status_code == 200
    assert bob.get("/api/auth/me").get_json()["user"]["display_name"] == "Bob Reyes"


def test_household_shows_on_me_and_on_profiles(users):
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    fam = users["_family"]
    assert bob.get("/api/auth/me").get_json()["families"][0]["household_name"] is None
    h = admin.post(f"/api/families/{fam['id']}/households", json={"name": "Reyes House"}).get_json()["household"]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    bob_m = next(m for m in members if m["user"]["username"] == BOB_USER)
    admin.patch(f"/api/families/{fam['id']}/members/{bob_m['membership_id']}", json={"household_id": h["id"]})
    assert bob.get("/api/auth/me").get_json()["families"][0]["household_name"] == "Reyes House"

    ev = admin.post(f"/api/families/{fam['id']}/events",
                    json={"name": "Xmas", "event_date": future_date()}).get_json()["event"]
    admin.put(f"/api/events/{ev['id']}/participants", json={"user_ids": [m["user"]["id"] for m in members]})
    for path in (f"/api/events/{ev['id']}/wishlists/clan", f"/api/events/{ev['id']}/wishlists"):
        entries = admin.get(path).get_json()
        got = {e["user"]["username"]: e["household_name"] for e in entries}
        assert got[BOB_USER] == "Reyes House" and got[CARA_USER] == ""


def test_admin_can_choose_a_username_when_adding_a_member(app, users):
    fam, admin, bob = users["_family"], users[ADMIN_USER], users[BOB_USER]
    url = f"/api/families/{fam['id']}/members"
    assert bob.post(url, json={"full_name": "Nope", "username": "nope1"}).status_code == 403

    r = admin.post(url, json={"full_name": "Lola Nena", "username": "  Lola.Nena "})
    assert r.status_code == 201 and r.get_json()["username"] == "lola.nena"     # tidied like a normal username
    signed_in = app.test_client().post("/api/auth/login-password", json={
        "username": "lola.nena", "password": r.get_json()["temp_password"]})
    assert signed_in.status_code == 200

    # taken, badly formed, or just the display name again -> refused with a plain message
    assert admin.post(url, json={"full_name": "Someone", "username": "lola.nena"}).status_code == 409
    assert admin.post(url, json={"full_name": "Someone", "username": "no spaces!"}).status_code == 400
    r = admin.post(url, json={"full_name": "tito", "username": "tito"})
    assert r.status_code == 400 and "different from the username" in r.get_json()["error"]

    # blank username: generated from the display name, and never identical to it
    r = admin.post(url, json={"full_name": "Eve Tan", "username": ""})
    assert r.status_code == 201 and r.get_json()["username"] == "evetan"
    r = admin.post(url, json={"full_name": "tita", "username": ""})
    assert r.status_code == 201 and r.get_json()["username"] != "tita"



def test_members_only_see_the_events_they_are_joining(users):
    fam, admin, bob, cara = users["_family"], users[ADMIN_USER], users[BOB_USER], users[CARA_USER]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    uid = {m["user"]["username"]: m["user"]["id"] for m in members}
    mine = admin.post(f"/api/families/{fam['id']}/events",
                      json={"name": "Bob is in", "event_date": future_date()}).get_json()["event"]
    other = admin.post(f"/api/families/{fam['id']}/events",
                       json={"name": "Bob is out", "event_date": future_date(40)}).get_json()["event"]
    admin.put(f"/api/events/{mine['id']}/participants", json={"user_ids": [uid[ADMIN_USER], uid[BOB_USER], uid[CARA_USER]]})
    admin.put(f"/api/events/{other['id']}/participants", json={"user_ids": [uid[ADMIN_USER], uid[CARA_USER]]})
    bob.post(f"/api/events/{mine['id']}/wishlists", json={"item_name": "Boots"})

    # the list: members see only their events, the clan admin sees all of them
    assert [e["name"] for e in bob.get(f"/api/families/{fam['id']}/events").get_json()] == ["Bob is in"]
    assert {e["name"] for e in cara.get(f"/api/families/{fam['id']}/events").get_json()} == {"Bob is in", "Bob is out"}
    assert {e["name"] for e in admin.get(f"/api/families/{fam['id']}/events").get_json()} == {"Bob is in", "Bob is out"}

    # inside an event Bob isn't joining he gets nothing: not the event, its people, wishlists, dishes or messages
    eid = other["id"]
    for path in (f"/api/events/{eid}", f"/api/events/{eid}/attendees", f"/api/events/{eid}/wishlists/clan",
                 f"/api/events/{eid}/wishlists/mine", f"/api/events/{eid}/dishes", f"/api/events/{eid}/messages",
                 f"/api/events/{eid}/assignments/mine", f"/api/events/{eid}/participants"):
        assert bob.get(path).status_code == 403, path
    assert bob.post(f"/api/events/{eid}/wishlists", json={"item_name": "Sneaky"}).status_code == 403
    assert bob.post(f"/api/events/{eid}/messages", json={"to": "giftee", "body": "hi"}).status_code == 403
    assert bob.put(f"/api/events/{eid}/dishes/mine", json={"dishes": ["x"]}).status_code == 403
    # ...but the clan admin can open any event, and Bob's own event works as before
    assert admin.get(f"/api/events/{eid}").status_code == 200
    assert bob.get(f"/api/events/{mine['id']}/attendees").status_code == 200
    # the clan list in his event doesn't include people from events he's not in - only this event's people
    clan = bob.get(f"/api/events/{mine['id']}/wishlists/clan").get_json()
    assert sorted(e["user"]["username"] for e in clan) == sorted([ADMIN_USER, BOB_USER, CARA_USER])

    # being added to the event gives access; being removed takes it away again
    admin.put(f"/api/events/{eid}/participants", json={"user_ids": [uid[ADMIN_USER], uid[CARA_USER], uid[BOB_USER]]})
    assert bob.get(f"/api/events/{eid}").status_code == 200
    admin.put(f"/api/events/{eid}/participants", json={"user_ids": [uid[ADMIN_USER], uid[CARA_USER]]})
    assert bob.get(f"/api/events/{eid}").status_code == 403


def test_add_member_takes_household_and_admin_role_like_editing_does(app, users):
    fam, admin, bob = users["_family"], users[ADMIN_USER], users[BOB_USER]
    url = f"/api/families/{fam['id']}/members"
    house = admin.post(f"/api/families/{fam['id']}/households", json={"name": "Lola House"}).get_json()["household"]

    r = admin.post(url, json={"full_name": "Lola Nena", "household_id": house["id"], "role": "admin",
                              "phone": "(555) 010-9999", "email": "lola@example.com"})
    assert r.status_code == 201
    body = r.get_json()
    assert (body["role"], body["household_id"]) == ("admin", house["id"])
    members = admin.get(url).get_json()
    lola = next(m for m in members if m["user"]["full_name"] == "Lola Nena")
    assert (lola["role"], lola["household_name"], lola["user"]["email"]) == ("admin", "Lola House", "lola@example.com")

    # defaults: plain member, no household
    r = admin.post(url, json={"full_name": "Plain Person"})
    assert (r.get_json()["role"], r.get_json()["household_id"]) == ("member", None)

    # bad household (not this clan's) or a made-up role is refused, and nothing is created
    before = len(admin.get(url).get_json())
    assert admin.post(url, json={"full_name": "Bad House", "household_id": 99999}).status_code == 400
    assert admin.post(url, json={"full_name": "Bad Role", "role": "owner"}).status_code == 400
    assert len(admin.get(url).get_json()) == before
    assert bob.post(url, json={"full_name": "Nope", "role": "admin"}).status_code == 403


def test_admin_can_edit_a_members_username(app, users):
    fam, admin, bob = users["_family"], users[ADMIN_USER], users[BOB_USER]
    members = admin.get(f"/api/families/{fam['id']}/members").get_json()
    bob_m = next(m for m in members if m["user"]["username"] == BOB_USER)
    assert bob_m["user"]["username"] == BOB_USER                      # the members list carries it (the edit row shows it)
    url = f"/api/families/{fam['id']}/members/{bob_m['membership_id']}"

    # changed, tidied like any username, and the person signs in with the new one
    assert admin.patch(url, json={"username": "  Bobby.R "}).status_code == 200
    assert app.test_client().post("/api/auth/login-password",
                                  json={"username": "bobby.r", "password": PASSWORD}).status_code == 200
    assert app.test_client().post("/api/auth/login-password",
                                  json={"username": BOB_USER, "password": PASSWORD}).status_code == 401

    # taken / badly formed / the same as the display name -> refused, nothing changes
    assert admin.patch(url, json={"username": CARA_USER}).status_code == 409
    assert admin.patch(url, json={"username": "no spaces!"}).status_code == 400
    r = admin.patch(url, json={"username": "Bob", "full_name": "bob"})               # "Bob" is tidied to "bob" == display "bob"
    assert r.status_code == 400 and "different from the username" in r.get_json()["error"]
    assert next(m for m in admin.get(f"/api/families/{fam['id']}/members").get_json()
                if m["membership_id"] == bob_m["membership_id"])["user"]["username"] == "bobby.r"

    # the edit row sends every field on Save; unchanged values (even an old account whose
    # display name equals its username) must still save
    from app.models import User
    User.query.filter_by(username="bobby.r").first().full_name = "bobby.r"
    db.session.commit()
    assert admin.patch(url, json={"full_name": "bobby.r", "username": "bobby.r", "phone": "", "email": ""}).status_code == 200

    # members can't
    assert bob.patch(url, json={"username": "hax"}).status_code == 403
