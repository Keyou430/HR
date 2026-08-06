"""Phase 3: Finance approval records table.

Revision ID: 009
Revises: 008
Create Date: 2026-08-05

- finance_approval_records: new table for multi-step claim approval tracking
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

_backend_root = Path(__file__).resolve().parents[2]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    from sqlalchemy import inspect
    return inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _table_exists("finance_approval_records"):
        op.create_table(
            "finance_approval_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("claim_id", sa.Integer(), nullable=False),
            sa.Column("approver_id", sa.Integer(), nullable=False),
            sa.Column("step_order", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(32), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(32), nullable=False),
        )


def downgrade() -> None:
    if _table_exists("finance_approval_records"):
        op.drop_table("finance_approval_records")
