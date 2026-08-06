"""Auth endpoints: login, refresh, logout, me.

Rate limiting on /login is per-username + per-IP and lives in memory
(sufficient for dev / small-scale use; swap to Redis in Phase 7).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from audit_logger import audit_log
from auth.dependencies import _load_user_with_roles, get_current_user
from auth.password import hash_password, verify_password
from auth.sessions import InvalidSessionError, create_session, revoke_all_user_sessions, revoke_session, rotate_session
from auth.tokens import create_access_token
from config import get_settings
from schemas import ChangePasswordRequest, LoginRequest, LoginResponse, RefreshResponse, RegisterRequest, UserInfo
from session import get_db

logger = logging.getLogger("replica")
router = APIRouter()

# Pre-computed dummy bcrypt hash for constant-time "user not found" /
# "account disabled" path — avoids the timing leak of calling
# hash_password() (which invokes bcrypt.gensalt) on every failed attempt.
_DUMMY_HASH = hash_password("__dummy__for_timing_defense__")

# ──────────────────────────────────────────────────────────────────
# In-memory rate limiter (thread-safe via lock; swap to Redis in Phase 7)
# ──────────────────────────────────────────────────────────────────

import threading

_login_attempts: dict[str, list[float]] = {}
_login_lock = threading.Lock()


def _check_limited(key: str) -> bool:
    """Return True if *key* has exceeded the rate limit (under lock)."""
    settings = get_settings()
    now = time.time()
    window = settings.LOGIN_WINDOW_SECONDS
    attempts = [t for t in _login_attempts.get(key, []) if now - t < window]
    if attempts:
        _login_attempts[key] = attempts
    elif key in _login_attempts:
        del _login_attempts[key]  # evict empty lists
    return len(attempts) >= settings.LOGIN_MAX_ATTEMPTS


def _check_rate_limit(key: str) -> None:
    with _login_lock:
        limited = _check_limited(key)
    if limited:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后再试",
        )


def _record_failed_attempt(key: str) -> None:
    with _login_lock:
        _login_attempts.setdefault(key, []).append(time.time())


# ──────────────────────────────────────────────────────────────────
# Cookie helpers
# ──────────────────────────────────────────────────────────────────

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = "/"


def _set_refresh_cookie(response: Response, raw_token: str, *, request: Request | None = None) -> None:
    settings = get_settings()
    # Production: SameSite=Lax prevents CSRF-based cookie attachment while still
    # allowing top-level navigations (e.g. after OAuth redirects).
    # Development: SameSite=None allows cross-origin requests on localhost where
    # the frontend (e.g. :5173) and backend (:8000) are on different origins.
    use_samesite: str = "lax" if settings.is_production else "none"
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=raw_token,
        httponly=True,
        secure=True,
        samesite=use_samesite,
        path=REFRESH_COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


def _clear_refresh_cookie(response: Response, *, request: Request | None = None) -> None:
    settings = get_settings()
    use_samesite: str = "lax" if settings.is_production else "none"
    response.set_cookie(
        key=REFRESH_COOKIE,
        value="",
        httponly=True,
        secure=True,
        samesite=use_samesite,
        path=REFRESH_COOKIE_PATH,
        max_age=0,
    )


# ──────────────────────────────────────────────────────────────────
# User-info builder (shared by login & me)
# ──────────────────────────────────────────────────────────────────


def _build_user_info(user: dict[str, Any]) -> UserInfo:
    return UserInfo.model_validate(user)


# ──────────────────────────────────────────────────────────────────
# Seed data helper (ensures org/dept/roles exist for registration)
# ──────────────────────────────────────────────────────────────────


def _ensure_seed_data(db: Session) -> None:
    """Idempotent: create default org, dept, roles, and permissions.

    Uses a dedicated connection via ``db.connection()`` so seed operations
    bypass ORM transaction management.  After running, the implicit
    transaction that ``db.connection()`` may have begun is committed so the
    session is left in a clean state for subsequent operations.
    """
    from authorization.permissions import (
        seed_org_and_dept,
        seed_permissions,
        seed_role_bindings,
        seed_role_permissions,
        seed_roles,
        seed_users,
    )

    conn = db.connection()
    seed_org_and_dept(conn)
    seed_roles(conn)
    seed_permissions(conn)
    seed_role_permissions(conn)
    seed_users(conn)
    seed_role_bindings(conn)
    # Commit any implicit transaction the raw connection usage may have
    # begun, so the session is clean for the caller.
    db.commit()


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────


@router.post("/login", response_model=LoginResponse)
def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Authenticate with username + password.

    Rate-limited per username and per client IP.  On success sets an
    HttpOnly ``refresh_token`` cookie and returns a short-lived access token.
    """
    settings = get_settings()

    # ── Rate limiting ───────────────────────────────────────────
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(body.username)
    _check_rate_limit(client_ip)

    # ── Look up user ────────────────────────────────────────────
    row = db.execute(
        text(
            "SELECT id, username, password_hash, display_name, email, "
            "is_active, token_version, must_change_password "
            "FROM users WHERE username = :un"
        ),
        {"un": body.username},
    ).fetchone()

    # ── Constant-time behaviour ─────────────────────────────────
    # If the user doesn't exist we still do a bcrypt verify against a
    # pre-computed dummy hash so an attacker can't tell "no such user"
    # from "wrong password" by measuring response time.
    # For disabled users we also do a dummy verify BEFORE returning the
    # generic error, to prevent timing-based probing of whether a
    # disabled account's guessed password is correct.
    if row is None:
        verify_password(body.password, _DUMMY_HASH)
        _record_failed_attempt(body.username)
        _record_failed_attempt(client_ip)
        audit_log(
            db, action="auth.login.failed", reason="user_not_found",
            resource_type="user", resource_id=body.username,
            decision="deny", ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
        request.state._audit_recorded = True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    (
        uid, username, password_hash, display_name, email,
        is_active, token_version, must_change_password,
    ) = row

    # ── Account status check (before password, avoids timing oracle) ──
    if int(is_active) == 0:
        verify_password(body.password, _DUMMY_HASH)
        _record_failed_attempt(body.username)
        _record_failed_attempt(client_ip)
        audit_log(
            db, action="auth.login.failed", reason="account_disabled",
            user_id=uid, resource_type="user", resource_id=body.username,
            decision="deny", ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
        request.state._audit_recorded = True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # ── Password check ──────────────────────────────────────────
    if not verify_password(body.password, password_hash):
        _record_failed_attempt(body.username)
        _record_failed_attempt(client_ip)
        audit_log(
            db, action="auth.login.failed", reason="wrong_password",
            user_id=uid, resource_type="user", resource_id=body.username,
            decision="deny", ip_address=client_ip,
            user_agent=request.headers.get("user-agent"),
        )
        db.commit()
        request.state._audit_recorded = True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # ── Create session + issue tokens ───────────────────────────
    user_agent = request.headers.get("user-agent")
    _session_id, raw_refresh = create_session(
        db, uid, user_agent=user_agent, ip_address=client_ip,
    )
    _set_refresh_cookie(response, raw_refresh, request=request)

    access_token = create_access_token(uid, username, int(token_version))

    # ── Update last_login_at ────────────────────────────────────
    now_ts = datetime.now(timezone.utc).isoformat()
    db.execute(
        text("UPDATE users SET last_login_at = :now, updated_at = :now WHERE id = :uid"),
        {"now": now_ts, "uid": uid},
    )
    db.commit()

    # ── Load full user info (reuses _load_user_with_roles) ─────
    auth_user = _load_user_with_roles(db, uid, int(token_version))
    if auth_user is None:
        # Should not happen — we just verified the password and the user is active
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="登录后无法加载用户信息",
        )
    auth_user["must_change_password"] = bool(must_change_password)
    user_info = _build_user_info(auth_user)

    audit_log(
        db, action="auth.login.success",
        user_id=uid, resource_type="user", resource_id=username,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user_info,
        "must_change_password": bool(must_change_password),
    }


@router.post("/register", response_model=LoginResponse)
def register(
    request: Request,
    body: RegisterRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Create a new user account and auto-login.

    New users are assigned the ``member`` role by default.  Registration is
    rate-limited per client IP to prevent abuse.
    """
    settings = get_settings()

    # ── Rate limiting (per IP only — username doesn't exist yet) ──
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(f"register:{client_ip}")

    # ── Check username uniqueness ─────────────────────────────────
    existing = db.execute(
        text("SELECT id FROM users WHERE username = :un"),
        {"un": body.username},
    ).fetchone()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户名已被占用",
        )

    # ── Ensure seed data exists (idempotent — uses SAVEPOINT internally) ─
    _ensure_seed_data(db)

    # ── Create user ───────────────────────────────────────────────
    now_ts = datetime.now(timezone.utc).isoformat()
    new_hash = hash_password(body.password)
    display_name = body.display_name or body.username

    result = db.execute(
        text(
            "INSERT INTO users (username, password_hash, display_name, email, "
            "is_active, token_version, must_change_password, created_at, updated_at) "
            "VALUES (:un, :pw, :dn, :em, 1, 1, 0, :ts, :ts)"
        ),
        {"un": body.username, "pw": new_hash, "dn": display_name, "em": body.email, "ts": now_ts},
    )
    uid = result.lastrowid

    # ── Org / dept memberships ────────────────────────────────────
    db.execute(
        text(
            "INSERT OR IGNORE INTO user_org_memberships "
            "(user_id, org_id, is_default, created_at) "
            "VALUES (:uid, 'default', 1, :ts)"
        ),
        {"uid": uid, "ts": now_ts},
    )
    db.execute(
        text(
            "INSERT OR IGNORE INTO user_department_memberships "
            "(user_id, org_id, department_id, is_primary, created_at) "
            "VALUES (:uid, 'default', 'HQ', 1, :ts)"
        ),
        {"uid": uid, "ts": now_ts},
    )

    # ── Bind default "dept_staff" role ───────────────────────────
    role_row = db.execute(
        text("SELECT id FROM roles WHERE code = 'dept_staff'"),
    ).fetchone()
    if role_row:
        db.execute(
            text(
                "INSERT OR IGNORE INTO role_bindings "
                "(user_id, role_id, org_id, department_id, created_at) "
                "VALUES (:uid, :rid, 'default', 'HQ', :ts)"
            ),
            {"uid": uid, "rid": role_row[0], "ts": now_ts},
        )

    db.commit()

    # ── Auto-login: create session + issue tokens ─────────────────
    user_agent = request.headers.get("user-agent")
    _session_id, raw_refresh = create_session(
        db, uid, user_agent=user_agent, ip_address=client_ip,
    )
    _set_refresh_cookie(response, raw_refresh, request=request)

    access_token = create_access_token(uid, body.username, 1)

    # ── Load user info ────────────────────────────────────────────
    auth_user = _load_user_with_roles(db, uid, 1)
    if auth_user is None:
        # Should not happen — we just created the user
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="注册后无法加载用户信息",
        )
    user_info = _build_user_info(auth_user)

    audit_log(
        db, action="auth.register.success",
        user_id=uid, resource_type="user", resource_id=body.username,
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user_info,
        "must_change_password": False,
    }


@router.post("/refresh", response_model=RefreshResponse)
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Exchange a valid refresh-token cookie for a new access token.

    The old refresh token is immediately revoked and a new one is issued
    (rotation on each use).  If a revoked or expired token is replayed
    the request is rejected.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 Refresh Token",
        )

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")

    try:
        result = rotate_session(
            db, refresh_token,
            user_agent=user_agent,
            ip_address=client_ip,
        )
    except InvalidSessionError as exc:
        logger.info("Refresh failed: %s", exc.reason)
        # Record structured audit event for replay / expired / disabled attempts
        audit_log(
            db, action="auth.refresh.failed",
            reason=exc.reason, resource_type="auth_session",
            decision="deny", ip_address=client_ip,
            user_agent=user_agent,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        )

    settings = get_settings()
    access_token = create_access_token(
        result["user_id"],
        result["username"],
        result["token_version"],
    )
    _set_refresh_cookie(response, result["new_refresh_token"], request=request)

    audit_log(
        db, action="auth.refresh.success",
        user_id=result["user_id"], resource_type="auth_session",
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Revoke the current refresh token and clear the cookie."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent")

    # Resolve user identity from the refresh token for audit purposes.
    # We look up the session before revoking it so we can record *who* logged out.
    resolved_user_id: int | None = None
    if refresh_token:
        from auth.sessions import _hash_token
        token_hash = _hash_token(refresh_token)
        session_row = db.execute(
            text("SELECT user_id FROM auth_sessions WHERE refresh_token_hash = :hash"),
            {"hash": token_hash},
        ).fetchone()
        if session_row:
            resolved_user_id = session_row[0]

        revoke_session(db, refresh_token)

    audit_log(
        db, action="auth.logout",
        user_id=resolved_user_id, resource_type="auth_session",
        ip_address=client_ip,
        user_agent=user_agent,
    )
    db.commit()

    _clear_refresh_cookie(response, request=request)
    return {"message": "已退出登录"}


@router.get("/me", response_model=UserInfo)
def me(current_user: dict[str, Any] = Depends(get_current_user)) -> Any:
    """Return the authenticated user's identity and permissions."""
    return _build_user_info(current_user)


@router.post("/change-password", response_model=UserInfo)
def change_password(
    request: Request,
    body: ChangePasswordRequest,
    response: Response,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Any:
    """Change the current user's password.

    After a successful change, ``must_change_password`` is cleared,
    ``token_version`` is incremented (invalidating all existing tokens),
    and a new refresh-token cookie is set.
    """
    uid = current_user["id"]

    # Verify current password
    row = db.execute(
        text("SELECT password_hash FROM users WHERE id = :uid"),
        {"uid": uid},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    if not verify_password(body.current_password, row[0]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="当前密码错误",
        )

    # Hash new password
    new_hash = hash_password(body.new_password)
    now_ts = datetime.now(timezone.utc).isoformat()

    # Update user (token_version + 1 to invalidate existing access tokens;
    # must_change_password cleared; is_active NOT changed — the user was
    # already verified active by get_current_user)
    db.execute(
        text(
            "UPDATE users SET password_hash = :pw, token_version = token_version + 1, "
            "must_change_password = 0, updated_at = :now "
            "WHERE id = :uid"
        ),
        {"pw": new_hash, "now": now_ts, "uid": uid},
    )

    # Revoke all existing sessions
    revoke_all_user_sessions(db, uid)

    # Create new session
    user_agent = request.headers.get("user-agent")
    client_ip = request.client.host if request.client else "unknown"
    _session_id, raw_refresh = create_session(
        db, uid,
        user_agent=user_agent,
        ip_address=client_ip,
    )
    _set_refresh_cookie(response, raw_refresh, request=request)
    db.commit()

    client_ip = request.client.host if request.client else "unknown"
    audit_log(
        db, action="auth.change_password",
        user_id=uid, resource_type="user", resource_id=str(uid),
        ip_address=client_ip,
        user_agent=request.headers.get("user-agent"),
    )
    db.commit()

    return _build_user_info({
        **current_user,
        "must_change_password": False,
    })
