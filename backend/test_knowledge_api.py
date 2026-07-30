import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(BACKEND_ROOT))

from config import get_settings
from main import app


def test_knowledge_spaces_are_empty_without_real_fastgpt_dataset(monkeypatch) -> None:
    monkeypatch.delenv("FASTGPT_DEFAULT_DATASET_ID", raising=False)
    monkeypatch.delenv("FASTGPT_DEFAULT_APP_ID", raising=False)
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.get("/api/v1/knowledge/spaces")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_knowledge_spaces_use_configured_fastgpt_dataset(monkeypatch) -> None:
    monkeypatch.setenv("FASTGPT_DEFAULT_DATASET_ID", "dataset_live")
    monkeypatch.setenv("FASTGPT_DEFAULT_APP_ID", "app_live")
    monkeypatch.setenv("FASTGPT_DEFAULT_DISPLAY_NAME", "产品资料库")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.get("/api/v1/knowledge/spaces")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == "dataset_live"
    assert payload["items"][0]["fastgpt_dataset_id"] == "dataset_live"
    assert payload["items"][0]["fastgpt_app_id"] == "app_live"
    assert payload["items"][0]["title"] == "产品资料库"


def test_knowledge_import_proxies_file_to_fastgpt_dataset(monkeypatch) -> None:
    monkeypatch.setenv("FASTGPT_MODE", "real")
    monkeypatch.setenv("FASTGPT_BASE_URL", "http://fastgpt.local/api")
    monkeypatch.setenv("FASTGPT_API_KEY", "sk-test")
    get_settings.cache_clear()
    mocked_import = AsyncMock(return_value={
        "dataset_id": "dataset_live",
        "file_name": "handbook.txt",
        "status": "queued",
        "fastgpt_response": {"data": {"collectionId": "collection_live"}},
    })

    with patch("knowledge.import_file_to_fastgpt", mocked_import):
        client = TestClient(app)
        response = client.post(
            "/api/v1/knowledge/import",
            data={"dataset_id": "dataset_live"},
            files={"file": ("handbook.txt", b"hello knowledge", "text/plain")},
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["dataset_id"] == "dataset_live"
    assert payload["file_name"] == "handbook.txt"
    assert payload["status"] == "queued"
    mocked_import.assert_awaited_once()
    call = mocked_import.await_args
    assert call.kwargs["dataset_id"] == "dataset_live"
    assert call.kwargs["file_name"] == "handbook.txt"
    assert call.kwargs["content"] == b"hello knowledge"


def test_knowledge_sync_saves_fastgpt_dataset_mappings(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'knowledge_sync.db').as_posix()}")
    monkeypatch.setenv("FASTGPT_MODE", "real")
    monkeypatch.setenv("FASTGPT_BASE_URL", "http://fastgpt.local/api")
    monkeypatch.setenv("FASTGPT_API_KEY", "sk-test")
    monkeypatch.delenv("FASTGPT_DEFAULT_DATASET_ID", raising=False)
    get_settings.cache_clear()
    mocked_request = AsyncMock(return_value=(
        {"data": [{"_id": "dataset_live", "name": "产品资料库"}]}, "trace-datasets",
    ))

    with patch("knowledge.request_fastgpt_json", mocked_request):
        client = TestClient(app)
        response = client.post("/api/v1/knowledge/sync")
        spaces = client.get("/api/v1/knowledge/spaces")

    assert response.status_code == 200
    payload = response.json()
    assert payload["created"] == 1
    assert payload["updated"] == 0
    assert payload["total"] == 1
    assert spaces.status_code == 200
    items = spaces.json()["items"]
    assert items[0]["title"] == "产品资料库"
    assert items[0]["fastgpt_dataset_id"] == "dataset_live"
    assert items[0]["fastgpt_app_id"] is None


