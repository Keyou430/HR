import importlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_backend_exports_typed_portal_contracts() -> None:
    schemas = importlib.import_module("schemas")

    for name in [
        "EmbedUrls",
        "PortalCatalogItem",
        "PortalCatalog",
        "PortalBootstrapResponse",
    ]:
        assert hasattr(schemas, name)


def test_portal_bootstrap_uses_response_model_contract() -> None:
    source = read("backend/portal.py")

    assert "PortalBootstrapResponse" in source
    assert '@router.get("/bootstrap", response_model=PortalBootstrapResponse)' in source


def test_frontend_exports_portal_bootstrap_contracts() -> None:
    source = read("frontend/src/types/index.ts")

    for name in [
        "EmbedUrls",
        "PortalCatalogItem",
        "PortalCatalog",
        "PortalBootstrapResponse",
    ]:
        assert f"export interface {name}" in source


def test_backend_and_frontend_have_basic_project_configs() -> None:
    requirements = read("backend/requirements.txt")
    package_json = json.loads(read("frontend/package.json"))
    vite_config = read("frontend/vite.config.ts")

    for dependency in [
        "fastapi",
        "uvicorn[standard]",
        "pydantic-settings",
        "httpx",
    ]:
        assert dependency in requirements

    assert package_json["scripts"]["dev"] == "vite"
    assert package_json["scripts"]["test"] == "node --test"
    assert package_json["scripts"]["build"] == "tsc -b && npm exec vite build"
    assert "'/api'" in vite_config
    assert "http://127.0.0.1:8000" in vite_config


def test_database_session_module_uses_replica_local_config() -> None:
    session = importlib.import_module("session")

    assert hasattr(session, "create_db_engine")
    assert hasattr(session, "get_db")


def test_default_database_config_is_replica_scoped(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_default_database_config_is_replica_scoped")

    config = importlib.import_module("config")
    config.get_settings.cache_clear()

    settings = config.get_settings()

    assert settings.DATABASE_URL.startswith("sqlite:///")
    assert "replica_platform_" in settings.DATABASE_URL
    assert "hermes_platform" not in settings.DATABASE_URL


def test_backend_env_file_is_resolved_from_backend_directory(monkeypatch) -> None:
    source = read("backend/config.py")

    assert 'Path(__file__).with_name(".env")' in source
