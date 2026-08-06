"""Phase 5 T21: portal_documents external integration fields + approval_chain_json for subsystems + notice:publish permission.

Revision ID: 012
Revises: 011
Create Date: 2026-08-06

Adds external_id/external_source/external_url to portal_documents (nullable —
reserved for future Feishu/WPS cloud document integration).
Adds approval_chain_json to portal_subsystems (NOT NULL, default '[]').
Re-seeds permissions to install the new notice:publish code.
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

_backend_root = Path(__file__).resolve().parents[2]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

revision: str = "012"
down_revision: Union[str, None] = "011"
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


# ── Upgrade ─────────────────────────────────────────────────────────────

def upgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    use_batch = not is_pg  # SQLite needs batch mode for ALTER TABLE

    # ── Step 1: portal_documents — external integration fields ──────────
    if _table_exists("portal_documents"):
        if not _column_exists("portal_documents", "external_id"):
            _add_column("portal_documents",
                        sa.Column("external_id", sa.String(256), nullable=True),
                        use_batch)
        if not _column_exists("portal_documents", "external_source"):
            _add_column("portal_documents",
                        sa.Column("external_source", sa.String(32), nullable=True),
                        use_batch)
        if not _column_exists("portal_documents", "external_url"):
            _add_column("portal_documents",
                        sa.Column("external_url", sa.String(1024), nullable=True),
                        use_batch)

    # ── Step 2: portal_subsystems — approval_chain_json ────────────────
    if _table_exists("portal_subsystems"):
        if not _column_exists("portal_subsystems", "approval_chain_json"):
            _add_column("portal_subsystems",
                        sa.Column("approval_chain_json", sa.Text(), nullable=False,
                                  server_default=sa.text("'[]'")),
                        use_batch)

    # ── Step 3: Re-seed permissions (idempotent) — installs notice:publish
    from authorization.permissions import seed_all
    seed_all(op.get_bind())


# ── Downgrade ───────────────────────────────────────────────────────────

def downgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    use_batch = not is_pg

    # Drop document external fields
    if _table_exists("portal_documents"):
        for col in ("external_url", "external_source", "external_id"):
            if _column_exists("portal_documents", col):
                _drop_column("portal_documents", col, use_batch)

    # Drop subsystem approval_chain_json
    if _table_exists("portal_subsystems"):
        if _column_exists("portal_subsystems", "approval_chain_json"):
            _drop_column("portal_subsystems", "approval_chain_json", use_batch)
