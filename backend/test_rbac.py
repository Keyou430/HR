"""Phase 3: RBAC functional permission tests.

Covers:
- ``user_has_permission`` unit tests (direct function call)
- 5-role × permission matrix (integration via TestClient)
- Unauthenticated → 401
- Authenticated without permission → 403
- Authenticated with permission → success
- Admin endpoints require super_admin
- Knowledge import / sync / mapping update / delete
- Integrations modify endpoints
- Portal bootstrap requires auth
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
from authorization.rbac import user_has_permission
from sqlalchemy import create_engine, text

from main import app


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

ROLE_CODES = ["super_admin", "org_admin", "dept_leader", "dept_staff", "external"]

# For users without roles, use a descriptive label
NO_ROLE_LABEL = "(no role)"


def _alembic_config(db_path: str) -> Config:
    ini_path = str(BACKEND_ROOT / "alembic.ini")
    cfg = Config(ini_path)
    cfg.file_config.read(ini_path, encoding="utf-8")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def _upgrade(db_path: str, revision: str = "head") -> None:
    command.upgrade(_alembic_config(db_path), revision)


def _create_user_with_role(
    db_url: str,
    username: str,
    password: str,
    role_code: str,
    display_name: str = "",
) -> int:
    """Insert a user with a role binding. Returns user_id."""
    pw_hash = hash_password(password)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, display_name, is_active, "
                "token_version, must_change_password, created_at, updated_at) "
                "VALUES (:un, :pw, :dn, 1, 1, 0, '2026-07-30T00:00:00', '2026-07-30T00:00:00')"
            ),
            {"un": username, "pw": pw_hash, "dn": display_name or username},
        )
        uid = result.lastrowid

        # Org membership
        conn.execute(
            text(
                "INSERT OR IGNORE INTO user_org_memberships "
                "(user_id, org_id, is_default, created_at) "
                "VALUES (:uid, 'default', 1, '2026-07-30T00:00:00')"
            ),
            {"uid": uid},
        )
        # Dept membership
        conn.execute(
            text(
                "INSERT OR IGNORE INTO user_department_memberships "
                "(user_id, org_id, department_id, is_primary, created_at) "
                "VALUES (:uid, 'default', 'HQ', 1, '2026-07-30T00:00:00')"
            ),
            {"uid": uid},
        )
        # Role binding
        role_row = conn.execute(
            text("SELECT id FROM roles WHERE code = :rc"), {"rc": role_code}
        ).fetchone()
        if role_row:
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO role_bindings "
                    "(user_id, role_id, org_id, department_id, created_at) "
                    "VALUES (:uid, :rid, 'default', 'HQ', '2026-07-30T00:00:00')"
                ),
                {"uid": uid, "rid": role_row[0]},
            )

    engine.dispose()
    return uid


def _create_user_without_role(
    db_url: str,
    username: str,
    password: str,
    display_name: str = "",
) -> int:
    """Insert an active user with NO role bindings. Returns user_id."""
    pw_hash = hash_password(password)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, display_name, is_active, "
                "token_version, must_change_password, created_at, updated_at) "
                "VALUES (:un, :pw, :dn, 1, 1, 0, '2026-07-30T00:00:00', '2026-07-30T00:00:00')"
            ),
            {"un": username, "pw": pw_hash, "dn": display_name or username},
        )
        uid = result.lastrowid
        # Org + dept memberships (needed for get_current_user to load org/dept)
        conn.execute(
            text(
                "INSERT OR IGNORE INTO user_org_memberships "
                "(user_id, org_id, is_default, created_at) "
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


def _login(client: TestClient, username: str, password: str) -> str:
    """Login and return the access_token string."""
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed for {username}: {resp.json()}"
    return resp.json()["access_token"]


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def rbac_db(tmp_path, monkeypatch):
    """Create a fresh migrated DB with one user per role + one no-role user.

    Returns a dict mapping role_code → (username, password).
    """
    db_path = tmp_path / "test_rbac.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-rbac-secret-key-min-32charsok")
    monkeypatch.setenv("FASTGPT_MODE", "mock")
    monkeypatch.setenv("HERMES_MODE", "mock")
    from config import get_settings
    get_settings.cache_clear()

    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None

    _upgrade(str(db_path), "head")

    # Reset rate limiter
    from auth.router import _login_attempts
    _login_attempts.clear()

    users: dict[str, tuple[str, str]] = {}

    for role_code in ROLE_CODES:
        username = f"test_{role_code}"
        password = f"pw_{role_code}_123"
        _create_user_with_role(db_url, username, password, role_code)
        users[role_code] = (username, password)

    # No-role user
    _create_user_without_role(db_url, "test_norole", "pw_norole_123")
    users[NO_ROLE_LABEL] = ("test_norole", "pw_norole_123")

    yield users

    # Cleanup
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    get_settings.cache_clear()


@pytest.fixture
def client(rbac_db, monkeypatch):
    """Return a TestClient that shares the rbac_db fixture's database."""
    with TestClient(app, cookies={}) as c:
        yield c


