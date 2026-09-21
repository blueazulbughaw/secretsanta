"""users: add photo_path (profile photo)

Revision ID: c41f9a7e2b10
Revises: 946a98182b33
Create Date: 2026-09-21 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c41f9a7e2b10'
down_revision = '946a98182b33'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('photo_path', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('users', 'photo_path')
