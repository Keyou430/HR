"""Phase 1: Permission constants, role definitions, and seed data.

Used by the Alembic migration to insert initial RBAC data and serves as
the canonical reference for role-permission mappings throughout the app.
"""

from __future__ import annotations

from typing import Any

from utils import _ts

# ──────────────────────────────────────────────────────────────────
# Permission codes (53 total — Phase 1 expansion)
# ──────────────────────────────────────────────────────────────────

PERMISSIONS: list[dict[str, str]] = [
    # user management
    {"code": "user:view",        "name": "查看用户",       "resource": "user",     "action": "view"},
    {"code": "user:create",      "name": "创建用户",       "resource": "user",     "action": "create"},
    {"code": "user:update",      "name": "更新用户",       "resource": "user",     "action": "update"},
    {"code": "user:disable",     "name": "禁用用户",       "resource": "user",     "action": "disable"},
    {"code": "user:assign_role", "name": "分配角色",       "resource": "user",     "action": "assign_role"},
    # org
    {"code": "org:view",         "name": "查看组织",       "resource": "org",      "action": "view"},
    {"code": "org:update",       "name": "更新组织",       "resource": "org",      "action": "update"},
    # dept
    {"code": "dept:view",        "name": "查看部门",       "resource": "dept",     "action": "view"},
    {"code": "dept:update",      "name": "更新部门",       "resource": "dept",     "action": "update"},
    # system
    {"code": "system:config",    "name": "系统配置",       "resource": "system",   "action": "config"},
    # audit
    {"code": "audit:view",       "name": "查看审计",       "resource": "audit",    "action": "view"},
    # tasks
    {"code": "task:view",        "name": "查看任务",       "resource": "task",     "action": "view"},
    {"code": "task:create",      "name": "创建任务",       "resource": "task",     "action": "create"},
    {"code": "task:update",      "name": "更新任务",       "resource": "task",     "action": "update"},
    {"code": "task:delete",      "name": "删除任务",       "resource": "task",     "action": "delete"},
    # calendar
    {"code": "calendar:view",    "name": "查看日历",       "resource": "calendar", "action": "view"},
    {"code": "calendar:create",  "name": "创建日历",       "resource": "calendar", "action": "create"},
    {"code": "calendar:update",  "name": "更新日历",       "resource": "calendar", "action": "update"},
    {"code": "calendar:delete",  "name": "删除日历",       "resource": "calendar", "action": "delete"},
    # knowledge
    {"code": "kb:view",          "name": "查看知识库",     "resource": "kb",       "action": "view"},
    {"code": "kb:create",        "name": "创建知识库",     "resource": "kb",       "action": "create"},
    {"code": "kb:update",        "name": "更新知识库",     "resource": "kb",       "action": "update"},
    {"code": "kb:delete",        "name": "删除知识库",     "resource": "kb",       "action": "delete"},
    {"code": "kb:import",        "name": "导入知识库",     "resource": "kb",       "action": "import"},
    {"code": "kb:chat",          "name": "知识库问答",     "resource": "kb",       "action": "chat"},
    {"code": "kb:chat_sensitive","name": "敏感知识问答",   "resource": "kb",       "action": "chat_sensitive"},
    # search
    {"code": "search:view",      "name": "搜索",           "resource": "search",   "action": "view"},
    # notices
    {"code": "notice:view",      "name": "查看通知",       "resource": "notice",   "action": "view"},
    {"code": "notice:create",    "name": "创建通知",       "resource": "notice",   "action": "create"},
    {"code": "notice:update",    "name": "更新通知",       "resource": "notice",   "action": "update"},
    {"code": "notice:delete",    "name": "删除通知",       "resource": "notice",   "action": "delete"},
    # ── Phase 1: enterprise module permissions (22 new) ──────────
    # repair (报修)
    {"code": "repair:view",      "name": "查看报修",       "resource": "repair",   "action": "view"},
    {"code": "repair:create",    "name": "创建报修",       "resource": "repair",   "action": "create"},
    {"code": "repair:assign",    "name": "派单",           "resource": "repair",   "action": "assign"},
    {"code": "repair:update",    "name": "更新报修",       "resource": "repair",   "action": "update"},
    {"code": "repair:close",     "name": "关闭报修",       "resource": "repair",   "action": "close"},
    # asset (资产)
    {"code": "asset:view",       "name": "查看资产",       "resource": "asset",    "action": "view"},
    {"code": "asset:create",     "name": "创建资产",       "resource": "asset",    "action": "create"},
    {"code": "asset:update",     "name": "更新资产",       "resource": "asset",    "action": "update"},
    {"code": "asset:borrow",     "name": "借用资产",       "resource": "asset",    "action": "borrow"},
    # oa (OA 审批)
    {"code": "oa:view",          "name": "查看OA",         "resource": "oa",       "action": "view"},
    {"code": "oa:create",        "name": "创建OA",         "resource": "oa",       "action": "create"},
    {"code": "oa:update",        "name": "更新OA",         "resource": "oa",       "action": "update"},
    # hr (人事)
    {"code": "hr:view",          "name": "查看人事",       "resource": "hr",       "action": "view"},
    {"code": "hr:create",        "name": "创建人事",       "resource": "hr",       "action": "create"},
    {"code": "hr:update",        "name": "更新人事",       "resource": "hr",       "action": "update"},
    # finance (财务)
    {"code": "finance:view",     "name": "查看财务",       "resource": "finance",  "action": "view"},
    {"code": "finance:create",   "name": "创建财务",       "resource": "finance",  "action": "create"},
    {"code": "finance:approve",  "name": "审批财务",       "resource": "finance",  "action": "approve"},
    # subsystem (子系统管理)
    {"code": "subsystem:view",   "name": "查看子系统",     "resource": "subsystem","action": "view"},
    {"code": "subsystem:manage", "name": "管理子系统",     "resource": "subsystem","action": "manage"},
    # dashboard (仪表板)
    {"code": "dashboard:view",   "name": "查看仪表板",     "resource": "dashboard","action": "view"},
    # enterprise records (企业记录总览)
    {"code": "enterprise:records:view", "name": "查看企业记录", "resource": "enterprise", "action": "records:view"},
]

