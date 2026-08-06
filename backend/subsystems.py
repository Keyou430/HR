from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import get_current_user, require_permission
from store import store


router = APIRouter(
    prefix="/api/v1/subsystems",
    tags=["subsystems"],
    dependencies=[Depends(get_current_user)],
)


@router.get("")
async def list_subsystems(
    q: str = Query(default=""),
    category: str = Query(default=""),
    status: str = Query(default=""),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    return store.list_subsystems(query=q, category=category, status=status, user=current_user)


@router.get("/{code}")
async def get_subsystem(
    code: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    subsystem = store.get_subsystem(code, user=current_user)
    if subsystem is None or subsystem.get("status") == "disabled":
        raise HTTPException(status_code=404, detail="subsystem not found")
    return subsystem


@router.post("/{code}/visit")
async def visit_subsystem(
    code: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    result = store.record_subsystem_visit(code, user=current_user)
    if result is None:
        raise HTTPException(status_code=404, detail="subsystem not available")
    return result


@router.get("/{code}/dashboard")
async def get_subsystem_dashboard(
    code: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    dashboard = store.subsystem_dashboard(code, user=current_user)
    if dashboard is None:
        raise HTTPException(status_code=404, detail="subsystem not found")
    return dashboard


@router.post("", dependencies=[Depends(require_permission("system:config"))])
async def create_subsystem_not_enabled() -> dict:
    raise HTTPException(status_code=405, detail="subsystem management is handled in the admin portal configuration")
