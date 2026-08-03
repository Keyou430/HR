from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from auth.dependencies import require_permission
from schemas import TaskCreate, TaskUpdate
from store import store


router = APIRouter(
    prefix="/api/v1/tasks",
    tags=["tasks"],
    dependencies=[Depends(require_permission("task:view"))],
)


@router.get("")
async def list_tasks(
    current_user: dict[str, Any] = Depends(require_permission("task:view")),
) -> dict:
    return store.list_tasks(user=current_user)


@router.post("", status_code=status.HTTP_201_CREATED,
              dependencies=[Depends(require_permission("task:create"))])
async def create_task(
    payload: TaskCreate,
    current_user: dict[str, Any] = Depends(require_permission("task:create")),
) -> dict:
    return store.create_task(payload.model_dump(), user=current_user)


@router.patch("/{task_id}",
              dependencies=[Depends(require_permission("task:update"))])
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    current_user: dict[str, Any] = Depends(require_permission("task:update")),
) -> dict:
    task = store.update_task(task_id, payload.model_dump(exclude_none=True), user=current_user)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.delete("/{task_id}",
               dependencies=[Depends(require_permission("task:delete"))])
async def delete_task(
    task_id: int,
    current_user: dict[str, Any] = Depends(require_permission("task:delete")),
) -> dict[str, bool]:
    if not store.delete_task(task_id, user=current_user):
        raise HTTPException(status_code=404, detail="task not found")
    return {"ok": True}


@router.post("/clear-done",
              dependencies=[Depends(require_permission("task:delete"))])
async def clear_done_tasks(
    current_user: dict[str, Any] = Depends(require_permission("task:delete")),
) -> dict[str, int]:
    return {"deleted": store.clear_done_tasks(user=current_user)}
