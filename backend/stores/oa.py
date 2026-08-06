"""OaMixin — OA flow CRUD and approval lifecycle."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, insert, select, update

from session import get_session_local


class OaMixin:
    """OA flow CRUD and approval lifecycle mixed into PortalStore."""

    # ── CRUD ─────────────────────────────────────────────────────────

    def list_oa_flows(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._enterprise_list(
            self._enterprise_oa_flows_table, user=user
        )

    def get_oa_flow(
        self, flow_id: int, user: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope_clause = self._scope_single(ctx, self._enterprise_oa_flows_table, flow_id)
            row = (
                db.execute(
                    select(self._enterprise_oa_flows_table).where(scope_clause)
                )
                .mappings()
                .first()
            )
            return self._stringify_dt(dict(row)) if row else None

    def create_oa_flow(
        self, payload: dict[str, Any], user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = {
            **payload,
            "status": payload.get("status") or "pending",
            "initiator_id": user.get("id") if user else None,
        }
        return self._enterprise_create(
            self._enterprise_oa_flows_table, payload, user=user
        )

    def update_oa_flow(
        self,
        flow_id: int,
        payload: dict[str, Any],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self._enterprise_update(
            self._enterprise_oa_flows_table, flow_id, payload, user=user
        )

    # ── Approval lifecycle ───────────────────────────────────────────

    def submit_oa_flow(
        self,
        flow_id: int,
        approval_steps: list[dict[str, Any]],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Submit a pending flow for approval. Creates approval records.
        *approval_steps*: [{"approver_id": int, "step_order": int}, ...]
        First step's approver becomes the flow's current_handler.
        """
        if not approval_steps:
            raise ValueError("审批步骤不能为空")

        ticket = self.get_oa_flow(flow_id, user=user)
        if ticket is None:
            return None
        if ticket["status"] != "pending":
            raise ValueError("只能提交状态为 'pending' 的流程")

        now = self._now_iso()
        with self._lock:
            with self._session() as db:
                for step in approval_steps:
                    db.execute(
                        insert(self._oa_approval_records_table).values(
                            flow_id=flow_id,
                            approver_id=step["approver_id"],
                            step_order=step["step_order"],
                            action=None,
                            comment=None,
                            created_at=now,
                        )
                    )

                first_approver_id = approval_steps[0]["approver_id"]
                first_handler = str(first_approver_id)

                db.execute(
                    update(self._enterprise_oa_flows_table)
                    .where(self._enterprise_oa_flows_table.c.id == flow_id)
                    .values(
                        status="processing",
                        current_handler=first_handler,
                        updated_at=now,
                    )
                )
                db.commit()

        return self.get_oa_flow(flow_id, user=user)

    def _get_current_approval_step(
        self, db: Any, flow_id: int
    ) -> dict[str, Any] | None:
        """Find the first unprocessed approval step for *flow_id*."""
        row = (
            db.execute(
                select(self._oa_approval_records_table)
                .where(
                    and_(
                        self._oa_approval_records_table.c.flow_id == flow_id,
                        self._oa_approval_records_table.c.action.is_(None),
                    )
                )
                .order_by(self._oa_approval_records_table.c.step_order)
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None

    def approve_oa_step(
        self,
        flow_id: int,
        action: str,
        comment: str | None = None,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Approve, reject, or return the current approval step.
        *action*: 'approve', 'reject', or 'return'.
        """
        if action not in ("approve", "reject", "return"):
            raise ValueError("action 必须是 'approve'、'reject' 或 'return'")

        ticket = self.get_oa_flow(flow_id, user=user)
        if ticket is None:
            return None
        if ticket["status"] != "processing":
            raise ValueError("只能审批状态为 'processing' 的流程")

        user_id = user.get("id") if user else None
        now = self._now_iso()

        with self._lock:
            with self._session() as db:
                current_step = self._get_current_approval_step(db, flow_id)
                if current_step is None:
                    raise ValueError("该流程没有待审批的步骤")

                if current_step["approver_id"] != user_id:
                    raise ValueError("您不是当前审批人")

                # Record this approval action
                db.execute(
                    update(self._oa_approval_records_table)
                    .where(self._oa_approval_records_table.c.id == current_step["id"])
                    .values(action=action, comment=comment, created_at=now)
                )

                if action == "approve":
                    next_step = self._get_current_approval_step(db, flow_id)
                    if next_step:
                        new_handler = str(next_step["approver_id"])
                        db.execute(
                            update(self._enterprise_oa_flows_table)
                            .where(self._enterprise_oa_flows_table.c.id == flow_id)
                            .values(current_handler=new_handler, updated_at=now)
                        )
                    else:
                        # All steps approved
                        db.execute(
                            update(self._enterprise_oa_flows_table)
                            .where(self._enterprise_oa_flows_table.c.id == flow_id)
                            .values(
                                status="approved",
                                current_handler=None,
                                updated_at=now,
                            )
                        )
                elif action == "reject":
                    db.execute(
                        update(self._enterprise_oa_flows_table)
                        .where(self._enterprise_oa_flows_table.c.id == flow_id)
                        .values(status="rejected", current_handler=None, updated_at=now)
                    )
                elif action == "return":
                    db.execute(
                        update(self._enterprise_oa_flows_table)
                        .where(self._enterprise_oa_flows_table.c.id == flow_id)
                        .values(
                            current_handler=str(ticket["initiator_id"]),
                            updated_at=now,
                        )
                    )

                db.commit()

        return self.get_oa_flow(flow_id, user=user)

    # ── Query views ──────────────────────────────────────────────────

    def get_oa_pending(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Flows where current_user is the current handler."""
        if user is None:
            return self.list_response([])
        user_id = str(user.get("id", ""))
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._enterprise_oa_flows_table)
            rows = (
                db.execute(
                    select(self._enterprise_oa_flows_table)
                    .where(
                        and_(
                            scope,
                            self._enterprise_oa_flows_table.c.status == "processing",
                            self._enterprise_oa_flows_table.c.current_handler == user_id,
                        )
                    )
                    .order_by(self._enterprise_oa_flows_table.c.id.desc())
                )
                .mappings()
                .all()
            )
            return self.list_response(
                [self._stringify_dt(dict(row)) for row in rows]
            )

    def get_oa_my_flows(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Flows initiated by current_user."""
        if user is None:
            return self.list_response([])
        user_id = user.get("id")
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._enterprise_oa_flows_table)
            rows = (
                db.execute(
                    select(self._enterprise_oa_flows_table)
                    .where(
                        and_(
                            scope,
                            self._enterprise_oa_flows_table.c.initiator_id == user_id,
                        )
                    )
                    .order_by(self._enterprise_oa_flows_table.c.id.desc())
                )
                .mappings()
                .all()
            )
            return self.list_response(
                [self._stringify_dt(dict(row)) for row in rows]
            )

    def get_oa_history(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Flows the user has participated in (has approval records for)."""
        if user is None:
            return self.list_response([])
        user_id = user.get("id")
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._enterprise_oa_flows_table)

            flow_ids_subq = (
                select(self._oa_approval_records_table.c.flow_id)
                .where(self._oa_approval_records_table.c.approver_id == user_id)
                .distinct()
            )

            rows = (
                db.execute(
                    select(self._enterprise_oa_flows_table)
                    .where(
                        and_(
                            scope,
                            self._enterprise_oa_flows_table.c.id.in_(flow_ids_subq),
                        )
                    )
                    .order_by(self._enterprise_oa_flows_table.c.id.desc())
                )
                .mappings()
                .all()
            )
            return self.list_response(
                [self._stringify_dt(dict(row)) for row in rows]
            )

    def get_oa_flow_approval_records(
        self, flow_id: int, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Get all approval records for a flow."""
        with self._session() as db:
            rows = (
                db.execute(
                    select(self._oa_approval_records_table)
                    .where(self._oa_approval_records_table.c.flow_id == flow_id)
                    .order_by(self._oa_approval_records_table.c.step_order)
                )
                .mappings()
                .all()
            )
            return self.list_response(
                [self._stringify_dt(dict(row)) for row in rows]
            )

    # ── Statistics ────────────────────────────────────────────────────

    def get_oa_stats(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return OA flow statistics scoped to *user*."""
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._enterprise_oa_flows_table)
            table = self._enterprise_oa_flows_table

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

            by_type_rows = (
                db.execute(
                    select(table.c.flow_type, func.count())
                    .where(scope)
                    .group_by(table.c.flow_type)
                )
                .all()
            )
            by_type = {row[0]: row[1] for row in by_type_rows}

            return {
                "total": total,
                "by_status": by_status,
                "by_type": by_type,
            }