def test_knowledge_sync_updates_existing_mapping(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'knowledge_sync_update.db').as_posix()}")
    monkeypatch.setenv("FASTGPT_MODE", "real")
    monkeypatch.setenv("FASTGPT_BASE_URL", "http://fastgpt.local/api")
    monkeypatch.setenv("FASTGPT_API_KEY", "sk-test")
    get_settings.cache_clear()

    first = AsyncMock(return_value=(
        {"data": [{"_id": "dataset_live", "name": "产品资料库"}]}, "trace-datasets",
    ))
    second = AsyncMock(return_value=(
        {"data": [{"_id": "dataset_live", "name": "产品资料库（新版）"}]}, "trace-datasets",
    ))

    client = TestClient(app)
    with patch("knowledge.request_fastgpt_json", first):
        first_response = client.post("/api/v1/knowledge/sync")
    with patch("knowledge.request_fastgpt_json", second):
        second_response = client.post("/api/v1/knowledge/sync")
        spaces = client.get("/api/v1/knowledge/spaces")

    assert first_response.status_code == 200
    assert first_response.json()["created"] == 1
    assert second_response.status_code == 200
    assert second_response.json()["created"] == 0
    assert second_response.json()["updated"] == 1
    assert spaces.json()["items"][0]["title"] == "产品资料库（新版）"


def test_knowledge_sync_only_syncs_datasets(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'knowledge_sync_dataset_only.db').as_posix()}")
    monkeypatch.setenv("FASTGPT_MODE", "real")
    monkeypatch.setenv("FASTGPT_BASE_URL", "http://fastgpt.local/api")
    monkeypatch.setenv("FASTGPT_API_KEY", "sk-test")
    get_settings.cache_clear()

    mocked_request = AsyncMock(return_value=(
        {"data": [{"_id": "dataset_live", "name": "产品资料库"}]}, "trace-datasets",
    ))

    with patch("knowledge.request_fastgpt_json", mocked_request):
        client = TestClient(app)
        response = client.post("/api/v1/knowledge/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["created"] == 1
    assert payload["total"] == 1


def test_knowledge_mapping_management_controls_visibility_and_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'knowledge_manage.db').as_posix()}")
    monkeypatch.setenv("FASTGPT_MODE", "real")
    monkeypatch.setenv("FASTGPT_BASE_URL", "http://fastgpt.local/api")
    monkeypatch.setenv("FASTGPT_API_KEY", "sk-test")
    get_settings.cache_clear()
    mocked_request = AsyncMock(return_value=(
        {"data": [{"_id": "dataset_live", "name": "产品资料库"}]}, "trace-datasets",
    ))

    with patch("knowledge.request_fastgpt_json", mocked_request):
        client = TestClient(app)
        assert client.post("/api/v1/knowledge/sync").status_code == 200

    mappings = client.get("/api/v1/knowledge/mappings")
    assert mappings.status_code == 200
    assert mappings.json()["total"] == 1

    dataset_id = "dataset:dataset_live"
    updated = client.patch(
        f"/api/v1/knowledge/mappings/{dataset_id}",
        json={"display_name": "产品资料库（运营）", "enabled": False},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "产品资料库（运营）"
    assert updated.json()["enabled"] is False

    spaces = client.get("/api/v1/knowledge/spaces")
    assert all(item["id"] != dataset_id for item in spaces.json()["items"])

    reenabled = client.patch(
        f"/api/v1/knowledge/mappings/{dataset_id}",
        json={"enabled": True, "is_default_import_target": True},
    )
    assert reenabled.status_code == 200
    assert reenabled.json()["is_default_import_target"] is True

    deleted = client.delete("/api/v1/knowledge/mappings/dataset:dataset_live")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert client.get("/api/v1/knowledge/mappings").json()["total"] == 0


def test_knowledge_import_records_are_saved_for_dataset_mapping(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'knowledge_import_records.db').as_posix()}")
    monkeypatch.setenv("FASTGPT_MODE", "real")
    monkeypatch.setenv("FASTGPT_BASE_URL", "http://fastgpt.local/api")
    monkeypatch.setenv("FASTGPT_API_KEY", "sk-test")
    get_settings.cache_clear()
    mocked_request = AsyncMock(return_value=(
        {"data": [{"_id": "dataset_live", "name": "产品资料库"}]}, "trace-datasets",
    ))
    mocked_import = AsyncMock(return_value={
        "dataset_id": "dataset_live",
        "file_name": "handbook.txt",
        "status": "queued",
        "fastgpt_response": {"data": {"collectionId": "collection_live"}},
    })

    client = TestClient(app)
    with patch("knowledge.request_fastgpt_json", mocked_request):
        assert client.post("/api/v1/knowledge/sync").status_code == 200
    with patch("knowledge.import_file_to_fastgpt", mocked_import):
        response = client.post(
            "/api/v1/knowledge/import",
            data={"dataset_id": "dataset_live"},
            files={"file": ("handbook.txt", b"hello knowledge", "text/plain")},
        )

    assert response.status_code == 202
    imports = client.get("/api/v1/knowledge/imports")
    assert imports.status_code == 200
    payload = imports.json()
    assert payload["total"] == 1
    assert payload["items"][0]["file_name"] == "handbook.txt"
    assert payload["items"][0]["dataset_id"] == "dataset_live"
    assert payload["items"][0]["collection_id"] == "collection_live"
    assert payload["items"][0]["status"] == "queued"


