"""Phase 1: Permission constants, role definitions, and seed data.

Used by the Alembic migration to insert initial RBAC data and serves as
the canonical reference for role-permission mappings throughout the app.
"""

from __future__ import annotations

from typing import Any

from utils import _ts

# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# Permission codes (53 total 鈥?Phase 1 expansion)
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

PERMISSIONS: list[dict[str, str]] = [
    # user management
    {"code": "user:view",        "name": "鏌ョ湅鐢ㄦ埛",       "resource": "user",     "action": "view"},
    {"code": "user:create",      "name": "鍒涘缓鐢ㄦ埛",       "resource": "user",     "action": "create"},
    {"code": "user:update",      "name": "鏇存柊鐢ㄦ埛",       "resource": "user",     "action": "update"},
    {"code": "user:disable",     "name": "绂佺敤鐢ㄦ埛",       "resource": "user",     "action": "disable"},
    {"code": "user:assign_role", "name": "鍒嗛厤瑙掕壊",       "resource": "user",     "action": "assign_role"},
    # org
    {"code": "org:view",         "name": "鏌ョ湅缁勭粐",       "resource": "org",      "action": "view"},
    {"code": "org:update",       "name": "鏇存柊缁勭粐",       "resource": "org",      "action": "update"},
    # dept
    {"code": "dept:view",        "name": "鏌ョ湅閮ㄩ棬",       "resource": "dept",     "action": "view"},
    {"code": "dept:update",      "name": "鏇存柊閮ㄩ棬",       "resource": "dept",     "action": "update"},
    # system
    {"code": "system:config",    "name": "绯荤粺閰嶇疆",       "resource": "system",   "action": "config"},
    # audit
    {"code": "audit:view",       "name": "鏌ョ湅瀹¤",       "resource": "audit",    "action": "view"},
    # tasks
    {"code": "task:view",        "name": "鏌ョ湅浠诲姟",       "resource": "task",     "action": "view"},
    {"code": "task:create",      "name": "鍒涘缓浠诲姟",       "resource": "task",     "action": "create"},
    {"code": "task:update",      "name": "鏇存柊浠诲姟",       "resource": "task",     "action": "update"},
    {"code": "task:delete",      "name": "鍒犻櫎浠诲姟",       "resource": "task",     "action": "delete"},
    # calendar
    {"code": "calendar:view",    "name": "鏌ョ湅鏃ュ巻",       "resource": "calendar", "action": "view"},
    {"code": "calendar:create",  "name": "鍒涘缓鏃ュ巻",       "resource": "calendar", "action": "create"},
    {"code": "calendar:update",  "name": "鏇存柊鏃ュ巻",       "resource": "calendar", "action": "update"},
    {"code": "calendar:delete",  "name": "鍒犻櫎鏃ュ巻",       "resource": "calendar", "action": "delete"},
    # knowledge
    {"code": "kb:view",          "name": "鏌ョ湅鐭ヨ瘑搴?,     "resource": "kb",       "action": "view"},
    {"code": "kb:create",        "name": "鍒涘缓鐭ヨ瘑搴?,     "resource": "kb",       "action": "create"},
    {"code": "kb:update",        "name": "鏇存柊鐭ヨ瘑搴?,     "resource": "kb",       "action": "update"},
    {"code": "kb:delete",        "name": "鍒犻櫎鐭ヨ瘑搴?,     "resource": "kb",       "action": "delete"},
    {"code": "kb:import",        "name": "瀵煎叆鐭ヨ瘑搴?,     "resource": "kb",       "action": "import"},
    {"code": "kb:chat",          "name": "鐭ヨ瘑搴撻棶绛?,     "resource": "kb",       "action": "chat"},
    {"code": "kb:chat_sensitive","name": "鏁忔劅鐭ヨ瘑闂瓟",   "resource": "kb",       "action": "chat_sensitive"},
    # search
    {"code": "search:view",      "name": "鎼滅储",           "resource": "search",   "action": "view"},
    # notices
    {"code": "notice:view",      "name": "鏌ョ湅閫氱煡",       "resource": "notice",   "action": "view"},
    {"code": "notice:create",    "name": "鍒涘缓閫氱煡",       "resource": "notice",   "action": "create"},
    {"code": "notice:update",    "name": "鏇存柊閫氱煡",       "resource": "notice",   "action": "update"},
    {"code": "notice:delete",    "name": "鍒犻櫎閫氱煡",       "resource": "notice",   "action": "delete"},
    {"code": "notice:publish",   "name": "鍙戝竷閫氱煡",       "resource": "notice",   "action": "publish"},
    # 鈹€鈹€ Phase 1: enterprise module permissions (22 new) 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
    # repair (鎶ヤ慨)
    {"code": "repair:view",      "name": "鏌ョ湅鎶ヤ慨",       "resource": "repair",   "action": "view"},
    {"code": "repair:create",    "name": "鍒涘缓鎶ヤ慨",       "resource": "repair",   "action": "create"},
    {"code": "repair:assign",    "name": "娲惧崟",           "resource": "repair",   "action": "assign"},
    {"code": "repair:update",    "name": "鏇存柊鎶ヤ慨",       "resource": "repair",   "action": "update"},
    {"code": "repair:close",     "name": "鍏抽棴鎶ヤ慨",       "resource": "repair",   "action": "close"},
    # asset (璧勪骇)
    {"code": "asset:view",       "name": "鏌ョ湅璧勪骇",       "resource": "asset",    "action": "view"},
    {"code": "asset:create",     "name": "鍒涘缓璧勪骇",       "resource": "asset",    "action": "create"},
    {"code": "asset:update",     "name": "鏇存柊璧勪骇",       "resource": "asset",    "action": "update"},
    {"code": "asset:borrow",     "name": "鍊熺敤璧勪骇",       "resource": "asset",    "action": "borrow"},
    # oa (OA 瀹℃壒)
    {"code": "oa:view",          "name": "鏌ョ湅OA",         "resource": "oa",       "action": "view"},
    {"code": "oa:create",        "name": "鍒涘缓OA",         "resource": "oa",       "action": "create"},
    {"code": "oa:update",        "name": "鏇存柊OA",         "resource": "oa",       "action": "update"},
    # hr (浜轰簨)
    {"code": "hr:view",          "name": "鏌ョ湅浜轰簨",       "resource": "hr",       "action": "view"},
    {"code": "hr:create",        "name": "鍒涘缓浜轰簨",       "resource": "hr",       "action": "create"},
    {"code": "hr:update",        "name": "鏇存柊浜轰簨",       "resource": "hr",       "action": "update"},
    # finance (璐㈠姟)
    {"code": "finance:view",     "name": "鏌ョ湅璐㈠姟",       "resource": "finance",  "action": "view"},
    {"code": "finance:create",   "name": "鍒涘缓璐㈠姟",       "resource": "finance",  "action": "create"},
    {"code": "finance:approve",  "name": "瀹℃壒璐㈠姟",       "resource": "finance",  "action": "approve"},
    # subsystem (瀛愮郴缁熺鐞?
    {"code": "subsystem:view",   "name": "鏌ョ湅瀛愮郴缁?,     "resource": "subsystem","action": "view"},
    {"code": "subsystem:manage", "name": "绠＄悊瀛愮郴缁?,     "resource": "subsystem","action": "manage"},
    # dashboard (浠〃鏉?
    {"code": "dashboard:view",   "name": "鏌ョ湅浠〃鏉?,     "resource": "dashboard","action": "view"},
    # enterprise records (浼佷笟璁板綍鎬昏)
    {"code": "enterprise:records:view", "name": "鏌ョ湅浼佷笟璁板綍", "resource": "enterprise", "action": "records:view"},
]

# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# System roles (matching rbac-design-v2.md 搂5.2)
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

ROLES: list[dict[str, Any]] = [
    {"code": "super_admin", "name": "瓒呯骇绠＄悊鍛?, "description": "骞冲彴绾х鐞嗗憳锛屾嫢鏈夋墍鏈夋潈闄?,              "is_system": True},
    {"code": "org_admin",   "name": "缁勭粐绠＄悊鍛?, "description": "绠＄悊鏈粍缁囬厤缃拰涓氬姟鏁版嵁",                "is_system": True},
    {"code": "dept_leader", "name": "閮ㄩ棬璐熻矗浜?, "description": "绠＄悊鏈儴闂ㄥ強涓嬬骇閮ㄩ棬涓氬姟鏁版嵁",            "is_system": True},
    {"code": "dept_staff",  "name": "閮ㄩ棬鍛樺伐",   "description": "绠＄悊涓汉浠诲姟銆佹棩绋嬪拰鐭ヨ瘑",                "is_system": True},
    {"code": "external",    "name": "澶栭儴鐢ㄦ埛",   "description": "浠呭彲璁块棶鍏紑鍐呭",                        "is_system": True},
]

# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# Role 鈫?permission mapping (matching rbac-permission-matrix.md 搂2.2)
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

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
        "notice:view", "notice:create", "notice:update", "notice:delete", "notice:publish",
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
        "notice:view", "notice:create", "notice:update", "notice:publish",
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

# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# Permission groups for admin UI checkbox grid
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

PERMISSION_GROUPS: dict[str, dict[str, str | list[dict[str, str]]]] = {
    "鐢ㄦ埛绠＄悊": {
        "resource": "user",
        "permissions": [
            {"code": "user:view",        "name": "鏌ョ湅鐢ㄦ埛"},
            {"code": "user:create",      "name": "鍒涘缓鐢ㄦ埛"},
            {"code": "user:update",      "name": "鏇存柊鐢ㄦ埛"},
            {"code": "user:disable",     "name": "绂佺敤鐢ㄦ埛"},
            {"code": "user:assign_role", "name": "鍒嗛厤瑙掕壊"},
        ],
    },
    "缁勭粐绠＄悊": {
        "resource": "org",
        "permissions": [
            {"code": "org:view",   "name": "鏌ョ湅缁勭粐"},
            {"code": "org:update", "name": "鏇存柊缁勭粐"},
        ],
    },
    "閮ㄩ棬绠＄悊": {
        "resource": "dept",
        "permissions": [
            {"code": "dept:view",   "name": "鏌ョ湅閮ㄩ棬"},
            {"code": "dept:update", "name": "鏇存柊閮ㄩ棬"},
        ],
    },
    "绯荤粺閰嶇疆": {
        "resource": "system",
        "permissions": [
            {"code": "system:config", "name": "绯荤粺閰嶇疆"},
        ],
    },
    "鎿嶄綔瀹¤": {
        "resource": "audit",
        "permissions": [
            {"code": "audit:view", "name": "鏌ョ湅瀹¤"},
        ],
    },
    "浠诲姟": {
        "resource": "task",
        "permissions": [
            {"code": "task:view",   "name": "鏌ョ湅浠诲姟"},
            {"code": "task:create", "name": "鍒涘缓浠诲姟"},
            {"code": "task:update", "name": "鏇存柊浠诲姟"},
            {"code": "task:delete", "name": "鍒犻櫎浠诲姟"},
        ],
    },
    "鏃ュ巻": {
        "resource": "calendar",
        "permissions": [
            {"code": "calendar:view",   "name": "鏌ョ湅鏃ュ巻"},
            {"code": "calendar:create", "name": "鍒涘缓鏃ュ巻"},
            {"code": "calendar:update", "name": "鏇存柊鏃ュ巻"},
            {"code": "calendar:delete", "name": "鍒犻櫎鏃ュ巻"},
        ],
    },
    "鐭ヨ瘑搴?: {
        "resource": "kb",
        "permissions": [
            {"code": "kb:view",           "name": "鏌ョ湅鐭ヨ瘑搴?},
            {"code": "kb:create",         "name": "鍒涘缓鐭ヨ瘑搴?},
            {"code": "kb:update",         "name": "鏇存柊鐭ヨ瘑搴?},
            {"code": "kb:delete",         "name": "鍒犻櫎鐭ヨ瘑搴?},
            {"code": "kb:import",         "name": "瀵煎叆鐭ヨ瘑搴?},
            {"code": "kb:chat",           "name": "鐭ヨ瘑搴撻棶绛?},
            {"code": "kb:chat_sensitive", "name": "鏁忔劅鐭ヨ瘑闂瓟"},
        ],
    },
    "鎼滅储": {
        "resource": "search",
        "permissions": [
            {"code": "search:view", "name": "鎼滅储"},
        ],
    },
    "閫氱煡鍏憡": {
        "resource": "notice",
        "permissions": [
            {"code": "notice:view",   "name": "鏌ョ湅閫氱煡"},
            {"code": "notice:create", "name": "鍒涘缓閫氱煡"},
            {"code": "notice:update", "name": "鏇存柊閫氱煡"},
            {"code": "notice:delete", "name": "鍒犻櫎閫氱煡"},
            {"code": "notice:publish", "name": "鍙戝竷閫氱煡"},
        ],
    },
    "鎶ヤ慨绯荤粺": {
        "resource": "repair",
        "permissions": [
            {"code": "repair:view",   "name": "鏌ョ湅鎶ヤ慨"},
            {"code": "repair:create", "name": "鍒涘缓鎶ヤ慨"},
            {"code": "repair:assign", "name": "娲惧崟"},
            {"code": "repair:update", "name": "鏇存柊鎶ヤ慨"},
            {"code": "repair:close",  "name": "鍏抽棴鎶ヤ慨"},
        ],
    },
    "璧勪骇绯荤粺": {
        "resource": "asset",
        "permissions": [
            {"code": "asset:view",   "name": "鏌ョ湅璧勪骇"},
            {"code": "asset:create", "name": "鍒涘缓璧勪骇"},
            {"code": "asset:update", "name": "鏇存柊璧勪骇"},
            {"code": "asset:borrow", "name": "鍊熺敤璧勪骇"},
        ],
    },
    "OA 绯荤粺": {
        "resource": "oa",
        "permissions": [
            {"code": "oa:view",   "name": "鏌ョ湅OA"},
            {"code": "oa:create", "name": "鍒涘缓OA"},
            {"code": "oa:update", "name": "鏇存柊OA"},
        ],
    },
    "浜轰簨绯荤粺": {
        "resource": "hr",
        "permissions": [
            {"code": "hr:view",   "name": "鏌ョ湅浜轰簨"},
            {"code": "hr:create", "name": "鍒涘缓浜轰簨"},
            {"code": "hr:update", "name": "鏇存柊浜轰簨"},
        ],
    },
    "璐㈠姟绯荤粺": {
        "resource": "finance",
        "permissions": [
            {"code": "finance:view",    "name": "鏌ョ湅璐㈠姟"},
            {"code": "finance:create",  "name": "鍒涘缓璐㈠姟"},
            {"code": "finance:approve", "name": "瀹℃壒璐㈠姟"},
        ],
    },
    "瀛愮郴缁熺鐞?: {
        "resource": "subsystem",
        "permissions": [
            {"code": "subsystem:view",   "name": "鏌ョ湅瀛愮郴缁?},
            {"code": "subsystem:manage", "name": "绠＄悊瀛愮郴缁?},
        ],
    },
    "浠〃鏉?: {
        "resource": "dashboard",
        "permissions": [
            {"code": "dashboard:view", "name": "鏌ョ湅浠〃鏉?},
        ],
    },
    "浼佷笟璁板綍": {
        "resource": "enterprise",
        "permissions": [
            {"code": "enterprise:records:view", "name": "鏌ョ湅浼佷笟璁板綍"},
        ],
    },
}


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# Default seed data
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

DEFAULT_ORG_ID = "default"
DEFAULT_DEPT_ID = "HQ"
DEFAULT_DEPT_NAME = "鎬婚儴"
SYSTEM_SEED_USERNAME = "system_seed"
SYSTEM_SEED_DISPLAY = "绯荤粺绉嶅瓙鐢ㄦ埛"

# bcrypt hash of a mandatory-change password 鈥?the account is disabled
# (is_active=0) by default.  Phase 2 will enforce a forced password change
# on first successful authentication.
SYSTEM_SEED_PASSWORD_HASH = "$2b$12$MeUrwDTjryFVbkrtQPTU1.4pmwZX0qcvZbGUguk9bdMl7Yqjy6ey6"


# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€
# Seed helpers (called from migration)
# 鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€鈹€

def seed_org_and_dept(conn: Any) -> None:
    """Insert default org and HQ department if they do not exist."""
    org_exists = conn.exec_driver_sql(
        "SELECT 1 FROM orgs WHERE id='default'"
    ).fetchone()
    if org_exists is None:
        conn.exec_driver_sql(
            "INSERT INTO orgs (id, name, is_active, created_at, updated_at) "
            "VALUES ('default', '榛樿缁勭粐', 1, :ts, :ts)",
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
        # Membership: system_seed 鈫?default org
        conn.exec_driver_sql(
            "INSERT INTO user_org_memberships (user_id, org_id, is_default, created_at) "
            "VALUES (1, 'default', 1, :ts)",
            {"ts": _ts()},
        )
        # Membership: system_seed 鈫?HQ dept
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
