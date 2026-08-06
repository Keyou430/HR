"""Tests for notice publish 3-tier permissions (notice:publish)."""

import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parent
if str(_backend_root) not in sys.path:
    sys.path.insert(0, str(_backend_root))

from conftest import login, auth_headers  # noqa: E402


class TestNoticePublishScope:
    """3-tier announcement publish permissions using conftest fixtures."""

    def test_super_admin_can_publish_notice(self, client):
        token = login(client, "test_super_admin", "test-super-admin-32chars!!!")
        payload = {
            "title": "全域公告测试",
            "source": "党政办公室",
            "category": "通知公告",
            "body": "这是一条测试公告。",
            "published_at": "2026-08-06T10:00:00",
            "visibility": "org",
        }
        r = client.post("/api/v1/admin/notices", json=payload, headers=auth_headers(token))
        assert r.status_code == 201
        assert "id" in r.json()

    def test_dept_staff_cannot_publish(self, client):
        token = login(client, "test_dept_staff", "test-dept-staff-32chars!")
        r = client.post("/api/v1/admin/notices", json={
            "title": "不应成功",
            "source": "测试",
            "category": "测试",
            "body": "不应成功。",
            "published_at": "2026-08-06T10:00:00",
            "visibility": "org",
        }, headers=auth_headers(token))
        assert r.status_code == 403

    def test_notice_list_returns_paginated(self, client):
        token = login(client, "test_super_admin", "test-super-admin-32chars!!!")
        r = client.get("/api/v1/admin/notices?page=1&page_size=10", headers=auth_headers(token))
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
