#!/usr/bin/env python3
"""
seed_dev.py — Development seed data
Creates test users for all 5 RBAC roles + sample business data.
Idempotent: safe to run on every container start.
"""
import sys
from datetime import datetime, timezone

from auth.password import hash_password
from session import get_engine
from sqlalchemy import text

DEV_USERS = [
    {"username": "admin", "password": "admin123", "display_name": "Administrator",
     "email": "admin@hr.example.com", "role": "super_admin"},
    {"username": "org_admin", "password": "Admin123!", "display_name": "Organization Admin",
     "email": "org_admin@hr.example.com", "role": "org_admin"},
    {"username": "leader", "password": "Admin123!", "display_name": "Department Leader",
     "email": "leader@hr.example.com", "role": "dept_leader"},
    {"username": "staff", "password": "Admin123!", "display_name": "Department Staff",
     "email": "staff@hr.example.com", "role": "dept_staff"},
    {"username": "staff2", "password": "staff123", "display_name": "Staff 2",
     "email": "staff2@hr.example.com", "role": "dept_staff"},
    {"username": "external", "password": "Admin123!", "display_name": "External User",
     "email": "external@hr.example.com", "role": "external"},
]


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed() -> None:
    engine = get_engine()
    ts = _ts()

    with engine.begin() as conn:
        # ── Ensure default org ─────────────────────────────────────
        org = conn.execute(text("SELECT 1 FROM organizations WHERE id='default'")).fetchone()
        if org is None:
            conn.execute(
                text("INSERT INTO organizations (id, name, description, is_active, created_at) "
                     "VALUES ('default', 'Default Organization', 'Default organization from dev seed', 1, :ts)"),
                {"ts": ts})
            print("[seed] Created default organization")

        # ── Ensure HQ department ───────────────────────────────────
        dept = conn.execute(text("SELECT 1 FROM departments WHERE id='HQ'")).fetchone()
        if dept is None:
            conn.execute(
                text("INSERT INTO departments (id, name, org_id, created_at) "
                     "VALUES ('HQ', 'Headquarters', 'default', :ts)"),
                {"ts": ts})
            print("[seed] Created HQ department")

        # ── Lookup role IDs ────────────────────────────────────────
        role_ids: dict[str, int] = {}
        rows = conn.execute(text("SELECT id, code FROM roles")).fetchall()
        for row in rows:
            role_ids[row[1]] = row[0]

        # ── Create dev users ───────────────────────────────────────
        for user_def in DEV_USERS:
            existing = conn.execute(
                text("SELECT id FROM users WHERE username = :un"),
                {"un": user_def["username"]}).fetchone()
            if existing is not None:
                print(f'[seed] User "{user_def["username"]}" already exists (id={existing[0]}) — skipping')
                continue

            pwd_hash = hash_password(user_def["password"])
            result = conn.execute(
                text("INSERT INTO users (username, password_hash, display_name, email, "
                     "is_active, token_version, must_change_password, created_at, updated_at) "
                     "VALUES (:un, :pw, :dn, :em, 1, 1, 0, :ts, :ts)"),
                {"un": user_def["username"], "pw": pwd_hash,
                 "dn": user_def["display_name"], "em": user_def["email"], "ts": ts})
            user_id = result.lastrowid
            print(f'[seed] Created user "{user_def["username"]}" (id={user_id})')

            # Org + Dept + Role bindings
            conn.execute(text("INSERT INTO user_org_memberships (user_id, org_id, is_default, created_at) "
                              "VALUES (:uid, 'default', 1, :ts)"), {"uid": user_id, "ts": ts})
            conn.execute(text("INSERT INTO user_department_memberships (user_id, org_id, department_id, "
                              "is_primary, created_at) VALUES (:uid, 'default', 'HQ', 1, :ts)"),
                         {"uid": user_id, "ts": ts})
            role_id = role_ids.get(user_def["role"])
            if role_id:
                conn.execute(text("INSERT INTO role_bindings (user_id, role_id, org_id, department_id, created_at) "
                                  "VALUES (:uid, :rid, 'default', 'HQ', :ts)"), {"uid": user_id, "rid": role_id, "ts": ts})

        # ── Sample repair orders ───────────────────────────────────
        repair_count = conn.execute(text("SELECT COUNT(*) FROM repair_orders")).scalar()
        if repair_count == 0:
            conn.execute(text(
                "INSERT INTO repair_orders (title, description, status, priority, reporter_id, "
                "org_id, department_id, created_at, updated_at) "
                "VALUES ('办公室空调故障', '三楼东区空调不制冷，温度持续在28°C以上', "
                "'pending', 'high', 3, 'default', 'HQ', :ts, :ts)"), {"ts": ts})
            conn.execute(text(
                "INSERT INTO repair_orders (title, description, status, priority, reporter_id, "
                "org_id, department_id, created_at, updated_at) "
                "VALUES ('网络打印机脱机', '二楼打印机HP LaserJet M506无法连接网络', "
                "'in_progress', 'medium', 4, 'default', 'HQ', :ts, :ts)"), {"ts": ts})
            print("[seed] Created 2 sample repair orders")

        # ── Sample assets ──────────────────────────────────────────
        asset_count = conn.execute(text("SELECT COUNT(*) FROM assets")).scalar()
        if asset_count == 0:
            for code, name, cat, status in [
                ("LAPTOP-001", "ThinkPad X1 Carbon Gen 12", "laptop", "使用中"),
                ("MONITOR-001", "Dell U2723QE 27\" 4K", "monitor", "使用中"),
                ("PRINTER-001", "HP LaserJet M506", "printer", "维修中"),
            ]:
                conn.execute(text(
                    "INSERT INTO assets (code, name, category, status, custodian_id, "
                    "org_id, department_id, created_at, updated_at) "
                    "VALUES (:code, :name, :cat, :status, 3, 'default', 'HQ', :ts, :ts)"),
                    {"code": code, "name": name, "cat": cat, "status": status, "ts": ts})
            print("[seed] Created 3 sample asset records")

    print("[seed] Dev seed complete.")


if __name__ == "__main__":
    try:
        _seed()
    except Exception as exc:
        print(f"[seed] ERROR: {exc}", file=sys.stderr)
        sys.exit(0)  # Non-critical — don't block container startup
