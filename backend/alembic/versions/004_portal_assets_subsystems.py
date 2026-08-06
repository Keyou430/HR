"""Portal assets and internal subsystems.

Revision ID: 004
Revises: 003
Create Date: 2026-08-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    return inspect(op.get_bind()).has_table(name)


def _create_scoped_columns() -> list[sa.Column]:
    return [
        sa.Column("org_id", sa.String(64), nullable=True),
        sa.Column("department_id", sa.String(64), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("visibility", sa.String(16), nullable=False, server_default=sa.text("'org'")),
        sa.Column("sensitivity", sa.String(16), nullable=False, server_default=sa.text("'normal'")),
    ]


def _create_table_if_not_exists(name: str, *columns: sa.Column, **kw: object) -> None:
    if not _table_exists(name):
        op.create_table(name, *columns, **kw)


def upgrade() -> None:
    _create_table_if_not_exists(
        "portal_subsystems",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("entry_type", sa.String(32), nullable=False, server_default=sa.text("'internal'")),
        sa.Column("owner_department", sa.String(128), nullable=False),
        sa.Column("owner_name", sa.String(128), nullable=False),
        sa.Column("support_contact", sa.String(128), nullable=False),
        sa.Column("icon_tone", sa.String(32), nullable=False, server_default=sa.text("'app-blue'")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_featured", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("common_actions_json", sa.Text(), nullable=False),
        sa.Column("related_resources_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        *_create_scoped_columns(),
    )
    _create_table_if_not_exists(
        "portal_subsystem_visits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("subsystem_code", sa.String(64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("visited_at", sa.String(32), nullable=False),
        sa.Column("org_id", sa.String(64), nullable=True),
        sa.Column("department_id", sa.String(64), nullable=True),
    )
    _create_table_if_not_exists(
        "portal_notices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("published_at", sa.String(32), nullable=False),
        sa.Column("read_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        *_create_scoped_columns(),
    )
    _create_table_if_not_exists(
        "portal_documents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(128), nullable=False),
        sa.Column("owner", sa.String(128), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("favorite_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("visit_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.String(32), nullable=False),
        *_create_scoped_columns(),
    )
    _create_table_if_not_exists(
        "portal_resources",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(128), nullable=False),
        sa.Column("icon_tone", sa.String(32), nullable=False, server_default=sa.text("'app-blue'")),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        *_create_scoped_columns(),
    )
    _create_table_if_not_exists(
        "portal_services",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("materials", sa.Text(), nullable=False),
        sa.Column("audience", sa.String(128), nullable=False),
        sa.Column("contact", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("subscribed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        *_create_scoped_columns(),
    )
    _create_table_if_not_exists(
        "portal_news",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("published_at", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        *_create_scoped_columns(),
    )
    _create_table_if_not_exists(
        "portal_user_preferences",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("preferences_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
    )


def downgrade() -> None:
    for table in [
        "portal_user_preferences",
        "portal_news",
        "portal_services",
        "portal_resources",
        "portal_documents",
        "portal_notices",
        "portal_subsystem_visits",
        "portal_subsystems",
    ]:
        op.drop_table(table)
