"""SQLAlchemy Table definitions for audit tables (Phase 6).

These tables are created by Alembic migrations (Phase 1) or, when Alembic
has not run, by ``store.metadata.create_all()`` via ``_ensure_schema()``.

They are defined here so the audit query APIs can use SQLAlchemy Core to
build SELECT statements with pagination, filtering, and sorting.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, String, Text
from sqlalchemy import Table

metadata = MetaData()

audit_logs_table = Table(
    "audit_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("request_id", String(64), nullable=False),
    Column("user_id", Integer, nullable=True),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("action", String(96), nullable=False),
    Column("resource_type", String(64), nullable=True),
    Column("resource_id", String(128), nullable=True),
    Column("decision", String(16), nullable=False),
    Column("reason", String(256), nullable=True),
    Column("ip_address", String(45), nullable=True),
    Column("user_agent", String(512), nullable=True),
    Column("detail_json", Text, nullable=True),
    Column("created_at", String(32), nullable=False),
)

ai_query_logs_table = Table(
    "ai_query_logs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("request_id", String(64), nullable=False),
    Column("user_id", Integer, nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("query_hash", String(128), nullable=False),
    Column("query_snippet", String(256), nullable=True),
    Column("risk_label", String(64), nullable=True),
    Column("policy_version", String(32), nullable=False),
    Column("decision", String(16), nullable=False),
    Column("blocked_reason", String(256), nullable=True),
    Column("accessible_resource_count", Integer, nullable=False, default=0),
    Column("response_time_ms", Integer, nullable=True),
    Column("created_at", String(32), nullable=False),
)
