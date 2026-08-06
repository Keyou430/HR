# Replica Phase 1 — Setup & Deployment Guide

## Overview

Replica is a collaborative enterprise portal platform built on FastAPI (Python backend) + vanilla JS SPA (frontend) with RBAC, audit logging, and 15 subsystems.

This guide covers Phase 1 setup: development environment, testing, and Docker-based production deployment.

---

## Quick Start (Development)

### Prerequisites
- Python 3.12+ (tested on 3.12–3.14)
- Node.js 22+
- SQLite (built-in, no install needed)
- (Optional) PostgreSQL 16 + pgvector for production

### 1. Clone & install

```bash
cd backend
pip install -r requirements.txt
```

### 2. Environment

Copy the example env file and configure:

```bash
cp .env.example .env
```

For development, the default SQLite mode is auto-detected — no DATABASE_URL change needed:

```env
# Dev defaults (auto-redirects to SQLite under pytest)
DATABASE_URL=sqlite:///./replica_platform.db
JWT_SECRET_KEY=change-me-in-production-use-openssl-rand-hex-32
ENVIRONMENT=development
DEBUG=true
```

### 3. Run migrations & seed

```bash
alembic upgrade head
```

The seed logic (`store.py:_seed_defaults()`) is idempotent — it runs on first request to any endpoint and creates:
- 5 roles (super_admin, org_admin, dept_leader, dept_staff, external)
- 53 permissions across 9 groups
- 15 subsystems (6 deep / 9 shell)
- Default org "default" and department "HQ"
- Portal assets (notices, documents, resources, services, news)

### 4. Start dev server

```bash
python main.py
# or: uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` — the API serves the SPA frontend from `../frontend/`.

### 5. Frontend dev (optional)

```bash
cd ../frontend
npm install
npm run build          # production build → dist/
```

The SPA is a vanilla JS single-page app. There's no dev server needed — open `frontend/index.html` directly, and the app detects `file://` protocol and proxies API calls to `http://localhost:8000`.

---

## Running Tests

### All tests (SQLite)

```bash
cd backend
python -m pytest -q
```

### Test file overview

| File | Focus | Tests |
|---|---|---|
| `test_subsystems_phase1.py` | Subsystem shell — menu_items, entry_type, shell config | 24 |
| `test_admin_api.py` | Admin API — users, roles, sessions, audit | 58 |
| `test_security_contract.py` | E2E RBAC — 5 roles × cross-org/cross-dept isolation | 40 |
| `test_idor.py` | IDOR — direct object reference attack vectors | 30 |
| `test_audit.py` | Audit logging — security events, retention | 31 |
| `test_search_phase1.py` | Search — scope filtering, typeahead | 22 |
| `test_frontend_contract.py` | Frontend contract — embed URLs, markup, iframe usage | 25 |
| `test_rbac.py` | RBAC functional — permission matrix, 403s | 69 |
| `test_notifications.py` | Notifications — CRUD, read/unread, isolation | 15+ |
| `test_health.py` | Health check — liveness (200), readiness (503 when DB down) | 4 |
| `test_exception_format.py` | Exception format — 404/422/500 JSON envelopes | 7 |
| **Total (green)** | **All files except known exceptions** | **~325** |

### Known exceptions (Phase 1 scope)

| File | Issue | Resolution |
|---|---|---|
| `test_enterprise_modules.py` | 3–5 failures — Phase 2 contract | Tracked; not blocking Phase 1 |
| `test_data_scope.py` | 2 failures — knowledge dataset seed missing "Public Dataset" | Minor seed issue; Phase 2 |
| `test_rbac.py` | 1 failure — dataset "ds1" doesn't exist in test DB | Mock dataset issue; Phase 2 |
| `test_portal_assets_subsystems.py` | Exit 1 | To investigate in Phase 2 |
| `test_chat_api.py` | File doesn't exist (exit 4) | Placeholder; Phase 2 |

### PostgreSQL tests (optional)

