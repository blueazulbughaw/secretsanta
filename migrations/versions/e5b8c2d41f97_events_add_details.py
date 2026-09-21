"""events: add event_time, location, theme, rules, what_to_bring, other_info

Revision ID: e5b8c2d41f97
Revises: d7a3b5c9e128
Create Date: 2026-09-21 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5b8c2d41f97'
down_revision = 'd7a3b5c9e128'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('event_time', sa.Time(), nullable=True))
    op.add_column('events', sa.Column('location', sa.String(length=255), nullable=True))
    op.add_column('events', sa.Column('theme', sa.String(length=120), nullable=True))
    op.add_column('events', sa.Column('rules', sa.Text(), nullable=True))
    op.add_column('events', sa.Column('what_to_bring', sa.Text(), nullable=True))
    op.add_column('events', sa.Column('other_info', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('events', 'other_info')
    op.drop_column('events', 'what_to_bring')
    op.drop_column('events', 'rules')
    op.drop_column('events', 'theme')
    op.drop_column('events', 'location')
    op.drop_column('events', 'event_time')
