/**
 * Estate (房产管理) subsystem view — Phase 4 T17.
 * Registered on ``window.App.views.estate``.
 */
(function () {
  "use strict";

  var apiBase = window.COLLAB_API_BASE_URL || (window.location.protocol === "file:" ? "http://localhost:8000" : "");
  var currentTab = "all";
  var editId = null;
  var containerEl = null;

  function api(path, opts) {
    opts = opts || {};
    var headers = opts.headers || {};
    if (!(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
    var token = (window.App && window.App._authToken) || (window.__auth && window.__auth.getToken && window.__auth.getToken());
    if (token) headers["Authorization"] = "Bearer " + token;
    return fetch(apiBase + path, Object.assign({}, opts, { headers: headers }));
  }

  function $(sel) { return (containerEl || document).querySelector(sel); }

  function render(container, config) {
    if (typeof container === "string") container = document.querySelector(container);
    if (!container) return;
    containerEl = container;
    var system = (config && config.system) || { code: "estate", title: "房产管理" };
    container.innerHTML =
      '<div class="subsystem-view-shell">' +
      '<button class="btn btn-primary" id="esCreateBtn">+ 新增空间</button></div>' +
      '<div class="subsystem-tabs"><button class="subsystem-tab active" data-tab="all">全部空间</button><button class="subsystem-tab" data-tab="stats">用房统计</button></div>' +
      '<div id="estateContent"></div>';
    document.getElementById("esCreateBtn").addEventListener("click", showCreateForm);
    bindTabs();
    loadTab("all");
  }

  function bindTabs() {
    var tabs = containerEl.querySelectorAll(".subsystem-tab");
    tabs.forEach(function (t) {
      t.addEventListener("click", function () {
        tabs.forEach(function (b) { b.classList.remove("active"); });
        t.classList.add("active");
        currentTab = t.dataset.tab;
        loadTab(currentTab);
      });
    });
  }

  function loadTab(tab) {
    if (tab === "stats") loadStats(); else loadList();
  }

  async function loadList() {
    try {
      var resp = await api("/api/v1/enterprise/estate/spaces");
      if (!resp.ok) throw new Error("load failed");
      var data = await resp.json();
      renderList(data.items || []);
    } catch (e) {
      $("#estateContent").innerHTML = '<p style="text-align:center;padding:40px;color:var(--gray)">加载失败，请重试</p>';
    }
  }

  function renderList(items) {
    var rows = items.map(function (it) {
      return '<tr>' +
        '<td>' + esc(it.name) + '</td><td>' + esc(it.code) + '</td><td>' + esc(it.building || "-") + '</td><td>' + esc(it.floor || "-") + '</td>' +
        '<td>' + esc(catLabel(it.category)) + '</td>' +
        '<td><span class="status-pill" style="color:#fff;background:' + statusColor(it.status) + '">' + esc(statusLabel(it.status)) + '</span></td>' +
        '<td>' + (it.area_sqm != null ? it.area_sqm + " m²" : "-") + '</td>' +
        '<td>' + esc(it.contact_person || "-") + '</td>' +
        '<td><button class="btn btn-sm es-edit-btn" data-id="' + it.id + '">编辑</button></td>' +
        '</tr>';
    }).join("");
    $("#estateContent").innerHTML =
      '<table class="data-table"><thead><tr><th>名称</th><th>编号</th><th>楼栋</th><th>楼层</th><th>类别</th><th>状态</th><th>面积</th><th>联系人</th><th>操作</th></tr></thead><tbody>' + (rows || '<tr><td colspan="9" style="text-align:center;color:var(--gray)">暂无数据</td></tr>') + '</tbody></table>';
    $$(".es-edit-btn").forEach(function (btn) {
      btn.addEventListener("click", function () { editSpace(parseInt(btn.dataset.id)); });
    });
  }

  async function loadStats() {
    try {
      var resp = await api("/api/v1/enterprise/estate/spaces/stats");
      if (!resp.ok) throw new Error("load failed");
      var data = await resp.json();
      $("#estateContent").innerHTML =
        '<div class="subsystem-metrics" style="margin-bottom:12px"><div class="subsystem-metric"><strong>' + (data.total || 0) + '</strong><span>空间总数</span></div></div>' +
        '<div class="internal-card"><div class="card-header"><div class="card-title">按类别</div></div><div class="card-body">' + kvTable(data.by_category || {}, catLabel) + '</div></div>' +
        '<div class="internal-card" style="margin-top:12px"><div class="card-header"><div class="card-title">按状态</div></div><div class="card-body">' + kvTable(data.by_status || {}, statusLabel) + '</div></div>';
    } catch (e) {
      $("#estateContent").innerHTML = '<p style="text-align:center;padding:40px;color:var(--gray)">加载失败</p>';
    }
  }

  function kvTable(obj, labelFn) {
    var rows = Object.keys(obj).map(function (k) { return '<tr><td>' + (labelFn(k) || esc(k)) + '</td><td>' + obj[k] + '</td></tr>'; }).join("");
    return '<table class="data-table"><thead><tr><th>分类</th><th>数量</th></tr></thead><tbody>' + (rows || '<tr><td colspan="2" style="color:var(--gray)">暂无数据</td></tr>') + '</tbody></table>';
  }

  function showCreateForm() {
    editId = null;
    showModal("新增空间", spaceForm({ name: "", code: "", category: "办公", building: "", floor: "", area_sqm: null, status: "vacant", department_id: "", description: "", contact_person: "" }), saveSpace);
  }

  async function editSpace(id) {
    try {
      var r = await api("/api/v1/enterprise/estate/spaces/" + id);
      var it = await r.json();
      editId = id;
      showModal("编辑空间", spaceForm(it), saveSpace);
    } catch (e) { alert("加载失败"); }
  }

  function spaceForm(data) {
    return '<div class="form-grid">' +
      '<div class="field"><label>名称</label><input id="sfName" value="' + escAttr(data.name || "") + '"></div>' +
      '<div class="field"><label>编号</label><input id="sfCode" value="' + escAttr(data.code || "") + '"></div>' +
      '<div class="field"><label>类别</label><select id="sfCategory">' + catOptions(data.category) + '</select></div>' +
      '<div class="field"><label>楼栋</label><input id="sfBuilding" value="' + escAttr(data.building || "") + '"></div>' +
      '<div class="field"><label>楼层</label><input id="sfFloor" value="' + escAttr(data.floor || "") + '"></div>' +
      '<div class="field"><label>面积 (m²)</label><input id="sfArea" type="number" step="0.01" value="' + (data.area_sqm != null ? data.area_sqm : "") + '"></div>' +
      '<div class="field"><label>状态</label><select id="sfStatus">' + statusOptions(data.status) + '</select></div>' +
      '<div class="field"><label>使用部门</label><input id="sfDeptId" value="' + escAttr(data.department_id || "") + '"></div>' +
      '<div class="field"><label>联系人</label><input id="sfContact" value="' + escAttr(data.contact_person || "") + '"></div>' +
      '<div class="field"><label>描述</label><textarea id="sfDesc" rows="2">' + esc(data.description || "") + '</textarea></div>' +
      '</div>';
  }

  async function saveSpace() {
    var payload = {
      name: $("#sfName").value,
      code: $("#sfCode").value,
      category: $("#sfCategory").value,
      building: $("#sfBuilding").value || null,
      floor: $("#sfFloor").value || null,
      area_sqm: $("#sfArea").value ? parseFloat($("#sfArea").value) : null,
      status: $("#sfStatus").value,
      department_id: $("#sfDeptId").value || null,
      description: $("#sfDesc").value || null,
      contact_person: $("#sfContact").value || null,
    };
    var url = editId ? "/api/v1/enterprise/estate/spaces/" + editId : "/api/v1/enterprise/estate/spaces";
    var method = editId ? "PATCH" : "POST";
    try {
      var r = await api(url, { method: method, body: JSON.stringify(payload) });
      if (!r.ok) { var e = await r.json(); alert("保存失败: " + (e.detail || "")); return; }
      closeModal();
      loadTab(currentTab);
    } catch (ex) { alert("保存失败"); }
  }

  // ── Shared modal ──────────────────────────────────────────────────
  var _modalCb = null;
  function showModal(title, bodyHtml, cb) {
    _modalCb = cb;
    var overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.id = "esModal";
    overlay.innerHTML = '<div class="modal-content"><div class="modal-header"><h2>' + esc(title) + '</h2><button class="modal-close-btn" id="esModalClose">&times;</button></div>' + bodyHtml + '<div class="modal-actions"><button class="btn" id="esModalCancel">取消</button><button class="btn primary" id="esModalSubmit">保存</button></div></div>';
    document.body.appendChild(overlay);
    function onKey(e) { if (e.key === "Escape") closeModal(); }
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) closeModal(); });
    document.getElementById("esModalClose").onclick = closeModal;
    document.getElementById("esModalCancel").onclick = closeModal;
    document.getElementById("esModalSubmit").onclick = function () { if (_modalCb) _modalCb(); };
  }

  function closeModal() {
    var m = document.getElementById("esModal");
    if (m) m.remove();
    _modalCb = null;
  }

  function $$(sel) { return containerEl.querySelectorAll(sel); }
  function catLabel(c) { return { "教学": "教学", "办公": "办公", "生活": "生活", "商业": "商业" }[c] || c; }
  function catOptions(current) { return ["教学", "办公", "生活", "商业"].map(function (v) { return '<option value="' + v + '"' + (current === v ? " selected" : "") + '>' + v + '</option>'; }).join(""); }
  function statusColor(s) { return { vacant: "#868e96", occupied: "#20c997", maintenance: "#ff922b", reserved: "#339af0" }[s] || "#868e96"; }
  function statusLabel(s) { return { vacant: "空置", occupied: "已占用", maintenance: "维护中", reserved: "已预留" }[s] || s; }
  function statusOptions(current) { return ["vacant", "occupied", "maintenance", "reserved"].map(function (v) { return '<option value="' + v + '"' + (current === v ? " selected" : "") + '>' + statusLabel(v) + '</option>'; }).join(""); }
  function esc(s) { return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  function escAttr(s) { return String(s || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;"); }

  if (typeof window !== "undefined") {
    window.App = window.App || {};
    window.App.views = window.App.views || {};
    window.App.views.estate = { render: render };
  }
})();
