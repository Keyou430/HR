"""Phase 2 Enterprise: repair rating + completed_at, asset borrow records, OA approval records.

Revision ID: 007
Revises: 006
Create Date: 2026-08-05

- enterprise_repair_tickets: add rating (INT NULL) and completed_at (TEXT)
- asset_borrow_records: new table
- oa_approval_records: new table
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

_backend_root = Path(__file__).resolve().parents[2]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Helpers ─────────────────────────────────────────────────────────────

def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect
    cols = inspect(op.get_bind()).get_columns(table)
    return any(c["name"] == column for c in cols)


def _table_exists(table: str) -> bool:
    from sqlalchemy import inspect
    return inspect(op.get_bind()).has_table(table)


def _add_column(table: str, column: sa.Column, use_batch: bool) -> None:
    if use_batch:
        with op.batch_alter_table(table) as batch:
            batch.add_column(column)
    else:
        op.add_column(table, column)


def _drop_column(table: str, column_name: str, use_batch: bool) -> None:
    if use_batch:
        with op.batch_alter_table(table) as batch:
            batch.drop_column(column_name)
    else:
        op.drop_column(table, column_name)


def upgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    use_batch = not is_pg

    # ── Step 1: Add rating + completed_at to enterprise_repair_tickets ──
    if _table_exists("enterprise_repair_tickets"):
        if not _column_exists("enterprise_repair_tickets", "rating"):
            _add_column(
                "enterprise_repair_tickets",
                sa.Column("rating", sa.Integer(), nullable=True),
                use_batch,
            )
        if not _column_exists("enterprise_repair_tickets", "completed_at"):
            _add_column(
                "enterprise_repair_tickets",
                sa.Column("completed_at", sa.String(32), nullable=True),
                use_batch,
            )

    # ── Step 2: Create asset_borrow_records ─────────────────────────
    if not _table_exists("asset_borrow_records"):
        op.create_table(
            "asset_borrow_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("asset_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("borrow_date", sa.String(32), nullable=False),
            sa.Column("expected_return_date", sa.String(32), nullable=True),
            sa.Column("actual_return_date", sa.String(32), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, default="borrowed"),
            sa.Column("org_id", sa.String(64), nullable=True),
            sa.Column("department_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.String(32), nullable=False),
            sa.Column("updated_at", sa.String(32), nullable=False),
        )

    # ── Step 3: Create oa_approval_records ──────────────────────────
    if not _table_exists("oa_approval_records"):
        op.create_table(
            "oa_approval_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("flow_id", sa.Integer(), nullable=False),
            sa.Column("approver_id", sa.Integer(), nullable=False),
            sa.Column("step_order", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(32), nullable=True),
            sa.Column("comment", sa.Text(), nullable=True),
            sa.Column("created_at", sa.String(32), nullable=False),
        )


def downgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    use_batch = not is_pg

    if _table_exists("enterprise_repair_tickets"):
        if _column_exists("enterprise_repair_tickets", "completed_at"):
            _drop_column("enterprise_repair_tickets", "completed_at", use_batch)
        if _column_exists("enterprise_repair_tickets", "rating"):
            _drop_column("enterprise_repair_tickets", "rating", use_batch)

    if _table_exists("oa_approval_records"):
        op.drop_table("oa_approval_records")

    if _table_exists("asset_borrow_records"):
        op.drop_table("asset_borrow_records")
