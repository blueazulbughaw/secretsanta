from ..extensions import db
from ..models import Notification


def notify(user_id, type_, title, body=None, link_path=None):
    n = Notification(user_id=user_id, type=type_, title=title,
                     body=body, link_path=link_path)
    db.session.add(n)
    db.session.commit()
    # Future: if user has push_subscriptions, send Web Push here.
    return n
