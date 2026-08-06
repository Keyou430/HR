from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class EmbedUrls(BaseModel):
    feishu: str | None = None
    dingtalk: str | None = None


class PortalCatalogItem(BaseModel):
    code: str
    title: str
    description: str
    status: str | None = None


class PortalCatalog(BaseModel):
    items: list[PortalCatalogItem]
    total: int


class PortalBootstrapResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    embed_urls: EmbedUrls
    capabilities: PortalCatalog
    skills: PortalCatalog
    workspace: dict
    portal: dict
    calendar: dict
    knowledge: dict


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    tag: str = Field(default="今天", min_length=1, max_length=32)
    due_time: str | None = Field(default=None, min_length=0, max_length=8)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    tag: str | None = Field(default=None, min_length=1, max_length=32)
    due_time: str | None = Field(default=None, min_length=0, max_length=8)
    done: bool | None = None


class CalendarEventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    tone: Literal["blue", "green", "orange"] = "blue"


class CalendarEventUpdate(CalendarEventCreate):
    pass


class EmbedUrlsUpdate(BaseModel):
    feishu: str | None = None
    dingtalk: str | None = None


class KnowledgeChatRequest(BaseModel):
    question: str = Field(min_length=1)
    scope: str = "all"
    mode: str = "auto"  # "auto" | "rag" | "chat" — auto 由 Hermes 判断，rag/chat 强制指定
    web_search: bool = False
    deep_thinking: bool = False
    command_mode: bool = True  # 是否启用指令识别模式
    session_id: str | None = None  # 会话 ID，用于加载对话历史上下文


class KnowledgeMappingUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None
    permission_scope: Literal["private", "team", "org"] | None = None
    is_default_import_target: bool | None = None


class ChatMessageSave(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    role: str = Field(pattern=r"^(user|assistant)$")
    content: str = Field(min_length=1)
    action: str | None = None
    title: str | None = Field(default=None, max_length=255)
    created_at: str | None = Field(default=None, max_length=32)


# ──────────────────────────────────────────────────────────────────
# Auth schemas (Phase 2)
# ──────────────────────────────────────────────────────────────────


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=72)  # bcrypt 72-byte limit


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None = None
    default_org_id: str | None = None
    default_dept_id: str | None = None
    roles: list[str] = []
    permissions: list[str] = []
    must_change_password: bool = False


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo
    must_change_password: bool = False


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)  # bcrypt 72-byte limit


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=72)
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    email: str | None = Field(default=None, max_length=128)


# ── Admin schemas (account management) ────────────────────────────


class AdminUserItem(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None = None
    is_active: bool
    roles: list[str] = []
    role_names: list[str] = []
    last_login_at: str | None = None
    created_at: str | None = None


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int


class AdminRoleItem(BaseModel):
    id: int
    code: str
    name: str
    description: str | None = None
    is_system: bool = False
    org_id: str | None = None
    permission_codes: list[str] = []
    permissions: list[str] = []  # deprecated alias, kept for compat
    created_at: str | None = None
    updated_at: str | None = None


class AdminRoleCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_]*(:[a-z][a-z0-9_]*)?$")
    description: str | None = Field(default=None, max_length=256)
    org_id: str | None = None
    permission_codes: list[str] = []


class AdminRoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=256)


class AdminRolePermissionUpdateRequest(BaseModel):
    permission_codes: list[str]


