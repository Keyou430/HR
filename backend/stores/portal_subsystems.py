"""Phase 4 T17: Website, Estate, Employment store mixins.

Each mixin provides thin CRUD + stats over the corresponding enterprise table.
All methods delegate to the BaseStore enterprise primitives for scope-aware access.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select


class WebsiteMixin:
    """CMS site management (网站群)."""

    # ── CRUD ───────────────────────────────────────────────────────

    def list_cms_sites(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._enterprise_list(self._cms_sites_table, user)

    def get_cms_site(self, site_id: int, user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._enterprise_get(self._cms_sites_table, site_id, user)

    def create_cms_site(self, payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._enterprise_create(self._cms_sites_table, payload, user)

    def update_cms_site(self, site_id: int, payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._enterprise_update(self._cms_sites_table, site_id, payload, user)

    # ── Stats ──────────────────────────────────────────────────────

    def get_cms_site_stats(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            base = select(self._cms_sites_table).where(self._scope_filter(ctx, self._cms_sites_table))
            total = db.scalar(select(func.count()).select_from(base.subquery()))
            by_status = {
                row.status: row.cnt
                for row in db.execute(
                    select(self._cms_sites_table.c.status, func.count().label("cnt"))
                    .where(self._scope_filter(ctx, self._cms_sites_table))
                    .group_by(self._cms_sites_table.c.status)
                ).all()
            }
            by_category = {
                row.category: row.cnt
                for row in db.execute(
                    select(self._cms_sites_table.c.category, func.count().label("cnt"))
                    .where(self._scope_filter(ctx, self._cms_sites_table))
                    .group_by(self._cms_sites_table.c.category)
                ).all()
            }
            return {"total": total or 0, "by_status": by_status, "by_category": by_category}


class EstateMixin:
    """Space / room management (房产管理)."""

    # ── CRUD ───────────────────────────────────────────────────────

    def list_estate_spaces(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._enterprise_list(self._estate_spaces_table, user)

    def get_estate_space(self, space_id: int, user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._enterprise_get(self._estate_spaces_table, space_id, user)

    def create_estate_space(self, payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._enterprise_create(self._estate_spaces_table, payload, user)

    def update_estate_space(self, space_id: int, payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._enterprise_update(self._estate_spaces_table, space_id, payload, user)

    # ── Stats ──────────────────────────────────────────────────────

    def get_estate_space_stats(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            base = select(self._estate_spaces_table).where(self._scope_filter(ctx, self._estate_spaces_table))
            total = db.scalar(select(func.count()).select_from(base.subquery()))
            by_category = {
                row.category: row.cnt
                for row in db.execute(
                    select(self._estate_spaces_table.c.category, func.count().label("cnt"))
                    .where(self._scope_filter(ctx, self._estate_spaces_table))
                    .group_by(self._estate_spaces_table.c.category)
                ).all()
            }
            by_status = {
                row.status: row.cnt
                for row in db.execute(
                    select(self._estate_spaces_table.c.status, func.count().label("cnt"))
                    .where(self._scope_filter(ctx, self._estate_spaces_table))
                    .group_by(self._estate_spaces_table.c.status)
                ).all()
            }
            return {"total": total or 0, "by_category": by_category, "by_status": by_status}


class EmploymentMixin:
    """Job posting management (就业系统)."""

    # ── CRUD ───────────────────────────────────────────────────────

    def list_job_postings(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._enterprise_list(self._job_postings_table, user)

    def get_job_posting(self, posting_id: int, user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._enterprise_get(self._job_postings_table, posting_id, user)

    def create_job_posting(self, payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._enterprise_create(self._job_postings_table, payload, user)

    def update_job_posting(self, posting_id: int, payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._enterprise_update(self._job_postings_table, posting_id, payload, user)

    # ── Stats ──────────────────────────────────────────────────────

    def get_job_posting_stats(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            base = select(self._job_postings_table).where(self._scope_filter(ctx, self._job_postings_table))
            total = db.scalar(select(func.count()).select_from(base.subquery()))
            by_category = {
                row.position_category: row.cnt
                for row in db.execute(
                    select(self._job_postings_table.c.position_category, func.count().label("cnt"))
                    .where(self._scope_filter(ctx, self._job_postings_table))
                    .group_by(self._job_postings_table.c.position_category)
                ).all()
            }
            by_status = {
                row.status: row.cnt
                for row in db.execute(
                    select(self._job_postings_table.c.status, func.count().label("cnt"))
                    .where(self._scope_filter(ctx, self._job_postings_table))
                    .group_by(self._job_postings_table.c.status)
                ).all()
            }
            return {"total": total or 0, "by_category": by_category, "by_status": by_status}
