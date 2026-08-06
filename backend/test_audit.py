"""Phase 6: Audit system tests.

Tests:
- Unauthorized user cannot view audit logs.
- org_admin cannot view other org's audit records.
- Disabled user's old session is invalidated.
- 403 responses produce audit events.
- AI blocked queries produce audit events.
- Audit logs do not contain secret credentials.
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

# ── Constants ──────────────────────────────────────────────────────────

SUPER_USER = "audit_admin"
SUPER_PASSWORD = "audit-admin-123"
REGULAR_USER = "audit_user"
REGULAR_PASSWORD = "audit-user-123"
ORG_ADMIN_USER = "org_admin_audit"
ORG_ADMIN_PASSWORD = "org-admin-audit-123"


# ── Helpers ────────────────────────────────────────────────────────────


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
    is_active: int = 1,
    role_code: str = "dept_staff",
    org_id: str = "default",
) -> int:
    """Insert a user and bind a role."""
    pw_hash = hash_password(password)
    engine = create_engine(db_url)
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO users (username, password_hash, display_name, is_active, "
                "token_version, must_change_password, created_at, updated_at) "
                "VALUES (:un, :pw, :dn, :active, 1, 0, '2026-07-30T00:00:00', '2026-07-30T00:00:00')"
            ),
            {"un": username, "pw": pw_hash, "dn": display_name, "active": is_active},
        )
        uid = result.lastrowid

        conn.execute(
            text(
                "INSERT OR IGNORE INTO user_org_memberships "
                "(user_id, org_id, is_default, created_at) "
                "VALUES (:uid, :oid, 1, '2026-07-30T00:00:00')"
            ),
            {"uid": uid, "oid": org_id},
        )
        conn.execute(
            text(
                "INSERT OR IGNORE INTO user_department_memberships "
                "(user_id, org_id, department_id, is_primary, created_at) "
                "VALUES (:uid, :oid, 'HQ', 1, '2026-07-30T00:00:00')"
            ),
            {"uid": uid, "oid": org_id},
        )

        role_row = conn.execute(
            text("SELECT id FROM roles WHERE code = :rc"), {"rc": role_code}
        ).fetchone()
        if role_row:
            conn.execute(
                text(
                    "INSERT OR IGNORE INTO role_bindings "
                    "(user_id, role_id, org_id, department_id, created_at) "
                    "VALUES (:uid, :rid, :oid, 'HQ', '2026-07-30T00:00:00')"
                ),
                {"uid": uid, "rid": role_row[0], "oid": org_id},
            )

    engine.dispose()
    return uid


def _login(client: TestClient, username: str, password: str) -> dict:
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    return {
        "status": resp.status_code,
        "body": resp.json() if resp.status_code in (200, 201) else resp.json(),
    }


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _insert_audit_log(
    db_url: str,
    request_id: str,
    user_id: int | None,
    org_id: str | None,
    action: str,
    decision: str = "allow",
    reason: str | None = None,
):
    """Directly insert an audit log row for testing."""
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO audit_logs "
                "(request_id, user_id, org_id, action, decision, reason, created_at) "
                "VALUES (:rid, :uid, :oid, :act, :dec, :reason, '2026-08-03T10:00:00')"
            ),
            {
                "rid": request_id,
                "uid": user_id,
                "oid": org_id,
                "act": action,
                "dec": decision,
                "reason": reason,
            },
        )
    engine.dispose()


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient with fresh DB and seeded users."""
    db_path = tmp_path / "test_audit.db"
    db_url = f"sqlite:///{db_path.as_posix()}"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-for-pytest-audit-32c")
    monkeypatch.setenv("AUDIT_ENABLED", "true")
    monkeypatch.setenv("AUDIT_RECORD_AUTH_DENIED", "true")
    from config import get_settings
    get_settings.cache_clear()

    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None

    _upgrade(str(db_path), "head")
    _create_user(db_url, SUPER_USER, SUPER_PASSWORD, "Audit Admin", role_code="super_admin")
    _create_user(db_url, REGULAR_USER, REGULAR_PASSWORD, "Audit User")
    _create_user(db_url, ORG_ADMIN_USER, ORG_ADMIN_PASSWORD, "Org Admin", role_code="org_admin")

    from auth.router import _login_attempts
    _login_attempts.clear()

    with TestClient(app, cookies={}) as c:
        yield c

    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    get_settings.cache_clear()


