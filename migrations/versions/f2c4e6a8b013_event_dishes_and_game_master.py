"""events: add game_master_id; add event_dishes (dish sign-up)

Revision ID: f2c4e6a8b013
Revises: e5b8c2d41f97
Create Date: 2026-09-21 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2c4e6a8b013'
down_revision = 'e5b8c2d41f97'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'event_dishes',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), nullable=False),
        sa.Column('event_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_event_dishes_event_id'), 'event_dishes', ['event_id'], unique=False)
    op.create_index(op.f('ix_event_dishes_user_id'), 'event_dishes', ['user_id'], unique=False)
    op.add_column('events', sa.Column('game_master_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_events_game_master', 'events', 'users',
                          ['game_master_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('fk_events_game_master', 'events', type_='foreignkey')
    op.drop_column('events', 'game_master_id')
    op.drop_index(op.f('ix_event_dishes_user_id'), table_name='event_dishes')
    op.drop_index(op.f('ix_event_dishes_event_id'), table_name='event_dishes')
    op.drop_table('event_dishes')
