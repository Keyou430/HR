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

from fastapi import HTTPException
from sqlalchemy import Table, and_, false, insert, or_, select, update
from sqlalchemy.orm import Session

from authorization.scope import KNOWN_VISIBILITIES, AccessContext, get_access_context
from session import get_session_local

# New resources must declare their scope policy before being accessible.
ENTERPRISE_SCOPE_TABLES = frozenset({
    "enterprise_repair_tickets", "enterprise_asset_items", "enterprise_oa_flows",
    "hr_requests", "finance_claims", "finance_budgets", "cms_sites", "estate_spaces", "job_postings",
})
OWNER_SCOPE_TABLES = ENTERPRISE_SCOPE_TABLES | {"portal_tasks", "portal_calendar_events"}
RESOURCE_SCOPE_TABLES = OWNER_SCOPE_TABLES | {"knowledge_dataset_mappings"}
PORTAL_SCOPE_TABLES = frozenset({
    "portal_subsystems", "portal_notices", "portal_documents", "portal_resources", "portal_news",
})


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
        """Require an authenticated identity and build its data scope."""
        return get_access_context(user, db)

    def _scope_filter(self, ctx, table):
        """Return only rows covered by a declared policy and valid context."""
        if not isinstance(ctx, AccessContext) or table.name not in RESOURCE_SCOPE_TABLES:
            return false()
        from authorization.sql_filters import knowledge_visibility_filter, task_visibility_filter
        if table.name == "knowledge_dataset_mappings":
            return knowledge_visibility_filter(ctx, table)
        return task_visibility_filter(ctx, table)

    def _scope_single(self, ctx, table, resource_id: int | str):
        """Build WHERE clause for single-resource access (update/delete).

        Returns a clause that yields 0 rows if the user lacks access.

        Tasks and calendar events use owner-only isolation: only the
        creator (or super_admin) can modify or delete them.
        """
        if not isinstance(ctx, AccessContext) or table.name not in RESOURCE_SCOPE_TABLES:
            return false()
        if table.name in {"portal_tasks", "portal_calendar_events"}:
            return and_(table.c.id == resource_id, self._scope_filter(ctx, table))
        from authorization.sql_filters import resource_owner_filter
        return resource_owner_filter(ctx, table, resource_id)

    def _portal_visibility_clause(
        self, user: dict[str, Any] | None, table: Table, db: Session
    ):
        ctx = self._build_scope_context(user, db)
        if table.name not in PORTAL_SCOPE_TABLES:
            return false()
        policy = and_(
            table.c.visibility.in_(KNOWN_VISIBILITIES),
            table.c.sensitivity.in_(ctx.allowed_sensitivities),
        )
        if ctx.is_super_admin:
            return policy
        # Explicit public-content policy; anonymous access is not supported.
        clauses = [table.c.visibility == "public"]
        if ctx.org_ids:
            clauses.append(
                and_(table.c.visibility == "org", table.c.org_id.in_(ctx.org_ids))
            )
        if ctx.org_ids and ctx.default_dept_id is not None:
            # Include own dept + descendants (visible_dept_ids) + ancestors (walk up path)
            dept_ids = set(ctx.visible_dept_ids) if ctx.visible_dept_ids else {ctx.default_dept_id}
            if ctx.default_dept_id not in dept_ids:
                dept_ids.add(ctx.default_dept_id)
            # Resolve ancestor department IDs by walking up the path column
            try:
                from sqlalchemy import text as _text
                path_row = db.execute(
                    _text("SELECT path FROM departments WHERE org_id = :oid AND id = :did"),
                    {"oid": ctx.default_org_id, "did": ctx.default_dept_id},
                ).fetchone()
                if path_row and path_row[0]:
                    parts = path_row[0].split("/")
                    # Collect ancestor paths (all prefixes including full path)
                    ancestor_paths = {"/".join(parts[: i + 1]) for i in range(len(parts))}
                    ancestor_rows = db.execute(
                        _text(
                            "SELECT id FROM departments "
                            "WHERE org_id = :oid AND path IN ({})".format(
                                ", ".join(f":p{i}" for i in range(len(ancestor_paths)))
                            )
                        ),
                        {"oid": ctx.default_org_id, **{f"p{i}": p for i, p in enumerate(sorted(ancestor_paths))}},
                    ).fetchall()
                    for r in ancestor_rows:
                        dept_ids.add(r[0])
            except Exception:
                pass  # departments table may not exist in very early migration states
            clauses.append(
                and_(
                    table.c.visibility == "dept",
                    table.c.org_id.in_(ctx.org_ids),
                    table.c.department_id.in_(dept_ids),
                )
            )
        clauses.append(
            and_(table.c.visibility == "private", table.c.owner_id == ctx.user_id)
        )
        return and_(policy, or_(*clauses))

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
        item["approval_chain"] = json.loads(item.pop("approval_chain_json", None) or "[]")
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
                if table.name not in ENTERPRISE_SCOPE_TABLES:
                    raise HTTPException(status_code=403, detail="未声明资源的数据范围政策")
                values = {
                    key: value
                    for key, value in payload.items()
                    if key in table.c and value is not None
                }
                values.update({
                    "created_at": now,
                    "updated_at": now,
                    "org_id": ctx.default_org_id,
                    "department_id": ctx.default_dept_id,
                    "owner_id": ctx.user_id,
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