class AdminRoleListResponse(BaseModel):
    items: list[AdminRoleItem]


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=72)
    display_name: str | None = Field(default=None, min_length=1, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    is_admin: bool = False


class AdminSetActiveRequest(BaseModel):
    is_active: bool


class AdminSetRolesRequest(BaseModel):
    role_codes: list[str]


class AdminResetPasswordRequest(BaseModel):
    """管理员重置用户密码 — 可指定新密码或自动生成"""
    password: str | None = Field(
        default=None, min_length=8, max_length=72,
        description="自定义新密码；不传则自动生成随机密码"
    )


class AdminResetPasswordResponse(BaseModel):
    """返回一次性明文密码 — 仅此响应中包含，不存日志/数据库"""
    user_id: int
    username: str
    display_name: str
    password: str          # 明文，仅本次返回
    must_change_password: bool  # 始终为 True


# ── Phase 6: Audit & Session schemas ──────────────────────────────


class AuditLogItem(BaseModel):
    id: int
    request_id: str
    user_id: int | None = None
    org_id: str | None = None
    department_id: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    decision: str
    reason: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    detail_json: str | None = None
    created_at: str | None = None


class AuditLogListResponse(BaseModel):
    items: list[AuditLogItem]
    total: int


class AIQueryLogItem(BaseModel):
    id: int
    request_id: str
    user_id: int
    org_id: str | None = None
    department_id: str | None = None
    query_hash: str
    query_snippet: str | None = None
    risk_label: str | None = None
    policy_version: str
    decision: str
    blocked_reason: str | None = None
    accessible_resource_count: int = 0
    response_time_ms: int | None = None
    created_at: str | None = None


class AIQueryLogListResponse(BaseModel):
    items: list[AIQueryLogItem]
    total: int


class AdminSessionItem(BaseModel):
    id: str
    user_id: int
    username: str | None = None
    display_name: str | None = None
    user_agent: str | None = None
    ip_address: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    created_at: str | None = None
    is_active: bool


class AdminSessionListResponse(BaseModel):
    items: list[AdminSessionItem]
    total: int


class AdminSessionRevokeRequest(BaseModel):
    session_id: str


class AnomalyStats(BaseModel):
    total_users: int
    active_users: int
    disabled_users: int
    total_sessions: int
    active_sessions: int
    recent_failed_logins_24h: int
    recent_403_24h: int
    recent_ai_blocks_24h: int
    recent_injections_24h: int


# ── T5: Admin org/department schemas ───────────────────────────────


class AdminOrgItem(BaseModel):
    id: str
    name: str
    is_active: bool
    created_at: str | None = None
    updated_at: str | None = None


class AdminOrgCreateRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=128)


class AdminOrgUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    is_active: bool | None = None


class AdminOrgListResponse(BaseModel):
    items: list[AdminOrgItem]
    total: int


class AdminDeptItem(BaseModel):
    id: str
    org_id: str
    name: str
    parent_id: str | None = None
    path: str = ""
    level: int = 0
    sort_order: int = 0
    is_active: bool = True
    children: list["AdminDeptItem"] = []
    created_at: str | None = None
    updated_at: str | None = None


class AdminDeptCreateRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    org_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    parent_id: str | None = None


class AdminDeptUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: str | None = None
    is_active: bool | None = None


class AdminDeptReorderItem(BaseModel):
    id: str
    sort_order: int


class AdminDeptReorderRequest(BaseModel):
    items: list[AdminDeptReorderItem]


class AdminDeptListResponse(BaseModel):
    items: list[AdminDeptItem]
    total: int


# ── T5: Admin notice schemas ────────────────────────────────────────


class AdminNoticeCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    source: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1)
    pinned: bool = False
    published_at: str = Field(min_length=1, max_length=32)
    org_id: str | None = None
    visibility: str = "org"


class AdminNoticeUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    source: str | None = Field(default=None, min_length=1, max_length=128)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    body: str | None = Field(default=None, min_length=1)
    pinned: bool | None = None
    published_at: str | None = Field(default=None, min_length=1, max_length=32)
    org_id: str | None = None
    visibility: str | None = None


class AdminNoticeItem(BaseModel):
    id: int
    title: str
    source: str
    category: str
    body: str
    pinned: bool = False
    published_at: str
    read_count: int = 0
    status: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    visibility: str = "org"
    created_at: str | None = None
    updated_at: str | None = None


class AdminNoticeListResponse(BaseModel):
    items: list[AdminNoticeItem]
    total: int


# ── T5: Admin service schemas ───────────────────────────────────────


class AdminServiceCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")
    title: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1)
    materials: str = ""
    audience: str = Field(min_length=1, max_length=128)
    contact: str = Field(min_length=1, max_length=128)
    status: str = "active"


class AdminServiceUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, min_length=1)
    materials: str | None = None
    audience: str | None = Field(default=None, min_length=1, max_length=128)
    contact: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = None


class AdminServiceItem(BaseModel):
    code: str
    title: str
    category: str
    description: str
    materials: str = ""
    audience: str
    contact: str
    status: str = "active"
    subscribed_count: int = 0
    org_id: str | None = None
    department_id: str | None = None
    visibility: str = "org"
    created_at: str | None = None
    updated_at: str | None = None


class AdminServiceListResponse(BaseModel):
    items: list[AdminServiceItem]
    total: int


# ── T7: Notification schemas ───────────────────────────────────────────

class NotificationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    title: str
    content: str | None = None
    type: str = "info"
    reference_type: str | None = None
    reference_id: str | None = None
    is_read: bool = False
    org_id: str | None = None
    department_id: str | None = None
    created_at: str | None = None


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    total: int


class NotificationUnreadCount(BaseModel):
    unread_count: int


# ── Phase 2: Repair schemas ──────────────────────────────────────────


class RepairTicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    location: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|urgent)$")


class RepairTicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, min_length=1)
    priority: str | None = Field(default=None, pattern=r"^(low|normal|high|urgent)$")
    status: str | None = None
    assignee: str | None = Field(default=None, max_length=128)


class AssignRepairRequest(BaseModel):
    assignee: str = Field(min_length=1, max_length=128)


class RateRepairRequest(BaseModel):
    rating: int = Field(ge=1, le=5)


class RepairTicketItem(BaseModel):
    id: int
    title: str
    location: str
    description: str
    priority: str = "normal"
    status: str = "submitted"
    assignee: str | None = None
    requester_id: int | None = None
    rating: int | None = None
    completed_at: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    owner_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class RepairTicketListResponse(BaseModel):
    items: list[RepairTicketItem]
    total: int


class RepairStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]


# ── Phase 2: Asset schemas ───────────────────────────────────────────


class AssetItemCreate(BaseModel):
    asset_code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=128)
    location: str = Field(min_length=1, max_length=255)
    custodian: str | None = Field(default=None, max_length=128)


class AssetItemUpdate(BaseModel):
    asset_code: str | None = Field(default=None, min_length=1, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=128)
    location: str | None = Field(default=None, min_length=1, max_length=255)
    custodian: str | None = Field(default=None, max_length=128)
    status: str | None = None


class AssetItemResponse(BaseModel):
    id: int
    asset_code: str
    name: str
    category: str
    location: str
    status: str = "available"
    custodian: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    owner_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AssetItemListResponse(BaseModel):
    items: list[AssetItemResponse]
    total: int


class BorrowAssetRequest(BaseModel):
    expected_return_date: str | None = Field(default=None, max_length=32)


class BorrowRecordItem(BaseModel):
    id: int
    asset_id: int
    user_id: int
    borrow_date: str
    expected_return_date: str | None = None
    actual_return_date: str | None = None
    status: str = "borrowed"
    created_at: str | None = None
    updated_at: str | None = None


class AssetStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_category: dict[str, int]
    borrowed_count: int


# ── Phase 2: OA schemas ──────────────────────────────────────────────


class OaFlowCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    flow_type: str = Field(min_length=1, max_length=128)


class OaFlowUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    flow_type: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = None
    current_handler: str | None = Field(default=None, max_length=128)


class OaFlowSubmitRequest(BaseModel):
    approval_steps: list[dict[str, Any]] = Field(min_length=1)


class OaStepActionRequest(BaseModel):
    action: str = Field(pattern=r"^(approve|reject|return)$")
    comment: str | None = None


class OaFlowItem(BaseModel):
    id: int
    title: str
    flow_type: str
    status: str = "pending"
    initiator_id: int | None = None
    current_handler: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    owner_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class OaFlowListResponse(BaseModel):
    items: list[OaFlowItem]
    total: int


