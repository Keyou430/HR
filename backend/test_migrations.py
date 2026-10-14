"""Phase 1: Alembic migration tests — fresh DB, existing DB, backfill, downgrade.

These tests verify that the RBAC v2.0 migration can be applied to both
empty and populated databases without data loss, and that seed data is
complete and correct.
"""

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from alembic.config import Config
from alembic import command
from sqlalchemy import MetaData, Table, create_engine, insert, text


MIGRATION_READER = {"id": 1, "roles": ["super_admin"]}


def _create_legacy_database(db_url: str) -> None:
    """Create pre-RBAC business tables without runtime schema initialization."""
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("""
                CREATE TABLE portal_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title VARCHAR(255) NOT NULL, tag VARCHAR(32) NOT NULL,
                    due_time VARCHAR(8), done BOOLEAN NOT NULL DEFAULT 0
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE portal_calendar_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, date VARCHAR(10) NOT NULL,
                    title VARCHAR(255) NOT NULL, tone VARCHAR(16) NOT NULL
                )
            """)
            conn.exec_driver_sql("""
                CREATE TABLE knowledge_dataset_mappings (
                    id VARCHAR(160) PRIMARY KEY, resource_type VARCHAR(16) NOT NULL,
                    resource_id VARCHAR(128) NOT NULL, display_name VARCHAR(255) NOT NULL,
                    fastgpt_app_id VARCHAR(128), fastgpt_dataset_id VARCHAR(128),
                    permission_scope VARCHAR(16) NOT NULL DEFAULT 'team',
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    is_default_import_target BOOLEAN NOT NULL DEFAULT 0,
                    last_synced_at VARCHAR(32), last_imported_at VARCHAR(32),
                    stale BOOLEAN NOT NULL DEFAULT 0, updated_at VARCHAR(32) NOT NULL
                )
            """)
    finally:
        engine.dispose()


def _insert_legacy_resource(db_url, table_name, values):
    """Insert into the actual legacy schema, leaving attribution to the migration."""
    engine = create_engine(db_url)
    try:
        with engine.begin() as conn:
            table = Table(table_name, MetaData(), autoload_with=conn)
            result = conn.execute(insert(table).values(**values))
            return {"id": result.inserted_primary_key[0]}
    finally:
        engine.dispose()


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────


def _alembic_config(db_path: str) -> Config:
    """Return an Alembic Config pointed at a specific SQLite database.

    Forces UTF-8 encoding when reading alembic.ini because Alembic's
    config parser defaults to locale encoding (cp936 on Chinese Windows).
    """
    ini_path = str(BACKEND_ROOT / "alembic.ini")
    cfg = Config(ini_path)
    # Re-read with explicit UTF-8 to avoid UnicodeDecodeError on Windows
    cfg.file_config.read(ini_path, encoding="utf-8")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg


def _upgrade(cfg: Config, revision: str = "head") -> None:
    command.upgrade(cfg, revision)


def _downgrade(cfg: Config, revision: str = "-1") -> None:
    command.downgrade(cfg, revision)


def _table_exists(db_path: str, table: str) -> bool:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.exec_driver_sql(
            f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'"
        ).fetchone()
    engine.dispose()
    return row is not None


def _count_rows(db_path: str, table: str) -> int:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        row = conn.exec_driver_sql(f"SELECT COUNT(1) FROM {table}").fetchone()
    engine.dispose()
    return int(row[0]) if row else 0


def _col_exists(db_path: str, table: str, column: str) -> bool:
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
    engine.dispose()
    return any(row[1] == column for row in rows)


# ──────────────────────────────────────────────────────────────────
# 1. Fresh (empty) database upgrade
# ──────────────────────────────────────────────────────────────────


def test_fresh_db_upgrade_succeeds(tmp_path, monkeypatch) -> None:
    """An empty SQLite database can be migrated to head without errors."""
    db_path = tmp_path / "fresh.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from config import get_settings
    get_settings.cache_clear()

    cfg = _alembic_config(str(db_path))
    _upgrade(cfg, "head")  # must not raise

    # Verify alembic_version stamp exists
    assert _table_exists(str(db_path), "alembic_version")


