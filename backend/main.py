"""FastAPI application entry point for the collaboration portal."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from calendar_api import router as calendar_router
from integrations import router as integrations_router
from knowledge import router as knowledge_router
from portal import router as portal_router
from search import router as search_router
from tasks import router as tasks_router


app = FastAPI(
    title="Collaboration Portal API",
    description="统一协同门户后端接口",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "null",
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
app.include_router(search_router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
