"""Phase 2: Auth integration tests — login, refresh, logout, token lifecycle.

These tests use FastAPI's TestClient against an in-memory SQLite database
so no external server is required.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# ── Ensure backend is importable ────────────────────────────────────
BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from alembic import command
from alembic.config import Config
from auth.password import hash_password
from sqlalchemy import create_engine, text

from main import app


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

TEST_USER = "testuser"
TEST_PASSWORD = "correct-password-123"
TEST_DISPLAY = "Test User"


def _alembic_config(db_path: str) -> Config:
    ini_path = str(BACKEND_ROOT / "alembic.ini")
    cfg = Config(ini_path)
    cfg.file_config.read(ini_path, encoding="utf-8")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def _upgrade(db_path: str, revision: str = "head") -> None:
    command.upgrade(_alembic_config(db_path), revision)


def _seed_test_user(db_url: str, **overrides) -> int:
    """Insert an active test user with a known password. Returns user_id."""
    pw_hash = hash_password(TEST_PASSWORD)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, display_name, is_active, "
                "token_version, must_change_password, created_at, updated_at) "
                "VALUES (:un, :pw, :dn, :active, :tv, :mcp, '2026-07-30T00:00:00', '2026-07-30T00:00:00')"
            ),
            {
                "un": overrides.get("username", TEST_USER),
                "pw": pw_hash,
                "dn": overrides.get("display_name", TEST_DISPLAY),
                "active": overrides.get("is_active", 1),
                "tv": overrides.get("token_version", 1),
                "mcp": overrides.get("must_change_password", 0),
            },
        )
        uid = result.lastrowid

        # Check if orgs/departments exist (from seed) and create memberships
        org_exists = conn.execute(text("SELECT 1 FROM orgs WHERE id='default'")).fetchone()
        if org_exists:
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO user_org_memberships (user_id, org_id, is_default, created_at) "
                    "VALUES (:uid, 'default', 1, '2026-07-30T00:00:00')"
                ),
                {"uid": uid},
            )
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO user_department_memberships "
                    "(user_id, org_id, department_id, is_primary, created_at) "
                    "VALUES (:uid, 'default', 'HQ', 1, '2026-07-30T00:00:00')"
                ),
                {"uid": uid},
            )

    engine.dispose()
    return uid


def _login(client: TestClient, username: str = TEST_USER, password: str = TEST_PASSWORD) -> dict:
    """Helper: login and return the full response dict."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    return {"status": resp.status_code, "body": resp.json() if resp.status_code == 200 else resp.json()}


# ──────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Return a TestClient backed by a fresh, migrated SQLite database.

    The database has:
    - All RBAC tables (migration 001)
    - must_change_password column (migration 002)
    - Seed data (org, dept, system_seed, roles, permissions)
    - One active test user (testuser / correct-password-123)
    """
    db_path = tmp_path / "test_auth.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-pytest-32chars-min")
    from config import get_settings
    get_settings.cache_clear()

    # Reset session module globals so get_engine() picks up the new DATABASE_URL
    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None

    # Run migrations
    _upgrade(str(db_path), "head")

    # Seed test user
    _seed_test_user(db_url)

    # Reset rate limiter
    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        yield c

    # Cleanup
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    get_settings.cache_clear()


# ──────────────────────────────────────────────────────────────────
# 1. Login — correct password
# ──────────────────────────────────────────────────────────────────


def test_login_correct_password(client):
    """Correct credentials return 200 + access_token + user info + refresh cookie."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USER, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, resp.json()
    data = resp.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["user"]["username"] == TEST_USER
    assert data["user"]["display_name"] == TEST_DISPLAY
    assert "must_change_password" in data

    # Refresh cookie should be set
    cookies = resp.cookies
    assert "refresh_token" in cookies
    # HttpOnly is set by the server but not visible in TestClient cookies


# ──────────────────────────────────────────────────────────────────
# 2. Login — wrong password
# ──────────────────────────────────────────────────────────────────