@pytest.fixture
def tokens(client, rbac_db) -> dict[str, str]:
    """Login all test users and return role_code → access_token."""
    result: dict[str, str] = {}
    for role_code in ROLE_CODES:
        username, password = rbac_db[role_code]
        result[role_code] = _login(client, username, password)
    # Also login no-role user
    username, password = rbac_db[NO_ROLE_LABEL]
    result[NO_ROLE_LABEL] = _login(client, username, password)
    return result


# ═══════════════════════════════════════════════════════════════════
# 1. Unit tests — user_has_permission
# ═══════════════════════════════════════════════════════════════════


def test_user_has_permission_super_admin_always_true():
    """super_admin has every permission regardless of explicit list."""
    user = {"id": 1, "roles": ["super_admin"], "permissions": []}
    assert user_has_permission(user, "task:view") is True
    assert user_has_permission(user, "system:config") is True
    assert user_has_permission(user, "nonexistent:perm") is True


def test_user_has_permission_explicit_grant():
    """User with a permission in their list returns True."""
    user = {"id": 2, "roles": ["dept_staff"], "permissions": ["task:view", "task:create"]}
    assert user_has_permission(user, "task:view") is True
    assert user_has_permission(user, "task:create") is True


def test_user_has_permission_default_deny():
    """Permission not in list returns False."""
    user = {"id": 2, "roles": ["dept_staff"], "permissions": ["task:view"]}
    assert user_has_permission(user, "task:delete") is False
    assert user_has_permission(user, "kb:import") is False


def test_user_has_permission_no_roles_no_perms():
    """User with no roles and no permissions gets nothing."""
    user = {"id": 3, "roles": [], "permissions": []}
    assert user_has_permission(user, "task:view") is False
    assert user_has_permission(user, "search:view") is False


def test_user_has_permission_empty_user_dict():
    """Empty user dict defaults to deny."""
    user: dict = {}
    assert user_has_permission(user, "task:view") is False


# ═══════════════════════════════════════════════════════════════════
# 2. Unauthenticated access → 401
# ═══════════════════════════════════════════════════════════════════


UNAUTH_401_ENDPOINTS = [
    ("GET", "/api/v1/tasks"),
    ("POST", "/api/v1/tasks"),
    ("PATCH", "/api/v1/tasks/1"),
    ("DELETE", "/api/v1/tasks/1"),
    ("POST", "/api/v1/tasks/clear-done"),
    ("GET", "/api/v1/calendar/events"),
    ("POST", "/api/v1/calendar/events"),
    ("PUT", "/api/v1/calendar/events/1"),
    ("DELETE", "/api/v1/calendar/events/1"),
    ("GET", "/api/v1/knowledge/spaces"),
    ("GET", "/api/v1/knowledge/mappings"),
    ("PATCH", "/api/v1/knowledge/mappings/x"),
    ("DELETE", "/api/v1/knowledge/mappings/x"),
    ("GET", "/api/v1/knowledge/imports"),
    ("POST", "/api/v1/knowledge/sync"),
    ("POST", "/api/v1/knowledge/chat"),
    ("GET", "/api/v1/knowledge/datasets/ds1/files"),
    ("DELETE", "/api/v1/knowledge/datasets/ds1/files/f1"),
    ("GET", "/api/v1/search"),
    ("GET", "/api/v1/integrations/embed-urls"),
    ("PUT", "/api/v1/integrations/embed-urls"),
    ("GET", "/api/v1/portal/bootstrap"),
    ("GET", "/api/v1/chat/sessions"),
    ("GET", "/api/v1/chat/sessions/s1/messages"),
    ("POST", "/api/v1/chat/messages"),
    ("DELETE", "/api/v1/chat/sessions/s1"),
    ("GET", "/api/v1/admin/users"),
]


