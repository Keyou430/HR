/**
 * Website (网站群) subsystem view — Phase 4 T17.
 * Registered on ``window.App.views.website``.
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
    var system = (config && config.system) || { code: "website", title: "网站群" };
    container.innerHTML =
      '<div class="subsystem-view-shell">' +
      '<button class="btn btn-primary" id="wsCreateBtn">+ 新建站点</button></div>' +
      '<div class="subsystem-tabs"><button class="subsystem-tab active" data-tab="all">全部站点</button><button class="subsystem-tab" data-tab="stats">站点统计</button></div>' +
      '<div id="websiteContent"></div>';
    document.getElementById("wsCreateBtn").addEventListener("click", showCreateForm);
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
      var resp = await api("/api/v1/enterprise/website/sites");
      if (!resp.ok) throw new Error("load failed");
      var data = await resp.json();
      renderList(data.items || []);
    } catch (e) {
      $("#websiteContent").innerHTML = '<p style="text-align:center;padding:40px;color:var(--gray)">加载失败，请重试</p>';
    }
  }

  function renderList(items) {
    var rows = items.map(function (it) {
      return '<tr>' +
        '<td>' + esc(it.name) + '</td><td>' + esc(it.domain || "-") + '</td><td>' + esc(it.category) + '</td>' +
        '<td><span class="status-pill" style="color:#fff;background:' + statusColor(it.status) + '">' + esc(statusLabel(it.status)) + '</span></td>' +
        '<td>' + esc(it.owner_dept || "-") + '</td>' +
        '<td><button class="btn btn-sm ws-edit-btn" data-id="' + it.id + '">编辑</button></td>' +
        '</tr>';
    }).join("");
    $("#websiteContent").innerHTML =
      '<table class="data-table"><thead><tr><th>名称</th><th>域名</th><th>分类</th><th>状态</th><th>负责部门</th><th>操作</th></tr></thead><tbody>' + (rows || '<tr><td colspan="6" style="text-align:center;color:var(--gray)">暂无数据</td></tr>') + '</tbody></table>';
    $$(".ws-edit-btn").forEach(function (btn) {
      btn.addEventListener("click", function () { editSite(parseInt(btn.dataset.id)); });
    });
  }

  async function loadStats() {
    try {
      var resp = await api("/api/v1/enterprise/website/sites/stats");
      if (!resp.ok) throw new Error("load failed");
      var data = await resp.json();
      $("#websiteContent").innerHTML =
        '<div class="subsystem-metrics" style="margin-bottom:12px"><div class="subsystem-metric"><strong>' + (data.total || 0) + '</strong><span>站点总数</span></div></div>' +
        '<div class="internal-card"><div class="card-header"><div class="card-title">按状态</div></div><div class="card-body">' + kvTable(data.by_status || {}, statusLabel) + '</div></div>' +
        '<div class="internal-card" style="margin-top:12px"><div class="card-header"><div class="card-title">按分类</div></div><div class="card-body">' + kvTable(data.by_category || {}, esc) + '</div></div>';
    } catch (e) {
      $("#websiteContent").innerHTML = '<p style="text-align:center;padding:40px;color:var(--gray)">加载失败</p>';
    }
  }

  function kvTable(obj, labelFn) {
    var rows = Object.keys(obj).map(function (k) { return '<tr><td>' + (labelFn(k) || esc(k)) + '</td><td>' + obj[k] + '</td></tr>'; }).join("");
    return '<table class="data-table"><thead><tr><th>分类</th><th>数量</th></tr></thead><tbody>' + (rows || '<tr><td colspan="2" style="color:var(--gray)">暂无数据</td></tr>') + '</tbody></table>';
  }

  function showCreateForm() {
    editId = null;
    showModal("新建站点", siteForm({ name: "", domain: "", category: "", status: "draft", owner_dept: "", columns_json: "[]", description: "" }), saveSite);
  }

  async function editSite(id) {
    try {
      var r = await api("/api/v1/enterprise/website/sites/" + id);
      var it = await r.json();
      editId = id;
      showModal("编辑站点", siteForm(it), saveSite);
    } catch (e) { alert("加载失败"); }
  }

  function siteForm(data) {
    return '<div class="form-grid">' +
      '<div class="field"><label>名称</label><input id="sfName" value="' + escAttr(data.name || "") + '"></div>' +
      '<div class="field"><label>域名</label><input id="sfDomain" value="' + escAttr(data.domain || "") + '"></div>' +
      '<div class="field"><label>分类</label><input id="sfCategory" value="' + escAttr(data.category || "") + '"></div>' +
      '<div class="field"><label>状态</label><select id="sfStatus">' + statusOptions(data.status) + '</select></div>' +
      '<div class="field"><label>负责部门</label><input id="sfOwnerDept" value="' + escAttr(data.owner_dept || "") + '"></div>' +
      '<div class="field"><label>栏目配置 (JSON)</label><textarea id="sfColumns" rows="3">' + esc(data.columns_json || "[]") + '</textarea></div>' +
      '<div class="field"><label>描述</label><textarea id="sfDesc" rows="2">' + esc(data.description || "") + '</textarea></div>' +
      '</div>';
  }

  async function saveSite() {
    var payload = {
      name: $("#sfName").value,
      domain: $("#sfDomain").value || null,
      category: $("#sfCategory").value,
      status: $("#sfStatus").value,
      owner_dept: $("#sfOwnerDept").value || null,
      columns_json: $("#sfColumns").value || null,
      description: $("#sfDesc").value || null,
    };
    var url = editId ? "/api/v1/enterprise/website/sites/" + editId : "/api/v1/enterprise/website/sites";
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
    overlay.id = "wsModal";
    overlay.innerHTML = '<div class="modal-content"><div class="modal-header"><h2>' + esc(title) + '</h2><button class="modal-close-btn" id="wsModalClose">&times;</button></div>' + bodyHtml + '<div class="modal-actions"><button class="btn" id="wsModalCancel">取消</button><button class="btn primary" id="wsModalSubmit">保存</button></div></div>';
    document.body.appendChild(overlay);
    function onKey(e) { if (e.key === "Escape") closeModal(); }
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) closeModal(); });
    document.getElementById("wsModalClose").onclick = closeModal;
    document.getElementById("wsModalCancel").onclick = closeModal;
    document.getElementById("wsModalSubmit").onclick = function () { if (_modalCb) _modalCb(); };
  }

  function closeModal() {
    var m = document.getElementById("wsModal");
    if (m) m.remove();
    _modalCb = null;
  }

  function $$(sel) { return containerEl.querySelectorAll(sel); }
  function statusColor(s) { return { draft: "#868e96", published: "#20c997", archived: "#ff922b" }[s] || "#868e96"; }
  function statusLabel(s) { return { draft: "草稿", published: "已发布", archived: "已归档" }[s] || s; }
  function statusOptions(current) { return ["draft", "published", "archived"].map(function (v) { return '<option value="' + v + '"' + (current === v ? " selected" : "") + '>' + statusLabel(v) + '</option>'; }).join(""); }
  function esc(s) { return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  function escAttr(s) { return String(s || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;"); }

  if (typeof window !== "undefined") {
    window.App = window.App || {};
    window.App.views = window.App.views || {};
    window.App.views.website = { render: render };
  }
})();