def test_login_wrong_password(client):
    """Wrong password returns 401 with a generic error message."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USER, "password": "wrong-password"},
    )
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert "用户名或密码错误" in detail
    # Must NOT distinguish "user not found" vs "wrong password"
    assert "不存在" not in detail
    assert "密码错误" not in detail.replace("用户名或密码错误", "")


# ──────────────────────────────────────────────────────────────────
# 3. Login — non-existent user (should look the same as wrong password)
# ──────────────────────────────────────────────────────────────────


def test_login_nonexistent_user(client):
    """Login with a username that doesn't exist returns same generic error."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "no_such_user_42", "password": "anything"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "用户名或密码错误"


# ──────────────────────────────────────────────────────────────────
# 4. Login — disabled user
# ──────────────────────────────────────────────────────────────────


def test_login_disabled_user(client, tmp_path, monkeypatch):
    """A disabled user (is_active=0) cannot log in."""
    db_path = tmp_path / "test_disabled.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-pytest-32chars-min")
    from config import get_settings
    get_settings.cache_clear()

    _upgrade(str(db_path), "head")
    _seed_test_user(db_url, is_active=0, username="disabled_user")

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app) as c:
        resp = c.post(
            "/api/v1/auth/login",
            json={"username": "disabled_user", "password": TEST_PASSWORD},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "用户名或密码错误"


# ──────────────────────────────────────────────────────────────────
# 5. Access Token — expiry
# ──────────────────────────────────────────────────────────────────


def test_access_token_expired(client, monkeypatch):
    """An expired access token returns 401."""
    # First login to get a valid token
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USER, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200
    access_token = resp.json()["access_token"]

    # Verify /me works with valid token
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200

    # Now create a token that is already expired by patching the expiry
    from auth import tokens as tokens_mod
    import jwt as pyjwt
    from datetime import datetime, timedelta, timezone

    # Create an already-expired token
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": "1",
        "usr": TEST_USER,
        "ver": 1,
        "exp": now - timedelta(minutes=5),
        "iat": now - timedelta(minutes=20),
    }
    expired_token = pyjwt.encode(expired_payload, "test-secret-key-for-pytest-32chars-min", algorithm="HS256")

    me_resp2 = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert me_resp2.status_code == 401
    assert "过期" in me_resp2.json()["detail"]


# ──────────────────────────────────────────────────────────────────
# 6. Refresh Token — rotation
# ──────────────────────────────────────────────────────────────────


def test_refresh_token_rotation(client):
    """Refresh returns a new access token and sets a new refresh cookie."""
    # Login
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USER, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200
    old_cookie = resp.cookies.get("refresh_token")
    assert old_cookie

    # Refresh
    client.cookies.set("refresh_token", old_cookie, path="/api/v1/auth")
    refresh_resp = client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200, refresh_resp.json()
    data = refresh_resp.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0

    new_cookie = refresh_resp.cookies.get("refresh_token")
    assert new_cookie
    assert new_cookie != old_cookie  # Must be a new token


# ──────────────────────────────────────────────────────────────────
# 7. Refresh — old token replay
# ──────────────────────────────────────────────────────────────────


def test_refresh_old_token_replay(client):
    """After rotation, the old refresh token is rejected (replay detection)."""
    # Login
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USER, "password": TEST_PASSWORD},
    )
    old_cookie = resp.cookies.get("refresh_token")

    # First refresh — consumes the old token, issues new one
    client.cookies.set("refresh_token", old_cookie, path="/api/v1/auth")
    refresh_resp = client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 200

    # Second refresh with the SAME old token — must fail
    client.cookies.clear()
    client.cookies.set("refresh_token", old_cookie, path="/api/v1/auth")
    replay_resp = client.post("/api/v1/auth/refresh")
    assert replay_resp.status_code == 401


# ──────────────────────────────────────────────────────────────────
# 8. Logout revokes refresh token
# ──────────────────────────────────────────────────────────────────


def test_logout_revokes_refresh(client):
    """After logout, the refresh token can no longer be used."""
    # Login
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USER, "password": TEST_PASSWORD},
    )
    cookie = resp.cookies.get("refresh_token")

    # Logout
    client.cookies.set("refresh_token", cookie, path="/api/v1/auth")
    logout_resp = client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert "退出" in logout_resp.json()["message"]

    # Try to refresh with the revoked token
    client.cookies.set("refresh_token", cookie, path="/api/v1/auth")
    refresh_resp = client.post("/api/v1/auth/refresh")
    assert refresh_resp.status_code == 401


