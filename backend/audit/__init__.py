"""Audit logging and middleware (Phase 6).

Provides:
- SQLAlchemy table definitions for ``audit_logs`` and ``ai_query_logs``
- Structured audit logger (extends the root-level ``audit_logger.py``)
- Starlette middleware that injects ``X-Request-ID`` and records
  authentication / authorization events (401, 403) automatically.
"""

from audit.models import ai_query_logs_table, audit_logs_table
from audit.logger import AuditLogger, audit_logger
from audit.middleware import AuditMiddleware

__all__ = [
    "audit_logs_table",
    "ai_query_logs_table",
    "AuditLogger",
    "audit_logger",
    "AuditMiddleware",
]
