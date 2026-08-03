"""Phase 2: Auth additions — must_change_password column on users.

Revision ID: 002
Revises: 001
Create Date: 2026-07-30

Adds ``must_change_password`` column to the ``users`` table so the auth
layer can force system_seed and other seed accounts to change their
password before accessing protected endpoints.
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

_backend_root = Path(__file__).resolve().parents[2]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect
    cols = inspect(op.get_bind()).get_columns(table)
    return any(c["name"] == column for c in cols)


def _table_exists(table: str) -> bool:
    from sqlalchemy import inspect
    return inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    # ── Add must_change_password column ───────────────────────────
    if _table_exists("users") and not _column_exists("users", "must_change_password"):
        with op.batch_alter_table("users") as batch:
            batch.add_column(
                sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            )

    # ── Flag all inactive / seed accounts for password change ────
    # Any user that is not yet active should be forced to set a real
    # password before accessing the system.
    op.execute(
        sa.text(
            "UPDATE users SET must_change_password = 1 WHERE is_active = 0"
        )
    )


def downgrade() -> None:
    if _table_exists("users") and _column_exists("users", "must_change_password"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("must_change_password")