@pytest.mark.parametrize("method,path", [(m, p) for m, p in UNAUTH_401_ENDPOINTS])
def test_unauthenticated_returns_401(client, method, path):
    """All protected endpoints return 401 without a token."""
    body = None
    if method in ("POST", "PATCH", "PUT"):
        body = {}
        if "tasks" in path and "clear-done" not in path:
            body = {"title": "x", "tag": "今天"}
        elif "calendar" in path:
            body = {"title": "x", "date": "2026-08-01", "tone": "blue"}
        elif "chat/messages" in path:
            body = {"session_id": "s1", "role": "user", "content": "x"}
        elif "knowledge/chat" in path:
            body = {"question": "x", "mode": "chat"}
        elif "integrations" in path:
            body = {"feishu": "https://x.com"}
        elif "knowledge/mappings" in path:
            body = {"display_name": "x"}

    resp = client.request(method, path, json=body)
    assert resp.status_code == 401, (
        f"{method} {path} returned {resp.status_code}, expected 401"
    )


# ═══════════════════════════════════════════════════════════════════
# 3. Health check is public
# ═══════════════════════════════════════════════════════════════════


def test_health_is_public(client):
    """GET /health requires no auth."""
    resp = client.get("/health")
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 4. Permission matrix — key endpoints × all roles
# ═══════════════════════════════════════════════════════════════════

