"""Phase 4: Chat session user scoping — add user_id to chat_sessions.

Revision ID: 003
Revises: 002
Create Date: 2026-08-03

Adds ``user_id`` column to the ``chat_sessions`` table so chat history is
isolated per-user (Phase 4 review P1-1 fix).  Existing sessions are
backfilled to ``system_seed`` (user 1).
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

_backend_root = Path(__file__).resolve().parents[2]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

revision: str = "003"
down_revision: Union[str, None] = "002"
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
    if _table_exists("chat_sessions") and not _column_exists("chat_sessions", "user_id"):
        with op.batch_alter_table("chat_sessions") as batch:
            batch.add_column(
                sa.Column("user_id", sa.Integer(), nullable=True),
            )

        # Backfill existing chat sessions to system_seed (user 1).
        # Sessions created before Phase 4 scoping have no owner;
        # assign them to the seed admin so they remain accessible
        # to super_admin but not to arbitrary authenticated users.
        op.execute(
            sa.text(
                "UPDATE chat_sessions SET user_id = 1 WHERE user_id IS NULL"
            )
        )


def downgrade() -> None:
    if _table_exists("chat_sessions") and _column_exists("chat_sessions", "user_id"):
        with op.batch_alter_table("chat_sessions") as batch:
            batch.drop_column("user_id")