def test_knowledge_chat_delegates_to_hermes(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_MODE", "mock")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/v1/knowledge/chat",
        json={"question": "什么是协同门户？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "answer" in payload
    assert "[Hermes mock]" in payload["answer"]
    assert "什么是协同门户？" in payload["answer"]
    assert "sources" in payload


def test_knowledge_chat_falls_back_when_hermes_fails(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_MODE", "real")
    monkeypatch.setenv("HERMES_BASE_URL", "http://127.0.0.1:19999")
    monkeypatch.setenv("HERMES_TIMEOUT_SECONDS", "1")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/v1/knowledge/chat",
        json={"question": "协同门户有哪些功能？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "answer" in payload
    assert "协同门户有哪些功能？" in payload["answer"]
    assert "sources" in payload


def test_knowledge_chat_force_rag_with_slash_command(monkeypatch) -> None:
    """输入以 /rag 开头时强制走 RAG 检索模式。"""
    monkeypatch.setenv("HERMES_MODE", "mock")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/v1/knowledge/chat",
        json={"question": "/rag 什么是差序格局？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "answer" in payload
    assert payload.get("mode") == "rag"
    # 斜杠命令已被剥离，问题中不含 /rag
    assert "差序格局" in payload["answer"]


def test_knowledge_chat_force_chat_with_slash_command(monkeypatch) -> None:
    """输入以 /chat 开头时强制走直接对话模式。"""
    monkeypatch.setenv("HERMES_MODE", "mock")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/v1/knowledge/chat",
        json={"question": "/chat 如何安装 Python？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "answer" in payload
    assert payload.get("mode") == "chat"
    # sources 应为空（chat 模式不检索）
    assert payload.get("sources") == []


def test_knowledge_chat_mode_field_forces_rag(monkeypatch) -> None:
    """通过 mode 字段指定 rag 时强制走 RAG。"""
    monkeypatch.setenv("HERMES_MODE", "mock")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/v1/knowledge/chat",
        json={"question": "什么是协同门户？", "mode": "rag"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("mode") == "rag"
    assert "answer" in payload


def test_knowledge_chat_mode_field_forces_chat(monkeypatch) -> None:
    """通过 mode 字段指定 chat 时强制走直接对话。"""
    monkeypatch.setenv("HERMES_MODE", "mock")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/v1/knowledge/chat",
        json={"question": "今天天气怎么样？", "mode": "chat"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("mode") == "chat"
    assert payload.get("sources") == []
    assert "answer" in payload


def test_knowledge_chat_auto_mode_returns_mode_field(monkeypatch) -> None:
    """auto 模式下响应包含 mode 字段标识实际运行模式。"""
    monkeypatch.setenv("HERMES_MODE", "mock")
    get_settings.cache_clear()
    client = TestClient(app)

    response = client.post(
        "/api/v1/knowledge/chat",
        json={"question": "协同门户有哪些功能？"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "mode" in payload
    assert payload["mode"] in ("rag", "chat")
    assert "answer" in payload
    assert "sources" in payload
