"""T8: Search enhancement tests — repair/asset/OA sources, limit, scope isolation.

Tests the enhanced GET /api/v1/search endpoint:
  - Auth required (search:view permission)
  - Returns results from repair, asset, OA, portal sources
  - Limit parameter is respected
  - Cross-org isolation (user in org B doesn't see org A data)
  - Match by asset_code, title, location, flow_type
  - Empty query returns items (up to limit)
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

USER_A = "search_user_a"
PASS_A = "search-a-123"
USER_B = "search_user_b"
PASS_B = "search-b-123"


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
                "VALUES (:un, :pw, :dn, 1, 1, 0, '2026-07-30T00:00:00', '2026-07-30T00:00:00')"
            ),
            {"un": username, "pw": pw_hash, "dn": display_name},
        )
        uid = result.lastrowid
        conn.execute(
            text("INSERT OR IGNORE INTO user_org_memberships "
                 "(user_id, org_id, is_default, created_at) "
                 "VALUES (:uid, :oid, 1, '2026-07-30T00:00:00')"),
            {"uid": uid, "oid": org_id},
        )
        conn.execute(
            text("INSERT OR IGNORE INTO user_department_memberships "
                 "(user_id, org_id, department_id, is_primary, created_at) "
                 "VALUES (:uid, :oid, :did, 1, '2026-07-30T00:00:00')"),
            {"uid": uid, "oid": org_id, "did": dept_id},
        )
        role_row = conn.execute(
            text("SELECT id FROM roles WHERE code = :rc"), {"rc": role_code}
        ).fetchone()
        if role_row:
            conn.execute(
                text("INSERT OR IGNORE INTO role_bindings "
                     "(user_id, role_id, org_id, department_id, created_at) "
                     "VALUES (:uid, :rid, :oid, :did, '2026-07-30T00:00:00')"),
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
    """Create a fresh test DB with two users in different orgs.

    Seeds repair tickets, asset items, and OA flows for both orgs.
    """
    db_path = tmp_path / "test_search.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-for-search-phase1")
    monkeypatch.setenv("AUDIT_ENABLED", "false")
    from config import get_settings
    get_settings.cache_clear()
    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    _upgrade(str(db_path), "head")

    # Ensure both orgs exist
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT OR IGNORE INTO orgs (id, name, is_active, created_at) "
            "VALUES ('default', '默认组织', 1, '2026-07-30T00:00:00')"
        ))
        conn.execute(text(
            "INSERT OR IGNORE INTO orgs (id, name, is_active, created_at) "
            "VALUES ('org_b', 'B组织', 1, '2026-07-30T00:00:00')"
        ))
    engine.dispose()

    uid_a = _create_user(db_url, USER_A, PASS_A, "User A", org_id="default", dept_id="HQ")
    uid_b = _create_user(db_url, USER_B, PASS_B, "User B", org_id="org_b", dept_id="HQ")

    from auth.router import _login_attempts
    _login_attempts.clear()

    # Seed repair/asset/OA data via store for org-scoped visibility
    from store import store

    # --- Org "default" data (visible to User A) ---
    store.create_repair_ticket({
        "title": "Default空调故障", "location": "A栋301",
        "description": "空调漏水", "priority": "high", "status": "submitted",
        "org_id": "default", "department_id": "HQ",
    }, user={"id": uid_a, "org_id": "default", "department_id": "HQ"})
    store.create_repair_ticket({
        "title": "Default网络中断", "location": "B栋202",
        "description": "交换机故障", "priority": "normal", "status": "processing",
        "org_id": "default", "department_id": "HQ",
    }, user={"id": uid_a, "org_id": "default", "department_id": "HQ"})

    store.create_asset_item({
        "asset_code": "AS-DEF-001", "name": "Default投影仪",
        "category": "办公设备", "location": "default仓库",
        "status": "available",
        "org_id": "default", "department_id": "HQ",
    }, user={"id": uid_a, "org_id": "default", "department_id": "HQ"})
    store.create_asset_item({
        "asset_code": "AS-DEF-002", "name": "Default工作站",
        "category": "信息设备", "location": "default机房",
        "status": "in_use",
        "org_id": "default", "department_id": "HQ",
    }, user={"id": uid_a, "org_id": "default", "department_id": "HQ"})

    store.create_oa_flow({
        "title": "Default用印申请", "flow_type": "用印申请",
        "status": "pending",
        "org_id": "default", "department_id": "HQ",
    }, user={"id": uid_a, "org_id": "default", "department_id": "HQ"})
    store.create_oa_flow({
        "title": "Default采购审批", "flow_type": "采购申请",
        "status": "approved",
        "org_id": "default", "department_id": "HQ",
    }, user={"id": uid_a, "org_id": "default", "department_id": "HQ"})

    # --- Org "org_b" data (visible to User B only) ---
    store.create_repair_ticket({
        "title": "OrgB灯管更换", "location": "C栋101",
        "description": "灯管损坏", "priority": "low", "status": "submitted",
        "org_id": "org_b", "department_id": "HQ",
    }, user={"id": uid_b, "org_id": "org_b", "department_id": "HQ"})

    store.create_asset_item({
        "asset_code": "AS-ORGB-001", "name": "OrgB服务器",
        "category": "信息设备", "location": "org_b机房",
        "status": "available",
        "org_id": "org_b", "department_id": "HQ",
    }, user={"id": uid_b, "org_id": "org_b", "department_id": "HQ"})

    store.create_oa_flow({
        "title": "OrgB请假申请", "flow_type": "请假申请",
        "status": "pending",
        "org_id": "org_b", "department_id": "HQ",
    }, user={"id": uid_b, "org_id": "org_b", "department_id": "HQ"})

    with TestClient(app, cookies={}) as c:
        yield c

    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    get_settings.cache_clear()


# ── T8.1: Auth required ─────────────────────────────────────────────────

class TestAuthRequired:
    """Search endpoint requires authentication + search:view permission."""

    def test_search_requires_auth(self, client):
        resp = client.get("/api/v1/search?q=test")
        assert resp.status_code == 401


# ── T8.2: Search across sources ─────────────────────────────────────────

class TestSearchAcrossSources:
    """Search returns results from repair, asset, OA, and portal sources."""

    def test_search_finds_repair_by_title(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=空调", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        titles = [it["title"] for it in items]
        assert any("空调" in t for t in titles)

    def test_search_finds_repair_by_location(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=B栋202", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        subtitles = [it.get("subtitle", "") for it in items]
        assert any("B栋202" in s for s in subtitles)

    def test_search_finds_asset_by_name(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=投影仪", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        titles = [it["title"] for it in items]
        assert any("投影仪" in t for t in titles)

    def test_search_finds_asset_by_code(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=AS-DEF-001", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        titles = [it["title"] for it in items]
        assert any("AS-DEF-001" in t for t in titles)

    def test_search_finds_asset_by_category(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=办公设备", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        subtitles = [it.get("subtitle", "") for it in items]
        assert any("办公设备" in s for s in subtitles)

    def test_search_finds_oa_by_title(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=用印申请", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        titles = [it["title"] for it in items]
        assert any("用印申请" in t for t in titles)

    def test_search_finds_oa_by_flow_type(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=采购", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        found = False
        for it in items:
            if "采购" in (it.get("title", "") + it.get("subtitle", "")):
                found = True
                break
        assert found

    def test_result_has_expected_fields(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=空调", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) > 0
        item = items[0]
        assert "type" in item
        assert "title" in item
        assert "subtitle" in item
        assert "href" in item
        assert "status" in item


# ── T8.3: Limit parameter ───────────────────────────────────────────────

class TestLimit:
    """The limit parameter is respected and clamped to [1, 50]."""

    def test_limit_respected(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=&limit=3", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) <= 3

    def test_limit_default_is_20(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) <= 20

    def test_limit_clamped_at_50(self, client):
        """limit > 50 is clamped server-side (FastAPI rejects >50 with 422, store clamps internally)."""
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=&limit=100", headers=_auth(token))
        # FastAPI Query(le=50) returns 422 for out-of-range values
        assert resp.status_code in (200, 422)
        if resp.status_code == 200:
            items = resp.json()["items"]
            assert len(items) <= 50


# ── T8.4: Cross-org isolation ───────────────────────────────────────────

class TestCrossOrgIsolation:
    """Users in different orgs cannot see each other's data."""

    def test_user_a_cannot_see_org_b_repair(self, client):
        token_a = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=灯管", headers=_auth(token_a))
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 0

    def test_user_a_cannot_see_org_b_asset(self, client):
        token_a = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=OrgB", headers=_auth(token_a))
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 0

    def test_user_a_cannot_see_org_b_oa(self, client):
        token_a = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=OrgB请假", headers=_auth(token_a))
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 0

    def test_user_b_sees_only_own_org_data(self, client):
        token_b = _login(client, USER_B, PASS_B)
        resp = client.get("/api/v1/search?q=", headers=_auth(token_b))
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            if item["type"] in ("repair", "asset", "oa"):
                assert "Default" not in item.get("title", "")


