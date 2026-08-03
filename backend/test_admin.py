"""Phase 2: Admin router integration tests — user CRUD, role assignment, guards.

Uses FastAPI TestClient against in-memory SQLite, same pattern as test_auth.py.
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

# ── Helpers ────────────────────────────────────────────────────────────

SUPER_USER = "superadmin"
SUPER_PASSWORD = "super-pass-123"
REGULAR_USER = "regular"
REGULAR_PASSWORD = "regular-pass-123"


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
                 is_active: int = 1, is_super_admin: bool = False) -> int:
    """Insert a user and optionally bind the super_admin role."""
    pw_hash = hash_password(password)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, display_name, is_active, "
                "token_version, must_change_password, created_at, updated_at) "
                "VALUES (:un, :pw, :dn, :active, 1, 0, '2026-07-30T00:00:00', '2026-07-30T00:00:00')"
            ),
            {"un": username, "pw": pw_hash, "dn": display_name, "active": is_active},
        )
        uid = result.lastrowid

        # Org / dept membership
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

        # Role binding
        role_code = "super_admin" if is_super_admin else "dept_staff"
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


def _login(client: TestClient, username: str, password: str) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    return {
        "status": resp.status_code,
        "body": resp.json() if resp.status_code == 200 else resp.json(),
    }


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with fresh DB, one super_admin + one regular user."""
    db_path = tmp_path / "test_admin.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-pytest-admin-32c")
    from config import get_settings
    get_settings.cache_clear()

    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None

    _upgrade(str(db_path), "head")
    _create_user(db_url, SUPER_USER, SUPER_PASSWORD, "Super Admin", is_super_admin=True)
    _create_user(db_url, REGULAR_USER, REGULAR_PASSWORD, "Regular User")

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        yield c

    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    get_settings.cache_clear()


@pytest.fixture
def admin_token(client):
    """Return a valid access token for the super_admin user."""
    result = _login(client, SUPER_USER, SUPER_PASSWORD)
    assert result["status"] == 200, f"Admin login failed: {result['body']}"
    return result["body"]["access_token"]


@pytest.fixture
def user_token(client):
    """Return a valid access token for the regular user."""
    result = _login(client, REGULAR_USER, REGULAR_PASSWORD)
    assert result["status"] == 200, f"User login failed: {result['body']}"
    return result["body"]["access_token"]


# ── Tests ───────────────────────────────────────────────────────────────