def test_fresh_db_has_all_new_tables(tmp_path, monkeypatch) -> None:
    """After fresh migration, all 12 new RBAC tables exist."""
    db_path = tmp_path / "fresh_tables.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from config import get_settings
    get_settings.cache_clear()

    _upgrade(_alembic_config(str(db_path)), "head")

    new_tables = [
        "orgs", "departments", "users", "user_org_memberships",
        "user_department_memberships", "roles", "permissions",
        "role_permissions", "role_bindings", "auth_sessions",
        "audit_logs", "ai_query_logs",
    ]
    for table in new_tables:
        assert _table_exists(str(db_path), table), f"Table {table} missing after migration"


def test_fresh_db_has_seed_data(tmp_path, monkeypatch) -> None:
    """Seed data is populated: org, dept, user, roles, permissions, bindings."""
    from authorization.permissions import PERMISSIONS, ROLE_PERMISSION_MAP

    db_path = tmp_path / "fresh_seed.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from config import get_settings
    get_settings.cache_clear()

    _upgrade(_alembic_config(str(db_path)), "head")

    # Default org & department
    assert _count_rows(str(db_path), "orgs") >= 1
    assert _count_rows(str(db_path), "departments") >= 1

    # system_seed user
    assert _count_rows(str(db_path), "users") >= 1

    # 5 system roles
    assert _count_rows(str(db_path), "roles") == 5

    expected_permission_codes = {permission["code"] for permission in PERMISSIONS}
    assert _count_rows(str(db_path), "permissions") == len(expected_permission_codes)

    # Every role must have exactly its declared permissions
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT r.code, p.code "
            "FROM roles r JOIN role_permissions rp ON r.id=rp.role_id "
            "JOIN permissions p ON p.id=rp.permission_id"
        ).fetchall()
    engine.dispose()

    role_permissions = {}
    for role_code, permission_code in rows:
        role_permissions.setdefault(role_code, set()).add(permission_code)
    assert role_permissions == {
        role_code: set(permission_codes)
        for role_code, permission_codes in ROLE_PERMISSION_MAP.items()
    }
    assert role_permissions["super_admin"] == expected_permission_codes

    # system_seed bound as super_admin
    assert _count_rows(str(db_path), "role_bindings") >= 1


def test_fresh_db_business_tables_have_attribution_columns(tmp_path, monkeypatch) -> None:
    """After migration, portal_tasks, portal_calendar_events, knowledge_dataset_mappings
    have the new data-attribution columns."""
    db_path = tmp_path / "fresh_cols.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from config import get_settings
    get_settings.cache_clear()

    _upgrade(_alembic_config(str(db_path)), "head")

    for table in ("portal_tasks", "portal_calendar_events", "knowledge_dataset_mappings"):
        for col in ("org_id", "department_id", "owner_id", "visibility", "sensitivity"):
            assert _col_exists(str(db_path), table, col), f"{table}.{col} missing"


# ──────────────────────────────────────────────────────────────────
# 2. Existing-database upgrade (with pre-existing data)
# ──────────────────────────────────────────────────────────────────


def test_existing_db_upgrade_preserves_data(tmp_path, monkeypatch) -> None:
    """Migrating a DB that already has tasks/events/mappings does not delete them."""
    db_path = tmp_path / "existing.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    # Step A: create the business schema before RBAC was introduced
    monkeypatch.setenv("DATABASE_URL", db_url)
    from config import get_settings
    get_settings.cache_clear()

    _create_legacy_database(db_url)

    # Create some data
    t = _insert_legacy_resource(db_url, "portal_tasks", {"title": "Phase 1 测试任务", "tag": "今天"})
    e = _insert_legacy_resource(db_url, "portal_calendar_events", {"title": "Phase 1 测试日程", "date": "2026-07-30", "tone": "blue"})

    # Step B: Run Alembic migration over the existing DB
    _upgrade(_alembic_config(str(db_path)), "head")

    # Step C: Verify old data survives (re-open store to bypass cache)
    get_settings.cache_clear()
    from store import PortalStore
    store2 = PortalStore()

    tasks = store2.list_tasks(user=MIGRATION_READER)
    assert tasks["total"] >= 1
    assert any(item["id"] == t["id"] and item["title"] == "Phase 1 测试任务" for item in tasks["items"])

    events = store2.list_events(user=MIGRATION_READER)
    assert events["total"] >= 1
    assert any(ev["id"] == e["id"] and ev["title"] == "Phase 1 测试日程" for ev in events["items"])


