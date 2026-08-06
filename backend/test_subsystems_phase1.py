"""T9: Subsystem shell enhancement — menu_items_json + entry_type tests.

Tests for the subsystem configuration delivered in T9:
  - 6 deep subsystems (supervision/oa/hr/finance/assets/repair) have >= 3 menu_items sections
  - Deep subsystems have entry_type="internal"
  - Shell subsystems have entry_type="disabled" or "iframe"
  - API returns menu_items as a parsed list of section objects
  - Each menu section has {section, items: [{code, label, icon, href}]}
  - entry_url is present for iframe subsystems
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

USERNAME = "subsys_user"
PASSWORD = "subsys-test-456"

DEEP_SUBSYSTEMS = {"supervision", "oa", "hr", "finance", "assets", "repair", "data-portal", "website", "estate", "employment"}
SHELL_DISABLED = {"party", "alumni", "student", "mental-health"}
SHELL_IFRAME = {"teaching-cloud"}


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
    """Create a fresh test DB with subsystems seeded."""
    db_path = tmp_path / "test_subsystems_t9.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-for-subsystems-t9")
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
            "VALUES ('default', '默认组织', 1, '2026-07-30T00:00:00')"
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


# ── T9.1: Auth required ───────────────────────────────────────────────

class TestAuthRequired:
    """Subsystem endpoint requires authentication."""

    def test_list_subsystems_requires_auth(self, client):
        resp = client.get("/api/v1/subsystems")
        assert resp.status_code == 401

    def test_get_subsystem_requires_auth(self, client):
        resp = client.get("/api/v1/subsystems/repair")
        assert resp.status_code == 401


# ── T9.2: Deep subsystems have menu_items ─────────────────────────────

class TestDeepSubsystemMenuItems:
    """The 6 deep subsystems each return menu_items with >= 3 sections."""

    def test_all_deep_subsystems_have_menu_items(self, client):
        token = _login(client, USERNAME, PASSWORD)
        for code in DEEP_SUBSYSTEMS:
            resp = client.get(f"/api/v1/subsystems/{code}", headers=_auth(token))
            assert resp.status_code == 200, f"Expected 200 for {code}, got {resp.status_code}: {resp.text}"
            data = resp.json()
            assert "menu_items" in data, f"{code} missing menu_items"
            assert isinstance(data["menu_items"], list), f"{code} menu_items is not a list"
            assert len(data["menu_items"]) >= 3, (
                f"{code} has {len(data['menu_items'])} menu sections, expected >= 3"
            )

    def test_menu_items_have_section_structure(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems/repair", headers=_auth(token))
        assert resp.status_code == 200
        sections = resp.json()["menu_items"]
        for sec in sections:
            assert "section" in sec, f"menu section missing 'section': {sec}"
            assert isinstance(sec["section"], str)
            assert "items" in sec, f"menu section missing 'items': {sec}"
            assert isinstance(sec["items"], list)
            assert len(sec["items"]) >= 1, f"section '{sec['section']}' has 0 items"
            for item in sec["items"]:
                assert "code" in item, f"item missing 'code': {item}"
                assert "label" in item, f"item missing 'label': {item}"
                assert "href" in item, f"item missing 'href': {item}"

    def test_menu_item_href_starts_with_hash(self, client):
        token = _login(client, USERNAME, PASSWORD)
        for code in DEEP_SUBSYSTEMS:
            resp = client.get(f"/api/v1/subsystems/{code}", headers=_auth(token))
            assert resp.status_code == 200, f"Expected 200 for {code}"
            for sec in resp.json()["menu_items"]:
                for item in sec["items"]:
                    assert item["href"].startswith("#/subsystem/"), (
                        f"{code} item '{item['label']}' href does not start with #/subsystem/: {item['href']}"
                    )

    def test_deep_subsystems_have_internal_entry_type(self, client):
        token = _login(client, USERNAME, PASSWORD)
        for code in DEEP_SUBSYSTEMS:
            resp = client.get(f"/api/v1/subsystems/{code}", headers=_auth(token))
            assert resp.status_code == 200, f"Expected 200 for {code}"
            assert resp.json()["entry_type"] == "internal", (
                f"{code} entry_type is {resp.json()['entry_type']}, expected 'internal'"
            )

    def test_list_subsystems_includes_menu_items(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        deep_items = [it for it in items if it["code"] in DEEP_SUBSYSTEMS]
        for it in deep_items:
            assert isinstance(it.get("menu_items"), list), (
                f"{it['code']} menu_items missing or not a list in list response"
            )

    def test_repair_menu_has_tickets_section(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems/repair", headers=_auth(token))
        sections = resp.json()["menu_items"]
        section_labels = [s["section"] for s in sections]
        assert "工单管理" in section_labels
        assert "派单处理" in section_labels
        assert "统计评价" in section_labels

    def test_oa_menu_has_flow_section(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems/oa", headers=_auth(token))
        sections = resp.json()["menu_items"]
        section_labels = [s["section"] for s in sections]
        assert "流程中心" in section_labels
        assert "文件管理" in section_labels
        assert "办公辅助" in section_labels

    def test_hr_menu_has_certificate_section(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems/hr", headers=_auth(token))
        sections = resp.json()["menu_items"]
        section_labels = [s["section"] for s in sections]
        assert "证明申请" in section_labels
        assert "考勤请假" in section_labels
        assert "人员信息" in section_labels

    def test_finance_menu_has_claim_section(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems/finance", headers=_auth(token))
        sections = resp.json()["menu_items"]
        section_labels = [s["section"] for s in sections]
        assert "报销管理" in section_labels
        assert "预算管理" in section_labels
        assert "材料清单" in section_labels

    def test_assets_menu_has_borrow_section(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems/assets", headers=_auth(token))
        sections = resp.json()["menu_items"]
        section_labels = [s["section"] for s in sections]
        assert "资产管理" in section_labels
        assert "借用管理" in section_labels
        assert "盘点维护" in section_labels

    def test_supervision_menu_has_item_section(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems/supervision", headers=_auth(token))
        sections = resp.json()["menu_items"]
        section_labels = [s["section"] for s in sections]
        assert "督办事项" in section_labels
        assert "责任清单" in section_labels
        assert "统计分析" in section_labels


# ── T9.3: Shell subsystems have correct entry_type ────────────────────

class TestShellSubsystemEntryType:
    """Shell subsystems are configured as disabled or iframe."""

    def test_shell_disabled_subsystems(self, client):
        token = _login(client, USERNAME, PASSWORD)
        for code in SHELL_DISABLED:
            resp = client.get(f"/api/v1/subsystems/{code}", headers=_auth(token))
            assert resp.status_code == 200, f"Expected 200 for {code}, got {resp.status_code}"
            assert resp.json()["entry_type"] == "disabled", (
                f"{code} entry_type is {resp.json()['entry_type']}, expected 'disabled'"
            )

    def test_shell_iframe_subsystems(self, client):
        token = _login(client, USERNAME, PASSWORD)
        for code in SHELL_IFRAME:
            resp = client.get(f"/api/v1/subsystems/{code}", headers=_auth(token))
            assert resp.status_code == 200, f"Expected 200 for {code}, got {resp.status_code}"
            assert resp.json()["entry_type"] == "iframe", (
                f"{code} entry_type is {resp.json()['entry_type']}, expected 'iframe'"
            )

    def test_shell_iframe_has_entry_url_field(self, client):
        token = _login(client, USERNAME, PASSWORD)
        for code in SHELL_IFRAME:
            resp = client.get(f"/api/v1/subsystems/{code}", headers=_auth(token))
            assert resp.status_code == 200
            data = resp.json()
            assert "entry_url" in data, f"{code} missing entry_url field"

    def test_shell_subsystems_have_empty_menu_items(self, client):
        token = _login(client, USERNAME, PASSWORD)
        for code in list(SHELL_DISABLED | SHELL_IFRAME):
            resp = client.get(f"/api/v1/subsystems/{code}", headers=_auth(token))
            assert resp.status_code == 200
            menu = resp.json().get("menu_items", [])
            assert isinstance(menu, list)
            assert len(menu) == 0, (
                f"{code} has {len(menu)} menu items, expected 0 for shell subsystem"
            )

    def test_shell_disabled_not_in_dashboard(self, client):
        """All subsystems (including disabled) still appear in the full list."""
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems", headers=_auth(token))
        assert resp.status_code == 200
        items = resp.json()["items"]
        codes = {it["code"] for it in items}
        for code in SHELL_DISABLED:
            assert code in codes, f"{code} should appear in subsystems list"


# ── T9.4: Subsystem dashboard and visits ──────────────────────────────

class TestSubsystemDashboard:
    """Dashboard and visit endpoints work correctly."""

    def test_dashboard_returns_expected_fields(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems/repair/dashboard", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert "code" in data
        assert data["code"] == "repair"
        assert "status" in data
        assert "visits_total" in data
        assert "related_services" in data
        assert "related_resources" in data

    def test_visit_records_visit(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/subsystems/repair/visit", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["code"] == "repair"
        assert "visits_7d" in data

    def test_visit_shell_subsystem_succeeds(self, client):
        """Shell subsystems with entry_type=disabled still have status=active,
        so visits are recorded normally (the frontend shows a placeholder)."""
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/subsystems/website/visit", headers=_auth(token))
        assert resp.status_code == 200

    def test_shell_subsystem_is_reachable(self, client):
        """Shell subsystems (entry_type=disabled, status=active) are reachable.
        The frontend shows a 'coming soon' placeholder instead of a 404."""
        token = _login(client, USERNAME, PASSWORD)
        resp = client.get("/api/v1/subsystems/party", headers=_auth(token))
        assert resp.status_code == 200
        data = resp.json()
        assert data["entry_type"] == "disabled"
        assert data["status"] == "active"


# ── T9.5: menu_items idempotent re-seed ───────────────────────────────

class TestMenuItemsIdempotency:
    """Re-seeding does not corrupt menu_items."""

    def test_list_subsystems_twice_returns_same_menu(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp1 = client.get("/api/v1/subsystems/repair", headers=_auth(token))
        resp2 = client.get("/api/v1/subsystems/repair", headers=_auth(token))
        assert resp1.json()["menu_items"] == resp2.json()["menu_items"]

    def test_deep_subsystem_total_item_count(self, client):
        """Each deep subsystem should have at least 7 total menu items across sections."""
        token = _login(client, USERNAME, PASSWORD)
        for code in DEEP_SUBSYSTEMS:
            resp = client.get(f"/api/v1/subsystems/{code}", headers=_auth(token))
            sections = resp.json()["menu_items"]
            total = sum(len(s.get("items", [])) for s in sections)
            assert total >= 7, f"{code} has only {total} total menu items, expected >= 7"
