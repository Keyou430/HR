"""RBAC: core permission-checking logic.

``user_has_permission`` is the single source of truth for whether a user
holds a specific permission code.  It operates on the user dict produced by
``get_current_user``, which already contains pre-loaded ``roles`` and
``permissions`` lists from the database.

Key principles (from rbac-design-v2.md §2.1):
- Default-deny: no explicit permission → False
- Explicit authorization only: no role-priority auto-inheritance
- Super-admin bypass is explicit (checked against role list, not
  permission list) and triggers an audit event.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("replica.rbac")

SUPER_ADMIN_ROLE = "super_admin"


def user_has_permission(user: dict[str, Any], permission_code: str) -> bool:
    """Return True if *user* holds *permission_code*.

    The check works as follows:

    1. ``super_admin`` role → always True (audited).
    2. Permission code present in ``user["permissions"]`` → True.
    3. Everything else → False (default-deny).

    *user* must be the dict returned by ``get_current_user`` /
    ``_load_user_with_roles``, which includes:

    - ``"roles": list[str]`` — role codes
    - ``"permissions": list[str]`` — permission codes (pre-computed from DB)
    """
    roles: list[str] = user.get("roles", [])
    permissions: list[str] = user.get("permissions", [])

    # Super-admin bypass — logged at INFO level for audit visibility.
    # Phase 6 will add structured audit_log() integration.
    if SUPER_ADMIN_ROLE in roles:
        logger.info(
            "AUDIT: super_admin bypass — user_id=%s username=%s permission=%s",
            user.get("id"), user.get("username", "?"), permission_code,
        )
        return True

    if permission_code in permissions:
        return True

    return False
