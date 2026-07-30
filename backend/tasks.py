from fastapi import APIRouter, HTTPException, status

from schemas import TaskCreate, TaskUpdate
from store import store


router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("")
async def list_tasks() -> dict:
    return store.list_tasks()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate) -> dict:
    return store.create_task(payload.model_dump())


@router.patch("/{task_id}")
async def update_task(task_id: int, payload: TaskUpdate) -> dict:
    task = store.update_task(task_id, payload.model_dump(exclude_none=True))
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.delete("/{task_id}")
async def delete_task(task_id: int) -> dict[str, bool]:
    if not store.delete_task(task_id):
        raise HTTPException(status_code=404, detail="task not found")
    return {"ok": True}


@router.post("/clear-done")
async def clear_done_tasks() -> dict[str, int]:
    return {"deleted": store.clear_done_tasks()}
