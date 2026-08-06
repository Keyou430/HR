"""Task deadline + overdue notifications

- Replace due_time VARCHAR(8) with deadline VARCHAR(32) (ISO datetime)
- Add overdue_notified_at VARCHAR(32) (ISO datetime, for notification dedup)
- Add status index for overdue queries
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns (nullable first, data migration follows)
    op.execute(
        "ALTER TABLE portal_tasks ADD COLUMN deadline VARCHAR(32) DEFAULT NULL"
    )
    op.execute(
        "ALTER TABLE portal_tasks ADD COLUMN overdue_notified_at VARCHAR(32) DEFAULT NULL"
    )

    # 2. Drop old due_time column (no reliable conversion possible — time-only string)
    # SQLite doesn't support DROP COLUMN natively via ALTER, so use batch mode
    with op.batch_alter_table("portal_tasks") as batch_op:
        batch_op.drop_column("due_time")

    # 3. Index for overdue scanning
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_portal_tasks_overdue_scan "
        "ON portal_tasks (done, deadline, overdue_notified_at)"
    )


def downgrade() -> None:
    with op.batch_alter_table("portal_tasks") as batch_op:
        batch_op.add_column(sa.Column("due_time", sa.String(8), nullable=True))
    op.execute("ALTER TABLE portal_tasks DROP COLUMN deadline")
    op.execute("ALTER TABLE portal_tasks DROP COLUMN overdue_notified_at")
    op.execute("DROP INDEX IF EXISTS ix_portal_tasks_overdue_scan")
