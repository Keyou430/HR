"""RepairMixin — repair ticket CRUD and lifecycle operations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from session import get_session_local


class RepairMixin:
    """Repair ticket CRUD and lifecycle mixed into PortalStore."""

    # ── CRUD ─────────────────────────────────────────────────────────

    def list_repair_tickets(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._enterprise_list(
            self._enterprise_repair_tickets_table, user=user
        )

    def get_repair_ticket(
        self, ticket_id: int, user: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope_clause = self._scope_single(ctx, self._enterprise_repair_tickets_table, ticket_id)
            row = (
                db.execute(
                    select(self._enterprise_repair_tickets_table).where(scope_clause)
                )
                .mappings()
                .first()
            )
            return self._stringify_dt(dict(row)) if row else None

    def create_repair_ticket(
        self, payload: dict[str, Any], user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = {
            **payload,
            "status": payload.get("status") or "submitted",
            "priority": payload.get("priority") or "normal",
            "requester_id": user.get("id") if user else None,
        }
        return self._enterprise_create(
            self._enterprise_repair_tickets_table, payload, user=user
        )

    def update_repair_ticket(
        self,
        ticket_id: int,
        payload: dict[str, Any],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self._enterprise_update(
            self._enterprise_repair_tickets_table, ticket_id, payload, user=user
        )

    # ── Lifecycle operations ──────────────────────────────────────────

    def _validate_repair_state(
        self, ticket_id: int, allowed: set[str], user: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        """Fetch a ticket and validate its status is in *allowed*.
        Returns the ticket dict or None (ticket not found).
        Raises ValueError on invalid status transition.
        """
        ticket = self.get_repair_ticket(ticket_id, user=user)
        if ticket is None:
            return None
        if ticket.get("status") not in allowed:
            raise ValueError(
                f"工单状态为 '{ticket.get('status')}'，不允许此操作"
            )
        return ticket

    def assign_repair_ticket(
        self,
        ticket_id: int,
        assignee: str,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Assign ticket → status 'processing' (from 'submitted')."""
        self._validate_repair_state(ticket_id, {"submitted"}, user=user)
        return self._enterprise_update(
            self._enterprise_repair_tickets_table,
            ticket_id,
            {"status": "processing", "assignee": assignee},
            user=user,
        )

    def complete_repair_ticket(
        self,
        ticket_id: int,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Complete ticket → status 'completed' (from 'processing')."""
        self._validate_repair_state(ticket_id, {"processing"}, user=user)
        return self._enterprise_update(
            self._enterprise_repair_tickets_table,
            ticket_id,
            {"status": "completed", "completed_at": self._now_iso()},
            user=user,
        )

    def rate_repair_ticket(
        self,
        ticket_id: int,
        rating: int,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Rate ticket → status 'rated' (from 'completed'). Rating 1-5."""
        if not 1 <= rating <= 5:
            raise ValueError("评分必须在 1-5 之间")
        self._validate_repair_state(ticket_id, {"completed"}, user=user)
        return self._enterprise_update(
            self._enterprise_repair_tickets_table,
            ticket_id,
            {"status": "rated", "rating": rating},
            user=user,
        )

    # ── Statistics ────────────────────────────────────────────────────

    def get_repair_stats(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return repair ticket statistics scoped to *user*."""
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._enterprise_repair_tickets_table)
            table = self._enterprise_repair_tickets_table

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

            by_priority_rows = (
                db.execute(
                    select(table.c.priority, func.count())
                    .where(scope)
                    .group_by(table.c.priority)
                )
                .all()
            )
            by_priority = {row[0]: row[1] for row in by_priority_rows}

            return {
                "total": total,
                "by_status": by_status,
                "by_priority": by_priority,
            }
