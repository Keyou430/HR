"""FastAPI application entry point for the collaboration portal."""

import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from admin_router import router as admin_router
from audit.middleware import AuditMiddleware
from auth.router import router as auth_router
from calendar_api import router as calendar_router
from chat_api import router as chat_router
from config import get_settings
from integrations import router as integrations_router
from knowledge import router as knowledge_router
from portal import router as portal_router
from routers.enterprise import router as enterprise_router
from routers.notifications import router as notifications_router, push_event
from search import router as search_router
from session import get_engine
from subsystems import router as subsystems_router
from tasks import router as tasks_router

# ── JSON log formatter ────────────────────────────────────────────────


class JsonFormatter(logging.Formatter):
    """Emit log records as JSON lines for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False, default=str)


def _setup_logging() -> None:
    """Configure root logger with JSON formatter when JSON_LOGS is set or in production."""
    use_json = (
        os.getenv("JSON_LOGS", "").lower() == "true"
        or get_settings().is_production
    )
    if not use_json:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    # Configure root logger so uvicorn and all child loggers emit JSON
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Ensure third-party loggers don't propagate duplicate handlers
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True


_setup_logging()

logger = logging.getLogger("replica")
_settings = get_settings()


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup: verify security-critical configuration and start the overdue scanner."""
    settings = get_settings()

    # ── JWT secret check ─────────────────────────────────────────
    if settings.jwt_secret_is_default:
        logger.critical(
            "SECURITY: JWT_SECRET_KEY is still the default value. "
            "Generate a real secret:  python -c \"import secrets; print(secrets.token_hex(32))\"  "
            "Set it via the JWT_SECRET_KEY environment variable before deploying to production."
        )

    # ── Production hardening checks ──────────────────────────────
    if settings.is_production:
        if settings.DEBUG:
            raise SystemExit(
                "SECURITY: DEBUG=True in production environment. "
                "Set DEBUG=false in your .env file."
            )
        if settings.jwt_secret_is_default:
            raise SystemExit(
                "SECURITY: Cannot start in production with default JWT_SECRET_KEY. "
                "Set JWT_SECRET_KEY in your environment to a strong random value."
            )
        # Validate CORS origins for production
        cors_origins = settings.cors_origin_list
        if not cors_origins or cors_origins == ["http://localhost:5173", "http://127.0.0.1:5173"]:
            logger.warning(
                "SECURITY: CORS origins are still at development defaults. "
                "Set CORS_ORIGINS in your .env file for production."
            )
        logger.info("Running in PRODUCTION mode — security checks passed.")

    # ── APScheduler: overdue task scanner (every 2 s) ────────────
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from store import store as _store

    _scheduler = AsyncIOScheduler()

    async def _scan_overdue_tasks():
        """Find tasks whose deadline has passed and notify their owners."""
        try:
            overdue = _store.find_overdue_tasks()
        except Exception:
            logger.exception("Overdue scanner failed to query tasks")
            return

        for task in overdue:
            try:
                task_id = task["id"]
                owner_id = task.get("owner_id")
                title = task.get("title", "")

                # Mark task as overdue-notified
                _store.mark_task_overdue_notified(task_id)

                # Create notification record
                if owner_id is not None:
                    notif = _store.create_notification(
                        user_id=owner_id,
                        title="任务已过期",
                        content=f"「{title}」已超过截止时间，请尽快处理",
                        type_="task_overdue",
                        reference_type="task",
                        reference_id=str(task_id),
                    )

                    # Push SSE event to online user
                    if notif:
                        push_event(owner_id, {
                            "type": "task_overdue",
                            "notification": notif,
                            "task": {"id": task_id, "title": title, "status": "overdue"},
                        })
            except Exception:
                logger.exception("Overdue scanner failed for task %d", task.get("id"))

    _scheduler.add_job(_scan_overdue_tasks, "interval", seconds=2, id="overdue_scanner")

    # ── Audit retention cleanup (daily) ──────────────────────────
    async def _purge_audit_retention():
        """Purge audit logs older than AUDIT_RETENTION_DAYS."""
        try:
            from audit.logger import purge_expired_audit_logs
            from session import get_session_local

            retention_days = settings.AUDIT_RETENTION_DAYS
            with get_session_local()() as db:
                deleted = purge_expired_audit_logs(db, retention_days)
            if deleted:
                logger.info("Audit retention purge: %d records deleted (retention=%d days)", deleted, retention_days)
        except Exception:
            logger.exception("Audit retention purge failed")

    _scheduler.add_job(_purge_audit_retention, "interval", hours=24, id="audit_retention_purge")
    _scheduler.start()
    logger.info("APScheduler started (overdue scanner + audit retention purge)")

    try:
        yield
    finally:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler overdue scanner stopped")


app = FastAPI(
    title="Collaboration Portal API",
    description="统一协同门户后端接口",
    version="0.1.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 6: request-level audit (request_id + 401/403 recording).
# Must be installed AFTER CORSMiddleware so it can see the auth layer's
# response status codes.
app.add_middleware(AuditMiddleware)

app.include_router(portal_router)
app.include_router(subsystems_router)
app.include_router(tasks_router)
app.include_router(calendar_router)
app.include_router(integrations_router)
app.include_router(knowledge_router)
app.include_router(chat_router)
app.include_router(search_router)
app.include_router(admin_router)
app.include_router(enterprise_router)
app.include_router(notifications_router)
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])


# ── Health check (3-level) ────────────────────────────────────────────


@app.get("/health")
async def health_check(full: bool = False) -> JSONResponse:
    """Liveness probe (always 200).  Set ?full=true for readiness with DB check."""
    if not full:
        return JSONResponse({"status": "ok"})

    db_ok = False
    db_error: str | None = None
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_error = str(exc)
        logger.warning("Health check: database unreachable — %s", db_error)

    status_code = 200 if db_ok else 503
    return JSONResponse(
        content={
            "status": "ok" if db_ok else "degraded",
            "database": {"ok": db_ok, "error": db_error},
        },
        status_code=status_code,
    )


# ── Global exception handlers ─────────────────────────────────────────


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return 422 with a structured JSON envelope for validation failures."""
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def _global_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Catch-all handler — log the error and return a 500 JSON envelope."""
    logger.error(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected error occurred"
            if not _settings.DEBUG
            else str(exc),
        },
    )


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
