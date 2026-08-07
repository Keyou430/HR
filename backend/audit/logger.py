"""Structured audit logger (Phase 6).

Wraps the root-level ``audit_logger.py`` function with a class-based
interface and adds ``ai_query_logs`` writing and ``request_id`` injection.

Security invariants (rbac-design-v2.md §6.3, §12):
- Never record Authorization headers, passwords, or refresh tokens.
- AI queries: only SHA-256 hash + truncated snippet, never full response.
- The audit logger itself must never throw — a failure to write an audit
  record must not block the business operation (fail-open for non-security
  events, best-effort flush for security blocks).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("replica.audit")

# Dedicated logger for security-block events that could not be persisted
# to the database.  Operators should monitor this logger at WARNING level
# or above so that failed security-block audit writes trigger alerts.
_security_fallback = logging.getLogger("replica.audit.security_block_fallback")


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_request_id() -> str:
    return uuid.uuid4().hex[:16]


class AuditLogger:
    """Structured audit writer with safe defaults.

    Usage::

        from audit.logger import audit_logger

        audit_logger.record(
            db, action="admin.user.disable", user_id=admin_id,
            resource_type="user", resource_id=str(target_id),
            detail={"before": {...}, "after": {...}},
        )
    """

    # ── Public API ────────────────────────────────────────────────

    def record(
        self,
        db: Session,
        *,
        action: str,
        user_id: int | None = None,
        org_id: str | None = None,
        department_id: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        decision: str = "allow",
        reason: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        detail: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        """Write one row to ``audit_logs``.

        Does **not** commit — the caller owns the transaction boundary.
        """
        try:
            db.execute(
                text(
                    "INSERT INTO audit_logs "
                    "(request_id, user_id, org_id, department_id, action, "
                    "resource_type, resource_id, decision, reason, "
                    "ip_address, user_agent, detail_json, created_at) "
                    "VALUES (:rid, :uid, :oid, :did, :act, :rtype, :rid2, :dec, :reason, "
                    ":ip, :ua, :detail, :ts)"
                ),
                {
                    "rid": request_id or _new_request_id(),
                    "uid": user_id,
                    "oid": org_id,
                    "did": department_id,
                    "act": action[:96],
                    "rtype": resource_type,
                    "rid2": str(resource_id)[:128] if resource_id else None,
                    "dec": decision,
                    "reason": reason[:256] if reason else None,
                    "ip": ip_address[:45] if ip_address else None,
                    "ua": user_agent[:512] if user_agent else None,
                    "detail": json.dumps(detail, ensure_ascii=False) if detail else None,
                    "ts": _ts(),
                },
            )
        except Exception:
            logger.warning(
                "Failed to write audit log — action=%s user_id=%s",
                action, user_id, exc_info=True,
            )

    def record_block(
        self,
        db: Session,
        *,
        action: str,
        reason: str,
        user_id: int | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> None:
        """Convenience — record a denied/blocked event.

        This is called from middleware for 401/403 responses and from the
        AI firewall for blocked queries.  Must be best-effort reliable:
        if the DB write or commit fails we emit a **structured JSON**
        line to the ``replica.audit.security_block_fallback`` logger at
        CRITICAL level so operators can alert on these events even when
        the database is unavailable.
        """
        fallback_record = json.dumps(
            {
                "event": "security_block",
                "action": action,
                "reason": reason,
                "user_id": user_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "request_id": request_id,
                "timestamp": _ts(),
            },
            ensure_ascii=False,
        )
        try:
            self.record(
                db,
                action=action,
                user_id=user_id,
                decision="deny",
                reason=reason,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
            try:
                db.commit()
            except Exception:
                logger.critical(
                    "CRITICAL: failed to commit security block audit — action=%s reason=%s",
                    action, reason, exc_info=True,
                )
                _security_fallback.critical(fallback_record)
                try:
                    db.rollback()
                except Exception:
                    pass
        except Exception:
            logger.critical(
                "CRITICAL: failed to write security block audit — action=%s reason=%s",
                action, reason, exc_info=True,
            )
            _security_fallback.critical(fallback_record)

    def record_ai_query(
        self,
        db: Session,
        *,
        request_id: str,
        user_id: int,
        org_id: str | None = None,
        department_id: str | None = None,
        query_hash: str,
        query_snippet: str,
        risk_label: str,
        policy_version: str,
        decision: str,
        blocked_reason: str = "",
        accessible_resource_count: int = 0,
        response_time_ms: int = 0,
    ) -> None:
        """Write one row to ``ai_query_logs``.

        Only stores hash + snippet — never the full query or response.
        """
        try:
            db.execute(
                text(
                    "INSERT INTO ai_query_logs "
                    "(request_id, user_id, org_id, department_id, query_hash, "
                    "query_snippet, risk_label, policy_version, decision, "
                    "blocked_reason, accessible_resource_count, response_time_ms, "
                    "created_at) "
                    "VALUES (:rid, :uid, :oid, :did, :qh, :qs, :rl, :pv, :dec, "
                    ":br, :arc, :rt, :ts)"
                ),
                {
                    "rid": request_id,
                    "uid": user_id,
                    "oid": org_id,
                    "did": department_id,
                    "qh": query_hash,
                    "qs": query_snippet[:256],
                    "rl": risk_label,
                    "pv": policy_version,
                    "dec": decision,
                    "br": blocked_reason[:256] if blocked_reason else "",
                    "arc": accessible_resource_count,
                    "rt": response_time_ms,
                    "ts": _ts(),
                },
            )
        except Exception:
            logger.warning(
                "Failed to write AI query log — user_id=%s decision=%s",
                user_id, decision, exc_info=True,
            )


# Module-level singleton (replaces the root-level audit_log function
# for new code; existing callers are unaffected).
audit_logger = AuditLogger()


def purge_expired_audit_logs(db: Session, retention_days: int) -> int:
    """Delete audit log records older than *retention_days*.

    Returns the number of deleted rows.
    """
    from datetime import timedelta

    from audit.models import ai_query_logs_table, audit_logs_table

    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    deleted = 0

    for table in (audit_logs_table, ai_query_logs_table):
        result = db.execute(table.delete().where(table.c.created_at < cutoff))
        deleted += result.rowcount

    if deleted:
        logger.info("Purged %d audit records older than %d days (cutoff=%s)", deleted, retention_days, cutoff)
    return deleted
