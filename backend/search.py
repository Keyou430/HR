from fastapi import APIRouter, Query

from store import store


router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("")
async def global_search(q: str = Query(default="")) -> dict:
    return store.search(q)
