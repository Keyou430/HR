"""FinanceMixin — finance claims (multi-step approval) and budgets CRUD."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, update

from session import get_session_local


class FinanceMixin:
    """Finance claims and budgets CRUD + multi-step approval."""

    # ── Helper ──────────────────────────────────────────────────────

    def _mask_amount(self, row: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
        """Mask amount field if user lacks finance:view permission."""
        if user is None:
            return row
        permissions = user.get("permissions", [])
        if "finance:view" not in permissions:
            row = dict(row)
            row["amount"] = None
        return row

    # ═════════════════════════════════════════════════════════════════
    # CLAIMS
    # ═════════════════════════════════════════════════════════════════

    def list_finance_claims(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._finance_claims_table)
            rows = (
                db.execute(
                    select(self._finance_claims_table)
                    .where(scope)
                    .order_by(self._finance_claims_table.c.id.desc())
                )
                .mappings()
                .all()
            )
            items = [self._mask_amount(self._stringify_dt(dict(row)), user) for row in rows]
            return self.list_response(items)

    def get_finance_claim(
        self, claim_id: int, user: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope_clause = self._scope_single(ctx, self._finance_claims_table, claim_id)
            row = (
                db.execute(
                    select(self._finance_claims_table).where(scope_clause)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            return self._mask_amount(self._stringify_dt(dict(row)), user)

    def create_finance_claim(
        self, payload: dict[str, Any], user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = {
            **payload,
            "status": "pending",
            "applicant_id": user.get("id") if user else None,
        }
        result = self._enterprise_create(
            self._finance_claims_table, payload, user=user
        )
        return self._mask_amount(result, user)

    def update_finance_claim(
        self,
        claim_id: int,
        payload: dict[str, Any],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        result = self._enterprise_update(
            self._finance_claims_table, claim_id, payload, user=user
        )
        if result is None:
            return None
        return self._mask_amount(result, user)

    # ── Claim approval (multi-step, same pattern as OA) ─────────────

    def submit_finance_claim(
        self,
        claim_id: int,
        approval_steps: list[dict[str, Any]],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Submit a claim for approval. Creates approval records and sets current_handler."""
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                scope_clause = self._scope_single(ctx, self._finance_claims_table, claim_id)
                existing = (
                    db.execute(select(self._finance_claims_table).where(scope_clause))
                    .mappings()
                    .first()
                )
                if existing is None:
                    return None
                if existing["status"] != "pending":
                    raise ValueError("只能提交待提交的报销单")

                for step in approval_steps:
                    db.execute(
                        self._finance_approval_records_table.insert().values(
                            claim_id=claim_id,
                            approver_id=step["approver_id"],
                            step_order=step.get("step_order", 1),
                            created_at=self._now_iso(),
                        )
                    )

                first_handler = str(approval_steps[0]["approver_id"])
                db.execute(
                    update(self._finance_claims_table)
                    .where(scope_clause)
                    .values(
                        status="processing",
                        current_handler=first_handler,
                        updated_at=self._now_iso(),
                    )
                )
                db.commit()

                row = (
                    db.execute(select(self._finance_claims_table).where(scope_clause))
                    .mappings()
                    .first()
                )
                return self._mask_amount(self._stringify_dt(dict(row)), user)

    def _get_current_finance_approval_step(self, db, claim_id: int):
        """Return the first unprocessed approval record for a claim."""
        return (
            db.execute(
                select(self._finance_approval_records_table)
                .where(self._finance_approval_records_table.c.claim_id == claim_id)
                .where(self._finance_approval_records_table.c.action.is_(None))
                .order_by(self._finance_approval_records_table.c.step_order)
            )
            .mappings()
            .first()
        )

    def _get_next_finance_step(self, db, claim_id: int, current_order: int):
        """Return the next unprocessed approval record after current_order."""
        return (
            db.execute(
                select(self._finance_approval_records_table)
                .where(self._finance_approval_records_table.c.claim_id == claim_id)
                .where(self._finance_approval_records_table.c.action.is_(None))
                .where(self._finance_approval_records_table.c.step_order > current_order)
                .order_by(self._finance_approval_records_table.c.step_order)
            )
            .mappings()
            .first()
        )

    def approve_finance_claim(
        self,
        claim_id: int,
        action: str,
        comment: str | None = None,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Approve, reject, or return a claim at the current step."""
        if action not in ("approve", "reject", "return"):
            raise ValueError("审批动作必须是 approve, reject 或 return")

        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                scope_clause = self._scope_single(ctx, self._finance_claims_table, claim_id)
                existing = (
                    db.execute(select(self._finance_claims_table).where(scope_clause))
                    .mappings()
                    .first()
                )
                if existing is None:
                    return None
                if existing["status"] != "processing":
                    raise ValueError("只能审批处理中的报销单")

                current_step = self._get_current_finance_approval_step(db, claim_id)
                if current_step is None:
                    raise ValueError("没有待处理的审批步骤")

                user_id = user.get("id") if user else None
                if str(current_step["approver_id"]) != str(user_id):
                    raise ValueError("您不是当前审批人")

                now = self._now_iso()
                db.execute(
                    update(self._finance_approval_records_table)
                    .where(self._finance_approval_records_table.c.id == current_step["id"])
                    .values(action=action, comment=comment, created_at=now)
                )

                if action == "approve":
                    next_step = self._get_next_finance_step(db, claim_id, current_step["step_order"])
                    if next_step:
                        db.execute(
                            update(self._finance_claims_table)
                            .where(scope_clause)
                            .values(
                                current_handler=str(next_step["approver_id"]),
                                updated_at=now,
                            )
                        )
                        db.commit()
                        row = db.execute(
                            select(self._finance_claims_table).where(scope_clause)
                        ).mappings().first()
                        return self._mask_amount(self._stringify_dt(dict(row)), user)
                    else:
                        db.execute(
                            update(self._finance_claims_table)
                            .where(scope_clause)
                            .values(
                                status="approved",
                                current_handler=None,
                                updated_at=now,
                            )
                        )
                elif action == "reject":
                    db.execute(
                        update(self._finance_claims_table)
                        .where(scope_clause)
                        .values(
                            status="rejected",
                            current_handler=None,
                            updated_at=now,
                        )
                    )
                elif action == "return":
                    db.execute(
                        update(self._finance_claims_table)
                        .where(scope_clause)
                        .values(
                            status="pending",
                            current_handler=None,
                            updated_at=now,
                        )
                    )

                db.commit()
                row = (
                    db.execute(select(self._finance_claims_table).where(scope_clause))
                    .mappings()
                    .first()
                )
                return self._mask_amount(self._stringify_dt(dict(row)), user)

    def get_finance_claim_approvals(
        self, claim_id: int, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return approval records for a claim."""
        with self._session() as db:
            rows = (
                db.execute(
                    select(self._finance_approval_records_table)
                    .where(self._finance_approval_records_table.c.claim_id == claim_id)
                    .order_by(self._finance_approval_records_table.c.step_order)
                )
                .mappings()
                .all()
            )
            return self.list_response([dict(row) for row in rows])

    # ── Claim views ────────────────────────────────────────────────

    def get_finance_my_pending(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Claims where current user is the current handler."""
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._finance_claims_table)
            table = self._finance_claims_table
            uid = user.get("id") if user else None
            rows = (
                db.execute(
                    select(table)
                    .where(scope)
                    .where(table.c.status == "processing")
                    .where(table.c.current_handler == str(uid) if uid else table.c.current_handler.is_(None))
                    .order_by(table.c.id.desc())
                )
                .mappings()
                .all()
            )
            items = [self._mask_amount(self._stringify_dt(dict(row)), user) for row in rows]
            return self.list_response(items)

    def get_finance_my_initiated(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Claims initiated by the current user."""
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._finance_claims_table)
            table = self._finance_claims_table
            uid = user.get("id") if user else None
            rows = (
                db.execute(
                    select(table)
                    .where(scope)
                    .where(table.c.applicant_id == uid)
                    .order_by(table.c.id.desc())
                )
                .mappings()
                .all()
            )
            items = [self._mask_amount(self._stringify_dt(dict(row)), user) for row in rows]
            return self.list_response(items)

    def get_finance_claims_stats(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._finance_claims_table)
            table = self._finance_claims_table

            total = db.scalar(select(func.count()).select_from(table).where(scope)) or 0

            by_status_rows = (
                db.execute(
                    select(table.c.status, func.count())
                    .where(scope)
                    .group_by(table.c.status)
                ).all()
            )
            by_status = {row[0]: row[1] for row in by_status_rows}

            return {"total": total, "by_status": by_status}

    # ═════════════════════════════════════════════════════════════════
    # BUDGETS
    # ═════════════════════════════════════════════════════════════════

    def list_finance_budgets(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._enterprise_list(self._finance_budgets_table, user=user)

    def get_finance_budget(
        self, budget_id: int, user: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope_clause = self._scope_single(ctx, self._finance_budgets_table, budget_id)
            row = (
                db.execute(
                    select(self._finance_budgets_table).where(scope_clause)
                )
                .mappings()
                .first()
            )
            return self._stringify_dt(dict(row)) if row else None

    def create_finance_budget(
        self, payload: dict[str, Any], user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._enterprise_create(self._finance_budgets_table, payload, user=user)

    def update_finance_budget(
        self,
        budget_id: int,
        payload: dict[str, Any],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self._enterprise_update(
            self._finance_budgets_table, budget_id, payload, user=user
        )

    def get_finance_budget_stats(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._finance_budgets_table)
            table = self._finance_budgets_table

            total = db.scalar(select(func.count()).select_from(table).where(scope)) or 0

            total_amount = db.scalar(
                select(func.sum(table.c.amount_total)).where(scope)
            ) or 0.0

            total_used = db.scalar(
                select(func.sum(table.c.amount_used)).where(scope)
            ) or 0.0

            by_category_rows = (
                db.execute(
                    select(table.c.category, func.count())
                    .where(scope)
                    .group_by(table.c.category)
                ).all()
            )
            by_category = {row[0]: row[1] for row in by_category_rows}

            return {
                "total": total,
                "total_amount": total_amount,
                "total_used": total_used,
                "by_category": by_category,
            }
