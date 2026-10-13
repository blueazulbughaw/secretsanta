from ..extensions import db
from ..models import Notification
from . import push_service


def notify_many(user_ids, type_, title, body=None, link_path=None, *,
                family_id=None, event_id=None, announcement_id=None):
    """One notification per person: shown in the app's bell, and pushed to their phones if
    they turned that on. family_id / event_id / announcement_id say what it's about, so
    deleting that also deletes the notification."""
    ns = [Notification(user_id=uid, type=type_, title=title, body=body, link_path=link_path,
                       family_id=family_id, event_id=event_id, announcement_id=announcement_id)
          for uid in user_ids]
    if not ns:
        return []
    db.session.add_all(ns)
    db.session.commit()
    push_service.send(ns)
    return ns


def notify(user_id, type_, title, body=None, link_path=None, **about):
    return notify_many([user_id], type_, title, body, link_path, **about)[0]
