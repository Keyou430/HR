"""Phase 1: pgvector extension (PostgreSQL only).

Revision ID: 006
Revises: 005
Create Date: 2026-08-04

Creates the pgvector extension on PostgreSQL for future knowledge-base
vector storage. No-op on SQLite.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("DROP EXTENSION IF EXISTS vector"))
