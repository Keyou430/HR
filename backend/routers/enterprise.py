"""Enterprise API endpoints — repair, asset, OA, HR, finance, data portal, and subsystem workbench.

Phase 2-3: full CRUD + lifecycle operations for all enterprise modules.
"""

from __future__ import annotations

import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.responses import StreamingResponse

from auth.dependencies import get_current_user, require_permission
from schemas import (
    AssetItemCreate,
    AssetItemUpdate,
    AssignRepairRequest,
    BorrowAssetRequest,
    CmsSiteCreate,
    CmsSiteUpdate,
    EstateSpaceCreate,
    EstateSpaceUpdate,
    FinanceBudgetCreate,
    FinanceBudgetUpdate,
    FinanceClaimApproveRequest,
    FinanceClaimCreate,
    FinanceClaimSubmitRequest,
    FinanceClaimUpdate,
    HrApproveRequest,
    HrRequestCreate,
    HrRequestUpdate,
    JobPostingCreate,
    JobPostingUpdate,
    OaFlowCreate,
    OaFlowSubmitRequest,
    OaStepActionRequest,
    OaFlowUpdate,
    RateRepairRequest,
    RepairTicketCreate,
    RepairTicketUpdate,
)
from store import store

router = APIRouter(prefix="/api/v1/enterprise", tags=["enterprise"])


# ═══════════════════════════════════════════════════════════════════════
# Repair tickets
# ═══════════════════════════════════════════════════════════════════════


