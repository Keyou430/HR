"""SearchMixin — unified cross-entity search with repair, asset, and OA sources."""

from __future__ import annotations

from typing import Any


class SearchMixin:
    """Search mixed into PortalStore — delegates to entity-specific list methods.

    Each result includes:
      - type:   category key used for grouping and icon selection on the frontend
      - title:  primary display text (bold)
      - subtitle: secondary info (location / flow_type / status, etc.)
      - href:   deep-link for navigation (hash route)
      - status: optional status string for the status-badge component
    """

    # ── per-source result builders ──────────────────────────────────────

    def _search_subsystems(
        self, user: dict[str, Any] | None
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "subsystem",
                "title": item["name"],
                "subtitle": item.get("description", ""),
                "href": f"#/subsystem/{item['code']}",
                "status": None,
            }
            for item in self.list_subsystems(user=user)["items"]
        ]

    def _search_portal_assets(
        self, collection: str, type_key: str, user: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for item in self.list_portal_assets(collection, user=user)["items"]:
            # Primary key varies: 'id' for notices/docs/news, 'code' for resources/services
            pk = item.get("id") or item.get("code", "")
            results.append({
                "type": type_key,
                "title": item.get("title") or item.get("name", ""),
                "subtitle": item.get("source") or item.get("location")
                           or item.get("description", ""),
                "href": f"#/portal/{collection}/{pk}",
                "status": item.get("status"),
            })
        return results

    def _search_repair(
        self, user: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "repair",
                "title": item["title"],
                "subtitle": f"{item.get('location', '')} · {item.get('status', '')}",
                "href": f"#/subsystem/repair/tickets/{item['id']}",
                "status": item.get("status"),
            }
            for item in self.list_repair_tickets(user=user)["items"]
        ]

    def _search_assets(
        self, user: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "asset",
                "title": f"{item['name']} ({item.get('asset_code', '')})",
                "subtitle": f"{item.get('category', '')} · {item.get('location', '')}",
                "href": f"#/subsystem/asset/items/{item['id']}",
                "status": item.get("status"),
            }
            for item in self.list_asset_items(user=user)["items"]
        ]

    def _search_oa(
        self, user: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        return [
            {
                "type": "oa",
                "title": item["title"],
                "subtitle": f"{item.get('flow_type', '')} · {item.get('status', '')}",
                "href": f"#/subsystem/oa/flows/{item['id']}",
                "status": item.get("status"),
            }
            for item in self.list_oa_flows(user=user)["items"]
        ]

    # ── main entry point ────────────────────────────────────────────────

    def search(
        self,
        query: str,
        user: dict[str, Any] | None = None,
        *,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return scope-filtered search results across all data sources.

        *limit* is clamped to [1, 50]; default 20.
        """
        limit = max(1, min(limit, 50))
        needle = query.strip().lower()

        # Gather all sources — each is already scope-filtered by its
        # list method, so cross-org data never enters the candidate pool.
        sources: list[dict[str, Any]] = []
        sources.extend(self._search_subsystems(user))
        sources.extend(
            self._search_portal_assets("documents", "document", user))
        sources.extend(
            self._search_portal_assets("notices", "notice", user))
        sources.extend(
            self._search_portal_assets("resources", "resource", user))
        sources.extend(
            self._search_portal_assets("services", "service", user))
        sources.extend(
            self._search_portal_assets("news", "news", user))
        sources.extend(self._search_repair(user))
        sources.extend(self._search_assets(user))
        sources.extend(self._search_oa(user))

        # Client-side text match
        if needle:
            items = [
                item
                for item in sources
                if needle in f"{item.get('title', '')}{item.get('subtitle', '')}{item.get('type', '')}".lower()
            ]
        else:
            items = sources

        return self.list_response(items[:limit])
