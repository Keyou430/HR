/**
 * Employment (就业系统) subsystem view — Phase 4 T17.
 * Registered on ``window.App.views.employment``.
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
    var system = (config && config.system) || { code: "employment", title: "就业系统" };
    container.innerHTML =
      '<div class="subsystem-view-shell">' +
      '<button class="btn btn-primary" id="epCreateBtn">+ 发布岗位</button></div>' +
      '<div class="subsystem-tabs"><button class="subsystem-tab active" data-tab="all">全部岗位</button><button class="subsystem-tab" data-tab="stats">就业统计</button></div>' +
      '<div id="empContent"></div>';
    document.getElementById("epCreateBtn").addEventListener("click", showCreateForm);
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
      var resp = await api("/api/v1/enterprise/employment/postings");
      if (!resp.ok) throw new Error("load failed");
      var data = await resp.json();
      renderList(data.items || []);
    } catch (e) {
      $("#empContent").innerHTML = '<p style="text-align:center;padding:40px;color:var(--gray)">加载失败，请重试</p>';
    }
  }

  function renderList(items) {
    var rows = items.map(function (it) {
      return '<tr>' +
        '<td>' + esc(it.title) + '</td><td>' + esc(it.company_name) + '</td><td>' + esc(catLabel(it.position_category)) + '</td>' +
        '<td>' + esc(it.salary_range || "-") + '</td><td>' + esc(it.location || "-") + '</td>' +
        '<td><span class="status-pill" style="color:#fff;background:' + statusColor(it.status) + '">' + esc(statusLabel(it.status)) + '</span></td>' +
        '<td>' + esc(it.deadline || "-") + '</td>' +
        '<td><button class="btn btn-sm ep-edit-btn" data-id="' + it.id + '">编辑</button></td>' +
        '</tr>';
    }).join("");
    $("#empContent").innerHTML =
      '<table class="data-table"><thead><tr><th>岗位</th><th>企业</th><th>类别</th><th>薪资</th><th>地点</th><th>状态</th><th>截止日期</th><th>操作</th></tr></thead><tbody>' + (rows || '<tr><td colspan="8" style="text-align:center;color:var(--gray)">暂无数据</td></tr>') + '</tbody></table>';
    $$(".ep-edit-btn").forEach(function (btn) {
      btn.addEventListener("click", function () { editPosting(parseInt(btn.dataset.id)); });
    });
  }

  async function loadStats() {
    try {
      var resp = await api("/api/v1/enterprise/employment/postings/stats");
      if (!resp.ok) throw new Error("load failed");
      var data = await resp.json();
      $("#empContent").innerHTML =
        '<div class="subsystem-metrics" style="margin-bottom:12px"><div class="subsystem-metric"><strong>' + (data.total || 0) + '</strong><span>岗位总数</span></div></div>' +
        '<div class="internal-card"><div class="card-header"><div class="card-title">按职位类别</div></div><div class="card-body">' + kvTable(data.by_category || {}, catLabel) + '</div></div>' +
        '<div class="internal-card" style="margin-top:12px"><div class="card-header"><div class="card-title">按状态</div></div><div class="card-body">' + kvTable(data.by_status || {}, statusLabel) + '</div></div>' +
        '<div class="internal-card" style="margin-top:12px"><div class="card-header"><div class="card-title">图表</div></div><div class="card-body"><canvas id="empStatsChart" style="max-height:240px;width:100%"></canvas></div></div>';
      setTimeout(function () { drawChart(data); }, 50);
    } catch (e) {
      $("#empContent").innerHTML = '<p style="text-align:center;padding:40px;color:var(--gray)">加载失败</p>';
    }
  }

  function drawChart(data) {
    var canvas = document.getElementById("empStatsChart");
    if (!canvas) return;
    var ctx = canvas.getContext("2d");
    var combined = Object.assign({}, data.by_status || {}, data.by_category || {});
    var labels = Object.keys(combined);
    var values = labels.map(function (k) { return combined[k]; });
    if (!labels.length) return;

    var maxVal = Math.max.apply(null, values.concat([1]));
    var w = Math.max(300, canvas.parentElement.clientWidth - 30);
    var h = 200;
    canvas.width = w;
    canvas.height = h;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";

    var barW = Math.max(14, (w - 60) / labels.length - 10);
    var colors = ["#4dabf7", "#20c997", "#ff922b", "#845ef7", "#f06595", "#339af0", "#94d82d"];

    ctx.strokeStyle = "#eee";
    ctx.lineWidth = 1;
    for (var i = 0; i < 5; i++) {
      var gy = 20 + (h - 50) * i / 4;
      ctx.beginPath(); ctx.moveTo(40, gy); ctx.lineTo(w - 15, gy); ctx.stroke();
    }

    for (var j = 0; j < labels.length; j++) {
      var barH = (values[j] / maxVal) * (h - 70);
      var x = 40 + j * (barW + 10) + (w - 50 - labels.length * (barW + 10)) / 2;
      var by = h - 35 - barH;
      ctx.fillStyle = colors[j % colors.length];
      ctx.fillRect(x, by, barW, barH);
      ctx.fillStyle = "#333";
      ctx.font = "10px system-ui";
      ctx.textAlign = "center";
      ctx.fillText(values[j], x + barW / 2, by - 5);
      ctx.fillStyle = "#666";
      ctx.font = "9px system-ui";
      ctx.fillText(labels[j], x + barW / 2, h - 18);
    }
  }

  function kvTable(obj, labelFn) {
    var rows = Object.keys(obj).map(function (k) { return '<tr><td>' + (labelFn(k) || esc(k)) + '</td><td>' + obj[k] + '</td></tr>'; }).join("");
    return '<table class="data-table"><thead><tr><th>分类</th><th>数量</th></tr></thead><tbody>' + (rows || '<tr><td colspan="2" style="color:var(--gray)">暂无数据</td></tr>') + '</tbody></table>';
  }

  function showCreateForm() {
    editId = null;
    showModal("发布岗位", postingForm({ title: "", company_name: "", position_category: "技术", salary_range: "", location: "", requirements: "", status: "open", contact_info: "", description: "", posted_date: "", deadline: "" }), savePosting);
  }

  async function editPosting(id) {
    try {
      var r = await api("/api/v1/enterprise/employment/postings/" + id);
      var it = await r.json();
      editId = id;
      showModal("编辑岗位", postingForm(it), savePosting);
    } catch (e) { alert("加载失败"); }
  }

  function postingForm(data) {
    return '<div class="form-grid">' +
      '<div class="field"><label>岗位名称</label><input id="sfTitle" value="' + escAttr(data.title || "") + '"></div>' +
      '<div class="field"><label>企业名称</label><input id="sfCompany" value="' + escAttr(data.company_name || "") + '"></div>' +
      '<div class="field"><label>职位类别</label><select id="sfCategory">' + catOptions(data.position_category) + '</select></div>' +
      '<div class="field"><label>薪资范围</label><input id="sfSalary" value="' + escAttr(data.salary_range || "") + '" placeholder="例: 8k-12k"></div>' +
      '<div class="field"><label>工作地点</label><input id="sfLocation" value="' + escAttr(data.location || "") + '"></div>' +
      '<div class="field"><label>状态</label><select id="sfStatus">' + statusOptions(data.status) + '</select></div>' +
      '<div class="field"><label>截止日期</label><input id="sfDeadline" value="' + escAttr(data.deadline || "") + '" placeholder="YYYY-MM-DD"></div>' +
      '<div class="field"><label>联系方式</label><input id="sfContact" value="' + escAttr(data.contact_info || "") + '"></div>' +
      '<div class="field"><label>岗位要求</label><textarea id="sfReqs" rows="3">' + esc(data.requirements || "") + '</textarea></div>' +
      '<div class="field"><label>岗位描述</label><textarea id="sfDesc" rows="2">' + esc(data.description || "") + '</textarea></div>' +
      '</div>';
  }

  async function savePosting() {
    var payload = {
      title: $("#sfTitle").value,
      company_name: $("#sfCompany").value,
      position_category: $("#sfCategory").value,
      salary_range: $("#sfSalary").value || null,
      location: $("#sfLocation").value || null,
      requirements: $("#sfReqs").value || null,
      status: $("#sfStatus").value,
      contact_info: $("#sfContact").value || null,
      description: $("#sfDesc").value || null,
      deadline: $("#sfDeadline").value || null,
    };
    var url = editId ? "/api/v1/enterprise/employment/postings/" + editId : "/api/v1/enterprise/employment/postings";
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
    overlay.id = "epModal";
    overlay.innerHTML = '<div class="modal-content"><div class="modal-header"><h2>' + esc(title) + '</h2><button class="modal-close-btn" id="epModalClose">&times;</button></div>' + bodyHtml + '<div class="modal-actions"><button class="btn" id="epModalCancel">取消</button><button class="btn primary" id="epModalSubmit">保存</button></div></div>';
    document.body.appendChild(overlay);
    function onKey(e) { if (e.key === "Escape") closeModal(); }
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) closeModal(); });
    document.getElementById("epModalClose").onclick = closeModal;
    document.getElementById("epModalCancel").onclick = closeModal;
    document.getElementById("epModalSubmit").onclick = function () { if (_modalCb) _modalCb(); };
  }

  function closeModal() {
    var m = document.getElementById("epModal");
    if (m) m.remove();
    _modalCb = null;
  }

  function $$(sel) { return containerEl.querySelectorAll(sel); }
  function catLabel(c) { return { "技术": "技术", "行政": "行政", "销售": "销售", "其他": "其他" }[c] || c; }
  function catOptions(current) { return ["技术", "行政", "销售", "其他"].map(function (v) { return '<option value="' + v + '"' + (current === v ? " selected" : "") + '>' + v + '</option>'; }).join(""); }
  function statusColor(s) { return { open: "#20c997", closed: "#868e96", filled: "#339af0" }[s] || "#868e96"; }
  function statusLabel(s) { return { open: "在招", closed: "已关闭", filled: "已招满" }[s] || s; }
  function statusOptions(current) { return ["open", "closed", "filled"].map(function (v) { return '<option value="' + v + '"' + (current === v ? " selected" : "") + '>' + statusLabel(v) + '</option>'; }).join(""); }
  function esc(s) { return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  function escAttr(s) { return String(s || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;"); }

  if (typeof window !== "undefined") {
    window.App = window.App || {};
    window.App.views = window.App.views || {};
    window.App.views.employment = { render: render };
  }
})();
