"""Replica 用户管理脚本 — 激活 system_seed 或创建新用户。

用法::

    # 激活 system_seed（交互式输入新密码）
    python manage_users.py activate-system-seed

    # 激活 system_seed（命令行指定密码）
    python manage_users.py activate-system-seed --password "MySecurePass123"

    # 创建新管理员用户
    python manage_users.py create-admin --username admin --password "MySecurePass123"

    # 创建普通用户
    python manage_users.py create-user --username zhangsan --password "MySecurePass123"

    # 列出所有用户
    python manage_users.py list-users

    # 重置用户密码
    python manage_users.py reset-password --username admin --password "NewPass456"

    # 启用/禁用一个用户
    python manage_users.py set-active --username admin --active yes
    python manage_users.py set-active --username admin --active no

    # 赋予/撤销角色
    python manage_users.py grant-role --username admin --role super_admin
    python manage_users.py revoke-role --username admin --role editor
"""

from __future__ import annotations

import argparse
import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure the backend package is importable
_backend_root = Path(__file__).resolve().parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from sqlalchemy import text
from sqlalchemy.orm import Session

from auth.password import hash_password
from config import get_settings
from session import get_session_local


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_migrations(db: Session) -> None:
    """Run any pending Alembic migrations."""
    from alembic.config import Config
    from alembic import command

    alembic_ini = _backend_root / "alembic.ini"
    if not alembic_ini.exists():
        print("[warn] alembic.ini not found — skipping migrations")
        return

    cfg = Config(str(alembic_ini))
    # Point to the right database
    cfg.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

    try:
        command.upgrade(cfg, "head")
        print("[ok] Migrations up to date")
    except Exception as exc:
        print(f"[warn] Migration check failed: {exc}")


def _get_db() -> Session:
    """Return a database session."""
    return get_session_local()()


# ═══════════════════════════════════════════════════════════════════════
# Commands
# ═══════════════════════════════════════════════════════════════════════


def _ensure_db_ready(db: Session) -> None:
    """Make sure the DB exists with all tables. Run once at start of any command."""
    _ensure_migrations(db)


def cmd_activate_system_seed(args: argparse.Namespace) -> None:
    """Activate system_seed and set a real password."""
    password = args.password or _prompt_password("system_seed 的新密码")
    if not password:
        print("[error] 密码不能为空")
        sys.exit(1)

    if len(password) < 8:
        print("[error] 密码长度至少 8 位")
        sys.exit(1)

    db = _get_db()
    try:
        _ensure_db_ready(db)
        with db.begin():
            row = db.execute(
                text("SELECT id, username, is_active FROM users WHERE username = 'system_seed'")
            ).fetchone()

            if row is None:
                print("[error] system_seed 用户不存在——请先运行 migration (alembic upgrade head)")
                sys.exit(1)

            uid, username, is_active = row
            new_hash = hash_password(password)

            db.execute(
                text(
                    "UPDATE users SET password_hash = :pw, is_active = 1, "
                    "must_change_password = 0, token_version = token_version + 1, "
                    "updated_at = :ts WHERE id = :uid"
                ),
                {"pw": new_hash, "ts": _ts(), "uid": uid},
            )

            # Revoke all pending sessions (clean slate)
            db.execute(
                text("UPDATE auth_sessions SET revoked_at = :ts WHERE user_id = :uid AND revoked_at IS NULL"),
                {"ts": _ts(), "uid": uid},
            )

        print(f"[ok] system_seed 已激活，请使用新密码登录")
        print(f"     用户名: system_seed")
    finally:
        db.close()


