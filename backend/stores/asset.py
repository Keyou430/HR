"""AssetMixin — asset item CRUD and borrow/return lifecycle."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, insert, select, update

from session import get_session_local


class AssetMixin:
    """Asset item CRUD and borrow/return mixed into PortalStore."""

    # ── CRUD ─────────────────────────────────────────────────────────

    def list_asset_items(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._enterprise_list(
            self._enterprise_asset_items_table, user=user
        )

    def get_asset_item(
        self, item_id: int, user: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope_clause = self._scope_single(ctx, self._enterprise_asset_items_table, item_id)
            row = (
                db.execute(
                    select(self._enterprise_asset_items_table).where(scope_clause)
                )
                .mappings()
                .first()
            )
            return self._stringify_dt(dict(row)) if row else None

    def create_asset_item(
        self, payload: dict[str, Any], user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = {
            **payload,
            "status": payload.get("status") or "available",
        }
        return self._enterprise_create(
            self._enterprise_asset_items_table, payload, user=user
        )

    def update_asset_item(
        self,
        item_id: int,
        payload: dict[str, Any],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self._enterprise_update(
            self._enterprise_asset_items_table, item_id, payload, user=user
        )

    # ── Borrow / Return lifecycle ────────────────────────────────────

    def borrow_asset(
        self,
        asset_id: int,
        expected_return_date: str | None = None,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Borrow an available asset. Creates borrow record + sets status to 'borrowed'."""
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                asset_table = self._enterprise_asset_items_table
                scope_clause = self._scope_single(ctx, asset_table, asset_id)
                existing = (
                    db.execute(select(asset_table).where(scope_clause))
                    .mappings()
                    .first()
                )
                if existing is None:
                    raise ValueError("资产不存在或无权操作")
                if existing["status"] != "available":
                    raise ValueError("资产不可借用（当前状态不是 'available'）")

                now = self._now_iso()
                user_id = user.get("id") if user else None

                # Update asset status
                db.execute(
                    update(asset_table)
                    .where(scope_clause)
                    .values(status="borrowed", updated_at=now)
                )

                # Create borrow record
                borrow_values = {
                    "asset_id": asset_id,
                    "user_id": user_id,
                    "borrow_date": now,
                    "expected_return_date": expected_return_date,
                    "status": "borrowed",
                    "org_id": ctx.default_org_id if ctx else "default",
                    "department_id": ctx.default_dept_id if ctx else "HQ",
                    "created_at": now,
                    "updated_at": now,
                }
                result = db.execute(
                    insert(self._asset_borrow_records_table).values(**borrow_values)
                )
                db.commit()
                record_id = int(result.inserted_primary_key[0])

                # Return the borrow record
                row = (
                    db.execute(
                        select(self._asset_borrow_records_table).where(
                            self._asset_borrow_records_table.c.id == record_id
                        )
                    )
                    .mappings()
                    .one()
                )
                return self._stringify_dt(dict(row))

    def return_asset(
        self,
        borrow_record_id: int,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a borrowed asset. Updates borrow record + restores asset status to 'available'."""
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                now = self._now_iso()

                # Find the borrow record
                borrow_record = (
                    db.execute(
                        select(self._asset_borrow_records_table).where(
                            self._asset_borrow_records_table.c.id == borrow_record_id
                        )
                    )
                    .mappings()
                    .first()
                )
                if borrow_record is None:
                    raise ValueError("借用记录不存在")
                if borrow_record["status"] != "borrowed":
                    raise ValueError("该借用记录已归还")

                # Update borrow record
                db.execute(
                    update(self._asset_borrow_records_table)
                    .where(self._asset_borrow_records_table.c.id == borrow_record_id)
                    .values(
                        status="returned",
                        actual_return_date=now,
                        updated_at=now,
                    )
                )

                # Restore asset status
                asset_table = self._enterprise_asset_items_table
                db.execute(
                    update(asset_table)
                    .where(asset_table.c.id == borrow_record["asset_id"])
                    .values(status="available", updated_at=now)
                )

                db.commit()

                # Return updated borrow record
                row = (
                    db.execute(
                        select(self._asset_borrow_records_table).where(
                            self._asset_borrow_records_table.c.id == borrow_record_id
                        )
                    )
                    .mappings()
                    .one()
                )
                return self._stringify_dt(dict(row))

    # ── Statistics ────────────────────────────────────────────────────

    def get_asset_stats(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return asset statistics scoped to *user*."""
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._enterprise_asset_items_table)
            table = self._enterprise_asset_items_table

            total = db.scalar(select(func.count()).select_from(table).where(scope)) or 0

            by_status_rows = (
                db.execute(
                    select(table.c.status, func.count())
                    .where(scope)
                    .group_by(table.c.status)
                )
                .all()
            )
            by_status = {row[0]: row[1] for row in by_status_rows}

            by_category_rows = (
                db.execute(
                    select(table.c.category, func.count())
                    .where(scope)
                    .group_by(table.c.category)
                )
                .all()
            )
            by_category = {row[0]: row[1] for row in by_category_rows}

            borrowed_count = by_status.get("borrowed", 0)

            return {
                "total": total,
                "by_status": by_status,
                "by_category": by_category,
                "borrowed_count": borrowed_count,
            }