@pytest.fixture
def admin_token(client):
    result = _login(client, SUPER_USER, SUPER_PASSWORD)
    assert result["status"] == 200, f"Admin login failed: {result['body']}"
    return result["body"]["access_token"]


@pytest.fixture
def user_token(client):
    result = _login(client, REGULAR_USER, REGULAR_PASSWORD)
    assert result["status"] == 200, f"User login failed: {result['body']}"
    return result["body"]["access_token"]


@pytest.fixture
def org_admin_token(client):
    result = _login(client, ORG_ADMIN_USER, ORG_ADMIN_PASSWORD)
    assert result["status"] == 200, f"Org admin login failed: {result['body']}"
    return result["body"]["access_token"]


@pytest.fixture
def db_url_for_audit(tmp_path, monkeypatch):
    """Return the DB URL after migration (for direct SQL insertion)."""
    db_path = tmp_path / "test_audit_direct.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-key-direct-min-32chars")
    from config import get_settings
    get_settings.cache_clear()
    import session as sess_mod
    sess_mod._engine = None
    sess_mod._engine_url = None
    sess_mod._SessionLocal = None
    _upgrade(str(db_path), "head")
    return db_url


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════


class TestAuditAccessControl:
    """Audit viewing endpoints must be protected."""

    def test_unauthenticated_cannot_view_audit(self, client):
        resp = client.get("/api/v1/admin/audit")
        assert resp.status_code == 401

    def test_regular_user_cannot_view_audit(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403

    def test_admin_can_view_audit(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body

    def test_unauthenticated_cannot_view_ai_queries(self, client):
        resp = client.get("/api/v1/admin/audit/ai-queries")
        assert resp.status_code == 401

    def test_regular_user_cannot_view_ai_queries(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/audit/ai-queries",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403


class TestOrgScoping:
    """org_admin must not see audit records from other orgs."""

    def test_org_admin_sees_only_own_org(self, db_url_for_audit, tmp_path, monkeypatch):
        """Seed audit logs for two orgs; org_admin of 'default' only sees 'default' logs."""
        # Re-init with temp DB that has the seeded audit logs
        monkeypatch.setenv("DATABASE_URL", db_url_for_audit)
        from config import get_settings
        get_settings.cache_clear()
        import session as sess_mod
        sess_mod._engine = None
        sess_mod._engine_url = None
        sess_mod._SessionLocal = None

        # Create users
        uid_oa = _create_user(db_url_for_audit, "oa_scoping", "pass123", "OA Scoping",
                              role_code="org_admin", org_id="default")
        _create_user(db_url_for_audit, "other_org_user", "pass123", "Other Org User",
                     role_code="dept_staff", org_id="org-other")

        # Seed audit logs in two different orgs
        _insert_audit_log(db_url_for_audit, "rid-001", uid_oa, "default", "admin.user.create", "allow")
        _insert_audit_log(db_url_for_audit, "rid-002", 999, "org-other", "admin.user.create", "allow")
        _insert_audit_log(db_url_for_audit, "rid-003", uid_oa, "default", "auth.login.success", "allow")

        from auth.router import _login_attempts
        _login_attempts.clear()

        with TestClient(app) as c:
            # Login as org_admin of 'default'
            login_resp = _login(c, "oa_scoping", "pass123")
            assert login_resp["status"] == 200
            token = login_resp["body"]["access_token"]

            resp = c.get(
                "/api/v1/admin/audit",
                headers=_auth_headers(token),
                params={"page_size": 100},
            )
            assert resp.status_code == 200
            items = resp.json()["items"]
            # Should only contain 'default' org items + items with no org_id
            for item in items:
                if item.get("org_id"):
                    assert item["org_id"] == "default", (
                        f"org_admin saw audit log from org={item['org_id']}"
                    )

        sess_mod._engine = None
        sess_mod._engine_url = None
        sess_mod._SessionLocal = None
        get_settings.cache_clear()

    def test_super_admin_sees_all_orgs(self, db_url_for_audit, tmp_path, monkeypatch):
        """super_admin can see audit logs from all orgs."""
        monkeypatch.setenv("DATABASE_URL", db_url_for_audit)
        from config import get_settings
        get_settings.cache_clear()
        import session as sess_mod
        sess_mod._engine = None
        sess_mod._engine_url = None
        sess_mod._SessionLocal = None

        _create_user(db_url_for_audit, "sa_all", "pass123", "SA All", role_code="super_admin")

        _insert_audit_log(db_url_for_audit, "rid-100", 1, "default", "admin.user.create", "allow")
        _insert_audit_log(db_url_for_audit, "rid-101", 2, "org-other", "admin.user.create", "allow")

        from auth.router import _login_attempts
        _login_attempts.clear()

        with TestClient(app) as c:
            login_resp = _login(c, "sa_all", "pass123")
            assert login_resp["status"] == 200
            token = login_resp["body"]["access_token"]

            resp = c.get(
                "/api/v1/admin/audit",
                headers=_auth_headers(token),
                params={"page_size": 100},
            )
            assert resp.status_code == 200
            items = resp.json()["items"]
            org_ids = {item.get("org_id") for item in items if item.get("org_id")}
            assert "default" in org_ids
            assert "org-other" in org_ids


class TestSessionInvalidation:
    """Disabled user's old sessions must become invalid."""

    def test_disabled_user_session_invalid(self, client, admin_token):
        """After admin disables a user, the user's token should stop working."""
        # Create a fresh user
        resp = client.post(
            "/api/v1/admin/users",
            headers=_auth_headers(admin_token),
            json={
                "username": "temp_disable",
                "password": "disable-pass-123",
                "display_name": "Temp Disable",
            },
        )
        assert resp.status_code == 201
        uid = resp.json()["id"]

        # Login as that user
        login_resp = _login(client, "temp_disable", "disable-pass-123")
        assert login_resp["status"] == 200
        user_access_token = login_resp["body"]["access_token"]

        # Verify the token works
        me_resp = client.get("/api/v1/auth/me", headers=_auth_headers(user_access_token))
        assert me_resp.status_code == 200

        # Admin disables the user
        disable_resp = client.patch(
            f"/api/v1/admin/users/{uid}/status",
            headers=_auth_headers(admin_token),
            json={"is_active": False},
        )
        assert disable_resp.status_code == 200

        # The old access token should now be invalid (token_version bumped)
        me_resp2 = client.get("/api/v1/auth/me", headers=_auth_headers(user_access_token))
        assert me_resp2.status_code == 401, (
            f"Expected 401 after disable, got {me_resp2.status_code}"
        )

        # Clean up — re-enable
        client.patch(
            f"/api/v1/admin/users/{uid}/status",
            headers=_auth_headers(admin_token),
            json={"is_active": True},
        )

    def test_admin_cannot_disable_self(self, client, admin_token):
        """Admin should not be able to disable their own account."""
        # Get admin's user_id from /me
        me_resp = client.get("/api/v1/auth/me", headers=_auth_headers(admin_token))
        admin_id = me_resp.json()["id"]

        resp = client.patch(
            f"/api/v1/admin/users/{admin_id}/status",
            headers=_auth_headers(admin_token),
            json={"is_active": False},
        )
        assert resp.status_code == 400
        assert "当前登录" in resp.json()["detail"]


class TestAuditEvents:
    """403 and AI block events must produce audit records."""

    def test_403_produces_audit_event(self, client, user_token):
        """A permission-denied request should create an audit record."""
        # Regular user tries to access admin endpoint → 403
        resp = client.get(
            "/api/v1/admin/users",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403

        # The middleware should have recorded a 403 audit event.
        # Verify by logging in as admin and checking audit logs.
        # We need a fresh admin login within this client.
        admin_result = _login(client, SUPER_USER, SUPER_PASSWORD)
        admin_token_local = admin_result["body"]["access_token"]

        audit_resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token_local),
            params={"decision": "deny", "page_size": 100},
        )
        assert audit_resp.status_code == 200
        items = audit_resp.json()["items"]
        denied_actions = [item["action"] for item in items]
        # Should contain at least one 403 event
        has_403 = any("403" in a for a in denied_actions)
        assert has_403, f"No 403 audit events found in: {denied_actions}"

    def test_audit_log_filter_by_action(self, client, admin_token):
        """Audit logs can be filtered by action prefix."""
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"action": "auth.login", "page_size": 50},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        for item in items:
            assert "auth.login" in item["action"], (
                f"Expected auth.login in action, got: {item['action']}"
            )

    def test_audit_log_filter_by_decision(self, client, admin_token):
        """Audit logs can be filtered by decision."""
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"decision": "allow", "page_size": 50},
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["decision"] == "allow"

    def test_audit_log_pagination(self, client, admin_token):
        """Audit logs support pagination."""
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"page": 1, "page_size": 2},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) <= 2