def cmd_create_user(args: argparse.Namespace) -> None:
    """Create a new user (admin or regular)."""
    username: str = args.username
    password: str = args.password or ""
    display_name: str = args.display_name or username
    email: str | None = args.email or None
    is_admin: bool = args.admin

    if not password:
        password = _prompt_password(f"{username} 的密码")
    if not password:
        print("[error] 密码不能为空")
        sys.exit(1)
    if len(password) < 8:
        print("[error] 密码长度至少 8 位")
        sys.exit(1)
    if len(username) < 1 or len(username) > 64:
        print("[error] 用户名长度须在 1–64 之间")
        sys.exit(1)

    db = _get_db()
    try:
        _ensure_db_ready(db)
        new_hash = hash_password(password)

        with db.begin():
            # Ensure seed data exists (org, dept, roles, permissions)
            _ensure_seed_data(db.connection())

            # Check username uniqueness inside the transaction
            existing = db.execute(
                text("SELECT id FROM users WHERE username = :un"),
                {"un": username},
            ).fetchone()
            if existing:
                print(f"[error] 用户名 '{username}' 已存在")
                sys.exit(1)

            result = db.execute(
                text(
                    "INSERT INTO users (username, password_hash, display_name, email, "
                    "is_active, token_version, must_change_password, created_at, updated_at) "
                    "VALUES (:un, :pw, :dn, :em, 1, 1, 0, :ts, :ts)"
                ),
                {"un": username, "pw": new_hash, "dn": display_name, "em": email, "ts": _ts()},
            )
            uid = result.lastrowid

            # Add org membership
            db.execute(
                text(
                    "INSERT OR IGNORE INTO user_org_memberships (user_id, org_id, is_default, created_at) "
                    "VALUES (:uid, 'default', 1, :ts)"
                ),
                {"uid": uid, "ts": _ts()},
            )

            # Add department membership
            db.execute(
                text(
                    "INSERT OR IGNORE INTO user_department_memberships "
                    "(user_id, org_id, department_id, is_primary, created_at) "
                    "VALUES (:uid, 'default', 'HQ', 1, :ts)"
                ),
                {"uid": uid, "ts": _ts()},
            )

            # Bind role
            role_code = "super_admin" if is_admin else "dept_staff"
            role_row = db.execute(
                text("SELECT id FROM roles WHERE code = :rc"),
                {"rc": role_code},
            ).fetchone()
            if role_row:
                db.execute(
                    text(
                        "INSERT OR IGNORE INTO role_bindings "
                        "(user_id, role_id, org_id, department_id, created_at) "
                        "VALUES (:uid, :rid, 'default', 'HQ', :ts)"
                    ),
                    {"uid": uid, "rid": role_row[0], "ts": _ts()},
                )

        role_label = "超级管理员 (super_admin)" if is_admin else "普通成员 (member)"
        print(f"[ok] 用户 '{username}' 创建成功")
        print(f"     ID: {uid}")
        print(f"     角色: {role_label}")
        print(f"     请使用密码登录: {password}")
    finally:
        db.close()


def cmd_list_users(args: argparse.Namespace) -> None:
    """List all users with status."""
    db = _get_db()
    try:
        _ensure_db_ready(db)
        rows = db.execute(
            text(
                "SELECT u.id, u.username, u.display_name, u.is_active, u.must_change_password, "
                "u.last_login_at, "
                "GROUP_CONCAT(r.name, ', ') AS roles "
                "FROM users u "
                "LEFT JOIN role_bindings rb ON rb.user_id = u.id "
                "LEFT JOIN roles r ON r.id = rb.role_id "
                "GROUP BY u.id ORDER BY u.id"
            )
        ).fetchall()

        if not rows:
            print("(无用户)")
            return

        print(f"{'ID':<5} {'用户名':<20} {'显示名':<15} {'活跃':<5} {'强制改密':<8} {'角色'}")
        print("-" * 100)
        for row in rows:
            uid, un, dn, active, mcp, last_login, roles = row
            active_str = "是" if int(active) == 1 else "否"
            mcp_str = "是" if mcp and int(mcp) == 1 else "否"
            roles_str = roles or "—"
            last = last_login[:16] if last_login else "从未登录"
            print(f"{uid:<5} {un:<20} {(dn or ''):<15} {active_str:<5} {mcp_str:<8} {roles_str}")
    finally:
        db.close()


def cmd_reset_password(args: argparse.Namespace) -> None:
    """Reset a user's password (invalidate all sessions)."""
    username: str = args.username
    password: str = args.password or ""
    if not password:
        password = _prompt_password(f"{username} 的新密码")
    if not password:
        print("[error] 密码不能为空")
        sys.exit(1)
    if len(password) < 8:
        print("[error] 密码长度至少 8 位")
        sys.exit(1)

    db = _get_db()
    try:
        _ensure_db_ready(db)
        with db.begin():
            row = db.execute(
                text("SELECT id FROM users WHERE username = :un"),
                {"un": username},
            ).fetchone()
            if row is None:
                print(f"[error] 用户 '{username}' 不存在")
                sys.exit(1)

            uid = row[0]
            new_hash = hash_password(password)
            db.execute(
                text(
                    "UPDATE users SET password_hash = :pw, token_version = token_version + 1, "
                    "updated_at = :ts WHERE id = :uid"
                ),
                {"pw": new_hash, "ts": _ts(), "uid": uid},
            )
            db.execute(
                text("UPDATE auth_sessions SET revoked_at = :ts WHERE user_id = :uid AND revoked_at IS NULL"),
                {"ts": _ts(), "uid": uid},
            )
        print(f"[ok] 用户 '{username}' 密码已重置，所有会话已撤销")
    finally:
        db.close()


