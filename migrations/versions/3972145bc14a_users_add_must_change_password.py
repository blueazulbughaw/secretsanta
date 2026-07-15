"""users: add must_change_password

Revision ID: 3972145bc14a
Revises: 2d551de931e7
Create Date: 2026-07-15 10:00:45.150971

NOT NULL with a server_default so this applies cleanly to the existing,
non-empty production users table. Autogenerate also flagged the same
unrelated ix_users_phone drift noted in 2d551de931e7 - left untouched again.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3972145bc14a'
down_revision = '2d551de931e7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(),
                                      nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('users', 'must_change_password')
