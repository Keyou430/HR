from fastapi import APIRouter

from schemas import EmbedUrlsUpdate
from store import store


router = APIRouter(prefix="/api/v1/integrations", tags=["integrations"])


@router.get("/embed-urls")
async def get_embed_urls() -> dict:
    return dict(store.embed_urls)


@router.put("/embed-urls")
async def update_embed_urls(payload: EmbedUrlsUpdate) -> dict:
    return store.update_embed_urls(payload.model_dump(exclude_none=True))
