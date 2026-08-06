"""Phase 3: HR requests, finance claims, and finance budgets.

Revision ID: 008
Revises: 007
Create Date: 2026-08-05

- hr_requests: new table (certificate / attendance / leave)
- finance_claims: new table (reimbursement with multi-step approval)
- finance_budgets: new table (budget CRUD)
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

_backend_root = Path(__file__).resolve().parents[2]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Helpers ─────────────────────────────────────────────────────────────

def _table_exists(table: str) -> bool:
    from sqlalchemy import inspect
    return inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    # ── Step 1: Create hr_requests ─────────────────────────────────
    if not _table_exists("hr_requests"):
        op.create_table(
            "hr_requests",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("request_type", sa.String(32), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, default="pending"),
            sa.Column("applicant_id", sa.Integer(), nullable=True),
            sa.Column("content_json", sa.Text(), nullable=True),
            sa.Column("approved_by", sa.Integer(), nullable=True),
            sa.Column("approved_at", sa.String(32), nullable=True),
            sa.Column("org_id", sa.String(64), nullable=True),
            sa.Column("department_id", sa.String(64), nullable=True),
            sa.Column("owner_id", sa.Integer(), nullable=True),
            sa.Column("visibility", sa.String(16), nullable=False, default="org"),
            sa.Column("sensitivity", sa.String(16), nullable=False, default="normal"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.String(32), nullable=False),
            sa.Column("updated_at", sa.String(32), nullable=False),
        )

    # ── Step 2: Create finance_claims ───────────────────────────────
    if not _table_exists("finance_claims"):
        op.create_table(
            "finance_claims",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("amount", sa.Float(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, default="pending"),
            sa.Column("applicant_id", sa.Integer(), nullable=True),
            sa.Column("budget_id", sa.Integer(), nullable=True),
            sa.Column("current_handler", sa.String(128), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("org_id", sa.String(64), nullable=True),
            sa.Column("department_id", sa.String(64), nullable=True),
            sa.Column("owner_id", sa.Integer(), nullable=True),
            sa.Column("visibility", sa.String(16), nullable=False, default="org"),
            sa.Column("sensitivity", sa.String(16), nullable=False, default="normal"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.String(32), nullable=False),
            sa.Column("updated_at", sa.String(32), nullable=False),
        )

    # ── Step 3: Create finance_budgets ──────────────────────────────
    if not _table_exists("finance_budgets"):
        op.create_table(
            "finance_budgets",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("category", sa.String(128), nullable=False),
            sa.Column("amount_total", sa.Float(), nullable=False, default=0.0),
            sa.Column("amount_used", sa.Float(), nullable=False, default=0.0),
            sa.Column("fiscal_year", sa.Integer(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("org_id", sa.String(64), nullable=True),
            sa.Column("department_id", sa.String(64), nullable=True),
            sa.Column("owner_id", sa.Integer(), nullable=True),
            sa.Column("visibility", sa.String(16), nullable=False, default="org"),
            sa.Column("sensitivity", sa.String(16), nullable=False, default="normal"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.String(32), nullable=False),
            sa.Column("updated_at", sa.String(32), nullable=False),
        )


def downgrade() -> None:
    if _table_exists("finance_budgets"):
        op.drop_table("finance_budgets")

    if _table_exists("finance_claims"):
        op.drop_table("finance_claims")

    if _table_exists("hr_requests"):
        op.drop_table("hr_requests")
