from typing import Any

from fastapi import APIRouter, Depends, Query

from auth.dependencies import require_permission
from store import store


router = APIRouter(
    prefix="/api/v1/search",
    tags=["search"],
    dependencies=[Depends(require_permission("search:view"))],
)


@router.get("")
async def global_search(
    q: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: dict[str, Any] = Depends(require_permission("search:view")),
) -> dict:
    return store.search(q, user=current_user, limit=limit)