class OaApprovalRecordItem(BaseModel):
    id: int
    flow_id: int
    approver_id: int
    step_order: int
    action: str | None = None
    comment: str | None = None
    created_at: str | None = None


class OaApprovalRecordListResponse(BaseModel):
    items: list[OaApprovalRecordItem]
    total: int


class OaStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]


# ── Phase 2: Enterprise subsystem workbench schemas ──────────────────


class EnterpriseSubsystemRecordsResponse(BaseModel):
    code: str
    title: str
    metrics: dict[str, Any]
    records: list[dict[str, Any]]
    columns: list[str]


# ── Phase 3: HR schemas ──────────────────────────────────────────────


class HrRequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    request_type: str = Field(min_length=1, max_length=32, pattern=r"^(certificate|attendance|leave)$")
    content_json: str | None = Field(default=None, max_length=4000)
    approved_by: int | None = None


class HrRequestUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    request_type: str | None = Field(default=None, min_length=1, max_length=32)
    content_json: str | None = Field(default=None, max_length=4000)
    approved_by: int | None = None
    status: str | None = None


class HrApproveRequest(BaseModel):
    action: str = Field(pattern=r"^(approve|reject)$")
    comment: str | None = None


class HrRequestItem(BaseModel):
    id: int
    title: str
    request_type: str
    status: str = "pending"
    applicant_id: int | None = None
    content_json: str | None = None
    approved_by: int | None = None
    approved_at: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    owner_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class HrRequestListResponse(BaseModel):
    items: list[HrRequestItem]
    total: int


class HrStaffItem(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None = None
    phone: str | None = None
    is_active: bool = True
    last_login_at: str | None = None
    created_at: str | None = None


class HrStaffListResponse(BaseModel):
    items: list[HrStaffItem]
    total: int


class HrStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_type: dict[str, int]


# ── Phase 3: Finance schemas ──────────────────────────────────────────


class FinanceClaimCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    amount: float | None = None
    budget_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)


class FinanceClaimUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    amount: float | None = None
    budget_id: int | None = None
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = None
    current_handler: str | None = Field(default=None, max_length=128)


class FinanceClaimSubmitRequest(BaseModel):
    approval_steps: list[dict[str, Any]] = Field(min_length=1)


class FinanceClaimApproveRequest(BaseModel):
    action: str = Field(pattern=r"^(approve|reject|return)$")
    comment: str | None = None


class FinanceClaimItem(BaseModel):
    id: int
    title: str
    amount: float | None = None
    status: str = "pending"
    applicant_id: int | None = None
    budget_id: int | None = None
    current_handler: str | None = None
    description: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class FinanceClaimListResponse(BaseModel):
    items: list[FinanceClaimItem]
    total: int


class FinanceApprovalRecordItem(BaseModel):
    id: int
    claim_id: int
    approver_id: int
    step_order: int
    action: str | None = None
    comment: str | None = None
    created_at: str | None = None


class FinanceApprovalRecordListResponse(BaseModel):
    items: list[FinanceApprovalRecordItem]
    total: int


class FinanceClaimStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]


class FinanceBudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=128)
    amount_total: float = Field(default=0.0, ge=0)
    fiscal_year: int = Field(ge=2000, le=2100)
    description: str | None = Field(default=None, max_length=2000)


class FinanceBudgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=128)
    amount_total: float | None = Field(default=None, ge=0)
    amount_used: float | None = Field(default=None, ge=0)
    fiscal_year: int | None = Field(default=None, ge=2000, le=2100)
    description: str | None = Field(default=None, max_length=2000)


class FinanceBudgetItem(BaseModel):
    id: int
    name: str
    category: str
    amount_total: float = 0.0
    amount_used: float = 0.0
    fiscal_year: int
    description: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class FinanceBudgetListResponse(BaseModel):
    items: list[FinanceBudgetItem]
    total: int


class FinanceBudgetStatsResponse(BaseModel):
    total: int
    total_amount: float
    total_used: float
    by_category: dict[str, int]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Website (网站群) schemas
