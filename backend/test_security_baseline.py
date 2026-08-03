"""Phase 0: Security baseline tests for Replica RBAC v2.0.

These tests verify the CURRENT state of the API — all endpoints are accessible
without any authentication. They serve as the baseline against which we will
measure progress as we add auth, RBAC, and data isolation in later phases.

IMPORTANT: These tests must pass against the current codebase. If any test
fails, it means either:
- An endpoint has changed since this baseline was written.
- The test incorrectly asserts a behavior the endpoint doesn't have.

Do NOT modify production code to make these tests pass — update the test instead.
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from main import app

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Health endpoint
# ---------------------------------------------------------------------------


def test_health_accessible_without_auth(client: TestClient) -> None:
    """GET /health returns 200 without any authentication."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# 2. Portal bootstrap
# ---------------------------------------------------------------------------


def test_portal_bootstrap_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/portal/bootstrap returns 200 without auth."""
    response = client.get("/api/v1/portal/bootstrap")
    assert response.status_code == 200
    payload = response.json()
    # Verify expected top-level keys exist
    assert "embed_urls" in payload
    assert "capabilities" in payload
    assert "skills" in payload
    assert "workspace" in payload
    assert "portal" in payload
    assert "calendar" in payload
    assert "knowledge" in payload


# ---------------------------------------------------------------------------
# 3. Tasks — CRUD + clear-done
# ---------------------------------------------------------------------------


def test_task_list_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/tasks returns 200 without auth."""
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload
    assert isinstance(payload["items"], list)


def test_task_create_accessible_without_auth(client: TestClient) -> None:
    """POST /api/v1/tasks returns 201 without auth."""
    response = client.post(
        "/api/v1/tasks",
        json={"title": "基线测试任务", "tag": "今天"},
    )
    assert response.status_code == 201
    task = response.json()
    assert task["title"] == "基线测试任务"
    assert task["done"] is False


def test_task_update_accessible_without_auth(client: TestClient) -> None:
    """PATCH /api/v1/tasks/{id} returns 200 without auth."""
    # Create first
    created = client.post("/api/v1/tasks", json={"title": "待更新任务", "tag": "本周"})
    assert created.status_code == 201
    task_id = created.json()["id"]

    response = client.patch(f"/api/v1/tasks/{task_id}", json={"done": True})
    assert response.status_code == 200
    assert response.json()["done"] is True


