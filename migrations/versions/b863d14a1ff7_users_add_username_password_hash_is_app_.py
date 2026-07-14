"""users: add username/password_hash/is_app_admin, phone optional

Revision ID: b863d14a1ff7
Revises: 6b1517b587a9
Create Date: 2026-07-14 08:03:33.344441

Backfills a placeholder username (derived from phone, or "userN") for any
pre-existing rows before making the column NOT NULL UNIQUE, so this is safe
to run against a non-empty users table.

Written as explicit raw SQL per dialect rather than op.batch_alter_table():
Alembic's SQLite batch mode reflects the "copy from" table using the app's
live SQLAlchemy metadata (models.py) when available, not strict historical
DB state - so on SQLite it can intermittently pull in columns models.py
already defines for a *later* migration, causing spurious "duplicate
column"/"table already exists" failures when the chain is replayed fresh
in dev. Doing this by hand sidesteps that entirely. MySQL (production)
supports these ALTER statements natively with no rebuild needed either way.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b863d14a1ff7'
down_revision = '6b1517b587a9'
branch_labels = None
depends_on = None


def _backfill_usernames(conn):
    users_table = sa.table('users', sa.column('id', sa.Integer),
                            sa.column('username', sa.String), sa.column('phone', sa.String))
    for row in conn.execute(sa.select(users_table.c.id, users_table.c.phone)):
        placeholder = row.phone.lstrip('+') if row.phone else f'user{row.id}'
        conn.execute(users_table.update()
                     .where(users_table.c.id == row.id, users_table.c.username.is_(None))
                     .values(username=placeholder))


def upgrade():
    conn = op.get_bind()

    if conn.dialect.name == "sqlite":
        conn.exec_driver_sql("ALTER TABLE users ADD COLUMN username VARCHAR(60)")
        conn.exec_driver_sql("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)")
        conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN is_app_admin BOOLEAN NOT NULL DEFAULT 0")
        _backfill_usernames(conn)

        conn.exec_driver_sql("""
            CREATE TABLE users_new (
                id INTEGER NOT NULL PRIMARY KEY,
                username VARCHAR(60) NOT NULL,
                phone VARCHAR(30),
                email VARCHAR(255),
                password_hash VARCHAR(255),
                is_app_admin BOOLEAN NOT NULL,
                full_name VARCHAR(120) NOT NULL,
                display_name VARCHAR(60),
                avatar_color VARCHAR(7) NOT NULL,
                is_active BOOLEAN NOT NULL,
                last_login_at DATETIME,
                created_at DATETIME NOT NULL
            )
        """)
        conn.exec_driver_sql("""
            INSERT INTO users_new (id, username, phone, email, password_hash, is_app_admin,
                                    full_name, display_name, avatar_color, is_active,
                                    last_login_at, created_at)
            SELECT id, username, phone, email, password_hash, is_app_admin,
                   full_name, display_name, avatar_color, is_active, last_login_at, created_at
            FROM users
        """)
        conn.exec_driver_sql("DROP TABLE users")
        conn.exec_driver_sql("ALTER TABLE users_new RENAME TO users")
        conn.exec_driver_sql("CREATE UNIQUE INDEX ix_users_username ON users (username)")
        conn.exec_driver_sql("CREATE INDEX ix_users_phone ON users (phone)")
        conn.exec_driver_sql("CREATE UNIQUE INDEX ix_users_email ON users (email)")
    else:
        op.add_column('users', sa.Column('username', sa.String(length=60), nullable=True))
        op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=True))
        op.add_column('users', sa.Column('is_app_admin', sa.Boolean(), nullable=False,
                                          server_default=sa.false()))
        _backfill_usernames(conn)
        op.alter_column('users', 'username', existing_type=sa.String(length=60), nullable=False)
        op.alter_column('users', 'phone', existing_type=sa.VARCHAR(length=30), nullable=True)
        op.alter_column('users', 'is_app_admin', server_default=None)
        op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_username'))
        batch_op.alter_column('phone', existing_type=sa.VARCHAR(length=30), nullable=False)
        batch_op.drop_column('is_app_admin')
        batch_op.drop_column('password_hash')
        batch_op.drop_column('username')
