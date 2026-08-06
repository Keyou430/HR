"""Phase 3a: HR request lifecycle, approval, and staff tests."""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class TestHrRequestCRUD:
    """Create, list, get, update HR requests."""

    def test_create_request(self, super_admin_client):
        resp = super_admin_client.post(
            "/api/v1/enterprise/hr/requests",
            json={
                "title": "在职证明申请",
                "request_type": "certificate",
                "content_json": '{"reason": "购房贷款"}',
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "processing"
        assert data["title"] == "在职证明申请"
        assert data["request_type"] == "certificate"

    def test_list_requests(self, super_admin_client):
        super_admin_client.post(
            "/api/v1/enterprise/hr/requests",
            json={"title": "请假", "request_type": "leave"},
        )
        resp = super_admin_client.get("/api/v1/enterprise/hr/requests")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_single_request(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/hr/requests",
            json={"title": "考勤补签", "request_type": "attendance"},
        )
        req_id = created.json()["id"]
        resp = super_admin_client.get(f"/api/v1/enterprise/hr/requests/{req_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == req_id

    def test_update_request(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/hr/requests",
            json={"title": "旧标题", "request_type": "certificate"},
        )
        req_id = created.json()["id"]
        resp = super_admin_client.patch(
            f"/api/v1/enterprise/hr/requests/{req_id}",
            json={"title": "新标题"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "新标题"

    def test_get_nonexistent_request(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/hr/requests/99999")
        assert resp.status_code == 404

    def test_create_requires_auth(self, super_admin_client):
        from fastapi.testclient import TestClient
        from main import app
        with TestClient(app) as c:
            resp = c.post(
                "/api/v1/enterprise/hr/requests",
                json={"title": "test", "request_type": "certificate"},
            )
            assert resp.status_code in (401, 403)


class TestHrApproval:
    """Single-step approval: approve and reject."""

    def test_approve_request(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        # org_admin creates request (has hr:create), designating super_admin as approver
        resp = c.post(
            "/api/v1/enterprise/hr/requests",
            json={
                "title": "在职工资证明",
                "request_type": "certificate",
                "approved_by": admin_uid,
            },
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        req_id = resp.json()["id"]

        # Super admin approves
        resp = c.post(
            f"/api/v1/enterprise/hr/requests/{req_id}/approve",
            json={"action": "approve", "comment": "同意"},
            headers={"Authorization": f"Bearer {tokens['super_admin']}"},
        )
        assert resp.status_code == 200, f"Approve failed: {resp.text}"
        assert resp.json()["status"] == "approved"
        assert resp.json()["approved_at"] is not None

    def test_reject_request(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        resp = c.post(
            "/api/v1/enterprise/hr/requests",
            json={
                "title": "请假申请",
                "request_type": "leave",
                "approved_by": admin_uid,
            },
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        req_id = resp.json()["id"]

        resp = c.post(
            f"/api/v1/enterprise/hr/requests/{req_id}/approve",
            json={"action": "reject", "comment": "不批准"},
            headers={"Authorization": f"Bearer {tokens['super_admin']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_approve_non_processing_fails(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/hr/requests",
            json={"title": "重复审批测试", "request_type": "certificate"},
        )
        req_id = created.json()["id"]
        uid = created.json()["applicant_id"]

        # Set approver to self so first approval succeeds
        super_admin_client.patch(
            f"/api/v1/enterprise/hr/requests/{req_id}",
            json={"approved_by": uid},
        )

        # First approval succeeds
        r = super_admin_client.post(
            f"/api/v1/enterprise/hr/requests/{req_id}/approve",
            json={"action": "approve"},
        )
        assert r.status_code == 200, f"First approve failed: {r.text}"

        # Second approval should fail (already approved)
        resp = super_admin_client.post(
            f"/api/v1/enterprise/hr/requests/{req_id}/approve",
            json={"action": "approve"},
        )
        assert resp.status_code == 400

    def test_non_approver_cannot_approve(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        # org_admin creates request designating super_admin as approver
        resp = c.post(
            "/api/v1/enterprise/hr/requests",
            json={
                "title": "他人审批测试",
                "request_type": "attendance",
                "approved_by": admin_uid,
            },
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert resp.status_code == 201, f"Create failed: {resp.text}"
        req_id = resp.json()["id"]

        # org_admin tries to approve (but admin is the designated approver) — should fail
        resp = c.post(
            f"/api/v1/enterprise/hr/requests/{req_id}/approve",
            json={"action": "approve"},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert resp.status_code == 400


class TestHrViews:
    """My pending, my initiated views."""

    def test_my_pending(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        # org_admin creates request for super_admin to approve
        c.post(
            "/api/v1/enterprise/hr/requests",
            json={
                "title": "待审批测试",
                "request_type": "certificate",
                "approved_by": admin_uid,
            },
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )

        # Admin sees it in pending
        resp = c.get(
            "/api/v1/enterprise/hr/requests/my-pending",
            headers={"Authorization": f"Bearer {tokens['super_admin']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_my_initiated(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        c.post(
            "/api/v1/enterprise/hr/requests",
            json={
                "title": "我发起的测试",
                "request_type": "leave",
                "approved_by": admin_uid,
            },
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )

        resp = c.get(
            "/api/v1/enterprise/hr/requests/my-initiated",
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_pending_empty_for_non_approver(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        # org_admin creates request for super_admin (not for themselves)
        c.post(
            "/api/v1/enterprise/hr/requests",
            json={
                "title": "给admin的申请",
                "request_type": "certificate",
                "approved_by": admin_uid,
            },
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )

        # org_admin should not see it in pending (it's for super_admin)
        resp = c.get(
            "/api/v1/enterprise/hr/requests/my-pending",
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert resp.status_code == 200
        items = resp.json().get("items", [])
        org_pending = [i for i in items if i["title"] == "给admin的申请"]
        assert len(org_pending) == 0


class TestHrStaff:
    """Staff list endpoint."""

    def test_staff_list_as_admin(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/hr/staff")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert "items" in data

    def test_staff_list_as_staff(self, dept_staff_client):
        resp = dept_staff_client.get("/api/v1/enterprise/hr/staff")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1


class TestHrStats:
    """HR statistics endpoint."""

    def test_stats(self, super_admin_client):
        super_admin_client.post(
            "/api/v1/enterprise/hr/requests",
            json={"title": "统计测试1", "request_type": "certificate"},
        )
        super_admin_client.post(
            "/api/v1/enterprise/hr/requests",
            json={"title": "统计测试2", "request_type": "leave"},
        )
        resp = super_admin_client.get("/api/v1/enterprise/hr/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "by_status" in data
        assert "by_type" in data
        assert data["total"] >= 2
