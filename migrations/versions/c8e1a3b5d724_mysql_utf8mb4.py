"""mysql: convert the database and every table from latin1 to utf8mb4

The database was created as latin1, which can't hold emoji or most non-Latin
text: anything like a notification title with a gift emoji was saved as "?".
utf8mb4 keeps them. MySQL/MariaDB only (SQLite has no such problem).

Revision ID: c8e1a3b5d724
Revises: a9c1d3e5f702
Create Date: 2026-09-21 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8e1a3b5d724'
down_revision = 'a9c1d3e5f702'
branch_labels = None
depends_on = None

CHARSET = "utf8mb4"
COLLATION = "utf8mb4_unicode_ci"


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    db_name = bind.execute(sa.text("SELECT DATABASE()")).scalar()
    try:
        # new tables then default to utf8mb4 too
        op.execute(f"ALTER DATABASE `{db_name}` CHARACTER SET {CHARSET} COLLATE {COLLATION}")
    except Exception as exc:  # e.g. no ALTER privilege on the database itself
        print(f"warning: could not change the database default charset: {exc}")
    tables = bind.execute(sa.text(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' "
        "AND TABLE_NAME <> 'alembic_version' AND TABLE_COLLATION NOT LIKE 'utf8mb4%'")).scalars().all()
    for table in tables:
        op.execute(f"ALTER TABLE `{table}` CONVERT TO CHARACTER SET {CHARSET} COLLATE {COLLATION}")


def downgrade():
    # Not reversible: text already saved with emoji can't go back to latin1.
    pass
