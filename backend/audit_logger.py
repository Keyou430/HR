"""Audit logging utility — writes to the ``audit_logs`` table.

Every auth-sensitive operation should call ``audit_log`` so that
security-relevant events are traceable.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit_log(
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
) -> None:
    """Write one row to ``audit_logs``.

    Parameters are designed to be called inline from auth endpoints.
    ``action`` should be a short kebab-case identifier (e.g.
    ``"auth.login.success"``).  ``decision`` is ``"allow"`` (default),
    ``"deny"``, or ``"error"``.
    """
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
            "rid": uuid.uuid4().hex[:16],
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
    # Intentionally NOT committing here — the caller's transaction boundary
    # is responsible for commit/rollback.
