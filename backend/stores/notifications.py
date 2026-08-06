"""NotificationMixin — user notification CRUD mixed into PortalStore."""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select, text


class NotificationMixin:
    """Notification store — all operations force user_id = current user for isolation."""

    # ── helpers ─────────────────────────────────────────────────────────

    def _notification_table(self):
        """Resolve the notifications table at runtime (set during PortalStore.__init__)."""
        return self._notifications_table

    # ── read ────────────────────────────────────────────────────────────

    def list_notifications(
        self,
        user: dict[str, Any] | None,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return the current user's notifications, newest first."""
        if user is None:
            return self.list_response([])

        with self._session() as db:
            t = self._notification_table()
            rows = (
                db.execute(
                    select(t)
                    .where(t.c.user_id == user["id"])
                    .order_by(t.c.created_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
                .mappings()
                .fetchall()
            )
            items = [self._stringify_dt(dict(r)) for r in rows]
        return self.list_response(items)

    def get_unread_count(self, user: dict[str, Any] | None) -> int:
        """Return the number of unread notifications for the current user."""
        if user is None:
            return 0
        with self._session() as db:
            t = self._notification_table()
            row = db.execute(
                select(text("COUNT(*)")).select_from(t).where(
                    and_(t.c.user_id == user["id"], t.c.is_read == False)
                )
            ).scalar()
            return int(row or 0)

    # ── mutate ──────────────────────────────────────────────────────────

    def mark_notification_read(self, user: dict[str, Any] | None, notification_id: int) -> bool:
        """Mark a single notification as read. Returns True if a row was updated."""
        if user is None:
            return False
        with self._session() as db:
            t = self._notification_table()
            result = db.execute(
                t.update()
                .where(and_(t.c.id == notification_id, t.c.user_id == user["id"]))
                .values(is_read=True)
            )
            db.commit()
            return result.rowcount > 0

    def mark_all_notifications_read(self, user: dict[str, Any] | None) -> int:
        """Mark all notifications for the current user as read. Returns count updated."""
        if user is None:
            return 0
        with self._session() as db:
            t = self._notification_table()
            result = db.execute(
                t.update()
                .where(and_(t.c.user_id == user["id"], t.c.is_read == False))
                .values(is_read=True)
            )
            db.commit()
            return result.rowcount

    def create_notification(
        self,
        user_id: int,
        title: str,
        content: str = "",
        *,
        type_: str = "info",
        reference_type: str | None = None,
        reference_id: str | None = None,
        org_id: str | None = None,
        department_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Create a notification for a user. Returns the created row as a dict."""
        ts = self._now_iso()
        row = {
            "user_id": user_id,
            "title": title,
            "content": content,
            "type": type_,
            "reference_type": reference_type,
            "reference_id": reference_id,
            "is_read": False,
            "org_id": org_id,
            "department_id": department_id,
            "created_at": ts,
        }
        with self._session() as db:
            t = self._notification_table()
            result = db.execute(t.insert().values(**row))
            db.commit()
            row["id"] = result.inserted_primary_key[0]
        return row

    def delete_notification(self, user: dict[str, Any] | None, notification_id: int) -> bool:
        """Delete a single notification belonging to the current user."""
        if user is None:
            return False
        with self._session() as db:
            t = self._notification_table()
            result = db.execute(
                t.delete().where(
                    and_(t.c.id == notification_id, t.c.user_id == user["id"])
                )
            )
            db.commit()
            return result.rowcount > 0
