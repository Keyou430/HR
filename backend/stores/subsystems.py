"""SubsystemsMixin — subsystem listing, detail, visits, and dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, insert, select


class SubsystemsMixin:
    """Subsystem CRUD mixed into PortalStore — expects BaseStore primitives."""

    def list_subsystems(
        self,
        *,
        query: str = "",
        category: str = "",
        status: str = "",
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        needle = query.strip().lower()
        with self._session() as db:
            stmt = (
                select(self._portal_subsystems_table)
                .where(
                    self._portal_visibility_clause(
                        user, self._portal_subsystems_table, db
                    )
                )
                .order_by(
                    self._portal_subsystems_table.c.sort_order,
                    self._portal_subsystems_table.c.name,
                )
            )
            if category:
                stmt = stmt.where(self._portal_subsystems_table.c.category == category)
            if status:
                stmt = stmt.where(self._portal_subsystems_table.c.status == status)
            rows = db.execute(stmt).mappings().all()
            items = [self._subsystem_from_row(row) for row in rows]
            if needle:
                items = [
                    item
                    for item in items
                    if needle
                    in f"{item['code']}{item['name']}{item['category']}{item['description']}".lower()
                ]
            return self.list_response(items)

    def get_subsystem(
        self, code: str, user: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self._session() as db:
            row = (
                db.execute(
                    select(self._portal_subsystems_table)
                    .where(self._portal_subsystems_table.c.code == code)
                    .where(
                        self._portal_visibility_clause(
                            user, self._portal_subsystems_table, db
                        )
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            return self._subsystem_from_row(row)

    def record_subsystem_visit(
        self, code: str, user: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        subsystem = self.get_subsystem(code, user=user)
        if subsystem is None or subsystem["status"] != "active":
            return None
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._session() as db:
                db.execute(
                    insert(self._portal_subsystem_visits_table).values(
                        subsystem_code=code,
                        user_id=user.get("id") if user else None,
                        visited_at=now,
                        org_id=user.get("default_org_id") if user else "default",
                        department_id=user.get("default_dept_id") if user else "HQ",
                    )
                )
                db.commit()
        dashboard = self.portal_dashboard(user=user)
        return {
            "ok": True,
            "code": code,
            "visited_at": now,
            "visits_7d": dashboard["visits_7d"],
        }

    def subsystem_dashboard(
        self, code: str, user: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        subsystem = self.get_subsystem(code, user=user)
        if subsystem is None:
            return None
        with self._session() as db:
            visits = (
                db.scalar(
                    select(func.count())
                    .select_from(self._portal_subsystem_visits_table)
                    .where(
                        self._portal_subsystem_visits_table.c.subsystem_code == code
                    )
                )
                or 0
            )
        return {
            "code": code,
            "status": subsystem["status"],
            "visits_total": int(visits),
            "related_services": self.list_portal_assets("services", user=user)[
                "items"
            ][:3],
            "related_resources": self.list_portal_assets("resources", user=user)[
                "items"
            ][:3],
        }
