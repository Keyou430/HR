from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_INDEX = PROJECT_ROOT / "frontend" / "index.html"


def test_frontend_bootstraps_embed_urls_from_backend_contract() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert "/api/v1/portal/bootstrap" in markup
    assert "fetchPortalBootstrap" in markup
    assert "payload.embed_urls" in markup
    assert "state.embedUrls" in markup


def test_frontend_calls_backend_for_interactive_portal_data() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    for endpoint in [
        "/api/v1/tasks",
        "/api/v1/calendar/events",
        "/api/v1/integrations/embed-urls",
        "/api/v1/knowledge/sync",
        "/api/v1/knowledge/mappings",
        "/api/v1/knowledge/imports",
        "/api/v1/knowledge/import",
        "/api/v1/knowledge/chat",
        "/api/v1/search",
    ]:
        assert endpoint in markup


def test_frontend_uses_vite_proxy_for_http_dev_server() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert 'window.location.protocol === "file:" ? "http://localhost:8000" : ""' in markup
    assert "fetch(`${apiBaseUrl}/api/v1/portal/bootstrap`)" in markup


def test_frontend_bootstrap_does_not_rebind_embed_event_handlers() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert "function renderEmbeds()" in markup
    assert "function bindEmbeds()" in markup
    apply_bootstrap = markup.split("function applyPortalBootstrap", 1)[1].split("async function fetchPortalBootstrap", 1)[0]
    assert "renderEmbeds();" in apply_bootstrap
    assert "bindEmbeds();" not in apply_bootstrap


def test_frontend_declares_inline_favicon_to_avoid_browser_404() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert '<link rel="icon" href="data:image/svg+xml,' in markup


def test_frontend_persists_custom_calendar_events() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert 'const eventStorageKey = "collab-calendar-events";' in markup
    assert "function getInitialEvents()" in markup
    assert "function saveEvents()" in markup
    assert "window.localStorage.setItem(eventStorageKey, JSON.stringify(state.events));" in markup
    assert "events: getInitialEvents()," in markup
    assert "saveEvents();" in markup


def test_frontend_allows_choosing_calendar_event_color() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert 'id="eventTone"' in markup
    assert 'name="eventTone"' in markup
    assert 'class="tone-option blue"' in markup
    assert 'class="tone-option green"' in markup
    assert 'class="tone-option orange"' in markup
    assert 'value="blue"' in markup
    assert 'value="green"' in markup
    assert 'value="orange"' in markup
    assert 'const tone = $("[name=\\"eventTone\\"]:checked").value;' in markup
    assert "state.events.push({ title, date, tone });" in markup


def test_frontend_allows_editing_existing_calendar_events() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert "editingEventIndex: null" in markup
    assert "function openEventModal(index = null)" in markup
    assert "data-edit-event" in markup
    assert "$$('[data-edit-event]', scope)" in markup
    assert 'state.events[state.editingEventIndex] = { title, date, tone };' in markup
    assert 'state.editingEventIndex = null;' in markup
    assert '$("#eventModalTitle").textContent = index === null ? "添加日程" : "编辑日程";' in markup


def test_frontend_uses_platform_current_time_for_calendar_today() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert 'id="platformClock"' in markup
    assert "function updatePlatformTime()" in markup
    assert "const currentDate = new Date();" in markup
    assert "const todayKey = dateKey(currentDate);" in markup
    assert "selectedScheduleDate: todayKey" in markup
    assert "month: currentDate.getMonth()" in markup
    assert "year: currentDate.getFullYear()" in markup
    assert 'const current = key === todayKey;' in markup
    assert 'state.selectedScheduleDate = todayKey;' in markup
    assert 'state.month = currentDate.getMonth();' in markup
    assert 'state.year = currentDate.getFullYear();' in markup


def test_frontend_platform_clock_updates_every_second() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert 'String(now.getSeconds()).padStart(2, "0")' in markup
    assert "window.setInterval(updatePlatformTime, 1000);" in markup


def test_frontend_allows_deleting_existing_calendar_events() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert 'id="eventDeleteButton"' in markup
    assert "function deleteEditingEvent()" in markup
    assert 'deleteButton.hidden = index === null;' in markup
    assert 'state.events.splice(state.editingEventIndex, 1);' in markup
    assert '$("#eventDeleteButton").addEventListener("click", () => deleteEditingEvent());' in markup
    assert 'showToast("日程已删除");' in markup


def test_frontend_imports_files_into_a_selected_fastgpt_dataset() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    assert "async function readApiError(response)" in markup
    assert "throw new Error(await readApiError(response));" in markup
    assert 'function syncKnowledgeMappings()' in markup
    assert 'id="refreshKnowledge"' in markup
    assert 'id="knowledgeImportForm"' in markup
    assert 'id="knowledgeDatasetSelect"' in markup
    assert 'id="knowledgeImportFile"' in markup
    assert 'function renderKnowledgeDatasetOptions()' in markup
    assert 'function importKnowledgeFile(event)' in markup
    assert 'formData.append("dataset_id", datasetId);' in markup
    assert 'formData.append("file", file);' in markup
    assert 'apiJson("/api/v1/knowledge/sync"' in markup
    assert 'apiJson("/api/v1/knowledge/import"' in markup


def test_frontend_exposes_knowledge_mapping_management_controls() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    for expected in [
        'data-kb-filter="dataset"',
        'data-kb-filter="disabled"',
        'data-knowledge-import',
        'data-knowledge-toggle',
        'data-knowledge-default',
        'data-knowledge-rename',
        'data-knowledge-delete',
        'id="knowledgeImportRecords"',
        "function fetchKnowledgeMappings(",
        "function updateKnowledgeMapping(",
        "function deleteKnowledgeMapping(",
        "function fetchKnowledgeImports()",
        'apiJson(`/api/v1/knowledge/mappings/${mappingId}`',
        'apiJson("/api/v1/knowledge/imports"',
    ]:
        assert expected in markup


def test_frontend_supports_per_dataset_file_management() -> None:
    markup = FRONTEND_INDEX.read_text(encoding="utf-8")

    for expected in [
        'id="kbFilesModal"',
        'id="kbFilesList"',
        'data-kb-files=',
        'data-kb-files-dataset=',
        'data-delete-file=',
        "function bindKbFileActions()",
        "function openKbFiles(",
        "function renderKbFilesList(",
        "function closeKbFilesModal()",
        'apiJson(`/api/v1/knowledge/datasets/${encodeURIComponent(datasetId)}/files`',
        'apiJson(`/api/v1/knowledge/datasets/${encodeURIComponent(datasetId)}/files/${encodeURIComponent(fileId)}`',
    ]:
        assert expected in markup
