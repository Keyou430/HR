"""SQLAlchemy WHERE-clause builders for object-level data scope (Phase 4).

Each function accepts an :class:`AccessContext` and a SQLAlchemy
:class:`Table` and returns a clause suitable for ``.where()``::

    stmt = select(tasks_table).where(
        task_visibility_filter(ctx, tasks_table),
    )

All filters are expressed in SQL so the database enforces data scope —
the application never loads rows the user isn't authorised to see.
"""

from __future__ import annotations

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ClauseElement

from authorization.scope import (
    AccessContext,
    SENSITIVITY_NORMAL,
    SENSITIVITY_RESTRICTED,
    VISIBILITY_DEPT,
    VISIBILITY_ORG,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    _ALL_SENTINEL,
)


# ═════════════════════════════════════════════════════════════════════
# Public filter builders
# ═════════════════════════════════════════════════════════════════════


def task_visibility_filter(ctx: AccessContext, table) -> ClauseElement:
    """WHERE clause for ``portal_tasks`` queries."""
    return _build_filter(
        ctx,
        table,
        org_col=table.c.org_id,
        dept_col=table.c.department_id,
        owner_col=table.c.owner_id,
        vis_col=table.c.visibility,
        sens_col=table.c.sensitivity,
    )


def calendar_visibility_filter(ctx: AccessContext, table) -> ClauseElement:
    """WHERE clause for ``portal_calendar_events`` queries."""
    return _build_filter(
        ctx,
        table,
        org_col=table.c.org_id,
        dept_col=table.c.department_id,
        owner_col=table.c.owner_id,
        vis_col=table.c.visibility,
        sens_col=table.c.sensitivity,
    )


def knowledge_visibility_filter(ctx: AccessContext, table) -> ClauseElement:
    """WHERE clause for ``knowledge_dataset_mappings`` queries."""
    return _build_filter(
        ctx,
        table,
        org_col=table.c.org_id,
        dept_col=table.c.department_id,
        owner_col=table.c.owner_id,
        vis_col=table.c.visibility,
        sens_col=table.c.sensitivity,
    )


def resource_owner_filter(
    ctx: AccessContext,
    table,
    resource_id: int | str,
    id_column: str = "id",
) -> ClauseElement:
    """Build a WHERE clause that scopes a single-resource operation
    (update / delete) to rows the user is authorised to touch.

    Combines the resource's PK match with the full visibility filter.
    Returns a clause that yields **zero rows** when the user lacks access
    (preventing IDOR without leaking existence).
    """
    pk_col = table.c[id_column]
    scope = _build_filter(
        ctx,
        table,
        org_col=table.c.org_id,
        dept_col=table.c.department_id,
        owner_col=table.c.owner_id,
        vis_col=table.c.visibility,
        sens_col=table.c.sensitivity,
    )
    return and_(pk_col == resource_id, scope)


# ═════════════════════════════════════════════════════════════════════
# Internal
# ═════════════════════════════════════════════════════════════════════


def _build_filter(
    ctx: AccessContext,
    table,
    *,
    org_col,
    dept_col,
    owner_col,
    vis_col,
    sens_col,
) -> ClauseElement:
    """Shared visibility + sensitivity filter builder.

    Strategy
    --------

    1. **Visibility** — an OR of:
       - *owner*: ``owner_id = ctx.user_id``
       - *public*: ``visibility = 'public'``
       - *org*: ``visibility = 'org' AND org_id IN (ctx.org_ids)``
       - *dept*: ``visibility = 'dept' AND department_id IN (ctx.visible_dept_ids)``

    2. **Sensitivity** — an AND with:
       ``sensitivity IN (ctx.allowed_sensitivities)``
       (super_admin sees everything; external only sees ``'normal'``;
       internal users see ``'normal'`` + ``'internal'``;
       ``kb:chat_sensitive`` holders also see ``'sensitive'``.)

    The two gates are AND-ed together: a row must pass **both** to be visible.
    """
    # ── Super-admin shortcut ──────────────────────────────────────
    if ctx.is_super_admin:
        return True  # no filter — SQLAlchemy treats ``True`` as "no WHERE restriction"

    # ── Visibility gate ──────────────────────────────────────────

    vis_parts = [
        # 1. Owner always sees own resources
        owner_col == ctx.user_id,
        # 2. Public resources are visible to everyone
        vis_col == VISIBILITY_PUBLIC,
    ]

    # 3. Org-scoped
    if _ALL_SENTINEL in ctx.org_ids:
        vis_parts.append(vis_col == VISIBILITY_ORG)
    elif ctx.org_ids:
        vis_parts.append(
            and_(vis_col == VISIBILITY_ORG, org_col.in_(ctx.org_ids)),
        )

    # 4. Dept-scoped — must also cross-check org_id to prevent
    #    cross-org bypass via same-named departments (Phase 4 review F1).
    if _ALL_SENTINEL in ctx.visible_dept_ids:
        vis_parts.append(vis_col == VISIBILITY_DEPT)
    elif ctx.visible_dept_ids and ctx.org_ids:
        vis_parts.append(
            and_(
                vis_col == VISIBILITY_DEPT,
                dept_col.in_(ctx.visible_dept_ids),
                org_col.in_(ctx.org_ids),
            ),
        )
    elif ctx.visible_dept_ids:
        # No org scope (e.g. external-only) — dept check alone is still valid
        # because visible_dept_ids is empty for external users.
        vis_parts.append(
            and_(vis_col == VISIBILITY_DEPT, dept_col.in_(ctx.visible_dept_ids)),
        )

    visibility_clause = or_(*vis_parts)

    # ── Sensitivity gate ─────────────────────────────────────────

    allowed = ctx.allowed_sensitivities
    if len(allowed) == 1:
        sensitivity_clause = sens_col == allowed[0]
    else:
        sensitivity_clause = sens_col.in_(allowed)

    # ── Combine ───────────────────────────────────────────────────

    return and_(visibility_clause, sensitivity_clause)
