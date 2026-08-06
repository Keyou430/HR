"""Phase 6: Admin API endpoint tests (session management, audit viewing, anomalies).

Tests specific to the Phase 6 admin API endpoints that aren't covered
by test_admin.py (user/role CRUD) or test_audit.py (audit security).
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

SUPER_USER = "api_admin"
SUPER_PASSWORD = "api-admin-123"
REGULAR_USER = "api_user"
REGULAR_PASSWORD = "api-user-123"


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


def _login(client: TestClient, username: str, password: str) -> dict:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return {"status": resp.status_code, "body": resp.json() if resp.status_code == 200 else resp.json()}


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_admin_api.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-for-admin-api-32chars")
    monkeypatch.setenv("AUDIT_ENABLED", "true")
    monkeypatch.setenv("AUDIT_RECORD_AUTH_DENIED", "true")
    from config import get_settings
    get_settings.cache_clear()
    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    _upgrade(str(db_path), "head")
    _create_user(db_url, SUPER_USER, SUPER_PASSWORD, "API Admin", role_code="super_admin")
    _create_user(db_url, REGULAR_USER, REGULAR_PASSWORD, "API User")
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
    result = _login(client, SUPER_USER, SUPER_PASSWORD)
    assert result["status"] == 200
    return result["body"]["access_token"]


@pytest.fixture
def user_token(client):
    result = _login(client, REGULAR_USER, REGULAR_PASSWORD)
    assert result["status"] == 200
    return result["body"]["access_token"]


class TestAdminAuditEndpoints:
    """GET /api/v1/admin/audit"""

    def test_list_audit_returns_paginated(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"page": 1, "page_size": 5},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert len(body["items"]) <= 5

    def test_list_audit_filter_by_action(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"action": "nonexistent_action_xyz"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_list_audit_denied_only(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"decision": "deny"},
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["decision"] == "deny"


class TestAdminAIQueryEndpoints:
    """GET /api/v1/admin/audit/ai-queries"""

    def test_list_ai_queries_as_admin(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/audit/ai-queries",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    def test_ai_queries_denied_for_user(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/audit/ai-queries",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403


class TestAdminSessionEndpoints:
    """GET/DELETE /api/v1/admin/sessions"""

    def test_list_sessions_as_admin(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/sessions",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_list_sessions_active_only(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/sessions",
            headers=_auth_headers(admin_token),
            params={"active_only": "true"},
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["is_active"] is True

    def test_revoke_nonexistent_session(self, client, admin_token):
        resp = client.delete(
            "/api/v1/admin/sessions/fake-session-id-12345",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_sessions_denied_for_user(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/sessions",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403


class TestAdminAnomalyEndpoint:
    """GET /api/v1/admin/anomalies"""

    def test_anomalies_as_admin(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/anomalies",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        required = [
            "total_users", "active_users", "disabled_users",
            "total_sessions", "active_sessions",
            "recent_failed_logins_24h", "recent_403_24h",
            "recent_ai_blocks_24h", "recent_injections_24h",
        ]
        for key in required:
            assert key in body, f"Missing key: {key}"
            assert isinstance(body[key], int), f"Key {key} is not int"

    def test_anomalies_denied_for_user(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/anomalies",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403


class TestAdminSessionRevokeAll:
    """DELETE /api/v1/admin/users/{user_id}/sessions"""

    def test_revoke_all_for_user(self, client, admin_token):
        # Find a user
        users_resp = client.get(
            "/api/v1/admin/users",
            headers=_auth_headers(admin_token),
            params={"search": REGULAR_USER},
        )
        if users_resp.json()["total"] == 0:
            pytest.skip("No test user found")
        uid = users_resp.json()["items"][0]["id"]

        resp = client.delete(
            f"/api/v1/admin/users/{uid}/sessions",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_revoke_all_denied_for_user(self, client, user_token):
        resp = client.delete(
            "/api/v1/admin/users/1/sessions",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403


class TestAdminCustomRoles:
    """T4: POST/PUT /api/v1/admin/roles + GET /api/v1/admin/permissions"""

    def test_list_permissions_grouped(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/permissions",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "groups" in data
        assert len(data["groups"]) >= 18  # 18 permission groups in Phase 1
        # Verify repair group exists
        assert "报修系统" in data["groups"]
        repair_codes = [p["code"] for p in data["groups"]["报修系统"]["permissions"]]
        assert "repair:view" in repair_codes
        assert "repair:create" in repair_codes
        assert "repair:assign" in repair_codes
        assert "repair:update" in repair_codes
        assert "repair:close" in repair_codes

    def test_permissions_denied_for_user(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/permissions",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403

    def test_create_custom_role(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/roles",
            headers=_auth_headers(admin_token),
            json={
                "name": "测试自定义角色",
                "code": "test_custom_role",
                "description": "A custom role for testing",
                "org_id": "default",
                "permission_codes": ["repair:view", "repair:create", "asset:view"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "test_custom_role"
        assert data["name"] == "测试自定义角色"
        assert data["is_system"] is False
        assert data["org_id"] == "default"
        assert "repair:view" in data["permission_codes"]
        assert "repair:create" in data["permission_codes"]
        assert "asset:view" in data["permission_codes"]

    def test_create_role_duplicate_code(self, client, admin_token):
        # First creation
        client.post(
            "/api/v1/admin/roles",
            headers=_auth_headers(admin_token),
            json={"name": "Dup", "code": "dup_role_test", "permission_codes": []},
        )
        # Duplicate
        resp = client.post(
            "/api/v1/admin/roles",
            headers=_auth_headers(admin_token),
            json={"name": "Dup2", "code": "dup_role_test", "permission_codes": []},
        )
        assert resp.status_code == 409

    def test_create_role_invalid_permission(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/roles",
            headers=_auth_headers(admin_token),
            json={
                "name": "Bad",
                "code": "bad_role",
                "permission_codes": ["nonexistent:perm"],
            },
        )
        assert resp.status_code == 400

    def test_update_custom_role_name(self, client, admin_token):
        # Create
        create_resp = client.post(
            "/api/v1/admin/roles",
            headers=_auth_headers(admin_token),
            json={"name": "Original", "code": "update_test_role", "permission_codes": []},
        )
        role_id = create_resp.json()["id"]

        # Update
        resp = client.put(
            f"/api/v1/admin/roles/{role_id}",
            headers=_auth_headers(admin_token),
            json={"name": "Renamed", "description": "Updated desc"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Renamed"
        assert data["description"] == "Updated desc"

    def test_cannot_edit_system_role(self, client, admin_token):
        """System roles (is_system=1) cannot be edited."""
        # Find super_admin role id
        roles_resp = client.get(
            "/api/v1/admin/roles",
            headers=_auth_headers(admin_token),
        )
        sa_id = None
        for r in roles_resp.json()["items"]:
            if r["code"] == "super_admin":
                sa_id = r["id"]
                break
        assert sa_id is not None

        resp = client.put(
            f"/api/v1/admin/roles/{sa_id}",
            headers=_auth_headers(admin_token),
            json={"name": "Hacked"},
        )
        assert resp.status_code == 403

    def test_update_role_permissions(self, client, admin_token):
        # Create
        create_resp = client.post(
            "/api/v1/admin/roles",
            headers=_auth_headers(admin_token),
            json={
                "name": "PermTest",
                "code": "perm_test_role",
                "permission_codes": ["repair:view"],
            },
        )
        role_id = create_resp.json()["id"]

        # Replace permissions
        resp = client.put(
            f"/api/v1/admin/roles/{role_id}/permissions",
            headers=_auth_headers(admin_token),
            json={"permission_codes": ["asset:view", "asset:create", "oa:view"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["permission_codes"]) == {"asset:view", "asset:create", "oa:view"}

    def test_update_role_permissions_invalid_code(self, client, admin_token):
        # Create
        create_resp = client.post(
            "/api/v1/admin/roles",
            headers=_auth_headers(admin_token),
            json={"name": "BadPerm", "code": "bad_perm_role", "permission_codes": []},
        )
        role_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/admin/roles/{role_id}/permissions",
            headers=_auth_headers(admin_token),
            json={"permission_codes": ["fake:perm"]},
        )
        assert resp.status_code == 400

    def test_list_roles_includes_new_fields(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/roles",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) >= 5  # 5 system roles
        sa_role = next(r for r in data["items"] if r["code"] == "super_admin")
        assert sa_role["is_system"] is True
        assert "org_id" in sa_role
        assert "permission_codes" in sa_role
        assert "created_at" in sa_role
        assert "updated_at" in sa_role
        # Verify super_admin has all 53 permissions
        assert len(sa_role["permission_codes"]) == 53


# ═════════════════════════════════════════════════════════════════════
# T5: Organization CRUD tests
# ═════════════════════════════════════════════════════════════════════


class TestAdminOrgs:
    """T5: GET/POST/PUT/DELETE /api/v1/admin/orgs"""

    def test_list_orgs(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/orgs",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1  # default org exists
        org_ids = [o["id"] for o in data["items"]]
        assert "default" in org_ids

    def test_orgs_denied_for_user(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/orgs",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403

    def test_create_org(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/orgs",
            headers=_auth_headers(admin_token),
            json={"id": "test_org", "name": "测试组织"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "test_org"
        assert data["name"] == "测试组织"
        assert data["is_active"] is True
        assert "created_at" in data

    def test_create_org_duplicate_id(self, client, admin_token):
        # First creation
        client.post(
            "/api/v1/admin/orgs",
            headers=_auth_headers(admin_token),
            json={"id": "dup_org", "name": "Dup Org"},
        )
        # Duplicate
        resp = client.post(
            "/api/v1/admin/orgs",
            headers=_auth_headers(admin_token),
            json={"id": "dup_org", "name": "Dup Org 2"},
        )
        assert resp.status_code == 409

    def test_update_org(self, client, admin_token):
        # Create first
        client.post(
            "/api/v1/admin/orgs",
            headers=_auth_headers(admin_token),
            json={"id": "update_org", "name": "Original"},
        )
        # Update
        resp = client.put(
            "/api/v1/admin/orgs/update_org",
            headers=_auth_headers(admin_token),
            json={"name": "Renamed Org"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Renamed Org"

    def test_update_nonexistent_org(self, client, admin_token):
        resp = client.put(
            "/api/v1/admin/orgs/nonexistent",
            headers=_auth_headers(admin_token),
            json={"name": "Ghost"},
        )
        assert resp.status_code == 404

    def test_delete_org_soft(self, client, admin_token):
        # Create first
        client.post(
            "/api/v1/admin/orgs",
            headers=_auth_headers(admin_token),
            json={"id": "delete_org", "name": "To Delete"},
        )
        resp = client.delete(
            "/api/v1/admin/orgs/delete_org",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_cannot_delete_default_org(self, client, admin_token):
        resp = client.delete(
            "/api/v1/admin/orgs/default",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 400


# ═════════════════════════════════════════════════════════════════════
# T5: Department CRUD tests
# ═════════════════════════════════════════════════════════════════════


class TestAdminDepartments:
    """T5: GET/POST/PUT/DELETE /api/v1/admin/departments + reorder"""

    def test_list_departments(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/departments",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_list_departments_filtered_by_org(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/departments?org_id=default",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        # HQ should exist under default org
        dept_ids = [d["id"] for d in data["items"]]
        assert "HQ" in dept_ids

    def test_departments_denied_for_user(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/departments",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403

    def test_create_department(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/departments",
            headers=_auth_headers(admin_token),
            json={
                "id": "dev_dept",
                "org_id": "default",
                "name": "研发部",
                "parent_id": "HQ",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "dev_dept"
        assert data["name"] == "研发部"
        assert data["parent_id"] == "HQ"
        assert data["org_id"] == "default"
        # Path should include parent
        assert "HQ" in data["path"]
        assert "dev_dept" in data["path"]
        assert data["level"] >= 1

    def test_create_department_duplicate_id(self, client, admin_token):
        client.post(
            "/api/v1/admin/departments",
            headers=_auth_headers(admin_token),
            json={"id": "dup_dept", "org_id": "default", "name": "Dup Dept"},
        )
        resp = client.post(
            "/api/v1/admin/departments",
            headers=_auth_headers(admin_token),
            json={"id": "dup_dept", "org_id": "default", "name": "Dup Dept 2"},
        )
        assert resp.status_code == 409

    def test_create_department_bad_org(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/departments",
            headers=_auth_headers(admin_token),
            json={"id": "ghost_dept", "org_id": "nonexistent", "name": "Ghost"},
        )
        assert resp.status_code == 400

    def test_create_department_bad_parent(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/departments",
            headers=_auth_headers(admin_token),
            json={"id": "orphan", "org_id": "default", "name": "Orphan", "parent_id": "nonexistent"},
        )
        assert resp.status_code == 400

    def test_update_department(self, client, admin_token):
        # Create first
        client.post(
            "/api/v1/admin/departments",
            headers=_auth_headers(admin_token),
            json={"id": "update_dept", "org_id": "default", "name": "Original"},
        )
        resp = client.put(
            "/api/v1/admin/departments/update_dept",
            headers=_auth_headers(admin_token),
            json={"name": "Renamed Dept"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed Dept"

    def test_delete_department(self, client, admin_token):
        client.post(
            "/api/v1/admin/departments",
            headers=_auth_headers(admin_token),
            json={"id": "del_dept", "org_id": "default", "name": "To Delete"},
        )
        resp = client.delete(
            "/api/v1/admin/departments/del_dept",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_reorder_departments(self, client, admin_token):
        resp = client.put(
            "/api/v1/admin/departments/reorder",
            headers=_auth_headers(admin_token),
            json={"items": [{"id": "HQ", "sort_order": 100}]},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_department_tree_structure(self, client, admin_token):
        """Verify departments are returned in tree structure with children."""
        # Create parent and child
        client.post(
            "/api/v1/admin/departments",
            headers=_auth_headers(admin_token),
            json={"id": "parent_dept", "org_id": "default", "name": "Parent"},
        )
        client.post(
            "/api/v1/admin/departments",
            headers=_auth_headers(admin_token),
            json={"id": "child_dept", "org_id": "default", "name": "Child", "parent_id": "parent_dept"},
        )
        resp = client.get(
            "/api/v1/admin/departments?org_id=default",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        # Find parent_dept in the tree
        def find_dept(nodes, target_id):
            for n in nodes:
                if n["id"] == target_id:
                    return n
                result = find_dept(n.get("children", []), target_id)
                if result:
                    return result
            return None

        parent = find_dept(items, "parent_dept")
        assert parent is not None, "Parent dept should be in tree"
        assert len(parent.get("children", [])) >= 1
        child_ids = [c["id"] for c in parent["children"]]
        assert "child_dept" in child_ids


# ═════════════════════════════════════════════════════════════════════
# T5: Notice CRUD tests
# ═════════════════════════════════════════════════════════════════════


class TestAdminNotices:
    """T5: POST/PUT/DELETE /api/v1/admin/notices"""

    def test_list_notices_admin(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/notices",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_notices_admin_denied_for_user(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/notices",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403

    def test_create_notice(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/notices",
            headers=_auth_headers(admin_token),
            json={
                "title": "测试公告",
                "source": "测试来源",
                "category": "测试分类",
                "body": "这是一条测试公告内容。",
                "pinned": True,
                "published_at": "2026-08-01T10:00:00",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "测试公告"
        assert data["pinned"] is True
        assert "id" in data

    def test_update_notice(self, client, admin_token):
        # Create first
        create_resp = client.post(
            "/api/v1/admin/notices",
            headers=_auth_headers(admin_token),
            json={
                "title": "原始标题",
                "source": "来源",
                "category": "分类",
                "body": "原始内容。",
                "pinned": False,
                "published_at": "2026-08-01T10:00:00",
            },
        )
        notice_id = create_resp.json()["id"]

        resp = client.put(
            f"/api/v1/admin/notices/{notice_id}",
            headers=_auth_headers(admin_token),
            json={"title": "更新标题", "pinned": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "更新标题"
        assert data["pinned"] is True

    def test_update_nonexistent_notice(self, client, admin_token):
        resp = client.put(
            "/api/v1/admin/notices/99999",
            headers=_auth_headers(admin_token),
            json={"title": "Ghost"},
        )
        assert resp.status_code == 404

    def test_delete_notice(self, client, admin_token):
        create_resp = client.post(
            "/api/v1/admin/notices",
            headers=_auth_headers(admin_token),
            json={
                "title": "待删除",
                "source": "来源",
                "category": "分类",
                "body": "内容。",
                "pinned": False,
                "published_at": "2026-08-01T10:00:00",
            },
        )
        notice_id = create_resp.json()["id"]

        resp = client.delete(
            f"/api/v1/admin/notices/{notice_id}",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ═════════════════════════════════════════════════════════════════════
# T5: Service CRUD tests
# ═════════════════════════════════════════════════════════════════════


class TestAdminServices:
    """T5: POST/PUT/DELETE /api/v1/admin/services"""

    def test_list_services_admin(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/services",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_services_admin_denied_for_user(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/services",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403

    def test_create_service(self, client, admin_token):
        resp = client.post(
            "/api/v1/admin/services",
            headers=_auth_headers(admin_token),
            json={
                "code": "test_service",
                "title": "测试服务",
                "category": "测试分类",
                "description": "这是一个测试服务。",
                "materials": "身份证、申请表",
                "audience": "全体员工",
                "contact": "服务台",
                "status": "active",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "test_service"
        assert data["title"] == "测试服务"

    def test_create_service_duplicate_code(self, client, admin_token):
        client.post(
            "/api/v1/admin/services",
            headers=_auth_headers(admin_token),
            json={
                "code": "dup_svc",
                "title": "Dup",
                "category": "Cat",
                "description": "Desc",
                "audience": "All",
                "contact": "Contact",
            },
        )
        resp = client.post(
            "/api/v1/admin/services",
            headers=_auth_headers(admin_token),
            json={
                "code": "dup_svc",
                "title": "Dup 2",
                "category": "Cat",
                "description": "Desc",
                "audience": "All",
                "contact": "Contact",
            },
        )
        assert resp.status_code == 409

    def test_update_service(self, client, admin_token):
        client.post(
            "/api/v1/admin/services",
            headers=_auth_headers(admin_token),
            json={
                "code": "update_svc",
                "title": "Original",
                "category": "Cat",
                "description": "Desc",
                "audience": "All",
                "contact": "Contact",
            },
        )
        resp = client.put(
            "/api/v1/admin/services/update_svc",
            headers=_auth_headers(admin_token),
            json={"title": "Updated Service", "status": "inactive"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Updated Service"
        assert data["status"] == "inactive"

    def test_update_nonexistent_service(self, client, admin_token):
        resp = client.put(
            "/api/v1/admin/services/nonexistent",
            headers=_auth_headers(admin_token),
            json={"title": "Ghost"},
        )
        assert resp.status_code == 404

    def test_delete_service(self, client, admin_token):
        client.post(
            "/api/v1/admin/services",
            headers=_auth_headers(admin_token),
            json={
                "code": "del_svc",
                "title": "To Delete",
                "category": "Cat",
                "description": "Desc",
                "audience": "All",
                "contact": "Contact",
            },
        )
        resp = client.delete(
            "/api/v1/admin/services/del_svc",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ═════════════════════════════════════════════════════════════════════
# T5: Audit CSV export test
# ═════════════════════════════════════════════════════════════════════


class TestAdminAuditExport:
    """T5: GET /api/v1/admin/audit/export"""

    def test_export_csv_as_admin(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/audit/export",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/csv" in content_type
        # Should have UTF-8 BOM
        body = resp.text
        assert body.startswith("﻿")
        # Should have header row
        assert "ID," in body or "ID\r\n" in body.split("\n")[0]
        assert "Action" in body

    def test_export_csv_denied_for_user(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/audit/export",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403

    def test_export_csv_with_filters(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/audit/export",
            headers=_auth_headers(admin_token),
            params={"decision": "deny", "since": "2020-01-01T00:00:00"},
        )
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