def cmd_set_active(args: argparse.Namespace) -> None:
    """Enable or disable a user."""
    username: str = args.username
    active_flag = 1 if args.active.lower() in ("yes", "true", "1", "on") else 0
    label = "启用" if active_flag else "禁用"

    db = _get_db()
    try:
        _ensure_db_ready(db)
        with db.begin():
            row = db.execute(
                text("SELECT id FROM users WHERE username = :un"),
                {"un": username},
            ).fetchone()
            if row is None:
                print(f"[error] 用户 '{username}' 不存在")
                sys.exit(1)

            uid = row[0]
            db.execute(
                text("UPDATE users SET is_active = :flag, token_version = token_version + 1, updated_at = :ts WHERE id = :uid"),
                {"flag": active_flag, "ts": _ts(), "uid": uid},
            )
            if not active_flag:
                db.execute(
                    text("UPDATE auth_sessions SET revoked_at = :ts WHERE user_id = :uid AND revoked_at IS NULL"),
                    {"ts": _ts(), "uid": uid},
                )
        print(f"[ok] 用户 '{username}' 已{label}")
    finally:
        db.close()


def cmd_grant_role(args: argparse.Namespace) -> None:
    """Grant a role to a user."""
    username: str = args.username
    role_code: str = args.role

    db = _get_db()
    try:
        _ensure_db_ready(db)
        with db.begin():
            user_row = db.execute(
                text("SELECT id FROM users WHERE username = :un"),
                {"un": username},
            ).fetchone()
            if user_row is None:
                print(f"[error] 用户 '{username}' 不存在")
                sys.exit(1)

            role_row = db.execute(
                text("SELECT id FROM roles WHERE code = :rc"),
                {"rc": role_code},
            ).fetchone()
            if role_row is None:
                valid = db.execute(text("SELECT code FROM roles ORDER BY code")).fetchall()
                codes = ", ".join(r[0] for r in valid)
                print(f"[error] 角色 '{role_code}' 不存在。可用角色: {codes}")
                sys.exit(1)

            uid, rid = user_row[0], role_row[0]
            existing = db.execute(
                text("SELECT 1 FROM role_bindings WHERE user_id = :uid AND role_id = :rid AND org_id = 'default'"),
                {"uid": uid, "rid": rid},
            ).fetchone()
            if existing:
                print(f"[info] 用户 '{username}' 已拥有角色 '{role_code}'，无需重复绑定")
            else:
                db.execute(
                    text(
                        "INSERT INTO role_bindings (user_id, role_id, org_id, department_id, created_at) "
                        "VALUES (:uid, :rid, 'default', 'HQ', :ts)"
                    ),
                    {"uid": uid, "rid": rid, "ts": _ts()},
                )
                print(f"[ok] 已为用户 '{username}' 赋予角色 '{role_code}'")

        # Bump token_version so next refresh picks up new roles
        with db.begin():
            db.execute(
                text("UPDATE users SET token_version = token_version + 1, updated_at = :ts WHERE id = :uid"),
                {"uid": uid, "ts": _ts()},
            )
    finally:
        db.close()


def cmd_revoke_role(args: argparse.Namespace) -> None:
    """Revoke a role from a user."""
    username: str = args.username
    role_code: str = args.role

    db = _get_db()
    try:
        _ensure_db_ready(db)
        with db.begin():
            user_row = db.execute(
                text("SELECT id FROM users WHERE username = :un"),
                {"un": username},
            ).fetchone()
            if user_row is None:
                print(f"[error] 用户 '{username}' 不存在")
                sys.exit(1)

            role_row = db.execute(
                text("SELECT id FROM roles WHERE code = :rc"),
                {"rc": role_code},
            ).fetchone()
            if role_row is None:
                print(f"[error] 角色 '{role_code}' 不存在")
                sys.exit(1)

            uid, rid = user_row[0], role_row[0]
            result = db.execute(
                text(
                    "DELETE FROM role_bindings WHERE user_id = :uid AND role_id = :rid AND org_id = 'default'"
                ),
                {"uid": uid, "rid": rid},
            )
            if result.rowcount == 0:
                print(f"[info] 用户 '{username}' 本就不拥有角色 '{role_code}'")
            else:
                print(f"[ok] 已从用户 '{username}' 撤销角色 '{role_code}'")

        with db.begin():
            db.execute(
                text("UPDATE users SET token_version = token_version + 1, updated_at = :ts WHERE id = :uid"),
                {"uid": uid, "ts": _ts()},
            )
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════


