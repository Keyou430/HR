"""Phase 3b: Finance claims (multi-step approval) and budgets tests."""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class TestFinanceClaimsCRUD:
    """Create, list, get, update claims."""

    def test_create_claim(self, super_admin_client):
        resp = super_admin_client.post(
            "/api/v1/enterprise/finance/claims",
            json={
                "title": "差旅报销",
                "amount": 1500.00,
                "description": "北京出差往返机票",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["status"] == "pending"
        assert data["title"] == "差旅报销"

    def test_list_claims(self, super_admin_client):
        super_admin_client.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "列表示例", "amount": 10.00},
        )
        resp = super_admin_client.get("/api/v1/enterprise/finance/claims")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_single_claim(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "办公用品报销", "amount": 200.00},
        )
        claim_id = created.json()["id"]
        resp = super_admin_client.get(f"/api/v1/enterprise/finance/claims/{claim_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == claim_id

    def test_update_claim(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "旧标题", "amount": 100.00},
        )
        claim_id = created.json()["id"]
        resp = super_admin_client.patch(
            f"/api/v1/enterprise/finance/claims/{claim_id}",
            json={"title": "新标题", "amount": 200.00},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "新标题"

    def test_get_nonexistent_claim(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/finance/claims/99999")
        assert resp.status_code == 404


class TestFinanceClaimApproval:
    """Multi-step approval workflow."""

    def test_submit_and_approve(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        created = c.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "采购报销", "amount": 5000.00},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert created.status_code == 201
        claim_id = created.json()["id"]

        submit = c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/submit",
            json={"approval_steps": [{"approver_id": admin_uid, "step_order": 1}]},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert submit.status_code == 200, f"Submit failed: {submit.text}"
        assert submit.json()["status"] == "processing"

        approve = c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/approve",
            json={"action": "approve", "comment": "同意报销"},
            headers={"Authorization": f"Bearer {tokens['super_admin']}"},
        )
        assert approve.status_code == 200, f"Approve failed: {approve.text}"
        assert approve.json()["status"] == "approved"

    def test_multi_step_approval(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]
        org_admin_uid = all_roles_client["user_ids"]["org_admin"]

        created = c.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "多级审批报销", "amount": 8000.00},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        claim_id = created.json()["id"]

        c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/submit",
            json={
                "approval_steps": [
                    {"approver_id": admin_uid, "step_order": 1},
                    {"approver_id": org_admin_uid, "step_order": 2},
                ]
            },
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )

        # Step 1
        r1 = c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/approve",
            json={"action": "approve"},
            headers={"Authorization": f"Bearer {tokens['super_admin']}"},
        )
        assert r1.status_code == 200
        assert r1.json()["status"] == "processing"
        assert r1.json()["current_handler"] == str(org_admin_uid)

        # Step 2
        r2 = c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/approve",
            json={"action": "approve"},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert r2.status_code == 200
        assert r2.json()["status"] == "approved"

    def test_reject_claim(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        created = c.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "被驳回的报销", "amount": 300.00},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        claim_id = created.json()["id"]

        c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/submit",
            json={"approval_steps": [{"approver_id": admin_uid, "step_order": 1}]},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )

        r = c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/approve",
            json={"action": "reject"},
            headers={"Authorization": f"Bearer {tokens['super_admin']}"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

    def test_wrong_approver_fails(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        created = c.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "越权审批测试", "amount": 100.00},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        claim_id = created.json()["id"]

        c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/submit",
            json={"approval_steps": [{"approver_id": admin_uid, "step_order": 1}]},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )

        r = c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/approve",
            json={"action": "approve"},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert r.status_code == 400

    def test_submit_non_pending_fails(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "重复提交测试", "amount": 50.00},
        )
        claim_id = created.json()["id"]

        super_admin_client.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/submit",
            json={"approval_steps": [{"approver_id": 1, "step_order": 1}]},
        )

        resp = super_admin_client.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/submit",
            json={"approval_steps": [{"approver_id": 2, "step_order": 1}]},
        )
        assert resp.status_code == 400

    def test_approval_records(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        created = c.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "审批记录测试", "amount": 100.00},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        claim_id = created.json()["id"]

        c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/submit",
            json={"approval_steps": [{"approver_id": admin_uid, "step_order": 1}]},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )

        c.post(
            f"/api/v1/enterprise/finance/claims/{claim_id}/approve",
            json={"action": "approve"},
            headers={"Authorization": f"Bearer {tokens['super_admin']}"},
        )

        resp = c.get(
            f"/api/v1/enterprise/finance/claims/{claim_id}/approvals",
            headers={"Authorization": f"Bearer {tokens['super_admin']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1


class TestFinanceViews:
    """My pending, my initiated, stats."""

    def test_my_pending(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]
        admin_uid = all_roles_client["user_ids"]["super_admin"]

        created = c.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "待审批报销", "amount": 200.00},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        c.post(
            f"/api/v1/enterprise/finance/claims/{created.json()['id']}/submit",
            json={"approval_steps": [{"approver_id": admin_uid, "step_order": 1}]},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )

        resp = c.get(
            "/api/v1/enterprise/finance/claims/my-pending",
            headers={"Authorization": f"Bearer {tokens['super_admin']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_my_initiated(self, all_roles_client):
        c = all_roles_client["client"]
        tokens = all_roles_client["tokens"]

        c.post(
            "/api/v1/enterprise/finance/claims",
            json={"title": "我的报销", "amount": 300.00},
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )

        resp = c.get(
            "/api/v1/enterprise/finance/claims/my-initiated",
            headers={"Authorization": f"Bearer {tokens['org_admin']}"},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_stats(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/finance/claims/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "by_status" in data


class TestFinanceBudgets:
    """Budget CRUD + stats."""

    def test_create_budget(self, super_admin_client):
        resp = super_admin_client.post(
            "/api/v1/enterprise/finance/budgets",
            json={
                "name": "2026年IT预算",
                "category": "IT设备",
                "amount_total": 100000.00,
                "fiscal_year": 2026,
            },
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "2026年IT预算"

    def test_list_budgets(self, super_admin_client):
        super_admin_client.post(
            "/api/v1/enterprise/finance/budgets",
            json={"name": "列表测试预算", "category": "测试", "amount_total": 1000, "fiscal_year": 2026},
        )
        resp = super_admin_client.get("/api/v1/enterprise/finance/budgets")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_get_single_budget(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/finance/budgets",
            json={"name": "培训预算", "category": "培训", "amount_total": 50000, "fiscal_year": 2026},
        )
        budget_id = created.json()["id"]
        resp = super_admin_client.get(f"/api/v1/enterprise/finance/budgets/{budget_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == budget_id

    def test_update_budget(self, super_admin_client):
        created = super_admin_client.post(
            "/api/v1/enterprise/finance/budgets",
            json={"name": "旧预算", "category": "办公", "amount_total": 10000, "fiscal_year": 2026},
        )
        budget_id = created.json()["id"]
        resp = super_admin_client.patch(
            f"/api/v1/enterprise/finance/budgets/{budget_id}",
            json={"name": "新预算", "amount_used": 5000.00},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "新预算"

    def test_budget_stats(self, super_admin_client):
        resp = super_admin_client.get("/api/v1/enterprise/finance/budgets/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "total_amount" in data
        assert "total_used" in data
        assert "by_category" in data
