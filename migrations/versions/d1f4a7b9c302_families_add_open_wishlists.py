"""families: add open_wishlists

Revision ID: d1f4a7b9c302
Revises: b6e2c9d4f813
Create Date: 2026-10-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1f4a7b9c302'
down_revision = 'b6e2c9d4f813'
branch_labels = None
depends_on = None


def upgrade():
    # Existing clans keep today's behaviour: everyone sees every wishlist.
    op.add_column('families', sa.Column('open_wishlists', sa.Boolean(),
                                        nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column('families', 'open_wishlists')