# ═══════════════════════════════════════════════════════════════════════════


class CmsSiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    category: str = Field(min_length=1, max_length=128)
    status: str = "draft"
    owner_dept: str | None = Field(default=None, max_length=128)
    columns_json: str | None = None
    description: str | None = None


class CmsSiteUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, min_length=1, max_length=128)
    status: str | None = None
    owner_dept: str | None = Field(default=None, max_length=128)
    columns_json: str | None = None
    description: str | None = None


class CmsSiteItem(BaseModel):
    id: int
    name: str
    domain: str | None = None
    category: str
    status: str = "draft"
    owner_dept: str | None = None
    columns_json: str | None = None
    description: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    owner_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class CmsSiteListResponse(BaseModel):
    items: list[CmsSiteItem]
    total: int


class CmsSiteStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_category: dict[str, int]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Estate (房产管理) schemas
# ═══════════════════════════════════════════════════════════════════════════


class EstateSpaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    building: str | None = Field(default=None, max_length=128)
    floor: str | None = Field(default=None, max_length=32)
    area_sqm: float | None = None
    status: str = "vacant"
    department_id: str | None = Field(default=None, max_length=64)
    description: str | None = None
    contact_person: str | None = Field(default=None, max_length=128)


class EstateSpaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    code: str | None = Field(default=None, min_length=1, max_length=128)
    category: str | None = Field(default=None, min_length=1, max_length=64)
    building: str | None = Field(default=None, max_length=128)
    floor: str | None = Field(default=None, max_length=32)
    area_sqm: float | None = None
    status: str | None = None
    department_id: str | None = Field(default=None, max_length=64)
    description: str | None = None
    contact_person: str | None = Field(default=None, max_length=128)


class EstateSpaceItem(BaseModel):
    id: int
    name: str
    code: str
    category: str
    building: str | None = None
    floor: str | None = None
    area_sqm: float | None = None
    status: str = "vacant"
    department_id: str | None = None
    description: str | None = None
    contact_person: str | None = None
    org_id: str | None = None
    owner_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class EstateSpaceListResponse(BaseModel):
    items: list[EstateSpaceItem]
    total: int


class EstateSpaceStatsResponse(BaseModel):
    total: int
    by_category: dict[str, int]
    by_status: dict[str, int]


# ═══════════════════════════════════════════════════════════════════════════
# Phase 4: Employment (就业系统) schemas
# ═══════════════════════════════════════════════════════════════════════════


class JobPostingCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    company_name: str = Field(min_length=1, max_length=255)
    position_category: str = Field(min_length=1, max_length=64)
    salary_range: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    requirements: str | None = None
    status: str = "open"
    contact_info: str | None = Field(default=None, max_length=255)
    description: str | None = None
    posted_date: str | None = Field(default=None, max_length=32)
    deadline: str | None = Field(default=None, max_length=32)


class JobPostingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    company_name: str | None = Field(default=None, min_length=1, max_length=255)
    position_category: str | None = Field(default=None, min_length=1, max_length=64)
    salary_range: str | None = Field(default=None, max_length=128)
    location: str | None = Field(default=None, max_length=255)
    requirements: str | None = None
    status: str | None = None
    contact_info: str | None = Field(default=None, max_length=255)
    description: str | None = None
    posted_date: str | None = Field(default=None, max_length=32)
    deadline: str | None = Field(default=None, max_length=32)


class JobPostingItem(BaseModel):
    id: int
    title: str
    company_name: str
    position_category: str
    salary_range: str | None = None
    location: str | None = None
    requirements: str | None = None
    status: str = "open"
    contact_info: str | None = None
    description: str | None = None
    posted_date: str | None = None
    deadline: str | None = None
    org_id: str | None = None
    department_id: str | None = None
    owner_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


class JobPostingListResponse(BaseModel):
    items: list[JobPostingItem]
    total: int


class JobPostingStatsResponse(BaseModel):
    total: int
    by_category: dict[str, int]
    by_status: dict[str, int]
