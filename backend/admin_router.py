"""Admin endpoints: user management + RBAC assignment (super_admin only)."""

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
from store import store
from authorization.permissions import PERMISSION_GROUPS, PERMISSIONS, ROLE_PERMISSION_MAP
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
    AdminNewsCreateRequest,
    AdminNewsItem,
    AdminNewsListResponse,
    AdminNewsUpdateRequest,
    AdminOrgCreateRequest,
    AdminOrgItem,
    AdminOrgListResponse,
    AdminOrgUpdateRequest,
    AdminRoleCreateRequest,
    AdminRoleItem,
    AdminRoleListResponse,
    AdminRolePermissionUpdateRequest,
    AdminRoleUpdateRequest,

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

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
logger = logging.getLogger("replica")

# 鈹€鈹€ Reusable SQL fragments 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
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
            detail="闇€瑕佽秴绾х鐞嗗憳鏉冮檺",
        )
    return current_user


def require_notice_manager(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Allow super_admin or users with notice:publish permission."""
    roles = current_user.get("roles", [])
    perms = current_user.get("permissions", [])
    if SUPER_ADMIN_ROLE not in roles and "notice:publish" not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="缂哄皯鏉冮檺: notice:publish",
        )
    return current_user


# 鈹€鈹€ Helpers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


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
        raise HTTPException(status_code=404, detail="鐢ㄦ埛涓嶅瓨鍦?)
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


# 鈹€鈹€ Endpoints 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@router.get("/users", response_model=AdminUserListResponse)
def list_users(
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """List all users with roles. Supports search, pagination.

    - **search**: filter by username or display_name (partial match)
    - **page**: 1-based page number (default 1)
    - **page_size**: items per page (default 20, max 100)
    """
    page_size = max(1, min(page_size, 100))
    page = max(1, page)

    # 鈹€鈹€ Build query 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    where_clause = ""
    params: dict[str, Any] = {}
    if search and search.strip():
        where_clause = " WHERE (u.username LIKE :search OR u.display_name LIKE :search)"
        params["search"] = f"%{search.strip()}%"

    # Total count (no JOINs needed 鈥?just count matching users)
    count_sql = "SELECT COUNT(*) FROM users u" + where_clause
    total = db.execute(text(count_sql), params).fetchone()[0]

    # Paginated query
    offset = (page - 1) * page_size
    paginated_sql = (
        _USER_WITH_ROLES_SQL
        + where_clause
        + " GROUP BY u.id ORDER BY u.id LIMIT :limit OFFSET :offset"
    )
    params["limit"] = page_size
    params["offset"] = offset
    rows = db.execute(text(paginated_sql), params).fetchall()
    items = [_build_user_item(r) for r in rows]
    return {"items": items, "total": total}


@router.get("/roles", response_model=AdminRoleListResponse)
def list_roles(
    db: Session = Depends(get_db),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """List all roles with their permission codes."""
    role_rows = db.execute(
        text(
            "SELECT id, code, name, description, is_system, org_id, "
            "created_at, updated_at FROM roles ORDER BY id"
        )
    ).fetchall()
    perm_rows = db.execute(
        text(
            "SELECT rp.role_id, p.code FROM role_permissions rp "
            "JOIN permissions p ON p.id = rp.permission_id ORDER BY rp.role_id, p.code"
        )
    ).fetchall()
    # Group permissions by role_id
    perm_map: dict[int, list[str]] = {}
    for role_id, code in perm_rows:
        perm_map.setdefault(role_id, []).append(code)
    items = [
        AdminRoleItem(
            id=r[0], code=r[1], name=r[2], description=r[3],
            is_system=bool(int(r[4])) if r[4] is not None else False,
            org_id=r[5],
            permission_codes=perm_map.get(r[0], []),
            permissions=perm_map.get(r[0], []),  # compat
            created_at=r[6],
            updated_at=r[7],
        )
        for r in role_rows
    ]
    return {"items": items}


# 鈹€鈹€ Custom role management 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@router.get("/permissions")
def list_permissions_grouped(
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """List all permissions grouped by resource for the admin role editor.

    Returns PERMISSION_GROUPS 鈥?each group has a display name, resource,
    and list of {code, name} entries.
    """
    return {"groups": PERMISSION_GROUPS}


@router.post("/roles", status_code=201, response_model=AdminRoleItem)
def create_role(
    body: AdminRoleCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminRoleItem:
    """Create a custom (non-system) role with optional permission codes.

    - **name**: display name (1-64 chars)
    - **code**: unique role code (lowercase, underscore-separated)
    - **description**: optional description
    - **org_id**: optional org scope (NULL = platform-wide)
    - **permission_codes**: list of permission codes to assign
    """
    # Ensure seed data exists (commits internally)
    _ensure_seed_data(db)

    ts = _ts()

    # Validate permission codes
    if body.permission_codes:
        valid_codes = {p["code"] for p in PERMISSIONS}
        for code in body.permission_codes:
            if code not in valid_codes:
                raise HTTPException(
                    status_code=400, detail=f"鏈煡鏉冮檺鐮? {code}"
                )

    # Commit any implicit transaction from pre-checks
    db.commit()

    with db.begin():
        # Uniqueness check
        existing = db.execute(
            text("SELECT id FROM roles WHERE code = :code"),
            {"code": body.code},
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="瑙掕壊浠ｇ爜宸茶鍗犵敤")

        result = db.execute(
            text(
                "INSERT INTO roles (code, name, description, is_system, org_id, "
                "created_at, updated_at) "
                "VALUES (:code, :name, :desc, 0, :org_id, :ts, :ts)"
            ),
            {
                "code": body.code,
                "name": body.name,
                "desc": body.description,
                "org_id": body.org_id,
                "ts": ts,
            },
        )
        role_id = result.lastrowid

        # Bind permissions
        if body.permission_codes:
            _bind_permissions(db, role_id, body.permission_codes)

        # Audit log
        audit_log(
            db, action="admin.role.create",
            user_id=current_user["id"], resource_type="role",
            resource_id=str(role_id),
            detail={
                "code": body.code, "name": body.name,
                "permission_codes": body.permission_codes,
            },
        )

    # Re-query
    return _load_role_by_id(db, role_id)


@router.put("/roles/{role_id}", response_model=AdminRoleItem)
def update_role(
    role_id: int,
    body: AdminRoleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminRoleItem:
    """Update a role's name and/or description.

    System roles (is_system=1) cannot be edited.
    """
    role = _load_role_or_404(db, role_id, allow_system=False)
    ts = _ts()

    updates: list[str] = []
    params: dict[str, Any] = {"rid": role_id, "ts": ts}

    if body.name is not None:
        updates.append("name = :name")
        params["name"] = body.name
    if body.description is not None:
        updates.append("description = :desc")
        params["desc"] = body.description

    # Commit any implicit transaction from the SELECT above
    db.commit()

    if updates:
        updates.append("updated_at = :ts")
        with db.begin():
            db.execute(
                text(f"UPDATE roles SET {', '.join(updates)} WHERE id = :rid"),
                params,
            )
            audit_log(
                db, action="admin.role.update",
                user_id=current_user["id"], resource_type="role",
                resource_id=str(role_id),
                detail={
                    "code": role["code"],
                    "before": {"name": role["name"], "description": role["description"]},
                    "after": {
                        "name": body.name if body.name is not None else role["name"],
                        "description": body.description if body.description is not None else role["description"],
                    },
                },
            )

    return _load_role_by_id(db, role_id)


@router.put("/roles/{role_id}/permissions", response_model=AdminRoleItem)
def update_role_permissions(
    role_id: int,
    body: AdminRolePermissionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminRoleItem:
    """Replace all permissions for a role (whole-set replacement).

    System roles (is_system=1) cannot be edited.
    """
    role = _load_role_or_404(db, role_id, allow_system=False)
    ts = _ts()

    # Validate permission codes
    if body.permission_codes:
        valid_codes = {p["code"] for p in PERMISSIONS}
        for code in body.permission_codes:
            if code not in valid_codes:
                raise HTTPException(
                    status_code=400, detail=f"鏈煡鏉冮檺鐮? {code}"
                )

    # Commit any implicit transaction from the SELECT above
    db.commit()

    with db.begin():
        # Remove existing permissions
        db.execute(
            text("DELETE FROM role_permissions WHERE role_id = :rid"),
            {"rid": role_id},
        )
        # Insert new permissions
        if body.permission_codes:
            _bind_permissions(db, role_id, body.permission_codes)
        # Touch updated_at
        db.execute(
            text("UPDATE roles SET updated_at = :ts WHERE id = :rid"),
            {"rid": role_id, "ts": ts},
        )

        audit_log(
            db, action="admin.role.set_permissions",
            user_id=current_user["id"], resource_type="role",
            resource_id=str(role_id),
            detail={
                "code": role["code"],
                "new_permission_codes": body.permission_codes,
            },
        )

    return _load_role_by_id(db, role_id)


# 鈹€鈹€ Role helpers 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


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
        raise HTTPException(status_code=404, detail="瑙掕壊涓嶅瓨鍦?)
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
    """Load a role by id or raise 404. If allow_system is False, raise 403
    for system roles."""
    row = db.execute(
        text(
            "SELECT id, code, name, description, is_system, org_id, "
            "created_at, updated_at FROM roles WHERE id = :rid"
        ),
        {"rid": role_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="瑙掕壊涓嶅瓨鍦?)
    is_system = bool(int(row[4])) if row[4] is not None else False
    if not allow_system and is_system:
        raise HTTPException(status_code=403, detail="绯荤粺瑙掕壊涓嶅彲缂栬緫")
    return {
        "id": row[0], "code": row[1], "name": row[2],
        "description": row[3], "is_system": is_system,
        "org_id": row[5], "created_at": row[6], "updated_at": row[7],
    }


def _bind_permissions(
    db: Session, role_id: int, perm_codes: list[str],
) -> None:
    """Insert role_permissions rows for *role_id* matching *perm_codes*.

    Uses existence-check-then-insert to be dialect-safe (SQLite + PG).
    """
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


# 鈹€鈹€ User management 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€


@router.post("/users", status_code=201, response_model=AdminUserItem)
def create_user(
    body: AdminCreateUserRequest,
    db: Session = Depends(get_db),
    _admin: dict[str, Any] = Depends(require_admin),
) -> AdminUserItem:
    """Create a new user (admin or regular)."""
    # Ensure seed data exists (commits internally, leaves session clean)
    _ensure_seed_data(db)

    pw_hash = hash_password(body.password)
    display_name = body.display_name or body.username
    ts = _ts()

    with db.begin():
        # Uniqueness check (inside transaction)
        existing = db.execute(
            text("SELECT id FROM users WHERE username = :un"),
            {"un": body.username},
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="鐢ㄦ埛鍚嶅凡琚崰鐢?)
        result = db.execute(
            text(
                "INSERT INTO users (username, password_hash, display_name, email, "
                "is_active, token_version, must_change_password, created_at, updated_at) "
                "VALUES (:un, :pw, :dn, :em, 1, 1, 0, :ts, :ts)"
            ),
            {"un": body.username, "pw": pw_hash, "dn": display_name, "em": body.email, "ts": ts},
        )
        uid = result.lastrowid

        # Org membership
        db.execute(
            text(
                "INSERT OR IGNORE INTO user_org_memberships "
                "(user_id, org_id, is_default, created_at) "
                "VALUES (:uid, 'default', 1, :ts)"
            ),
            {"uid": uid, "ts": ts},
        )
        # Department membership
        db.execute(
            text(
                "INSERT OR IGNORE INTO user_department_memberships "
                "(user_id, org_id, department_id, is_primary, created_at) "
                "VALUES (:uid, 'default', 'HQ', 1, :ts)"
            ),
            {"uid": uid, "ts": ts},
        )
        # Role binding
        role_code = SUPER_ADMIN_ROLE if body.is_admin else "dept_staff"
        role_row = db.execute(
            text("SELECT id FROM roles WHERE code = :rc"), {"rc": role_code}
        ).fetchone()
        if role_row:
            db.execute(
                text(
                    "INSERT OR IGNORE INTO role_bindings "
                    "(user_id, role_id, org_id, department_id, created_at) "
                    "VALUES (:uid, :rid, 'default', 'HQ', :ts)"
                ),
                {"uid": uid, "rid": role_row[0], "ts": ts},
            )

        # Audit log (inside transaction)
        audit_log(
            db, action="admin.user.create",
            user_id=_admin["id"], resource_type="user", resource_id=str(uid),
            detail={"new_username": body.username, "is_admin": body.is_admin},
        )

    # Re-query the created user (outside transaction 鈥?auto-begin new implicit tx)
    row = db.execute(text(_USER_BY_ID_SQL), {"uid": uid}).fetchone()
    return _build_user_item(row)


@router.patch("/users/{user_id}/status", response_model=AdminUserItem)
def set_user_status(
    user_id: int,
    body: AdminSetActiveRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminUserItem:
    """Enable or disable a user."""
    user = _load_user_or_404(db, user_id)
    ts = _ts()

    if body.is_active is False:
        # Cannot disable yourself
        if user_id == current_user["id"]:
            raise HTTPException(status_code=400, detail="涓嶈兘绂佺敤褰撳墠鐧诲綍璐﹀彿")
        # Cannot disable the last active super_admin
        if _user_has_role(db, user_id, SUPER_ADMIN_ROLE):
            if _count_active_super_admins(db) <= 1:
                raise HTTPException(status_code=400, detail="涓嶈兘绂佺敤鏈€鍚庝竴鍚嶈秴绾х鐞嗗憳")

    # Commit any implicit transaction from pre-checks above
    db.commit()

    with db.begin():
        db.execute(
            text(
                "UPDATE users SET is_active = :flag, token_version = token_version + 1, "
                "updated_at = :ts WHERE id = :uid"
            ),
            {"flag": 1 if body.is_active else 0, "ts": ts, "uid": user_id},
        )
        if not body.is_active:
            revoke_all_user_sessions(db, user_id)

        # Audit log (inside transaction) 鈥?includes before/after summary
        audit_log(
            db, action="admin.user." + ("enable" if body.is_active else "disable"),
            user_id=current_user["id"], resource_type="user", resource_id=str(user_id),
            detail={
                "target_username": user["username"],
                "before": {"is_active": user["is_active"]},
                "after": {"is_active": body.is_active},
            },
        )

    row = db.execute(text(_USER_BY_ID_SQL), {"uid": user_id}).fetchone()
    return _build_user_item(row)


@router.put("/users/{user_id}/roles", response_model=AdminUserItem)
def set_user_roles(
    user_id: int,
    body: AdminSetRolesRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminUserItem:
    """Replace all role bindings for a user."""
    user = _load_user_or_404(db, user_id)
    ts = _ts()

    # Validate all requested roles exist
    if body.role_codes:
        placeholders = ",".join(f":rc{i}" for i in range(len(body.role_codes)))
        params = {f"rc{i}": code for i, code in enumerate(body.role_codes)}
        found = {
            r[0] for r in db.execute(
                text(f"SELECT code FROM roles WHERE code IN ({placeholders})"), params
            ).fetchall()
        }
        for code in body.role_codes:
            if code not in found:
                raise HTTPException(status_code=400, detail=f"瑙掕壊 '{code}' 涓嶅瓨鍦?)

    # Guard: cannot remove super_admin from yourself
    is_self = user_id == current_user["id"]
    if is_self and SUPER_ADMIN_ROLE not in body.role_codes:
        raise HTTPException(status_code=400, detail="涓嶈兘鎾ら攢鑷繁鐨勮秴绾х鐞嗗憳瑙掕壊")

    # Guard: cannot remove the last active super_admin
    currently_has_super = _user_has_role(db, user_id, SUPER_ADMIN_ROLE)
    if currently_has_super and SUPER_ADMIN_ROLE not in body.role_codes:
        if _count_active_super_admins(db) <= 1:
            raise HTTPException(status_code=400, detail="涓嶈兘绉婚櫎鏈€鍚庝竴鍚嶈秴绾х鐞嗗憳")

    # Commit any implicit transaction from pre-checks above
    db.commit()

    with db.begin():
        # Remove all existing role bindings for this user
        db.execute(
            text("DELETE FROM role_bindings WHERE user_id = :uid"),
            {"uid": user_id},
        )
        # Insert new bindings (deduplicate role codes)
        for code in dict.fromkeys(body.role_codes):
            role_row = db.execute(
                text("SELECT id FROM roles WHERE code = :rc"), {"rc": code}
            ).fetchone()
            if role_row:
                db.execute(
                    text(
                        "INSERT OR IGNORE INTO role_bindings "
                        "(user_id, role_id, org_id, department_id, created_at) "
                        "VALUES (:uid, :rid, 'default', 'HQ', :ts)"
                    ),
                    {"uid": user_id, "rid": role_row[0], "ts": ts},
                )
        # Bump token_version so next refresh picks up new roles
        db.execute(
            text(
                "UPDATE users SET token_version = token_version + 1, "
                "updated_at = :ts WHERE id = :uid"
            ),
            {"uid": user_id, "ts": ts},
        )

        # Audit log (inside transaction)
        audit_log(
            db, action="admin.user.set_roles",
            user_id=current_user["id"], resource_type="user", resource_id=str(user_id),
            detail={"target_username": user["username"], "new_roles": body.role_codes},
        )

    # Notify target user of role change (T7 鈥?Phase 1 notification hook)
    role_names = ", ".join(body.role_codes) if body.role_codes else "鏃犺鑹?
    try:
        store.create_notification(
            user_id=user_id,
            title="瑙掕壊宸叉洿鏂?,
            content=f"绠＄悊鍛樺凡灏嗕綘鐨勮鑹叉洿鏂颁负锛歿role_names}",
            type_="system",
            reference_type="user",
            reference_id=str(user_id),
        )
    except Exception:
        logger.warning("Failed to send role-change notification to user %s", user_id, exc_info=True)

    row = db.execute(text(_USER_BY_ID_SQL), {"uid": user_id}).fetchone()
    return _build_user_item(row)


@router.post("/users/{user_id}/reset-password", response_model=AdminResetPasswordResponse)
def reset_user_password(
    user_id: int,
    body: AdminResetPasswordRequest,
    response: Response,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminResetPasswordResponse:
    """Reset a user's password and return the new plaintext password once.

    The returned password is shown exactly once in the HTTP response body and is
    never stored in plaintext, logged, or persisted.
    """
    user = _load_user_or_404(db, user_id)
    ts = _ts()

    # Guard: cannot reset own password via admin panel
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="涓嶈兘閲嶇疆褰撳墠鐧诲綍璐﹀彿鐨勫瘑鐮侊紝璇蜂娇鐢ㄤ慨鏀瑰瘑鐮佸姛鑳?)

    # Determine the new password
    new_password: str = body.password or secrets.token_urlsafe(12)
    new_hash = hash_password(new_password)

    # Commit any implicit transaction from pre-checks
    db.commit()

    with db.begin():
        db.execute(
            text(
                "UPDATE users SET password_hash = :pw, token_version = token_version + 1, "
                "must_change_password = 1, updated_at = :ts WHERE id = :uid"
            ),
            {"pw": new_hash, "ts": ts, "uid": user_id},
        )
        revoke_all_user_sessions(db, user_id)

        audit_log(
            db, action="admin.user.reset_password",
            user_id=current_user["id"], resource_type="user", resource_id=str(user_id),
            detail={
                "target_username": user["username"],
                "generated": body.password is None,
            },
        )

    # Prevent browser/proxy caching of the plaintext password
    response.headers["Cache-Control"] = "no-store"

    return AdminResetPasswordResponse(
        user_id=user_id,
        username=user["username"],
        display_name=user["display_name"],
        password=new_password,
        must_change_password=True,
    )


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# Phase 6: Audit log viewing
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?


@router.get("/audit", response_model=AuditLogListResponse)
def list_audit_logs(
    page: int = 1,
    page_size: int = 20,
    action: str | None = None,
    decision: str | None = None,
    user_id: int | None = None,
    since: str | None = None,
    until: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_permission("audit:view")),
) -> dict[str, Any]:
    """List audit logs (requires audit:view permission).

    Filters:
    - **action**: partial match on action (e.g. "auth.login")
    - **decision**: "allow" | "deny" | "error"
    - **user_id**: filter by specific user
    - **since**: ISO-8601 start time (inclusive)
    - **until**: ISO-8601 end time (inclusive)
    - **page**: 1-based page number
    - **page_size**: items per page (max 100)
    """
    page_size = max(1, min(page_size, 100))
    page = max(1, page)

    conditions: list[str] = []
    params: dict[str, Any] = {}

    # 鈹€鈹€ Org-scoping: super_admin sees all; org_admin sees own org 鈹€鈹€
    _apply_org_scope(conditions, params, current_user)

    if action and action.strip():
        conditions.append("action LIKE :action")
        params["action"] = f"%{action.strip()}%"
    if decision and decision.strip():
        conditions.append("decision = :decision")
        params["decision"] = decision.strip()
    if user_id is not None:
        conditions.append("user_id = :filter_uid")
        params["filter_uid"] = user_id
    if since and since.strip():
        conditions.append("created_at >= :since")
        params["since"] = since.strip()
    if until and until.strip():
        conditions.append("created_at <= :until")
        params["until"] = until.strip()

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total = db.execute(
        text(f"SELECT COUNT(*) FROM audit_logs{where}"), params
    ).fetchone()[0]

    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            f"SELECT id, request_id, user_id, org_id, department_id, action, "
            f"resource_type, resource_id, decision, reason, ip_address, "
            f"user_agent, detail_json, created_at "
            f"FROM audit_logs{where} "
            f"ORDER BY id DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": offset},
    ).fetchall()

    items = [
        {
            "id": r[0], "request_id": r[1], "user_id": r[2], "org_id": r[3],
            "department_id": r[4], "action": r[5], "resource_type": r[6],
            "resource_id": r[7], "decision": r[8], "reason": r[9],
            "ip_address": r[10], "user_agent": r[11], "detail_json": r[12],
            "created_at": r[13],
        }
        for r in rows
    ]
    return {"items": items, "total": total}


@router.get("/audit/ai-queries", response_model=AIQueryLogListResponse)
def list_ai_query_logs(
    page: int = 1,
    page_size: int = 20,
    decision: str | None = None,
    risk_label: str | None = None,
    user_id: int | None = None,
    since: str | None = None,
    until: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_permission("audit:view")),
) -> dict[str, Any]:
    """List AI query logs (requires audit:view permission).

    These records contain only SHA-256 hashes and truncated snippets 鈥?
    full query text and full AI responses are never stored.
    """
    page_size = max(1, min(page_size, 100))
    page = max(1, page)

    conditions: list[str] = []
    params: dict[str, Any] = {}

    _apply_org_scope(conditions, params, current_user)

    if decision and decision.strip():
        conditions.append("decision = :decision")
        params["decision"] = decision.strip()
    if risk_label and risk_label.strip():
        conditions.append("risk_label = :risk_label")
        params["risk_label"] = risk_label.strip()
    if user_id is not None:
        conditions.append("user_id = :filter_uid")
        params["filter_uid"] = user_id
    if since and since.strip():
        conditions.append("created_at >= :since")
        params["since"] = since.strip()
    if until and until.strip():
        conditions.append("created_at <= :until")
        params["until"] = until.strip()

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total = db.execute(
        text(f"SELECT COUNT(*) FROM ai_query_logs{where}"), params
    ).fetchone()[0]

    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            f"SELECT id, request_id, user_id, org_id, department_id, query_hash, "
            f"query_snippet, risk_label, policy_version, decision, blocked_reason, "
            f"accessible_resource_count, response_time_ms, created_at "
            f"FROM ai_query_logs{where} "
            f"ORDER BY id DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": offset},
    ).fetchall()

    items = [
        {
            "id": r[0], "request_id": r[1], "user_id": r[2], "org_id": r[3],
            "department_id": r[4], "query_hash": r[5], "query_snippet": r[6],
            "risk_label": r[7], "policy_version": r[8], "decision": r[9],
            "blocked_reason": r[10], "accessible_resource_count": r[11],
            "response_time_ms": r[12], "created_at": r[13],
        }
        for r in rows
    ]
    return {"items": items, "total": total}


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# Phase 6: Session management
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?


@router.get("/sessions", response_model=AdminSessionListResponse)
def list_sessions(
    page: int = 1,
    page_size: int = 20,
    user_id: int | None = None,
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_permission("audit:view")),
) -> dict[str, Any]:
    """List auth sessions (requires audit:view permission).

    - **user_id**: filter by user
    - **active_only**: when True, only show non-revoked, non-expired sessions
    """
    page_size = max(1, min(page_size, 100))
    page = max(1, page)

    conditions: list[str] = []
    params: dict[str, Any] = {}

    # 鈹€鈹€ Org-scoping: non-super_admin only sees sessions of users in their org 鈹€鈹€
    if SUPER_ADMIN_ROLE not in current_user.get("roles", []):
        admin_org = current_user.get("default_org_id")
        if admin_org:
            conditions.append(
                "s.user_id IN (SELECT user_id FROM user_org_memberships WHERE org_id = :scope_org_id)"
            )
            params["scope_org_id"] = admin_org

    if user_id is not None:
        conditions.append("s.user_id = :filter_uid")
        params["filter_uid"] = user_id
    if active_only:
        conditions.append(
            "s.revoked_at IS NULL AND s.expires_at > :now"
        )
        params["now"] = _ts()

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    total = db.execute(
        text(f"SELECT COUNT(*) FROM auth_sessions s{where}"), params
    ).fetchone()[0]

    offset = (page - 1) * page_size
    rows = db.execute(
        text(
            f"SELECT s.id, s.user_id, u.username, u.display_name, s.user_agent, "
            f"s.ip_address, s.expires_at, s.revoked_at, s.created_at "
            f"FROM auth_sessions s "
            f"LEFT JOIN users u ON u.id = s.user_id "
            f"{where} "
            f"ORDER BY s.created_at DESC LIMIT :limit OFFSET :offset"
        ),
        {**params, "limit": page_size, "offset": offset},
    ).fetchall()

    now = _ts()
    items = [
        {
            "id": r[0], "user_id": r[1], "username": r[2], "display_name": r[3],
            "user_agent": r[4], "ip_address": r[5], "expires_at": r[6],
            "revoked_at": r[7], "created_at": r[8],
            "is_active": r[7] is None and (r[6] is not None and r[6] > now),
        }
        for r in rows
    ]
    return {"items": items, "total": total}


@router.delete("/sessions/{session_id}")
def revoke_session_endpoint(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_permission("audit:view")),
) -> dict[str, bool]:
    """Revoke a specific session by ID (requires audit:view permission).

    Non-super_admin callers can only revoke sessions of users in their own org.
    """
    now_ts = _ts()

    # 鈹€鈹€ Org-scoping check 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    if SUPER_ADMIN_ROLE not in current_user.get("roles", []):
        admin_org = current_user.get("default_org_id")
        if admin_org:
            session_org = db.execute(
                text(
                    "SELECT uom.org_id FROM auth_sessions s "
                    "JOIN user_org_memberships uom ON uom.user_id = s.user_id "
                    "WHERE s.id = :sid AND uom.org_id = :oid LIMIT 1"
                ),
                {"sid": session_id, "oid": admin_org},
            ).fetchone()
            if session_org is None:
                raise HTTPException(
                    status_code=404, detail="浼氳瘽涓嶅瓨鍦ㄦ垨宸叉挙閿€"
                )

    result = db.execute(
        text(
            "UPDATE auth_sessions SET revoked_at = :now, updated_at = :now "
            "WHERE id = :sid AND revoked_at IS NULL"
        ),
        {"now": now_ts, "sid": session_id},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="浼氳瘽涓嶅瓨鍦ㄦ垨宸叉挙閿€")

    audit_log(
        db, action="admin.session.revoke",
        user_id=current_user["id"], resource_type="auth_session",
        resource_id=session_id,
        detail={"session_id": session_id},
    )
    db.commit()  # Single commit: audit record + session revocation are atomic
    return {"ok": True}


@router.delete("/users/{user_id}/sessions")
def revoke_user_sessions(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_permission("audit:view")),
) -> dict[str, Any]:
    """Revoke all active sessions for a user (requires audit:view permission).

    Non-super_admin callers are restricted to users within their own org.
    """
    user = _load_user_or_404(db, user_id)
    now_ts = _ts()

    # 鈹€鈹€ Org-scoping: non-super_admin can only revoke sessions for users
    #    in their own org 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    if SUPER_ADMIN_ROLE not in current_user.get("roles", []):
        admin_org = current_user.get("default_org_id")
        if admin_org:
            membership = db.execute(
                text(
                    "SELECT 1 FROM user_org_memberships "
                    "WHERE user_id = :uid AND org_id = :oid LIMIT 1"
                ),
                {"uid": user_id, "oid": admin_org},
            ).fetchone()
            if membership is None:
                raise HTTPException(
                    status_code=403,
                    detail="鏃犳潈鎿嶄綔鍏朵粬缁勭粐鐨勭敤鎴蜂細璇?,
                )

    result = db.execute(
        text(
            "UPDATE auth_sessions SET revoked_at = :now, updated_at = :now "
            "WHERE user_id = :uid AND revoked_at IS NULL"
        ),
        {"now": now_ts, "uid": user_id},
    )
    # Also bump token_version so access tokens become invalid
    db.execute(
        text(
            "UPDATE users SET token_version = token_version + 1, "
            "updated_at = :now WHERE id = :uid"
        ),
        {"now": now_ts, "uid": user_id},
    )

    audit_log(
        db, action="admin.session.revoke_all",
        user_id=current_user["id"], resource_type="user",
        resource_id=str(user_id),
        detail={"target_username": user["username"], "revoked_count": result.rowcount},
    )
    db.commit()  # Single commit: session revocations + token bump + audit are atomic
    return {"ok": True, "revoked_count": result.rowcount}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """Delete a user permanently.

    Safety guards:
    - Cannot delete yourself
    - Cannot delete the last active super_admin
    """
    user = _load_user_or_404(db, user_id)

    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="涓嶈兘鍒犻櫎鑷繁鐨勮处鍙?)

    if _user_has_role(db, user_id, SUPER_ADMIN_ROLE):
        active_super_count = _count_active_super_admins(db)
        if active_super_count <= 1:
            raise HTTPException(status_code=400, detail="涓嶈兘鍒犻櫎鍞竴鐨勮秴绾х鐞嗗憳")

    ts = _ts()

    db.commit()
    with db.begin():
        # Revoke sessions
        db.execute(
            text("UPDATE auth_sessions SET revoked_at = :ts, updated_at = :ts "
                 "WHERE user_id = :uid AND revoked_at IS NULL"),
            {"ts": ts, "uid": user_id},
        )
        # Clear AI query logs FK
        db.execute(
            text("DELETE FROM ai_query_logs WHERE user_id = :uid"),
            {"uid": user_id},
        )
        # Nullify owner references on portal assets owned by this user
        for table in ("portal_notices", "portal_documents", "portal_resources",
                       "portal_news"):
            db.execute(
                text(f"UPDATE {table} SET owner_id = NULL WHERE owner_id = :uid"),
                {"uid": user_id},
            )
        # Unassign owned enterprise records
        for table in ("enterprise_repair_tickets", "enterprise_asset_items",
                       "enterprise_oa_flows", "hr_requests", "finance_claims"):
            db.execute(
                text(f"UPDATE {table} SET owner_id = NULL WHERE owner_id = :uid"),
                {"uid": user_id},
            )
        # Delete user-owned portal_tasks and calendar_events (private data)
        db.execute(text("DELETE FROM portal_tasks WHERE owner_id = :uid"), {"uid": user_id})
        db.execute(text("DELETE FROM portal_calendar_events WHERE owner_id = :uid"), {"uid": user_id})
        # Clean up memberships and roles
        db.execute(text("DELETE FROM user_org_memberships WHERE user_id = :uid"), {"uid": user_id})
        db.execute(text("DELETE FROM user_department_memberships WHERE user_id = :uid"), {"uid": user_id})
        db.execute(text("DELETE FROM role_bindings WHERE user_id = :uid"), {"uid": user_id})
        # Delete the user
        db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})
        audit_log(
            db, action="admin.user.delete",
            user_id=current_user["id"], resource_type="user",
            resource_id=str(user_id),
            detail={"username": user["username"], "display_name": user["display_name"]},
        )

    return {"ok": True}


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# Phase 6: Anomaly statistics
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?


@router.get("/anomalies", response_model=AnomalyStats)
def get_anomaly_stats(
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_permission("audit:view")),
) -> dict[str, Any]:
    """Return anomaly / security statistics for the admin dashboard.

    Metrics are scoped to the admin's org (super_admin sees everything).
    """
    _24h_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    _now = datetime.now(timezone.utc).isoformat()

    # 鈹€鈹€ User counts 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    user_condition, user_params = _user_org_condition(current_user)
    _user_where = f" WHERE {user_condition}" if user_condition.strip() else ""

    total_users = db.execute(
        text(f"SELECT COUNT(*) FROM users{_user_where}"), user_params
    ).fetchone()[0]

    active_users = db.execute(
        text(f"SELECT COUNT(*) FROM users WHERE is_active = 1{_prefix_and(user_condition)}"),
        user_params,
    ).fetchone()[0]

    disabled_users = db.execute(
        text(f"SELECT COUNT(*) FROM users WHERE is_active = 0{_prefix_and(user_condition)}"),
        user_params,
    ).fetchone()[0]

    # 鈹€鈹€ Session counts 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    total_sessions = db.execute(
        text("SELECT COUNT(*) FROM auth_sessions")
    ).fetchone()[0]

    active_sessions = db.execute(
        text(
            "SELECT COUNT(*) FROM auth_sessions "
            "WHERE revoked_at IS NULL AND expires_at > :now"
        ),
        {"now": _now},
    ).fetchone()[0]

    # 鈹€鈹€ Recent failed logins (24h) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    audit_condition, audit_params = _org_count_condition(current_user)
    recent_failed = db.execute(
        text(
            f"SELECT COUNT(*) FROM audit_logs "
            f"WHERE action LIKE 'auth.login.failed%' AND created_at >= :since"
            f"{_prefix_and(audit_condition)}"
        ),
        {"since": _24h_ago, **audit_params},
    ).fetchone()[0]

    # 鈹€鈹€ Recent 403 responses (24h) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    recent_403 = db.execute(
        text(
            f"SELECT COUNT(*) FROM audit_logs "
            f"WHERE action LIKE 'auth.403.%' AND created_at >= :since"
            f"{_prefix_and(audit_condition)}"
        ),
        {"since": _24h_ago, **audit_params},
    ).fetchone()[0]

    # 鈹€鈹€ Recent AI blocks (24h) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    recent_ai_blocks = db.execute(
        text(
            f"SELECT COUNT(*) FROM ai_query_logs "
            f"WHERE decision = 'blocked' AND created_at >= :since"
            f"{_prefix_and(audit_condition)}"
        ),
        {"since": _24h_ago, **audit_params},
    ).fetchone()[0]

    # 鈹€鈹€ Recent injection blocks (24h) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    recent_injections = db.execute(
        text(
            f"SELECT COUNT(*) FROM ai_query_logs "
            f"WHERE risk_label = 'PROMPT_INJECTION' AND created_at >= :since"
            f"{_prefix_and(audit_condition)}"
        ),
        {"since": _24h_ago, **audit_params},
    ).fetchone()[0]

    return {
        "total_users": total_users,
        "active_users": active_users,
        "disabled_users": disabled_users,
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "recent_failed_logins_24h": recent_failed,
        "recent_403_24h": recent_403,
        "recent_ai_blocks_24h": recent_ai_blocks,
        "recent_injections_24h": recent_injections,
    }


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# Phase 6: Org-scoping helpers
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?


def _apply_org_scope(
    conditions: list[str],
    params: dict[str, Any],
    current_user: dict[str, Any],
) -> None:
    """Add org-scoping WHERE clause for super_admin bypass.

    super_admin sees all orgs; org_admin sees only their own org plus
    records where org_id IS NULL (e.g. failed-login events that occur
    before a user context is established).
    """
    if SUPER_ADMIN_ROLE in current_user.get("roles", []):
        return  # No restriction
    org_id = current_user.get("default_org_id")
    if org_id:
        conditions.append("(org_id = :scope_org_id OR org_id IS NULL)")
        params["scope_org_id"] = org_id


def _org_count_condition(current_user: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Return (sql_fragment, params) for org-scoping tables that have ``org_id``.

    The returned fragment is a bare SQL expression (no leading ``WHERE`` /
    ``AND``) so it can be composed with existing ``WHERE`` clauses via
    ``_prefix_and``.

    Returns empty string + empty dict for super_admin (no restriction).
    For non-super_admin, includes records where org_id IS NULL (e.g.
    failed-login events that occur before a user context is established)
    to stay consistent with ``_apply_org_scope``.

    Use ``_user_org_condition`` for counting users (the ``users`` table does
    not carry ``org_id`` directly 鈥?it is modelled via
    ``user_org_memberships``).
    """
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
    """Return (sql_fragment, params) for org-scoping the ``users`` table.

    The ``users`` table does not carry ``org_id`` directly, so we filter via
    ``user_org_memberships``.  The returned fragment is a bare SQL expression
    (no leading ``WHERE`` / ``AND``) so it can be composed with existing
    ``WHERE`` clauses via ``_prefix_and``.

    Returns empty string + empty dict for super_admin (no restriction).
    """
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


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# T5: Organization management
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?


@router.get("/orgs", response_model=AdminOrgListResponse)
def list_orgs(
    db: Session = Depends(get_db),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """List all organizations (super_admin only)."""
    rows = db.execute(
        text("SELECT id, name, is_active, created_at, updated_at FROM orgs ORDER BY id")
    ).fetchall()
    items = [
        AdminOrgItem(
            id=r[0], name=r[1], is_active=bool(int(r[2])),
            created_at=r[3], updated_at=r[4],
        )
        for r in rows
    ]
    return {"items": items, "total": len(items)}


@router.post("/orgs", status_code=201, response_model=AdminOrgItem)
def create_org(
    body: AdminOrgCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminOrgItem:
    """Create a new organization."""
    ts = _ts()

    # Uniqueness check
    existing = db.execute(
        text("SELECT id FROM orgs WHERE id = :oid"), {"oid": body.id}
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="缁勭粐ID宸茶鍗犵敤")

    db.commit()
    with db.begin():
        db.execute(
            text(
                "INSERT INTO orgs (id, name, is_active, created_at, updated_at) "
                "VALUES (:id, :name, 1, :ts, :ts)"
            ),
            {"id": body.id, "name": body.name, "ts": ts},
        )
        audit_log(
            db, action="admin.org.create",
            user_id=current_user["id"], resource_type="org",
            resource_id=body.id,
            detail={"name": body.name},
        )

    return AdminOrgItem(id=body.id, name=body.name, is_active=True,
                        created_at=ts, updated_at=ts)


@router.put("/orgs/{org_id}", response_model=AdminOrgItem)
def update_org(
    org_id: str,
    body: AdminOrgUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminOrgItem:
    """Update an organization's name or active status."""
    row = db.execute(
        text("SELECT id, name, is_active, created_at, updated_at FROM orgs WHERE id = :oid"),
        {"oid": org_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="缁勭粐涓嶅瓨鍦?)

    ts = _ts()
    updates: list[str] = []
    params: dict[str, Any] = {"oid": org_id, "ts": ts}
    if body.name is not None:
        updates.append("name = :name")
        params["name"] = body.name
    if body.is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = 1 if body.is_active else 0

    if updates:
        updates.append("updated_at = :ts")
        db.commit()
        with db.begin():
            db.execute(
                text(f"UPDATE orgs SET {', '.join(updates)} WHERE id = :oid"),
                params,
            )
            audit_log(
                db, action="admin.org.update",
                user_id=current_user["id"], resource_type="org",
                resource_id=org_id,
                detail={
                    "before": {"name": row[1], "is_active": bool(int(row[2]))},
                    "after": {
                        "name": body.name if body.name is not None else row[1],
                        "is_active": body.is_active if body.is_active is not None else bool(int(row[2])),
                    },
                },
            )

    # Re-query
    row2 = db.execute(
        text("SELECT id, name, is_active, created_at, updated_at FROM orgs WHERE id = :oid"),
        {"oid": org_id},
    ).fetchone()
    return AdminOrgItem(
        id=row2[0], name=row2[1], is_active=bool(int(row2[2])),
        created_at=row2[3], updated_at=row2[4],
    )


@router.delete("/orgs/{org_id}")
def delete_org(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> dict[str, bool]:
    """Soft-delete an organization (set is_active=0). Refuse to delete 'default' org."""
    if org_id == "default":
        raise HTTPException(status_code=400, detail="涓嶈兘娉ㄩ攢榛樿缁勭粐")

    row = db.execute(
        text("SELECT id FROM orgs WHERE id = :oid"), {"oid": org_id}
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="缁勭粐涓嶅瓨鍦?)

    ts = _ts()
    db.commit()
    with db.begin():
        db.execute(
            text("UPDATE orgs SET is_active = 0, updated_at = :ts WHERE id = :oid"),
            {"oid": org_id, "ts": ts},
        )
        audit_log(
            db, action="admin.org.delete",
            user_id=current_user["id"], resource_type="org",
            resource_id=org_id,
            detail={"soft_delete": True},
        )
    return {"ok": True}


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# T5: Department management
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?


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

    # Sort by sort_order within each level
    def sort_children(item: AdminDeptItem) -> None:
        item.children.sort(key=lambda d: (d.sort_order, d.id))
        for child in item.children:
            sort_children(child)

    for root in roots:
        sort_children(root)
    roots.sort(key=lambda d: (d.sort_order, d.id))
    return roots


@router.get("/departments", response_model=AdminDeptListResponse)
def list_departments(
    org_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """List departments, optionally filtered by org_id."""
    if org_id:
        rows = db.execute(
            text(
                "SELECT id, org_id, name, parent_id, path, level, sort_order, "
                "is_active, created_at, updated_at "
                "FROM departments WHERE org_id = :oid ORDER BY sort_order, id"
            ),
            {"oid": org_id},
        ).fetchall()
    else:
        rows = db.execute(
            text(
                "SELECT id, org_id, name, parent_id, path, level, sort_order, "
                "is_active, created_at, updated_at "
                "FROM departments ORDER BY org_id, sort_order, id"
            )
        ).fetchall()
    items = _build_dept_tree(rows)
    return {"items": items, "total": len(rows)}


@router.post("/departments", status_code=201, response_model=AdminDeptItem)
def create_department(
    body: AdminDeptCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDeptItem:
    """Create a new department. Auto-computes path and level from parent."""
    ts = _ts()

    # Validate org exists
    org_row = db.execute(
        text("SELECT id FROM orgs WHERE id = :oid AND is_active = 1"),
        {"oid": body.org_id},
    ).fetchone()
    if org_row is None:
        raise HTTPException(status_code=400, detail="缁勭粐涓嶅瓨鍦ㄦ垨宸插仠鐢?)

    # Uniqueness check
    existing = db.execute(
        text("SELECT id FROM departments WHERE id = :did"), {"did": body.id}
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="閮ㄩ棬ID宸茶鍗犵敤")

    # Compute path and level from parent
    path = body.id
    level = 0
    if body.parent_id:
        parent = db.execute(
            text(
                "SELECT id, path, level FROM departments "
                "WHERE id = :pid AND org_id = :oid"
            ),
            {"pid": body.parent_id, "oid": body.org_id},
        ).fetchone()
        if parent is None:
            raise HTTPException(status_code=400, detail="鐖堕儴闂ㄤ笉瀛樺湪")
        path = parent[1] + "/" + body.id if parent[1] else body.id
        level = (parent[2] or 0) + 1

    db.commit()
    with db.begin():
        db.execute(
            text(
                "INSERT INTO departments (id, org_id, name, parent_id, path, level, "
                "sort_order, is_active, created_at, updated_at) "
                "VALUES (:id, :org_id, :name, :parent_id, :path, :level, "
                ":sort_order, 1, :ts, :ts)"
            ),
            {
                "id": body.id, "org_id": body.org_id, "name": body.name,
                "parent_id": body.parent_id, "path": path, "level": level,
                "sort_order": 0, "ts": ts,
            },
        )
        audit_log(
            db, action="admin.department.create",
            user_id=current_user["id"], resource_type="department",
            resource_id=body.id,
            detail={"org_id": body.org_id, "name": body.name, "parent_id": body.parent_id},
        )

    return AdminDeptItem(
        id=body.id, org_id=body.org_id, name=body.name, parent_id=body.parent_id,
        path=path, level=level, sort_order=0, is_active=True,
        created_at=ts, updated_at=ts,
    )


@router.put("/departments/reorder")
def reorder_departments(
    body: AdminDeptReorderRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> dict[str, bool]:
    """Batch-update department sort_order values."""
    ts = _ts()
    db.commit()
    with db.begin():
        for item in body.items:
            db.execute(
                text(
                    "UPDATE departments SET sort_order = :so, updated_at = :ts "
                    "WHERE id = :did"
                ),
                {"so": item.sort_order, "ts": ts, "did": item.id},
            )
        audit_log(
            db, action="admin.department.reorder",
            user_id=current_user["id"], resource_type="department",
            resource_id="batch",
            detail={"count": len(body.items)},
        )
    return {"ok": True}


@router.put("/departments/{dept_id}", response_model=AdminDeptItem)
def update_department(
    dept_id: str,
    body: AdminDeptUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDeptItem:
    """Update a department's name, parent, or active status."""
    row = db.execute(
        text(
            "SELECT id, org_id, name, parent_id, path, level, sort_order, "
            "is_active, created_at, updated_at FROM departments WHERE id = :did"
        ),
        {"did": dept_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="閮ㄩ棬涓嶅瓨鍦?)

    ts = _ts()
    new_name = body.name if body.name is not None else row[2]
    new_parent_id = body.parent_id if body.parent_id is not None else row[3]
    new_is_active = body.is_active if body.is_active is not None else bool(int(row[7]))

    # Recompute path and level if parent changed
    new_path = row[4] or ""
    new_level = int(row[5]) if row[5] is not None else 0
    if body.parent_id is not None and body.parent_id != row[3]:
        if body.parent_id:
            parent = db.execute(
                text(
                    "SELECT id, path, level FROM departments "
                    "WHERE id = :pid AND org_id = :oid"
                ),
                {"pid": body.parent_id, "oid": row[1]},
            ).fetchone()
            if parent is None:
                raise HTTPException(status_code=400, detail="鐖堕儴闂ㄤ笉瀛樺湪")
            new_path = (parent[1] + "/" + dept_id) if parent[1] else dept_id
            new_level = (parent[2] or 0) + 1
        else:
            new_path = dept_id
            new_level = 0

    updates: list[str] = []
    params: dict[str, Any] = {"did": dept_id, "ts": ts}
    if body.name is not None:
        updates.append("name = :name")
        params["name"] = body.name
    if body.parent_id is not None:
        updates.append("parent_id = :parent_id")
        params["parent_id"] = body.parent_id
        updates.append("path = :path")
        params["path"] = new_path
        updates.append("level = :level")
        params["level"] = new_level
    if body.is_active is not None:
        updates.append("is_active = :is_active")
        params["is_active"] = 1 if body.is_active else 0

    if updates:
        updates.append("updated_at = :ts")
        db.commit()
        with db.begin():
            db.execute(
                text(f"UPDATE departments SET {', '.join(updates)} WHERE id = :did"),
                params,
            )
            audit_log(
                db, action="admin.department.update",
                user_id=current_user["id"], resource_type="department",
                resource_id=dept_id,
                detail={
                    "before": {"name": row[2], "parent_id": row[3]},
                    "after": {"name": new_name, "parent_id": new_parent_id},
                },
            )

    return AdminDeptItem(
        id=dept_id, org_id=row[1], name=new_name, parent_id=new_parent_id,
        path=new_path, level=new_level,
        sort_order=int(row[6]) if row[6] is not None else 0,
        is_active=new_is_active, created_at=row[8], updated_at=ts,
    )


@router.delete("/departments/{dept_id}")
def delete_department(
    dept_id: str,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> dict[str, bool]:
    """Soft-delete a department (set is_active=0)."""
    row = db.execute(
        text("SELECT id FROM departments WHERE id = :did"), {"did": dept_id}
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="閮ㄩ棬涓嶅瓨鍦?)

    ts = _ts()
    db.commit()
    with db.begin():
        db.execute(
            text("UPDATE departments SET is_active = 0, updated_at = :ts WHERE id = :did"),
            {"did": dept_id, "ts": ts},
        )
        audit_log(
            db, action="admin.department.delete",
            user_id=current_user["id"], resource_type="department",
            resource_id=dept_id,
            detail={"soft_delete": True},
        )
    return {"ok": True}


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# T5: Notice management
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?


def _build_notice_item(row: Any) -> AdminNoticeItem:
    """Build an AdminNoticeItem from a portal_notices row (mapping or tuple)."""
    from collections.abc import Mapping as _Mapping

    # SQLAlchemy RowMapping, plain dict, or Row._mapping 鈫?named access
    if isinstance(row, _Mapping):
        return AdminNoticeItem(
            id=row["id"], title=row["title"], source=row["source"], category=row["category"],
            body=row["body"], pinned=bool(int(row["pinned"])) if row["pinned"] is not None else False,
            published_at=row["published_at"], read_count=int(row["read_count"]) if row["read_count"] is not None else 0,
            status=row.get("status"), org_id=row.get("org_id"), department_id=row.get("department_id"),
            visibility=row.get("visibility", "org"),
            created_at=row.get("created_at"), updated_at=row.get("updated_at"),
        )
    # SQLAlchemy Row 鈥?use _mapping for named access
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


@router.get("/notices", response_model=AdminNoticeListResponse)
def list_notices_admin(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_notice_manager),
) -> dict[str, Any]:
    """List notices with pagination. Non-super_admins see only own org/dept scope."""
    page_size = max(1, min(page_size, 100))
    page = max(1, page)
    offset = (page - 1) * page_size

    roles = current_user.get("roles", [])
    is_super = SUPER_ADMIN_ROLE in roles

    if is_super:
        total = db.execute(
            text("SELECT COUNT(*) FROM portal_notices")
        ).fetchone()[0]
        rows = db.execute(
            text(
                "SELECT id, title, source, category, body, pinned, published_at, "
                "read_count, status, org_id, department_id, visibility, "
                "created_at, updated_at "
                "FROM portal_notices ORDER BY pinned DESC, published_at DESC "
                "LIMIT :limit OFFSET :offset"
            ),
            {"limit": page_size, "offset": offset},
        ).mappings().all()
    else:
        org_id = current_user.get("default_org_id") or "default"
        dept_id = current_user.get("default_dept_id") or "HQ"
        total = db.execute(
            text("SELECT COUNT(*) FROM portal_notices WHERE org_id = :oid AND department_id = :did"),
            {"oid": org_id, "did": dept_id},
        ).fetchone()[0]
        rows = db.execute(
            text(
                "SELECT id, title, source, category, body, pinned, published_at, "
                "read_count, status, org_id, department_id, visibility, "
                "created_at, updated_at "
                "FROM portal_notices WHERE org_id = :oid AND department_id = :did "
                "ORDER BY pinned DESC, published_at DESC "
                "LIMIT :limit OFFSET :offset"
            ),
            {"oid": org_id, "did": dept_id, "limit": page_size, "offset": offset},
        ).mappings().all()

    items = [_build_notice_item(r) for r in rows]
    return {"items": items, "total": total}


@router.post("/notices", status_code=201, response_model=AdminNoticeItem)
def create_notice(
    body: AdminNoticeCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_notice_manager),
) -> AdminNoticeItem:
    """Create a new notice. Non-super_admins get their org/dept auto-assigned."""
    ts = _ts()
    roles = current_user.get("roles", [])
    is_super = SUPER_ADMIN_ROLE in roles

    org_id = body.org_id or current_user.get("default_org_id") or "default"
    actual_dept = current_user.get("default_dept_id") or "HQ"
    db.commit()
    with db.begin():
        result = db.execute(
            text(
                "INSERT INTO portal_notices (title, source, category, body, pinned, "
                "published_at, read_count, status, org_id, department_id, "
                "visibility, sensitivity, created_at, updated_at) "
                "VALUES (:title, :source, :category, :body, :pinned, "
                ":published_at, 0, 'active', :org_id, :dept_id, "
                ":visibility, 'normal', :ts, :ts)"
            ),
            {
                "title": body.title, "source": body.source,
                "category": body.category, "body": body.body,
                "pinned": 1 if body.pinned else 0,
                "published_at": body.published_at,
                "org_id": org_id,
                "dept_id": actual_dept,
                "visibility": body.visibility,
                "ts": ts,
            },
        )
        notice_id = result.lastrowid
        audit_log(
            db, action="admin.notice.create",
            user_id=current_user["id"], resource_type="notice",
            resource_id=str(notice_id),
            detail={"title": body.title, "category": body.category},
        )

    return AdminNoticeItem(
        id=notice_id, title=body.title, source=body.source,
        category=body.category, body=body.body,
        pinned=body.pinned, published_at=body.published_at,
        read_count=0, status="active",
        org_id=org_id, department_id=actual_dept,
        visibility=body.visibility, created_at=ts, updated_at=ts,
    )


@router.put("/notices/{notice_id}", response_model=AdminNoticeItem)
def update_notice(
    notice_id: int,
    body: AdminNoticeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_notice_manager),
) -> AdminNoticeItem:
    """Update an existing notice. Non-super_admins can only update own org/dept notices."""
    roles = current_user.get("roles", [])
    is_super = SUPER_ADMIN_ROLE in roles

    row = db.execute(
        text(
            "SELECT id, title, source, category, body, pinned, published_at, "
            "read_count, status, org_id, department_id, visibility, "
            "created_at, updated_at FROM portal_notices WHERE id = :nid"
        ),
        {"nid": notice_id},
    ).mappings().fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="鍏憡涓嶅瓨鍦?)

    # Scope guard: non-super_admins can only update their own org/dept notices
    if not is_super:
        user_org = current_user.get("default_org_id") or "default"
        user_dept = current_user.get("default_dept_id") or "HQ"
        if row.get("org_id") != user_org or row.get("department_id") != user_dept:
            raise HTTPException(status_code=404, detail="鍏憡涓嶅瓨鍦?)

    ts = _ts()
    updates: list[str] = []
    params: dict[str, Any] = {"nid": notice_id, "ts": ts}

    field_map = {
        "title": body.title, "source": body.source, "category": body.category,
        "body": body.body, "pinned": body.pinned, "published_at": body.published_at,
        "org_id": body.org_id, "visibility": body.visibility,
    }
    for field, value in field_map.items():
        if value is not None:
            if field == "pinned":
                updates.append("pinned = :pinned")
                params["pinned"] = 1 if value else 0
            else:
                updates.append(f"{field} = :{field}")
                params[field] = value

    if updates:
        updates.append("updated_at = :ts")
        db.commit()
        with db.begin():
            db.execute(
                text(f"UPDATE portal_notices SET {', '.join(updates)} WHERE id = :nid"),
                params,
            )
            audit_log(
                db, action="admin.notice.update",
                user_id=current_user["id"], resource_type="notice",
                resource_id=str(notice_id),
                detail={"before": {"title": row["title"]}, "after": {"title": body.title or row["title"]}},
            )

    # Re-query using fetchone (Row) 鈥?_build_notice_item handles both
    # Row (with _mapping) and RowMapping objects safely
    row2 = db.execute(
        text(
            "SELECT id, title, source, category, body, pinned, published_at, "
            "read_count, status, org_id, department_id, visibility, "
            "created_at, updated_at FROM portal_notices WHERE id = :nid"
        ),
        {"nid": notice_id},
    ).fetchone()
    return _build_notice_item(row2)


@router.delete("/notices/{notice_id}")
def delete_notice(
    notice_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_notice_manager),
) -> dict[str, bool]:
    """Delete a notice. Non-super_admins can only delete own org/dept notices."""
    roles = current_user.get("roles", [])
    is_super = SUPER_ADMIN_ROLE in roles

    row = db.execute(
        text("SELECT id, title, org_id, department_id FROM portal_notices WHERE id = :nid"),
        {"nid": notice_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="鍏憡涓嶅瓨鍦?)

    # Scope guard: non-super_admins can only delete their own org/dept notices
    if not is_super:
        user_org = current_user.get("default_org_id") or "default"
        user_dept = current_user.get("default_dept_id") or "HQ"
        if row[2] != user_org or row[3] != user_dept:
            raise HTTPException(status_code=404, detail="鍏憡涓嶅瓨鍦?)

    ts = _ts()
    db.commit()
    with db.begin():
        db.execute(
            text("DELETE FROM portal_notices WHERE id = :nid"),
            {"nid": notice_id},
        )
        audit_log(
            db, action="admin.notice.delete",
            user_id=current_user["id"], resource_type="notice",
            resource_id=str(notice_id),
            detail={"title": row[1]},
        )
    return {"ok": True}


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# T: News management (admin)
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?


def _build_news_item(row: Any) -> AdminNewsItem:
    """Normalize a portal_news row into AdminNewsItem."""
    try:
        m = row._mapping if hasattr(row, "_mapping") else row
        return AdminNewsItem(
            id=m["id"], title=m["title"], source=m["source"],
            category=m["category"], body=m["body"],
            pinned=bool(m.get("pinned")),
            published_at=m["published_at"],
            status=m.get("status"), org_id=m.get("org_id"),
            department_id=m.get("department_id"),
            visibility=m.get("visibility", "org"),
            created_at=m.get("created_at"), updated_at=m.get("updated_at"),
        )
    except (KeyError, TypeError):
        # Legacy tuple fallback
        return AdminNewsItem(
            id=row[0], title=row[1], source=row[2], category=row[3],
            body=row[4], pinned=bool(row[5]), published_at=row[6],
            status=row[7] if len(row) > 7 else None,
            org_id=row[8] if len(row) > 8 else None,
            department_id=row[9] if len(row) > 9 else None,
            visibility=row[10] if len(row) > 10 else "org",
            created_at=row[11] if len(row) > 11 else None,
            updated_at=row[12] if len(row) > 12 else None,
        )


@router.get("/news", response_model=AdminNewsListResponse)
def list_news_admin(
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """List all news with pagination (admin view)."""
    page_size = max(1, min(page_size, 100))
    page = max(1, page)
    offset = (page - 1) * page_size

    total = db.execute(
        text("SELECT COUNT(*) FROM portal_news")
    ).fetchone()[0]

    rows = db.execute(
        text(
            "SELECT id, title, source, category, body, pinned, published_at, "
            "status, org_id, department_id, visibility, "
            "created_at, updated_at "
            "FROM portal_news ORDER BY pinned DESC, published_at DESC "
            "LIMIT :limit OFFSET :offset"
        ),
        {"limit": page_size, "offset": offset},
    ).mappings().all()

    items = [_build_news_item(r) for r in rows]
    return {"items": items, "total": total}


@router.post("/news", status_code=201, response_model=AdminNewsItem)
def create_news(
    body: AdminNewsCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminNewsItem:
    """Create a new news article."""
    ts = _ts()
    db.commit()
    with db.begin():
        result = db.execute(
            text(
                "INSERT INTO portal_news (title, source, category, body, pinned, "
                "published_at, status, org_id, department_id, "
                "visibility, sensitivity, created_at, updated_at) "
                "VALUES (:title, :source, :category, :body, :pinned, "
                ":published_at, 'active', :org_id, :dept_id, "
                ":visibility, 'normal', :ts, :ts)"
            ),
            {
                "title": body.title, "source": body.source,
                "category": body.category, "body": body.body,
                "pinned": 1 if body.pinned else 0,
                "published_at": body.published_at,
                "org_id": "default",
                "dept_id": "HQ",
                "visibility": "org",
                "ts": ts,
            },
        )
        news_id = result.lastrowid
        audit_log(
            db, action="admin.news.create",
            user_id=current_user["id"], resource_type="news",
            resource_id=str(news_id),
            detail={"title": body.title, "category": body.category},
        )

    return AdminNewsItem(
        id=news_id, title=body.title, source=body.source,
        category=body.category, body=body.body,
        pinned=body.pinned, published_at=body.published_at,
        status="active", org_id="default", department_id="HQ",
        visibility="org", created_at=ts, updated_at=ts,
    )


@router.put("/news/{news_id}", response_model=AdminNewsItem)
def update_news(
    news_id: int,
    body: AdminNewsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminNewsItem:
    """Update an existing news article."""
    row = db.execute(
        text(
            "SELECT id, title, source, category, body, pinned, published_at, "
            "status, org_id, department_id, visibility, "
            "created_at, updated_at FROM portal_news WHERE id = :nid"
        ),
        {"nid": news_id},
    ).mappings().fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="璧勮涓嶅瓨鍦?)

    ts = _ts()
    updates: list[str] = []
    params: dict[str, Any] = {"nid": news_id, "ts": ts}

    field_map = {
        "title": body.title, "source": body.source, "category": body.category,
        "body": body.body, "pinned": body.pinned, "published_at": body.published_at,
    }
    for field, value in field_map.items():
        if value is not None:
            if field == "pinned":
                updates.append("pinned = :pinned")
                params["pinned"] = 1 if value else 0
            else:
                updates.append(f"{field} = :{field}")
                params[field] = value

    if updates:
        updates.append("updated_at = :ts")
        db.commit()
        with db.begin():
            db.execute(
                text(f"UPDATE portal_news SET {', '.join(updates)} WHERE id = :nid"),
                params,
            )
            audit_log(
                db, action="admin.news.update",
                user_id=current_user["id"], resource_type="news",
                resource_id=str(news_id),
                detail={"before": {"title": row["title"]},
                        "after": {"title": body.title or row["title"]}},
            )

    row2 = db.execute(
        text(
            "SELECT id, title, source, category, body, pinned, published_at, "
            "status, org_id, department_id, visibility, "
            "created_at, updated_at FROM portal_news WHERE id = :nid"
        ),
        {"nid": news_id},
    ).mappings().fetchone()
    return _build_news_item(row2)


@router.delete("/news/{news_id}")
def delete_news(
    news_id: int,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_admin),
) -> dict[str, bool]:
    """Delete a news article."""
    row = db.execute(
        text("SELECT id, title FROM portal_news WHERE id = :nid"),
        {"nid": news_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="璧勮涓嶅瓨鍦?)

    db.commit()
    with db.begin():
        db.execute(
            text("DELETE FROM portal_news WHERE id = :nid"),
            {"nid": news_id},
        )
        audit_log(
            db, action="admin.news.delete",
            user_id=current_user["id"], resource_type="news",
            resource_id=str(news_id),
            detail={"title": row[1]},
        )
    return {"ok": True}


# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?
# T5: Audit CSV export
# 鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺愨晲鈺?


@router.get("/audit/export")
def export_audit_csv(
    action: str | None = None,
    decision: str | None = None,
    user_id: int | None = None,
    since: str | None = None,
    until: str | None = None,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(require_permission("audit:view")),
) -> StreamingResponse:
    """Export audit logs as CSV (UTF-8 BOM). Same filters as GET /audit."""
    conditions: list[str] = []
    params: dict[str, Any] = {}

    _apply_org_scope(conditions, params, current_user)

    if action and action.strip():
        conditions.append("action LIKE :action")
        params["action"] = f"%{action.strip()}%"
    if decision and decision.strip():
        conditions.append("decision = :decision")
        params["decision"] = decision.strip()
    if user_id is not None:
        conditions.append("user_id = :filter_uid")
        params["filter_uid"] = user_id
    if since and since.strip():
        conditions.append("created_at >= :since")
        params["since"] = since.strip()
    if until and until.strip():
        conditions.append("created_at <= :until")
        params["until"] = until.strip()

    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    rows = db.execute(
        text(
            f"SELECT id, request_id, user_id, org_id, department_id, action, "
            f"resource_type, resource_id, decision, reason, ip_address, "
            f"user_agent, detail_json, created_at "
            f"FROM audit_logs{where} "
            f"ORDER BY id DESC LIMIT 10000"
        ),
        params,
    ).fetchall()

    output = io.StringIO()
    output.write("锘?)  # UTF-8 BOM
    writer = csv.writer(output)
    writer.writerow([
        "ID", "Request ID", "User ID", "Org ID", "Department ID",
        "Action", "Resource Type", "Resource ID", "Decision", "Reason",
        "IP Address", "User Agent", "Detail JSON", "Created At",
    ])
    for r in rows:
        writer.writerow([
            r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8],
            r[9], r[10], r[11], r[12], r[13],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=audit_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        },
    )
