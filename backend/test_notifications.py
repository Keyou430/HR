"""T7: Notification API tests — CRUD, cross-user isolation, unread count, auth.

Tests the four notification endpoints:
  GET  /api/v1/notifications          — list (authenticated)
  GET  /api/v1/notifications/unread-count  — unread badge count
  PUT  /api/v1/notifications/{id}/read  — mark one as read
  PUT  /api/v1/notifications/read-all   — mark all as read

Also covers the Phase 1 notification hook: role-change → create_notification.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from alembic import command
from alembic.config import Config
from auth.password import hash_password
from sqlalchemy import create_engine, text

from main import app

USER_A = "notif_user_a"
PASS_A = "notif-a-123"
USER_B = "notif_user_b"
PASS_B = "notif-b-123"
SUPER_USER = "notif_admin"
SUPER_PASS = "notif-admin-123"


def _alembic_config(db_path: str) -> Config:
    ini_path = str(BACKEND_ROOT / "alembic.ini")
    cfg = Config(ini_path)
    cfg.file_config.read(ini_path, encoding="utf-8")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def _upgrade(db_path: str, revision: str = "head") -> None:
    command.upgrade(_alembic_config(db_path), revision)


def _create_user(db_url: str, username: str, password: str, display_name: str,
                 role_code: str = "dept_staff") -> int:
    pw_hash = hash_password(password)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, display_name, is_active, "
                "token_version, must_change_password, created_at, updated_at) "
                "VALUES (:un, :pw, :dn, 1, 1, 0, '2026-07-30T00:00:00', '2026-07-30T00:00:00')"
            ),
            {"un": username, "pw": pw_hash, "dn": display_name},
        )
        uid = result.lastrowid
        conn.execute(
            text("INSERT OR IGNORE INTO user_org_memberships "
                 "(user_id, org_id, is_default, created_at) "
                 "VALUES (:uid, 'default', 1, '2026-07-30T00:00:00')"),
            {"uid": uid},
        )
        conn.execute(
            text("INSERT OR IGNORE INTO user_department_memberships "
                 "(user_id, org_id, department_id, is_primary, created_at) "
                 "VALUES (:uid, 'default', 'HQ', 1, '2026-07-30T00:00:00')"),
            {"uid": uid},
        )
        role_row = conn.execute(
            text("SELECT id FROM roles WHERE code = :rc"), {"rc": role_code}
        ).fetchone()
        if role_row:
            conn.execute(
                text("INSERT OR IGNORE INTO role_bindings "
                     "(user_id, role_id, org_id, department_id, created_at) "
                     "VALUES (:uid, :rid, 'default', 'HQ', '2026-07-30T00:00:00')"),
                {"uid": uid, "rid": role_row[0]},
            )
    engine.dispose()
    return uid


def _login(client: TestClient, username: str, password: str) -> str:
    """Login and return the access token string."""
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed: {resp.json()}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Create a fresh test DB with two users and seed a notification for user A."""
    db_path = tmp_path / "test_notifications.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-for-notifications-32ch")
    monkeypatch.setenv("AUDIT_ENABLED", "false")
    from config import get_settings
    get_settings.cache_clear()
    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    _upgrade(str(db_path), "head")
    uid_a = _create_user(db_url, USER_A, PASS_A, "User A")
    uid_b = _create_user(db_url, USER_B, PASS_B, "User B")
    _create_user(db_url, SUPER_USER, SUPER_PASS, "Admin", role_code="super_admin")
    from auth.router import _login_attempts
    _login_attempts.clear()

    # Seed a notification for user A using the store
    from store import store
    store.create_notification(
        user_id=uid_a,
        title="测试通知",
        content="这是一条测试通知内容",
        type_="info",
    )
    store.create_notification(
        user_id=uid_a,
        title="已读通知",
        content="这条已经读过了",
        type_="system",
    )

    with TestClient(app, cookies={}) as c:
        yield c

    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    get_settings.cache_clear()


# ── T7.1: Auth required ──────────────────────────────────────────────────

class TestAuthRequired:
    """All notification endpoints require authentication."""

    def test_list_requires_auth(self, client):
        resp = client.get("/api/v1/notifications")
        assert resp.status_code == 401

    def test_unread_count_requires_auth(self, client):
        resp = client.get("/api/v1/notifications/unread-count")
        assert resp.status_code == 401

    def test_mark_read_requires_auth(self, client):
        resp = client.put("/api/v1/notifications/1/read")
        assert resp.status_code == 401

    def test_mark_all_read_requires_auth(self, client):
        resp = client.put("/api/v1/notifications/read-all")
        assert resp.status_code == 401


# ── T7.2: List notifications ─────────────────────────────────────────────

