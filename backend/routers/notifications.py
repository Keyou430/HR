"""Notification API endpoints — list, unread count, mark read, mark all read.

All endpoints are authenticated and scoped to the current user only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from schemas import NotificationItem, NotificationListResponse, NotificationUnreadCount
from session import get_db
from store import store

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


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