# ──────────────────────────────────────────────────────────────────
# System roles (matching rbac-design-v2.md §5.2)
# ──────────────────────────────────────────────────────────────────

ROLES: list[dict[str, Any]] = [
    {"code": "super_admin", "name": "超级管理员", "description": "平台级管理员，拥有所有权限",              "is_system": True},
    {"code": "org_admin",   "name": "组织管理员", "description": "管理本组织配置和业务数据",                "is_system": True},
    {"code": "dept_leader", "name": "部门负责人", "description": "管理本部门及下级部门业务数据",            "is_system": True},
    {"code": "dept_staff",  "name": "部门员工",   "description": "管理个人任务、日程和知识",                "is_system": True},
    {"code": "external",    "name": "外部用户",   "description": "仅可访问公开内容",                        "is_system": True},
]

# ──────────────────────────────────────────────────────────────────
# Role → permission mapping (matching rbac-permission-matrix.md §2.2)
# ──────────────────────────────────────────────────────────────────

ROLE_PERMISSION_MAP: dict[str, list[str]] = {
    "super_admin": [p["code"] for p in PERMISSIONS],  # all 53

    "org_admin": [
        # user / org / dept / audit
        "user:view", "user:create", "user:update",
        "org:view", "org:update",
        "dept:view", "dept:update",
        "audit:view",
        # tasks / calendar / knowledge / search
        "task:view", "task:create", "task:update", "task:delete",
        "calendar:view", "calendar:create", "calendar:update", "calendar:delete",
        "kb:view", "kb:create", "kb:update", "kb:delete", "kb:import", "kb:chat", "kb:chat_sensitive",
        "search:view",
        # notices
        "notice:view", "notice:create", "notice:update", "notice:delete",
        # enterprise modules (full access)
        "repair:view", "repair:create", "repair:assign", "repair:update", "repair:close",
        "asset:view", "asset:create", "asset:update", "asset:borrow",
        "oa:view", "oa:create", "oa:update",
        "hr:view", "hr:create", "hr:update",
        "finance:view", "finance:create", "finance:approve",
        # subsystem / dashboard / enterprise
        "subsystem:view", "subsystem:manage",
        "dashboard:view",
        "enterprise:records:view",
    ],

    "dept_leader": [
        "org:view",
        "dept:view",
        "task:view", "task:create", "task:update", "task:delete",
        "calendar:view", "calendar:create", "calendar:update", "calendar:delete",
        "kb:view", "kb:update", "kb:import", "kb:chat",
        "search:view",
        "notice:view", "notice:create", "notice:update",
        # enterprise modules (view + limited create)
        "repair:view", "repair:create", "repair:update",
        "asset:view",
        "oa:view",
        "hr:view",
        "finance:view",
        "subsystem:view",
        "dashboard:view",
    ],

    "dept_staff": [
        "org:view",
        "dept:view",
        "task:view", "task:create", "task:update", "task:delete",
        "calendar:view", "calendar:create", "calendar:update", "calendar:delete",
        "kb:view", "kb:chat",
        "search:view",
        "notice:view",
        # enterprise modules (view only)
        "repair:view",
        "asset:view",
        "oa:view",
        "hr:view",
        "finance:view",
        "subsystem:view",
        "dashboard:view",
    ],

    "external": [
        "task:view",
        "calendar:view",
        "kb:view",
        "search:view",
    ],
}

