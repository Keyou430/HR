from fastapi import APIRouter, Depends

from auth.dependencies import require_permission
from schemas import EmbedUrlsUpdate
from store import store


router = APIRouter(
    prefix="/api/v1/integrations",
    tags=["integrations"],
    dependencies=[Depends(require_permission("org:view"))],
)


@router.get("/embed-urls")
async def get_embed_urls() -> dict:
    return dict(store.embed_urls)


@router.put("/embed-urls",
            dependencies=[Depends(require_permission("org:update"))])
async def update_embed_urls(payload: EmbedUrlsUpdate) -> dict:
    return store.update_embed_urls(payload.model_dump(exclude_none=True))
