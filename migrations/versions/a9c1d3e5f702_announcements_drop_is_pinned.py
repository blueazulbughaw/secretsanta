"""announcements: drop is_pinned (is_published already means "shown on the dashboard")

Revision ID: a9c1d3e5f702
Revises: f2c4e6a8b013
Create Date: 2026-09-21 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a9c1d3e5f702'
down_revision = 'f2c4e6a8b013'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('announcements', 'is_pinned')


def downgrade():
    op.add_column('announcements', sa.Column('is_pinned', sa.Boolean(), nullable=False,
                                             server_default=sa.false()))
