from pathlib import Path
import sys

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from auth.dependencies import get_current_user
from main import app


def _user(*permissions: str) -> dict:
    return {
        "id": 1,
        "username": "enterprise_admin",
        "display_name": "企业管理员",
        "email": "enterprise@example.com",
        "default_org_id": "default",
        "default_dept_id": "HQ",
        "roles": ["org_admin"],
        "permissions": list(permissions),
        "must_change_password": False,
    }


def _client(*permissions: str) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: _user(*permissions)
    return TestClient(app)


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_repair_ticket_has_create_list_and_status_update_lifecycle() -> None:
    client = _client(
        "enterprise:records:view",
        "repair:create",
        "repair:update",
    )

    listed = client.get("/api/v1/enterprise/repair/tickets")
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    created = client.post(
        "/api/v1/enterprise/repair/tickets",
        json={
            "title": "会议室投影设备报修",
            "location": "A 栋 203",
            "description": "投影设备无法启动",
            "priority": "normal",
        },
    )
    assert created.status_code == 201
    ticket_id = created.json()["id"]
    assert created.json()["status"] == "submitted"

    updated = client.patch(
        f"/api/v1/enterprise/repair/tickets/{ticket_id}",
        json={"status": "processing", "assignee": "后勤服务中心"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "processing"
    assert updated.json()["assignee"] == "后勤服务中心"


def test_asset_item_has_create_list_and_borrow_status_lifecycle() -> None:
    client = _client(
        "enterprise:records:view",
        "asset:create",
        "asset:update",
    )

    created = client.post(
        "/api/v1/enterprise/assets/items",
        json={
            "asset_code": "ASSET-2026-001",
            "name": "移动投影设备",
            "category": "教学设备",
            "location": "设备库",
        },
    )
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert created.json()["status"] == "available"

    updated = client.patch(
        f"/api/v1/enterprise/assets/items/{item_id}",
        json={"status": "borrowed", "custodian": "张老师"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "borrowed"
    assert updated.json()["custodian"] == "张老师"

    listed = client.get("/api/v1/enterprise/assets/items")
    assert listed.status_code == 200
    assert any(item["id"] == item_id for item in listed.json()["items"])


def test_oa_flow_has_create_list_and_process_status_lifecycle() -> None:
    client = _client(
        "enterprise:records:view",
        "oa:create",
        "oa:update",
    )

    created = client.post(
        "/api/v1/enterprise/oa/flows",
        json={
            "title": "部门采购申请",
            "flow_type": "采购申请",
        },
    )
    assert created.status_code == 201
    flow_id = created.json()["id"]
    assert created.json()["status"] == "pending"

    updated = client.patch(
        f"/api/v1/enterprise/oa/flows/{flow_id}",
        json={"status": "processing", "current_handler": "部门负责人"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "processing"

    listed = client.get("/api/v1/enterprise/oa/flows")
    assert listed.status_code == 200
    assert any(item["id"] == flow_id for item in listed.json()["items"])


def test_subsystem_workbench_reads_real_records_for_supported_modules() -> None:
    client = _client("enterprise:records:view")

    for code, title in [
        ("repair", "报修工单"),
        ("assets", "资产台账"),
        ("oa", "待办流程"),
    ]:
        response = client.get(f"/api/v1/enterprise/subsystems/{code}/records")
        assert response.status_code == 200
        payload = response.json()
        assert payload["code"] == code
        assert payload["title"] == title
        assert "metrics" in payload
        assert "records" in payload
        assert "columns" in payload


def test_enterprise_write_actions_require_explicit_permissions() -> None:
    client = _client("enterprise:records:view")

    response = client.post(
        "/api/v1/enterprise/repair/tickets",
        json={
            "title": "无权限报修",
            "location": "A 栋",
            "description": "不应创建",
        },
    )

    assert response.status_code == 403