```bash
REPLICA_TEST_DATABASE_URL=postgresql+psycopg2://replica:replica@localhost:5432/replica_test \
python -m pytest -q
```

### Test architecture

- `conftest.py` — Shared fixtures: `client` (temp SQLite + migrations + seeded users), pre-authenticated role clients (`super_admin_client`, `dept_staff_client`, etc.), `all_roles_client` (returns dict of all 5 role tokens).
- Each test file can define its own `client` fixture — pytest uses the most-local definition.
- `config._pytest_database_url()` auto-redirects to per-test temp SQLite when running under pytest, preventing accidental dev DB mutations.

---

## Docker Deployment

### Prerequisites
- Docker Engine 24+
- Docker Compose v2

### 1. Configure environment

Create a `.env` file at the repo root:

```env
# Required
JWT_SECRET_KEY=<generate with: python -c "import secrets; print(secrets.token_hex(32))">

# PostgreSQL (defaults shown)
POSTGRES_DB=replica
POSTGRES_USER=replica
POSTGRES_PASSWORD=<generate a strong password>

# Admin user (optional but recommended)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<generate a strong password>
ADMIN_EMAIL=admin@example.com

# Deployment
ENVIRONMENT=production
DEBUG=false
CORS_ORIGINS=https://your-domain.com
NGINX_PORT=80
```

### 2. Build & start

```bash
docker compose up -d --build
```

This starts 4 containers:
- **postgres** — PostgreSQL 16 + pgvector (healthcheck: `pg_isready`)
- **api** — FastAPI (migrates on start, bootstraps admin, then starts uvicorn)
- **nginx** — Reverse proxy (port 80, security headers, rate limiting, gzip, SPA routing)
- **pgbackup** — Auto-backup every 6 hours (retention: `BACKUP_RETENTION_DAYS`)

### 3. Verify

```bash
# Liveness
curl http://localhost/health
# → {"status":"ok"}

# Readiness (with DB check)
curl http://localhost/health?full=true
# → {"status":"ok","database":{"ok":true,"error":null}}

# Login
curl -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"<your-admin-password>"}'
```

### 4. Backup

```bash
# Manual backup
docker compose exec pgbackup /backup.sh

# Backups are stored in the `backups` Docker volume
docker compose run --rm pgbackup ls /backups/
```

---

## API Endpoints

### Health
| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness (always 200) |
| GET | `/health?full=true` | Readiness (503 if DB down) |

### Auth
| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/login` | Login (returns JWT access + refresh tokens) |
| POST | `/api/v1/auth/refresh` | Refresh access token |

### Portal
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/portal/bootstrap` | Portal bootstrap data (embed URLs, user info) |
| GET | `/api/v1/subsystems` | List all subsystems |
| GET | `/api/v1/subsystems/{code}` | Get subsystem detail (inc. menu_items) |
| POST | `/api/v1/subsystems/{code}/visit` | Record subsystem visit |
| GET | `/api/v1/subsystems/{code}/dashboard` | Subsystem dashboard |

### Portal Assets
| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/v1/portal/notices` | Notices |
| GET/POST | `/api/v1/portal/documents` | Documents |
| GET/POST | `/api/v1/portal/resources` | Resources |
| GET/POST | `/api/v1/portal/services` | Services |
| GET/POST | `/api/v1/portal/news` | News |

### Tasks & Calendar
| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/v1/tasks` | Tasks |
| PATCH/DELETE | `/api/v1/tasks/{id}` | Task update/delete |
| GET/POST | `/api/v1/calendar/events` | Calendar events |

### Knowledge & Search
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/search?q=` | Global search |
| GET/POST | `/api/v1/knowledge/mappings` | Knowledge dataset mappings |
| POST | `/api/v1/knowledge/sync` | Sync knowledge datasets |
| POST | `/api/v1/knowledge/import` | Import file to dataset |
| POST | `/api/v1/knowledge/chat` | Knowledge chat |

### Notifications
| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/notifications` | List notifications |
| GET | `/api/v1/notifications/unread-count` | Unread count |
| PUT | `/api/v1/notifications/{id}/read` | Mark as read |
| PUT | `/api/v1/notifications/read-all` | Mark all read |

