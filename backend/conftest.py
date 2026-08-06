"""Shared pytest fixtures for Replica backend tests.

Provides fixtures for:
- Temp SQLite database with alembic migrations applied
- FastAPI TestClient with standard test users pre-seeded
- Role-specific pre-authenticated clients
- Helper functions exported at module level for direct use

Existing test files that define their own ``client`` fixture are unaffected —
pytest uses the most-specific fixture (the one defined closest to the test).

Usage::

    def test_something(client):
        token = login(client, "test_super_admin", "test-super-admin-32chars!!!")
        resp = client.get("/api/v1/subsystems", headers=auth_headers(token))
        assert resp.status_code == 200

    def test_as_super_admin(super_admin_client):
        resp = super_admin_client.get("/api/v1/admin/users")
        assert resp.status_code == 200
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

# ═══════════════════════════════════════════════════════════════════════
# Test user definitions
# ═══════════════════════════════════════════════════════════════════════

TEST_USERS = {
    "super_admin": {
        "username": "test_super_admin",
        "password": "test-super-admin-32chars!!!",
        "display_name": "Test Super Admin",
        "role_code": "super_admin",
        "org_id": "default",
        "dept_id": "HQ",
    },
    "org_admin": {
        "username": "test_org_admin",
        "password": "test-org-admin-32chars!!!",
        "display_name": "Test Org Admin",
        "role_code": "org_admin",
        "org_id": "default",
        "dept_id": "HQ",
    },
    "dept_leader": {
        "username": "test_dept_leader",
        "password": "test-dept-leader-32chars!",
        "display_name": "Test Dept Leader",
        "role_code": "dept_leader",
        "org_id": "default",
        "dept_id": "HQ",
    },
    "dept_staff": {
        "username": "test_dept_staff",
        "password": "test-dept-staff-32chars!",
        "display_name": "Test Dept Staff",
        "role_code": "dept_staff",
        "org_id": "default",
        "dept_id": "HQ",
    },
    "external": {
        "username": "test_external",
        "password": "test-external-32chars!!",
        "display_name": "Test External",
        "role_code": "external",
        "org_id": "default",
        "dept_id": "HQ",
    },
}


# ═══════════════════════════════════════════════════════════════════════
# Module-level helpers (usable in any test file via import from conftest)
# ═══════════════════════════════════════════════════════════════════════


def alembic_config(db_path: str) -> Config:
    """Build an Alembic Config pointed at a temp SQLite database."""
    ini_path = str(BACKEND_ROOT / "alembic.ini")
    cfg = Config(ini_path)
    cfg.file_config.read(ini_path, encoding="utf-8")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def upgrade_db(db_path: str, revision: str = "head") -> None:
    """Run all alembic migrations on a temp database."""
    command.upgrade(alembic_config(db_path), revision)


def create_user(
    db_url: str,
    username: str,
    password: str,
    display_name: str,
    role_code: str = "dept_staff",
    org_id: str = "default",
    dept_id: str = "HQ",
) -> int:
    """Insert a test user with org/dept membership and role binding.

    Returns the new user's integer ID.
    """
    pw_hash = hash_password(password)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, display_name, is_active, "
                "token_version, must_change_password, created_at, updated_at) "
                "VALUES (:un, :pw, :dn, 1, 1, 0, '2026-08-04T00:00:00', '2026-08-04T00:00:00')"
            ),
            {"un": username, "pw": pw_hash, "dn": display_name},
        )
        uid = result.lastrowid

        conn.execute(
            text(
                "INSERT OR IGNORE INTO user_org_memberships "
                "(user_id, org_id, is_default, created_at) "
                "VALUES (:uid, :oid, 1, '2026-08-04T00:00:00')"
            ),
            {"uid": uid, "oid": org_id},
        )
        conn.execute(
            text(
                "INSERT OR IGNORE INTO user_department_memberships "
                "(user_id, org_id, department_id, is_primary, created_at) "
                "VALUES (:uid, :oid, :did, 1, '2026-08-04T00:00:00')"
            ),
            {"uid": uid, "oid": org_id, "did": dept_id},
        )

        role_row = conn.execute(
            text("SELECT id FROM roles WHERE code = :rc"), {"rc": role_code}
        ).fetchone()
        if role_row:
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO role_bindings "
                    "(user_id, role_id, org_id, department_id, created_at) "
                    "VALUES (:uid, :rid, :oid, :did, '2026-08-04T00:00:00')"
                ),
                {"uid": uid, "rid": role_row[0], "oid": org_id, "did": dept_id},
            )
    engine.dispose()
    return uid


def login(client: TestClient, username: str, password: str) -> str:
    """Log in and return an access token string."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, (
        f"Login failed for {username}: {resp.status_code} {resp.text}"
    )
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    """Return an Authorization header dict for the given token."""
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════


def _setup_test_env(monkeypatch, db_url: str) -> None:
    """Configure environment and reset module-level caches for testing."""
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "conftest-test-secret-32chars!")
    monkeypatch.setenv("FASTGPT_MODE", "mock")
    monkeypatch.setenv("HERMES_MODE", "mock")
    monkeypatch.setenv("AUDIT_ENABLED", "false")

    from config import get_settings
    get_settings.cache_clear()

    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None


