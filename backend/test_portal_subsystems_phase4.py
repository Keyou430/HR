"""Phase 4 T17: Website, Estate, Employment — CRUD + scope + stats tests."""

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

USERNAME = "p4_user"
PASSWORD = "p4-test-789"


def _alembic_config(db_path: str) -> Config:
    ini_path = str(BACKEND_ROOT / "alembic.ini")
    cfg = Config(ini_path)
    cfg.file_config.read(ini_path, encoding="utf-8")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def _upgrade(db_path: str, revision: str = "head") -> None:
    command.upgrade(_alembic_config(db_path), revision)


def _create_user(
    db_url: str,
    username: str,
    password: str,
    display_name: str,
    role_code: str = "dept_staff",
    org_id: str = "default",
    dept_id: str = "HQ",
) -> int:
    pw_hash = hash_password(password)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, display_name, is_active, "
                "token_version, must_change_password, created_at, updated_at) "
                "VALUES (:un, :pw, :dn, 1, 1, 0, '2026-08-05T00:00:00', '2026-08-05T00:00:00')"
            ),
            {"un": username, "pw": pw_hash, "dn": display_name},
        )
        uid = result.lastrowid
        conn.execute(
            text("INSERT OR IGNORE INTO user_org_memberships "
                 "(user_id, org_id, is_default, created_at) "
                 "VALUES (:uid, :oid, 1, '2026-08-05T00:00:00')"),
            {"uid": uid, "oid": org_id},
        )
        conn.execute(
            text("INSERT OR IGNORE INTO user_department_memberships "
                 "(user_id, org_id, department_id, is_primary, created_at) "
                 "VALUES (:uid, :oid, :did, 1, '2026-08-05T00:00:00')"),
            {"uid": uid, "oid": org_id, "did": dept_id},
        )
        role_row = conn.execute(
            text("SELECT id FROM roles WHERE code = :rc"), {"rc": role_code}
        ).fetchone()
        if role_row:
            conn.execute(
                text("INSERT OR IGNORE INTO role_bindings "
                     "(user_id, role_id, org_id, department_id, created_at) "
                     "VALUES (:uid, :rid, :oid, :did, '2026-08-05T00:00:00')"),
                {"uid": uid, "rid": role_row[0], "oid": org_id, "did": dept_id},
            )
    engine.dispose()
    return uid


def _login(client: TestClient, username: str, password: str) -> str:
    resp = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.json()}"
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_p4_t17.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-for-p4-t17")
    monkeypatch.setenv("AUDIT_ENABLED", "false")
    from config import get_settings
    get_settings.cache_clear()
    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    _upgrade(str(db_path), "head")

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT OR IGNORE INTO orgs (id, name, is_active, created_at) "
            "VALUES ('default', '默认组织', 1, '2026-08-05T00:00:00')"
        ))
    engine.dispose()

    _create_user(db_url, USERNAME, PASSWORD, "Test User")

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        yield c

    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    get_settings.cache_clear()


# ═══════════════════════════════════════════════════════════════════════
# Website (网站群)
# ═══════════════════════════════════════════════════════════════════════

