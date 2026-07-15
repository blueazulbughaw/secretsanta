"""announcements: add is_published

Revision ID: 946a98182b33
Revises: 3972145bc14a
Create Date: 2026-07-15 13:28:00.602063

NOT NULL with a server_default so this applies cleanly to the existing,
non-empty production announcements table. Autogenerate also flagged the
same unrelated ix_users_phone drift noted in prior migrations - left
untouched again.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '946a98182b33'
down_revision = '3972145bc14a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('announcements', sa.Column('is_published', sa.Boolean(),
                                              nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column('announcements', 'is_published')