def test_backfill_assigns_correct_default_values(tmp_path, monkeypatch) -> None:
    """After migrating a DB with pre-existing data, rows are backfilled correctly."""
    db_path = tmp_path / "backfill.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    from config import get_settings
    get_settings.cache_clear()

    _create_legacy_database(db_url)
    task = _insert_legacy_resource(db_url, "portal_tasks", {"title": "回填测试", "tag": "今天"})
    event = _insert_legacy_resource(db_url, "portal_calendar_events", {"title": "回填日程", "date": "2026-08-01", "tone": "green"})
    mapping = _insert_legacy_resource(db_url, "knowledge_dataset_mappings", {
        "id": "legacy-dataset", "resource_type": "dataset", "resource_id": "legacy-dataset",
        "display_name": "回填知识库", "fastgpt_dataset_id": "legacy-dataset",
        "updated_at": "2026-08-01T00:00:00",
    })

    # Run migration
    _upgrade(_alembic_config(str(db_path)), "head")

    # Verify backfill values
    engine = create_engine(db_url)
    with engine.connect() as conn:
        task_row = conn.execute(text("SELECT org_id, department_id, owner_id, visibility, sensitivity FROM portal_tasks WHERE id=:id"), task).fetchone()
        assert task_row is not None
        assert task_row[0] == "default", f"org_id={task_row[0]}"
        assert task_row[1] == "HQ", f"department_id={task_row[1]}"
        assert task_row[2] == 1, f"owner_id={task_row[2]}"
        assert task_row[3] == "org", f"visibility={task_row[3]}"
        assert task_row[4] == "normal", f"sensitivity={task_row[4]}"

        event_row = conn.execute(text("SELECT org_id, department_id, owner_id, visibility, sensitivity FROM portal_calendar_events WHERE id=:id"), event).fetchone()
        assert event_row is not None
        assert event_row[0] == "default"
        assert event_row[1] == "HQ"
        assert event_row[2] == 1
        assert event_row[3] == "org"
        assert event_row[4] == "normal"

        mapping_row = conn.execute(text(
            "SELECT org_id, department_id, owner_id, visibility, sensitivity "
            "FROM knowledge_dataset_mappings WHERE id=:id"
        ), mapping).fetchone()
        assert mapping_row is not None
        assert tuple(mapping_row) == ("default", "HQ", 1, "dept", "internal")
    engine.dispose()


# ──────────────────────────────────────────────────────────────────
# 3. Idempotency
# ──────────────────────────────────────────────────────────────────


def test_migration_idempotent_upgrade(tmp_path, monkeypatch) -> None:
    """Running upgrade twice on the same DB succeeds without errors."""
    from authorization.permissions import PERMISSIONS

    db_path = tmp_path / "idempotent.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from config import get_settings
    get_settings.cache_clear()

    cfg = _alembic_config(str(db_path))
    _upgrade(cfg, "head")
    engine = create_engine(f"sqlite:///{db_path}")
    try:
        with engine.connect() as conn:
            permissions_before = conn.exec_driver_sql("SELECT * FROM permissions ORDER BY id").fetchall()
            bindings_before = conn.exec_driver_sql(
                "SELECT * FROM role_permissions ORDER BY role_id, permission_id"
            ).fetchall()
        # Second upgrade must not raise or alter seed rows and role bindings.
        _upgrade(cfg, "head")
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT * FROM permissions ORDER BY id").fetchall() == permissions_before
            assert conn.exec_driver_sql(
                "SELECT * FROM role_permissions ORDER BY role_id, permission_id"
            ).fetchall() == bindings_before
    finally:
        engine.dispose()

    # Data should still be consistent
    assert _count_rows(str(db_path), "roles") == 5
    assert _count_rows(str(db_path), "permissions") == len({permission["code"] for permission in PERMISSIONS})
    assert {row[1] for row in permissions_before} == {permission["code"] for permission in PERMISSIONS}


