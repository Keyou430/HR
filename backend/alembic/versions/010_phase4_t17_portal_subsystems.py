"""Phase 4 T17: Activate website, estate, employment subsystems.

Revision ID: 010
Revises: 009
Create Date: 2026-08-05

- cms_sites: website (网站群) — site/column management
- estate_spaces: estate (房产管理) — space/room management
- job_postings: employment (就业系统) — job posting CRUD
"""

import sys
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

_backend_root = Path(__file__).resolve().parents[2]
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table: str) -> bool:
    from sqlalchemy import inspect
    return inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    # ── Step 1: Create cms_sites (website) ──────────────────────────
    if not _table_exists("cms_sites"):
        op.create_table(
            "cms_sites",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("domain", sa.String(255), nullable=True),
            sa.Column("category", sa.String(128), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, default="draft"),
            sa.Column("owner_dept", sa.String(128), nullable=True),
            sa.Column("columns_json", sa.Text(), nullable=True),
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

    # ── Step 2: Create estate_spaces (estate) ───────────────────────
    if not _table_exists("estate_spaces"):
        op.create_table(
            "estate_spaces",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("code", sa.String(128), nullable=False),
            sa.Column("category", sa.String(64), nullable=False),
            sa.Column("building", sa.String(128), nullable=True),
            sa.Column("floor", sa.String(32), nullable=True),
            sa.Column("area_sqm", sa.Float(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, default="vacant"),
            sa.Column("department_id", sa.String(64), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("contact_person", sa.String(128), nullable=True),
            sa.Column("org_id", sa.String(64), nullable=True),
            sa.Column("owner_id", sa.Integer(), nullable=True),
            sa.Column("visibility", sa.String(16), nullable=False, default="org"),
            sa.Column("sensitivity", sa.String(16), nullable=False, default="normal"),
            sa.Column("created_by", sa.Integer(), nullable=True),
            sa.Column("updated_by", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.String(32), nullable=False),
            sa.Column("updated_at", sa.String(32), nullable=False),
        )

    # ── Step 3: Create job_postings (employment) ────────────────────
    if not _table_exists("job_postings"):
        op.create_table(
            "job_postings",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("company_name", sa.String(255), nullable=False),
            sa.Column("position_category", sa.String(64), nullable=False),
            sa.Column("salary_range", sa.String(128), nullable=True),
            sa.Column("location", sa.String(255), nullable=True),
            sa.Column("requirements", sa.Text(), nullable=True),
            sa.Column("status", sa.String(32), nullable=False, default="open"),
            sa.Column("contact_info", sa.String(255), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("posted_date", sa.String(32), nullable=True),
            sa.Column("deadline", sa.String(32), nullable=True),
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
    if _table_exists("job_postings"):
        op.drop_table("job_postings")

    if _table_exists("estate_spaces"):
        op.drop_table("estate_spaces")

    if _table_exists("cms_sites"):
        op.drop_table("cms_sites")
