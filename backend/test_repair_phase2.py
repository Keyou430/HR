"""Phase 2a: Repair ticket lifecycle, permissions, and scope tests."""
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class TestRepairLifecycle:
    """Full lifecycle: submit → assign → complete → rate."""

    def test_create_ticket(self, super_admin_client):
        resp = super_admin_client.post(
            "/api/v1/enterprise/repair/tickets",
            json={"title": "空调故障", "location": "A-301", "description": "不制冷", "priority": "normal"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "submitted"
        assert data["title"] == "空调故障"

    def test_list_tickets(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/repair/tickets")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_assign_ticket(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/repair/tickets",
            json={"title": "灯管更换", "location": "B-101", "description": "闪烁", "priority": "high"},
        )
        ticket_id = created.json()["id"]
        resp = super_admin_client.post(
            f"/api/v1/enterprise/repair/tickets/{ticket_id}/assign",
            json={"assignee": "后勤王师傅"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "processing"

    def test_assign_non_submitted_fails(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/repair/tickets",
            json={"title": "测试", "location": "C-1", "description": "test"},
        )
        ticket_id = created.json()["id"]
        super_admin_client.post(
            f"/api/v1/enterprise/repair/tickets/{ticket_id}/assign",
            json={"assignee": "张三"},
        )
        resp = super_admin_client.post(
            f"/api/v1/enterprise/repair/tickets/{ticket_id}/assign",
            json={"assignee": "李四"},
        )
        assert resp.status_code == 400

    def test_complete_ticket(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/repair/tickets",
            json={"title": "网络故障", "location": "机房", "description": "断网"},
        )
        ticket_id = created.json()["id"]
        super_admin_client.post(
            f"/api/v1/enterprise/repair/tickets/{ticket_id}/assign",
            json={"assignee": "IT部"},
        )
        resp = super_admin_client.post(f"/api/v1/enterprise/repair/tickets/{ticket_id}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"
        assert resp.json()["completed_at"] is not None

    def test_complete_non_processing_fails(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/repair/tickets",
            json={"title": "测试2", "location": "D-2", "description": "test"},
        )
        ticket_id = created.json()["id"]
        resp = super_admin_client.post(f"/api/v1/enterprise/repair/tickets/{ticket_id}/complete")
        assert resp.status_code == 400

    def test_rate_ticket(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/repair/tickets",
            json={"title": "水龙头漏水", "location": "洗手间", "description": "滴水"},
        )
        ticket_id = created.json()["id"]
        super_admin_client.post(
            f"/api/v1/enterprise/repair/tickets/{ticket_id}/assign",
            json={"assignee": "维修组"},
        )
        super_admin_client.post(f"/api/v1/enterprise/repair/tickets/{ticket_id}/complete")
        resp = super_admin_client.post(
            f"/api/v1/enterprise/repair/tickets/{ticket_id}/rate",
            json={"rating": 4},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rated"

    def test_rate_invalid_value(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/repair/tickets",
            json={"title": "测试3", "location": "E-3", "description": "test"},
        )
        ticket_id = created.json()["id"]
        super_admin_client.post(
            f"/api/v1/enterprise/repair/tickets/{ticket_id}/assign",
            json={"assignee": "X"},
        )
        super_admin_client.post(f"/api/v1/enterprise/repair/tickets/{ticket_id}/complete")
        resp = super_admin_client.post(
            f"/api/v1/enterprise/repair/tickets/{ticket_id}/rate",
            json={"rating": 6},
        )
        assert resp.status_code == 422

    def test_rate_non_completed_fails(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/repair/tickets",
            json={"title": "测试4", "location": "F-4", "description": "test"},
        )
        ticket_id = created.json()["id"]
        resp = super_admin_client.post(
            f"/api/v1/enterprise/repair/tickets/{ticket_id}/rate",
            json={"rating": 3},
        )
        assert resp.status_code == 400

    def test_get_stats(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/repair/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "by_status" in data

    def test_update_ticket_fields(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/repair/tickets",
            json={"title": "原始标题", "location": "G-7", "description": "原始描述"},
        )
        ticket_id = created.json()["id"]
        resp = super_admin_client.patch(
            f"/api/v1/enterprise/repair/tickets/{ticket_id}",
            json={"title": "更新标题", "priority": "urgent"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "更新标题"

    def test_get_single_ticket(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/repair/tickets",
            json={"title": "查单条", "location": "Z-1", "description": "test"},
        )
        ticket_id = created.json()["id"]
        resp = super_admin_client.get(f"/api/v1/enterprise/repair/tickets/{ticket_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == ticket_id

    def test_get_nonexistent_ticket(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/repair/tickets/99999")
        assert resp.status_code == 404