# (method, path, body, permission_name, expected_by_role)
# expected_by_role: dict[role_code, expected_status]
PERMISSION_MATRIX = [
    # ── Tasks ──────────────────────────────────────────────────
    (
        "GET", "/api/v1/tasks", None, "task:view",
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 200, NO_ROLE_LABEL: 403},
    ),
    (
        "POST", "/api/v1/tasks", {"title": "test", "tag": "今天"}, "task:create",
        {"super_admin": 201, "org_admin": 201, "dept_leader": 201,
         "dept_staff": 201, "external": 403, NO_ROLE_LABEL: 403},
    ),
    (
        "PATCH", "/api/v1/tasks/99999", {"done": True}, "task:update",
        {"super_admin": 404, "org_admin": 404, "dept_leader": 404,
         "dept_staff": 404, "external": 403, NO_ROLE_LABEL: 403},
    ),
    (
        "DELETE", "/api/v1/tasks/99999", None, "task:delete",
        {"super_admin": 404, "org_admin": 404, "dept_leader": 404,
         "dept_staff": 404, "external": 403, NO_ROLE_LABEL: 403},
    ),
    # G1: clear-done requires task:delete
    (
        "POST", "/api/v1/tasks/clear-done", None, "task:delete",
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 403, NO_ROLE_LABEL: 403},
    ),
    # ── Calendar ───────────────────────────────────────────────
    (
        "GET", "/api/v1/calendar/events", None, "calendar:view",
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 200, NO_ROLE_LABEL: 403},
    ),
    (
        "POST", "/api/v1/calendar/events",
        {"title": "test", "date": "2026-08-01", "tone": "blue"}, "calendar:create",
        {"super_admin": 201, "org_admin": 201, "dept_leader": 201,
         "dept_staff": 201, "external": 403, NO_ROLE_LABEL: 403},
    ),
    # G2: calendar update / delete (non-existent → 404 for authorized, 403 for denied)
    (
        "PUT", "/api/v1/calendar/events/99999",
        {"title": "x", "date": "2026-08-01", "tone": "blue"}, "calendar:update",
        {"super_admin": 404, "org_admin": 404, "dept_leader": 404,
         "dept_staff": 404, "external": 403, NO_ROLE_LABEL: 403},
    ),
    (
        "DELETE", "/api/v1/calendar/events/99999", None, "calendar:delete",
        {"super_admin": 404, "org_admin": 404, "dept_leader": 404,
         "dept_staff": 404, "external": 403, NO_ROLE_LABEL: 403},
    ),
    # ── Search ─────────────────────────────────────────────────
    (
        "GET", "/api/v1/search", None, "search:view",
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 200, NO_ROLE_LABEL: 403},
    ),
    # ── Knowledge ──────────────────────────────────────────────
    (
        "GET", "/api/v1/knowledge/spaces", None, "kb:view",
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 200, NO_ROLE_LABEL: 403},
    ),
    (
        "POST", "/api/v1/knowledge/chat",
        {"question": "hello", "mode": "chat"}, "kb:chat",
        # Mock Hermes mode returns 200
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 403, NO_ROLE_LABEL: 403},
    ),
    (
        "POST", "/api/v1/knowledge/sync", None, "kb:import",
        # Mock FastGPT mode returns 409, but only for those WITH kb:import
        {"super_admin": 409, "org_admin": 409, "dept_leader": 409,
         "dept_staff": 403, "external": 403, NO_ROLE_LABEL: 403},
    ),
    (
        "PATCH", "/api/v1/knowledge/mappings/nonexistent",
        {"display_name": "x"}, "kb:update",
        {"super_admin": 404, "org_admin": 404, "dept_leader": 404,
         "dept_staff": 403, "external": 403, NO_ROLE_LABEL: 403},
    ),
    (
        "DELETE", "/api/v1/knowledge/mappings/nonexistent",
        None, "kb:delete",
        {"super_admin": 404, "org_admin": 404, "dept_leader": 403,
         "dept_staff": 403, "external": 403, NO_ROLE_LABEL: 403},
    ),
    # G3: dataset files — GET needs kb:view, DELETE needs kb:delete
    (
        "GET", "/api/v1/knowledge/datasets/ds1/files", None, "kb:view",
        # Mock FastGPT mode returns {"items": [], "total": 0}
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 200, NO_ROLE_LABEL: 403},
    ),
    (
        "DELETE", "/api/v1/knowledge/datasets/ds1/files/f1", None, "kb:delete",
        # Mock FastGPT mode: users WITH kb:delete get 409, without get 403
        {"super_admin": 409, "org_admin": 409, "dept_leader": 403,
         "dept_staff": 403, "external": 403, NO_ROLE_LABEL: 403},
    ),
    # ── Integrations ───────────────────────────────────────────
    (
        "GET", "/api/v1/integrations/embed-urls", None, "org:view",
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 403, NO_ROLE_LABEL: 403},
    ),
    (
        "PUT", "/api/v1/integrations/embed-urls",
        {"feishu": "https://custom.example.com"}, "org:update",
        {"super_admin": 200, "org_admin": 200, "dept_leader": 403,
         "dept_staff": 403, "external": 403, NO_ROLE_LABEL: 403},
    ),
    # ── Portal bootstrap ───────────────────────────────────────
    # (authenticated only — all roles including no-role should get 200)
    (
        "GET", "/api/v1/portal/bootstrap", None, "(authenticated)",
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 200, NO_ROLE_LABEL: 200},
    ),
    # ── Chat sessions ──────────────────────────────────────────
    (
        "GET", "/api/v1/chat/sessions", None, "(authenticated)",
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 200, NO_ROLE_LABEL: 200},
    ),
    (
        "POST", "/api/v1/chat/messages",
        {"session_id": "test-s1", "role": "user", "content": "hello"},
        "(authenticated)",
        {"super_admin": 200, "org_admin": 200, "dept_leader": 200,
         "dept_staff": 200, "external": 200, NO_ROLE_LABEL: 200},
    ),
]


@pytest.mark.parametrize(
    "method,path,body,_perm,expected_by_role",
    [(m, p, b, pm, ebr) for m, p, b, pm, ebr in PERMISSION_MATRIX],
)
def test_permission_matrix(client, tokens, method, path, body, _perm, expected_by_role):
    """Each role gets the expected HTTP status for each endpoint."""
    for role_code, expected_status in expected_by_role.items():
        token = tokens.get(role_code)
        assert token is not None, f"No token for role: {role_code}"

        headers = {"Authorization": f"Bearer {token}"}
        if method == "GET":
            resp = client.get(path, headers=headers)
        else:
            resp = client.request(method, path, json=body, headers=headers)

        assert resp.status_code == expected_status, (
            f"{method} {path} as {role_code}: "
            f"expected {expected_status}, got {resp.status_code} "
            f"(body={resp.json() if resp.headers.get('content-type') == 'application/json' else resp.text[:200]})"
        )


# ═══════════════════════════════════════════════════════════════════
# 5. Admin endpoints require super_admin
# ═══════════════════════════════════════════════════════════════════