# ──────────────────────────────────────────────────────────────────
# Permission groups for admin UI checkbox grid
# ──────────────────────────────────────────────────────────────────

PERMISSION_GROUPS: dict[str, dict[str, str | list[dict[str, str]]]] = {
    "用户管理": {
        "resource": "user",
        "permissions": [
            {"code": "user:view",        "name": "查看用户"},
            {"code": "user:create",      "name": "创建用户"},
            {"code": "user:update",      "name": "更新用户"},
            {"code": "user:disable",     "name": "禁用用户"},
            {"code": "user:assign_role", "name": "分配角色"},
        ],
    },
    "组织管理": {
        "resource": "org",
        "permissions": [
            {"code": "org:view",   "name": "查看组织"},
            {"code": "org:update", "name": "更新组织"},
        ],
    },
    "部门管理": {
        "resource": "dept",
        "permissions": [
            {"code": "dept:view",   "name": "查看部门"},
            {"code": "dept:update", "name": "更新部门"},
        ],
    },
    "系统配置": {
        "resource": "system",
        "permissions": [
            {"code": "system:config", "name": "系统配置"},
        ],
    },
    "操作审计": {
        "resource": "audit",
        "permissions": [
            {"code": "audit:view", "name": "查看审计"},
        ],
    },
    "任务": {
        "resource": "task",
        "permissions": [
            {"code": "task:view",   "name": "查看任务"},
            {"code": "task:create", "name": "创建任务"},
            {"code": "task:update", "name": "更新任务"},
            {"code": "task:delete", "name": "删除任务"},
        ],
    },
    "日历": {
        "resource": "calendar",
        "permissions": [
            {"code": "calendar:view",   "name": "查看日历"},
            {"code": "calendar:create", "name": "创建日历"},
            {"code": "calendar:update", "name": "更新日历"},
            {"code": "calendar:delete", "name": "删除日历"},
        ],
    },
    "知识库": {
        "resource": "kb",
        "permissions": [
            {"code": "kb:view",           "name": "查看知识库"},
            {"code": "kb:create",         "name": "创建知识库"},
            {"code": "kb:update",         "name": "更新知识库"},
            {"code": "kb:delete",         "name": "删除知识库"},
            {"code": "kb:import",         "name": "导入知识库"},
            {"code": "kb:chat",           "name": "知识库问答"},
            {"code": "kb:chat_sensitive", "name": "敏感知识问答"},
        ],
    },
    "搜索": {
        "resource": "search",
        "permissions": [
            {"code": "search:view", "name": "搜索"},
        ],
    },
    "通知公告": {
        "resource": "notice",
        "permissions": [
            {"code": "notice:view",   "name": "查看通知"},
            {"code": "notice:create", "name": "创建通知"},
            {"code": "notice:update", "name": "更新通知"},
            {"code": "notice:delete", "name": "删除通知"},
        ],
    },
    "报修系统": {
        "resource": "repair",
        "permissions": [
            {"code": "repair:view",   "name": "查看报修"},
            {"code": "repair:create", "name": "创建报修"},
            {"code": "repair:assign", "name": "派单"},
            {"code": "repair:update", "name": "更新报修"},
            {"code": "repair:close",  "name": "关闭报修"},
        ],
    },
    "资产系统": {
        "resource": "asset",
        "permissions": [
            {"code": "asset:view",   "name": "查看资产"},
            {"code": "asset:create", "name": "创建资产"},
            {"code": "asset:update", "name": "更新资产"},
            {"code": "asset:borrow", "name": "借用资产"},
        ],
    },
    "OA 系统": {
        "resource": "oa",
        "permissions": [
            {"code": "oa:view",   "name": "查看OA"},
            {"code": "oa:create", "name": "创建OA"},
            {"code": "oa:update", "name": "更新OA"},
        ],
    },
    "人事系统": {
        "resource": "hr",
        "permissions": [
            {"code": "hr:view",   "name": "查看人事"},
            {"code": "hr:create", "name": "创建人事"},
            {"code": "hr:update", "name": "更新人事"},
        ],
    },
    "财务系统": {
        "resource": "finance",
        "permissions": [
            {"code": "finance:view",    "name": "查看财务"},
            {"code": "finance:create",  "name": "创建财务"},
            {"code": "finance:approve", "name": "审批财务"},
        ],
    },
    "子系统管理": {
        "resource": "subsystem",
        "permissions": [
            {"code": "subsystem:view",   "name": "查看子系统"},
            {"code": "subsystem:manage", "name": "管理子系统"},
        ],
    },
    "仪表板": {
        "resource": "dashboard",
        "permissions": [
            {"code": "dashboard:view", "name": "查看仪表板"},
        ],
    },
    "企业记录": {
        "resource": "enterprise",
        "permissions": [
            {"code": "enterprise:records:view", "name": "查看企业记录"},
        ],
    },
}


