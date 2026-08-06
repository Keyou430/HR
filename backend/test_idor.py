"""Phase 4: IDOR (Insecure Direct Object Reference) prevention tests.

Verifies that:
- User A cannot PATCH/DELETE User B's private resources
- User A cannot PATCH/DELETE resources outside their data scope
- Cross-dept IDOR is prevented
- Cross-org IDOR is prevented
- Nonexistent and unauthorized resources produce uniform 404 responses
- External users cannot mutate resources
- Knowledge mapping IDOR is prevented

Reuses the scope_db fixture from test_data_scope.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import app


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════


def _login(client: TestClient, username: str, password: str) -> str:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, f"Login failed for {username}: {resp.json()}"
    return resp.json()["access_token"]


# ═══════════════════════════════════════════════════════════════════
# Fixture — same as test_data_scope.py
# ═══════════════════════════════════════════════════════════════════


def _alembic_config(db_path: str):
    from alembic.config import Config
    ini_path = str(BACKEND_ROOT / "alembic.ini")
    cfg = Config(ini_path)
    cfg.file_config.read(ini_path, encoding="utf-8")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def _upgrade(db_path: str) -> None:
    from alembic import command
    command.upgrade(_alembic_config(db_path), "head")


@pytest.fixture
def idor_db(tmp_path, monkeypatch):
    """Multi-user DB with test resources for IDOR testing."""
    db_path = tmp_path / "test_idor.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-idor-secret-key-min-32charsok")
    monkeypatch.setenv("FASTGPT_MODE", "mock")
    monkeypatch.setenv("HERMES_MODE", "mock")
    from config import get_settings
    get_settings.cache_clear()

    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None

    _upgrade(str(db_path))

    from auth.router import _login_attempts
    _login_attempts.clear()

    from auth.password import hash_password
    from sqlalchemy import create_engine, text

    engine = create_engine(db_url)

    # Create org2
    with engine.begin() as conn:
        conn.execute(
            text("INSERT OR IGNORE INTO orgs (id, name, is_active, created_at, updated_at) "
                 "VALUES ('org2', '第二组织', 1, '2026-07-30T00:00:00', '2026-07-30T00:00:00')")
        )
        conn.execute(
            text("INSERT OR IGNORE INTO departments (id, org_id, name, parent_id, path, level, "
                 "sort_order, is_active, created_at, updated_at) "
                 "VALUES ('Engineering', 'default', '工程部', 'HQ', 'HQ/Engineering', 1, "
                 "1, 1, '2026-07-30T00:00:00', '2026-07-30T00:00:00')")
        )
        conn.execute(
            text("INSERT OR IGNORE INTO departments (id, org_id, name, parent_id, path, level, "
                 "sort_order, is_active, created_at, updated_at) "
                 "VALUES ('Org2HQ', 'org2', '组织二总部', NULL, 'Org2HQ', 0, "
                 "0, 1, '2026-07-30T00:00:00', '2026-07-30T00:00:00')")
        )

    def _make_user(username: str, org_id: str, dept_id: str, role_code: str) -> int:
        pw_hash = hash_password("test12345678")
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO users (username, password_hash, display_name, is_active, "
                    "token_version, must_change_password, created_at, updated_at) "
                    "VALUES (:un, :pw, :dn, 1, 1, 0, '2026-07-30T00:00:00', '2026-07-30T00:00:00')"
                ),
                {"un": username, "pw": pw_hash, "dn": username},
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
        return uid

    alice_id = _make_user("alice", "default", "HQ", "dept_staff")
    bob_id = _make_user("bob", "default", "HQ", "dept_staff")
    charlie_id = _make_user("charlie", "default", "Engineering", "dept_leader")
    dave_id = _make_user("dave", "org2", "Org2HQ", "org_admin")
    eve_id = _make_user("eve", "default", "HQ", "external")
    super_id = _make_user("super_test", "default", "HQ", "super_admin")

    # Seed tasks with different ownership
    task_ids = {}
    def _add_task(owner_id: int, title: str, visibility: str, org_id="default",
                  dept_id="HQ", sensitivity="normal") -> int:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO portal_tasks (title, tag, deadline, done, "
                    "org_id, department_id, owner_id, visibility, sensitivity) "
                    "VALUES (:title, '今天', NULL, 0, :org, :dept, :owner, :vis, :sens)"
                ),
                {"title": title, "org": org_id, "dept": dept_id,
                 "owner": owner_id, "vis": visibility, "sens": sensitivity},
            )
            return int(result.lastrowid)

    task_ids["alice_private"] = _add_task(alice_id, "Alice Private Task", "private")
    task_ids["alice_dept"] = _add_task(alice_id, "Alice Dept Task", "dept")
    task_ids["alice_org"] = _add_task(alice_id, "Alice Org Task", "org")
    task_ids["alice_public"] = _add_task(alice_id, "Alice Public Task", "public")
    task_ids["charlie_dept"] = _add_task(charlie_id, "Charlie Dept Task", "dept", dept_id="Engineering")
    task_ids["dave_org"] = _add_task(dave_id, "Dave Org Task", "org", org_id="org2", dept_id="Org2HQ")

    # Seed events
    event_ids = {}
    def _add_event(owner_id: int, title: str, visibility: str, org_id="default",
                   dept_id="HQ", sensitivity="normal") -> int:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "INSERT INTO portal_calendar_events (date, title, tone, "
                    "org_id, department_id, owner_id, visibility, sensitivity) "
                    "VALUES ('2026-08-01', :title, 'blue', :org, :dept, :owner, :vis, :sens)"
                ),
                {"title": title, "org": org_id, "dept": dept_id,
                 "owner": owner_id, "vis": visibility, "sens": sensitivity},
            )
            return int(result.lastrowid)

    event_ids["alice_private"] = _add_event(alice_id, "Alice Private Event", "private")
    event_ids["dave_org"] = _add_event(dave_id, "Dave Org Event", "org", org_id="org2", dept_id="Org2HQ")

    # Seed knowledge mappings
    with engine.begin() as conn:
        for mid, name, vis, sens, oid in [
            ("dataset:private_ds", "Private DS", "private", "normal", alice_id),
            ("dataset:org_ds", "Org DS", "org", "internal", 1),
            ("dataset:public_ds", "Public DS", "public", "normal", 1),
        ]:
            conn.execute(
                text(
                    "INSERT INTO knowledge_dataset_mappings "
                    "(id, resource_type, resource_id, display_name, permission_scope, "
                    "enabled, is_default_import_target, last_synced_at, "
                    "stale, updated_at, org_id, department_id, owner_id, visibility, sensitivity) "
                    "VALUES (:id, 'dataset', :rid, :dn, 'team', 1, 0, '2026-07-30T00:00:00', "
                    "0, '2026-07-30T00:00:00', :org_id, 'HQ', :owner, :vis, :sens)"
                ),
                {"id": mid, "rid": mid.split(":", 1)[1], "dn": name,
                 "org_id": "default", "owner": oid, "vis": vis, "sens": sens},
            )

    engine.dispose()

    users = {
        "alice": ("alice", "test12345678"),
        "bob": ("bob", "test12345678"),
        "charlie": ("charlie", "test12345678"),
        "dave": ("dave", "test12345678"),
        "eve": ("eve", "test12345678"),
        "super": ("super_test", "test12345678"),
    }

    yield {
        "users": users,
        "user_ids": {"alice": alice_id, "bob": bob_id, "charlie": charlie_id,
                     "dave": dave_id, "eve": eve_id, "super": super_id},
        "task_ids": task_ids,
        "event_ids": event_ids,
    }

    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    get_settings.cache_clear()


@pytest.fixture
def client(idor_db, monkeypatch):
    with TestClient(app, cookies={}) as c:
        yield c


@pytest.fixture
def tokens(client, idor_db) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, (username, password) in idor_db["users"].items():
        result[name] = _login(client, username, password)
    return result


# ═══════════════════════════════════════════════════════════════════
# 1. Task IDOR — User A cannot mutate User B's private tasks
# ═══════════════════════════════════════════════════════════════════


def test_cannot_patch_other_private_task(client, tokens, idor_db):
    """Bob cannot PATCH Alice's private task."""
    task_id = idor_db["task_ids"]["alice_private"]
    resp = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Hacked by Bob"},
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp.status_code == 404, (
        f"Bob got {resp.status_code}, expected 404 (uniform for nonexistent/unauthorized)"
    )


