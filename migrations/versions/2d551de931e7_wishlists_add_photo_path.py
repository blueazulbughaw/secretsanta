"""wishlists: add photo_path

Revision ID: 2d551de931e7
Revises: b863d14a1ff7
Create Date: 2026-07-15 08:10:20.460968

Autogenerate also flagged an unrelated pre-existing drift (ix_users_phone
unique=False vs True) between this dev sqlite baseline and current models.py -
left untouched here since it isn't part of this change and production's
actual index state wasn't verified.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2d551de931e7'
down_revision = 'b863d14a1ff7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('wishlists', sa.Column('photo_path', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('wishlists', 'photo_path')
