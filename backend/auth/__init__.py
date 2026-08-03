"""Replica auth package — password hashing, token management, session handling."""

from auth.dependencies import require_permission
from auth.password import hash_password, verify_password, password_needs_change
from auth.sessions import (
    create_session,
    revoke_all_user_sessions,
    revoke_session,
    rotate_session,
)
from auth.tokens import create_access_token, decode_access_token

__all__ = [
    "hash_password",
    "verify_password",
    "password_needs_change",
    "create_access_token",
    "decode_access_token",
    "create_session",
    "rotate_session",
    "revoke_session",
    "revoke_all_user_sessions",
    "require_permission",
]
