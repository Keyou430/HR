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
from sqlalchemy import create_engine, text


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

    # 31 permissions
    assert _count_rows(str(db_path), "permissions") == 31

    # Each role has at least some permissions
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(
            "SELECT r.code, COUNT(rp.permission_id) AS cnt "
            "FROM roles r JOIN role_permissions rp ON r.id=rp.role_id "
            "GROUP BY r.code"
        ).fetchall()
    engine.dispose()

    role_counts = {row[0]: row[1] for row in rows}
    assert role_counts.get("super_admin") == 31, f"super_admin should have 31 perms, got {role_counts}"
    assert role_counts.get("org_admin", 0) >= 20
    assert role_counts.get("dept_leader", 0) >= 12
    assert role_counts.get("dept_staff", 0) >= 8
    assert role_counts.get("external", 0) >= 3

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

    # Step A: simulate pre-migration state — create old tables via metadata.create_all
    monkeypatch.setenv("DATABASE_URL", db_url)
    from config import get_settings
    get_settings.cache_clear()

    from store import PortalStore
    store = PortalStore()

    # Create some data
    t = store.create_task({"title": "Phase 1 测试任务", "tag": "今天"})
    e = store.create_event({"title": "Phase 1 测试日程", "date": "2026-07-30", "tone": "blue"})

    # Step B: Run Alembic migration over the existing DB
    _upgrade(_alembic_config(str(db_path)), "head")

    # Step C: Verify old data survives (re-open store to bypass cache)
    get_settings.cache_clear()
    store2 = PortalStore()

    tasks = store2.list_tasks()
    assert tasks["total"] >= 1
    assert any(item["id"] == t["id"] and item["title"] == "Phase 1 测试任务" for item in tasks["items"])

    events = store2.list_events()
    assert events["total"] >= 1
    assert any(ev["id"] == e["id"] and ev["title"] == "Phase 1 测试日程" for ev in events["items"])


def test_backfill_assigns_correct_default_values(tmp_path, monkeypatch) -> None:
    """After migrating a DB with pre-existing data, rows are backfilled correctly."""
    db_path = tmp_path / "backfill.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    from config import get_settings
    get_settings.cache_clear()

    from store import PortalStore
    store = PortalStore()
    store.create_task({"title": "回填测试", "tag": "今天"})
    store.create_event({"title": "回填日程", "date": "2026-08-01", "tone": "green"})

    # Run migration
    _upgrade(_alembic_config(str(db_path)), "head")

    # Verify backfill values
    engine = create_engine(db_url)
    with engine.connect() as conn:
        task_row = conn.exec_driver_sql("SELECT org_id, department_id, owner_id, visibility, sensitivity FROM portal_tasks LIMIT 1").fetchone()
        assert task_row is not None
        assert task_row[0] == "default", f"org_id={task_row[0]}"
        assert task_row[1] == "HQ", f"department_id={task_row[1]}"
        assert task_row[2] == 1, f"owner_id={task_row[2]}"
        assert task_row[3] == "org", f"visibility={task_row[3]}"
        assert task_row[4] == "normal", f"sensitivity={task_row[4]}"

        event_row = conn.exec_driver_sql("SELECT org_id, department_id, owner_id, visibility, sensitivity FROM portal_calendar_events LIMIT 1").fetchone()
        assert event_row is not None
        assert event_row[0] == "default"
        assert event_row[1] == "HQ"
        assert event_row[2] == 1
        assert event_row[3] == "org"
        assert event_row[4] == "normal"
    engine.dispose()


# ──────────────────────────────────────────────────────────────────
# 3. Idempotency
# ──────────────────────────────────────────────────────────────────


def test_migration_idempotent_upgrade(tmp_path, monkeypatch) -> None:
    """Running upgrade twice on the same DB succeeds without errors."""
    db_path = tmp_path / "idempotent.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from config import get_settings
    get_settings.cache_clear()

    cfg = _alembic_config(str(db_path))
    _upgrade(cfg, "head")
    # Second upgrade must not raise
    _upgrade(cfg, "head")

    # Data should still be consistent
    assert _count_rows(str(db_path), "roles") == 5
    assert _count_rows(str(db_path), "permissions") == 31


# ──────────────────────────────────────────────────────────────────
# 4. Downgrade
# ──────────────────────────────────────────────────────────────────


def test_downgrade_removes_new_tables(tmp_path, monkeypatch) -> None:
    """downgrade -1 removes the new RBAC tables but keeps old business tables."""
    db_path = tmp_path / "downgrade.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from config import get_settings
    get_settings.cache_clear()

    # Create some business data first
    from store import PortalStore
    store = PortalStore()
    t = store.create_task({"title": "降级测试", "tag": "今天"})

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
    get_settings.cache_clear()
    store2 = PortalStore()
    tasks = store2.list_tasks()
    assert any(item["id"] == t["id"] for item in tasks["items"]), "Task lost after downgrade"


def test_downgrade_removes_attribution_columns(tmp_path, monkeypatch) -> None:
    """After downgrade, attribution columns are removed from business tables."""
    db_path = tmp_path / "downgrade_cols.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    from config import get_settings
    get_settings.cache_clear()

    # Create data so tables exist
    from store import PortalStore
    PortalStore()

    cfg = _alembic_config(str(db_path))
    _upgrade(cfg, "head")
    _downgrade(cfg, "base")

    for table in ("portal_tasks", "portal_calendar_events", "knowledge_dataset_mappings"):
        for col in ("org_id", "department_id", "owner_id", "visibility", "sensitivity"):
            assert not _col_exists(str(db_path), table, col), f"{table}.{col} should be gone after downgrade"
