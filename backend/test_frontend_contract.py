from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_INDEX = PROJECT_ROOT / "frontend" / "index.html"
FRONTEND_APP_JS = PROJECT_ROOT / "frontend" / "src" / "app.js"


def _read_frontend_markup() -> str:
    """Read both index.html and app.js — the inline script was extracted in T6a."""
    html = FRONTEND_INDEX.read_text(encoding="utf-8")
    if FRONTEND_APP_JS.exists():
        html += "\n" + FRONTEND_APP_JS.read_text(encoding="utf-8")
    return html


def test_frontend_bootstraps_embed_urls_from_backend_contract() -> None:
    markup = _read_frontend_markup()

    assert "/api/v1/portal/bootstrap" in markup
    assert "fetchPortalBootstrap" in markup
    assert "payload.embed_urls" in markup
    assert "state.embedUrls" in markup


def test_frontend_calls_backend_for_interactive_portal_data() -> None:
    markup = _read_frontend_markup()

    for endpoint in [
        "/api/v1/subsystems",
        "/api/v1/portal/notices",
        "/api/v1/portal/documents",
        "/api/v1/portal/resources",
        "/api/v1/portal/services",
        "/api/v1/portal/news",
        "/api/v1/portal/preferences",
        "/api/v1/portal/dashboard",
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
    markup = _read_frontend_markup()

    assert 'window.location.protocol === "file:" ? "http://localhost:8000" : ""' in markup
    assert 'apiJson("/api/v1/portal/bootstrap")' in markup


def test_frontend_implements_portal_assets_inside_platform() -> None:
    markup = _read_frontend_markup()

    for expected in [
        "function renderSubsystems(",
        "function openSubsystem(",
        "function renderAssetCenter(",
        "function openPortalAsset(",
        "function fetchPortalPreferences(",
        "function savePortalPreferences(",
        "function fetchPortalDashboard(",
        'id="subsystem"',
        'id="notice-center"',
        'id="document-center"',
        'id="resource-center"',
        'id="service-center"',
        'id="news-center"',
        'id="portal-dashboard"',
    ]:
        assert expected in markup


def test_frontend_keeps_iframe_usage_limited_to_feishu_and_dingtalk() -> None:
    markup = _read_frontend_markup()

    # Phase 1 T9: 3 iframes total — feishu, dingtalk, + dynamic subsystem iframe for teaching-cloud / data-portal shells
    assert markup.count("<iframe") == 3
    assert 'id="feishuFrame"' in markup
    assert 'id="dingtalkFrame"' in markup


def test_frontend_replaces_portal_business_toast_only_entries() -> None:
    markup = _read_frontend_markup()

    forbidden = [
        'data-toast="已打开：',
        'data-toast="打开：制度手册"',
        'data-toast="已进入公告中心"',
        'data-toast="已进入文档中心"',
        'data-toast="资源管理已打开"',
        'data-toast="经营看板已进入详情"',
    ]
    for text in forbidden:
        assert text not in markup


def test_frontend_subsystem_view_has_native_actions_not_service_redirects() -> None:
    markup = _read_frontend_markup()
    subsystem_view = markup.split("function renderSubsystemView()", 1)[1].split("async function renderAssetCenter", 1)[0]

    assert "function renderSubsystemAction(" in markup
    assert "subsystem-action-toolbar" in subsystem_view
    assert 'data-open-asset-center="services"' not in subsystem_view


def test_frontend_portal_layout_uses_compact_density_controls() -> None:
    markup = _read_frontend_markup()

    for expected in [
        ".portal-hero { min-height: 132px;",
        ".empty-state { min-height: 118px;",
        ".asset-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));",
        ".internal-grid { display: grid; grid-template-columns: minmax(0, 1fr) 220px;",
        ".subsystem-action-toolbar",
    ]:
        assert expected in markup


def test_frontend_subsystem_detail_view_is_dense() -> None:
    markup = _read_frontend_markup()
    subsystem_view = markup.split("function renderSubsystemView()", 1)[1].split("async function renderAssetCenter", 1)[0]

    for expected in [
        ".internal-card.subsystem-card .card-header { min-height: 36px;",
        ".internal-card.subsystem-card .card-body { gap: 6px; padding: 8px 10px;",
        ".subsystem-summary-line { margin: 0;",
        ".subsystem-action { min-height: 28px;",
        ".subsystem-card .detail-list li { min-height: 28px;",
    ]:
        assert expected in markup
    assert "subsystem-card" in subsystem_view
    assert "subsystem-summary-line" in subsystem_view


def test_frontend_renders_independent_subsystem_workbenches() -> None:
    markup = _read_frontend_markup()
    subsystem_view = markup.split("function renderSubsystemView()", 1)[1].split("async function renderAssetCenter", 1)[0]

    for expected in [
        "const subsystemWorkbenches =",
        "function getSubsystemWorkbench(",
        "function renderSubsystemMetrics(",
        "function renderSubsystemRecordList(",
        "function renderSubsystemRelatedPanel(",
        "data-subsystem-record",
        "subsystem-workbench-layout",
        "subsystem-record-table",
        "报修工单",
        "资产台账",
        "报销单",
        "待办流程",
        "指标看板",
    ]:
        assert expected in markup
    assert "getSubsystemWorkbench(system.code)" in subsystem_view
    assert "renderSubsystemRecordList(workbench" in subsystem_view


def test_frontend_subsystem_workbench_collapses_on_narrow_viewports() -> None:
    markup = _read_frontend_markup()

    assert ".subsystem-workbench-layout { grid-template-columns: 1fr; }" in markup
    assert ".subsystem-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in markup


def test_frontend_cards_have_static_edge_highlight() -> None:
    markup = _read_frontend_markup()

    for expected in [
        "--edge-highlight-width",
        "--edge-highlight-color",
        ".card::after",
        ".internal-card::after",
        ".asset-item::after",
        ".system-item::after",
        ".service-item::after",
        ".resource-item::after",
        "linear-gradient(135deg",
    ]:
        assert expected in markup
    assert "@keyframes borderBeamSpin" not in markup
    assert "animation: borderBeamSpin" not in markup


def test_frontend_buttons_integrate_liquid_metal_with_original_style() -> None:
    markup = _read_frontend_markup()
    skin = markup.split("/* White liquid metal buttons */", 1)[1].split("/* Card shell */", 1)[0]

    for expected in [
        "--liquid-button-surface",
        "--liquid-button-highlight",
        ".btn::before",
        ".subsystem-action::before",
        ".quick-action::before",
        "radial-gradient(",
        "linear-gradient(180deg, #ffffff 0%, #f7fbff 100%)",
        "linear-gradient(180deg, #2f6bd7 0%, #1f56c4 100%)",
    ]:
        assert expected in skin
    for intrusive_selector in [
        ".global-tab::before",
        ".top-icon::before",
        ".card-link::before",
        ".asset-item::before",
        ".system-item::before",
        ".service-item::before",
        ".resource-item::before",
        ".shortcut::before",
        ".admin-subtab::before",
    ]:
        assert intrusive_selector not in skin
    assert "#000000" not in skin
    assert "#202020" not in skin
    assert "rgba(0, 0, 0" not in skin


def test_frontend_primary_task_button_keeps_blue_surface_under_liquid_skin() -> None:
    markup = _read_frontend_markup()
    skin = markup.split("/* White liquid metal buttons */", 1)[1].split("/* Card shell */", 1)[0]

    assert ".task-composer .btn.primary" in skin
    assert "background: linear-gradient(180deg, #2f6bd7 0%, #1f56c4 100%)" in skin
    assert ".btn > *" in skin
    assert "z-index: 1;" in skin


def test_frontend_bootstrap_does_not_rebind_embed_event_handlers() -> None:
    markup = _read_frontend_markup()

    assert "function renderEmbeds()" in markup
    assert "function bindEmbeds()" in markup
    apply_bootstrap = markup.split("function applyPortalBootstrap", 1)[1].split("async function fetchPortalBootstrap", 1)[0]
    assert "renderEmbeds();" in apply_bootstrap
    assert "bindEmbeds();" not in apply_bootstrap


def test_frontend_declares_inline_favicon_to_avoid_browser_404() -> None:
    markup = _read_frontend_markup()

    assert '<link rel="icon" href="data:image/svg+xml,' in markup


def test_frontend_persists_custom_calendar_events() -> None:
    markup = _read_frontend_markup()

    assert 'const eventStorageKey = "collab-calendar-events";' in markup
    assert "function getInitialEvents()" in markup
    assert "function saveEvents()" in markup
    assert "window.localStorage.setItem(eventStorageKey, JSON.stringify(state.events));" in markup
    assert "events: getInitialEvents()," in markup
    assert "saveEvents();" in markup


def test_frontend_allows_choosing_calendar_event_color() -> None:
    markup = _read_frontend_markup()

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
    markup = _read_frontend_markup()

    assert "editingEventIndex: null" in markup
    assert "function openEventModal(index = null)" in markup
    assert "data-edit-event" in markup
    assert "$$('[data-edit-event]', scope)" in markup
    assert 'state.events[state.editingEventIndex] = { title, date, tone };' in markup
    assert 'state.editingEventIndex = null;' in markup
    assert '$("#eventModalTitle").textContent = index === null ? "添加日程" : "编辑日程";' in markup


def test_frontend_uses_platform_current_time_for_calendar_today() -> None:
    markup = _read_frontend_markup()

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
    markup = _read_frontend_markup()

    assert 'String(now.getSeconds()).padStart(2, "0")' in markup
    assert "window.setInterval(updatePlatformTime, 1000);" in markup


def test_frontend_allows_deleting_existing_calendar_events() -> None:
    markup = _read_frontend_markup()

    assert 'id="eventDeleteButton"' in markup
    assert "function deleteEditingEvent()" in markup
    assert 'deleteButton.hidden = index === null;' in markup
    assert 'state.events.splice(state.editingEventIndex, 1);' in markup
    assert '$("#eventDeleteButton").addEventListener("click", () => deleteEditingEvent());' in markup
    assert 'showToast("日程已删除");' in markup


def test_frontend_imports_files_into_a_selected_fastgpt_dataset() -> None:
    markup = _read_frontend_markup()

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
    markup = _read_frontend_markup()

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
    markup = _read_frontend_markup()

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