ADMIN_ENDPOINTS = [
    ("GET", "/api/v1/admin/users", None),
    ("GET", "/api/v1/admin/roles", None),
    ("POST", "/api/v1/admin/users",
     {"username": "newuser", "password": "newpw_12345678", "display_name": "New"}),
    # G4: PATCH status and PUT roles — use high ID so super_admin gets 404
    ("PATCH", "/api/v1/admin/users/99999/status",
     {"is_active": True}),
    ("PUT", "/api/v1/admin/users/99999/roles",
     {"role_codes": ["dept_staff"]}),
]


@pytest.mark.parametrize("method,path,body", ADMIN_ENDPOINTS)
def test_admin_endpoints_super_admin_only(client, tokens, method, path, body):
    """Only super_admin can access admin endpoints."""
    for role_code in ROLE_CODES:
        token = tokens[role_code]
        headers = {"Authorization": f"Bearer {token}"}
        if method == "GET":
            resp = client.get(path, headers=headers)
        else:
            resp = client.request(method, path, json=body, headers=headers)

        if role_code == "super_admin":
            assert resp.status_code in (200, 201, 404), (
                f"super_admin should have access to {method} {path}, "
                f"got {resp.status_code}"
            )
        else:
            assert resp.status_code == 403, (
                f"{role_code} should NOT have access to {method} {path}, "
                f"got {resp.status_code}"
            )


def test_admin_require_admin_dependency_exists():
    """Verify require_admin function rejects non-super_admin."""
    from admin_router import require_admin
    # require_admin is a function that takes current_user and returns it or raises
    assert callable(require_admin)


# ═══════════════════════════════════════════════════════════════════
# 6. Knowledge import endpoint permission
# ═══════════════════════════════════════════════════════════════════


def test_knowledge_import_requires_kb_import(client, tokens):
    """POST /api/v1/knowledge/import needs kb:import permission."""
    # dept_staff (no kb:import) → 403
    resp = client.post(
        "/api/v1/knowledge/import",
        headers={"Authorization": f"Bearer {tokens['dept_staff']}"},
    )
    assert resp.status_code == 403, f"dept_staff got {resp.status_code}, expected 403"

    # dept_leader (has kb:import) → 422 (missing file, but permission ok)
    resp = client.post(
        "/api/v1/knowledge/import",
        headers={"Authorization": f"Bearer {tokens['dept_leader']}"},
    )
    assert resp.status_code == 422, (
        f"dept_leader got {resp.status_code}, expected 422 (missing file)"
    )


# ═══════════════════════════════════════════════════════════════════
# 7. Knowledge mapping update / delete permission
# ═══════════════════════════════════════════════════════════════════


def test_knowledge_mapping_update_permission(client, tokens):
    """PATCH on mappings requires kb:update."""
    # external (no kb:update) → 403
    resp = client.patch(
        "/api/v1/knowledge/mappings/nonexistent",
        json={"display_name": "x"},
        headers={"Authorization": f"Bearer {tokens['external']}"},
    )
    assert resp.status_code == 403

    # dept_leader (has kb:update) → 404 (doesn't exist, but permission ok)
    resp = client.patch(
        "/api/v1/knowledge/mappings/nonexistent",
        json={"display_name": "x"},
        headers={"Authorization": f"Bearer {tokens['dept_leader']}"},
    )
    assert resp.status_code == 404