def test_cannot_delete_other_private_task(client, tokens, idor_db):
    """Bob cannot DELETE Alice's private task."""
    task_id = idor_db["task_ids"]["alice_private"]
    resp = client.delete(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp.status_code == 404


def test_can_mutate_own_task(client, tokens, idor_db):
    """Alice CAN patch and delete her own private task."""
    # Create a new task owned by Alice first
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "Alice own task", "tag": "今天"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    # Patch
    resp = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Alice updated task"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Alice updated task"

    # Delete
    resp = client.delete(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_cannot_patch_across_dept(client, tokens, idor_db):
    """Charlie (Engineering) cannot PATCH Bob's private task (HQ)."""
    # First, Bob creates a private task
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "Bob private task", "tag": "今天"},
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    # Charlie tries to patch it
    resp = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Hacked by Charlie"},
        headers={"Authorization": f"Bearer {tokens['charlie']}"},
    )
    assert resp.status_code == 404, f"Charlie got {resp.status_code}, expected 404"


def test_cannot_patch_across_org(client, tokens, idor_db):
    """Dave (org2) cannot PATCH Alice's private task (default org)."""
    task_id = idor_db["task_ids"]["alice_private"]
    resp = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Hacked by Dave"},
        headers={"Authorization": f"Bearer {tokens['dave']}"},
    )
    assert resp.status_code == 404