class TestAdminListUsers:
    """GET /api/v1/admin/users"""

    def test_list_users_as_admin(self, client, admin_token):
        resp = client.get("/api/v1/admin/users", headers=_auth_headers(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["total"] >= 2  # super_admin + regular + maybe system_seed
        usernames = [u["username"] for u in body["items"]]
        assert SUPER_USER in usernames
        assert REGULAR_USER in usernames

    def test_list_users_supports_search(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/users", headers=_auth_headers(admin_token),
            params={"search": "regular"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert body["items"][0]["username"] == REGULAR_USER

    def test_list_users_supports_pagination(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/users", headers=_auth_headers(admin_token),
            params={"page": 1, "page_size": 1},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["total"] >= 2  # total still reflects all users

    def test_rejects_regular_user(self, client, user_token):
        resp = client.get("/api/v1/admin/users", headers=_auth_headers(user_token))
        assert resp.status_code == 403

    def test_rejects_unauthenticated(self, client):
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 401


class TestAdminListRoles:
    """GET /api/v1/admin/roles"""

    def test_list_roles(self, client, admin_token):
        resp = client.get("/api/v1/admin/roles", headers=_auth_headers(admin_token))
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 5  # 5 system roles
        codes = {r["code"] for r in body["items"]}
        assert codes == {"super_admin", "org_admin", "dept_leader", "dept_staff", "external"}

    def test_rejects_regular_user(self, client, user_token):
        resp = client.get("/api/v1/admin/roles", headers=_auth_headers(user_token))
        assert resp.status_code == 403


class TestAdminCreateUser:
    """POST /api/v1/admin/users"""

    def test_create_regular_user(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/users",
            json={"username": "newuser", "password": "newpass12", "display_name": "Newbie"},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["username"] == "newuser"
        assert body["display_name"] == "Newbie"
        assert body["is_active"] is True
        assert "dept_staff" in body["roles"]

    def test_create_admin_user(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/users",
            json={"username": "newadmin", "password": "newpass12", "is_admin": True},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "super_admin" in body["roles"]

    def test_rejects_duplicate_username(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/users",
            json={"username": REGULAR_USER, "password": "dup-pass-123"},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 409

    def test_rejects_weak_password(self, client, admin_token):
        """Pydantic schema enforces min_length=8 on password."""
        resp = client.post(
            "/api/v1/admin/users",
            json={"username": "weakpw", "password": "short"},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 422

    def test_rejects_regular_user(self, client, user_token):
        resp = client.post(
            "/api/v1/admin/users",
            json={"username": "hacker", "password": "hackpass123"},
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403


class TestAdminSetUserStatus:
    """PATCH /api/v1/admin/users/{id}/status"""

    def test_disable_and_reenable_user(self, client, admin_token):
        # Create a disposable user
        create_resp = client.post(
            "/api/v1/admin/users",
            json={"username": "toggleme", "password": "toggleme123"},
            headers=_auth_headers(admin_token),
        )
        uid = create_resp.json()["id"]

        # Disable
        resp = client.patch(
            f"/api/v1/admin/users/{uid}/status",
            json={"is_active": False},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        # Re-enable
        resp = client.patch(
            f"/api/v1/admin/users/{uid}/status",
            json={"is_active": True},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    def test_cannot_disable_self(self, client, admin_token):
        # Find our own user id
        me_resp = client.get("/api/v1/auth/me", headers=_auth_headers(admin_token))
        my_id = me_resp.json()["id"]

        resp = client.patch(
            f"/api/v1/admin/users/{my_id}/status",
            json={"is_active": False},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_cannot_disable_last_super_admin(self, client, admin_token):
        # Only one ACTIVE super_admin — disabling should be rejected
        list_resp = client.get("/api/v1/admin/users", headers=_auth_headers(admin_token))
        active_super_admins = [
            u for u in list_resp.json()["items"]
            if "super_admin" in u["roles"] and u["is_active"]
        ]
        assert len(active_super_admins) == 1

        resp = client.patch(
            f"/api/v1/admin/users/{active_super_admins[0]['id']}/status",
            json={"is_active": False},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_404_for_nonexistent_user(self, client, admin_token):
        resp = client.patch(
            "/api/v1/admin/users/99999/status",
            json={"is_active": False},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 404


class TestAdminSetUserRoles:
    """PUT /api/v1/admin/users/{id}/roles"""

    def test_set_roles(self, client, admin_token):
        # Give the regular user dept_leader role
        list_resp = client.get("/api/v1/admin/users", headers=_auth_headers(admin_token),
                               params={"search": REGULAR_USER})
        uid = list_resp.json()["items"][0]["id"]

        resp = client.put(
            f"/api/v1/admin/users/{uid}/roles",
            json={"role_codes": ["dept_leader", "dept_staff"]},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        new_roles = resp.json()["roles"]
        assert "dept_leader" in new_roles
        assert "dept_staff" in new_roles

    def test_rejects_invalid_role_code(self, client, admin_token):
        list_resp = client.get("/api/v1/admin/users", headers=_auth_headers(admin_token),
                               params={"search": REGULAR_USER})
        uid = list_resp.json()["items"][0]["id"]

        resp = client.put(
            f"/api/v1/admin/users/{uid}/roles",
            json={"role_codes": ["nonexistent_role"]},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_cannot_remove_own_super_admin(self, client, admin_token):
        me_resp = client.get("/api/v1/auth/me", headers=_auth_headers(admin_token))
        my_id = me_resp.json()["id"]

        resp = client.put(
            f"/api/v1/admin/users/{my_id}/roles",
            json={"role_codes": ["dept_staff"]},  # removing super_admin
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_cannot_remove_last_super_admin(self, client, admin_token):
        # Only one ACTIVE super_admin — removing their super_admin role should be rejected
        list_resp = client.get("/api/v1/admin/users", headers=_auth_headers(admin_token))
        active_super_admins = [
            u for u in list_resp.json()["items"]
            if "super_admin" in u["roles"] and u["is_active"]
        ]
        assert len(active_super_admins) == 1

        resp = client.put(
            f"/api/v1/admin/users/{active_super_admins[0]['id']}/roles",
            json={"role_codes": []},  # remove all roles
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 400

    def test_404_for_nonexistent_user(self, client, admin_token):
        resp = client.put(
            "/api/v1/admin/users/99999/roles",
            json={"role_codes": ["dept_staff"]},
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 404