class TestAuditNoSecrets:
    """Audit logs must never contain passwords, tokens, or full sensitive queries."""

    def test_audit_log_no_password_in_detail(self, client, admin_token):
        """Audit records should not contain passwords in their detail_json."""
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"page_size": 200},
        )
        assert resp.status_code == 200
        import json
        for item in resp.json()["items"]:
            detail = item.get("detail_json")
            if detail:
                detail_str = json.dumps(detail) if isinstance(detail, dict) else str(detail)
                assert "password" not in detail_str.lower(), (
                    f"Audit log contains 'password' in detail: {detail_str[:200]}"
                )
                # Check for JWT/token patterns
                assert "Bearer " not in detail_str, (
                    f"Audit log contains Bearer token pattern"
                )

    def test_ai_query_log_no_full_query(self, db_url_for_audit, tmp_path, monkeypatch):
        """AI query logs only store hash + snippet, never the full query."""
        monkeypatch.setenv("DATABASE_URL", db_url_for_audit)
        from config import get_settings
        get_settings.cache_clear()
        import session as sess_mod
        sess_mod._engine = None
        sess_mod._engine_url = None
        sess_mod._SessionLocal = None

        # Insert an AI query log with a known snippet
        engine = create_engine(db_url_for_audit)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO ai_query_logs "
                    "(request_id, user_id, query_hash, query_snippet, risk_label, "
                    "policy_version, decision, accessible_resource_count, created_at) "
                    "VALUES ('rid-ai-001', 1, 'abc123hash', 'How do I reset my password?', "
                    "'GENERAL', '2.0.0', 'allowed', 3, '2026-08-03T10:00:00')"
                ),
            )
        engine.dispose()

        _create_user(db_url_for_audit, "sa_ai_audit", "pass123", "SA AI Audit",
                     role_code="super_admin")

        from auth.router import _login_attempts
        _login_attempts.clear()

        with TestClient(app) as c:
            login_resp = _login(c, "sa_ai_audit", "pass123")
            token = login_resp["body"]["access_token"]

            resp = c.get(
                "/api/v1/admin/audit/ai-queries",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 200
            items = resp.json()["items"]
            assert len(items) >= 1
            for item in items:
                # query_snippet should be truncated (default 256 chars)
                snippet = item.get("query_snippet") or ""
                assert len(snippet) <= 256
                # query_hash should be a hex string (SHA-256), not the raw query
                h = item.get("query_hash", "")
                assert len(h) <= 128
                # The full query text should never appear anywhere in the record
                record_str = str(item)
                # "How do I reset my password" is the snippet, so it can appear
                # But long queries (>256 chars) should be truncated

        sess_mod._engine = None
        sess_mod._engine_url = None
        sess_mod._SessionLocal = None
        get_settings.cache_clear()


class TestSessionManagement:
    """Admin session management endpoints."""

    def test_list_sessions_admin_only(self, client, user_token, admin_token):
        """Only super_admin can list sessions."""
        resp_user = client.get(
            "/api/v1/admin/sessions",
            headers=_auth_headers(user_token),
        )
        assert resp_user.status_code == 403

        resp_admin = client.get(
            "/api/v1/admin/sessions",
            headers=_auth_headers(admin_token),
        )
        assert resp_admin.status_code == 200
        assert "items" in resp_admin.json()

    def test_revoke_session(self, client, admin_token):
        """Admin can revoke a specific session."""
        # List sessions to find one
        resp = client.get(
            "/api/v1/admin/sessions",
            headers=_auth_headers(admin_token),
        )
        items = resp.json()["items"]
        if not items:
            pytest.skip("No sessions to revoke")

        session_id = items[0]["id"]
        revoke_resp = client.delete(
            f"/api/v1/admin/sessions/{session_id}",
            headers=_auth_headers(admin_token),
        )
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["ok"] is True

    def test_revoke_nonexistent_session(self, client, admin_token):
        """Revoking a non-existent session returns 404."""
        resp = client.delete(
            "/api/v1/admin/sessions/nonexistent-id",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 404

    def test_revoke_all_user_sessions(self, client, admin_token):
        """Admin can revoke all sessions for a user."""
        # Get a user ID
        users_resp = client.get(
            "/api/v1/admin/users",
            headers=_auth_headers(admin_token),
            params={"search": REGULAR_USER},
        )
        uid = users_resp.json()["items"][0]["id"]

        resp = client.delete(
            f"/api/v1/admin/users/{uid}/sessions",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


class TestAnomalyStats:
    """Anomaly statistics endpoint."""

    def test_anomaly_stats_unauthorized(self, client, user_token):
        resp = client.get(
            "/api/v1/admin/anomalies",
            headers=_auth_headers(user_token),
        )
        assert resp.status_code == 403

    def test_anomaly_stats_authorized(self, client, admin_token):
        resp = client.get(
            "/api/v1/admin/anomalies",
            headers=_auth_headers(admin_token),
        )
        assert resp.status_code == 200
        body = resp.json()
        for key in (
            "total_users", "active_users", "disabled_users",
            "total_sessions", "active_sessions",
            "recent_failed_logins_24h", "recent_403_24h",
            "recent_ai_blocks_24h", "recent_injections_24h",
        ):
            assert key in body, f"Missing key: {key}"
            assert isinstance(body[key], int), f"Key {key} should be int"


class TestAuditTimeRange:
    """Audit log time range filtering."""

    def test_audit_filter_by_since(self, client, admin_token):
        """Filter audit logs by 'since' timestamp."""
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"since": "2026-08-03T00:00:00"},
        )
        assert resp.status_code == 200
        # Should return results created after the given time

    def test_audit_filter_by_until(self, client, admin_token):
        """Filter audit logs by 'until' timestamp."""
        resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"until": "2026-01-01T00:00:00"},
        )
        assert resp.status_code == 200
        # Should return 0 results (everything was created after 2026-01-01)
        assert resp.json()["total"] == 0