# ──────────────────────────────────────────────────────────────────
# 9. token_version change invalidates old access token
# ──────────────────────────────────────────────────────────────────


def test_token_version_invalidation(client, tmp_path, monkeypatch):
    """After token_version is incremented, old access tokens are rejected."""
    # Login
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USER, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200
    access_token = resp.json()["access_token"]

    # Verify /me works
    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200

    # Increment token_version in the database
    db_url = f"sqlite:///{tmp_path.as_posix()}/test_auth.db"
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET token_version = token_version + 1 WHERE username = :un"),
            {"un": TEST_USER},
        )
    engine.dispose()

    # Same access token should now be rejected
    me_resp2 = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp2.status_code == 401


# ──────────────────────────────────────────────────────────────────
# 10. Unauthenticated access returns 401
# ──────────────────────────────────────────────────────────────────


def test_unauthenticated_returns_401(client):
    """Accessing /me without a token returns 401."""
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401


# ──────────────────────────────────────────────────────────────────
# 11. Me returns complete user info
# ──────────────────────────────────────────────────────────────────


def test_me_returns_user_info(client):
    """GET /me returns the authenticated user's identity and permissions."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": TEST_USER, "password": TEST_PASSWORD},
    )
    access_token = resp.json()["access_token"]

    me_resp = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["username"] == TEST_USER
    assert data["display_name"] == TEST_DISPLAY
    assert "roles" in data
    assert "permissions" in data
    assert "must_change_password" in data
    assert isinstance(data["id"], int)


# ──────────────────────────────────────────────────────────────────
# 12. Rate limiting on login
# ──────────────────────────────────────────────────────────────────


def test_login_rate_limiting(client, monkeypatch):
    """After LOGIN_MAX_ATTEMPTS failed attempts, further attempts get 429."""

    # Set a very low limit for testing
    monkeypatch.setenv("LOGIN_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("LOGIN_WINDOW_SECONDS", "60")
    from config import get_settings
    get_settings.cache_clear()

    from auth.router import _login_attempts
    _login_attempts.clear()

    # 3 failed attempts
    for _ in range(3):
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": "bad_user", "password": "wrong"},
        )
        assert resp.status_code == 401

    # 4th attempt should be rate limited (429)
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": "bad_user", "password": "wrong"},
    )
    assert resp.status_code == 429

    _login_attempts.clear()
    get_settings.cache_clear()


# ──────────────────────────────────────────────────────────────────
# 13. Change password
# ──────────────────────────────────────────────────────────────────


def test_change_password(client, tmp_path, monkeypatch):
    """change-password updates the hash, clears must_change_password, and bumps token_version."""
    db_path = tmp_path / "test_changepw.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-pytest-32chars-min")
    from config import get_settings
    get_settings.cache_clear()

    _upgrade(str(db_path), "head")
    uid = _seed_test_user(db_url, must_change_password=1)

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app) as c:
        # Login — should indicate must_change_password
        resp = c.post(
            "/api/v1/auth/login",
            json={"username": TEST_USER, "password": TEST_PASSWORD},
        )
        assert resp.status_code == 200
        assert resp.json()["must_change_password"] is True

        access_token = resp.json()["access_token"]

        # Change password
        cp_resp = c.post(
            "/api/v1/auth/change-password",
            json={"current_password": TEST_PASSWORD, "new_password": "new-secure-password-456"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert cp_resp.status_code == 200, cp_resp.json()
        assert cp_resp.json()["must_change_password"] is False

        # Old access token should be invalid (token_version bumped)
        me_resp = c.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_resp.status_code == 401

        # New login with old password should fail
        old_login = c.post(
            "/api/v1/auth/login",
            json={"username": TEST_USER, "password": TEST_PASSWORD},
        )
        assert old_login.status_code == 401

        # New login with new password should succeed
        new_login = c.post(
            "/api/v1/auth/login",
            json={"username": TEST_USER, "password": "new-secure-password-456"},
        )
        assert new_login.status_code == 200
        assert new_login.json()["must_change_password"] is False

    _login_attempts.clear()
    get_settings.cache_clear()