# ──────────────────────────────────────────────────────────────────
# 4. Downgrade
# ──────────────────────────────────────────────────────────────────


def test_downgrade_removes_new_tables(tmp_path, monkeypatch) -> None:
    """Downgrading to base removes RBAC tables and preserves legacy business rows."""
    db_path = tmp_path / "downgrade.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from config import get_settings
    get_settings.cache_clear()

    # Create some business data first
    db_url = f"sqlite:///{db_path.as_posix()}"
    _create_legacy_database(db_url)
    t = _insert_legacy_resource(db_url, "portal_tasks", {"title": "降级测试", "tag": "今天"})

    # Upgrade then downgrade
    cfg = _alembic_config(str(db_path))
    _upgrade(cfg, "head")
    _downgrade(cfg, "base")

    # New tables gone
    for table in ("orgs", "departments", "roles", "permissions", "role_permissions",
                  "role_bindings", "auth_sessions", "audit_logs", "ai_query_logs"):
        assert not _table_exists(str(db_path), table), f"Table {table} should be gone after downgrade"

    # Old tables still have data
    assert _table_exists(str(db_path), "portal_tasks")
    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            task = conn.execute(
                text("SELECT id, title, tag FROM portal_tasks WHERE id=:id"), t
            ).fetchone()
            assert task is not None, "Task lost after downgrade"
            assert tuple(task) == (t["id"], "降级测试", "今天")
    finally:
        engine.dispose()


def test_downgrade_removes_attribution_columns(tmp_path, monkeypatch) -> None:
    """After downgrade, attribution columns are removed from business tables."""
    db_path = tmp_path / "downgrade_cols.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from config import get_settings
    get_settings.cache_clear()

    # Start from real pre-RBAC tables, without creating runtime RBAC tables.
    _create_legacy_database(f"sqlite:///{db_path.as_posix()}")

    cfg = _alembic_config(str(db_path))
    _upgrade(cfg, "head")
    _downgrade(cfg, "base")

    for table in ("portal_tasks", "portal_calendar_events", "knowledge_dataset_mappings"):
        for col in ("org_id", "department_id", "owner_id", "visibility", "sensitivity"):
            assert not _col_exists(str(db_path), table, col), f"{table}.{col} should be gone after downgrade"


def test_task_deadline_downgrade_can_upgrade_again(tmp_path, monkeypatch) -> None:
    """013 -> 012 -> 013 preserves tasks and rebuilds the overdue index."""
    db_path = tmp_path / "task_deadline_roundtrip.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    from config import get_settings
    get_settings.cache_clear()

    cfg = _alembic_config(str(db_path))
    _upgrade(cfg, "013")
    task = _insert_legacy_resource(db_url, "portal_tasks", {
        "title": "截止时间回滚测试", "tag": "今天", "done": True,
        "deadline": "2026-10-15T10:00:00", "overdue_notified_at": "2026-10-14T10:00:00",
    })
    _downgrade(cfg, "012")
    assert _col_exists(str(db_path), "portal_tasks", "due_time")
    assert not _col_exists(str(db_path), "portal_tasks", "deadline")
    assert not _col_exists(str(db_path), "portal_tasks", "overdue_notified_at")

    engine = create_engine(db_url)
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT title, tag, done FROM portal_tasks WHERE id=:id"), task).fetchone()
            assert row is not None
            assert tuple(row) == ("截止时间回滚测试", "今天", 1)
            assert conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='ix_portal_tasks_overdue_scan'"
            ).fetchone() is None
        _upgrade(cfg, "013")
        assert not _col_exists(str(db_path), "portal_tasks", "due_time")
        assert _col_exists(str(db_path), "portal_tasks", "deadline")
        assert _col_exists(str(db_path), "portal_tasks", "overdue_notified_at")
        with engine.connect() as conn:
            row = conn.execute(text("SELECT title, tag, done FROM portal_tasks WHERE id=:id"), task).fetchone()
            assert row is not None
            assert tuple(row) == ("截止时间回滚测试", "今天", 1)
            assert conn.exec_driver_sql(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='ix_portal_tasks_overdue_scan'"
            ).fetchone() is not None
    finally:
        engine.dispose()
