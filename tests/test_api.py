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
    """Signs up admin + two members (username + password), returns logged-in clients."""
    clients = {}
    for username, name in [(ADMIN_USER, "Ana"), (BOB_USER, "Bob"), (CARA_USER, "Cara")]:
        c = app.test_client()
        r = c.post("/api/auth/signup", json={"username": username})
        assert r.status_code == 200
        c.patch("/api/auth/security", json={"password": PASSWORD})
        c.patch("/api/auth/me", json={"full_name": name})
        clients[username] = c
    with app.app_context():
        from app.models import User
        admin = User.query.filter_by(username=ADMIN_USER).first()
        admin.is_app_admin = True
        db.session.commit()
    return clients


def setup_family(users):
    admin = users[ADMIN_USER]
    fam = admin.post("/api/families", json={"name": "Test Fam"}).get_json()["family"]
    for username in (BOB_USER, CARA_USER):
        users[username].post("/api/families/join", json={"join_code": fam["join_code"]})
    return fam


def test_signup_requires_unique_username(app):
    c = app.test_client()
    assert c.post("/api/auth/signup", json={"username": "taken"}).status_code == 200
    c2 = app.test_client()
    assert c2.post("/api/auth/signup", json={"username": "taken"}).status_code == 409


def test_login_start_unknown_username(app):
    c = app.test_client()
    r = c.post("/api/auth/login-start", json={"username": "nobody"})
    assert r.status_code == 404


def test_password_login_flow(app):
    c = app.test_client()
    c.post("/api/auth/signup", json={"username": "pwuser"})
    c.patch("/api/auth/security", json={"password": PASSWORD})
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
    c.post("/api/auth/signup", json={"username": "phoneuser"})
    c.patch("/api/auth/security", json={"phone": "5551234567"})

    c2 = app.test_client()
    r = c2.post("/api/auth/login-start", json={"username": "phoneuser"})
    assert r.status_code == 200 and r.get_json()["method"] == "otp"
    code = re.search(r"code for \+15551234567: (\d{6})", capsys.readouterr().out).group(1)

    assert c2.post("/api/auth/verify-otp",
                    json={"username": "phoneuser", "code": "000000"}).status_code == 401
    r2 = c2.post("/api/auth/verify-otp", json={"username": "phoneuser", "code": code})
    assert r2.status_code == 200


def test_family_creation_restricted_to_app_admins(users):
    admin, bob = users[ADMIN_USER], users[BOB_USER]
    assert admin.post("/api/families", json={"name": "Allowed"}).status_code == 201
    assert bob.post("/api/families", json={"name": "Not allowed"}).status_code == 403


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