def test_task_delete_accessible_without_auth(client: TestClient) -> None:
    """DELETE /api/v1/tasks/{id} returns 200 without auth."""
    created = client.post("/api/v1/tasks", json={"title": "待删除任务", "tag": "今天"})
    assert created.status_code == 201
    task_id = created.json()["id"]

    response = client.delete(f"/api/v1/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_task_clear_done_accessible_without_auth(client: TestClient) -> None:
    """POST /api/v1/tasks/clear-done returns 200 without auth."""
    response = client.post("/api/v1/tasks/clear-done")
    assert response.status_code == 200
    assert "deleted" in response.json()


def test_task_update_nonexistent_returns_404(client: TestClient) -> None:
    """PATCH /api/v1/tasks/{id} on nonexistent ID returns 404."""
    response = client.patch("/api/v1/tasks/99999", json={"done": True})
    assert response.status_code == 404


def test_task_delete_nonexistent_returns_404(client: TestClient) -> None:
    """DELETE /api/v1/tasks/{id} on nonexistent ID returns 404."""
    response = client.delete("/api/v1/tasks/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 4. Calendar events — CRUD
# ---------------------------------------------------------------------------


def test_calendar_list_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/calendar/events returns 200 without auth."""
    response = client.get("/api/v1/calendar/events")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload


def test_calendar_create_accessible_without_auth(client: TestClient) -> None:
    """POST /api/v1/calendar/events returns 201 without auth."""
    response = client.post(
        "/api/v1/calendar/events",
        json={"title": "基线测试日程", "date": "2026-07-30", "tone": "blue"},
    )
    assert response.status_code == 201
    event = response.json()
    assert event["title"] == "基线测试日程"
    assert event["date"] == "2026-07-30"


def test_calendar_update_accessible_without_auth(client: TestClient) -> None:
    """PUT /api/v1/calendar/events/{id} returns 200 without auth."""
    created = client.post(
        "/api/v1/calendar/events",
        json={"title": "待更新日程", "date": "2026-08-01", "tone": "green"},
    )
    assert created.status_code == 201
    event_id = created.json()["id"]

    response = client.put(
        f"/api/v1/calendar/events/{event_id}",
        json={"title": "已更新日程", "date": "2026-08-02", "tone": "orange"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "已更新日程"


def test_calendar_delete_accessible_without_auth(client: TestClient) -> None:
    """DELETE /api/v1/calendar/events/{id} returns 200 without auth."""
    created = client.post(
        "/api/v1/calendar/events",
        json={"title": "待删除日程", "date": "2026-08-03", "tone": "blue"},
    )
    assert created.status_code == 201
    event_id = created.json()["id"]

    response = client.delete(f"/api/v1/calendar/events/{event_id}")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_calendar_update_nonexistent_returns_404(client: TestClient) -> None:
    """PUT /api/v1/calendar/events/{id} on nonexistent ID returns 404."""
    response = client.put(
        "/api/v1/calendar/events/99999",
        json={"title": "x", "date": "2026-01-01", "tone": "blue"},
    )
    assert response.status_code == 404


def test_calendar_delete_nonexistent_returns_404(client: TestClient) -> None:
    """DELETE /api/v1/calendar/events/{id} on nonexistent ID returns 404."""
    response = client.delete("/api/v1/calendar/events/99999")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 5. Knowledge — spaces, mappings, imports, sync
# ---------------------------------------------------------------------------


def test_knowledge_spaces_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/knowledge/spaces returns 200 without auth."""
    response = client.get("/api/v1/knowledge/spaces")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload


def test_knowledge_mappings_list_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/knowledge/mappings returns 200 without auth."""
    response = client.get("/api/v1/knowledge/mappings")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload


def test_knowledge_mappings_update_nonexistent_returns_404(client: TestClient) -> None:
    """PATCH /api/v1/knowledge/mappings/{id} on nonexistent ID returns 404."""
    response = client.patch(
        "/api/v1/knowledge/mappings/nonexistent:id",
        json={"display_name": "test"},
    )
    assert response.status_code == 404


def test_knowledge_mappings_delete_nonexistent_returns_404(client: TestClient) -> None:
    """DELETE /api/v1/knowledge/mappings/{id} on nonexistent ID returns 404."""
    response = client.delete("/api/v1/knowledge/mappings/nonexistent:id")
    assert response.status_code == 404


def test_knowledge_imports_list_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/knowledge/imports returns 200 without auth."""
    response = client.get("/api/v1/knowledge/imports")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload


def test_knowledge_sync_accessible_without_auth(client: TestClient) -> None:
    """POST /api/v1/knowledge/sync is accessible without auth.

    The endpoint may succeed (200 in real mode) or fail with configuration errors
    (409 in mock mode, 5xx if FastGPT unreachable). The key assertion: it does NOT
    return 401 or 403 — the endpoint has no auth check in the current baseline.
    """
    response = client.post("/api/v1/knowledge/sync")
    # In mock mode: 409 (FASTGPT_REAL_MODE_REQUIRED)
    # In real mode with FastGPT reachable: 200
    # In real mode with FastGPT unreachable: 5xx
    # NEVER: 401 or 403 (no auth check exists)
    assert response.status_code not in (401, 403), (
        f"BASELINE BROKEN: /api/v1/knowledge/sync returned {response.status_code}"
    )


def test_knowledge_chat_accessible_without_auth(client: TestClient) -> None:
    """POST /api/v1/knowledge/chat returns 200 without auth.

    In mock Hermes mode the answer contains "[Hermes mock]"; in real mode it
    returns an actual AI-generated answer. Either way, the endpoint must not
    require authentication in the current baseline.
    """
    response = client.post(
        "/api/v1/knowledge/chat",
        json={"question": "什么是协同门户？", "mode": "chat"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "answer" in payload
    assert isinstance(payload["answer"], str)
    assert len(payload["answer"]) > 0


def test_knowledge_import_requires_file_in_mock_mode(client: TestClient) -> None:
    """POST /api/v1/knowledge/import returns 422 without file."""
    # Send without file — the endpoint requires multipart form data
    response = client.post("/api/v1/knowledge/import")
    # 422: missing required form fields (dataset_id + file)
    assert response.status_code == 422


def test_knowledge_dataset_files_list_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/knowledge/datasets/{id}/files returns 200 without auth.

    In mock mode returns {"items": [], "total": 0}; in real mode may return
    actual FastGPT files. Only assert structure and absence of auth rejection.
    """
    response = client.get("/api/v1/knowledge/datasets/test-dataset-id/files")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload
    assert isinstance(payload["items"], list)


def test_knowledge_dataset_file_delete_accessible_without_auth(client: TestClient) -> None:
    """DELETE /api/v1/knowledge/datasets/{id}/files/{fid} is accessible without auth.

    May fail with 409 (mock mode), 502/504 (real mode, FastGPT unreachable), or
    succeed with 200 (real mode, FastGPT reachable). Must NOT return 401 or 403.
    """
    response = client.delete("/api/v1/knowledge/datasets/ds1/files/file1")
    # In mock mode: 409 (FASTGPT_REAL_MODE_REQUIRED)
    # In real mode with FastGPT unreachable: 502 or 504
    # In real mode with FastGPT reachable: 200
    # NEVER: 401 or 403 (no auth check exists)
    assert response.status_code not in (401, 403), (
        f"BASELINE BROKEN: DELETE dataset file returned {response.status_code}"
    )


# ---------------------------------------------------------------------------
# 6. Search
# ---------------------------------------------------------------------------


def test_search_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/search returns 200 without auth."""
    response = client.get("/api/v1/search", params={"q": "制度"})
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload


def test_search_empty_query_returns_all(client: TestClient) -> None:
    """GET /api/v1/search with empty q returns results."""
    response = client.get("/api/v1/search", params={"q": ""})
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    # Searches across knowledge, documents, notices, services


# ---------------------------------------------------------------------------
# 7. Integrations — embed URLs
# ---------------------------------------------------------------------------


def test_integrations_get_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/integrations/embed-urls returns 200 without auth."""
    response = client.get("/api/v1/integrations/embed-urls")
    assert response.status_code == 200
    payload = response.json()
    assert "feishu" in payload
    assert "dingtalk" in payload


def test_integrations_update_accessible_without_auth(client: TestClient) -> None:
    """PUT /api/v1/integrations/embed-urls returns 200 without auth."""
    original = client.get("/api/v1/integrations/embed-urls").json()

    response = client.put(
        "/api/v1/integrations/embed-urls",
        json={"feishu": "https://custom.example.com/feishu"},
    )
    assert response.status_code == 200
    assert response.json()["feishu"] == "https://custom.example.com/feishu"

    # Restore original
    client.put("/api/v1/integrations/embed-urls", json={"feishu": original["feishu"]})


# ---------------------------------------------------------------------------
# 8. Chat sessions — CRUD
# ---------------------------------------------------------------------------


def test_chat_sessions_list_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/chat/sessions returns 200 without auth."""
    response = client.get("/api/v1/chat/sessions")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert "total" in payload


def test_chat_messages_save_accessible_without_auth(client: TestClient) -> None:
    """POST /api/v1/chat/messages returns 200 without auth."""
    response = client.post(
        "/api/v1/chat/messages",
        json={
            "session_id": "test-baseline-session",
            "role": "user",
            "content": "基线测试消息",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_chat_messages_get_accessible_without_auth(client: TestClient) -> None:
    """GET /api/v1/chat/sessions/{id}/messages returns 200 without auth."""
    # First save a message to ensure the session exists
    client.post(
        "/api/v1/chat/messages",
        json={
            "session_id": "test-baseline-session-2",
            "role": "user",
            "content": "消息1",
        },
    )

    response = client.get("/api/v1/chat/sessions/test-baseline-session-2/messages")
    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert len(payload["items"]) >= 1


def test_chat_session_delete_accessible_without_auth(client: TestClient) -> None:
    """DELETE /api/v1/chat/sessions/{id} returns 200 without auth."""
    # Create and then delete
    client.post(
        "/api/v1/chat/messages",
        json={
            "session_id": "test-baseline-delete-session",
            "role": "user",
            "content": "待删除",
        },
    )

    response = client.delete("/api/v1/chat/sessions/test-baseline-delete-session")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_chat_session_delete_nonexistent_returns_404(client: TestClient) -> None:
    """DELETE /api/v1/chat/sessions/{id} on nonexistent returns 404."""
    response = client.delete("/api/v1/chat/sessions/nonexistent-session-xyz")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# 9. Edge cases: validate that current API has NO auth enforcement
# ---------------------------------------------------------------------------


def test_all_write_endpoints_accessible_without_auth_header(client: TestClient) -> None:
    """Verify that key write endpoints accept requests without any Authorization header."""
    write_endpoints = [
        ("POST", "/api/v1/tasks", {"title": "auth test", "tag": "今天"}),
        ("POST", "/api/v1/calendar/events", {"title": "auth test", "date": "2026-08-01", "tone": "blue"}),
        ("POST", "/api/v1/chat/messages", {"session_id": "auth-test", "role": "user", "content": "test"}),
    ]

    for method, path, body in write_endpoints:
        response = client.request(method, path, json=body)
        # None of these should return 401 or 403 in the current baseline
        assert response.status_code not in (401, 403), (
            f"BASELINE BROKEN: {method} {path} returned {response.status_code} "
            f"— current code should NOT require auth. "
            f"If this fails, the API has already been locked down (test needs update)."
        )


def test_all_read_endpoints_accessible_without_auth_header(client: TestClient) -> None:
    """Verify that key read endpoints accept requests without any Authorization header."""
    read_endpoints = [
        ("GET", "/health"),
        ("GET", "/api/v1/portal/bootstrap"),
        ("GET", "/api/v1/tasks"),
        ("GET", "/api/v1/calendar/events"),
        ("GET", "/api/v1/knowledge/spaces"),
        ("GET", "/api/v1/knowledge/mappings"),
        ("GET", "/api/v1/knowledge/imports"),
        ("GET", "/api/v1/search", {"q": "test"}),
        ("GET", "/api/v1/integrations/embed-urls"),
        ("GET", "/api/v1/chat/sessions"),
    ]

    for spec in read_endpoints:
        method = spec[0]
        path = spec[1]
        params = spec[2] if len(spec) > 2 else None
        response = client.request(method, path, params=params)
        assert response.status_code not in (401, 403), (
            f"BASELINE BROKEN: {method} {path} returned {response.status_code} "
            f"— current code should NOT require auth. "
            f"If this fails, the API has already been locked down (test needs update)."
        )
