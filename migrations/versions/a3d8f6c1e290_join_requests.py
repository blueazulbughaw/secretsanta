"""join_requests: joining a clan with its code waits for a clan admin's approval

Revision ID: a3d8f6c1e290
Revises: c7f1e9a2d405
Create Date: 2026-10-12 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3d8f6c1e290'
down_revision = 'c7f1e9a2d405'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'join_requests',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), primary_key=True),
        sa.Column('family_id', sa.BigInteger(), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('family_id', 'user_id', name='uq_join_request'),
        mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_unicode_ci',
    )
    op.create_index('ix_join_requests_family_id', 'join_requests', ['family_id'])
    op.create_index('ix_join_requests_user_id', 'join_requests', ['user_id'])


def downgrade():
    op.drop_index('ix_join_requests_user_id', table_name='join_requests')
    op.drop_index('ix_join_requests_family_id', table_name='join_requests')
    op.drop_table('join_requests')
