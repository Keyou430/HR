"""PortalMixin — portal assets (notices, documents, resources, services, news) and user preferences."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, insert, select, text, update


class PortalMixin:
    """Portal asset CRUD mixed into PortalStore — expects BaseStore primitives."""

    # ── Portal assets ──────────────────────────────────────────────────

    def list_portal_assets(
        self, collection: str, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        table = self._asset_table(collection)
        with self._session() as db:
            order = table.c.title if "title" in table.c else table.c.name
            if "published_at" in table.c:
                order = table.c.published_at.desc()
            stmt = (
                select(table)
                .where(self._portal_visibility_clause(user, table, db))
                .order_by(order)
            )
            rows = db.execute(stmt).mappings().all()
            items = [self._portal_asset_from_row(collection, row) for row in rows]
            return self.list_response(items)

    def get_portal_asset(
        self,
        collection: str,
        key: str,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        table = self._asset_table(collection)
        column = table.c.code if "code" in table.c else table.c.id
        value: int | str = int(key) if column.name == "id" else key
        with self._session() as db:
            row = (
                db.execute(
                    select(table)
                    .where(column == value)
                    .where(self._portal_visibility_clause(user, table, db))
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            return self._portal_asset_from_row(collection, row)

    def _portal_asset_from_row(
        self, collection: str, row: Any
    ) -> dict[str, Any]:
        if collection in {"notices", "resources", "news"}:
            return self._bool_fields_from_row(row, "pinned")
        return dict(row)

    # ── User preferences ──────────────────────────────────────────────

    def get_portal_preferences(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        user_id = user.get("id") if user else 0
        defaults = {
            "favorite_subsystems": [],
            "favorite_services": [],
            "favorite_documents": [],
            "hidden_cards": [],
            "card_order": [],
            "news_subscriptions": [],
            "service_subscriptions": [],
        }
        with self._session() as db:
            row = db.execute(
                select(self._portal_user_preferences_table.c.preferences_json).where(
                    self._portal_user_preferences_table.c.user_id == user_id
                )
            ).first()
            if row is None:
                return defaults
            try:
                saved = json.loads(row[0])
            except json.JSONDecodeError:
                return defaults
            return {**defaults, **saved}

    def update_portal_preferences(
        self, payload: dict[str, Any], user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        allowed = {
            "favorite_subsystems",
            "favorite_services",
            "favorite_documents",
            "hidden_cards",
            "card_order",
            "news_subscriptions",
            "service_subscriptions",
        }
        user_id = user.get("id") if user else 0
        current = self.get_portal_preferences(user=user)
        for key, value in payload.items():
            if key in allowed and isinstance(value, list):
                current[key] = value
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._session() as db:
                existing = db.scalar(
                    select(self._portal_user_preferences_table.c.user_id).where(
                        self._portal_user_preferences_table.c.user_id == user_id
                    )
                )
                values = json.dumps(current, ensure_ascii=False)
                if existing is None:
                    db.execute(
                        insert(self._portal_user_preferences_table).values(
                            user_id=user_id,
                            preferences_json=values,
                            updated_at=now,
                        )
                    )
                else:
                    db.execute(
                        update(self._portal_user_preferences_table)
                        .where(
                            self._portal_user_preferences_table.c.user_id == user_id
                        )
                        .values(preferences_json=values, updated_at=now)
                    )
                db.commit()
        return current

    # ── Data Portal overview (Phase 3c) ─────────────────────────────

    def get_data_portal_overview(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Aggregate counts across subsystems, users, tickets, assets, flows, and notices."""
        with self._session() as db:
            ctx = self._build_scope_context(user, db)

            subs_scope = self._scope_filter(ctx, self._portal_subsystems_table)
            subsystem_count = db.scalar(
                select(func.count()).select_from(self._portal_subsystems_table).where(subs_scope)
            ) or 0

            total_users = db.scalar(
                select(func.count()).select_from(text("users"))
            ) or 0

            repair_scope = self._scope_filter(ctx, self._enterprise_repair_tickets_table)
            total_tickets = db.scalar(
                select(func.count()).select_from(self._enterprise_repair_tickets_table).where(repair_scope)
            ) or 0

            asset_scope = self._scope_filter(ctx, self._enterprise_asset_items_table)
            total_assets = db.scalar(
                select(func.count()).select_from(self._enterprise_asset_items_table).where(asset_scope)
            ) or 0

            oa_scope = self._scope_filter(ctx, self._enterprise_oa_flows_table)
            total_flows = db.scalar(
                select(func.count()).select_from(self._enterprise_oa_flows_table).where(oa_scope)
            ) or 0

            notices_scope = self._scope_filter(ctx, self._portal_notices_table)
            notices_count = db.scalar(
                select(func.count()).select_from(self._portal_notices_table).where(notices_scope)
            ) or 0

            docs_scope = self._scope_filter(ctx, self._portal_documents_table)
            documents_count = db.scalar(
                select(func.count()).select_from(self._portal_documents_table).where(docs_scope)
            ) or 0

            return {
                "subsystem_count": subsystem_count,
                "active_users": total_users,
                "total_tickets": total_tickets,
                "total_assets": total_assets,
                "total_flows": total_flows,
                "notices_count": notices_count,
                "documents_count": documents_count,
            }
