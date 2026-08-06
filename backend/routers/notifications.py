"""Notification API endpoints — list, unread count, mark read, mark all read, SSE stream.

All endpoints are authenticated and scoped to the current user only.
The SSE endpoint (/stream) uses a query-param token for auth (EventSource
browsers don't support custom headers).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from auth.dependencies import get_current_user
from auth.tokens import decode_access_token
from schemas import NotificationItem, NotificationListResponse, NotificationUnreadCount
from session import get_session_local
from sqlalchemy import text
from store import store

logger = logging.getLogger("replica.notifications")

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

# ── SSE connection pool ───────────────────────────────────────────────
# Keyed by user_id, each queue carries dict messages to be serialised as
# SSE data lines.  The overdue scanner (APScheduler job in main.py) and
# the SSE endpoint itself are the only producers/consumers.
_active_connections: dict[int, asyncio.Queue] = {}


def push_event(user_id: int, event: dict[str, Any]) -> None:
    """Push an SSE event to a connected user. No-op if the user is offline."""
    queue = _active_connections.get(user_id)
    if queue is not None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.debug("SSE queue full for user %d — dropping event", user_id)


# ── REST endpoints ────────────────────────────────────────────────────


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    limit: int = 50,
    offset: int = 0,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """List the current user's notifications, newest first."""
    return store.list_notifications(current_user, limit=limit, offset=offset)


@router.get("/unread-count", response_model=NotificationUnreadCount)
def unread_count(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the number of unread notifications for the current user."""
    return {"unread_count": store.get_unread_count(current_user)}


@router.put("/{notification_id}/read", status_code=status.HTTP_200_OK)
def mark_read(
    notification_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark a single notification as read."""
    updated = store.mark_notification_read(current_user, notification_id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="通知不存在或无权操作",
        )
    return {"ok": True}


@router.put("/read-all", status_code=status.HTTP_200_OK)
def mark_all_read(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Mark all of the current user's unread notifications as read."""
    count = store.mark_all_notifications_read(current_user)
    return {"ok": True, "updated": count}


# ── SSE stream ────────────────────────────────────────────────────────


@router.get("/stream")
async def notification_stream(
    token: str = Query(..., description="JWT access token for auth"),
):
    """SSE endpoint for real-time notification push.

    Browsers' EventSource API does not support custom headers, so the
    token is passed as a query parameter.  The connection is held open
    indefinitely with a 60-second heartbeat.
    """
    # Authenticate via query-param token
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id_val = payload.get("sub")
    token_ver = payload.get("ver")
    if user_id_val is None or token_ver is None:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    try:
        uid = int(user_id_val)
        ver = int(token_ver)
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token payload")

    db = get_session_local()()
    try:
        user_row = db.execute(
            text(
                "SELECT id, username, display_name, default_dept_id, "
                "token_version, is_active, org_id, department_id "
                "FROM users WHERE id = :uid AND is_active = 1 AND token_version = :ver"
            ),
            {"uid": uid, "ver": ver},
        ).mappings().first()
    finally:
        db.close()

    if user_row is None:
        raise HTTPException(status_code=401, detail="User not available or credentials invalid")

    user_id: int = uid
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    _active_connections[user_id] = queue

    async def event_generator():
        # Send retry hint so the browser reconnects after 3 s on disconnect
        yield "retry: 3000\n\n"
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=60)
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    # Heartbeat — SSE comment line, ignored by clients
                    yield ":\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            _active_connections.pop(user_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
