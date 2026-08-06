#!/bin/bash
# ---------------------------------------------------------------------------
# init-admin.sh — Idempotent admin user bootstrap
# ---------------------------------------------------------------------------
# Reads ADMIN_USERNAME / ADMIN_PASSWORD / ADMIN_EMAIL from environment.
# Creates the admin user (with bcrypt password) and binds the super_admin
# role if they do not already exist.  Safe to run on every container start.
# ---------------------------------------------------------------------------
set -euo pipefail

# ── Guard: skip if credentials are not configured ──────────────────────
if [ -z "${ADMIN_USERNAME:-}" ] || [ -z "${ADMIN_PASSWORD:-}" ]; then
    echo "[init-admin] ADMIN_USERNAME or ADMIN_PASSWORD not set — skipping admin bootstrap"
    exit 0
fi

echo "[init-admin] Checking admin user '${ADMIN_USERNAME}'..."

python3 -c "
import bcrypt
import os
import sys

from store import store
from config import get_settings

settings = get_settings()
username = settings.ADMIN_USERNAME
password = settings.ADMIN_PASSWORD
email   = settings.ADMIN_EMAIL or 'admin@example.com'

# ── Check whether admin already exists ──────────────────────────────
existing = store._db_fetch_one('users', username=username)
if existing is not None:
    print(f'[init-admin] Admin user \"{username}\" already exists (id={existing[\"id\"]}) — skipping')
    sys.exit(0)

# ── Create admin user ───────────────────────────────────────────────
pwd_hash = bcrypt.hashpw(
    password.encode('utf-8'),
    bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS),
).decode('utf-8')

from store import users, user_role_bindings
from sqlalchemy import select

engine = store._engine
with engine.begin() as conn:
    # Insert user
    result = conn.execute(
        users.insert().values(
            username=username,
            password_hash=pwd_hash,
            email=email,
            display_name='Administrator',
            is_active=True,
            org_id='default',
            department_id='hq',
            created_at=__import__('datetime').datetime.utcnow().isoformat(),
        )
    )
    user_id = result.inserted_primary_key[0]

    # Bind super_admin role (role id 1 = super_admin in seed data)
    # First find the super_admin role
    from store import roles
    role_row = conn.execute(
        select(roles.c.id).where(roles.c.code == 'super_admin')
    ).first()
    if role_row is None:
        print('[init-admin] WARNING: super_admin role not found — skipping role binding')
    else:
        conn.execute(
            user_role_bindings.insert().values(
                user_id=user_id,
                role_id=role_row[0],
                org_id='default',
            )
        )

    print(f'[init-admin] Created admin user \"{username}\" (id={user_id}) with super_admin role')

print('[init-admin] Bootstrap complete.')
"
