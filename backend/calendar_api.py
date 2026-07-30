from fastapi import APIRouter, HTTPException, status

from schemas import CalendarEventCreate, CalendarEventUpdate
from store import store


router = APIRouter(prefix="/api/v1/calendar/events", tags=["calendar"])


@router.get("")
async def list_calendar_events() -> dict:
    return store.list_events()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_calendar_event(payload: CalendarEventCreate) -> dict:
    return store.create_event(payload.model_dump())


@router.put("/{event_id}")
async def update_calendar_event(event_id: int, payload: CalendarEventUpdate) -> dict:
    event = store.update_event(event_id, payload.model_dump())
    if event is None:
        raise HTTPException(status_code=404, detail="calendar event not found")
    return event


@router.delete("/{event_id}")
async def delete_calendar_event(event_id: int) -> dict[str, bool]:
    if not store.delete_event(event_id):
        raise HTTPException(status_code=404, detail="calendar event not found")
    return {"ok": True}