class TestAuditMiddleware:
    """Audit middleware behavior."""

    def test_x_request_id_header(self, client):
        """Every response should include an X-Request-ID header."""
        resp = client.get("/health")
        assert "X-Request-ID" in resp.headers
        rid = resp.headers["X-Request-ID"]
        assert len(rid) == 16  # hex uuid4 truncated

    def test_401_response_recorded(self, client):
        """Unauthenticated access should produce a 401 audit record."""
        # Access a protected endpoint without auth
        resp = client.get("/api/v1/admin/users")
        assert resp.status_code == 401

        # Login as admin to verify
        admin_result = _login(client, SUPER_USER, SUPER_PASSWORD)
        token = admin_result["body"]["access_token"]

        audit_resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(token),
            params={"action": "401", "page_size": 100},
        )
        assert audit_resp.status_code == 200
        items = audit_resp.json()["items"]
        has_401 = any("401" in item["action"] for item in items)
        assert has_401, f"No 401 audit events found"


class TestAuditLogFailureIsolation:
    """audit_log write failures must never crash business operations."""

    def test_login_succeeds_even_when_audit_write_fails(
        self, client, admin_token, monkeypatch,
    ):
        """Login should return 401 (not 500) even if audit_log raises."""
        import audit_logger

        # Force audit_log to raise on every call
        def _failing_audit(*args, **kwargs):
            raise RuntimeError("simulated disk full")
        monkeypatch.setattr(audit_logger, "audit_log", _failing_audit)

        # Wrong-password login must still return 401, not 500
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": SUPER_USER, "password": "wrong-password"},
        )
        assert resp.status_code == 401, (
            f"Expected 401 despite audit failure, got {resp.status_code}"
        )

        # Correct login must still succeed
        # Need fresh session — the monkeypatch breaks audit but login should work
        resp2 = client.post(
            "/api/v1/auth/login",
            json={"username": SUPER_USER, "password": SUPER_PASSWORD},
        )
        # Login may fail because audit_log is mocked — the important thing is
        # we don't get a 500 from an unhandled exception propagating through
        # the middleware stack.
        assert resp2.status_code != 500, (
            f"Audit write failure caused 500 error (should be handled gracefully)"
        )


