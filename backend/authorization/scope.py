"""Data-scope engine for object-level access control (Phase 4).

Computes an ``AccessContext`` once per request and provides helpers to
answer two questions:

1. **Which rows can this user see in a list query?** → use the filter
   builders in ``sql_filters.py``, which consume ``AccessContext``.

2. **Can this user touch a specific resource?** → use ``can_access_resource()``.

Visibility levels (rbac-design-v2.md §5.4):
    ``private`` — only the owner
    ``dept``    — owner's department + sub-departments
    ``org``     — owner's entire org
    ``public``  — everyone, including external users

Sensitivity levels:
    ``normal``     — anyone who passes the visibility check
    ``internal``   — org members only (not external)
    ``sensitive``  — requires ``kb:chat_sensitive`` permission
    ``restricted`` — requires explicit grant (future)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from authorization.rbac import SUPER_ADMIN_ROLE

# ── Visibility constants ────────────────────────────────────────────

VISIBILITY_PRIVATE = "private"
VISIBILITY_DEPT = "dept"
VISIBILITY_ORG = "org"
VISIBILITY_PUBLIC = "public"

# ── Sensitivity constants ───────────────────────────────────────────

SENSITIVITY_NORMAL = "normal"
SENSITIVITY_INTERNAL = "internal"
SENSITIVITY_SENSITIVE = "sensitive"
SENSITIVITY_RESTRICTED = "restricted"

# ── Sentinel for "all orgs / all depts" (super_admin) ────────────────

_ALL_SENTINEL = "*"


# ═════════════════════════════════════════════════════════════════════
# AccessContext
# ═════════════════════════════════════════════════════════════════════


@dataclass
class AccessContext:
    """Resolved data-scope context for a single authenticated request.

    Computed once in the API layer via :func:`get_access_context` and
    threaded through store methods so every query is filtered consistently.
    """

    user_id: int
    username: str
    roles: list[str]
    permissions: list[str]

    # Identity anchors (from user_org_memberships / user_department_memberships)
    default_org_id: str | None
    default_dept_id: str | None

    # Pre-computed flags
    is_super_admin: bool = False

    # Set of org IDs the user can access.
    # ``{"*"}`` means all orgs (super_admin).
    org_ids: set[str] = field(default_factory=set)

    # Set of department IDs the user can access (own dept + sub-depts).
    # ``{"*"}`` means all depts (super_admin).
    visible_dept_ids: set[str] = field(default_factory=set)

    # Cached permission set for fast membership tests
    _perm_set: set[str] = field(default_factory=set)

    # ── Convenience helpers ──────────────────────────────────────

    def has_perm(self, code: str) -> bool:
        """Check a single permission code (super_admin always True)."""
        return self.is_super_admin or code in self._perm_set

    def has_sensitive_access(self) -> bool:
        """Can this user view sensitive-level resources?"""
        return self.has_perm("kb:chat_sensitive")

    @property
    def is_external_only(self) -> bool:
        """True when the user ONLY has the 'external' role."""
        return (
            len(self.roles) == 1
            and "external" in self.roles
        )

    @property
    def allowed_sensitivities(self) -> list[str]:
        """Sensitivity levels this user is permitted to see."""
        if self.is_super_admin:
            return [
                SENSITIVITY_NORMAL,
                SENSITIVITY_INTERNAL,
                SENSITIVITY_SENSITIVE,
                SENSITIVITY_RESTRICTED,
            ]
        allowed = [SENSITIVITY_NORMAL]
        if not self.is_external_only:
            allowed.append(SENSITIVITY_INTERNAL)
        if self.has_sensitive_access():
            allowed.append(SENSITIVITY_SENSITIVE)
        # restricted always requires explicit grant (future Phase)
        return allowed


# ═════════════════════════════════════════════════════════════════════
# Public API
# ═════════════════════════════════════════════════════════════════════


def get_access_context(
    user: dict[str, Any],
    db: Session,
    org_id: str | None = None,
) -> AccessContext:
    """Build an ``AccessContext`` from the user dict returned by ``get_current_user``.

    Args:
        user: Authenticated user dict (``get_current_user`` output).
        db: Database session for department-tree queries.
        org_id: Optional override for the organisation scope.  Defaults to
            the user's primary org.
    """
    roles: list[str] = user.get("roles", [])
    permissions: list[str] = user.get("permissions", [])
    is_super = SUPER_ADMIN_ROLE in roles
    user_default_org = user.get("default_org_id")
    effective_dept = user.get("default_dept_id")

    # ── Resolve effective org ────────────────────────────────────
    # Phase 4 F5: when an explicit org_id is provided, validate that the
    # user actually belongs to that org.  Fall back to the default org
    # otherwise — never grant unauthorised cross-org scope.
    if org_id is not None and org_id != user_default_org:
        # Explicit org requested — verify membership
        membership = db.execute(
            text(
                "SELECT 1 FROM user_org_memberships "
                "WHERE user_id = :uid AND org_id = :oid LIMIT 1"
            ),
            {"uid": user["id"], "oid": org_id},
        ).fetchone()
        effective_org = org_id if membership is not None else user_default_org
    else:
        effective_org = org_id or user_default_org

    ctx = AccessContext(
        user_id=user["id"],
        username=user.get("username", ""),
        roles=roles,
        permissions=permissions,
        default_org_id=effective_org,
        default_dept_id=effective_dept,
        is_super_admin=is_super,
        _perm_set=set(permissions),
    )

    if is_super:
        ctx.org_ids = {_ALL_SENTINEL}
        ctx.visible_dept_ids = {_ALL_SENTINEL}
    elif ctx.is_external_only:
        # External users only see public visibility items (plus their own).
        # They must NOT receive org/dept scope even if they hold
        # memberships — otherwise they would see org/dept-scoped resources.
        # org_ids and visible_dept_ids are left empty.
        pass
    elif effective_org:
        ctx.org_ids = {effective_org}
        if effective_dept:
            ctx.visible_dept_ids = _resolve_visible_dept_ids(
                db, effective_org, effective_dept
            )

    return ctx


def get_visible_department_ids(
    db: Session,
    org_id: str,
    dept_id: str,
) -> set[str]:
    """Public alias — return the set of dept IDs visible from *dept_id*.

    Includes *dept_id* itself and all descendant departments matched via
    the ``path`` column (e.g. ``'HQ'`` → ``{'HQ', 'HQ/Eng', 'HQ/Eng/Backend'}``).
    """
    return _resolve_visible_dept_ids(db, org_id, dept_id)


def can_access_resource(
    ctx: AccessContext,
    resource_org_id: str | None,
    resource_dept_id: str | None,
    resource_owner_id: int | None,
    resource_visibility: str,
    resource_sensitivity: str = SENSITIVITY_NORMAL,
) -> bool:
    """Check whether *ctx* is authorised to access a **single** resource.

    Used primarily for update / delete authorisation where the caller
    already knows the resource's attributes (e.g. from a prior SELECT).

    Returns ``True`` if access is permitted.
    """
    # super_admin sees everything
    if ctx.is_super_admin:
        return True

    # Sensitivity gate — applied first so sensitive resources are
    # invisible even to owners who lack the required permission.
    if resource_sensitivity not in ctx.allowed_sensitivities:
        return False

    # Owner bypass — owner always sees their own resources (provided
    # sensitivity check passed above).
    if resource_owner_id is not None and resource_owner_id == ctx.user_id:
        return True

    # Visibility gate
    if resource_visibility == VISIBILITY_PRIVATE:
        return False  # only owner — already handled above
    elif resource_visibility == VISIBILITY_DEPT:
        if resource_dept_id is None:
            return False
        if _ALL_SENTINEL in ctx.visible_dept_ids:
            return True
        return resource_dept_id in ctx.visible_dept_ids
    elif resource_visibility == VISIBILITY_ORG:
        if resource_org_id is None:
            return False
        if _ALL_SENTINEL in ctx.org_ids:
            return True
        return resource_org_id in ctx.org_ids
    # VISIBILITY_PUBLIC — always passes

    return True


# ═════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════


def _resolve_visible_dept_ids(
    db: Session,
    org_id: str,
    dept_id: str,
) -> set[str]:
    """Return {dept_id} ∪ all descendant department IDs.

    Uses the ``path`` column: a department with path ``'HQ/Eng'`` is a
    descendant of the department whose path is ``'HQ'``.
    """
    row = db.execute(
        text(
            "SELECT path FROM departments "
            "WHERE org_id = :oid AND id = :did"
        ),
        {"oid": org_id, "did": dept_id},
    ).fetchone()

    if row is None:
        return {dept_id}

    dept_path = row[0] or dept_id

    rows = db.execute(
        text(
            "SELECT id FROM departments WHERE org_id = :oid "
            "AND (path = :path OR path LIKE :pattern)"
        ),
        {
            "oid": org_id,
            "path": dept_path,
            "pattern": f"{dept_path}/%",
        },
    ).fetchall()

    if rows:
        return {r[0] for r in rows}
    return {dept_id}
