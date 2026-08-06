"""HrMixin — HR request CRUD, single-step approval, and staff listing."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select, text

from session import get_session_local


class HrMixin:
    """HR request CRUD, single-step approval, and staff lookup."""

    # ── CRUD ─────────────────────────────────────────────────────────

    def list_hr_requests(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._enterprise_list(
            self._hr_requests_table, user=user
        )

    def get_hr_request(
        self, request_id: int, user: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope_clause = self._scope_single(ctx, self._hr_requests_table, request_id)
            row = (
                db.execute(
                    select(self._hr_requests_table).where(scope_clause)
                )
                .mappings()
                .first()
            )
            return self._stringify_dt(dict(row)) if row else None

    def create_hr_request(
        self, payload: dict[str, Any], user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        payload = {
            **payload,
            "status": "processing",
            "applicant_id": user.get("id") if user else None,
        }
        return self._enterprise_create(
            self._hr_requests_table, payload, user=user
        )

    def update_hr_request(
        self,
        request_id: int,
        payload: dict[str, Any],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        return self._enterprise_update(
            self._hr_requests_table, request_id, payload, user=user
        )

    # ── Approval (single-step) ──────────────────────────────────────

    def approve_hr_request(
        self,
        request_id: int,
        action: str,
        comment: str | None = None,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Approve or reject an HR request. Only the designated approver may act."""
        request = self.get_hr_request(request_id, user=user)
        if request is None:
            return None
        if request.get("status") != "processing":
            raise ValueError("只能审批处理中的申请")
        if action not in ("approve", "reject"):
            raise ValueError("审批动作必须是 approve 或 reject")

        approved_by = request.get("approved_by")
        user_id = user.get("id") if user else None
        if approved_by is not None:
            if user_id is None or str(approved_by) != str(user_id):
                raise ValueError("您不是该申请的审批人")

        new_status = "approved" if action == "approve" else "rejected"
        return self._enterprise_update(
            self._hr_requests_table,
            request_id,
            {
                "status": new_status,
                "approved_by": user_id,
                "approved_at": self._now_iso(),
            },
            user=user,
        )

    # ── Views ───────────────────────────────────────────────────────

    def get_hr_pending(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Requests that need the current user's approval."""
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._hr_requests_table)
            table = self._hr_requests_table
            uid = user.get("id") if user else None
            rows = (
                db.execute(
                    select(table)
                    .where(scope)
                    .where(table.c.status == "processing")
                    .where(table.c.approved_by == uid)
                    .order_by(table.c.id.desc())
                )
                .mappings()
                .all()
            )
            return self.list_response(
                [self._stringify_dt(dict(row)) for row in rows]
            )

    def get_hr_my_initiated(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Requests initiated by the current user."""
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._hr_requests_table)
            table = self._hr_requests_table
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
            return self.list_response(
                [self._stringify_dt(dict(row)) for row in rows]
            )

    # ── Staff list ──────────────────────────────────────────────────

    def get_hr_staff(
        self,
        user: dict[str, Any] | None = None,
        dept_id: str | None = None,
    ) -> dict[str, Any]:
        """List staff from the users table, scope-filtered by role.

        - super_admin / org_admin: see all users in org
        - dept_leader: see users in own department
        - staff: see only themselves
        """
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            uid = user.get("id") if user else None
            default_org = ctx.default_org_id if ctx else "default"
            default_dept = ctx.default_dept_id if ctx else None
            is_super = ctx.is_super_admin if ctx else False
            roles = ctx.roles if ctx else []
            is_org_admin = "org_admin" in roles
            is_dept_leader = "dept_leader" in roles

            base_sql = """
                SELECT u.id, u.username, u.display_name, u.email, u.phone,
                       u.is_active, u.last_login_at, u.created_at
                FROM users u
                LEFT JOIN user_org_memberships uom ON u.id = uom.user_id
                LEFT JOIN user_department_memberships udm ON u.id = udm.user_id
                WHERE 1=1
            """
            params: dict[str, Any] = {}

            if is_super:
                pass
            elif is_org_admin or is_dept_leader:
                base_sql += " AND uom.org_id = :org"
                params["org"] = default_org
                if dept_id:
                    base_sql += " AND udm.department_id = :dept"
                    params["dept"] = dept_id
                elif is_dept_leader and default_dept:
                    base_sql += " AND udm.department_id = :dept"
                    params["dept"] = default_dept
            else:
                base_sql += " AND u.id = :uid"
                params["uid"] = uid

            base_sql += " GROUP BY u.id ORDER BY u.id ASC"
            rows = db.execute(text(base_sql), params).mappings().all()
            return self.list_response([dict(row) for row in rows])

    # ── Statistics ───────────────────────────────────────────────────

    def get_hr_stats(
        self, user: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return HR request statistics scoped to *user*."""
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_filter(ctx, self._hr_requests_table)
            table = self._hr_requests_table

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
                    select(table.c.request_type, func.count())
                    .where(scope)
                    .group_by(table.c.request_type)
                )
                .all()
            )
            by_type = {row[0]: row[1] for row in by_type_rows}

            return {
                "total": total,
                "by_status": by_status,
                "by_type": by_type,
            }