class TestListNotifications:
    """GET /api/v1/notifications — list current user's notifications."""

    def test_list_returns_items(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/notifications", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 2
        # Verify structure
        item = data["items"][0]
        assert "id" in item
        assert "title" in item
        assert "is_read" in item
        assert "created_at" in item

    def test_list_newest_first(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/notifications", headers=_auth(token))
        items = resp.json()["items"]
        # Items should be in descending order by created_at
        if len(items) >= 2:
            assert items[0]["created_at"] >= items[1]["created_at"]

    def test_list_respects_limit(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/notifications?limit=1", headers=_auth(token))
        data = resp.json()
        assert len(data["items"]) <= 1

    def test_other_user_sees_only_own(self, client):
        """User B should not see User A's notifications."""
        token = _login(client, USER_B, PASS_B)
        resp = client.get("/api/v1/notifications", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        # User B has no notifications
        assert data["total"] == 0


# ── T7.3: Unread count ───────────────────────────────────────────────────

class TestUnreadCount:
    """GET /api/v1/notifications/unread-count"""

    def test_unread_count_matches(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/notifications/unread-count", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["unread_count"] == 2  # Both seeded notifications are unread

    def test_unread_count_zero_for_new_user(self, client):
        token = _login(client, USER_B, PASS_B)
        resp = client.get("/api/v1/notifications/unread-count", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["unread_count"] == 0


# ── T7.4: Mark single notification as read ────────────────────────────────

class TestMarkRead:
    """PUT /api/v1/notifications/{id}/read"""

    def test_mark_read_success(self, client):
        token = _login(client, USER_A, PASS_A)
        # Get the first notification
        list_resp = client.get("/api/v1/notifications", headers=_auth(token))
        notif_id = list_resp.json()["items"][0]["id"]

        resp = client.put(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Verify unread count decreased
        count_resp = client.get("/api/v1/notifications/unread-count", headers=_auth(token))
        assert count_resp.json()["unread_count"] == 1

    def test_mark_read_404_for_other_user(self, client):
        """User B cannot mark User A's notification as read."""
        token_a = _login(client, USER_A, PASS_A)
        token_b = _login(client, USER_B, PASS_B)
        # Get a notification ID belonging to user A
        list_resp = client.get("/api/v1/notifications", headers=_auth(token_a))
        notif_id = list_resp.json()["items"][0]["id"]

        # User B tries to mark it read
        resp = client.put(f"/api/v1/notifications/{notif_id}/read", headers=_auth(token_b))
        assert resp.status_code == 404

    def test_mark_read_404_for_nonexistent(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.put("/api/v1/notifications/99999/read", headers=_auth(token))
        assert resp.status_code == 404


# ── T7.5: Mark all read ───────────────────────────────────────────────────

class TestMarkAllRead:
    """PUT /api/v1/notifications/read-all"""

    def test_mark_all_read_success(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.put("/api/v1/notifications/read-all", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["updated"] == 2  # Both seeded notifications

        # Verify unread count is now 0
        count_resp = client.get("/api/v1/notifications/unread-count", headers=_auth(token))
        assert count_resp.json()["unread_count"] == 0

    def test_mark_all_read_idempotent(self, client):
        token = _login(client, USER_A, PASS_A)
        # First call
        client.put("/api/v1/notifications/read-all", headers=_auth(token))
        # Second call — should be a no-op
        resp = client.put("/api/v1/notifications/read-all", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["updated"] == 0

    def test_mark_all_read_only_affects_own(self, client):
        """Marking all read for User B should not affect User A's notifications."""
        token_a = _login(client, USER_A, PASS_A)
        token_b = _login(client, USER_B, PASS_B)

        # User B marks all read (has none anyway)
        client.put("/api/v1/notifications/read-all", headers=_auth(token_b))

        # User A's unread count should be unchanged
        count_resp = client.get("/api/v1/notifications/unread-count", headers=_auth(token_a))
        assert count_resp.json()["unread_count"] == 2


# ── T7.6: Notification hook — role change creates notification ────────────

class TestNotificationHook:
    """When an admin changes a user's roles, the target user gets a notification."""

    def test_role_change_creates_notification(self, client):
        admin_token = _login(client, SUPER_USER, SUPER_PASS)
        user_b_token = _login(client, USER_B, PASS_B)

        # Get User B's actual ID from /me
        me_resp = client.get("/api/v1/auth/me", headers=_auth(user_b_token))
        assert me_resp.status_code == 200
        user_b_id = me_resp.json()["id"]

        # Admin sets roles for User B
        resp = client.put(
            f"/api/v1/admin/users/{user_b_id}/roles",
            json={"role_codes": ["super_admin", "dept_staff"]},
            headers=_auth(admin_token),
        )
        assert resp.status_code == 200

        # Role change bumps token_version — re-login to get a fresh token
        user_b_token = _login(client, USER_B, PASS_B)

        # User B should now have a notification about role change
        list_resp = client.get("/api/v1/notifications", headers=_auth(user_b_token))
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        role_notifs = [n for n in items if n["type"] == "system" and "角色" in n["title"]]
        assert len(role_notifs) >= 1
        assert "super_admin" in role_notifs[0]["content"] or "dept_staff" in role_notifs[0]["content"]
