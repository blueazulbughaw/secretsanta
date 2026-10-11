"""users: session_version (sign out everywhere); favorite_color holds picked colors

Revision ID: c7f1e9a2d405
Revises: b4e7d2a9c316
Create Date: 2026-10-11 15:00:00.000000

"""
import re

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7f1e9a2d405'
down_revision = 'b4e7d2a9c316'
branch_labels = None
depends_on = None

# favorite_color used to be free text ("Teal"); it's now "#rrggbb,..." from a color
# picker. Common color names carry over; anything else can't be turned into a color.
NAMED = {
    "black": "#000000", "white": "#ffffff", "gray": "#808080", "grey": "#808080",
    "silver": "#c0c0c0", "red": "#ff0000", "maroon": "#800000", "crimson": "#dc143c",
    "pink": "#ffc0cb", "hot pink": "#ff69b4", "orange": "#ffa500", "coral": "#ff7f50",
    "yellow": "#ffff00", "gold": "#ffd700", "beige": "#f5f5dc", "brown": "#a52a2a",
    "tan": "#d2b48c", "green": "#008000", "lime": "#00ff00", "olive": "#808000",
    "mint": "#98ff98", "sage": "#9caf88", "sage green": "#9caf88", "emerald": "#50c878",
    "teal": "#008080", "turquoise": "#40e0d0", "aqua": "#00ffff", "cyan": "#00ffff",
    "blue": "#0000ff", "navy": "#000080", "navy blue": "#000080", "sky blue": "#87ceeb",
    "light blue": "#add8e6", "royal blue": "#4169e1", "purple": "#800080",
    "violet": "#ee82ee", "lavender": "#e6e6fa", "lilac": "#c8a2c8", "magenta": "#ff00ff",
    "burgundy": "#800020",
}


def _to_colors(text):
    out = []
    for part in re.split(r"[,/&]| and ", (text or "").lower()):
        part = part.strip()
        hexed = part if re.fullmatch(r"#[0-9a-f]{6}", part) else NAMED.get(part)
        if hexed and hexed not in out:
            out.append(hexed)
    return ",".join(out[:8]) or None


def upgrade():
    with op.batch_alter_table('users') as t:
        t.add_column(sa.Column('session_version', sa.Integer(), nullable=False, server_default='0'))
        t.alter_column('favorite_color', existing_type=sa.String(length=40), type_=sa.String(length=80))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, favorite_color FROM users WHERE favorite_color IS NOT NULL")).fetchall()
    for uid, text in rows:
        conn.execute(sa.text("UPDATE users SET favorite_color = :c WHERE id = :id"),
                     {"c": _to_colors(text), "id": uid})


def downgrade():
    with op.batch_alter_table('users') as t:
        t.alter_column('favorite_color', existing_type=sa.String(length=80), type_=sa.String(length=40))
        t.drop_column('session_version')
