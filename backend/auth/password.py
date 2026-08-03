"""Password hashing and verification using bcrypt.

All hashes use the ``$2b$`` prefix with configurable rounds (default 12).
Timing-safe comparison is handled by bcrypt internally.
"""

from __future__ import annotations

import bcrypt

from config import get_settings


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain* as a str (``$2b$12$...``)."""
    settings = get_settings()
    return bcrypt.hashpw(
        plain.encode("utf-8"),
        bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS),
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time comparison of *plain* against *hashed*."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def password_needs_change(user_row: object) -> bool:
    """Return True if the user must change their password before proceeding.

    This is True when:
    - ``must_change_password`` column is 1 / True
    - The account is inactive (``is_active == 0``) — treated as
      "needs activation via password change"
    """
    must_change = getattr(user_row, "must_change_password", None)
    if must_change and int(must_change) == 1:
        return True
    is_active = getattr(user_row, "is_active", None)
    if is_active is not None and int(is_active) == 0:
        return True
    return False
