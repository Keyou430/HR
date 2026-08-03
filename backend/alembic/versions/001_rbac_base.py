"""Phase 1: RBAC base schema — new tables, data-attribution columns, seed data, backfill.

Revision ID: 001
Revises: None (initial migration)
Create Date: 2026-07-30

Works for both empty databases (creates all tables from scratch) and existing
databases (adds columns to pre-existing tables and creates new RBAC tables).
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# Ensure backend/ is importable inside the migration
_backend_root = Path(__file__).resolve().parents[2]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ──────────────────────────────────────────────────────────────────
# Helpers  (dialect-agnostic via SQLAlchemy inspect — works on SQLite & PostgreSQL)
# ──────────────────────────────────────────────────────────────────

def _table_exists(table: str) -> bool:
    from sqlalchemy import inspect
    return inspect(op.get_bind()).has_table(table)


def _column_exists(table: str, column: str) -> bool:
    from sqlalchemy import inspect
    cols = inspect(op.get_bind()).get_columns(table)
    return any(c["name"] == column for c in cols)


def _table_has_rows(table: str) -> bool:
    row = op.get_bind().execute(sa.text(f"SELECT COUNT(1) FROM {table}")).fetchone()
    return bool(row and row[0] > 0)


# ──────────────────────────────────────────────────────────────────
# Business table definitions (used when table doesn't exist yet)
# ──────────────────────────────────────────────────────────────────

_BUSINESS_TABLES: dict[str, list[tuple[str, object]]] = {
    "portal_tasks": [
        ("id",       sa.Integer(), {"primary_key": True, "autoincrement": True}),
        ("title",    sa.String(255), {"nullable": False}),
        ("tag",      sa.String(32), {"nullable": False}),
        ("due_time", sa.String(8), {"nullable": True}),
        ("done",     sa.Boolean(), {"nullable": False, "server_default": sa.text("0")}),
        # RBAC attribution (included when creating from scratch)
        ("org_id",         sa.String(64), {"nullable": True}),
        ("department_id",  sa.String(64), {"nullable": True}),
        ("owner_id",       sa.Integer(), {"nullable": True}),
        ("visibility",     sa.String(16), {"nullable": False, "server_default": sa.text("'private'")}),
        ("sensitivity",    sa.String(16), {"nullable": False, "server_default": sa.text("'normal'")}),
    ],
    "portal_calendar_events": [
        ("id",       sa.Integer(), {"primary_key": True, "autoincrement": True}),
        ("date",     sa.String(10), {"nullable": False}),
        ("title",    sa.String(255), {"nullable": False}),
        ("tone",     sa.String(16), {"nullable": False}),
        ("org_id",         sa.String(64), {"nullable": True}),
        ("department_id",  sa.String(64), {"nullable": True}),
        ("owner_id",       sa.Integer(), {"nullable": True}),
        ("visibility",     sa.String(16), {"nullable": False, "server_default": sa.text("'private'")}),
        ("sensitivity",    sa.String(16), {"nullable": False, "server_default": sa.text("'normal'")}),
    ],
    "knowledge_dataset_mappings": [
        ("id",                 sa.String(160), {"primary_key": True}),
        ("resource_type",      sa.String(16), {"nullable": False}),
        ("resource_id",        sa.String(128), {"nullable": False}),
        ("display_name",       sa.String(255), {"nullable": False}),
        ("fastgpt_app_id",     sa.String(128), {"nullable": True}),
        ("fastgpt_dataset_id", sa.String(128), {"nullable": True}),
        ("permission_scope",   sa.String(16), {"nullable": False, "server_default": sa.text("'team'")}),
        ("enabled",            sa.Boolean(), {"nullable": False, "server_default": sa.text("1")}),
        ("is_default_import_target", sa.Boolean(), {"nullable": False, "server_default": sa.text("0")}),
        ("last_synced_at",     sa.String(32), {"nullable": True}),
        ("last_imported_at",   sa.String(32), {"nullable": True}),
        ("stale",              sa.Boolean(), {"nullable": False, "server_default": sa.text("0")}),
        ("updated_at",         sa.String(32), {"nullable": False}),
        ("org_id",         sa.String(64), {"nullable": True}),
        ("department_id",  sa.String(64), {"nullable": True}),
        ("owner_id",       sa.Integer(), {"nullable": True}),
        ("visibility",     sa.String(16), {"nullable": False, "server_default": sa.text("'dept'")}),
        ("sensitivity",    sa.String(16), {"nullable": False, "server_default": sa.text("'internal'")}),
    ],
}

# Remaining business tables that Alembic should also manage
_REMAINING_BUSINESS_TABLES = {
    "portal_settings": [
        ("key",        sa.String(128), {"primary_key": True}),
        ("value_json", sa.Text(), {"nullable": False}),
    ],
    "knowledge_import_records": [
        ("id",            sa.Integer(), {"primary_key": True, "autoincrement": True}),
        ("mapping_id",    sa.String(160), {"nullable": True}),
        ("dataset_id",    sa.String(128), {"nullable": False}),
        ("file_name",     sa.String(255), {"nullable": False}),
        ("status",        sa.String(32), {"nullable": False}),
        ("collection_id", sa.String(128), {"nullable": True}),
        ("error_message", sa.Text(), {"nullable": True}),
        ("created_at",    sa.String(32), {"nullable": False}),
    ],
    "chat_sessions": [
        ("id",         sa.String(64), {"primary_key": True}),
        ("title",      sa.String(255), {"nullable": False, "server_default": sa.text("''")}),
        ("created_at", sa.String(32), {"nullable": False}),
        ("updated_at", sa.String(32), {"nullable": False}),
    ],
    "chat_messages": [
        ("id",         sa.Integer(), {"primary_key": True, "autoincrement": True}),
        ("session_id", sa.String(64), {"nullable": False}),
        ("role",       sa.String(16), {"nullable": False}),
        ("content",    sa.Text(), {"nullable": False}),
        ("action",     sa.String(32), {"nullable": True}),
        ("created_at", sa.String(32), {"nullable": False}),
    ],
}


def _create_business_table(name: str) -> None:
    """Create a business table from its definition (idempotent)."""
    if _table_exists(name):
        return
    cols = _BUSINESS_TABLES.get(name) or _REMAINING_BUSINESS_TABLES.get(name)
    if cols is None:
        return
    columns = [
        sa.Column(col_name, *((col_type,) if not isinstance(col_type, tuple) else (col_type[0],)), **kw)
        if isinstance(col_type, tuple)
        else sa.Column(col_name, col_type, **kw)
        for col_name, col_type, kw in (
            (c[0], c[1], c[2]) if len(c) == 3 else (c[0], c[1], {})
            for c in cols
        )
    ]
    op.create_table(name, *columns)


def _add_attribution_columns(table: str, *, visibility_default: str, sensitivity_default: str) -> None:
    """Ensure a business table exists with all attribution columns.

    If the table doesn't exist yet (fresh DB), create it in full.
    If it exists, add any missing attribution columns via batch mode.
    """
    if not _table_exists(table):
        _create_business_table(table)
        return

    # Table exists — add any missing columns
    with op.batch_alter_table(table) as batch:
        if not _column_exists(table, "org_id"):
            batch.add_column(sa.Column("org_id", sa.String(64), nullable=True))
        if not _column_exists(table, "department_id"):
            batch.add_column(sa.Column("department_id", sa.String(64), nullable=True))
        if not _column_exists(table, "owner_id"):
            batch.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        if not _column_exists(table, "visibility"):
            batch.add_column(sa.Column(
                "visibility", sa.String(16), nullable=False,
                server_default=sa.text(f"'{visibility_default}'"),
            ))
        if not _column_exists(table, "sensitivity"):
            batch.add_column(sa.Column(
                "sensitivity", sa.String(16), nullable=False,
                server_default=sa.text(f"'{sensitivity_default}'"),
            ))


def _create_index_if_not_exists(table: str, column: str) -> None:
    idx_name = f"idx_{table}_{column}"
    op.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})")


def _backfill_existing_data(conn: object) -> None:
    if _table_has_rows("portal_tasks"):
        conn.exec_driver_sql(
            "UPDATE portal_tasks SET org_id='default', department_id='HQ', "
            "owner_id=1, visibility='org', sensitivity='normal' "
            "WHERE org_id IS NULL OR org_id=''"
        )
    if _table_has_rows("portal_calendar_events"):
        conn.exec_driver_sql(
            "UPDATE portal_calendar_events SET org_id='default', department_id='HQ', "
            "owner_id=1, visibility='org', sensitivity='normal' "
            "WHERE org_id IS NULL OR org_id=''"
        )
    if _table_has_rows("knowledge_dataset_mappings"):
        conn.exec_driver_sql(
            "UPDATE knowledge_dataset_mappings SET org_id='default', department_id='HQ', "
            "owner_id=1, visibility='dept', sensitivity='internal' "
            "WHERE org_id IS NULL OR org_id=''"
        )


# ──────────────────────────────────────────────────────────────────
# upgrade()
# ──────────────────────────────────────────────────────────────────

def upgrade() -> None:
    # ----------------------------------------------------------------
    # 1. Ensure all business tables exist (create or alter as needed)
    # ----------------------------------------------------------------
    _add_attribution_columns("portal_tasks", visibility_default="private", sensitivity_default="normal")
    _add_attribution_columns("portal_calendar_events", visibility_default="private", sensitivity_default="normal")
    _add_attribution_columns("knowledge_dataset_mappings", visibility_default="dept", sensitivity_default="internal")

    # Other business tables (no RBAC columns needed yet)
    for name in _REMAINING_BUSINESS_TABLES:
        _create_business_table(name)

    # ----------------------------------------------------------------
    # 2. New RBAC tables
    # ----------------------------------------------------------------

    op.create_table(
        "orgs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
    )

    op.create_table(
        "departments",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("parent_id", sa.String(64), nullable=True),
        sa.Column("path", sa.String(512), nullable=False, server_default=sa.text("''")),
        sa.Column("level", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_departments_org_id_id ON departments(org_id, id)")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_login_at", sa.String(32), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
    )

    op.create_table(
        "user_org_memberships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.String(64), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("user_id", "org_id"),
    )

    op.create_table(
        "user_department_memberships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("department_id", sa.String(64), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint("user_id", "department_id"),
        # Composite FK prevents cross-org department binding (rbac-design-v2.md §6.1)
        sa.ForeignKeyConstraint(
            ["org_id", "department_id"],
            ["departments.org_id", "departments.id"],
        ),
    )

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(256), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.String(32), nullable=False),
    )

    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(96), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("resource", sa.String(64), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("description", sa.String(256), nullable=True),
    )

    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("permission_id", sa.Integer(), sa.ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    op.create_table(
        "role_bindings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_id", sa.Integer(), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("org_id", sa.String(64), sa.ForeignKey("orgs.id"), nullable=False),
        sa.Column("department_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        # Composite FK prevents cross-org department binding (rbac-design-v2.md §6.1)
        sa.ForeignKeyConstraint(
            ["org_id", "department_id"],
            ["departments.org_id", "departments.id"],
        ),
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_role_bindings_with_dept "
        "ON role_bindings(user_id, role_id, org_id, department_id) "
        "WHERE department_id IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_role_bindings_without_dept "
        "ON role_bindings(user_id, role_id, org_id) "
        "WHERE department_id IS NULL"
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(256), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("expires_at", sa.String(32), nullable=False),
        sa.Column("revoked_at", sa.String(32), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("org_id", sa.String(64), nullable=True),
        sa.Column("department_id", sa.String(64), nullable=True),
        sa.Column("action", sa.String(96), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(256), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=False),
    )

    op.create_table(
        "ai_query_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("org_id", sa.String(64), nullable=True),
        sa.Column("department_id", sa.String(64), nullable=True),
        sa.Column("query_hash", sa.String(128), nullable=False),
        sa.Column("query_snippet", sa.String(256), nullable=True),
        sa.Column("risk_label", sa.String(64), nullable=True),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("blocked_reason", sa.String(256), nullable=True),
        sa.Column("accessible_resource_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.String(32), nullable=False),
    )

    # ----------------------------------------------------------------
    # 3. Indexes
    # ----------------------------------------------------------------

    for tbl in ("portal_tasks", "portal_calendar_events", "knowledge_dataset_mappings"):
        for col in ("org_id", "department_id", "owner_id"):
            _create_index_if_not_exists(tbl, col)

    _create_index_if_not_exists("audit_logs", "user_id")
    _create_index_if_not_exists("audit_logs", "created_at")
    _create_index_if_not_exists("ai_query_logs", "user_id")
    _create_index_if_not_exists("ai_query_logs", "created_at")

    # Performance indexes for Phase 2+ (auth sessions, session expiry)
    _create_index_if_not_exists("auth_sessions", "user_id")
    _create_index_if_not_exists("auth_sessions", "expires_at")

    # ----------------------------------------------------------------
    # 4. Seed data
    # ----------------------------------------------------------------

    from authorization.permissions import seed_all as seed
    conn = op.get_bind()
    seed(conn)

    # ----------------------------------------------------------------
    # 5. Backfill old data
    # ----------------------------------------------------------------
    _backfill_existing_data(conn)


# ──────────────────────────────────────────────────────────────────
# downgrade()
# ──────────────────────────────────────────────────────────────────

def downgrade() -> None:
    # IMPORTANT: drop indexes BEFORE removing columns, otherwise Alembic's
    # batch mode will try to recreate the indexes on the new table and fail.
    for tbl, col in [
        ("portal_tasks", "org_id"), ("portal_tasks", "department_id"), ("portal_tasks", "owner_id"),
        ("portal_calendar_events", "org_id"), ("portal_calendar_events", "department_id"), ("portal_calendar_events", "owner_id"),
        ("knowledge_dataset_mappings", "org_id"), ("knowledge_dataset_mappings", "department_id"), ("knowledge_dataset_mappings", "owner_id"),
        ("audit_logs", "user_id"), ("audit_logs", "created_at"),
        ("ai_query_logs", "user_id"), ("ai_query_logs", "created_at"),
    ]:
        op.execute(f"DROP INDEX IF EXISTS idx_{tbl}_{col}")

    # Remove attribution columns from business tables (keep the tables)
    for table in ("portal_tasks", "portal_calendar_events", "knowledge_dataset_mappings"):
        if _table_exists(table):
            with op.batch_alter_table(table) as batch:
                for col in ("org_id", "department_id", "owner_id", "visibility", "sensitivity"):
                    if _column_exists(table, col):
                        batch.drop_column(col)

    # Drop new tables in reverse dependency order
    op.drop_table("ai_query_logs")
    op.drop_table("audit_logs")
    op.drop_table("auth_sessions")
    op.execute("DROP INDEX IF EXISTS uq_role_bindings_with_dept")
    op.execute("DROP INDEX IF EXISTS uq_role_bindings_without_dept")
    op.drop_table("role_bindings")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("user_department_memberships")
    op.drop_table("user_org_memberships")
    op.drop_table("users")
    op.execute("DROP INDEX IF EXISTS uq_departments_org_id_id")
    op.drop_table("departments")
    op.drop_table("orgs")
