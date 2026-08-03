"""FastAPI dependencies that extract and validate the current user.

``get_current_user`` is the main guard — it rejects unauthenticated requests
with 401.  ``get_optional_user`` returns ``None`` when no credentials are
provided, which is useful for endpoints that behave differently for
authenticated vs anonymous users.
"""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.tokens import decode_access_token
from authorization.rbac import user_has_permission
from session import get_db

# ── Bearer token extraction ────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


async def _extract_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """Extract the raw JWT string from the Authorization header."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


# ── User loading ───────────────────────────────────────────────────


def _load_user_with_roles(db: Session, user_id: int, token_version: int) -> dict[str, Any] | None:
    """Load a user by id and verify they are still active with a matching token_version.

    Returns a dict with identity + permission info, or None if the user is
    not found / disabled / has a stale token_version.
    """
    row = db.execute(
        text(
            "SELECT id, username, display_name, email, is_active, "
            "token_version, must_change_password, last_login_at "
            "FROM users WHERE id = :uid"
        ),
        {"uid": user_id},
    ).fetchone()

    if row is None:
        return None

    (
        uid, username, display_name, email,
        is_active, db_token_version, must_change_password, last_login_at,
    ) = row

    if int(is_active) == 0:
        return None

    if int(db_token_version) != token_version:
        return None

    # ── Load roles ──────────────────────────────────────────────
    roles_rows = db.execute(
        text(
            "SELECT DISTINCT r.code FROM roles r "
            "JOIN role_bindings rb ON rb.role_id = r.id "
            "WHERE rb.user_id = :uid"
        ),
        {"uid": uid},
    ).fetchall()
    roles = [r[0] for r in roles_rows]

    # ── Load permissions ────────────────────────────────────────
    perm_rows = db.execute(
        text(
            "SELECT DISTINCT p.code FROM permissions p "
            "JOIN role_permissions rp ON rp.permission_id = p.id "
            "JOIN role_bindings rb ON rb.role_id = rp.role_id "
            "WHERE rb.user_id = :uid"
        ),
        {"uid": uid},
    ).fetchall()
    permissions = [r[0] for r in perm_rows]

    # ── Load default org / dept ─────────────────────────────────
    org_row = db.execute(
        text(
            "SELECT org_id FROM user_org_memberships "
            "WHERE user_id = :uid AND is_default = 1 LIMIT 1"
        ),
        {"uid": uid},
    ).fetchone()
    dept_row = db.execute(
        text(
            "SELECT department_id FROM user_department_memberships "
            "WHERE user_id = :uid AND is_primary = 1 LIMIT 1"
        ),
        {"uid": uid},
    ).fetchone()

    return {
        "id": uid,
        "username": username,
        "display_name": display_name,
        "email": email,
        "default_org_id": org_row[0] if org_row else None,
        "default_dept_id": dept_row[0] if dept_row else None,
        "roles": roles,
        "permissions": permissions,
        "must_change_password": bool(must_change_password),
        "last_login_at": last_login_at,
    }


# ── Public dependencies ────────────────────────────────────────────


def get_current_user(
    request: Request,
    token: str = Depends(_extract_token),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Validate the Bearer token and return the current user.

    Synchronous so FastAPI runs this in the threadpool — the DB calls inside
    are all synchronous SQLAlchemy operations and must not block the event loop.

    Raises 401 if:
    - The token is missing, malformed, or expired
    - The user has been disabled
    - The user's ``token_version`` no longer matches the token
    """
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access Token 已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = payload.get("sub")
    token_ver = payload.get("ver")
    if user_id is None or token_ver is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        uid_int = int(user_id)
        ver_int = int(token_ver)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = _load_user_with_roles(db, uid_int, ver_int)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不可用或凭证已失效",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_optional_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> dict[str, Any] | None:
    """Like ``get_current_user`` but returns ``None`` when no token is provided.

    Useful for endpoints that serve both authenticated and anonymous users
    (e.g. public knowledge base with extra features for logged-in users).
    """
    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError:
        return None

    user_id = payload.get("sub")
    token_ver = payload.get("ver")
    if user_id is None or token_ver is None:
        return None

    try:
        uid_int = int(user_id)
        ver_int = int(token_ver)
    except (ValueError, TypeError):
        return None

    return _load_user_with_roles(db, uid_int, ver_int)


# ── Permission guard ─────────────────────────────────────────────────


def require_permission(permission_code: str):
    """FastAPI dependency factory — only admit users who hold *permission_code*.

    Usage::

        @router.get("/tasks")
        def list_tasks(
            db: Session = Depends(get_db),
            current_user: dict = Depends(require_permission("task:view")),
        ):
            ...

    Super-admins bypass all permission checks (they always have every permission).
    Returns 403 if the authenticated user lacks the required permission.
    """

    def _check(
        current_user: dict[str, Any] = Depends(get_current_user),
    ) -> dict[str, Any]:
        if not user_has_permission(current_user, permission_code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少权限: {permission_code}",
            )
        return current_user

    return _check