def _teardown_test_env() -> None:
    """Reset module-level caches after a test."""
    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None

    from config import get_settings
    get_settings.cache_clear()


def _seed_default_org(db_url: str) -> None:
    """Ensure the default org exists."""
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT OR IGNORE INTO orgs (id, name, is_active, created_at) "
            "VALUES ('default', '默认组织', 1, '2026-08-04T00:00:00')"
        ))
    engine.dispose()


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Yield a FastAPI TestClient connected to a fresh temp SQLite database.

    The database is fully migrated and seeded with:
    - Default org (id="default")
    - One super_admin user
    - One dept_staff user

    Usage::

        def test_example(client):
            token = login(client, "test_super_admin", "test-super-admin-32chars!!!")
            resp = client.get("/api/v1/subsystems", headers=auth_headers(token))
            assert resp.status_code == 200
    """
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    _setup_test_env(monkeypatch, db_url)
    upgrade_db(str(db_path), "head")
    _seed_default_org(db_url)

    create_user(db_url, **TEST_USERS["super_admin"])
    create_user(db_url, **TEST_USERS["dept_staff"])

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        yield c

    _teardown_test_env()


@pytest.fixture
def super_admin_client(tmp_path, monkeypatch):
    """Yield a TestClient pre-authenticated as super_admin.

    The token is obtained via real login, so it passes full auth middleware.
    """
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    _setup_test_env(monkeypatch, db_url)
    upgrade_db(str(db_path), "head")
    _seed_default_org(db_url)

    create_user(db_url, **TEST_USERS["super_admin"])

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        token = login(c, TEST_USERS["super_admin"]["username"],
                      TEST_USERS["super_admin"]["password"])
        c.headers = {**c.headers, **auth_headers(token)}
        yield c

    _teardown_test_env()


@pytest.fixture
def dept_staff_client(tmp_path, monkeypatch):
    """Yield a TestClient pre-authenticated as dept_staff."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    _setup_test_env(monkeypatch, db_url)
    upgrade_db(str(db_path), "head")
    _seed_default_org(db_url)

    create_user(db_url, **TEST_USERS["dept_staff"])

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        token = login(c, TEST_USERS["dept_staff"]["username"],
                      TEST_USERS["dept_staff"]["password"])
        c.headers = {**c.headers, **auth_headers(token)}
        yield c

    _teardown_test_env()


@pytest.fixture
def dept_leader_client(tmp_path, monkeypatch):
    """Yield a TestClient pre-authenticated as dept_leader."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    _setup_test_env(monkeypatch, db_url)
    upgrade_db(str(db_path), "head")
    _seed_default_org(db_url)

    create_user(db_url, **TEST_USERS["dept_leader"])

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        token = login(c, TEST_USERS["dept_leader"]["username"],
                      TEST_USERS["dept_leader"]["password"])
        c.headers = {**c.headers, **auth_headers(token)}
        yield c

    _teardown_test_env()


@pytest.fixture
def org_admin_client(tmp_path, monkeypatch):
    """Yield a TestClient pre-authenticated as org_admin."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    _setup_test_env(monkeypatch, db_url)
    upgrade_db(str(db_path), "head")
    _seed_default_org(db_url)

    create_user(db_url, **TEST_USERS["org_admin"])

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        token = login(c, TEST_USERS["org_admin"]["username"],
                      TEST_USERS["org_admin"]["password"])
        c.headers = {**c.headers, **auth_headers(token)}
        yield c

    _teardown_test_env()


@pytest.fixture
def external_client(tmp_path, monkeypatch):
    """Yield a TestClient pre-authenticated as external."""
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    _setup_test_env(monkeypatch, db_url)
    upgrade_db(str(db_path), "head")
    _seed_default_org(db_url)

    create_user(db_url, **TEST_USERS["external"])

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        token = login(c, TEST_USERS["external"]["username"],
                      TEST_USERS["external"]["password"])
        c.headers = {**c.headers, **auth_headers(token)}
        yield c

    _teardown_test_env()


@pytest.fixture
def all_roles_client(tmp_path, monkeypatch):
    """Yield a dict with client + tokens for all 5 roles.

    Returns::

        {
            "client": TestClient,          # unauthenticated
            "tokens": dict[str, str],      # role_code → access_token
            "user_ids": dict[str, int],    # role_code → user_id
        }
    """
    db_path = tmp_path / "test.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    _setup_test_env(monkeypatch, db_url)
    upgrade_db(str(db_path), "head")
    _seed_default_org(db_url)

    user_ids: dict[str, int] = {}
    for role_key, user_def in TEST_USERS.items():
        uid = create_user(db_url, **user_def)
        user_ids[role_key] = uid

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        tokens: dict[str, str] = {}
        for role_key, user_def in TEST_USERS.items():
            tokens[role_key] = login(c, user_def["username"], user_def["password"])

        yield {
            "client": c,
            "tokens": tokens,
            "user_ids": user_ids,
        }

    _teardown_test_env()
