"""Starlette middleware for request-level audit (Phase 6).

Responsibilities
----------------
1. Inject ``X-Request-ID`` into every response header.
2. Attach ``request.state.request_id`` so downstream code can correlate logs.
3. Record ``auth.*.denied`` audit events for 401 and 403 responses.
4. Never block or delay the actual response — audit writes are fire-and-forget
   from the middleware's perspective (security-block audit records are
   committed synchronously by ``AuditLogger.record_block`` when called from
   auth / admin endpoints; the middleware only supplements those).

Non-goals
---------
- The middleware does NOT log 2xx responses (that would flood the audit table).
- The middleware does NOT parse request bodies — it only inspects status codes.
- The middleware never accesses ``Authorization`` headers or cookies.
"""

from __future__ import annotations

import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("replica.audit.middleware")


class AuditMiddleware(BaseHTTPMiddleware):
    """Inject ``X-Request-ID`` and record 401 / 403 audit events.

    Install in ``main.py``::

        app.add_middleware(AuditMiddleware)

    The middleware must be installed AFTER ``CORSMiddleware`` so it can
    inspect the response status code that the auth layer produced.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # ── Request ID ────────────────────────────────────────────
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id

        # ── Process request ───────────────────────────────────────
        response = await call_next(request)

        # ── Echo request ID ───────────────────────────────────────
        response.headers.setdefault("X-Request-ID", request_id)

        # ── Record 401 / 403 audit events ─────────────────────────
        # Skip if the business layer already wrote an audit record for
        # this event (signalled via request.state._audit_recorded).
        if response.status_code in (401, 403):
            if not getattr(request.state, "_audit_recorded", False):
                _record_auth_denied(request, response, request_id)

        return response


def _record_auth_denied(
    request: Request,
    response: Response,
    request_id: str,
) -> None:
    """Best-effort audit record for auth failures.

    This is a supplement — the primary audit records are written by
    ``audit_logger.record_block`` inside the auth / permission-check
    code paths.  The middleware covers edge cases where a 401/403 is
    raised without an explicit audit call (e.g. FastAPI's built-in
    dependency injection failures).
    """
    try:
        from config import get_settings

        settings = get_settings()
        if not settings.AUDIT_ENABLED:
            return
        if not settings.AUDIT_RECORD_AUTH_DENIED:
            return

        # Determine user identity from request state (set by auth deps)
        user_id: int | None = None
        user = getattr(request.state, "current_user", None)
        if user and isinstance(user, dict):
            user_id = user.get("id")

        ip = request.client.host if request.client else None
        ua = request.headers.get("user-agent")

        # Build action from path to avoid coupling to specific route names
        path = request.url.path
        method = request.method
        status_code = response.status_code

        action = (
            f"auth.{status_code}.{method}.{_sanitize_path(path)}"
        )[:96]

        from audit.logger import audit_logger
        from session import get_session_local

        # Use a separate short-lived session so we don't interfere with
        # the request's own DB session lifecycle.
        db = get_session_local()()
        try:
            audit_logger.record_block(
                db,
                action=action,
                reason=f"HTTP {status_code}",
                user_id=user_id,
                ip_address=ip,
                user_agent=ua,
                request_id=request_id,
            )
        finally:
            db.close()
    except Exception:
        # Audit middleware must never break the response, but a failure
        # to record a denied event is itself a security concern — use
        # WARNING so it is visible in production logs.
        logger.warning("Audit middleware: unable to record auth-denied event", exc_info=True)


def _sanitize_path(path: str) -> str:
    """Replace path segments that look like IDs with ``:id`` to keep
    audit actions compact and avoid leaking resource IDs in action names.
    """
    parts = path.strip("/").split("/")
    sanitized: list[str] = []
    for part in parts:
        # UUIDs, numeric IDs, long hex strings
        if (
            part.isdigit()
            or (len(part) >= 16 and all(c in "0123456789abcdefABCDEF-" for c in part))
        ):
            sanitized.append(":id")
        else:
            sanitized.append(part)
    return "/".join(sanitized)