def test_cannot_delete_across_org(client, tokens, idor_db):
    """Dave (org2) cannot DELETE Alice's org task (default org)."""
    task_id = idor_db["task_ids"]["alice_org"]
    resp = client.delete(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {tokens['dave']}"},
    )
    assert resp.status_code == 404


def test_external_cannot_mutate_anything(client, tokens, idor_db):
    """Eve (external) cannot create, patch, or delete tasks."""
    # External has task:view but not task:create/update/delete (Phase 3)
    task_id = idor_db["task_ids"]["alice_public"]

    # Cannot create (403 — missing task:create)
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "Eve task", "tag": "今天"},
        headers={"Authorization": f"Bearer {tokens['eve']}"},
    )
    assert resp.status_code == 403

    # Cannot patch (403 — missing task:update)
    resp = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Hacked by Eve"},
        headers={"Authorization": f"Bearer {tokens['eve']}"},
    )
    assert resp.status_code == 403

    # Cannot delete (403 — missing task:delete)
    resp = client.delete(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {tokens['eve']}"},
    )
    assert resp.status_code == 403


def test_super_admin_can_mutate_anything(client, tokens, idor_db):
    """Super admin can patch and delete any task."""
    task_id = idor_db["task_ids"]["alice_private"]

    # Patch
    resp = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Updated by super admin"},
        headers={"Authorization": f"Bearer {tokens['super']}"},
    )
    assert resp.status_code == 200

    # Delete
    resp = client.delete(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {tokens['super']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ═══════════════════════════════════════════════════════════════════
# 2. Calendar Event IDOR
# ═══════════════════════════════════════════════════════════════════


def test_cannot_patch_other_private_event(client, tokens, idor_db):
    """Bob cannot PATCH Alice's private calendar event."""
    event_id = idor_db["event_ids"]["alice_private"]
    resp = client.put(
        f"/api/v1/calendar/events/{event_id}",
        json={"title": "Hacked Event", "date": "2026-08-01", "tone": "blue"},
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp.status_code == 404


def test_cannot_delete_other_private_event(client, tokens, idor_db):
    """Bob cannot DELETE Alice's private calendar event."""
    event_id = idor_db["event_ids"]["alice_private"]
    resp = client.delete(
        f"/api/v1/calendar/events/{event_id}",
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp.status_code == 404


def test_cannot_access_cross_org_event(client, tokens, idor_db):
    """Alice cannot PATCH Dave's org2 event."""
    event_id = idor_db["event_ids"]["dave_org"]
    resp = client.put(
        f"/api/v1/calendar/events/{event_id}",
        json={"title": "Hacked Org2 Event", "date": "2026-08-01", "tone": "blue"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# 3. Knowledge Mapping IDOR
# ═══════════════════════════════════════════════════════════════════


def test_cannot_patch_private_knowledge_mapping(client, tokens, idor_db):
    """Bob cannot PATCH Alice's private knowledge mapping."""
    # Bob (dept_staff) has kb:update via phase 3 permissions? Let's check.
    # Actually dept_staff does NOT have kb:update. So Bob gets 403.
    # charlie (dept_leader) has kb:update but shouldn't see Alice's private mapping.
    resp = client.patch(
        "/api/v1/knowledge/mappings/dataset:private_ds",
        json={"display_name": "Hacked DS"},
        headers={"Authorization": f"Bearer {tokens['charlie']}"},
    )
    assert resp.status_code == 404, (
        f"Charlie got {resp.status_code}, expected 404 for private mapping"
    )


def test_cannot_delete_private_knowledge_mapping(client, tokens, idor_db):
    """Bob cannot DELETE Alice's private knowledge mapping."""
    # charlie (dept_leader) does NOT have kb:delete. So gets 403.
    # But let's test with someone who has kb:delete but shouldn't see the mapping.
    # org_admin has kb:delete but is in org2, not default.
    resp = client.delete(
        "/api/v1/knowledge/mappings/dataset:private_ds",
        headers={"Authorization": f"Bearer {tokens['dave']}"},
    )
    # Dave has kb:delete (org_admin) but is in org2. Private mapping is in default org.
    # Dave's org scope doesn't include default org, so 404.
    assert resp.status_code == 404, f"Dave got {resp.status_code}, expected 404"


def test_super_admin_can_manage_any_mapping(client, tokens, idor_db):
    """Super admin can patch/delete any knowledge mapping."""
    # Patch
    resp = client.patch(
        "/api/v1/knowledge/mappings/dataset:private_ds",
        json={"display_name": "Updated by Super Admin"},
        headers={"Authorization": f"Bearer {tokens['super']}"},
    )
    assert resp.status_code == 200

    # Delete
    resp = client.delete(
        "/api/v1/knowledge/mappings/dataset:private_ds",
        headers={"Authorization": f"Bearer {tokens['super']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ═══════════════════════════════════════════════════════════════════
# 4. Uniform 404 for nonexistent vs unauthorized
# ═══════════════════════════════════════════════════════════════════


def test_uniform_404_task(client, tokens, idor_db):
    """Nonexistent task and unauthorized task both return 404 (no ID enumeration)."""
    # Nonexistent task
    resp = client.get(
        "/api/v1/tasks/999999",
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    # GET /tasks/{id} doesn't exist as a separate endpoint — tasks are listed.
    # Let's test via PATCH on a nonexistent task vs unauthorized task.
    resp_nonexistent = client.patch(
        "/api/v1/tasks/999999",
        json={"title": "x"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    resp_unauthorized = client.patch(
        f"/api/v1/tasks/{idor_db['task_ids']['alice_private']}",
        json={"title": "x"},
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp_nonexistent.status_code == 404
    assert resp_unauthorized.status_code == 404
    # Both responses should not reveal whether the resource exists
    assert "not found" in resp_nonexistent.json()["detail"].lower()
    assert "not found" in resp_unauthorized.json()["detail"].lower()


def test_uniform_404_event(client, tokens, idor_db):
    """Nonexistent and unauthorized events both return 404."""
    resp_nonexistent = client.put(
        "/api/v1/calendar/events/999999",
        json={"title": "x", "date": "2026-08-01", "tone": "blue"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    resp_unauthorized = client.put(
        f"/api/v1/calendar/events/{idor_db['event_ids']['alice_private']}",
        json={"title": "x", "date": "2026-08-01", "tone": "blue"},
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp_nonexistent.status_code == 404
    assert resp_unauthorized.status_code == 404


def test_uniform_404_knowledge_mapping(client, tokens, idor_db):
    """Nonexistent and unauthorized knowledge mappings both return 404.

    Uses Charlie (dept_leader, has kb:update) who is in Engineering dept.
    Alice's private mapping is in HQ dept — different scope.
    """
    resp_nonexistent = client.patch(
        "/api/v1/knowledge/mappings/nonexistent:id",
        json={"display_name": "x"},
        headers={"Authorization": f"Bearer {tokens['super']}"},
    )
    # Charlie has kb:update (dept_leader) but is in Engineering.
    # Alice's private mapping is in HQ — outside Charlie's scope.
    resp_unauthorized = client.patch(
        "/api/v1/knowledge/mappings/dataset:private_ds",
        json={"display_name": "x"},
        headers={"Authorization": f"Bearer {tokens['charlie']}"},
    )
    assert resp_nonexistent.status_code == 404
    assert resp_unauthorized.status_code == 404, (
        f"Charlie got {resp_unauthorized.status_code}, expected 404 "
        f"(private mapping outside his dept scope)"
    )


# ═══════════════════════════════════════════════════════════════════
# 5. IDOR via ID guessing
# ═══════════════════════════════════════════════════════════════════


def test_cannot_guess_task_id(client, tokens, idor_db):
    """Bob cannot access Alice's private task by guessing the ID."""
    task_id = idor_db["task_ids"]["alice_private"]

    # Direct PATCH
    resp = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"done": True},
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp.status_code == 404

    # Verify the task was NOT modified
    # Alice should still see the original title
    resp = client.get(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    tasks = {t["title"]: t for t in resp.json()["items"]}
    private_task = tasks.get("Alice Private Task")
    assert private_task is not None, "Alice's private task should still exist"
    assert private_task["done"] is False, "Task should not have been modified"


def test_cannot_guess_event_id(client, tokens, idor_db):
    """Bob cannot delete Alice's private event by guessing the ID."""
    event_id = idor_db["event_ids"]["alice_private"]

    resp = client.delete(
        f"/api/v1/calendar/events/{event_id}",
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp.status_code == 404

    # Verify the event still exists for Alice
    resp = client.get(
        "/api/v1/calendar/events",
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    events = {e["title"]: e for e in resp.json()["items"]}
    assert "Alice Private Event" in events, "Alice's private event should still exist"


# ═══════════════════════════════════════════════════════════════════
# 6. Task create ownership is correctly set
# ═══════════════════════════════════════════════════════════════════


def test_created_task_has_correct_owner(client, tokens, idor_db):
    """A task created by Alice has Alice as the owner."""
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "Alice new owned task", "tag": "今天"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 201
    task = resp.json()
    # The response doesn't include owner_id (it's not in the response schema)
    # but we can verify that Alice sees it and Bob doesn't (since visibility defaults to private)
    task_id = task["id"]

    # Alice sees it
    resp = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {tokens['alice']}"})
    titles = [t["title"] for t in resp.json()["items"]]
    assert "Alice new owned task" in titles

    # Bob does NOT see it (private by default)
    resp = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {tokens['bob']}"})
    titles = [t["title"] for t in resp.json()["items"]]
    assert "Alice new owned task" not in titles


def test_created_event_has_correct_owner(client, tokens, idor_db):
    """A calendar event created by Alice is scoped correctly."""
    resp = client.post(
        "/api/v1/calendar/events",
        json={"title": "Alice new event", "date": "2026-08-15", "tone": "blue"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 201

    # Bob doesn't see it
    resp = client.get("/api/v1/calendar/events", headers={"Authorization": f"Bearer {tokens['bob']}"})
    titles = [e["title"] for e in resp.json()["items"]]
    assert "Alice new event" not in titles


# ═══════════════════════════════════════════════════════════════════
# 7. Dept-scoped task — same-dept user can mutate
# ═══════════════════════════════════════════════════════════════════


def test_same_dept_user_can_mutate_dept_scoped_task(client, tokens, idor_db):
    """Bob (same dept) CAN update Alice's dept-scoped task."""
    task_id = idor_db["task_ids"]["alice_dept"]
    resp = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "Updated by Bob (same dept)"},
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    # Bob is in HQ, task is dept-scoped to HQ → Bob should be able to update
    assert resp.status_code == 200, (
        f"Bob (same dept) should be able to update dept-scoped task. Got {resp.status_code}"
    )
    assert resp.json()["title"] == "Updated by Bob (same dept)"


def test_other_dept_user_cannot_mutate_dept_scoped_task(client, tokens, idor_db):
    """Charlie (Engineering) cannot update Bob's dept-scoped task (HQ)."""
    # Create a dept-scoped task for Bob in HQ
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "Bob HQ Dept Task", "tag": "今天"},
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    # But this task is private (default visibility). Let me check...
    # Actually, create_task sets visibility to "private" by default.
    # To test dept scope, we'd need to change the visibility.
    # The store.create_task always uses "private" as default for user-created tasks.
    # This is the correct behavior — user-created tasks default to private.
    # For dept-scoped testing, we use the pre-seeded tasks.

    # Charlie tries to update Alice's dept-scoped task (HQ) — Charlie is in Engineering
    task_id_alice = idor_db["task_ids"]["alice_dept"]
    resp = client.patch(
        f"/api/v1/tasks/{task_id_alice}",
        json={"title": "Hacked by Charlie"},
        headers={"Authorization": f"Bearer {tokens['charlie']}"},
    )
    assert resp.status_code == 404, (
        f"Charlie (Engineering) should NOT update HQ dept task. Got {resp.status_code}"
    )


# ═══════════════════════════════════════════════════════════════════
# 8. Defence-in-depth: extra JSON fields cannot override attribution
# ═══════════════════════════════════════════════════════════════════


def test_create_task_ignores_injected_attribution(client, tokens, idor_db):
    """Extra JSON fields (org_id, department_id, owner_id) in create request
    are ignored — attribution always comes from the server-side context."""
    # Alice tries to create a task claiming she belongs to org2
    resp = client.post(
        "/api/v1/tasks",
        json={
            "title": "Injected attribution task",
            "tag": "今天",
            "org_id": "org2",          # Attempted injection
            "department_id": "Org2HQ",  # Attempted injection
            "owner_id": 999,            # Attempted injection
            "visibility": "public",     # Attempted injection
            "sensitivity": "sensitive", # Attempted injection
        },
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 201, f"Alice got {resp.status_code}, expected 201"

    # Alice should see her own task (she owns it)
    resp = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {tokens['alice']}"})
    titles = [t["title"] for t in resp.json()["items"]]
    assert "Injected attribution task" in titles

    # Dave (org2 org_admin) should NOT see Alice's task (it belongs to default org, not org2)
    resp = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {tokens['dave']}"})
    titles = [t["title"] for t in resp.json()["items"]]
    assert "Injected attribution task" not in titles, (
        "DEFENCE-IN-DEPTH FAILURE: Alice's task leaked to org2! "
        "Injected org_id was not ignored."
    )

    # Bob (same org/dept) should NOT see Alice's task (it defaults to private visibility)
    resp = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {tokens['bob']}"})
    titles = [t["title"] for t in resp.json()["items"]]
    assert "Injected attribution task" not in titles, (
        "DEFENCE-IN-DEPTH FAILURE: Alice's private task is visible to Bob! "
        "Injected visibility='public' was not ignored."
    )


def test_create_event_ignores_injected_attribution(client, tokens, idor_db):
    """Extra JSON fields in calendar event create are ignored."""
    resp = client.post(
        "/api/v1/calendar/events",
        json={
            "title": "Injected attribution event",
            "date": "2026-09-01",
            "tone": "blue",
            "org_id": "org2",
            "department_id": "Org2HQ",
            "owner_id": 999,
            "visibility": "org",
            "sensitivity": "internal",
        },
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 201

    # Alice sees her event
    resp = client.get("/api/v1/calendar/events", headers={"Authorization": f"Bearer {tokens['alice']}"})
    titles = [e["title"] for e in resp.json()["items"]]
    assert "Injected attribution event" in titles

    # Dave (org2) does NOT see it
    resp = client.get("/api/v1/calendar/events", headers={"Authorization": f"Bearer {tokens['dave']}"})
    titles = [e["title"] for e in resp.json()["items"]]
    assert "Injected attribution event" not in titles, (
        "DEFENCE-IN-DEPTH FAILURE: Event leaked to org2!"
    )

    # Bob (same org, but private visibility) does NOT see it
    resp = client.get("/api/v1/calendar/events", headers={"Authorization": f"Bearer {tokens['bob']}"})
    titles = [e["title"] for e in resp.json()["items"]]
    assert "Injected attribution event" not in titles, (
        "DEFENCE-IN-DEPTH FAILURE: Private event visible to Bob!"
    )


def test_update_task_cannot_change_attribution(client, tokens, idor_db):
    """PATCH with extra attribution fields does not change org_id/department_id/owner_id/visibility."""
    # Alice creates a private task
    resp = client.post(
        "/api/v1/tasks",
        json={"title": "Target for attribution injection", "tag": "今天"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    # Alice patches it with injection attempt
    resp = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={
            "title": "Still Alice's task",
            "org_id": "org2",
            "department_id": "Org2HQ",
            "owner_id": 999,
            "visibility": "org",
            "sensitivity": "internal",
        },
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 200

    # Bob still cannot see it (visibility was NOT changed to org)
    resp = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {tokens['bob']}"})
    titles = [t["title"] for t in resp.json()["items"]]
    assert "Still Alice's task" not in titles, (
        "DEFENCE-IN-DEPTH FAILURE: attribution was changed via PATCH — "
        "Bob can now see Alice's private task!"
    )

    # Dave (org2) still cannot see it
    resp = client.get("/api/v1/tasks", headers={"Authorization": f"Bearer {tokens['dave']}"})
    titles = [t["title"] for t in resp.json()["items"]]
    assert "Still Alice's task" not in titles


# ═══════════════════════════════════════════════════════════════════
# 9. Chat session isolation (Phase 4 P1-1 fix)
# ═══════════════════════════════════════════════════════════════════


def test_chat_session_isolated_to_owner(client, tokens, idor_db):
    """Alice creates a chat session; Bob cannot see or access it."""
    # Alice creates a chat session
    resp = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "alice-chat-001", "role": "user", "content": "Alice's secret chat"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 200

    # Alice can see her session
    resp = client.get(
        "/api/v1/chat/sessions",
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    session_ids = [s["id"] for s in resp.json()["items"]]
    assert "alice-chat-001" in session_ids

    # Bob cannot see Alice's session
    resp = client.get(
        "/api/v1/chat/sessions",
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    session_ids = [s["id"] for s in resp.json()["items"]]
    assert "alice-chat-001" not in session_ids, (
        "P1-1 FAILURE: Bob can see Alice's chat session in list"
    )

    # Bob cannot read Alice's messages
    resp = client.get(
        "/api/v1/chat/sessions/alice-chat-001/messages",
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    items = resp.json()["items"]
    assert len(items) == 0, (
        f"P1-1 FAILURE: Bob can read Alice's chat messages! Got {len(items)} messages"
    )

    # Bob cannot delete Alice's session
    resp = client.delete(
        "/api/v1/chat/sessions/alice-chat-001",
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp.status_code == 404, (
        f"P1-1 FAILURE: Bob got {resp.status_code} when deleting Alice's session, expected 404"
    )

    # Verify Alice's session still exists (Bob's delete didn't work)
    resp = client.get(
        "/api/v1/chat/sessions",
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    session_ids = [s["id"] for s in resp.json()["items"]]
    assert "alice-chat-001" in session_ids, (
        "P1-1 FAILURE: Bob deleted Alice's chat session!"
    )


def test_chat_session_delete_own_only(client, tokens, idor_db):
    """Alice can delete her own session; Bob cannot delete nonexistent sessions."""
    # Create session as Alice
    resp = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "alice-chat-del-001", "role": "user", "content": "Delete me"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 200

    # Alice can delete her own session
    resp = client.delete(
        "/api/v1/chat/sessions/alice-chat-del-001",
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify it's gone
    resp = client.get(
        "/api/v1/chat/sessions",
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    session_ids = [s["id"] for s in resp.json()["items"]]
    assert "alice-chat-del-001" not in session_ids


def test_chat_message_write_rejected_for_foreign_session(client, tokens, idor_db):
    """Bob cannot inject messages into Alice's existing chat session."""
    # Alice creates a session
    resp = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "alice-chat-write-test", "role": "user", "content": "Hello"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 200

    # Bob tries to write to Alice's session
    resp = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "alice-chat-write-test", "role": "user", "content": "Injected by Bob!"},
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    # Request returns 200 (silently dropped — does not reveal session existence)
    assert resp.status_code == 200

    # Alice reads messages — should NOT contain Bob's injection
    resp = client.get(
        "/api/v1/chat/sessions/alice-chat-write-test/messages",
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    messages = [m["content"] for m in resp.json()["items"]]
    assert "Injected by Bob!" not in messages, (
        "P1-1 FAILURE: Bob injected a message into Alice's chat session!"
    )
    assert "Hello" in messages, "Alice's original message should still be there"


def test_chat_session_ownership_claimed_on_first_use(client, tokens, idor_db):
    """The first user to write to a new session becomes its owner."""
    # Alice writes first
    resp = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "shared-session-name", "role": "user", "content": "Alice was first"},
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    assert resp.status_code == 200

    # Bob tries to write to the same session name
    resp = client.post(
        "/api/v1/chat/messages",
        json={"session_id": "shared-session-name", "role": "user", "content": "Bob's attempt"},
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    assert resp.status_code == 200  # silently dropped

    # Alice should NOT see Bob's message
    resp = client.get(
        "/api/v1/chat/sessions/shared-session-name/messages",
        headers={"Authorization": f"Bearer {tokens['alice']}"},
    )
    messages = [m["content"] for m in resp.json()["items"]]
    assert "Alice was first" in messages
    assert "Bob's attempt" not in messages, (
        "P1-1 FAILURE: Bob wrote to Alice's session!"
    )

    # Bob should NOT see Alice's session
    resp = client.get(
        "/api/v1/chat/sessions",
        headers={"Authorization": f"Bearer {tokens['bob']}"},
    )
    session_ids = [s["id"] for s in resp.json()["items"]]
    assert "shared-session-name" not in session_ids, (
        "P1-1 FAILURE: Bob sees Alice's session in his list!"
    )
