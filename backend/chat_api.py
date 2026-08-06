"""聊天记录持久化 API — 会话和消息的保存与查询。

All endpoints require authentication.  Phase 4 scopes every chat session
to the user who created it — users can only see, read, and delete their
own sessions.
"""

from typing import Any

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
async def list_sessions(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    """列出当前用户的聊天会话（按最近更新时间倒序）。"""
    return store.list_chat_sessions(user=current_user)


@router.get("/sessions/{session_id}/messages")
async def get_messages(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    """获取指定会话的消息（仅限当前用户的会话）。"""
    return store.get_chat_messages(session_id, user=current_user)


@router.post("/messages")
async def save_message(
    payload: ChatMessageSave,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    """保存一条聊天消息（自动创建或更新所属会话，绑定当前用户）。"""
    store.save_chat_message(
        session_id=payload.session_id,
        role=payload.role,
        content=payload.content,
        action=payload.action,
        title=payload.title,
        created_at=payload.created_at,
        user_id=current_user["id"],
    )
    return {"ok": True}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, bool]:
    """删除整个会话及其所有消息（仅限当前用户的会话）。"""
    if not store.delete_chat_session(session_id, user=current_user):
        raise HTTPException(status_code=404, detail="session not found")
    return {"ok": True}
