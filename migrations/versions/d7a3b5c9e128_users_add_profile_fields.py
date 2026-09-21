"""users: add about_me, likes, favorite_color, avoid_gifts (profile)

Revision ID: d7a3b5c9e128
Revises: c41f9a7e2b10
Create Date: 2026-09-21 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7a3b5c9e128'
down_revision = 'c41f9a7e2b10'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('about_me', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('likes', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('favorite_color', sa.String(length=40), nullable=True))
    op.add_column('users', sa.Column('avoid_gifts', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('users', 'avoid_gifts')
    op.drop_column('users', 'favorite_color')
    op.drop_column('users', 'likes')
    op.drop_column('users', 'about_me')
