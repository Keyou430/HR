from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from auth.dependencies import require_permission
from schemas import CalendarEventCreate, CalendarEventUpdate
from store import store


router = APIRouter(
    prefix="/api/v1/calendar/events",
    tags=["calendar"],
    dependencies=[Depends(require_permission("calendar:view"))],
)


@router.get("")
async def list_calendar_events(
    current_user: dict[str, Any] = Depends(require_permission("calendar:view")),
) -> dict:
    return store.list_events(user=current_user)


@router.post("", status_code=status.HTTP_201_CREATED,
              dependencies=[Depends(require_permission("calendar:create"))])
async def create_calendar_event(
    payload: CalendarEventCreate,
    current_user: dict[str, Any] = Depends(require_permission("calendar:create")),
) -> dict:
    return store.create_event(payload.model_dump(), user=current_user)


@router.put("/{event_id}",
            dependencies=[Depends(require_permission("calendar:update"))])
async def update_calendar_event(
    event_id: int,
    payload: CalendarEventUpdate,
    current_user: dict[str, Any] = Depends(require_permission("calendar:update")),
) -> dict:
    event = store.update_event(event_id, payload.model_dump(), user=current_user)
    if event is None:
        raise HTTPException(status_code=404, detail="calendar event not found")
    return event


@router.delete("/{event_id}",
               dependencies=[Depends(require_permission("calendar:delete"))])
async def delete_calendar_event(
    event_id: int,
    current_user: dict[str, Any] = Depends(require_permission("calendar:delete")),
) -> dict[str, bool]:
    if not store.delete_event(event_id, user=current_user):
        raise HTTPException(status_code=404, detail="calendar event not found")
    return {"ok": True}