@router.get("/repair/tickets")
def list_repair_tickets(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_repair_tickets(user=current_user)


@router.get("/repair/tickets/{ticket_id}")
def get_repair_ticket(
    ticket_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    ticket = store.get_repair_ticket(ticket_id, user=current_user)
    if ticket is None:
        raise HTTPException(status_code=404, detail="工单不存在或无权访问")
    return ticket


@router.post("/repair/tickets", status_code=201)
def create_repair_ticket(
    body: RepairTicketCreate,
    current_user: dict[str, Any] = Depends(require_permission("repair:create")),
) -> dict[str, Any]:
    return store.create_repair_ticket(body.model_dump(), user=current_user)


@router.patch("/repair/tickets/{ticket_id}")
def update_repair_ticket(
    ticket_id: int,
    body: RepairTicketUpdate,
    current_user: dict[str, Any] = Depends(require_permission("repair:update")),
) -> dict[str, Any]:
    updated = store.update_repair_ticket(ticket_id, body.model_dump(exclude_none=True), user=current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="工单不存在或无权操作")
    return updated


@router.post("/repair/tickets/{ticket_id}/assign")
def assign_repair_ticket(
    ticket_id: int,
    body: AssignRepairRequest,
    current_user: dict[str, Any] = Depends(require_permission("repair:assign")),
) -> dict[str, Any]:
    try:
        updated = store.assign_repair_ticket(ticket_id, body.assignee, user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="工单不存在或无权操作")
    return updated


@router.post("/repair/tickets/{ticket_id}/complete")
def complete_repair_ticket(
    ticket_id: int,
    current_user: dict[str, Any] = Depends(require_permission("repair:update")),
) -> dict[str, Any]:
    try:
        updated = store.complete_repair_ticket(ticket_id, user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="工单不存在或无权操作")
    return updated


@router.post("/repair/tickets/{ticket_id}/rate")
def rate_repair_ticket(
    ticket_id: int,
    body: RateRepairRequest,
    current_user: dict[str, Any] = Depends(require_permission("repair:close")),
) -> dict[str, Any]:
    try:
        updated = store.rate_repair_ticket(ticket_id, body.rating, user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="工单不存在或无权操作")
    return updated


@router.get("/repair/stats")
def repair_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_repair_stats(user=current_user)


# ═══════════════════════════════════════════════════════════════════════
# Asset items
# ═══════════════════════════════════════════════════════════════════════


@router.get("/assets/items")
def list_asset_items(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_asset_items(user=current_user)


@router.get("/assets/items/{item_id}")
def get_asset_item(
    item_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    item = store.get_asset_item(item_id, user=current_user)
    if item is None:
        raise HTTPException(status_code=404, detail="资产不存在或无权访问")
    return item


@router.post("/assets/items", status_code=201)
def create_asset_item(
    body: AssetItemCreate,
    current_user: dict[str, Any] = Depends(require_permission("asset:create")),
) -> dict[str, Any]:
    return store.create_asset_item(body.model_dump(), user=current_user)


@router.patch("/assets/items/{item_id}")
def update_asset_item(
    item_id: int,
    body: AssetItemUpdate,
    current_user: dict[str, Any] = Depends(require_permission("asset:update")),
) -> dict[str, Any]:
    updated = store.update_asset_item(item_id, body.model_dump(exclude_none=True), user=current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="资产不存在或无权操作")
    return updated


@router.post("/assets/items/{item_id}/borrow", status_code=201)
def borrow_asset(
    item_id: int,
    body: BorrowAssetRequest = BorrowAssetRequest(),
    current_user: dict[str, Any] = Depends(require_permission("asset:borrow")),
) -> dict[str, Any]:
    try:
        return store.borrow_asset(item_id, body.expected_return_date, user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/assets/borrow/{record_id}/return")
def return_asset(
    record_id: int,
    current_user: dict[str, Any] = Depends(require_permission("asset:update")),
) -> dict[str, Any]:
    try:
        return store.return_asset(record_id, user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/assets/stats")
def asset_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_asset_stats(user=current_user)


# ═══════════════════════════════════════════════════════════════════════
# OA flows
# ═══════════════════════════════════════════════════════════════════════


@router.get("/oa/flows")
def list_oa_flows(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_oa_flows(user=current_user)


@router.get("/oa/flows/{flow_id}")
def get_oa_flow(
    flow_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    flow = store.get_oa_flow(flow_id, user=current_user)
    if flow is None:
        raise HTTPException(status_code=404, detail="流程不存在或无权访问")
    return flow


@router.post("/oa/flows", status_code=201)
def create_oa_flow(
    body: OaFlowCreate,
    current_user: dict[str, Any] = Depends(require_permission("oa:create")),
) -> dict[str, Any]:
    return store.create_oa_flow(body.model_dump(), user=current_user)


@router.patch("/oa/flows/{flow_id}")
def update_oa_flow(
    flow_id: int,
    body: OaFlowUpdate,
    current_user: dict[str, Any] = Depends(require_permission("oa:update")),
) -> dict[str, Any]:
    updated = store.update_oa_flow(flow_id, body.model_dump(exclude_none=True), user=current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="流程不存在或无权操作")
    return updated


@router.post("/oa/flows/{flow_id}/submit")
def submit_oa_flow(
    flow_id: int,
    body: OaFlowSubmitRequest,
    current_user: dict[str, Any] = Depends(require_permission("oa:update")),
) -> dict[str, Any]:
    try:
        updated = store.submit_oa_flow(flow_id, body.approval_steps, user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="流程不存在或无权操作")
    return updated


@router.post("/oa/flows/{flow_id}/approve")
def approve_oa_step(
    flow_id: int,
    body: OaStepActionRequest,
    current_user: dict[str, Any] = Depends(require_permission("oa:update")),
) -> dict[str, Any]:
    try:
        updated = store.approve_oa_step(flow_id, body.action, body.comment, user=current_user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="流程不存在或无权操作")
    return updated


@router.get("/oa/flows/{flow_id}/approvals")
def get_oa_approval_records(
    flow_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_oa_flow_approval_records(flow_id, user=current_user)


@router.get("/oa/pending")
def get_oa_pending(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_oa_pending(user=current_user)


@router.get("/oa/my-flows")
def get_oa_my_flows(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_oa_my_flows(user=current_user)


@router.get("/oa/history")
def get_oa_history(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_oa_history(user=current_user)


@router.get("/oa/stats")
def oa_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_oa_stats(user=current_user)


# ═══════════════════════════════════════════════════════════════════════
# Subsystem workbench (read real records)
# ═══════════════════════════════════════════════════════════════════════

_SUBSYSTEM_CONFIG: dict[str, dict[str, Any]] = {
    "repair": {
        "title": "报修工单",
        "columns": ["id", "title", "location", "status", "priority", "assignee", "created_at"],
    },
    "assets": {
        "title": "资产台账",
        "columns": ["id", "asset_code", "name", "category", "location", "status", "custodian", "created_at"],
    },
    "oa": {
        "title": "待办流程",
        "columns": ["id", "title", "flow_type", "status", "initiator_id", "current_handler", "created_at"],
    },
}


@router.get("/subsystems/{code}/records")
def subsystem_workbench_records(
    code: str,
    current_user: dict[str, Any] = Depends(require_permission("enterprise:records:view")),
) -> dict[str, Any]:
    if code not in _SUBSYSTEM_CONFIG:
        raise HTTPException(status_code=404, detail=f"不支持的子系统: {code}")

    config = _SUBSYSTEM_CONFIG[code]

    if code == "repair":
        result = store.list_repair_tickets(user=current_user)
    elif code == "assets":
        result = store.list_asset_items(user=current_user)
    elif code == "oa":
        result = store.list_oa_flows(user=current_user)
    else:
        result = {"items": [], "total": 0}

    records = result.get("items", [])
    total = result.get("total", 0)

    return {
        "code": code,
        "title": config["title"],
        "metrics": {"total": total},
        "records": records,
        "columns": config["columns"],
    }


# ═══════════════════════════════════════════════════════════════════════
# Phase 3a: HR (人事系统)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/hr/requests")
def list_hr_requests(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_hr_requests(user=current_user)


@router.get("/hr/requests/my-pending")
def hr_my_pending(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_hr_pending(user=current_user)


@router.get("/hr/requests/my-initiated")
def hr_my_initiated(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_hr_my_initiated(user=current_user)


@router.get("/hr/requests/{request_id}")
def get_hr_request(
    request_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    request = store.get_hr_request(request_id, user=current_user)
    if request is None:
        raise HTTPException(status_code=404, detail="申请不存在或无权访问")
    return request


@router.post("/hr/requests", status_code=status.HTTP_201_CREATED)
def create_hr_request(
    payload: HrRequestCreate,
    current_user: dict[str, Any] = Depends(require_permission("hr:create")),
) -> dict[str, Any]:
    return store.create_hr_request(payload.model_dump(), user=current_user)


@router.patch("/hr/requests/{request_id}")
def update_hr_request(
    request_id: int,
    payload: HrRequestUpdate,
    current_user: dict[str, Any] = Depends(require_permission("hr:update")),
) -> dict[str, Any]:
    updated = store.update_hr_request(request_id, payload.model_dump(exclude_unset=True), user=current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="申请不存在或无权操作")
    return updated


@router.post("/hr/requests/{request_id}/approve")
def approve_hr_request(
    request_id: int,
    payload: HrApproveRequest,
    current_user: dict[str, Any] = Depends(require_permission("hr:update")),
) -> dict[str, Any]:
    try:
        result = store.approve_hr_request(
            request_id, action=payload.action, comment=payload.comment, user=current_user
        )
        if result is None:
            raise HTTPException(status_code=404, detail="申请不存在或无权操作")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/hr/staff")
def hr_staff_list(
    dept_id: str | None = None,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_hr_staff(user=current_user, dept_id=dept_id)


@router.get("/hr/stats")
def hr_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_hr_stats(user=current_user)


# ═══════════════════════════════════════════════════════════════════════
# Phase 3b: Finance (财务系统)
# ═══════════════════════════════════════════════════════════════════════

# ── Claims ─────────────────────────────────────────────────────────

@router.get("/finance/claims")
def list_finance_claims(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_finance_claims(user=current_user)


@router.get("/finance/claims/my-pending")
def finance_my_pending(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_finance_my_pending(user=current_user)


@router.get("/finance/claims/my-initiated")
def finance_my_initiated(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_finance_my_initiated(user=current_user)


@router.get("/finance/claims/stats")
def finance_claims_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_finance_claims_stats(user=current_user)


@router.get("/finance/claims/{claim_id}")
def get_finance_claim(
    claim_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    claim = store.get_finance_claim(claim_id, user=current_user)
    if claim is None:
        raise HTTPException(status_code=404, detail="报销单不存在或无权访问")
    return claim


@router.get("/finance/claims/{claim_id}/approvals")
def finance_claim_approvals(
    claim_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_finance_claim_approvals(claim_id, user=current_user)


@router.post("/finance/claims", status_code=status.HTTP_201_CREATED)
def create_finance_claim(
    payload: FinanceClaimCreate,
    current_user: dict[str, Any] = Depends(require_permission("finance:create")),
) -> dict[str, Any]:
    return store.create_finance_claim(payload.model_dump(), user=current_user)


@router.patch("/finance/claims/{claim_id}")
def update_finance_claim(
    claim_id: int,
    payload: FinanceClaimUpdate,
    current_user: dict[str, Any] = Depends(require_permission("finance:create")),
) -> dict[str, Any]:
    updated = store.update_finance_claim(claim_id, payload.model_dump(exclude_unset=True), user=current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="报销单不存在或无权操作")
    return updated


@router.post("/finance/claims/{claim_id}/submit")
def submit_finance_claim(
    claim_id: int,
    payload: FinanceClaimSubmitRequest,
    current_user: dict[str, Any] = Depends(require_permission("finance:create")),
) -> dict[str, Any]:
    try:
        result = store.submit_finance_claim(claim_id, payload.approval_steps, user=current_user)
        if result is None:
            raise HTTPException(status_code=404, detail="报销单不存在或无权操作")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/finance/claims/{claim_id}/approve")
def approve_finance_claim(
    claim_id: int,
    payload: FinanceClaimApproveRequest,
    current_user: dict[str, Any] = Depends(require_permission("finance:approve")),
) -> dict[str, Any]:
    try:
        result = store.approve_finance_claim(
            claim_id, action=payload.action, comment=payload.comment, user=current_user
        )
        if result is None:
            raise HTTPException(status_code=404, detail="报销单不存在或无权操作")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ── Budgets ────────────────────────────────────────────────────────

@router.get("/finance/budgets")
def list_finance_budgets(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_finance_budgets(user=current_user)


@router.get("/finance/budgets/stats")
def finance_budget_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_finance_budget_stats(user=current_user)


@router.get("/finance/budgets/{budget_id}")
def get_finance_budget(
    budget_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    budget = store.get_finance_budget(budget_id, user=current_user)
    if budget is None:
        raise HTTPException(status_code=404, detail="预算项目不存在或无权访问")
    return budget


@router.post("/finance/budgets", status_code=status.HTTP_201_CREATED)
def create_finance_budget(
    payload: FinanceBudgetCreate,
    current_user: dict[str, Any] = Depends(require_permission("finance:create")),
) -> dict[str, Any]:
    return store.create_finance_budget(payload.model_dump(), user=current_user)


@router.patch("/finance/budgets/{budget_id}")
def update_finance_budget(
    budget_id: int,
    payload: FinanceBudgetUpdate,
    current_user: dict[str, Any] = Depends(require_permission("finance:create")),
) -> dict[str, Any]:
    updated = store.update_finance_budget(budget_id, payload.model_dump(exclude_unset=True), user=current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="预算项目不存在或无权操作")
    return updated


# ═══════════════════════════════════════════════════════════════════════
# Phase 3c: Data Portal
# ═══════════════════════════════════════════════════════════════════════


@router.get("/data-portal/overview")
def data_portal_overview(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_data_portal_overview(user=current_user)


# ═══════════════════════════════════════════════════════════════════════
# Phase 4 T17: Website (网站群)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/website/sites")
def list_cms_sites(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_cms_sites(user=current_user)


@router.get("/website/sites/stats")
def cms_site_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_cms_site_stats(user=current_user)


@router.get("/website/sites/{site_id}")
def get_cms_site(
    site_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    item = store.get_cms_site(site_id, user=current_user)
    if item is None:
        raise HTTPException(status_code=404, detail="站点不存在或无权访问")
    return item


@router.post("/website/sites", status_code=201)
def create_cms_site(
    body: CmsSiteCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.create_cms_site(body.model_dump(), user=current_user)


@router.patch("/website/sites/{site_id}")
def update_cms_site(
    site_id: int,
    body: CmsSiteUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    updated = store.update_cms_site(site_id, body.model_dump(exclude_none=True), user=current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="站点不存在或无权操作")
    return updated


# ═══════════════════════════════════════════════════════════════════════
# Phase 4 T17: Estate (房产管理)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/estate/spaces")
def list_estate_spaces(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_estate_spaces(user=current_user)


@router.get("/estate/spaces/stats")
def estate_space_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_estate_space_stats(user=current_user)


@router.get("/estate/spaces/{space_id}")
def get_estate_space(
    space_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    item = store.get_estate_space(space_id, user=current_user)
    if item is None:
        raise HTTPException(status_code=404, detail="空间不存在或无权访问")
    return item


@router.post("/estate/spaces", status_code=201)
def create_estate_space(
    body: EstateSpaceCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.create_estate_space(body.model_dump(), user=current_user)


@router.patch("/estate/spaces/{space_id}")
def update_estate_space(
    space_id: int,
    body: EstateSpaceUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    updated = store.update_estate_space(space_id, body.model_dump(exclude_none=True), user=current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="空间不存在或无权操作")
    return updated


# ═══════════════════════════════════════════════════════════════════════
# Phase 4 T17: Employment (就业系统)
# ═══════════════════════════════════════════════════════════════════════


@router.get("/employment/postings")
def list_job_postings(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_job_postings(user=current_user)


@router.get("/employment/postings/stats")
def job_posting_stats(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.get_job_posting_stats(user=current_user)


@router.get("/employment/postings/{posting_id}")
def get_job_posting(
    posting_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    item = store.get_job_posting(posting_id, user=current_user)
    if item is None:
        raise HTTPException(status_code=404, detail="岗位不存在或无权访问")
    return item


@router.post("/employment/postings", status_code=201)
def create_job_posting(
    body: JobPostingCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.create_job_posting(body.model_dump(), user=current_user)


@router.patch("/employment/postings/{posting_id}")
def update_job_posting(
    posting_id: int,
    body: JobPostingUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    updated = store.update_job_posting(posting_id, body.model_dump(exclude_none=True), user=current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="岗位不存在或无权操作")
    return updated


# ═══════════════════════════════════════════════════════════════════════
# Phase 4 T19: CSV Export
# ═══════════════════════════════════════════════════════════════════════

_EXPORT_TABLES = {
    "repair-tickets": (store._enterprise_repair_tickets_table, [
        "id", "title", "location", "description", "priority", "status",
        "assignee", "requester_id", "rating", "completed_at",
        "org_id", "department_id", "created_at", "updated_at",
    ]),
    "assets": (store._enterprise_asset_items_table, [
        "id", "asset_code", "name", "category", "location", "status",
        "custodian", "org_id", "department_id", "created_at", "updated_at",
    ]),
    "oa-flows": (store._enterprise_oa_flows_table, [
        "id", "title", "flow_type", "status", "initiator_id",
        "current_handler", "org_id", "department_id", "created_at", "updated_at",
    ]),
    "hr-requests": (store._hr_requests_table, [
        "id", "title", "request_type", "status", "applicant_id",
        "approved_by", "approved_at", "org_id", "department_id", "created_at", "updated_at",
    ]),
    "finance-claims": (store._finance_claims_table, [
        "id", "title", "amount", "status", "applicant_id", "budget_id",
        "current_handler", "org_id", "department_id", "created_at", "updated_at",
    ]),
    "finance-budgets": (store._finance_budgets_table, [
        "id", "name", "category", "amount_total", "amount_used",
        "fiscal_year", "org_id", "department_id", "created_at", "updated_at",
    ]),
    "cms-sites": (store._cms_sites_table, [
        "id", "name", "domain", "category", "status", "owner_dept",
        "org_id", "department_id", "created_at", "updated_at",
    ]),
    "estate-spaces": (store._estate_spaces_table, [
        "id", "name", "code", "category", "building", "floor", "area_sqm",
        "status", "department_id", "contact_person", "org_id", "created_at", "updated_at",
    ]),
    "job-postings": (store._job_postings_table, [
        "id", "title", "company_name", "position_category", "salary_range",
        "location", "status", "deadline", "contact_info",
        "org_id", "department_id", "created_at", "updated_at",
    ]),
}


@router.get("/export/{entity}")
def export_entity_csv(
    entity: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Export entity data as CSV (UTF-8 BOM)."""
    if entity not in _EXPORT_TABLES:
        raise HTTPException(status_code=404, detail=f"Unknown entity: {entity}")
    table, columns = _EXPORT_TABLES[entity]
    content, filename, media_type = store._enterprise_export_csv(
        table, user=current_user, columns=columns, filename=entity,
    )
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
