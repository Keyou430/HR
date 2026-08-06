"""Shared helpers, SQL fragments, and dependencies for admin routers."""

from __future__ import annotations

import csv
import io
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from audit_logger import audit_log
from auth.dependencies import get_current_user, require_permission
from auth.password import hash_password
from auth.router import _ensure_seed_data
from auth.sessions import revoke_all_user_sessions
from authorization.permissions import PERMISSION_GROUPS, PERMISSIONS
from authorization.rbac import SUPER_ADMIN_ROLE
from schemas import (
    AdminCreateUserRequest,
    AdminDeptCreateRequest,
    AdminDeptItem,
    AdminDeptListResponse,
    AdminDeptReorderRequest,
    AdminDeptUpdateRequest,
    AdminNoticeCreateRequest,
    AdminNoticeItem,
    AdminNoticeListResponse,
    AdminNoticeUpdateRequest,
    AdminOrgCreateRequest,
    AdminOrgItem,
    AdminOrgListResponse,
    AdminOrgUpdateRequest,
    AdminRoleCreateRequest,
    AdminRoleItem,
    AdminRoleListResponse,
    AdminRolePermissionUpdateRequest,
    AdminRoleUpdateRequest,
    AdminServiceCreateRequest,
    AdminServiceItem,
    AdminServiceListResponse,
    AdminServiceUpdateRequest,
    AdminSessionItem,
    AdminSessionListResponse,
    AdminResetPasswordRequest,
    AdminResetPasswordResponse,
    AdminSetActiveRequest,
    AdminSetRolesRequest,
    AdminUserItem,
    AdminUserListResponse,
    AIQueryLogItem,
    AIQueryLogListResponse,
    AnomalyStats,
    AuditLogItem,
    AuditLogListResponse,
)
from session import get_db
from utils import _ts

logger = logging.getLogger("replica")

# ── Reusable SQL fragments ──────────────────────────────────────────
_USER_WITH_ROLES_SQL = """
    SELECT u.id, u.username, u.display_name, u.email, u.is_active,
           u.last_login_at, u.created_at,
           COALESCE(GROUP_CONCAT(r.code, ','), '') AS role_codes,
           COALESCE(GROUP_CONCAT(r.name, ','), '') AS role_names
      FROM users u
      LEFT JOIN role_bindings rb ON rb.user_id = u.id
      LEFT JOIN roles r ON r.id = rb.role_id
"""

_USER_LIST_SQL = _USER_WITH_ROLES_SQL + " GROUP BY u.id ORDER BY u.id"

_USER_BY_ID_SQL = _USER_WITH_ROLES_SQL + " WHERE u.id = :uid GROUP BY u.id"


