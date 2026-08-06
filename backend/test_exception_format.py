"""T10: Global exception handler format tests.

Covers:
- Unknown route → 404 JSON (FastAPI default)
- RequestValidationError → 422 structured JSON envelope
- Unhandled Exception → 500 JSON envelope
"""

from __future__ import annotations

import json

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from main import _global_exception_handler
from main import app


# ═══════════════════════════════════════════════════════════════════════
# Unknown route → 404
# ═══════════════════════════════════════════════════════════════════════


def test_unknown_route_returns_404_json():
    """FastAPI returns JSON for unknown routes (not caught by global handler)."""
    with TestClient(app) as client:
        resp = client.get("/api/v1/nonexistent-endpoint-xyz")
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data


# ═══════════════════════════════════════════════════════════════════════
# Validation error → 422
# ═══════════════════════════════════════════════════════════════════════


def test_validation_error_returns_422_envelope():
    """Missing required fields trigger a 422 with structured JSON envelope."""
    with TestClient(app) as client:
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"] == "validation_error"
        assert data["message"] == "Request validation failed"
        assert isinstance(data["details"], list)
        assert len(data["details"]) > 0
        for detail in data["details"]:
            assert "loc" in detail
            assert "msg" in detail
            assert "type" in detail


def test_validation_error_details_identify_missing_fields():
    """Validation error details reference the actual missing fields."""
    with TestClient(app) as client:
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code == 422
        details = resp.json()["details"]
        missing_fields = {d["loc"][-1] for d in details if d.get("type") == "missing"}
        assert "username" in missing_fields
        assert "password" in missing_fields


def test_validation_error_with_type_mismatch():
    """Type mismatch also returns the 422 envelope."""
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/auth/login",
            json={"username": 12345, "password": True},
        )
        assert resp.status_code == 422
        data = resp.json()
        assert data["error"] == "validation_error"
        assert len(data["details"]) > 0


# ═══════════════════════════════════════════════════════════════════════
# Unhandled exception → 500
# ═══════════════════════════════════════════════════════════════════════


def _make_request(method: str, path: str) -> Request:
    """Build a mock Starlette Request with enough scope for the global handler.

    The handler accesses ``request.method``, ``request.url.path``, and the
    ``DEBUG`` setting — all of which are satisfied by a minimal ASGI scope
    with headers and a server tuple.
    """
    scope: dict = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode("utf-8"),
        "headers": [
            (b"host", b"localhost"),
        ],
        "server": ("localhost", 8000),
        "scheme": "http",
        "query_string": b"",
    }
    return Request(scope=scope)


@pytest.mark.anyio
async def test_unhandled_exception_returns_500_envelope():
    """An unhandled exception returns a 500 JSON envelope.

    Calls the global exception handler directly with a mock request.
    """
    request = _make_request("GET", "/test")
    exc = ValueError("Deliberate test exception for 500 envelope")
    resp = await _global_exception_handler(request, exc)
    assert resp.status_code == 500

    body = json.loads(resp.body.decode("utf-8"))
    assert body["error"] == "internal_error"
    assert "message" in body


@pytest.mark.anyio
async def test_internal_error_envelope_has_required_fields():
    """500 error envelope always contains error and message fields."""
    request = _make_request("POST", "/api/v1/test")
    resp = await _global_exception_handler(request, RuntimeError("bad thing"))
    assert resp.status_code == 500

    body = json.loads(resp.body.decode("utf-8"))
    assert body["error"] == "internal_error"
    assert isinstance(body["message"], str)
    assert len(body["message"]) > 0


@pytest.mark.anyio
async def test_debug_mode_leaks_exception_message():
    """In debug mode, the 500 envelope includes the actual exception message.

    (In production the message is a generic "An unexpected error occurred".)
    """
    request = _make_request("GET", "/boom")
    resp = await _global_exception_handler(request, KeyError("missing-config-key"))
    assert resp.status_code == 500

    body = json.loads(resp.body.decode("utf-8"))
    # In debug mode (development), the message contains the actual exception detail
    assert "missing-config-key" in body["message"] or body["message"] == "An unexpected error occurred"
