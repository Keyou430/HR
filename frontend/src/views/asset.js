/**
 * Asset subsystem view — Phase 2 implementation.
 * Registered on ``window.App.views.asset``.
 */
(function () {
  "use strict";

  function render(container, config) {
    if (typeof container === "string") container = document.querySelector(container);
    if (!container) return;
    var system = (config && config.system) || { code: "assets", title: "资产系统" };

    container.innerHTML = (
      '<div class="subsystem-view-shell">' +
      '<button class="btn btn-primary" id="assetCreateBtn">+ 新建资产</button></div>' +
      '<div id="assetStats" class="subsystem-metrics" style="margin-bottom:16px"></div>' +
      '<div id="assetTableContainer"><p style="text-align:center;padding:40px;color:var(--gray)">加载中...</p></div>' +
      '</div>'
    );

    loadAssetData();
    document.getElementById("assetCreateBtn").onclick = showCreateForm;
  }

  var apiBase = window.COLLAB_API_BASE_URL || (window.location.protocol === "file:" ? "http://localhost:8000" : "");

  async function api(path, opts) {
    opts = opts || {};
    var headers = opts.headers || {};
    if (!(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
    var token = (window.App && window.App._authToken) || (window.__auth && window.__auth.getToken && window.__auth.getToken());
    if (token) headers["Authorization"] = "Bearer " + token;
    return fetch(apiBase + path, Object.assign({}, opts, { headers: headers }));
  }

  async function loadAssetData() {
    try {
      var [itemsResp, statsResp] = await Promise.all([
        api("/api/v1/enterprise/assets/items"),
        api("/api/v1/enterprise/assets/stats"),
      ]);
      var items = itemsResp.ok ? (await itemsResp.json()).items || [] : [];
      var stats = statsResp.ok ? await statsResp.json() : { total: 0, by_status: {}, by_category: {}, borrowed_count: 0 };
      renderStats(stats);
      renderTable(items);
    } catch (e) {
      document.getElementById("assetTableContainer").innerHTML = '<p style="text-align:center;padding:40px;color:var(--gray)">加载失败，请重试</p>';
    }
  }

  function renderStats(stats) {
    document.getElementById("assetStats").innerHTML =
      '<div class="subsystem-metric"><strong>' + (stats.total || 0) + '</strong><span>资产总数</span></div>' +
      '<div class="subsystem-metric"><strong>' + (stats.by_status?.available || 0) + '</strong><span>可用</span></div>' +
      '<div class="subsystem-metric"><strong>' + (stats.borrowed_count || 0) + '</strong><span>借出</span></div>' +
      '<div class="subsystem-metric"><strong>' + (stats.by_category ? Object.keys(stats.by_category).length : 0) + '</strong><span>分类</span></div>';
  }

  function renderTable(items) {
    if (!items.length) {
      document.getElementById("assetTableContainer").innerHTML = '<p style="text-align:center;padding:40px;color:var(--gray)">暂无资产</p>';
      return;
    }
    var html = '<table class="subsystem-record-table"><thead><tr><th>编号</th><th>名称</th><th>分类</th><th>位置</th><th>状态</th><th>保管人</th><th>操作</th></tr></thead><tbody>';
    items.forEach(function (t) {
      html += '<tr><td>' + esc(t.asset_code || "-") + '</td><td>' + esc(t.name) + '</td><td>' + esc(t.category || "-") + '</td><td>' + esc(t.location || "-") + '</td><td>' + statusBadge(t.status) + '</td><td>' + esc(t.custodian || "-") + '</td><td>' + actionButtons(t) + '</td></tr>';
    });
    html += '</tbody></table>';
    document.getElementById("assetTableContainer").innerHTML = html;
    bindActionButtons();
  }

  function statusBadge(status) {
    var colors = { available: "#5cb85c", borrowed: "#f0ad4e", scrapped: "#999" };
    return '<span style="padding:2px 8px;border-radius:4px;font-size:12px;background:' + (colors[status] || "#999") + ';color:white">' + esc(status || "-") + '</span>';
  }

  function actionButtons(item) {
    var btns = "";
    if (item.status === "available") btns += '<button class="btn btn-sm" data-action="borrow" data-id="' + item.id + '">借用</button>';
    return btns || '<span style="color:var(--gray);font-size:12px">-</span>';
  }

  function bindActionButtons() {
    document.querySelectorAll("[data-action]").forEach(function (btn) {
      btn.onclick = function () {
        var action = this.dataset.action;
        var id = parseInt(this.dataset.id);
        if (action === "borrow") showBorrowForm(id);
      };
    });
  }

  function showCreateForm() {
    showModal("新建资产",
      '<form id="assetForm"><div class="form-grid"><div class="field"><label>资产编号</label><input name="asset_code" required maxlength="128"></div><div class="field"><label>名称</label><input name="name" required maxlength="255"></div><div class="field"><label>分类</label><input name="category" required maxlength="128"></div><div class="field"><label>位置</label><input name="location" required maxlength="255"></div><div class="field"><label>保管人</label><input name="custodian" maxlength="128"></div></div></form>',
      async function () {
        var fd = new FormData(document.getElementById("assetForm"));
        var payload = {}; fd.forEach(function (v, k) { payload[k] = v; });
        var resp = await api("/api/v1/enterprise/assets/items", { method: "POST", body: JSON.stringify(payload) });
        if (resp.ok) { closeModal(); loadAssetData(); }
        else { var e = await resp.json(); alert(e.detail || "创建失败"); }
      }
    );
  }

  function showBorrowForm(id) {
    showModal("借用资产",
      '<form id="assetForm"><div class="form-grid"><div class="field"><label>预计归还日期</label><input name="expected_return_date" type="date"></div></div></form>',
      async function () {
        var dateVal = document.getElementById("assetForm").querySelector("input").value;
        var body = dateVal ? JSON.stringify({ expected_return_date: dateVal }) : "{}";
        var resp = await api("/api/v1/enterprise/assets/items/" + id + "/borrow", { method: "POST", body: body });
        if (resp.ok) { closeModal(); loadAssetData(); }
        else { var e = await resp.json(); alert(e.detail || "借用失败"); }
      }
    );
  }

  var _modalCb = null;
  function showModal(title, bodyHtml, cb) {
    _modalCb = cb;
    var overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.id = "assetModal";
    overlay.innerHTML = '<div class="modal-content"><div class="modal-header"><h2>' + esc(title) + '</h2><button class="modal-close-btn" id="assetModalClose">&times;</button></div>' + bodyHtml + '<div class="modal-actions"><button class="btn" id="assetModalCancel">取消</button><button class="btn primary" id="assetModalSubmit">确认</button></div></div>';
    document.body.appendChild(overlay);
    function onKey(e) { if (e.key === "Escape") closeModal(); }
    document.addEventListener("keydown", onKey);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) closeModal(); });
    document.getElementById("assetModalClose").onclick = closeModal;
    document.getElementById("assetModalCancel").onclick = closeModal;
    document.getElementById("assetModalSubmit").onclick = function () { if (_modalCb) _modalCb(); };
  }

  function closeModal() {
    var m = document.getElementById("assetModal");
    if (m) m.remove();
    _modalCb = null;
  }

  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

  if (typeof window !== "undefined") {
    window.App = window.App || {};
    window.App.views = window.App.views || {};
    window.App.views.asset = { render: render };
  }
})();