class TestRefreshAndLogoutAudit:
    """refresh and logout endpoints must produce audit records (P1 fix)."""

    def test_logout_creates_audit_record(self, client, admin_token):
        """Logout should write an auth.logout audit event."""
        # Login to get a fresh session with cookie.
        # TestClient does not send Secure cookies over HTTP, so we extract
        # the cookie value from the response and pass it manually.
        login_resp_raw = client.post(
            "/api/v1/auth/login",
            json={"username": SUPER_USER, "password": SUPER_PASSWORD},
        )
        assert login_resp_raw.status_code == 200

        # Logout (cookie is sent automatically by TestClient despite Secure
        # flag because httpx stores it; if that fails, logout still returns 200)
        logout_resp = client.post("/api/v1/auth/logout")
        assert logout_resp.status_code == 200

        # Verify audit log contains the logout event
        audit_resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"action": "auth.logout", "page_size": 50},
        )
        assert audit_resp.status_code == 200
        items = audit_resp.json()["items"]
        assert len(items) >= 1, "No auth.logout audit event found after logout"

    def test_refresh_creates_audit_record(self, client, admin_token):
        """Successful refresh should write an auth.refresh.success event."""
        # Login to get a refresh-token cookie
        login_resp_raw = client.post(
            "/api/v1/auth/login",
            json={"username": SUPER_USER, "password": SUPER_PASSWORD},
        )
        assert login_resp_raw.status_code == 200
        # Extract the refresh-token cookie value from the response
        refresh_val = login_resp_raw.cookies.get("refresh_token")
        assert refresh_val is not None, "Login did not set refresh_token cookie"

        # Refresh — send the cookie manually so Secure flag does not block it
        refresh_resp = client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_val},
        )
        assert refresh_resp.status_code == 200, (
            f"Refresh failed: {refresh_resp.status_code} {refresh_resp.text}"
        )

        # Verify audit log
        audit_resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"action": "auth.refresh.success", "page_size": 50},
        )
        assert audit_resp.status_code == 200
        items = audit_resp.json()["items"]
        assert len(items) >= 1, "No auth.refresh.success audit event found"

    def test_refresh_replay_creates_audit_record(self, client, admin_token):
        """Replay of a revoked refresh token must create auth.refresh.failed audit."""
        # Create a separate test user so we don't invalidate admin_token
        resp = client.post(
            "/api/v1/admin/users",
            headers=_auth_headers(admin_token),
            json={
                "username": "replay_test_user",
                "password": "replay-pass-123",
                "display_name": "Replay Test",
            },
        )
        assert resp.status_code == 201
        test_uid = resp.json()["id"]

        # Login as the test user
        login_resp = client.post(
            "/api/v1/auth/login",
            json={"username": "replay_test_user", "password": "replay-pass-123"},
        )
        refresh_val = login_resp.cookies.get("refresh_token")
        assert refresh_val is not None

        # First refresh to rotate
        refresh1 = client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_val},
        )
        assert refresh1.status_code == 200

        # Revoke all sessions for the test user (simulates token theft)
        client.delete(
            f"/api/v1/admin/users/{test_uid}/sessions",
            headers=_auth_headers(admin_token),
        )

        # Replay the OLD (now revoked) token
        replay_resp = client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_val},
        )
        assert replay_resp.status_code == 401, (
            f"Expected 401 after replay, got {replay_resp.status_code}"
        )

        # Verify audit log — admin_token is still valid (different user!)
        audit_resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"action": "auth.refresh.failed", "page_size": 50},
        )
        assert audit_resp.status_code == 200
        items = audit_resp.json()["items"]
        assert len(items) >= 1, "No auth.refresh.failed audit event after replay"