def _prompt_password(label: str) -> str:
    """Prompt the user to enter and confirm a password interactively."""
    try:
        pw1 = getpass.getpass(f"  {label}: ")
        pw2 = getpass.getpass(f"  确认密码: ")
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)

    if pw1 != pw2:
        print("[error] 两次输入不一致")
        sys.exit(1)
    return pw1


def _ensure_seed_data(conn: Any) -> None:
    """Make sure the minimum seed data (org, dept, roles) exists.

    *conn* must be a raw DBAPI connection or a SQLAlchemy Connection that is
    already inside a transaction.  Call this from within a ``with db.begin()``
    block (pass ``db.connection()``).
    """
    from authorization.permissions import (
        seed_org_and_dept,
        seed_users,
        seed_roles,
        seed_permissions,
        seed_role_permissions,
        seed_role_bindings,
    )

    seed_org_and_dept(conn)
    seed_roles(conn)
    seed_permissions(conn)
    seed_role_permissions(conn)
    seed_users(conn)
    seed_role_bindings(conn)


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replica 用户管理脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", help="可用命令")

    # activate-system-seed
    p_activate = sub.add_parser("activate-system-seed", help="激活 system_seed 并设置密码")
    p_activate.add_argument("--password", help="新密码（不指定则交互输入）")
    p_activate.set_defaults(func=cmd_activate_system_seed)

    # create-admin
    p_ca = sub.add_parser("create-admin", help="创建管理员用户")
    p_ca.add_argument("--username", required=True, help="用户名")
    p_ca.add_argument("--password", help="密码（不指定则交互输入）")
    p_ca.add_argument("--display-name", help="显示名（默认同用户名）")
    p_ca.add_argument("--email", help="邮箱（可选）")
    p_ca.set_defaults(func=cmd_create_user, admin=True)

    # create-user
    p_cu = sub.add_parser("create-user", help="创建普通用户")
    p_cu.add_argument("--username", required=True, help="用户名")
    p_cu.add_argument("--password", help="密码（不指定则交互输入）")
    p_cu.add_argument("--display-name", help="显示名（默认同用户名）")
    p_cu.add_argument("--email", help="邮箱（可选）")
    p_cu.set_defaults(func=cmd_create_user, admin=False)

    # list-users
    p_list = sub.add_parser("list-users", help="列出所有用户")
    p_list.set_defaults(func=cmd_list_users)

    # reset-password
    p_rp = sub.add_parser("reset-password", help="重置用户密码")
    p_rp.add_argument("--username", required=True, help="用户名")
    p_rp.add_argument("--password", help="新密码（不指定则交互输入）")
    p_rp.set_defaults(func=cmd_reset_password)

    # set-active
    p_sa = sub.add_parser("set-active", help="启用/禁用用户")
    p_sa.add_argument("--username", required=True, help="用户名")
    p_sa.add_argument("--active", required=True, choices=["yes", "no", "true", "false", "1", "0"], help="yes/true/1 启用, no/false/0 禁用")
    p_sa.set_defaults(func=cmd_set_active)

    # grant-role
    p_gr = sub.add_parser("grant-role", help="赋予角色")
    p_gr.add_argument("--username", required=True, help="用户名")
    p_gr.add_argument("--role", required=True, help="角色代码（如 super_admin, admin, editor, viewer, member）")
    p_gr.set_defaults(func=cmd_grant_role)

    # revoke-role
    p_rr = sub.add_parser("revoke-role", help="撤销角色")
    p_rr.add_argument("--username", required=True, help="用户名")
    p_rr.add_argument("--role", required=True, help="角色代码")
    p_rr.set_defaults(func=cmd_revoke_role)

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
