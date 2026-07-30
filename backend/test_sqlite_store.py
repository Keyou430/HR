import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(BACKEND_ROOT))

from config import get_settings
from store import PortalStore


def test_store_persists_frontend_writes_in_sqlite(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "replica_persistence.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()

    first = PortalStore()
    task = first.create_task({"title": "重启后仍然存在", "tag": "今天"})
    first.update_embed_urls({"feishu": "https://example.com/feishu"})

    second = PortalStore()

    assert any(item["id"] == task["id"] and item["title"] == "重启后仍然存在" for item in second.list_tasks()["items"])
    assert second.embed_urls["feishu"] == "https://example.com/feishu"
