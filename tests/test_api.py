import re
import pytest

from app import create_app
from app.extensions import db

ADMIN_PHONE = "+15550000001"
BOB_PHONE = "+15550000002"
CARA_PHONE = "+15550000003"


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
def users(app, capsys):
    """Creates admin + two members via the real OTP flow (codes read from console)."""
    clients = {}
    for phone, name in [(ADMIN_PHONE, "Ana"),
                        (BOB_PHONE, "Bob"),
                        (CARA_PHONE, "Cara")]:
        c = app.test_client()
        c.post("/api/auth/request-otp", json={"phone": phone})
        code = re.search(r"code for {}: (\d{{6}})".format(re.escape(phone)),
                         capsys.readouterr().out).group(1)
        r = c.post("/api/auth/verify-otp", json={"phone": phone, "code": code})
        assert r.status_code == 200
        c.patch("/api/auth/me", json={"full_name": name})
        clients[phone] = c
    return clients


def setup_family(users):
    admin = users[ADMIN_PHONE]
    fam = admin.post("/api/families", json={"name": "Test Fam"}).get_json()["family"]
    for phone in (BOB_PHONE, CARA_PHONE):
        users[phone].post("/api/families/join", json={"join_code": fam["join_code"]})
    return fam


def test_wrong_otp_rejected(app):
    c = app.test_client()
    c.post("/api/auth/request-otp", json={"phone": "+15559999999"})
    r = c.post("/api/auth/verify-otp", json={"phone": "+15559999999", "code": "000000"})
    assert r.status_code == 401


def test_full_flow_and_privacy(app, users):
    fam = setup_family(users)
    admin, bob, cara = (users[ADMIN_PHONE], users[BOB_PHONE], users[CARA_PHONE])

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
