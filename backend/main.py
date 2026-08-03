"""FastAPI application entry point for the collaboration portal."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from admin_router import router as admin_router
from auth.router import router as auth_router
from calendar_api import router as calendar_router
from chat_api import router as chat_router
from integrations import router as integrations_router
from knowledge import router as knowledge_router
from portal import router as portal_router
from search import router as search_router
from tasks import router as tasks_router

logger = logging.getLogger("replica")


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup: verify security-critical configuration."""
    from config import get_settings

    settings = get_settings()
    if settings.jwt_secret_is_default:
        logger.critical(
            "SECURITY: JWT_SECRET_KEY is still the default value. "
            "Generate a real secret:  python -c \"import secrets; print(secrets.token_hex(32))\"  "
            "Set it via the JWT_SECRET_KEY environment variable before deploying to production."
        )
    yield


app = FastAPI(
    title="Collaboration Portal API",
    description="统一协同门户后端接口",
    version="0.1.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(portal_router)
app.include_router(tasks_router)
app.include_router(calendar_router)
app.include_router(integrations_router)
app.include_router(knowledge_router)
app.include_router(chat_router)
app.include_router(search_router)
app.include_router(admin_router)
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
