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
    permissions: list[str] = []


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
