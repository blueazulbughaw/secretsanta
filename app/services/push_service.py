"""Web Push: sends a notification to every phone/computer a person turned notifications on
for (Profile & Security > "Notifications on this device", stored in push_subscriptions).

Needs VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY (see config.py); without them nothing is sent
and the in-app bell works as before. Sending is best-effort: a failure is logged and never
breaks the request that caused the notification."""
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from flask import current_app

from ..extensions import db
from ..models import PushSubscription

log = logging.getLogger(__name__)
TIMEOUT_SECONDS = 5
MAX_PARALLEL = 8


def enabled():
    return bool(current_app.config.get("VAPID_PUBLIC_KEY") and current_app.config.get("VAPID_PRIVATE_KEY"))


def _send_one(sub, payload, private_key, claims):
    """Returns the subscription's id if the push service says it's gone for good."""
    from pywebpush import webpush, WebPushException
    try:
        webpush(subscription_info={"endpoint": sub["endpoint"],
                                   "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
                data=payload, vapid_private_key=private_key, vapid_claims=dict(claims),
                timeout=TIMEOUT_SECONDS, ttl=86400)
    except WebPushException as e:
        status = getattr(e.response, "status_code", None)
        if status in (404, 410):  # unsubscribed, or the browser dropped it
            return sub["id"]
        log.warning("Web push failed (%s)", status or type(e).__name__)
    except Exception as e:  # network trouble etc. - never break the caller
        log.warning("Web push failed (%s)", type(e).__name__)
    return None


def send(notifications):
    """Pushes each (already saved) Notification to its person's devices."""
    if not notifications or not enabled():
        return
    by_user = {}
    for s in PushSubscription.query.filter(
            PushSubscription.user_id.in_({n.user_id for n in notifications})).all():
        by_user.setdefault(s.user_id, []).append(
            {"id": s.id, "endpoint": s.endpoint, "p256dh": s.p256dh_key, "auth": s.auth_key})
    jobs = []
    for n in notifications:
        payload = json.dumps({"id": n.id, "title": n.title, "body": n.body or "",
                              "link_path": n.link_path or "/"})
        jobs += [(sub, payload) for sub in by_user.get(n.user_id, [])]
    if not jobs:
        return
    private_key = current_app.config["VAPID_PRIVATE_KEY"]
    claims = {"sub": current_app.config.get("VAPID_SUBJECT") or "https://secretsanta.glad.codes"}
    with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(jobs))) as pool:
        dead = {i for i in pool.map(lambda j: _send_one(j[0], j[1], private_key, claims), jobs) if i}
    if dead:
        PushSubscription.query.filter(PushSubscription.id.in_(dead)).delete(synchronize_session=False)
    sent_to = {n.user_id for n in notifications if by_user.get(n.user_id)}
    now = datetime.utcnow()
    for n in notifications:
        if n.user_id in sent_to:
            n.push_sent_at = now
    db.session.commit()
