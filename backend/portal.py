from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException

from auth.dependencies import get_current_user
from config import Settings, get_settings
from schemas import PortalBootstrapResponse
from store import store


router = APIRouter(
    prefix="/api/v1/portal",
    tags=["portal"],
    dependencies=[Depends(get_current_user)],
)

CAPABILITIES: list[dict[str, Any]] = [
    {
        "code": "workspace",
        "title": "个人工作台",
        "description": "聚合待办、公告、日程和常用资源。",
        "status": "available",
    },
    {
        "code": "knowledge",
        "title": "知识库",
        "description": "组织知识检索、AI 问答和知识空间管理。",
        "status": "available",
    },
    {
        "code": "calendar",
        "title": "日历会议",
        "description": "日程、会议和会议室入口。",
        "status": "available",
    },
]

SKILLS: list[dict[str, Any]] = [
    {"code": "notice", "title": "公告", "description": "通知中心"},
    {"code": "ai_assistant", "title": "智能问答", "description": "AI 助手"},
    {"code": "meeting", "title": "会议", "description": "会议管理"},
    {"code": "form", "title": "表单", "description": "流程申请"},
    {"code": "approval", "title": "轻审批", "description": "审批中心"},
    {"code": "note", "title": "笔记", "description": "我的笔记"},
    {"code": "report", "title": "汇报", "description": "工作汇报"},
    {"code": "calendar", "title": "日历", "description": "日程管理"},
    {"code": "task", "title": "待办中心", "description": "任务管理"},
    {"code": "portal", "title": "融合门户", "description": "门户首页"},
    {"code": "document", "title": "云文档", "description": "文档协作"},
    {"code": "service", "title": "服务台", "description": "统一服务入口"},
]


def build_capability_catalog() -> list[dict[str, Any]]:
    return [item.copy() for item in CAPABILITIES]


def build_skills_catalog() -> list[dict[str, Any]]:
    return [item.copy() for item in SKILLS]


@router.get("/bootstrap", response_model=PortalBootstrapResponse)
async def portal_bootstrap(
    settings: Annotated[Settings, Depends(get_settings)],
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    capabilities = build_capability_catalog()
    skills = build_skills_catalog()
    payload = store.bootstrap_payload(user=current_user)

    # Override the hardcoded profile with the authenticated user's identity
    payload.setdefault("portal", {})["profile"] = {
        "name": current_user.get("display_name", current_user.get("username", "")),
        "department": current_user.get("default_dept_id") or "",
        "last_login": current_user.get("last_login_at") or "",
    }

    return {
        "embed_urls": {
            "feishu": store.embed_urls.get("feishu") or settings.FEISHU_EMBED_URL,
            "dingtalk": store.embed_urls.get("dingtalk") or settings.DINGTALK_EMBED_URL,
        },
        "capabilities": {
            "items": capabilities,
            "total": len(capabilities),
        },
        "skills": {
            "items": skills,
            "total": len(skills),
        },
        **payload,
    }


@router.get("/notices")
async def list_notices(current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    return store.list_portal_assets("notices", user=current_user)


@router.get("/notices/{notice_id}")
async def get_notice(notice_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    item = store.get_portal_asset("notices", str(notice_id), user=current_user)
    if item is None:
        raise HTTPException(status_code=404, detail="notice not found")
    return item


@router.get("/documents")
async def list_documents(current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    return store.list_portal_assets("documents", user=current_user)


@router.get("/documents/{document_id}")
async def get_document(document_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    item = store.get_portal_asset("documents", str(document_id), user=current_user)
    if item is None:
        raise HTTPException(status_code=404, detail="document not found")
    return item


@router.get("/resources")
async def list_resources(current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    return store.list_portal_assets("resources", user=current_user)


@router.get("/resources/{code}")
async def get_resource(code: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    item = store.get_portal_asset("resources", code, user=current_user)
    if item is None:
        raise HTTPException(status_code=404, detail="resource not found")
    return item


@router.get("/services")
async def list_services(current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    return store.list_portal_assets("services", user=current_user)


@router.get("/services/{code}")
async def get_service(code: str, current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    item = store.get_portal_asset("services", code, user=current_user)
    if item is None:
        raise HTTPException(status_code=404, detail="service not found")
    return item


@router.get("/news")
async def list_news(current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    return store.list_portal_assets("news", user=current_user)


@router.get("/news/{news_id}")
async def get_news(news_id: int, current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    item = store.get_portal_asset("news", str(news_id), user=current_user)
    if item is None:
        raise HTTPException(status_code=404, detail="news not found")
    return item


@router.get("/preferences")
async def get_preferences(current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    return store.get_portal_preferences(user=current_user)


@router.put("/preferences")
async def update_preferences(
    payload: dict[str, Any] = Body(default_factory=dict),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    return store.update_portal_preferences(payload, user=current_user)


@router.get("/dashboard")
async def get_portal_dashboard(current_user: dict[str, Any] = Depends(get_current_user)) -> dict:
    return store.portal_dashboard(user=current_user)
