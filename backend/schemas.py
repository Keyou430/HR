from typing import Literal

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


class KnowledgeMappingUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    enabled: bool | None = None
    permission_scope: Literal["private", "team", "org"] | None = None
    is_default_import_target: bool | None = None