# ──────────────────────────────────────────────────────────────────
# Default seed data
# ──────────────────────────────────────────────────────────────────

DEFAULT_ORG_ID = "default"
DEFAULT_DEPT_ID = "HQ"
DEFAULT_DEPT_NAME = "总部"
SYSTEM_SEED_USERNAME = "system_seed"
SYSTEM_SEED_DISPLAY = "系统种子用户"

# bcrypt hash of a mandatory-change password — the account is disabled
# (is_active=0) by default.  Phase 2 will enforce a forced password change
# on first successful authentication.
SYSTEM_SEED_PASSWORD_HASH = "$2b$12$MeUrwDTjryFVbkrtQPTU1.4pmwZX0qcvZbGUguk9bdMl7Yqjy6ey6"


# ──────────────────────────────────────────────────────────────────
# Seed helpers (called from migration)
# ──────────────────────────────────────────────────────────────────

def seed_org_and_dept(conn: Any) -> None:
    """Insert default org and HQ department if they do not exist."""
    org_exists = conn.exec_driver_sql(
        "SELECT 1 FROM orgs WHERE id='default'"
    ).fetchone()
    if org_exists is None:
        conn.exec_driver_sql(
            "INSERT INTO orgs (id, name, is_active, created_at, updated_at) "
            "VALUES ('default', '默认组织', 1, :ts, :ts)",
            {"ts": _ts()},
        )

    dept_exists = conn.exec_driver_sql(
        "SELECT 1 FROM departments WHERE id='HQ' AND org_id='default'"
    ).fetchone()
    if dept_exists is None:
        conn.exec_driver_sql(
            "INSERT INTO departments (id, org_id, name, parent_id, path, level, "
            "sort_order, is_active, created_at, updated_at) "
            "VALUES ('HQ', 'default', :name, NULL, 'HQ', 0, 0, 1, :ts, :ts)",
            {"name": DEFAULT_DEPT_NAME, "ts": _ts()},
        )


