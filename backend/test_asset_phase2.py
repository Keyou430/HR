"""Phase 2b: Asset item lifecycle and borrow/return tests."""
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class TestAssetLifecycle:
    """CRUD + borrow/return + stats."""

    def test_create_asset(self, super_admin_client):
        resp = super_admin_client.post(
            "/api/v1/enterprise/assets/items",
            json={"asset_code": "EQ-001", "name": "投影仪", "category": "教学设备", "location": "多媒体教室"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "available"
        assert data["asset_code"] == "EQ-001"

    def test_list_assets(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/assets/items")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_single_asset(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/assets/items",
            json={"asset_code": "EQ-002", "name": "笔记本电脑", "category": "IT设备", "location": "办公室"},
        )
        item_id = created.json()["id"]
        resp = super_admin_client.get(f"/api/v1/enterprise/assets/items/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == item_id

    def test_update_asset(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/assets/items",
            json={"asset_code": "EQ-003", "name": "旧名称", "category": "办公", "location": "仓库"},
        )
        item_id = created.json()["id"]
        resp = super_admin_client.patch(
            f"/api/v1/enterprise/assets/items/{item_id}",
            json={"name": "新名称", "custodian": "李四"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "新名称"
        assert resp.json()["custodian"] == "李四"

    def test_borrow_asset(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/assets/items",
            json={"asset_code": "EQ-004", "name": "摄像机", "category": "媒体设备", "location": "设备室"},
        )
        item_id = created.json()["id"]
        resp = super_admin_client.post(
            f"/api/v1/enterprise/assets/items/{item_id}/borrow",
            json={"expected_return_date": "2026-08-15"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "borrowed"
        assert data["asset_id"] == item_id

    def test_borrow_unavailable_fails(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/assets/items",
            json={"asset_code": "EQ-005", "name": "借出测试", "category": "测试", "location": "仓库"},
        )
        item_id = created.json()["id"]
        super_admin_client.post(f"/api/v1/enterprise/assets/items/{item_id}/borrow")
        resp = super_admin_client.post(f"/api/v1/enterprise/assets/items/{item_id}/borrow")
        assert resp.status_code == 400

    def test_return_asset(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/assets/items",
            json={"asset_code": "EQ-006", "name": "归还测试", "category": "测试", "location": "仓库"},
        )
        item_id = created.json()["id"]
        borrow = super_admin_client.post(f"/api/v1/enterprise/assets/items/{item_id}/borrow")
        record_id = borrow.json()["id"]

        resp = super_admin_client.post(f"/api/v1/enterprise/assets/borrow/{record_id}/return")
        assert resp.status_code == 200
        assert resp.json()["status"] == "returned"
        assert resp.json()["actual_return_date"] is not None

        get_resp = super_admin_client.get(f"/api/v1/enterprise/assets/items/{item_id}")
        assert get_resp.json()["status"] == "available"

    def test_return_already_returned_fails(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/assets/items",
            json={"asset_code": "EQ-007", "name": "二次归还", "category": "测试", "location": "仓库"},
        )
        item_id = created.json()["id"]
        borrow = super_admin_client.post(f"/api/v1/enterprise/assets/items/{item_id}/borrow")
        record_id = borrow.json()["id"]
        super_admin_client.post(f"/api/v1/enterprise/assets/borrow/{record_id}/return")
        resp = super_admin_client.post(f"/api/v1/enterprise/assets/borrow/{record_id}/return")
        assert resp.status_code == 400

    def test_asset_stats(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/assets/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "by_status" in data
        assert "by_category" in data
        assert "borrowed_count" in data
