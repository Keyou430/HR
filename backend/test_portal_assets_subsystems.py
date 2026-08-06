from pathlib import Path
import sys

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from auth.dependencies import get_current_user
from main import app


def _auth_user() -> dict:
    return {
        "id": 1,
        "username": "admin",
        "display_name": "管理员",
        "email": "admin@example.com",
        "default_org_id": "default",
        "default_dept_id": "HQ",
        "roles": ["super_admin"],
        "permissions": ["system:config", "notice:view", "search:view", "org:view"],
        "must_change_password": False,
    }


def _client() -> TestClient:
    app.dependency_overrides[get_current_user] = _auth_user
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_subsystems_are_platform_internal_and_record_visits() -> None:
    client = _client()

    listed = client.get("/api/v1/subsystems")

    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] >= 15
    oa = next(item for item in payload["items"] if item["name"] == "OA 系统")
    assert oa["entry_type"] == "internal"
    assert oa["status"] == "active"

    detail = client.get(f"/api/v1/subsystems/{oa['code']}")
    assert detail.status_code == 200
    assert detail.json()["code"] == oa["code"]
    assert "常用操作" not in detail.text
    assert len(detail.json()["common_actions"]) >= 1

    visited = client.post(f"/api/v1/subsystems/{oa['code']}/visit")
    assert visited.status_code == 200
    assert visited.json()["visits_7d"] >= 1


def test_key_subsystems_have_distinct_workbench_actions() -> None:
    client = _client()

    listed = client.get("/api/v1/subsystems")

    assert listed.status_code == 200
    items = {item["code"]: item for item in listed.json()["items"]}
    expected_actions = {
        "repair": ["新建报修", "工单列表"],
        "assets": ["资产目录", "借用申请"],
        "finance": ["报销单", "预算项目"],
        "hr": ["证明申请", "请假考勤"],
        "oa": ["待办流程", "文件流转"],
        "data-portal": ["指标看板", "专题数据"],
    }
    for code, labels in expected_actions.items():
        action_labels = [action["label"] for action in items[code]["common_actions"]]
        for label in labels:
            assert label in action_labels


def test_portal_assets_have_lists_details_preferences_and_dashboard() -> None:
    client = _client()

    for collection, detail_key in [
        ("notices", "id"),
        ("documents", "id"),
        ("resources", "code"),
        ("services", "code"),
        ("news", "id"),
    ]:
        listed = client.get(f"/api/v1/portal/{collection}")
        assert listed.status_code == 200
        item = listed.json()["items"][0]
        detail = client.get(f"/api/v1/portal/{collection}/{item[detail_key]}")
        assert detail.status_code == 200

    preferences = client.put(
        "/api/v1/portal/preferences",
        json={"favorite_subsystems": ["oa"], "hidden_cards": ["workspace-assistant"]},
    )
    assert preferences.status_code == 200
    assert preferences.json()["favorite_subsystems"] == ["oa"]

    client.post("/api/v1/subsystems/oa/visit")
    dashboard = client.get("/api/v1/portal/dashboard")
    assert dashboard.status_code == 200
    stats = dashboard.json()
    assert stats["subsystems_total"] >= 15
    assert stats["notices_total"] >= 1
    assert stats["documents_total"] >= 1
    assert stats["visits_7d"] >= 1


def test_search_includes_internal_portal_assets() -> None:
    client = _client()

    result = client.get("/api/v1/search", params={"q": "OA"})

    assert result.status_code == 200
    assert any(item["type"] == "子系统" and item["title"] == "OA 系统" for item in result.json()["items"])
