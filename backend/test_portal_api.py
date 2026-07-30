import sys
from pathlib import Path

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from main import app


def test_health_endpoint_allows_null_origin_for_local_file_frontend() -> None:
    client = TestClient(app)

    response = client.get("/health", headers={"Origin": "null"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "null"


def test_portal_bootstrap_exposes_frontend_ready_data() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/portal/bootstrap")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embed_urls"]["feishu"] == "https://www.feishu.cn/"
    assert payload["embed_urls"]["dingtalk"] == "https://www.dingtalk.com/"
    assert payload["skills"]["total"] >= 12
    assert payload["capabilities"]["total"] >= 1
    assert payload["workspace"]["tasks"]["total"] >= 1
    assert payload["calendar"]["events"]["total"] >= 1
    assert payload["knowledge"]["spaces"]["total"] == 0
    assert payload["portal"]["systems"]["total"] >= 1


def test_task_endpoints_follow_frontend_workflow() -> None:
    client = TestClient(app)

    created = client.post("/api/v1/tasks", json={"title": "整理接口契约", "tag": "今天"})

    assert created.status_code == 201
    task = created.json()
    assert task["title"] == "整理接口契约"
    assert task["done"] is False

    updated = client.patch(f"/api/v1/tasks/{task['id']}", json={"done": True})

    assert updated.status_code == 200
    assert updated.json()["done"] is True

    listed = client.get("/api/v1/tasks")

    assert listed.status_code == 200
    assert any(item["id"] == task["id"] for item in listed.json()["items"])

    deleted = client.delete(f"/api/v1/tasks/{task['id']}")

    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True


def test_calendar_event_endpoints_follow_frontend_workflow() -> None:
    client = TestClient(app)

    created = client.post(
        "/api/v1/calendar/events",
        json={"title": "部门复盘会", "date": "2026-07-29", "tone": "orange"},
    )

    assert created.status_code == 201
    event = created.json()
    assert event["title"] == "部门复盘会"

    updated = client.put(
        f"/api/v1/calendar/events/{event['id']}",
        json={"title": "部门复盘会更新", "date": "2026-07-30", "tone": "blue"},
    )

    assert updated.status_code == 200
    assert updated.json()["date"] == "2026-07-30"

    deleted = client.delete(f"/api/v1/calendar/events/{event['id']}")

    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True


def test_embed_urls_can_be_saved_for_frontend_iframes() -> None:
    client = TestClient(app)

    response = client.put(
        "/api/v1/integrations/embed-urls",
        json={"feishu": "https://example.com/feishu", "dingtalk": "https://example.com/dingtalk"},
    )

    assert response.status_code == 200
    assert response.json()["feishu"] == "https://example.com/feishu"
    assert client.get("/api/v1/portal/bootstrap").json()["embed_urls"]["dingtalk"] == "https://example.com/dingtalk"


def test_knowledge_and_search_endpoints_support_static_frontend() -> None:
    client = TestClient(app)

    spaces = client.get("/api/v1/knowledge/spaces", params={"search": "服务"})

    assert spaces.status_code == 200
    assert spaces.json()["total"] == 0

    chat = client.post("/api/v1/knowledge/chat", json={"question": "服务目录是什么？", "scope": "all"})

    assert chat.status_code == 200
    assert "answer" in chat.json()

    search = client.get("/api/v1/search", params={"q": "教职工"})

    assert search.status_code == 200
    assert search.json()["total"] >= 1
