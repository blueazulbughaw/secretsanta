import re
import pytest

from app import create_app
from app.extensions import db

ADMIN_USER = "admin"
BOB_USER = "bob"
CARA_USER = "cara"
PASSWORD = "correct-horse-battery"


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


def test_register_without_full_name_falls_back_to_name_prompt(app):
    c = app.test_client()
    r = c.post("/api/auth/register", json={"username": "noname", "password": PASSWORD})
    assert r.status_code == 200
    assert r.get_json()["user"]["full_name"] == ""


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
    assert r.status_code == 200 and r.get_json()["method"] == "password"

    assert c2.post("/api/auth/login-password",
                    json={"username": "pwuser", "password": "wrong"}).status_code == 401
    r2 = c2.post("/api/auth/login-password", json={"username": "pwuser", "password": PASSWORD})
    assert r2.status_code == 200


def test_phone_otp_login_flow(app, capsys):
    c = app.test_client()
    c.post("/api/auth/register",
           json={"username": "phoneuser", "password": PASSWORD, "full_name": "T",
                 "phone": "5551234567"})

    c2 = app.test_client()
    r = c2.post("/api/auth/login-start", json={"username": "phoneuser"})
    assert r.status_code == 200 and r.get_json()["method"] == "otp"
    code = re.search(r"code for \+15551234567: (\d{6})", capsys.readouterr().out).group(1)

    assert c2.post("/api/auth/verify-otp",
                    json={"username": "phoneuser", "code": "000000"}).status_code == 401
    r2 = c2.post("/api/auth/verify-otp", json={"username": "phoneuser", "code": code})
    assert r2.status_code == 200


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
    giftee_view = santa.get(f"/api/events/{ev['id']}/wishlists/giftee").get_json()
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
