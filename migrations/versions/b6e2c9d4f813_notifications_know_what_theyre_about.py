"""notifications: family_id / event_id / announcement_id, so deleting those deletes them

Also cleans up what's already there: a notification about an event or announcement that
has since been deleted is removed, and the rest are linked to what they're about.

Revision ID: b6e2c9d4f813
Revises: a3d8f6c1e290
Create Date: 2026-10-13 12:00:00.000000

"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6e2c9d4f813'
down_revision = 'a3d8f6c1e290'
branch_labels = None
depends_on = None

COLUMNS = ('family_id', 'event_id', 'announcement_id')


def upgrade():
    for col in COLUMNS:
        op.add_column('notifications', sa.Column(col, sa.BigInteger(), nullable=True))
        op.create_index(f'ix_notifications_{col}', 'notifications', [col])

    conn = op.get_bind()
    events = dict(conn.execute(sa.text("SELECT id, family_id FROM events")).fetchall())
    # An announcement's notification body is "<title>: <message>" cut to 200 characters
    # (see post_announcement), which is the only way to tell which one it was about.
    anns = {}
    for aid, fid, eid, title, body in conn.execute(sa.text(
            "SELECT id, family_id, event_id, title, body FROM announcements")).fetchall():
        anns[f"{title}: {body}"[:200]] = (aid, fid, eid)

    gone, links = [], []
    for nid, ntype, body, link in conn.execute(sa.text(
            "SELECT id, type, body, link_path FROM notifications")).fetchall():
        if ntype == "announcement":
            match = anns.get(body or "")
            if not match:
                gone.append(nid)
            else:
                links.append({"id": nid, "a": match[0], "f": match[1], "e": match[2]})
            continue
        m = re.match(r"^/events/(\d+)", link or "")
        if m:
            eid = int(m.group(1))
            if eid not in events:
                gone.append(nid)
            else:
                links.append({"id": nid, "a": None, "f": events[eid], "e": eid})
    for nid in gone:
        conn.execute(sa.text("DELETE FROM notifications WHERE id = :id"), {"id": nid})
    for row in links:
        conn.execute(sa.text("UPDATE notifications SET announcement_id = :a, family_id = :f, "
                             "event_id = :e WHERE id = :id"), row)


def downgrade():
    for col in reversed(COLUMNS):
        op.drop_index(f'ix_notifications_{col}', table_name='notifications')
        op.drop_column('notifications', col)
