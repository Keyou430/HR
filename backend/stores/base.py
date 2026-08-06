"""BaseStore — shared infrastructure used by all store mixins.

Each mixin (PortalMixin, SubsystemsMixin, …) expects ``self`` to be a
PortalStore instance at runtime, so cross-mixin calls resolve via Python MRO.
"""

from __future__ import annotations

import csv
import io
import json
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from typing import Any, Iterator

from sqlalchemy import Table, and_, insert, or_, select, update
from sqlalchemy.orm import Session

from session import get_session_local


class BaseStore:
    """Shared store primitives — lock, session, scope filters, enterprise CRUD."""

    def __init__(self) -> None:
        self._lock = RLock()

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _stringify_dt(row: dict[str, Any]) -> dict[str, Any]:
        """Convert datetime objects in *row* to ISO-8601 strings.

        PostgreSQL returns datetime.datetime for TIMESTAMPTZ columns via
        psycopg2; SQLite returns plain strings.  This keeps the API stable.
        """
        for key, value in row.items():
            if isinstance(value, datetime):
                row[key] = value.isoformat()
        return row

    @staticmethod
    def list_response(items: list[dict[str, Any]] | list[str]) -> dict[str, Any]:
        return {"items": deepcopy(items), "total": len(items)}

    @contextmanager
    def _session(self) -> Iterator[Session]:
        """Open a database session.

        Note: schema creation is handled by PortalStore._ensure_schema at
        import time; this method intentionally does NOT call _ensure_schema
        so it can live on BaseStore without a circular dependency.
        """
        db = get_session_local()()
        try:
            yield db
        finally:
            db.close()

    # ── Scope / visibility helpers ────────────────────────────────────

    def _build_scope_context(
        self, user: dict[str, Any] | None, db: Session
    ):
        """Build an AccessContext from a user dict + DB session.

        Returns None when *user* is None (no scope filtering — internal / seed path).
        """
        if user is None:
            return None
        from authorization.scope import get_access_context as _get_ctx
        return _get_ctx(user, db)

    def _scope_filter(self, ctx, table):
        """Return a SQLAlchemy WHERE clause for *table* scoped to *ctx*, or True."""
        if ctx is None:
            return True  # No user context — return everything (seed / internal path)
        from authorization.sql_filters import (
            calendar_visibility_filter,
            knowledge_visibility_filter,
            task_visibility_filter,
        )
        table_name = str(table.name)
        if table_name == "portal_tasks":
            return task_visibility_filter(ctx, table)
        elif table_name == "portal_calendar_events":
            return calendar_visibility_filter(ctx, table)
        elif table_name == "knowledge_dataset_mappings":
            return knowledge_visibility_filter(ctx, table)
        elif table_name in {
            "enterprise_repair_tickets",
            "enterprise_asset_items",
            "enterprise_oa_flows",
            "hr_requests",
            "finance_claims",
            "finance_budgets",
            "cms_sites",
            "estate_spaces",
            "job_postings",
        }:
            return task_visibility_filter(ctx, table)
        return True

    def _scope_single(self, ctx, table, resource_id: int | str):
        """Build WHERE clause for single-resource access (update/delete).

        Returns a clause that yields 0 rows if the user lacks access.
        """
        if ctx is None:
            return table.c.id == resource_id
        from authorization.sql_filters import resource_owner_filter
        return resource_owner_filter(ctx, table, resource_id)

    def _portal_visibility_clause(
        self, user: dict[str, Any] | None, table: Table, db: Session
    ):
        if user is None:
            return True
        ctx = self._build_scope_context(user, db)
        if ctx is None or ctx.is_super_admin:
            return True
        clauses = [table.c.visibility == "public"]
        if ctx.default_org_id is not None:
            clauses.append(
                and_(table.c.visibility == "org", table.c.org_id == ctx.default_org_id)
            )
        if ctx.default_dept_id is not None:
            clauses.append(
                and_(table.c.visibility == "dept", table.c.department_id == ctx.default_dept_id)
            )
        clauses.append(
            and_(table.c.visibility == "private", table.c.owner_id == ctx.user_id)
        )
        return or_(*clauses)

    # ── Row helpers ────────────────────────────────────────────────────

    def _task_from_row(self, row: Any) -> dict[str, Any]:
        item = dict(row)
        item["done"] = bool(item["done"])
        return item

    def _event_from_row(self, row: Any) -> dict[str, Any]:
        return dict(row)

    def _subsystem_from_row(self, row: Any) -> dict[str, Any]:
        item = dict(row)
        item["is_featured"] = bool(item.get("is_featured"))
        item["common_actions"] = json.loads(item.pop("common_actions_json") or "[]")
        item["related_resources"] = json.loads(item.pop("related_resources_json") or "[]")
        item["menu_items"] = json.loads(item.pop("menu_items_json", None) or "[]")
        return item

    def _bool_fields_from_row(self, row: Any, *fields: str) -> dict[str, Any]:
        item = dict(row)
        for field in fields:
            if field in item:
                item[field] = bool(item[field])
        return item

    def _asset_table(self, collection: str) -> Table:
        tables = {
            "notices": self._portal_notices_table,
            "documents": self._portal_documents_table,
            "resources": self._portal_resources_table,
            "services": self._portal_services_table,
            "news": self._portal_news_table,
        }
        if collection not in tables:
            raise KeyError(collection)
        return tables[collection]

    # ── Enterprise CRUD primitives ────────────────────────────────────

    def _enterprise_list(
        self, table: Table, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            rows = (
                db.execute(
                    select(table)
                    .where(self._scope_filter(ctx, table))
                    .order_by(table.c.id.desc())
                )
                .mappings()
                .all()
            )
            return self.list_response(
                [self._stringify_dt(dict(row)) for row in rows]
            )

    def _enterprise_create(
        self,
        table: Table,
        payload: dict[str, Any],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = self._now_iso()
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                values = {
                    key: value
                    for key, value in payload.items()
                    if key in table.c and value is not None
                }
                values.update({
                    "created_at": now,
                    "updated_at": now,
                    "org_id": ctx.default_org_id if ctx else "default",
                    "department_id": ctx.default_dept_id if ctx else "HQ",
                    "owner_id": ctx.user_id if ctx else None,
                    "visibility": "org",
                    "sensitivity": "normal",
                })
                result = db.execute(insert(table).values(**values))
                db.commit()
                record_id = int(result.inserted_primary_key[0])
                row = (
                    db.execute(select(table).where(table.c.id == record_id))
                    .mappings()
                    .one()
                )
                return self._stringify_dt(dict(row))

    def _enterprise_get(
        self,
        table: Table,
        record_id: int,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope_clause = self._scope_single(ctx, table, record_id)
            row = (
                db.execute(select(table).where(scope_clause))
                .mappings()
                .first()
            )
            return self._stringify_dt(dict(row)) if row else None

    def _enterprise_update(
        self,
        table: Table,
        record_id: int,
        payload: dict[str, Any],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                scope_clause = self._scope_single(ctx, table, record_id)
                existing = (
                    db.execute(select(table).where(scope_clause))
                    .mappings()
                    .first()
                )
                if existing is None:
                    return None
                updates = {
                    key: value
                    for key, value in payload.items()
                    if key in table.c
                    and value is not None
                    and key
                    not in {
                        "id",
                        "org_id",
                        "department_id",
                        "owner_id",
                        "visibility",
                        "sensitivity",
                        "created_at",
                    }
                }
                updates["updated_at"] = self._now_iso()
                db.execute(update(table).where(scope_clause).values(**updates))
                db.commit()
                row = (
                    db.execute(select(table).where(scope_clause))
                    .mappings()
                    .first()
                )
                return self._stringify_dt(dict(row)) if row else None

    # ── CSV Export ───────────────────────────────────────────────────

    def _enterprise_export_csv(
        self,
        table: Table,
        user: dict[str, Any] | None,
        columns: list[str],
        filename: str,
    ) -> tuple[bytes, str, str]:
        """Export table rows as CSV (UTF-8 BOM). Returns (content, filename, media_type)."""
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            rows = (
                db.execute(
                    select(table)
                    .where(self._scope_filter(ctx, table))
                    .order_by(table.c.id.desc())
                )
                .mappings()
                .all()
            )
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(col, "") for col in columns])
        result = output.getvalue()
        bom = "﻿"
        content = (bom + result).encode("utf-8")
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return content, f"{filename}_{now_str}.csv", "text/csv; charset=utf-8"