### Admin
| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/v1/admin/users` | User management |
| GET/POST | `/api/v1/admin/roles` | Role CRUD |
| PUT | `/api/v1/admin/roles/{id}/permissions` | Set role permissions |
| GET | `/api/v1/admin/permissions` | List permissions (grouped) |
| GET/POST | `/api/v1/admin/orgs` | Organization management |
| GET/POST | `/api/v1/admin/departments` | Department management |
| GET | `/api/v1/admin/audit` | Audit log viewer |
| GET | `/api/v1/admin/audit/export` | Export audit log as CSV |

---

## Architecture

### Backend
- **Framework**: FastAPI (async, Pydantic v2)
- **Database**: PostgreSQL 16 + pgvector (prod), SQLite (dev/test)
- **Migrations**: Alembic (6 migrations: 001–006)
- **Auth**: JWT (HS256), bcrypt password hashing, refresh token rotation
- **RBAC**: 5 roles × 53 permissions, 3-dimension scope (org / dept / owner)
- **Audit**: Request-level middleware + explicit event logging
- **Store pattern**: Singleton `PortalStore` with mixin-based sub-stores

### Frontend
- **Architecture**: Vanilla JS SPA (no framework)
- **Routing**: Hash-based client-side router
- **State**: Global `state` object with reactive rendering
- **Components**: Custom elements (`<data-table>`, `<app-modal>`, `<app-drawer>`, `<status-badge>`, `<empty-state>`, `<notification-bell>`, `<app-sidebar>`, `<search-box>`)
- **Styling**: Custom CSS with liquid-metal design system, responsive 3-breakpoint layout

### Docker
- **api**: Python 3.12-slim, non-root user, JSON logging (production)
- **nginx**: Security headers (HSTS, CSP, X-Frame-Options), rate limiting (login 10r/s, general 30r/s), gzip, SPA routing
- **postgres**: pgvector/pgvector:pg16, persistent volume, healthcheck
- **pgbackup**: pg_dump -Fc every 6h, retention-based cleanup

---

## Security

### Authentication
- JWT access tokens (15 min) + refresh tokens (7 days)
- bcrypt password hashing (configurable rounds, default 12)
- Login rate limiting (5 attempts / 5 min window)
- Token version invalidation on password change

### Authorization
- 5 roles: super_admin, org_admin, dept_leader, dept_staff, external
- 53 fine-grained permissions across 9 groups
- 3-dimension data scope: org / department / owner
- Cross-org and cross-dept isolation enforced at SQL level

### Headers (nginx)
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Content-Security-Policy` with restricted frame-src

---

## Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://...` | Database connection URL |
| `JWT_SECRET_KEY` | (required) | HS256 signing key (min 32 chars) |
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` |
| `DEBUG` | `true` | Enable debug mode (dev only) |
| `CORS_ORIGINS` | `http://localhost:5173,...` | Comma-separated allowed origins |
| `POSTGRES_HOST/PORT/DB/USER/PASSWORD` | `localhost/5432/replica/replica/replica` | PG connection details |
| `POOL_SIZE` | `10` | SQLAlchemy pool size |
| `MAX_OVERFLOW` | `20` | SQLAlchemy max overflow |
| `ADMIN_USERNAME/PASSWORD/EMAIL` | (empty) | Bootstrap admin user |
| `BACKUP_RETENTION_DAYS` | `14` | Backup retention period |
| `AUDIT_ENABLED` | `true` | Enable audit logging |
| `AUDIT_RETENTION_DAYS` | `90` | Audit log retention |
| `JSON_LOGS` | `true` (prod) | JSON-structured log output |
| `NGINX_PORT` | `80` | Nginx listen port |
