"""Refresh-token session management.

Refresh tokens are random hex strings.  Only their SHA-256 hashes are
stored in the ``auth_sessions`` table.

Rotation policy: every call to ``rotate_session`` revokes the old token
and creates a fresh one (rotation-on-each-use).  This detects replay
attacks — if a revoked token is presented again we know it was stolen.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import get_settings

logger = logging.getLogger("replica")

# Public-facing message — never distinguish *why* a session is invalid
_INVALID_MSG = "会话已过期，请重新登录"


class InvalidSessionError(ValueError):
    """Raised when a refresh token is invalid for any reason.

    The public-facing message is always ``_INVALID_MSG``; the internal
    *reason* is written to the server log for diagnostics.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(_INVALID_MSG)
        self.reason = reason


# ── helpers ────────────────────────────────────────────────────────


def _hash_token(raw: str) -> str:
    """SHA-256 hex digest of *raw*."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_at() -> str:
    settings = get_settings()
    return (
        datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    ).isoformat()


# ── public API ─────────────────────────────────────────────────────


def create_session(
    db: Session,
    user_id: int,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> tuple[str, str]:
    """Create a new refresh-token session.

    Returns ``(session_id, raw_refresh_token)``.  The **caller** is
    responsible for setting the ``raw_refresh_token`` as an HttpOnly
    cookie — it is never stored in the database.
    """
    settings = get_settings()
    raw = secrets.token_hex(settings.REFRESH_TOKEN_BYTES)
    session_id = uuid.uuid4().hex
    now_ts = _now()
    expires = _expires_at()

    db.execute(
        text(
            "INSERT INTO auth_sessions "
            "(id, user_id, refresh_token_hash, user_agent, ip_address, "
            "expires_at, revoked_at, created_at, updated_at) "
            "VALUES (:id, :uid, :hash, :ua, :ip, :exp, NULL, :now, :now)"
        ),
        {
            "id": session_id,
            "uid": user_id,
            "hash": _hash_token(raw),
            "ua": user_agent,
            "ip": ip_address,
            "exp": expires,
            "now": now_ts,
        },
    )
    db.commit()
    return session_id, raw


def rotate_session(
    db: Session,
    raw_refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Validate *raw_refresh_token*, revoke the old session, and create a new one.

    Returns a dict with ``user_id``, ``username``, ``token_version``, and
    ``new_refresh_token`` for the authenticated user so the caller can issue
    a fresh access token.

    Raises ``InvalidSessionError`` if the token is invalid, revoked, or expired.

    The UPDATE includes ``AND revoked_at IS NULL`` + a rowcount check to close
    the TOCTOU window where two concurrent requests could both succeed on the
    same old token.
    """
    token_hash = _hash_token(raw_refresh_token)
    now_ts = _now()

    # Look up the session
    row = db.execute(
        text(
            "SELECT s.id, s.user_id, s.revoked_at, s.expires_at, "
            "u.username, u.token_version, u.is_active "
            "FROM auth_sessions s "
            "JOIN users u ON u.id = s.user_id "
            "WHERE s.refresh_token_hash = :hash"
        ),
        {"hash": token_hash},
    ).fetchone()

    if row is None:
        logger.warning("Refresh token not found in auth_sessions (hash prefix: %s)", token_hash[:12])
        raise InvalidSessionError("token not found")

    _id, user_id, revoked_at, expires_at, username, token_version, is_active = row

    # Check revocation
    if revoked_at is not None:
        logger.warning("Refresh token replay detected for user %s (session %s)", user_id, _id)
        raise InvalidSessionError("token already revoked")

    # Check expiry
    if expires_at < now_ts:
        logger.info("Refresh token expired for user %s (session %s)", user_id, _id)
        raise InvalidSessionError("token expired")

    # Check user is active
    if int(is_active) == 0:
        logger.info("Refresh attempt by disabled user %s", user_id)
        raise InvalidSessionError("account disabled")

    # ── Revoke the old session (with TOCTOU guard) ──────────────
    result = db.execute(
        text(
            "UPDATE auth_sessions SET revoked_at = :now, updated_at = :now "
            "WHERE id = :id AND revoked_at IS NULL"
        ),
        {"now": now_ts, "id": _id},
    )
    if result.rowcount == 0:
        logger.warning("Concurrent revocation detected for session %s (user %s)", _id, user_id)
        raise InvalidSessionError("token already revoked")

    # ── Create a new session (rotation) ─────────────────────────
    settings = get_settings()
    new_raw = secrets.token_hex(settings.REFRESH_TOKEN_BYTES)
    new_id = uuid.uuid4().hex
    new_expires = _expires_at()

    db.execute(
        text(
            "INSERT INTO auth_sessions "
            "(id, user_id, refresh_token_hash, user_agent, ip_address, "
            "expires_at, revoked_at, created_at, updated_at) "
            "VALUES (:id, :uid, :hash, :ua, :ip, :exp, NULL, :now, :now)"
        ),
        {
            "id": new_id,
            "uid": user_id,
            "hash": _hash_token(new_raw),
            "ua": user_agent,
            "ip": ip_address,
            "exp": new_expires,
            "now": now_ts,
        },
    )
    db.commit()

    return {
        "user_id": user_id,
        "username": username,
        "token_version": int(token_version),
        "new_refresh_token": new_raw,
    }


def revoke_session(db: Session, raw_refresh_token: str) -> None:
    """Revoke the session associated with *raw_refresh_token* (logout).

    Does not raise if the token is already revoked or does not exist —
    logout should always succeed from the user's perspective.
    """
    token_hash = _hash_token(raw_refresh_token)
    now_ts = _now()
    db.execute(
        text(
            "UPDATE auth_sessions SET revoked_at = :now, updated_at = :now "
            "WHERE refresh_token_hash = :hash AND revoked_at IS NULL"
        ),
        {"now": now_ts, "hash": token_hash},
    )
    db.commit()


def revoke_all_user_sessions(db: Session, user_id: int) -> None:
    """Revoke every active session for *user_id*.

    Called after ``token_version`` is incremented so that all existing
    access + refresh tokens become invalid in a single operation.

    Does **not** commit — the caller is responsible for the transaction
    boundary.
    """
    now_ts = _now()
    db.execute(
        text(
            "UPDATE auth_sessions SET revoked_at = :now, updated_at = :now "
            "WHERE user_id = :uid AND revoked_at IS NULL"
        ),
        {"now": now_ts, "uid": user_id},
    )