# ── T8.5: Empty query ───────────────────────────────────────────────────

class TestEmptyQuery:
    """Empty query returns all sources up to limit."""

    def test_empty_query_returns_items(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    def test_empty_query_results_have_types(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=", headers=_auth(token))
        items = resp.json()["items"]
        types = {it["type"] for it in items}
        expected_types = {"repair", "asset", "oa", "subsystem", "notice", "document", "resource", "service", "news"}
        assert len(types & expected_types) >= 2


# ── T8.6: Status field present on enterprise items ──────────────────────

class TestStatusField:
    """Repair/asset/OA results include a status field for badge rendering."""

    def test_repair_result_has_status(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=空调", headers=_auth(token))
        items = resp.json()["items"]
        repair_items = [it for it in items if it["type"] == "repair"]
        assert len(repair_items) > 0
        for item in repair_items:
            assert item["status"] in ("submitted", "processing", "completed", "closed")

    def test_asset_result_has_status(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=投影仪", headers=_auth(token))
        items = resp.json()["items"]
        asset_items = [it for it in items if it["type"] == "asset"]
        assert len(asset_items) > 0
        for item in asset_items:
            assert item["status"] in ("available", "in_use", "borrowed", "maintenance")

    def test_oa_result_has_status(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=用印申请", headers=_auth(token))
        items = resp.json()["items"]
        oa_items = [it for it in items if it["type"] == "oa"]
        assert len(oa_items) > 0
        for item in oa_items:
            assert item["status"] in ("pending", "processing", "approved", "rejected")

    def test_repair_result_has_href(self, client):
        token = _login(client, USER_A, PASS_A)
        resp = client.get("/api/v1/search?q=空调", headers=_auth(token))
        items = resp.json()["items"]
        repair_items = [it for it in items if it["type"] == "repair"]
        assert len(repair_items) > 0
        for item in repair_items:
            assert item["href"].startswith("#/subsystem/repair/")
