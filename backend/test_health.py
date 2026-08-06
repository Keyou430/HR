"""T10: Health check endpoint tests.

Covers:
- Liveness probe: GET /health → 200 ``{"status": "ok"}``
- Readiness probe: GET /health?full=true → 200 with DB ok
- Degraded state: GET /health?full=true → 503 when database is unreachable
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app


# ═══════════════════════════════════════════════════════════════════════
# Liveness
# ═══════════════════════════════════════════════════════════════════════


def test_health_liveness_returns_200():
    """GET /health (basic liveness) always returns 200 with status=ok."""
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════
# Readiness (requires real DB — use conftest client fixture)
# ═══════════════════════════════════════════════════════════════════════


def test_health_readiness_with_db_ok(client: TestClient):
    """GET /health?full=true returns 200 with database.ok=true when DB is reachable."""
    resp = client.get("/health?full=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "database" in data
    assert data["database"]["ok"] is True
    assert data["database"]["error"] is None


# ═══════════════════════════════════════════════════════════════════════
# Degraded (DB unreachable)
# ═══════════════════════════════════════════════════════════════════════


def test_health_readiness_degraded_when_db_down(monkeypatch):
    """GET /health?full=true returns 503 when the database is unreachable.

    Patches ``main.get_engine`` (imported from session) to raise an exception,
    simulating a database outage at the call site inside the health handler.
    """

    def _broken_engine():
        raise ConnectionError("Simulated database outage for health check test")

    monkeypatch.setattr("main.get_engine", _broken_engine)

    with TestClient(app) as client:
        resp = client.get("/health?full=true")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert "database" in data
        assert data["database"]["ok"] is False
        assert data["database"]["error"] is not None
        assert "Simulated database outage" in data["database"]["error"]


def test_health_readiness_degraded_with_generic_db_error(monkeypatch):
    """GET /health?full=true returns 503 when DB raises a generic exception."""

    def _broken_engine_generic():
        raise RuntimeError("pool exhausted")

    monkeypatch.setattr("main.get_engine", _broken_engine_generic)

    with TestClient(app) as client:
        resp = client.get("/health?full=true")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "degraded"
        assert data["database"]["ok"] is False
        assert "pool exhausted" in data["database"]["error"]