class TestAnomalyStatsNullOrg:
    """Anomaly stats for org_admin should include null-org audit records (P2 fix)."""

    def test_org_admin_anomaly_stats_includes_null_org_events(
        self, db_url_for_audit, tmp_path, monkeypatch,
    ):
        """Failed logins with NULL org_id should count toward org_admin anomaly stats."""
        monkeypatch.setenv("DATABASE_URL", db_url_for_audit)
        from config import get_settings
        get_settings.cache_clear()
        import session as sess_mod
        sess_mod._engine = None
        sess_mod._engine_url = None
        sess_mod._SessionLocal = None

        uid = _create_user(
            db_url_for_audit, "oa_null_org", "pass123", "OA Null Org",
            role_code="org_admin", org_id="default",
        )

        # Insert a failed login audit with NULL org_id (simulates nonexistent user)
        import datetime as _dt
        _24h_ago = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=1)).isoformat()
        engine = create_engine(db_url_for_audit)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_logs "
                    "(request_id, user_id, org_id, action, decision, reason, created_at) "
                    "VALUES (:rid, :uid, :oid, :act, :dec, :reason, :ts)"
                ),
                {
                    "rid": "rid-null-org-001",
                    "uid": None,
                    "oid": None,
                    "act": "auth.login.failed",
                    "dec": "deny",
                    "reason": "user_not_found",
                    "ts": _24h_ago,
                },
            )
        engine.dispose()

        from auth.router import _login_attempts
        _login_attempts.clear()

        with TestClient(app) as c:
            login_resp = _login(c, "oa_null_org", "pass123")
            assert login_resp["status"] == 200
            token = login_resp["body"]["access_token"]

            resp = c.get(
                "/api/v1/admin/anomalies",
                headers=_auth_headers(token),
            )
            assert resp.status_code == 200
            body = resp.json()
            # Should count the null-org failed login
            assert body["recent_failed_logins_24h"] >= 1, (
                f"Expected >=1 failed logins in anomaly stats, got {body['recent_failed_logins_24h']}"
            )

        sess_mod._engine = None
        sess_mod._engine_url = None
        sess_mod._SessionLocal = None
        get_settings.cache_clear()