def require_admin(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Reject non-super_admin callers with 403."""
    if SUPER_ADMIN_ROLE not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限",
        )
    return current_user


# ── Shared helpers ────────────────────────────────────────────────────


def _build_user_item(row: Any) -> AdminUserItem:
    """Build an AdminUserItem from a users + GROUP_CONCAT row."""
    (
        uid, username, display_name, email, is_active,
        last_login_at, created_at, role_codes_str, role_names_str,
    ) = row
    roles = [c for c in (role_codes_str or "").split(",") if c]
    role_names = [n for n in (role_names_str or "").split(",") if n]
    return AdminUserItem(
        id=uid,
        username=username,
        display_name=display_name,
        email=email,
        is_active=bool(int(is_active)),
        roles=roles,
        role_names=role_names,
        last_login_at=last_login_at,
        created_at=created_at,
    )


def _load_user_or_404(db: Session, user_id: int) -> dict[str, Any]:
    """Load a user by id or raise 404."""
    row = db.execute(
        text("SELECT id, username, display_name, is_active FROM users WHERE id = :uid"),
        {"uid": user_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"id": row[0], "username": row[1], "display_name": row[2], "is_active": bool(int(row[3]))}


def _count_active_super_admins(db: Session) -> int:
    """Return the number of active users who hold the super_admin role."""
    row = db.execute(
        text(
            "SELECT COUNT(DISTINCT u.id) FROM users u "
            "JOIN role_bindings rb ON rb.user_id = u.id "
            "JOIN roles r ON r.id = rb.role_id "
            "WHERE r.code = :rc AND u.is_active = 1"
        ),
        {"rc": SUPER_ADMIN_ROLE},
    ).fetchone()
    return row[0] if row else 0


def _user_has_role(db: Session, user_id: int, role_code: str) -> bool:
    """Check whether a user currently holds a specific role."""
    row = db.execute(
        text(
            "SELECT 1 FROM role_bindings rb "
            "JOIN roles r ON r.id = rb.role_id "
            "WHERE rb.user_id = :uid AND r.code = :rc"
        ),
        {"uid": user_id, "rc": role_code},
    ).fetchone()
    return row is not None


def _load_role_by_id(db: Session, role_id: int) -> AdminRoleItem:
    """Load a role by id and return an AdminRoleItem."""
    row = db.execute(
        text(
            "SELECT id, code, name, description, is_system, org_id, "
            "created_at, updated_at FROM roles WHERE id = :rid"
        ),
        {"rid": role_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    perm_rows = db.execute(
        text(
            "SELECT p.code FROM role_permissions rp "
            "JOIN permissions p ON p.id = rp.permission_id "
            "WHERE rp.role_id = :rid ORDER BY p.code"
        ),
        {"rid": role_id},
    ).fetchall()
    perm_codes = [r[0] for r in perm_rows]
    return AdminRoleItem(
        id=row[0], code=row[1], name=row[2], description=row[3],
        is_system=bool(int(row[4])) if row[4] is not None else False,
        org_id=row[5],
        permission_codes=perm_codes,
        permissions=perm_codes,  # compat
        created_at=row[6],
        updated_at=row[7],
    )


def _load_role_or_404(
    db: Session, role_id: int, allow_system: bool = True,
) -> dict[str, Any]:
    """Load a role by id or raise 404. If allow_system is False, raise 403 for system roles."""
    row = db.execute(
        text(
            "SELECT id, code, name, description, is_system, org_id, "
            "created_at, updated_at FROM roles WHERE id = :rid"
        ),
        {"rid": role_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    is_system = bool(int(row[4])) if row[4] is not None else False
    if not allow_system and is_system:
        raise HTTPException(status_code=403, detail="系统角色不可编辑")
    return {
        "id": row[0], "code": row[1], "name": row[2],
        "description": row[3], "is_system": is_system,
        "org_id": row[5], "created_at": row[6], "updated_at": row[7],
    }


def _bind_permissions(
    db: Session, role_id: int, perm_codes: list[str],
) -> None:
    """Insert role_permissions rows for *role_id* matching *perm_codes*."""
    placeholders = ", ".join(f":pc{i}" for i in range(len(perm_codes)))
    params: dict[str, Any] = {f"pc{i}": code for i, code in enumerate(perm_codes)}
    perm_rows = db.execute(
        text(
            f"SELECT id, code FROM permissions WHERE code IN ({placeholders})"
        ),
        params,
    ).fetchall()
    perm_id_map = {r[1]: r[0] for r in perm_rows}
    for code in perm_codes:
        perm_id = perm_id_map.get(code)
        if perm_id is None:
            continue
        existing = db.execute(
            text(
                "SELECT 1 FROM role_permissions "
                "WHERE role_id = :rid AND permission_id = :pid"
            ),
            {"rid": role_id, "pid": perm_id},
        ).fetchone()
        if existing is None:
            db.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:rid, :pid)"
                ),
                {"rid": role_id, "pid": perm_id},
            )


def _build_notice_item(row: Any) -> AdminNoticeItem:
    """Build an AdminNoticeItem from a portal_notices row (mapping or tuple)."""
    from collections.abc import Mapping as _Mapping

    # SQLAlchemy RowMapping, plain dict, or Row._mapping → named access
    if isinstance(row, _Mapping):
        return AdminNoticeItem(
            id=row["id"], title=row["title"], source=row["source"], category=row["category"],
            body=row["body"], pinned=bool(int(row["pinned"])) if row["pinned"] is not None else False,
            published_at=row["published_at"], read_count=int(row["read_count"]) if row["read_count"] is not None else 0,
            status=row.get("status"), org_id=row.get("org_id"), department_id=row.get("department_id"),
            visibility=row.get("visibility", "org"),
            created_at=row.get("created_at"), updated_at=row.get("updated_at"),
        )
    # SQLAlchemy Row — use _mapping for named access
    if hasattr(row, "_mapping"):
        return _build_notice_item(row._mapping)
    # Fallback: positional tuple (legacy compatibility)
    return AdminNoticeItem(
        id=row[0], title=row[1], source=row[2], category=row[3],
        body=row[4], pinned=bool(int(row[5])) if row[5] is not None else False,
        published_at=row[6], read_count=int(row[7]) if row[7] is not None else 0,
        status=row[8], org_id=row[9], department_id=row[10],
        visibility=row[12] if len(row) > 12 else "org",
        created_at=row[14] if len(row) > 14 else None,
        updated_at=row[15] if len(row) > 15 else None,
    )


def _build_dept_item(row: Any) -> AdminDeptItem:
    """Build an AdminDeptItem from a departments row."""
    return AdminDeptItem(
        id=row[0], org_id=row[1], name=row[2], parent_id=row[3],
        path=row[4] or "", level=int(row[5]) if row[5] is not None else 0,
        sort_order=int(row[6]) if row[6] is not None else 0,
        is_active=bool(int(row[7])) if row[7] is not None else True,
        created_at=row[8], updated_at=row[9],
    )


def _build_dept_tree(rows: list[Any]) -> list[AdminDeptItem]:
    """Convert flat department rows into a nested tree structure."""
    dept_map: dict[str, AdminDeptItem] = {}
    for r in rows:
        item = _build_dept_item(r)
        dept_map[item.id] = item

    roots: list[AdminDeptItem] = []
    for item in dept_map.values():
        if item.parent_id and item.parent_id in dept_map:
            dept_map[item.parent_id].children.append(item)
        else:
            roots.append(item)

    def sort_children(item: AdminDeptItem) -> None:
        item.children.sort(key=lambda d: (d.sort_order, d.id))
        for child in item.children:
            sort_children(child)

    for root in roots:
        sort_children(root)
    roots.sort(key=lambda d: (d.sort_order, d.id))
    return roots


# ── Org-scoping helpers ───────────────────────────────────────────────


def _apply_org_scope(
    conditions: list[str],
    params: dict[str, Any],
    current_user: dict[str, Any],
) -> None:
    """Add org-scoping WHERE clause for super_admin bypass."""
    if SUPER_ADMIN_ROLE in current_user.get("roles", []):
        return
    org_id = current_user.get("default_org_id")
    if org_id:
        conditions.append("(org_id = :scope_org_id OR org_id IS NULL)")
        params["scope_org_id"] = org_id


def _org_count_condition(current_user: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return (sql_fragment, params) for org-scoping tables that have org_id."""
    if SUPER_ADMIN_ROLE in current_user.get("roles", []):
        return "", {}
    org_id = current_user.get("default_org_id")
    if org_id:
        return (
            "(org_id = :scope_org_id OR org_id IS NULL)",
            {"scope_org_id": org_id},
        )
    return "", {}


def _user_org_condition(current_user: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return (sql_fragment, params) for org-scoping the users table."""
    if SUPER_ADMIN_ROLE in current_user.get("roles", []):
        return "", {}
    org_id = current_user.get("default_org_id")
    if org_id:
        return (
            "id IN (SELECT user_id FROM user_org_memberships WHERE org_id = :scope_org_id)",
            {"scope_org_id": org_id},
        )
    return "", {}


def _prefix_and(condition: str) -> str:
    """Prefix a WHERE fragment with ' AND ' if non-empty."""
    return (" AND " + condition.lstrip()) if condition.strip() else ""
