"""Phase 1 Platform Enterprise: new columns, notifications, TIMESTAMPTZ, permission re-seed.

Revision ID: 005
Revises: 004
Create Date: 2026-08-04

Adds status/created_by/updated_by columns across business tables,
menu_items_json/entry_url to subsystems, org_id/updated_at to roles,
creates notifications table, converts timestamp columns to TIMESTAMPTZ on PG,
and re-seeds permissions (idempotent).
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

_backend_root = Path(__file__).resolve().parents[2]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

revision: str = "005"
down_revision: Union[str, None] = "004"
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


# Tables that should get created_by + updated_by columns
_BUSINESS_TABLES_FOR_TRACKING = [
    "portal_tasks",
    "portal_calendar_events",
    "knowledge_dataset_mappings",
    "knowledge_import_records",
    "chat_sessions",
    "chat_messages",
    "portal_subsystems",
    "portal_subsystem_visits",
    "portal_notices",
    "portal_documents",
    "portal_resources",
    "portal_services",
    "portal_news",
    "portal_user_preferences",
    "enterprise_repair_tickets",
    "enterprise_asset_items",
    "enterprise_oa_flows",
]

# Tables that need a 'status' column (skip those that already have it)
_TABLES_NEEDING_STATUS = [
    "portal_tasks",
    "portal_calendar_events",
    "knowledge_dataset_mappings",
    "chat_sessions",
    "chat_messages",
    "portal_subsystem_visits",
    "portal_notices",
    "portal_documents",
    "portal_resources",
    "portal_news",
    "portal_user_preferences",
]

# Tables lacking created_at / updated_at entirely (add them)
_TABLES_NEEDING_TIMESTAMPS = [
    "portal_tasks",
    "portal_calendar_events",
]

# All tables and their timestamp column names for PG TIMESTAMPTZ conversion
_TIMESTAMP_COLUMNS_BY_TABLE: dict[str, list[str]] = {
    "portal_tasks": ["created_at", "updated_at"],
    "portal_calendar_events": ["created_at", "updated_at"],
    "knowledge_dataset_mappings": ["last_synced_at", "last_imported_at", "updated_at"],
    "knowledge_import_records": ["created_at"],
    "chat_sessions": ["created_at", "updated_at"],
    "chat_messages": ["created_at"],
    "portal_subsystems": ["created_at", "updated_at"],
    "portal_subsystem_visits": ["visited_at"],
    "portal_notices": ["published_at", "created_at", "updated_at"],
    "portal_documents": ["updated_at", "created_at"],
    "portal_resources": ["updated_at", "created_at"],
    "portal_services": ["updated_at", "created_at"],
    "portal_news": ["published_at", "created_at", "updated_at"],
    "portal_user_preferences": ["updated_at"],
    "enterprise_repair_tickets": ["created_at", "updated_at"],
    "enterprise_asset_items": ["created_at", "updated_at"],
    "enterprise_oa_flows": ["created_at", "updated_at"],
    "auth_sessions": ["created_at", "expires_at", "revoked_at"],
    "audit_logs": ["created_at"],
    "ai_query_logs": ["created_at"],
}


def upgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    use_batch = not is_pg  # SQLite needs batch mode for ALTER TABLE

    # ── Step 1: Add status column to tables that lack it ─────────────────
    for table in _TABLES_NEEDING_STATUS:
        if _table_exists(table) and not _column_exists(table, "status"):
            _add_column(table, sa.Column("status", sa.String(32), nullable=True), use_batch)

    # ── Step 2: Add created_at / updated_at to tables lacking them ──────
    for table in _TABLES_NEEDING_TIMESTAMPS:
        if _table_exists(table):
            if not _column_exists(table, "created_at"):
                _add_column(table, sa.Column("created_at", sa.String(32), nullable=True), use_batch)
            if not _column_exists(table, "updated_at"):
                _add_column(table, sa.Column("updated_at", sa.String(32), nullable=True), use_batch)

    # ── Step 3: Add created_by / updated_by to all business tables ─────
    for table in _BUSINESS_TABLES_FOR_TRACKING:
        if _table_exists(table):
            if not _column_exists(table, "created_by"):
                _add_column(table, sa.Column("created_by", sa.Integer(), nullable=True), use_batch)
            if not _column_exists(table, "updated_by"):
                _add_column(table, sa.Column("updated_by", sa.Integer(), nullable=True), use_batch)

    # ── Step 4: portal_subsystems -- menu_items_json + entry_url ───────
    if _table_exists("portal_subsystems"):
        if not _column_exists("portal_subsystems", "menu_items_json"):
            _add_column("portal_subsystems",
                        sa.Column("menu_items_json", sa.Text(), nullable=False,
                                  server_default=sa.text("'[]'")), use_batch)
        if not _column_exists("portal_subsystems", "entry_url"):
            _add_column("portal_subsystems",
                        sa.Column("entry_url", sa.String(512), nullable=True), use_batch)

    # ── Step 5: roles -- org_id + updated_at ────────────────────────────
    if _table_exists("roles"):
        if not _column_exists("roles", "org_id"):
            _add_column("roles", sa.Column("org_id", sa.String(64), nullable=True), use_batch)
        if not _column_exists("roles", "updated_at"):
            _add_column("roles", sa.Column("updated_at", sa.String(32), nullable=True), use_batch)

    # ── Step 6: Create notifications table ─────────────────────────────
    if not _table_exists("notifications"):
        op.create_table(
            "notifications",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("type", sa.String(32), nullable=False,
                      server_default=sa.text("'info'")),
            sa.Column("reference_type", sa.String(64), nullable=True),
            sa.Column("reference_id", sa.String(128), nullable=True),
            sa.Column("is_read", sa.Boolean(), nullable=False,
                      server_default=sa.text("0")),
            sa.Column("org_id", sa.String(64), nullable=True),
            sa.Column("department_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.String(32), nullable=False),
        )
        op.create_index("ix_notifications_user_unread", "notifications",
                        ["user_id", "is_read"])
        op.create_index("ix_notifications_created_at", "notifications",
                        ["created_at"])

    # ── Step 7: PG TIMESTAMPTZ conversion ──────────────────────────────
    if is_pg:
        for table, columns in _TIMESTAMP_COLUMNS_BY_TABLE.items():
            if not _table_exists(table):
                continue
            for col in columns:
                if not _column_exists(table, col):
                    continue
                try:
                    op.execute(sa.text(
                        f"ALTER TABLE {table} ALTER COLUMN {col} "
                        f"TYPE TIMESTAMPTZ USING ({col}::timestamp AT TIME ZONE 'UTC')"
                    ))
                except Exception:
                    # Column might already be TIMESTAMPTZ or have incompatible data
                    pass

    # ── Step 8: Re-seed permissions (idempotent) ────────────────────────
    from authorization.permissions import seed_all
    seed_all(op.get_bind())


def downgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"
    use_batch = not is_pg

    # Drop notifications table
    if _table_exists("notifications"):
        op.drop_index("ix_notifications_user_unread", table_name="notifications")
        op.drop_index("ix_notifications_created_at", table_name="notifications")
        op.drop_table("notifications")

    # Remove columns from roles
    if _table_exists("roles"):
        if _column_exists("roles", "updated_at"):
            _drop_column("roles", "updated_at", use_batch)
        if _column_exists("roles", "org_id"):
            _drop_column("roles", "org_id", use_batch)

    # Remove subsystem columns
    if _table_exists("portal_subsystems"):
        if _column_exists("portal_subsystems", "entry_url"):
            _drop_column("portal_subsystems", "entry_url", use_batch)
        if _column_exists("portal_subsystems", "menu_items_json"):
            _drop_column("portal_subsystems", "menu_items_json", use_batch)

    # Remove created_by/updated_by from business tables
    for table in reversed(_BUSINESS_TABLES_FOR_TRACKING):
        if _table_exists(table):
            if _column_exists(table, "updated_by"):
                _drop_column(table, "updated_by", use_batch)
            if _column_exists(table, "created_by"):
                _drop_column(table, "created_by", use_batch)

    # Remove status from tables we added it to
    for table in reversed(_TABLES_NEEDING_STATUS):
        if _table_exists(table) and _column_exists(table, "status"):
            _drop_column(table, "status", use_batch)

    # Remove timestamps from tables we added them to
    for table in reversed(_TABLES_NEEDING_TIMESTAMPS):
        if _table_exists(table):
            if _column_exists(table, "updated_at"):
                _drop_column(table, "updated_at", use_batch)
            if _column_exists(table, "created_at"):
                _drop_column(table, "created_at", use_batch)

    # PG TIMESTAMPTZ -> String reversion
    if is_pg:
        for table, columns in _TIMESTAMP_COLUMNS_BY_TABLE.items():
            if not _table_exists(table):
                continue
            for col in columns:
                if not _column_exists(table, col):
                    continue
                try:
                    op.execute(sa.text(
                        f"ALTER TABLE {table} ALTER COLUMN {col} TYPE VARCHAR(32) "
                        f"USING ({col}::text)"
                    ))
                except Exception:
                    pass