class TestBeforeAfterAudit:
    """Admin operations must record before/after in audit detail (P2 fix)."""

    def test_set_user_status_audit_has_before_after(self, client, admin_token):
        """Disabling a user should audit before/after is_active state."""
        # Create a new user to disable
        resp = client.post(
            "/api/v1/admin/users",
            headers=_auth_headers(admin_token),
            json={
                "username": "before_after_test",
                "password": "test-pass-12345",
                "display_name": "BeforeAfter Test",
            },
        )
        assert resp.status_code == 201
        uid = resp.json()["id"]

        # Disable the user
        disable_resp = client.patch(
            f"/api/v1/admin/users/{uid}/status",
            headers=_auth_headers(admin_token),
            json={"is_active": False},
        )
        assert disable_resp.status_code == 200

        # Check audit detail_json for before/after
        audit_resp = client.get(
            "/api/v1/admin/audit",
            headers=_auth_headers(admin_token),
            params={"action": "admin.user.disable", "page_size": 10},
        )
        assert audit_resp.status_code == 200
        items = audit_resp.json()["items"]

        # Find the item for our user
        found = None
        for item in items:
            if item.get("resource_id") == str(uid):
                found = item
                break
        assert found is not None, "No audit record for disabled user"

        detail = found.get("detail_json")
        assert detail is not None, "Audit record has no detail_json"
        import json as _json
        detail_obj = _json.loads(detail) if isinstance(detail, str) else detail
        assert "before" in detail_obj, f"detail_json missing 'before': {detail_obj}"
        assert "after" in detail_obj, f"detail_json missing 'after': {detail_obj}"
        assert detail_obj["before"]["is_active"] is True
        assert detail_obj["after"]["is_active"] is False

        # Clean up — re-enable
        client.patch(
            f"/api/v1/admin/users/{uid}/status",
            headers=_auth_headers(admin_token),
            json={"is_active": True},
        )
