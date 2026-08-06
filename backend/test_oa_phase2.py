"""Phase 2c: OA flow lifecycle and approval chain tests."""
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class TestOaLifecycle:
    """CRUD + submit → approve chain + views."""

    def test_create_flow(self, super_admin_client):
        resp = super_admin_client.post(
            "/api/v1/enterprise/oa/flows",
            json={"title": "采购申请", "flow_type": "采购"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["title"] == "采购申请"

    def test_list_flows(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/oa/flows")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_single_flow(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/oa/flows",
            json={"title": "请假申请", "flow_type": "人事"},
        )
        flow_id = created.json()["id"]
        resp = super_admin_client.get(f"/api/v1/enterprise/oa/flows/{flow_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == flow_id

    def test_submit_flow(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/oa/flows",
            json={"title": "报销申请", "flow_type": "财务"},
        )
        flow_id = created.json()["id"]
        resp = super_admin_client.post(
            f"/api/v1/enterprise/oa/flows/{flow_id}/submit",
            json={"approval_steps": [{"approver_id": 1, "step_order": 1}]},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "processing"
        assert resp.json()["current_handler"] == "1"

    def test_submit_non_pending_fails(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/oa/flows",
            json={"title": "重复提交测试", "flow_type": "测试"},
        )
        flow_id = created.json()["id"]
        super_admin_client.post(
            f"/api/v1/enterprise/oa/flows/{flow_id}/submit",
            json={"approval_steps": [{"approver_id": 1, "step_order": 1}]},
        )
        resp = super_admin_client.post(
            f"/api/v1/enterprise/oa/flows/{flow_id}/submit",
            json={"approval_steps": [{"approver_id": 2, "step_order": 1}]},
        )
        assert resp.status_code == 400

    def test_approve_flow(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/oa/flows",
            json={"title": "用印申请", "flow_type": "行政"},
        )
        flow_id = created.json()["id"]
        uid = created.json()["initiator_id"]
        super_admin_client.post(
            f"/api/v1/enterprise/oa/flows/{flow_id}/submit",
            json={"approval_steps": [{"approver_id": uid, "step_order": 1}]},
        )
        resp = super_admin_client.post(
            f"/api/v1/enterprise/oa/flows/{flow_id}/approve",
            json={"action": "approve", "comment": "同意"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    def test_reject_flow(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/oa/flows",
            json={"title": "驳回测试", "flow_type": "测试"},
        )
        flow_id = created.json()["id"]
        uid = created.json()["initiator_id"]
        super_admin_client.post(
            f"/api/v1/enterprise/oa/flows/{flow_id}/submit",
            json={"approval_steps": [{"approver_id": uid, "step_order": 1}]},
        )
        resp = super_admin_client.post(
            f"/api/v1/enterprise/oa/flows/{flow_id}/approve",
            json={"action": "reject", "comment": "不同意"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_approval_records(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/oa/flows",
            json={"title": "记录测试", "flow_type": "测试"},
        )
        flow_id = created.json()["id"]
        super_admin_client.post(
            f"/api/v1/enterprise/oa/flows/{flow_id}/submit",
            json={"approval_steps": [{"approver_id": 1, "step_order": 1}]},
        )
        resp = super_admin_client.get(f"/api/v1/enterprise/oa/flows/{flow_id}/approvals")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_pending(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/oa/pending")
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_get_my_flows(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/oa/my-flows")
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_get_history(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/oa/history")
        assert resp.status_code == 200
        assert "items" in resp.json()

    def test_get_stats(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/oa/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "by_status" in data
        assert "by_type" in data

    def test_multi_step_approval(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/oa/flows",
            json={"title": "多步审批", "flow_type": "综合"},
        )
        flow_id = created.json()["id"]
        uid = created.json()["initiator_id"]
        super_admin_client.post(
            f"/api/v1/enterprise/oa/flows/{flow_id}/submit",
            json={
                "approval_steps": [
                    {"approver_id": uid, "step_order": 1},
                    {"approver_id": 2, "step_order": 2},
                ]
            },
        )
        resp = super_admin_client.post(
            f"/api/v1/enterprise/oa/flows/{flow_id}/approve",
            json={"action": "approve"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "processing"
        assert resp.json()["current_handler"] == "2"
