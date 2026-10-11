"""add rate_limit_hits (IP rate limits shared by every app process)

Revision ID: b4e7d2a9c316
Revises: c8e1a3b5d724
Create Date: 2026-10-11 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4e7d2a9c316'
down_revision = 'c8e1a3b5d724'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'rate_limit_hits',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('bucket', sa.String(length=20), nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rate_limit_lookup', 'rate_limit_hits', ['bucket', 'ip', 'created_at'], unique=False)


def downgrade():
    op.drop_index('ix_rate_limit_lookup', table_name='rate_limit_hits')
    op.drop_table('rate_limit_hits')
