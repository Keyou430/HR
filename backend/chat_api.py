"""聊天记录持久化 API — 会话和消息的保存与查询。

All endpoints require authentication but no specific permission code.
NOTE: Per-user data isolation (user_id scoping) is deferred to Phase 4.
Currently all authenticated users share the same session namespace.
"""

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from schemas import ChatMessageSave
from store import store

router = APIRouter(
    prefix="/api/v1/chat",
    tags=["chat"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/sessions")
async def list_sessions() -> dict:
    """列出所有聊天会话（按最近更新时间倒序）。"""
    return store.list_chat_sessions()


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str) -> dict:
    """获取指定会话的所有消息。"""
    return store.get_chat_messages(session_id)


@router.post("/messages")
async def save_message(payload: ChatMessageSave) -> dict:
    """保存一条聊天消息（自动创建或更新所属会话）。"""
    store.save_chat_message(
        session_id=payload.session_id,
        role=payload.role,
        content=payload.content,
        action=payload.action,
        title=payload.title,
        created_at=payload.created_at,
    )
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict[str, bool]:
    """删除整个会话及其所有消息。"""
    if not store.delete_chat_session(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}