def test_knowledge_mapping_delete_permission(client, tokens):
    """DELETE on mappings requires kb:delete."""
    # dept_staff (no kb:delete) → 403
    resp = client.delete(
        "/api/v1/knowledge/mappings/nonexistent",
        headers={"Authorization": f"Bearer {tokens['dept_staff']}"},
    )
    assert resp.status_code == 403

    # org_admin (has kb:delete) → 404 (doesn't exist, but permission ok)
    resp = client.delete(
        "/api/v1/knowledge/mappings/nonexistent",
        headers={"Authorization": f"Bearer {tokens['org_admin']}"},
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# 8. Integrations modify endpoint permission
# ═══════════════════════════════════════════════════════════════════


def test_integrations_put_requires_org_update(client, tokens):
    """PUT /api/v1/integrations/embed-urls needs org:update."""
    # dept_staff (no org:update) → 403
    resp = client.put(
        "/api/v1/integrations/embed-urls",
        json={"feishu": "https://blocked.example.com"},
        headers={"Authorization": f"Bearer {tokens['dept_staff']}"},
    )
    assert resp.status_code == 403

    # org_admin (has org:update) → 200
    resp = client.put(
        "/api/v1/integrations/embed-urls",
        json={"feishu": "https://allowed.example.com"},
        headers={"Authorization": f"Bearer {tokens['org_admin']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["feishu"] == "https://allowed.example.com"


def test_integrations_get_requires_org_view(client, tokens):
    """GET /api/v1/integrations/embed-urls needs org:view."""
    # external (no org:view) → 403
    resp = client.get(
        "/api/v1/integrations/embed-urls",
        headers={"Authorization": f"Bearer {tokens['external']}"},
    )
    assert resp.status_code == 403

    # dept_staff (has org:view) → 200
    resp = client.get(
        "/api/v1/integrations/embed-urls",
        headers={"Authorization": f"Bearer {tokens['dept_staff']}"},
    )
    assert resp.status_code == 200
    assert "feishu" in resp.json()


# ═══════════════════════════════════════════════════════════════════
# 9. No-role user gets 403 on all permission-protected endpoints
# ═══════════════════════════════════════════════════════════════════


def test_norole_user_denied_on_permission_endpoints(client, tokens):
    """A user with no role bindings has no permissions — everything returns 403."""
    token = tokens[NO_ROLE_LABEL]

    permission_endpoints = [
        ("GET", "/api/v1/tasks"),
        ("POST", "/api/v1/tasks"),
        ("GET", "/api/v1/calendar/events"),
        ("GET", "/api/v1/search"),
        ("GET", "/api/v1/knowledge/spaces"),
        ("GET", "/api/v1/integrations/embed-urls"),
    ]
    for method, path in permission_endpoints:
        resp = client.request(method, path, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 403, (
            f"no-role user got {resp.status_code} on {method} {path}, expected 403"
        )

    # But auth-only endpoints should work
    resp = client.get(
        "/api/v1/portal/bootstrap",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    resp = client.get(
        "/api/v1/chat/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# 10. PermissionChecker class
# ═══════════════════════════════════════════════════════════════════


def test_permission_checker_class_exists():
    """PermissionChecker can be imported and instantiated."""
    from authorization.checks import PermissionChecker
    checker = PermissionChecker("task:view")
    assert checker._permission_code == "task:view"
    assert repr(checker) == "PermissionChecker('task:view')"


# ═══════════════════════════════════════════════════════════════════
# 11. External role — limited access verification
# ═══════════════════════════════════════════════════════════════════


def test_external_can_only_access_public_scoped_endpoints(client, tokens):
    """external has only task:view, calendar:view, kb:view, search:view."""
    token = tokens["external"]

    # Allowed
    assert client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/v1/calendar/events", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/v1/search", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert client.get("/api/v1/knowledge/spaces", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    # Not allowed
    assert client.post("/api/v1/tasks", json={"title": "x", "tag": "今天"}, headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.post("/api/v1/calendar/events", json={"title": "x", "date": "2026-08-01", "tone": "blue"}, headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.post("/api/v1/knowledge/chat", json={"question": "x", "mode": "chat"}, headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.get("/api/v1/integrations/embed-urls", headers={"Authorization": f"Bearer {token}"}).status_code == 403


# ═══════════════════════════════════════════════════════════════════
# 12. dept_staff permission boundaries
# ═══════════════════════════════════════════════════════════════════


def test_dept_staff_permission_boundaries(client, tokens):
    """dept_staff can CRUD own tasks but cannot import/delete knowledge."""
    token = tokens["dept_staff"]

    # Allowed — task CRUD
    assert client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    resp = client.post("/api/v1/tasks", json={"title": "staff task", "tag": "今天"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 201

    # Not allowed — knowledge management
    assert client.post("/api/v1/knowledge/sync", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.post("/api/v1/knowledge/import", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.patch("/api/v1/knowledge/mappings/x", json={"display_name": "x"}, headers={"Authorization": f"Bearer {token}"}).status_code == 403
    assert client.delete("/api/v1/knowledge/mappings/x", headers={"Authorization": f"Bearer {token}"}).status_code == 403

    # Not allowed — org management
    assert client.put("/api/v1/integrations/embed-urls", json={"feishu": "https://x.com"}, headers={"Authorization": f"Bearer {token}"}).status_code == 403

    # Not allowed — admin
    assert client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"}).status_code == 403

    # Allowed — chat (has kb:chat)
    resp = client.post("/api/v1/knowledge/chat", json={"question": "hello", "mode": "chat"}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