class TestWebsiteCRUD:
    def test_create_and_list(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/enterprise/website/sites", json={
            "name": "官网", "domain": "www.example.com", "category": "宣传",
            "status": "draft", "owner_dept": "宣传办", "columns_json": "[]",
        }, headers=_auth(token))
        assert resp.status_code == 201

        resp = client.get("/api/v1/enterprise/website/sites", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        site = data["items"][0]
        assert site["name"] == "官网"

    def test_get_by_id(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/enterprise/website/sites", json={
            "name": "子站", "domain": "sub.example.com", "category": "宣传",
            "status": "published", "owner_dept": "技术部",
        }, headers=_auth(token))
        sid = resp.json()["id"]

        resp = client.get(f"/api/v1/enterprise/website/sites/{sid}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["name"] == "子站"

    def test_get_404(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/enterprise/website/sites/99999", headers=_auth(token))
        assert resp.status_code == 404

    def test_update(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/enterprise/website/sites", json={
            "name": "测试站", "category": "宣传", "status": "draft",
        }, headers=_auth(token))
        sid = resp.json()["id"]

        resp = client.patch(f"/api/v1/enterprise/website/sites/{sid}", json={
            "name": "已改名", "status": "published",
        }, headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["name"] == "已改名"

    def test_stats(self, client):
        token = _login(client, USERNAME, PASSWORD)
        client.post("/api/v1/enterprise/website/sites", json={
            "name": "站点A", "category": "宣传", "status": "published",
        }, headers=_auth(token))
        client.post("/api/v1/enterprise/website/sites", json={
            "name": "站点B", "category": "服务", "status": "draft",
        }, headers=_auth(token))

        resp = client.get("/api/v1/enterprise/website/sites/stats", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert "by_status" in data
        assert "by_category" in data


# ═══════════════════════════════════════════════════════════════════════
# Estate (房产管理)
# ═══════════════════════════════════════════════════════════════════════

class TestEstateCRUD:
    def test_create_and_list(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/enterprise/estate/spaces", json={
            "name": "101会议室", "code": "BLD-A-101", "category": "办公",
            "building": "A栋", "floor": "1F", "area_sqm": 45.5,
            "status": "vacant", "contact_person": "张三",
        }, headers=_auth(token))
        assert resp.status_code == 201

        resp = client.get("/api/v1/enterprise/estate/spaces", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        space = data["items"][0]
        assert space["code"] == "BLD-A-101"

    def test_get_by_id(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/enterprise/estate/spaces", json={
            "name": "202办公室", "code": "BLD-B-202", "category": "办公",
            "status": "occupied", "building": "B栋", "floor": "2F",
        }, headers=_auth(token))
        sid = resp.json()["id"]

        resp = client.get(f"/api/v1/enterprise/estate/spaces/{sid}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["name"] == "202办公室"

    def test_get_404(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/enterprise/estate/spaces/99999", headers=_auth(token))
        assert resp.status_code == 404

    def test_update(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/enterprise/estate/spaces", json={
            "name": "原空间", "code": "OLD-001", "category": "办公", "status": "vacant",
        }, headers=_auth(token))
        sid = resp.json()["id"]

        resp = client.patch(f"/api/v1/enterprise/estate/spaces/{sid}", json={
            "name": "新空间", "status": "occupied",
        }, headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["name"] == "新空间"

    def test_stats(self, client):
        token = _login(client, USERNAME, PASSWORD)
        client.post("/api/v1/enterprise/estate/spaces", json={
            "name": "空间1", "code": "S1", "category": "教学", "status": "vacant",
        }, headers=_auth(token))
        client.post("/api/v1/enterprise/estate/spaces", json={
            "name": "空间2", "code": "S2", "category": "办公", "status": "occupied",
        }, headers=_auth(token))

        resp = client.get("/api/v1/enterprise/estate/spaces/stats", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert "by_category" in data
        assert "by_status" in data


# ═══════════════════════════════════════════════════════════════════════
# Employment (就业系统)
# ═══════════════════════════════════════════════════════════════════════

class TestEmploymentCRUD:
    def test_create_and_list(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/enterprise/employment/postings", json={
            "title": "前端工程师", "company_name": "示例科技",
            "position_category": "技术", "salary_range": "15k-25k",
            "location": "北京", "status": "open",
        }, headers=_auth(token))
        assert resp.status_code == 201

        resp = client.get("/api/v1/enterprise/employment/postings", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        posting = data["items"][0]
        assert posting["title"] == "前端工程师"

    def test_get_by_id(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/enterprise/employment/postings", json={
            "title": "HR经理", "company_name": "示例集团",
            "position_category": "行政", "location": "上海", "status": "open",
        }, headers=_auth(token))
        pid = resp.json()["id"]

        resp = client.get(f"/api/v1/enterprise/employment/postings/{pid}", headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["title"] == "HR经理"

    def test_get_404(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/enterprise/employment/postings/99999", headers=_auth(token))
        assert resp.status_code == 404

    def test_update(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/enterprise/employment/postings", json={
            "title": "旧岗位", "company_name": "旧公司",
            "position_category": "销售", "status": "open",
        }, headers=_auth(token))
        pid = resp.json()["id"]

        resp = client.patch(f"/api/v1/enterprise/employment/postings/{pid}", json={
            "title": "新岗位", "status": "closed",
        }, headers=_auth(token))
        assert resp.status_code == 200
        assert resp.json()["title"] == "新岗位"

    def test_stats(self, client):
        token = _login(client, USERNAME, PASSWORD)
        client.post("/api/v1/enterprise/employment/postings", json={
            "title": "P1", "company_name": "A", "position_category": "技术", "status": "open",
        }, headers=_auth(token))
        client.post("/api/v1/enterprise/employment/postings", json={
            "title": "P2", "company_name": "B", "position_category": "行政", "status": "closed",
        }, headers=_auth(token))

        resp = client.get("/api/v1/enterprise/employment/postings/stats", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert "by_category" in data
        assert "by_status" in data


# ═══════════════════════════════════════════════════════════════════════
# Auth required
# ═══════════════════════════════════════════════════════════════════════

class TestAuthRequired:
    routes = [
        ("GET", "/api/v1/enterprise/website/sites"),
        ("GET", "/api/v1/enterprise/website/sites/stats"),
        ("POST", "/api/v1/enterprise/website/sites"),
        ("GET", "/api/v1/enterprise/estate/spaces"),
        ("GET", "/api/v1/enterprise/estate/spaces/stats"),
        ("POST", "/api/v1/enterprise/estate/spaces"),
        ("GET", "/api/v1/enterprise/employment/postings"),
        ("GET", "/api/v1/enterprise/employment/postings/stats"),
        ("POST", "/api/v1/enterprise/employment/postings"),
    ]

    @pytest.mark.parametrize("method, path", routes)
    def test_401_without_token(self, client, method, path):
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json={})
        assert resp.status_code == 401, f"{method} {path} expected 401, got {resp.status_code}"
