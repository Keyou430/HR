"""JWT Access Token creation and validation.

Tokens use HS256 and carry minimal identity payloads:
``{"sub": user_id, "usr": username, "ver": token_version, "exp": ..., "iat": ...}``

Validation (signature, expiry) happens here.  Business-level checks
(is_active, token_version match, etc.) are done in *dependencies.py*
so they can query the database on every request.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from config import get_settings


def create_access_token(user_id: int, username: str, token_version: int) -> str:
    """Issue a short-lived JWT for *user_id*."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "usr": username,
        "ver": token_version,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
    }
    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """Verify signature and expiry of *token*.

    Returns the decoded payload dict on success.  Raises ``jwt.ExpiredSignatureError``,
    ``jwt.InvalidTokenError``, etc. on failure — callers should catch these and
    translate to appropriate HTTP errors.

    This function does **not** hit the database; it only performs cryptographic
    validation.  The caller (``get_current_user``) is responsible for checking
    that the user is still active and the *token_version* still matches.
    """
    settings = get_settings()
    return jwt.decode(
        token,
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["exp", "iat", "sub"]},
    )
