"""Tests for admin news CRUD endpoints (/api/v1/admin/news)."""

import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from conftest import login, auth_headers  # noqa: E402


class TestAdminNews:
    """Admin news CRUD tests."""

    def test_list_news_admin(self, client):
        token = login(client, "test_super_admin", "test-super-admin-32chars!!!")
        r = client.get("/api/v1/admin/news?page=1&page_size=20", headers=auth_headers(token))
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data

    def test_news_admin_denied_for_staff(self, client):
        token = login(client, "test_dept_staff", "test-dept-staff-32chars!")
        r = client.get("/api/v1/admin/news", headers=auth_headers(token))
        assert r.status_code == 403

    def test_create_news(self, client):
        token = login(client, "test_super_admin", "test-super-admin-32chars!!!")
        payload = {
            "title": "测试资讯标题",
            "source": "企业资讯",
            "category": "测试分类",
            "body": "这是一条测试资讯正文。",
            "pinned": True,
            "published_at": "2026-08-06T10:00:00",
        }
        r = client.post("/api/v1/admin/news", json=payload, headers=auth_headers(token))
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == payload["title"]
        assert data["pinned"] is True
        assert "id" in data

    def test_update_news(self, client):
        token = login(client, "test_super_admin", "test-super-admin-32chars!!!")
        payload = {
            "title": "待更新的资讯",
            "source": "测试源",
            "category": "测试",
            "body": "原始正文。",
            "published_at": "2026-08-06T10:00:00",
        }
        r = client.post("/api/v1/admin/news", json=payload, headers=auth_headers(token))
        assert r.status_code == 201
        news_id = r.json()["id"]

        r2 = client.put(f"/api/v1/admin/news/{news_id}", json={"title": "已更新的资讯标题", "pinned": True}, headers=auth_headers(token))
        assert r2.status_code == 200
        assert r2.json()["title"] == "已更新的资讯标题"
        assert r2.json()["pinned"] is True

    def test_update_nonexistent_news(self, client):
        token = login(client, "test_super_admin", "test-super-admin-32chars!!!")
        r = client.put("/api/v1/admin/news/99999", json={"title": "x"}, headers=auth_headers(token))
        assert r.status_code == 404

    def test_delete_news(self, client):
        token = login(client, "test_super_admin", "test-super-admin-32chars!!!")
        payload = {
            "title": "待删除的资讯",
            "source": "测试源",
            "category": "测试",
            "body": "将被删除。",
            "published_at": "2026-08-06T10:00:00",
        }
        r = client.post("/api/v1/admin/news", json=payload, headers=auth_headers(token))
        assert r.status_code == 201
        news_id = r.json()["id"]

        r2 = client.delete(f"/api/v1/admin/news/{news_id}", headers=auth_headers(token))
        assert r2.status_code == 200
        assert r2.json() == {"ok": True}

    def test_news_pagination(self, client):
        token = login(client, "test_super_admin", "test-super-admin-32chars!!!")
        r = client.get("/api/v1/admin/news?page=1&page_size=1", headers=auth_headers(token))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data["items"], list)
        assert isinstance(data["total"], int)
