"""Admin endpoints: user management + RBAC assignment (super_admin only)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from audit_logger import audit_log
from auth.dependencies import get_current_user
from auth.password import hash_password
from auth.router import _ensure_seed_data
from auth.sessions import revoke_all_user_sessions
from authorization.rbac import SUPER_ADMIN_ROLE
from schemas import (
    AdminCreateUserRequest,
    AdminRoleItem,
    AdminRoleListResponse,
    AdminSetActiveRequest,
    AdminSetRolesRequest,
    AdminUserItem,
    AdminUserListResponse,
)
from session import get_db

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
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


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_admin(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Reject non-super_admin callers with 403."""
    if SUPER_ADMIN_ROLE not in current_user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限",
        )
    return current_user


# ── Helpers ────────────────────────────────────────────────────────


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


# ── Endpoints ──────────────────────────────────────────────────────


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

    # ── Build query ────────────────────────────────────────────
    where_clause = ""
    params: dict[str, Any] = {}
    if search and search.strip():
        where_clause = " WHERE (u.username LIKE :search OR u.display_name LIKE :search)"
        params["search"] = f"%{search.strip()}%"

    # Total count (no JOINs needed — just count matching users)
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
        text("SELECT id, code, name, description FROM roles ORDER BY id")
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
            permissions=perm_map.get(r[0], []),
        )
        for r in role_rows
    ]
    return {"items": items}


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
            raise HTTPException(status_code=409, detail="用户名已被占用")
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

    # Re-query the created user (outside transaction — auto-begin new implicit tx)
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
            raise HTTPException(status_code=400, detail="不能禁用当前登录账号")
        # Cannot disable the last active super_admin
        if _user_has_role(db, user_id, SUPER_ADMIN_ROLE):
            if _count_active_super_admins(db) <= 1:
                raise HTTPException(status_code=400, detail="不能禁用最后一名超级管理员")

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

        # Audit log (inside transaction)
        audit_log(
            db, action="admin.user." + ("enable" if body.is_active else "disable"),
            user_id=current_user["id"], resource_type="user", resource_id=str(user_id),
            detail={"target_username": user["username"]},
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
                raise HTTPException(status_code=400, detail=f"角色 '{code}' 不存在")

    # Guard: cannot remove super_admin from yourself
    is_self = user_id == current_user["id"]
    if is_self and SUPER_ADMIN_ROLE not in body.role_codes:
        raise HTTPException(status_code=400, detail="不能撤销自己的超级管理员角色")

    # Guard: cannot remove the last active super_admin
    currently_has_super = _user_has_role(db, user_id, SUPER_ADMIN_ROLE)
    if currently_has_super and SUPER_ADMIN_ROLE not in body.role_codes:
        if _count_active_super_admins(db) <= 1:
            raise HTTPException(status_code=400, detail="不能移除最后一名超级管理员")

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

    row = db.execute(text(_USER_BY_ID_SQL), {"uid": user_id}).fetchone()
    return _build_user_item(row)