def seed_users(conn: Any) -> None:
    """Insert system_seed user if not already present."""
    user_exists = conn.exec_driver_sql(
        "SELECT 1 FROM users WHERE username='system_seed'"
    ).fetchone()
    if user_exists is None:
        conn.exec_driver_sql(
            "INSERT INTO users (username, password_hash, display_name, "
            "email, is_active, token_version, created_at, updated_at) "
            "VALUES ('system_seed', :pw, :dn, NULL, 0, 1, :ts, :ts)",
            {"pw": SYSTEM_SEED_PASSWORD_HASH, "dn": SYSTEM_SEED_DISPLAY, "ts": _ts()},
        )
        # Membership: system_seed → default org
        conn.exec_driver_sql(
            "INSERT INTO user_org_memberships (user_id, org_id, is_default, created_at) "
            "VALUES (1, 'default', 1, :ts)",
            {"ts": _ts()},
        )
        # Membership: system_seed → HQ dept
        conn.exec_driver_sql(
            "INSERT INTO user_department_memberships (user_id, org_id, department_id, "
            "is_primary, created_at) "
            "VALUES (1, 'default', 'HQ', 1, :ts)",
            {"ts": _ts()},
        )


def seed_roles(conn: Any) -> None:
    """Insert 5 system roles if not already present."""
    for role in ROLES:
        exists = conn.exec_driver_sql(
            "SELECT 1 FROM roles WHERE code=:code", {"code": role["code"]}
        ).fetchone()
        if exists is None:
            conn.exec_driver_sql(
                "INSERT INTO roles (code, name, description, is_system, created_at) "
                "VALUES (:code, :name, :desc, :is_sys, :ts)",
                {
                    "code": role["code"],
                    "name": role["name"],
                    "desc": role["description"],
                    "is_sys": 1 if role["is_system"] else 0,
                    "ts": _ts(),
                },
            )


def seed_permissions(conn: Any) -> None:
    """Insert 31 permissions if not already present."""
    for perm in PERMISSIONS:
        exists = conn.exec_driver_sql(
            "SELECT 1 FROM permissions WHERE code=:code", {"code": perm["code"]}
        ).fetchone()
        if exists is None:
            conn.exec_driver_sql(
                "INSERT INTO permissions (code, name, resource, action, description) "
                "VALUES (:code, :name, :res, :act, :desc)",
                {
                    "code": perm["code"],
                    "name": perm["name"],
                    "res": perm["resource"],
                    "act": perm["action"],
                    "desc": None,
                },
            )


def seed_role_permissions(conn: Any) -> None:
    """Bind each role to its assigned permissions."""
    # Resolve role IDs
    role_ids: dict[str, int] = {}
    rows = conn.exec_driver_sql("SELECT id, code FROM roles").fetchall()
    for row in rows:
        role_ids[row[1]] = row[0]

    # Resolve permission IDs
    perm_ids: dict[str, int] = {}
    rows = conn.exec_driver_sql("SELECT id, code FROM permissions").fetchall()
    for row in rows:
        perm_ids[row[1]] = row[0]

    for role_code, perm_codes in ROLE_PERMISSION_MAP.items():
        role_id = role_ids.get(role_code)
        if role_id is None:
            continue
        for perm_code in perm_codes:
            perm_id = perm_ids.get(perm_code)
            if perm_id is None:
                continue
            exists = conn.exec_driver_sql(
                "SELECT 1 FROM role_permissions WHERE role_id=:rid AND permission_id=:pid",
                {"rid": role_id, "pid": perm_id},
            ).fetchone()
            if exists is None:
                conn.exec_driver_sql(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:rid, :pid)",
                    {"rid": role_id, "pid": perm_id},
                )


def seed_role_bindings(conn: Any) -> None:
    """Bind system_seed (user 1) as super_admin in default org (Phase 2+)."""
    exists = conn.exec_driver_sql(
        "SELECT 1 FROM role_bindings WHERE user_id=1 AND role_id=("
        "SELECT id FROM roles WHERE code='super_admin') AND org_id='default'"
    ).fetchone()
    if exists is not None:
        return
    conn.exec_driver_sql(
        "INSERT INTO role_bindings (user_id, role_id, org_id, department_id, created_at) "
        "SELECT 1, id, 'default', 'HQ', :ts FROM roles WHERE code='super_admin'",
        {"ts": _ts()},
    )


def seed_all(conn: Any) -> None:
    """Run all seed steps inside a single connection (idempotent)."""
    seed_org_and_dept(conn)
    seed_users(conn)
    seed_roles(conn)
    seed_permissions(conn)
    seed_role_permissions(conn)
    seed_role_bindings(conn)
