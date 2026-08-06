    const viewStorageKey = "collab-active-view";
    const taskStorageKey = "collab-workspace-tasks";
    const pendingDeletesStorageKey = "collab-pending-task-deletes";
    const eventStorageKey = "collab-calendar-events";
    const embedStorageKey = "collab-embed-urls";
    const chatSessionsStorageKey = "collab-chat-sessions";
    const profileStorageKey = "collab-portal-profile";
    const newsSubsStorageKey = "collab-news-subs";
    const serviceSubsStorageKey = "collab-service-subs";
    const lastUserIdKey = "collab-last-user-id";

    // ── User-scoped localStorage helpers ──────────────────────────────
    function _scopedKey(baseKey) {
      var uid = (window.App && window.App._authUserId) || null;
      if (!uid) {
        // Fallback: read last-user-id marker so page-reload (before login) can
        // still find the previous session's scoped data.
        try { uid = window.localStorage.getItem(lastUserIdKey); } catch (e) {}
      }
      return uid ? baseKey + ":" + uid : baseKey;
    }

    function _saveScoped(key, value) {
      try { window.localStorage.setItem(_scopedKey(key), value); } catch (e) { /* quota exceeded — degrade gracefully */ }
    }

    function _loadScoped(key, fallback) {
      try {
        var raw = window.localStorage.getItem(_scopedKey(key));
        return raw !== null ? raw : fallback;
      } catch (e) { return fallback; }
    }

    function _removeScoped(key) {
      try { window.localStorage.removeItem(_scopedKey(key)); } catch (e) { /* ignore */ }
    }
    const defaultEmbedUrls = {
      feishu: "https://www.feishu.cn/",
      dingtalk: "https://www.dingtalk.com/"
    };
    const apiBaseUrl = window.COLLAB_API_BASE_URL || (window.location.protocol === "file:" ? "http://localhost:8000" : "");
    const authBaseUrl = apiBaseUrl + "/api/v1/auth";
    const validViews = new Set(["workspace", "portal", "subsystem", "notice-center", "document-center", "resource-center", "service-center", "news-center", "portal-dashboard", "calendar", "knowledge", "feishu", "dingtalk", "admin"]);
    const allNewsSources = [
      { id: "enterprise", label: "企业资讯" }, { id: "operations", label: "运营中心" },
      { id: "knowledge", label: "知识中心" }, { id: "security", label: "安全办公室" },
      { id: "weibo", label: "微博头条" }, { id: "people-daily", label: "人民日报" },
      { id: "xinhua", label: "新华社" }, { id: "cctv", label: "央视新闻" }
    ];
    const allNewsSourcesById = Object.fromEntries(allNewsSources.map(s => [s.id, s.label]));
    const portalNewsItems = [
      { title: "欢迎使用协同门户 — 点击订阅管理配置资讯源", source: "enterprise", tags: ["入门"], date: "" },
    ];
    // ── Auth state (Phase 2) ─────────────────────────────────────
    let _authToken = null;
    let _authUser = null;
    let _authRefreshing = false;
    let _authRefreshPromise = null;
    let _authSyncTimer = null;

    // Sync auth state into the TS module (window.__auth).
    // The module script may not have executed yet when initAuth() completes
    // (type="module" is deferred), so retry a few times if needed.
    function _syncAuthModule(token, user) {
      if (window.__auth && window.__auth._syncState) {
        window.__auth._syncState(token, user);
        return;
      }
      // Module not ready yet — retry with backoff
      var retries = 0;
      var maxRetries = 20; // up to ~2 seconds total
      if (_authSyncTimer) clearTimeout(_authSyncTimer);
      (function retry() {
        if (window.__auth && window.__auth._syncState) {
          window.__auth._syncState(token, user);
          _authSyncTimer = null;
        } else if (retries < maxRetries) {
          retries++;
          _authSyncTimer = setTimeout(retry, 100);
        }
      })();
    }

    function setAuth(token, user) {
      _authToken = token;
      _authUser = user;
      window.App = window.App || {};
      window.App._authToken = token;
      window.App._authUserId = (user && user.id) ? user.id : null;
      // Mark last logged-in user so page reload can scope localStorage correctly
      if (user && user.id) {
        try { window.localStorage.setItem(lastUserIdKey, String(user.id)); } catch (e) {}
      }
      _syncAuthModule(token, user);
      updateAuthUI();
    }

    function clearAuth() {
      _authToken = null;
      _authUser = null;
      window.App = window.App || {};
      window.App._authToken = null;
      window.App._authUserId = null;
      _syncAuthModule(null, null);
      updateAuthUI();
      // ── Clear user-data localStorage to prevent cross-user data leaks ──
      var userDataKeys = [
        taskStorageKey, pendingDeletesStorageKey, eventStorageKey,
        embedStorageKey, chatSessionsStorageKey, profileStorageKey,
        newsSubsStorageKey, serviceSubsStorageKey, lastUserIdKey, viewStorageKey,
      ];
      for (var i = 0; i < userDataKeys.length; i++) {
        try { window.localStorage.removeItem(userDataKeys[i]); } catch (e) { /* ignore */ }
      }
      _resetUserState();
    }

    // ── Reset all user-specific state fields to defaults ──────────────
    function _resetUserState() {
      state.tasks = defaultTasks.map(function (t) { return Object.assign({}, t); });
      state.events = defaultEvents.map(function (e) { return Object.assign({}, e); });
      state.pendingDeletes = new Set();
      state.embedUrls = Object.assign({}, defaultEmbedUrls);
      state.chatSessions = { activeSessionId: null, sessions: [] };
      state.portalProfile = Object.assign({}, defaultProfile);
      state.newsSubscriptions = [];
      state.serviceSubscriptions = [];
      state.notices = [];
      state.documents = [];
      state.resources = [];
      state.news = [];
      state.knowledge = [];
      state.knowledgeImports = [];
      state.portalDashboard = {};
      state.portalPreferences = { favorite_subsystems: [], favorite_services: [], favorite_documents: [], hidden_cards: [], card_order: [], news_subscriptions: [], service_subscriptions: [] };
      state.adminUsers = [];
      state.adminRoles = [];
      state.selectedSubsystem = null;
      state.selectedAsset = null;
    }

    function isSuperAdmin() {
      return !!(_authUser && Array.isArray(_authUser.roles) && _authUser.roles.includes("super_admin"));
    }

    function isLoggedIn() {
      return _authToken !== null && _authUser !== null;
    }

    async function refreshAuthToken() {
      // Single-flight guard: if a refresh is already in progress, wait for it
      if (_authRefreshing && _authRefreshPromise) {
        try { await _authRefreshPromise; } catch (e) { /* result checked below */ }
        if (!_authToken) throw new Error("会话已过期，请重新登录");
        return;
      }
      _authRefreshing = true;
      _authRefreshPromise = (async function() {
        const resp = await fetch(authBaseUrl + "/refresh", {
          method: "POST",
          credentials: "include",
        });
        if (!resp.ok) {
          clearAuth();
          throw new Error("会话已过期，请重新登录");
        }
        const data = await resp.json();
        _authToken = data.access_token;
        window.App = window.App || {};
        window.App._authToken = _authToken;
        _syncAuthModule(_authToken, _authUser);
        return data;
      })();
      try {
        return await _authRefreshPromise;
      } finally {
        _authRefreshing = false;
        _authRefreshPromise = null;
      }
    }

    async function loadCurrentUser() {
      if (!_authToken) return;
      try {
        var resp = await fetch(authBaseUrl + "/me", {
          headers: { Authorization: `Bearer ${_authToken}` },
        });
        if (resp.ok) {
          _authUser = await resp.json();
          window.App = window.App || {};
          window.App._authUserId = (_authUser && _authUser.id) ? _authUser.id : null;
          if (_authUser && _authUser.id) {
            try { window.localStorage.setItem(lastUserIdKey, String(_authUser.id)); } catch (e) {}
          }
          _syncAuthModule(_authToken, _authUser);
          updateAuthUI();
          return;
        }
        // On 401, try to refresh the access token once before giving up
        if (resp.status === 401) {
          try {
            await refreshAuthToken();
            resp = await fetch(authBaseUrl + "/me", {
              headers: { Authorization: `Bearer ${_authToken}` },
            });
            if (resp.ok) {
              _authUser = await resp.json();
              window.App = window.App || {};
              window.App._authUserId = (_authUser && _authUser.id) ? _authUser.id : null;
              if (_authUser && _authUser.id) {
                try { window.localStorage.setItem(lastUserIdKey, String(_authUser.id)); } catch (e) {}
              }
              _syncAuthModule(_authToken, _authUser);
              updateAuthUI();
              return;
            }
          } catch (refreshErr) {
            // Refresh failed — session truly expired
          }
          clearAuth();
        }
      } catch (e) {
        console.warn("Failed to load current user", e);
      }
    }

    async function handleLogin(username, password) {
      const errorEl = document.getElementById("loginError");
      const submitBtn = document.getElementById("loginSubmitBtn");
      errorEl.classList.remove("show");
      submitBtn.disabled = true;
      submitBtn.textContent = "登录中…";

      try {
        const resp = await fetch(authBaseUrl + "/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({ username, password }),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: "登录失败" }));
          errorEl.textContent = err.detail || "登录失败";
          errorEl.classList.add("show");
          submitBtn.disabled = false;
          submitBtn.textContent = "登录";
          return;
        }
        const data = await resp.json();
        setAuth(data.access_token, data.user);

        // Close login overlay
        document.getElementById("loginOverlay").classList.remove("show");

        // Check if must change password
        if (data.must_change_password) {
          showChangePasswordOverlay();
        }
      } catch (e) {
        errorEl.textContent = "网络错误，请稍后再试";
        errorEl.classList.add("show");
      }
      submitBtn.disabled = false;
      submitBtn.textContent = "登录";
    }

    function toggleLoginMode() {
      setLoginMode(_loginMode === "login" ? "register" : "login");
      document.getElementById("loginForm").reset();
      document.getElementById("loginError").classList.remove("show");
    }

    async function handleRegister(username, password, displayName, email) {
      var errorEl = document.getElementById("loginError");
      var submitBtn = document.getElementById("loginSubmitBtn");
      errorEl.classList.remove("show");
      submitBtn.disabled = true;
      submitBtn.textContent = "注册中…";

      try {
        var body = { username: username, password: password };
        if (displayName) body.display_name = displayName;
        if (email) body.email = email;

        var resp = await fetch(authBaseUrl + "/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify(body),
        });
        if (!resp.ok) {
          var err = await resp.json().catch(function() { return { detail: "注册失败" }; });
          errorEl.textContent = err.detail || "注册失败";
          errorEl.classList.add("show");
          submitBtn.disabled = false;
          submitBtn.textContent = "注册";
          return;
        }
        var data = await resp.json();
        setAuth(data.access_token, data.user);

        // Close login overlay
        document.getElementById("loginOverlay").classList.remove("show");

        // Reload page to refresh all data with new auth context
        showToast("注册成功，欢迎 " + data.user.display_name + "！");
        setTimeout(function() { window.location.reload(); }, 800);
      } catch (e) {
        errorEl.textContent = "网络错误，请稍后再试";
        errorEl.classList.add("show");
      }
      submitBtn.disabled = false;
      submitBtn.textContent = "注册";
    }

    async function handleLogout() {
      try {
        await fetch(authBaseUrl + "/logout", {
          method: "POST",
          credentials: "include",
        });
      } catch (e) {
        // ignore
      }
      clearAuth();
      // Reset portal profile to empty defaults on explicit logout only
      if (typeof state !== "undefined" && state.portalProfile) {
        state.portalProfile = { ...defaultProfile };
        saveProfile();
        syncProfileUI();
      }
      document.getElementById("userPopover").classList.remove("show");
    }

    async function handleChangePassword(currentPassword, newPassword) {
      const errorEl = document.getElementById("changePasswordError");
      const submitBtn = document.getElementById("changePasswordSubmitBtn");
      errorEl.classList.remove("show");
      submitBtn.disabled = true;
      submitBtn.textContent = "保存中…";

      try {
        const resp = await fetch(authBaseUrl + "/change-password", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${_authToken}`,
          },
          credentials: "include",
          body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword,
          }),
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: "密码修改失败" }));
          errorEl.textContent = err.detail || "密码修改失败";
          errorEl.classList.add("show");
          submitBtn.disabled = false;
          submitBtn.textContent = "保存新密码";
          return;
        }
        // Explicitly revoke the old refresh cookie via logout before clearing state
        try {
          await fetch(authBaseUrl + "/logout", {
            method: "POST",
            credentials: "include",
          });
        } catch (_) {
          // Best-effort — the old session is already invalidated server-side
        }
        clearAuth();
        document.getElementById("changePasswordOverlay").classList.remove("show");
        showLoginOverlay();
        showToast("密码已修改，请使用新密码登录");
      } catch (e) {
        errorEl.textContent = "网络错误，请稍后再试";
        errorEl.classList.add("show");
      }
      submitBtn.disabled = false;
      submitBtn.textContent = "保存新密码";
    }

    var _loginMode = "login";  // "login" | "register"

    function setLoginMode(mode) {
      _loginMode = mode;
      var isRegister = mode === "register";
      document.getElementById("loginCardTitle").textContent = isRegister ? "注册" : "登录";
      document.getElementById("loginCardSub").textContent = isRegister ? "创建新账号加入协同门户" : "使用你的账号登录协同门户";
      document.getElementById("loginSubmitBtn").textContent = isRegister ? "注册" : "登录";
      document.getElementById("regDisplayNameField").style.display = isRegister ? "" : "none";
      document.getElementById("regEmailField").style.display = isRegister ? "" : "none";
      document.getElementById("loginSwitchText").textContent = isRegister ? "已有账号？" : "没有账号？";
      document.getElementById("loginSwitchBtn").textContent = isRegister ? "去登录" : "注册新账号";
      document.getElementById("loginError").classList.remove("show");
    }

    function showLoginOverlay() {
      setLoginMode("login");
      document.getElementById("loginOverlay").classList.add("show");
      document.getElementById("loginForm").reset();
      setTimeout(function () {
        document.getElementById("loginUsername").focus();
      }, 100);
    }

    function showChangePasswordOverlay() {
      document.getElementById("changePasswordOverlay").classList.add("show");
      document.getElementById("changePasswordError").classList.remove("show");
      document.getElementById("changePasswordForm").reset();
    }

    function updateAuthUI() {
      var loggedIn = isLoggedIn();
      var user = _authUser;

      // Sidebar avatar/name
      var sidebarAvatar = document.getElementById("sidebarAvatar");
      var sidebarName = document.getElementById("sidebarName");
      var userTrigger = document.querySelector(".user-trigger");
      var userAvatar = userTrigger ? userTrigger.querySelector(".avatar") : null;
      var userNameSpan = userTrigger ? userTrigger.querySelector(".avatar + span") : null;

      if (loggedIn && user) {
        var initial = user.display_name ? user.display_name.charAt(0) : "?";
        if (sidebarAvatar) sidebarAvatar.textContent = initial;
        if (sidebarName) sidebarName.textContent = user.display_name;
        if (userAvatar) userAvatar.textContent = initial;
        if (userNameSpan) userNameSpan.textContent = user.display_name;
        document.body.classList.remove("auth-guest");

        // Sync portal profile card with auth user data
        var profileChanged = false;
        if (state.portalProfile.name !== (user.display_name || user.username || "")) {
          state.portalProfile.name = user.display_name || user.username || "";
          profileChanged = true;
        }
        if (state.portalProfile.email !== (user.email || "")) {
          state.portalProfile.email = user.email || "";
          profileChanged = true;
        }
        if (profileChanged) saveProfile();
        // Always refresh portal card — it may have rendered before auth was ready
        syncProfileUI();
      } else {
        if (sidebarAvatar) sidebarAvatar.textContent = "?";
        if (sidebarName) sidebarName.textContent = "未登录";
        if (userAvatar) userAvatar.textContent = "?";
        if (userNameSpan) userNameSpan.textContent = "未登录";
        document.body.classList.add("auth-guest");
      }
      updateAdminUI();
    }

    function updateAdminUI() {
      var tab = document.getElementById("adminTab");
      var show = isSuperAdmin();
      if (tab) tab.hidden = !show;
      if (show) {
        fetchAdminUsers().catch(function(){});
        fetchAdminRoles().catch(function(){});
      }
    }

    // Try to restore session on page load (with retry for slow backend startup).
    // The promise is exposed so auth-dependent API calls can defer until it resolves.
    var _initAuthReady = (async function initAuth() {
      var maxRetries = 3;
      for (var attempt = 0; attempt < maxRetries; attempt++) {
        try {
          var resp = await fetch(authBaseUrl + "/refresh", {
            method: "POST",
            credentials: "include",
          });
          if (resp.ok) {
            var data = await resp.json();
            _authToken = data.access_token;
            await loadCurrentUser();
            break;  // success — exit retry loop
          }
          // 401/403 — no valid session, don't retry
          if (resp.status === 401 || resp.status === 403) break;
        } catch (e) {
          // Network error — may retry after short delay
          if (attempt < maxRetries - 1) {
            await new Promise(function(r) { setTimeout(r, 500 * (attempt + 1)); });
          }
        }
      }
      updateAuthUI();
    })();

    function dateKey(date) {
      return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    }
    const currentDate = new Date();
    const todayKey = dateKey(currentDate);
    function getInitialView() {
      try {
        var scoped = _loadScoped(viewStorageKey, null);
        if (scoped && validViews.has(scoped)) return scoped;
      } catch (e) {}
      const savedView = window.localStorage.getItem(viewStorageKey);
      return validViews.has(savedView) ? savedView : "workspace";
    }
    // Capture which user's localStorage data was loaded at page init.
    // If a different user logs in later, applyPortalBootstrap will discard
    // the stale data before merging server results.
    var _pageLoadUserId = null;
    try { _pageLoadUserId = window.localStorage.getItem(lastUserIdKey); } catch (e) {}
    const defaultTasks = [];
    const defaultEvents = [];
    function getInitialTasks() {
      try {
        // Prefer user-scoped key (defence-in-depth against cross-user leaks)
        var raw = _loadScoped(taskStorageKey, null);
        if (raw) {
          var parsed = JSON.parse(raw);
          if (Array.isArray(parsed)) return parsed.map(function (t) { return Object.assign({}, t, { dueTime: t.dueTime || t.due_time || null }); });
        }
        // Fallback: unscoped key (backward compatibility)
        var savedTasks = JSON.parse(window.localStorage.getItem(taskStorageKey) || "null");
        if (Array.isArray(savedTasks)) return savedTasks.map(function (t) { return Object.assign({}, t, { dueTime: t.dueTime || t.due_time || null }); });
      } catch (error) {
        window.localStorage.removeItem(taskStorageKey);
      }
      return defaultTasks.map(function (task) { return Object.assign({}, task); });
    }

    function getInitialEvents() {
      try {
        var raw = _loadScoped(eventStorageKey, null);
        if (raw) {
          var parsed = JSON.parse(raw);
          if (Array.isArray(parsed)) return parsed;
        }
        const savedEvents = JSON.parse(window.localStorage.getItem(eventStorageKey) || "null");
        if (Array.isArray(savedEvents)) return savedEvents;
      } catch (error) {
        window.localStorage.removeItem(eventStorageKey);
      }
      return defaultEvents.map(function (event) { return Object.assign({}, event); });
    }

    function getInitialEmbedUrls() {
      try {
        var raw = _loadScoped(embedStorageKey, null);
        if (raw) {
          var parsed = JSON.parse(raw);
          if (parsed && typeof parsed === "object") return Object.assign({}, defaultEmbedUrls, parsed);
        }
        const savedUrls = JSON.parse(window.localStorage.getItem(embedStorageKey) || "null");
        return Object.assign({}, defaultEmbedUrls, (savedUrls && typeof savedUrls === "object" ? savedUrls : {}));
      } catch (error) {
        window.localStorage.removeItem(embedStorageKey);
        return Object.assign({}, defaultEmbedUrls);
      }
    }

    function getInitialChatSessions() {
      try {
        var raw = _loadScoped(chatSessionsStorageKey, null);
        if (raw) {
          var parsed = JSON.parse(raw);
          if (parsed && typeof parsed === "object" && Array.isArray(parsed.sessions)) return parsed;
        }
        const saved = JSON.parse(window.localStorage.getItem(chatSessionsStorageKey) || "null");
        if (saved && typeof saved === "object" && Array.isArray(saved.sessions)) return saved;
      } catch (error) {
        window.localStorage.removeItem(chatSessionsStorageKey);
      }
      return { activeSessionId: null, sessions: [] };
    }

    function saveChatSessions() {
      var data = JSON.stringify(state.chatSessions);
      _saveScoped(chatSessionsStorageKey, data);
      try { window.localStorage.setItem(chatSessionsStorageKey, data); } catch (e) {}
    }

    const defaultProfile = { name: "", department: "", email: "", phone: "" };
    function getInitialProfile() {
      try {
        var raw = _loadScoped(profileStorageKey, null);
        if (raw) {
          var parsed = JSON.parse(raw);
          if (parsed && typeof parsed === "object") return Object.assign({}, defaultProfile, parsed);
        }
        const saved = JSON.parse(window.localStorage.getItem(profileStorageKey) || "null");
        return saved && typeof saved === "object" ? Object.assign({}, defaultProfile, saved) : Object.assign({}, defaultProfile);
      } catch (error) { window.localStorage.removeItem(profileStorageKey); return Object.assign({}, defaultProfile); }
    }
    function saveProfile() {
      var data = JSON.stringify(state.portalProfile);
      _saveScoped(profileStorageKey, data);
      try { window.localStorage.setItem(profileStorageKey, data); } catch (e) {}
    }

    const defaultNewsSubs = allNewsSources.slice(0, 4).map(function (s) { return s.id; });
    function getInitialNewsSubs() {
      try {
        var raw = _loadScoped(newsSubsStorageKey, null);
        if (raw) { var parsed = JSON.parse(raw); if (Array.isArray(parsed)) return parsed; }
        const saved = JSON.parse(window.localStorage.getItem(newsSubsStorageKey) || "null");
        if (Array.isArray(saved)) return saved;
      } catch (error) { window.localStorage.removeItem(newsSubsStorageKey); }
      return [].concat(defaultNewsSubs);
    }
    function saveNewsSubs() {
      var data = JSON.stringify(state.newsSubscriptions);
      _saveScoped(newsSubsStorageKey, data);
      try { window.localStorage.setItem(newsSubsStorageKey, data); } catch (e) {}
    }

    function getInitialServiceSubs() {
      try {
        var raw = _loadScoped(serviceSubsStorageKey, null);
        if (raw) { var parsed = JSON.parse(raw); if (Array.isArray(parsed)) return parsed; }
        const saved = JSON.parse(window.localStorage.getItem(serviceSubsStorageKey) || "null");
        if (Array.isArray(saved)) return saved;
      } catch (error) { window.localStorage.removeItem(serviceSubsStorageKey); }
      return ["教职工考勤", "教职工请假", "教职工信息变更管理", "离退休人员管理"];
    }
    function saveServiceSubs() {
      var data = JSON.stringify(state.serviceSubscriptions);
      _saveScoped(serviceSubsStorageKey, data);
      try { window.localStorage.setItem(serviceSubsStorageKey, data); } catch (e) {}
    }

    function getInitialPendingDeletes() {
      try {
        var raw = _loadScoped(pendingDeletesStorageKey, null);
        if (raw) {
          var parsedScoped = JSON.parse(raw);
          if (Array.isArray(parsedScoped)) return new Set(parsedScoped.filter(function (id) { return typeof id === "number"; }));
        }
        const saved = JSON.parse(window.localStorage.getItem(pendingDeletesStorageKey) || "null");
        if (Array.isArray(saved)) return new Set(saved.filter((id) => typeof id === "number"));
      } catch (error) {
        window.localStorage.removeItem(pendingDeletesStorageKey);
      }
      return new Set();
    }

    function savePendingDeletes() {
      var data = JSON.stringify([].concat(state.pendingDeletes ? Array.from(state.pendingDeletes) : []));
      _saveScoped(pendingDeletesStorageKey, data);
      try { window.localStorage.setItem(pendingDeletesStorageKey, data); } catch (e) {}
    }

    async function apiJson(path, options = {}) {
      const isFormData = options.body instanceof FormData;
      const headers = {
        ...(isFormData ? {} : { "Content-Type": "application/json" }),
        ...(options.headers || {})
      };
      // Phase 2: attach access token if available
      if (_authToken) {
        headers["Authorization"] = `Bearer ${_authToken}`;
      }
      let response = await fetch(`${apiBaseUrl}${path}`, {
        ...options,
        headers,
        credentials: "include",
      });

      // Phase 2: on 401, try refresh once
      if (response.status === 401 && _authToken && !options._retried) {
        try {
          await refreshAuthToken();
          headers["Authorization"] = `Bearer ${_authToken}`;
          response = await fetch(`${apiBaseUrl}${path}`, {
            ...options,
            headers,
            credentials: "include",
            _retried: true,
          });
        } catch (e) {
          // refresh failed — let original 401 propagate
        }
      }

      if (!response.ok) throw new Error(await readApiError(response));
      return response.json();
    }

    async function readApiError(response) {
      try {
        const payload = await response.json();
        if (typeof payload.detail === "string") return payload.detail;
        if (payload.detail && typeof payload.detail.message === "string") return payload.detail.message;
      } catch (error) {
        console.warn("API error response was not JSON.", error);
      }
      return `API request failed: ${response.status}`;
    }

    function listItems(payload, fallback = []) {
      return payload && Array.isArray(payload.items) ? payload.items : fallback;
    }

    function mergeTasks(serverPayload, localTasks) {
      if (!serverPayload || !Array.isArray(serverPayload.items)) {
        return { merged: localTasks, localOnly: [], diverged: [] };
      }
      // Normalize snake_case from server to camelCase for frontend
      const normalize = (t) => ({ ...t, dueTime: t.dueTime || t.due_time || null });
      const serverTasks = serverPayload.items.filter((t) => !state.pendingDeletes.has(t.id)).map(normalize);
      const serverMap = new Map(serverTasks.map((t) => [t.id, t]));
      const localMap = new Map(localTasks.map((t) => [t.id, t]));
      const serverIds = new Set(serverTasks.map((t) => t.id));

      // Prefer local version when both exist (preserves offline done-toggle / edits)
      const merged = serverTasks.map((st) => localMap.get(st.id) || st);
      // Track diverged tasks (exist on both, but local state differs from server)
      const diverged = [];
      for (const lt of localTasks) {
        const st = serverMap.get(lt.id);
        if (st && (st.done !== lt.done || st.title !== lt.title || st.tag !== lt.tag || (st.dueTime || null) !== (lt.dueTime || null))) {
          diverged.push(lt);
        }
      }
      // Append local-only tasks (created offline — need to create on server)
      const localOnly = [];
      for (const lt of localTasks) {
        if (!serverIds.has(lt.id)) {
          merged.push(lt);
          localOnly.push(lt);
        }
      }
      return { merged, localOnly, diverged };
    }

    async function syncLocalTasksToServer(localOnly, diverged) {
      // Create local-only tasks on server
      for (const task of localOnly) {
        try {
          const created = await createTaskRemote(task.title, task.tag, task.dueTime);
          const idx = state.tasks.findIndex((t) => t.id === task.id);
          if (idx !== -1) {
            state.tasks[idx] = { ...created, done: task.done };
            if (task.done) {
              await updateTaskRemote(state.tasks[idx]).catch(() => {});
            }
          }
        } catch (e) {
          console.warn("Local task sync deferred.", e);
        }
      }
      // Push diverged local state back to server
      for (const task of diverged) {
        try {
          await updateTaskRemote(task);
        } catch (e) {
          console.warn("Task update sync deferred.", e);
        }
      }
    }

    async function retryPendingDeletes() {
      const ids = [...state.pendingDeletes];
      for (const taskId of ids) {
        try {
          await deleteTaskRemote(taskId);
          state.pendingDeletes.delete(taskId);
        } catch (e) {
          // Remove from pending if server confirms task doesn't exist (404)
          const msg = e && e.message ? e.message : "";
          if (msg.includes("404") || msg.includes("not found")) {
            state.pendingDeletes.delete(taskId);
          }
          // Otherwise keep in set — will retry on next bootstrap
        }
      }
      if (ids.length !== state.pendingDeletes.size) {
        savePendingDeletes();
      }
    }

    async function applyPortalBootstrap(payload) {
      if (!payload || typeof payload !== "object") return;
      // ── Detect user switch: if localStorage data belongs to a different user, ──
      // discard it so stale data from a previous session never leaks in.
      var currentUserId = (_authUser && _authUser.id) ? String(_authUser.id) : null;
      if (currentUserId && _pageLoadUserId && _pageLoadUserId !== currentUserId) {
        // Different user — reset all state before merging server data
        _resetUserState();
        // Clear old user's scoped localStorage data
        var _oldKeys = [taskStorageKey, pendingDeletesStorageKey, eventStorageKey, embedStorageKey, chatSessionsStorageKey, profileStorageKey, newsSubsStorageKey, serviceSubsStorageKey, viewStorageKey];
        for (var _i = 0; _i < _oldKeys.length; _i++) {
          try { window.localStorage.removeItem(_oldKeys[_i]); } catch (e) {}
        }
        // Also clear old user's scoped keys
        try {
          for (var _j = 0; _j < _oldKeys.length; _j++) {
            try { window.localStorage.removeItem(_oldKeys[_j] + ":" + _pageLoadUserId); } catch (e) {}
          }
        } catch (e) {}
      }
      // Update page-load marker so subsequent bootstraps in the same session
      // don't re-trigger the reset.
      _pageLoadUserId = currentUserId;
      if (payload.embed_urls && typeof payload.embed_urls === "object") {
        state.embedUrls = {
          ...state.embedUrls,
          ...Object.fromEntries(
            Object.entries(payload.embed_urls).filter(([, value]) => typeof value === "string" && value.trim())
          )
        };
        saveEmbedUrls();
      }
      const { merged, localOnly, diverged } = mergeTasks(payload.workspace?.tasks, state.tasks);
      state.tasks = merged;
      state.events = listItems(payload.calendar?.events, state.events);
      state.knowledge = listItems(payload.knowledge?.spaces, state.knowledge);
      state.systems = listItems(payload.portal?.systems, state.systems);
      state.services = listItems(payload.portal?.services, state.services);
      state.notices = listItems(payload.workspace?.notices, state.notices);
      state.documents = listItems(payload.workspace?.documents, state.documents);
      state.resources = listItems(payload.workspace?.resources, state.resources);
      state.news = listItems(payload.portal?.news, state.news);
      if (payload.portal?.preferences) state.portalPreferences = payload.portal.preferences;
      if (payload.portal?.dashboard) state.portalDashboard = payload.portal.dashboard;
      if (payload.workspace?.dashboard) state.portalDashboard = { ...state.portalDashboard, ...payload.workspace.dashboard };
      state.newsSubscriptions = state.portalPreferences.news_subscriptions?.length ? state.portalPreferences.news_subscriptions : state.newsSubscriptions;
      state.serviceSubscriptions = state.portalPreferences.service_subscriptions?.length ? state.portalPreferences.service_subscriptions : state.serviceSubscriptions;
      if (Array.isArray(payload.workspace?.shortcuts)) state.shortcuts = payload.workspace.shortcuts;
      // Sync local-only and diverged tasks to server before saving
      if (localOnly.length > 0 || diverged.length > 0) {
        await syncLocalTasksToServer(localOnly, diverged);
      }
      // Retry pending deletes (tasks deleted while server was unreachable)
      if (state.pendingDeletes.size > 0) {
        await retryPendingDeletes();
      }
      saveTasks();
      saveEvents();
      renderTasks();
      renderNotifications();
      renderShortcuts();
      renderWorkspaceAssets();
      renderPortalDashboard();
      renderWorkbenchSchedule();
      renderPortal();
      renderCalendar();
      renderKnowledge();
      renderEmbeds();
    }

    async function fetchPortalBootstrap() {
      try {
        const payload = await apiJson("/api/v1/portal/bootstrap");
        await applyPortalBootstrap(payload);
      } catch (error) {
        console.warn("Portal bootstrap unavailable; using local defaults.", error);
      }
    }

    const state = {
      activeView: getInitialView(),
      month: currentDate.getMonth(),
      year: currentDate.getFullYear(),
      selectedScheduleDate: todayKey,
      taskFilter: "todo",
      kbFilter: "all",
      editingEventIndex: null,
      events: getInitialEvents(),
      tasks: getInitialTasks(),
      pendingDeletes: getInitialPendingDeletes(),
      shortcuts: [
        ["公告", "通知中心", "app-orange"], ["智能问答", "AI 助手", "app-purple"], ["会议", "会议管理", "app-blue"], ["表单", "流程申请", "app-cyan"], ["轻审批", "审批中心", "app-red"], ["笔记", "我的笔记", "app-orange"], ["汇报", "工作汇报", "app-blue"], ["日历", "日程管理", "app-blue"], ["待办中心", "任务管理", "app-green"], ["融合门户", "门户首页", "app-red"]
      ],
      embedUrls: getInitialEmbedUrls(),
      systems: ["督办系统", "一体化教学云平台", "OA 系统", "网站群", "党建系统", "校友系统", "人事系统", "学工系统", "就业系统", "心理系统", "财务系统", "房产管理系统", "资产管理系统", "数据门户", "报修管理系统"],
      services: ["教职工考勤", "教职工请假", "教职工信息变更管理", "离退休人员管理", "教职工进校", "教职工招聘", "在职教职工工资查询与统计", "在职证明", "因公外出报备申请"],
      notices: [],
      documents: [],
      resources: [],
      news: [],
      portalDashboard: {},
      portalPreferences: { favorite_subsystems: [], favorite_services: [], favorite_documents: [], hidden_cards: [], card_order: [], news_subscriptions: [], service_subscriptions: [] },
      selectedSubsystem: null,
      selectedAsset: null,
      knowledge: [],
      knowledgeImports: [],
      knowledgeSubTab: "qa",
      chatSessions: getInitialChatSessions(),
      isStreaming: false,
      activeAbortController: null,
      portalEditMode: false,
      portalProfile: getInitialProfile(),
      newsSubscriptions: getInitialNewsSubs(),
      serviceSubscriptions: getInitialServiceSubs(),
      _lastOverdueIds: null,
      adminUsers: [],
      adminRoles: []
    };

    const icon = (id, extra = "") => `<svg class="icon ${extra}"><use href="#${id}"></use></svg>`;
    const $ = (selector) => document.querySelector(selector);
    const $$ = (selector) => [...document.querySelectorAll(selector)];
    const moduleSidebar = $("#moduleSidebar");
    const sidebarToggle = $("#sidebarToggle");
    const sidebarResizer = $("#sidebarResizer");

    function showToast(message) {
      const toast = $("#toast");
      toast.textContent = message;
      toast.classList.add("show");
      window.clearTimeout(showToast.timer);
      showToast.timer = window.setTimeout(() => toast.classList.remove("show"), 2200);
    }

    // ── Admin panel ────────────────────────────────────────────────
    var _adminKbUserId = null;
    var _adminPage = 1;
    var _adminPageSize = 15;
    var _adminTotalUsers = 0;
    var _adminSearchTerm = "";

    async function fetchAdminUsers() {
      if (!isSuperAdmin()) return;
      try {
        var params = "?page=" + _adminPage + "&page_size=" + _adminPageSize;
        if (_adminSearchTerm) params += "&search=" + encodeURIComponent(_adminSearchTerm);
        var payload = await apiJson("/api/v1/admin/users" + params);
        state.adminUsers = Array.isArray(payload.items) ? payload.items : [];
        _adminTotalUsers = payload.total || state.adminUsers.length;
        renderAdminUsers();
        renderAdminRoles();
      } catch (e) { console.warn("Admin users fetch failed", e); }
    }

    function renderAdminUsers() {
      var tbody = $("#adminUserTableBody");
      if (!tbody) return;
      var countEl = $("#adminUserCount");
      if (countEl) countEl.textContent = "(" + _adminTotalUsers + " 位用户)";
      if (!state.adminUsers || state.adminUsers.length === 0) {
        tbody.innerHTML = "<tr><td colspan=\"8\" style=\"text-align:center;padding:32px;color:#8a94a6\">" + (_adminSearchTerm ? "无匹配用户" : "暂无用户") + "</td></tr>";
        // Pagination
        var pageInfo = $("#adminPageInfo");
        if (pageInfo) pageInfo.textContent = "共 0 条";
        $("#adminPagePrev").disabled = true;
        $("#adminPageNext").disabled = true;
        return;
      }
      tbody.innerHTML = state.adminUsers.map(function(u) {
        var initial = (u.display_name || u.username || "?").charAt(0);
        var roleChips = u.roles.length > 0
          ? u.roles.map(function(c) { return "<span class=\"role-chip" + (c === "super_admin" ? " admin-chip" : "") + "\">" + escapeHTML(c) + "</span>"; }).join("")
          : "<span style=\"color:#8a94a6\">—</span>";
        var statusHtml = u.is_active
          ? "<span class=\"status-pill active\">启用</span>"
          : "<span class=\"status-pill disabled\">禁用</span>";
        var lastLogin = u.last_login_at
          ? "<span class=\"admin-login-time\" title=\"" + escapeHTML(u.last_login_at) + "\">" + escapeHTML(u.last_login_at.slice(0, 16).replace("T", " ")) + "</span>"
          : "<span style=\"color:#8a94a6\">从未登录</span>";
        var toggleLabel = u.is_active ? "禁用" : "启用";
        var toggleClass = u.is_active ? "btn-action-danger" : "btn-action-success";
        return "<tr>" +
          "<td><span class=\"admin-avatar\">" + escapeHTML(initial) + "</span></td>" +
          "<td><strong>" + escapeHTML(u.username) + "</strong></td>" +
          "<td>" + escapeHTML(u.display_name || "—") + "</td>" +
          "<td>" + (u.email ? "<a href=\"mailto:" + escapeHTML(u.email) + "\">" + escapeHTML(u.email) + "</a>" : "—") + "</td>" +
          "<td>" + roleChips + "</td>" +
          "<td>" + statusHtml + "</td>" +
          "<td>" + lastLogin + "</td>" +
          "<td><div class=\"admin-actions\">" +
          "<button class=\"btn btn-sm\" data-admin-reset-pwd=\"" + u.id + "\">重置密码</button>" +
          "<button class=\"btn btn-sm\" data-admin-roles=\"" + u.id + "\">分配角色</button>" +
          "<button class=\"btn btn-sm " + toggleClass + "\" data-admin-toggle=\"" + u.id + "\">" + toggleLabel + "</button>" +
          "</div></td>" +
          "</tr>";
      }).join("");
      // Bind role edit buttons
      $$("#adminUserTableBody [data-admin-roles]").forEach(function(btn) {
        btn.addEventListener("click", function() { openAdminKbAuthModal(parseInt(btn.dataset.adminRoles)); });
      });
      // Bind toggle buttons
      $$("#adminUserTableBody [data-admin-toggle]").forEach(function(btn) {
        btn.addEventListener("click", function() { toggleAdminUserActive(parseInt(btn.dataset.adminToggle)); });
      });
      // Bind reset-password buttons
      $$("#adminUserTableBody [data-admin-reset-pwd]").forEach(function(btn) {
        btn.addEventListener("click", function() { openAdminResetPwdModal(parseInt(btn.dataset.adminResetPwd)); });
      });

      // ── Pagination ──────────────────────────────────────────
      var totalPages = Math.max(1, Math.ceil(_adminTotalUsers / _adminPageSize));
      var pageInfo = $("#adminPageInfo");
      if (pageInfo) {
        var start = (_adminPage - 1) * _adminPageSize + 1;
        var end = Math.min(_adminPage * _adminPageSize, _adminTotalUsers);
        pageInfo.textContent = "显示 " + start + "-" + end + "，共 " + _adminTotalUsers + " 条";
      }
      $("#adminPagePrev").disabled = _adminPage <= 1;
      $("#adminPageNext").disabled = _adminPage >= totalPages;
    }

    async function fetchAdminRoles() {
      try {
        var payload = await apiJson("/api/v1/admin/roles");
        state.adminRoles = Array.isArray(payload.items) ? payload.items : [];
        renderAdminRoles();
      } catch (e) { console.warn("Admin roles fetch failed", e); }
    }

    function renderAdminRoles() {
      var container = $("#adminRoleList");
      if (!container) return;
      if (!state.adminRoles || state.adminRoles.length === 0) {
        container.innerHTML = "<div style=\"padding:20px;text-align:center;color:#8a94a6\">暂无角色数据</div>";
        return;
      }
      container.innerHTML = state.adminRoles.map(function(role) {
        var kbPerms = (role.permissions || []).filter(function(p) { return p.startsWith("kb:"); });
        var otherPerms = (role.permissions || []).filter(function(p) { return !p.startsWith("kb:"); });
        var userCount = (state.adminUsers || []).filter(function(u) { return u.roles && u.roles.includes(role.code); }).length;
        var permSummary = [];
        if (kbPerms.length > 0) permSummary.push("<span class=\"role-perm-tag kb\">知识库:" + kbPerms.length + "项</span>");
        if (otherPerms.length > 0) permSummary.push("<span class=\"role-perm-tag\">其他:" + otherPerms.length + "项</span>");
        if (permSummary.length === 0) permSummary.push("<span class=\"role-perm-tag none\">无权限</span>");
        return "<div class=\"admin-role-item\">" +
          "<div class=\"admin-role-left\"><span class=\"role-chip" + (role.code === "super_admin" ? " admin-chip" : "") + "\" style=\"font-size:12px\">" + escapeHTML(role.code) + "</span></div>" +
          "<div class=\"admin-role-body\"><strong>" + escapeHTML(role.name) + "</strong>" +
          (role.description ? "<span class=\"admin-role-desc\">" + escapeHTML(role.description) + "</span>" : "") +
          "<span class=\"admin-role-meta\">" + permSummary.join("") + " · " + userCount + " 位用户</span></div>" +
          "</div>";
      }).join("");
    }

    function openAdminUserModal() {
      $("#adminUserForm").reset();
      $("#adminUserModal").classList.add("show");
    }

    function closeAdminUserModal() {
      $("#adminUserModal").classList.remove("show");
    }

    async function createAdminUser(event) {
      event.preventDefault();
      var username = $("#adminUsername").value.trim();
      var password = $("#adminPassword").value;
      var displayName = $("#adminDisplayName").value.trim() || null;
      var email = $("#adminEmail").value.trim() || null;
      var isAdmin = $("#adminIsAdmin").value === "admin";
      if (!username || !password) return;
      if (password.length < 8) { showToast("密码至少 8 位"); return; }
      try {
        await apiJson("/api/v1/admin/users", {
          method: "POST",
          body: JSON.stringify({ username: username, password: password, display_name: displayName, email: email, is_admin: isAdmin })
        });
        closeAdminUserModal();
        showToast("账号已创建");
        fetchAdminUsers();
      } catch (e) { showToast(e.message || "创建失败"); }
    }

    async function toggleAdminUserActive(userId) {
      var user = (state.adminUsers || []).find(function(u) { return u.id === userId; });
      if (!user) return;
      var newActive = !user.is_active;
      var actionLabel = newActive ? "启用" : "禁用";
      if (!window.confirm("确认" + actionLabel + "账号 " + user.username + "？")) return;
      try {
        await apiJson("/api/v1/admin/users/" + userId + "/status", {
          method: "PATCH",
          body: JSON.stringify({ is_active: newActive })
        });
        showToast("账号已" + actionLabel);
        fetchAdminUsers();
      } catch (e) { showToast(e.message || "操作失败"); }
    }

    async function openAdminKbAuthModal(userId) {
      var user = (state.adminUsers || []).find(function(u) { return u.id === userId; });
      if (!user) return;
      _adminKbUserId = userId;
      $("#adminKbAuthUserName").textContent = user.display_name || user.username;
      if (!state.adminRoles || state.adminRoles.length === 0) await fetchAdminRoles();
      var roleList = $("#adminKbAuthRoleList");
      var userRoles = user.roles || [];
      roleList.innerHTML = (state.adminRoles || []).map(function(role) {
        var allPerms = role.permissions || [];
        // Show a summary of all permissions — group by resource for readability
        var permGroups = {};
        allPerms.forEach(function(p) {
          var resource = p.split(":")[0];
          if (!permGroups[resource]) permGroups[resource] = [];
          permGroups[resource].push(p);
        });
        var permSummary = Object.keys(permGroups).sort().map(function(res) {
          return "<span class=\"role-perm-tag\">" + escapeHTML(res) + ":" + permGroups[res].length + "项</span>";
        }).join(" ");
        if (!permSummary) permSummary = "<span class=\"role-perm-tag none\">无权限</span>";
        var checked = userRoles.includes(role.code) ? " checked" : "";
        return "<label style=\"display:flex;align-items:flex-start;gap:8px;padding:8px 0;border-bottom:1px solid var(--line);cursor:pointer\">" +
          "<input type=\"checkbox\" value=\"" + escapeHTML(role.code) + "\"" + checked + " style=\"margin-top:2px;flex-shrink:0\">" +
          "<div style=\"min-width:0\"><strong>" + escapeHTML(role.name) + "</strong> <span style=\"color:var(--subtle);font-size:11px\">(" + escapeHTML(role.code) + ")</span>" +
          (role.description ? "<br><span style=\"font-size:11px;color:var(--muted)\">" + escapeHTML(role.description) + "</span>" : "") +
          "<br><span style=\"font-size:11px\">" + permSummary + "</span></div></label>";
      }).join("");
      $("#adminKbAuthModal").classList.add("show");
    }

    function closeAdminKbAuthModal() {
      $("#adminKbAuthModal").classList.remove("show");
      _adminKbUserId = null;
    }

    // ── Admin: reset password modal ────────────────────────────────────
    var _adminResetPwdUserId = null;

    function openAdminResetPwdModal(userId) {
      var user = state.adminUsers.find(function(u) { return u.id === userId; });
      if (!user) return;
      _adminResetPwdUserId = userId;
      // Reset to step 1
      $("#adminResetPwdStep1").removeAttribute("hidden");
      $("#adminResetPwdStep2").setAttribute("hidden", "");
      $("#adminResetPwdConfirmBtn").style.display = "";
      $("#adminResetPwdDoneBtn").setAttribute("hidden", "");
      $("#adminResetPwdCancelBtn").style.display = "";
      $("#adminResetPwdUserName").textContent = user.display_name || user.username;
      $("#adminPwdModeAuto").checked = true;
      $("#adminResetPwdCustomField").style.display = "none";
      $("#adminResetPwdInput").value = "";
      $("#adminResetPwdOutput").textContent = "";
      $("#adminResetPwdOutputUser").textContent = "";
      $("#adminResetPwdModal").classList.add("show");

      // Radio toggle for custom password field
      $("#adminPwdModeAuto").onchange = function() {
        $("#adminResetPwdCustomField").style.display = "none";
      };
      $("#adminPwdModeCustom").onchange = function() {
        $("#adminResetPwdCustomField").style.display = "";
      };

      // Confirm button handler
      $("#adminResetPwdConfirmBtn").onclick = function() { resetAdminPassword(); };

      // Copy button handler
      $("#adminResetPwdCopyBtn").onclick = function() {
        var pwd = $("#adminResetPwdOutput").textContent;
        if (pwd && navigator.clipboard) {
          navigator.clipboard.writeText(pwd).then(function() {
            showToast("密码已复制到剪贴板");
          }).catch(function() {
            showToast("复制失败，请手动选择复制");
          });
        }
      };

      // Done button handler
      $("#adminResetPwdDoneBtn").onclick = function() { closeAdminResetPwdModal(); };
    }

    async function resetAdminPassword() {
      if (!_adminResetPwdUserId) return;
      var isAuto = $("#adminPwdModeAuto").checked;
      var customPwd = "";
      if (!isAuto) {
        customPwd = $("#adminResetPwdInput").value.trim();
        if (customPwd.length < 8) {
          showToast("密码至少需要 8 位字符");
          return;
        }
      }
      try {
        var body = isAuto ? {} : { password: customPwd };
        var data = await apiJson("/api/v1/admin/users/" + _adminResetPwdUserId + "/reset-password", {
          method: "POST",
          body: JSON.stringify(body)
        });
        // Switch to step 2
        $("#adminResetPwdStep1").setAttribute("hidden", "");
        $("#adminResetPwdStep2").removeAttribute("hidden");
        $("#adminResetPwdOutputUser").textContent = data.username;
        $("#adminResetPwdOutput").textContent = data.password;
        $("#adminResetPwdConfirmBtn").style.display = "none";
        $("#adminResetPwdDoneBtn").removeAttribute("hidden");
        $("#adminResetPwdCancelBtn").style.display = "none";
        showToast("密码已重置");
      } catch (e) {
        showToast(e.message || "密码重置失败");
      }
    }

    function closeAdminResetPwdModal() {
      $("#adminResetPwdModal").classList.remove("show");
      // Clear sensitive data from DOM
      $("#adminResetPwdOutput").textContent = "";
      $("#adminResetPwdOutputUser").textContent = "";
      $("#adminResetPwdInput").value = "";
      _adminResetPwdUserId = null;
    }

    async function saveAdminKbAuth() {
      if (!_adminKbUserId) return;
      var checked = [];
      $$("#adminKbAuthRoleList input:checked").forEach(function(cb) { checked.push(cb.value); });
      try {
        await apiJson("/api/v1/admin/users/" + _adminKbUserId + "/roles", {
          method: "PUT",
          body: JSON.stringify({ role_codes: checked })
        });
        closeAdminKbAuthModal();
        showToast("角色已更新");
        fetchAdminUsers().then(function() { renderAdminRoles(); });
      } catch (e) { showToast(e.message || "授权失败"); }
    }

    // ═══════════════════════════════════════════════════════════════
    // Phase 6: Admin sub-tabs + Audit / Sessions / Anomalies
    // ═══════════════════════════════════════════════════════════════

    var _adminSubTab = "users";
    var _adminAuditPage = 1;
    var _adminAIQueryPage = 1;
    var _adminSessionPage = 1;

    function switchAdminSubTab(tab) {
      _adminSubTab = tab;
      $$(".admin-subtab").forEach(function(btn) {
        btn.classList.toggle("active", btn.dataset.adminPanel === tab);
      });
      $$(".admin-panel").forEach(function(panel) {
        panel.classList.toggle("active", panel.id === "adminPanel" + tab.charAt(0).toUpperCase() + tab.slice(1));
      });
      if (tab === "users") { fetchAdminUsers(); }
      else if (tab === "audit") { fetchAdminAudit(); }
      else if (tab === "aiquery") { fetchAdminAIQueries(); }
      else if (tab === "sessions") { fetchAdminSessions(); }
      else if (tab === "anomalies") { fetchAdminAnomalies(); }
    }

    // ── Audit logs ──────────────────────────────────────────────

    async function fetchAdminAudit() {
      var params = new URLSearchParams({ page: _adminAuditPage, page_size: 20 });
      var action = $("#adminAuditAction").value.trim();
      var decision = $("#adminAuditDecision").value;
      if (action) params.set("action", action);
      if (decision) params.set("decision", decision);
      try {
        var data = await apiJson("/api/v1/admin/audit?" + params);
        renderAdminAudit(data);
      } catch (e) { /* silently fail */ }
    }

    function renderAdminAudit(data) {
      var tbody = $("#adminAuditTableBody");
      var countEl = $("#adminAuditCount");
      if (!data || !data.items) { tbody.innerHTML = "<tr><td colspan='6' style='padding:20px;text-align:center;color:var(--muted)'>暂无数据</td></tr>"; return; }
      countEl.textContent = data.total + " 条";
      tbody.innerHTML = data.items.map(function(item) {
        var time = (item.created_at || "").replace("T", " ").substring(0, 19);
        var decisionClass = item.decision === "deny" ? "color:var(--red)" : "color:var(--green)";
        return "<tr>" +
          "<td style='white-space:nowrap;font-size:11px'>" + escapeHTML(time) + "</td>" +
          "<td style='font-size:12px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap' title='" + escapeHTML(item.action) + "'>" + escapeHTML(item.action) + "</td>" +
          "<td>" + (item.user_id || "-") + "</td>" +
          "<td style='" + decisionClass + ";font-weight:600'>" + escapeHTML(item.decision) + "</td>" +
          "<td style='font-size:11px;color:var(--muted);max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>" + escapeHTML(item.reason || "") + "</td>" +
          "<td style='font-size:11px;color:var(--subtle)'>" + escapeHTML(item.ip_address || "-") + "</td>" +
          "</tr>";
      }).join("");
      $("#adminAuditPageInfo").textContent = "第 " + _adminAuditPage + " 页 / 共 " + Math.ceil(data.total / 20) + " 页";
      $("#adminAuditPagePrev").disabled = _adminAuditPage <= 1;
      $("#adminAuditPageNext").disabled = _adminAuditPage * 20 >= data.total;
    }

    function adminAuditPrev() { if (_adminAuditPage > 1) { _adminAuditPage--; fetchAdminAudit(); } }
    function adminAuditNext() { _adminAuditPage++; fetchAdminAudit(); }

    // ── AI Query logs ──────────────────────────────────────────

    async function fetchAdminAIQueries() {
      var params = new URLSearchParams({ page: _adminAIQueryPage, page_size: 20 });
      var decision = $("#adminAIQueryDecision").value;
      var risk = $("#adminAIQueryRisk").value;
      if (decision) params.set("decision", decision);
      if (risk) params.set("risk_label", risk);
      try {
        var data = await apiJson("/api/v1/admin/audit/ai-queries?" + params);
        renderAdminAIQueries(data);
      } catch (e) { /* silently fail */ }
    }

    function renderAdminAIQueries(data) {
      var tbody = $("#adminAIQueryTableBody");
      var countEl = $("#adminAIQueryCount");
      if (!data || !data.items) { tbody.innerHTML = "<tr><td colspan='7' style='padding:20px;text-align:center;color:var(--muted)'>暂无数据</td></tr>"; return; }
      countEl.textContent = data.total + " 条";
      tbody.innerHTML = data.items.map(function(item) {
        var time = (item.created_at || "").replace("T", " ").substring(0, 19);
        var decisionClass = item.decision === "blocked" ? "color:var(--red)" : "color:var(--green)";
        return "<tr>" +
          "<td style='white-space:nowrap;font-size:11px'>" + escapeHTML(time) + "</td>" +
          "<td>" + (item.user_id || "-") + "</td>" +
          "<td style='font-size:10px;font-family:monospace;max-width:100px;overflow:hidden;text-overflow:ellipsis'>" + escapeHTML((item.query_hash || "").substring(0, 12)) + "</td>" +
          "<td style='font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap' title='" + escapeHTML(item.query_snippet || "") + "'>" + escapeHTML(item.query_snippet || "") + "</td>" +
          "<td><span style='font-size:10px;padding:2px 5px;border-radius:4px;background:" + (item.risk_label === "PROMPT_INJECTION" ? "var(--red-soft)" : "var(--blue-soft)") + ";color:" + (item.risk_label === "PROMPT_INJECTION" ? "var(--red)" : "var(--blue)") + "'>" + escapeHTML(item.risk_label || "GENERAL") + "</span></td>" +
          "<td style='" + decisionClass + ";font-weight:600'>" + escapeHTML(item.decision) + "</td>" +
          "<td style='font-size:11px'>" + (item.response_time_ms || "-") + "</td>" +
          "</tr>";
      }).join("");
      $("#adminAIQueryPageInfo").textContent = "第 " + _adminAIQueryPage + " 页 / 共 " + Math.ceil(data.total / 20) + " 页";
      $("#adminAIQueryPagePrev").disabled = _adminAIQueryPage <= 1;
      $("#adminAIQueryPageNext").disabled = _adminAIQueryPage * 20 >= data.total;
    }

    function adminAIQueryPrev() { if (_adminAIQueryPage > 1) { _adminAIQueryPage--; fetchAdminAIQueries(); } }
    function adminAIQueryNext() { _adminAIQueryPage++; fetchAdminAIQueries(); }

    // ── Session management ──────────────────────────────────────

    async function fetchAdminSessions() {
      var params = new URLSearchParams({ page: _adminSessionPage, page_size: 20 });
      if ($("#adminSessionActiveOnly").checked) params.set("active_only", "true");
      try {
        var data = await apiJson("/api/v1/admin/sessions?" + params);
        renderAdminSessions(data);
      } catch (e) { /* silently fail */ }
    }

    function renderAdminSessions(data) {
      var tbody = $("#adminSessionTableBody");
      var countEl = $("#adminSessionCount");
      if (!data || !data.items) { tbody.innerHTML = "<tr><td colspan='7' style='padding:20px;text-align:center;color:var(--muted)'>暂无数据</td></tr>"; return; }
      countEl.textContent = data.total + " 个";
      tbody.innerHTML = data.items.map(function(item) {
        var created = (item.created_at || "").replace("T", " ").substring(0, 16);
        var expires = (item.expires_at || "").replace("T", " ").substring(0, 16);
        var statusHtml = item.is_active
          ? "<span style='color:var(--green);font-weight:600'>● 活跃</span>"
          : "<span style='color:var(--muted)'>○ " + (item.revoked_at ? "已撤销" : "已过期") + "</span>";
        return "<tr>" +
          "<td style='font-size:10px;font-family:monospace'>" + escapeHTML((item.id || "").substring(0, 16)) + "</td>" +
          "<td>" + escapeHTML(item.display_name || item.username || "-") + "</td>" +
          "<td style='font-size:11px;font-family:monospace'>" + escapeHTML(item.ip_address || "-") + "</td>" +
          "<td style='font-size:11px'>" + escapeHTML(created) + "</td>" +
          "<td style='font-size:11px'>" + escapeHTML(expires) + "</td>" +
          "<td>" + statusHtml + "</td>" +
          "<td>" + (item.is_active ? "<button class='btn' style='min-height:26px;padding:0 8px;font-size:11px' onclick='revokeAdminSession(\"" + item.id + "\")'>撤销</button>" : "-") + "</td>" +
          "</tr>";
      }).join("");
      $("#adminSessionPageInfo").textContent = "第 " + _adminSessionPage + " 页 / 共 " + Math.ceil(data.total / 20) + " 页";
      $("#adminSessionPagePrev").disabled = _adminSessionPage <= 1;
      $("#adminSessionPageNext").disabled = _adminSessionPage * 20 >= data.total;
    }

    async function revokeAdminSession(sessionId) {
      if (!confirm("确认撤销此会话？用户将被强制登出。")) return;
      try {
        await apiJson("/api/v1/admin/sessions/" + sessionId, { method: "DELETE" });
        showToast("会话已撤销");
        fetchAdminSessions();
      } catch (e) { showToast(e.message || "撤销失败"); }
    }

    function adminSessionPrev() { if (_adminSessionPage > 1) { _adminSessionPage--; fetchAdminSessions(); } }
    function adminSessionNext() { _adminSessionPage++; fetchAdminSessions(); }

    // ── Anomaly statistics ──────────────────────────────────────

    async function fetchAdminAnomalies() {
      try {
        var data = await apiJson("/api/v1/admin/anomalies");
        renderAdminAnomalies(data);
      } catch (e) { /* silently fail */ }
    }

    function renderAdminAnomalies(data) {
      $("#anomTotalUsers").textContent = data.total_users;
      $("#anomActiveUsers").textContent = data.active_users;
      $("#anomDisabledUsers").textContent = data.disabled_users;
      $("#anomActiveSessions").textContent = data.active_sessions;
      $("#anomFailedLogins").textContent = data.recent_failed_logins_24h;
      $("#anom403").textContent = data.recent_403_24h;
      $("#anomAIBlocks").textContent = data.recent_ai_blocks_24h;
      $("#anomInjections").textContent = data.recent_injections_24h;
      // Update badge on anomaly tab
      var totalWarnings = data.recent_failed_logins_24h + data.recent_403_24h + data.recent_ai_blocks_24h + data.recent_injections_24h;
      var badge = $("#adminAnomalyBadge");
      if (totalWarnings > 0) {
        badge.textContent = totalWarnings > 99 ? "99+" : totalWarnings;
        badge.hidden = false;
      } else {
        badge.hidden = true;
      }
    }

    function updatePlatformTime() {
      const now = new Date();
      const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
      const dateText = `${weekdays[now.getDay()]}，${now.getFullYear()} 年 ${now.getMonth() + 1} 月 ${now.getDate()} 日`;
      const timeText = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}:${String(now.getSeconds()).padStart(2, "0")}`;
      const clock = $("#platformClock");
      if (clock) {
        clock.dateTime = now.toISOString();
        clock.textContent = `${dateText} ${timeText}`;
      }
      const summary = $("#workspaceTodaySummary");
      if (summary) summary.textContent = `${dateText} · 这里汇总你今天最常用的信息和任务`;
    }

    function setSidebarCollapsed(collapsed) {
      moduleSidebar.classList.toggle("collapsed", collapsed);
      document.body.classList.toggle("sidebar-collapsed", collapsed);
      sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
      sidebarToggle.setAttribute("aria-label", collapsed ? "展开模块侧边栏" : "收起模块侧边栏");
      sidebarResizer.setAttribute("aria-hidden", String(collapsed));
    }

    function setSidebarWidth(width) {
      const nextWidth = Math.max(180, Math.min(380, width));
      document.documentElement.style.setProperty("--sidebar", `${nextWidth}px`);
      sidebarResizer.setAttribute("aria-valuenow", String(nextWidth));
    }

    function setView(view, opts = {}) {
      if (!validViews.has(view)) return;
      if (view === "admin" && !isSuperAdmin()) view = "workspace";
      state.activeView = view;
      _saveScoped(viewStorageKey, view);
      try { window.localStorage.setItem(viewStorageKey, view); } catch (e) {}
      window.location.hash = view === "workspace" ? "" : view;
      $$(".view").forEach((section) => section.classList.toggle("active", section.id === view));
      $$(".global-tab").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
      updateSidebar(view);
      if (view === "admin") {
        switchAdminSubTab(_adminSubTab);
      }
      if (view === "knowledge") {
        // Sync sidebar sub-link active state with current sub-tab (updateSidebar hardcodes "qa")
        $$("#sidebarContent .side-link").forEach((btn) => {
          if (btn.dataset.kbSubLink) btn.classList.toggle("active", btn.dataset.kbSubLink === state.knowledgeSubTab);
        });
        renderKnowledgeSubTabs();
        renderChatSessions();
        renderChatTranscript();
        updateChatSendButton();
      }
      // Only smooth-scroll to top on user-initiated switches, not initial page load
      if (!opts.isInit) {
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    }

    function scrollToModule(target, button) {
      const section = document.getElementById(target);
      if (!section) return;
      $$("#sidebarContent .side-link").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      section.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function updateSidebar(view) {
      const title = {
        workspace: "工作台",
        portal: "门户首页",
        subsystem: "子系统",
        "notice-center": "公告中心",
        "document-center": "文档中心",
        "resource-center": "资源库",
        "service-center": "服务台",
        "news-center": "资讯中心",
        "portal-dashboard": "经营看板",
        calendar: "日历",
        knowledge: "知识库",
        feishu: "飞书",
        dingtalk: "钉钉",
        admin: "账号管理"
      }[view];
      if (!title) return;
      $("#sidebarTitle").textContent = title;
      const content = {
        workspace: `<div class="side-section">首屏重点</div><button class="side-link active" data-scroll-target="workspace-tasks">${icon("i-check")}<span>待办任务</span></button><button class="side-link" data-scroll-target="workspace-today">${icon("i-grid")}<span>今日概览</span></button><div class="side-section">日常信息</div><button class="side-link" data-scroll-target="workspace-schedule">${icon("i-calendar")}<span>日程</span></button><button class="side-link" data-scroll-target="workspace-notices">${icon("i-message")}<span>公告</span></button><div class="side-section">工作资料</div><button class="side-link" data-scroll-target="workspace-documents">${icon("i-file")}<span>最近文档</span></button><button class="side-link" data-scroll-target="workspace-shortcuts">${icon("i-star")}<span>快捷入口</span></button><button class="side-link" data-scroll-target="workspace-resources">${icon("i-folder")}<span>常用资源</span></button><button class="side-link" data-scroll-target="workspace-assistant">${icon("i-spark")}<span>文档助手</span></button><div class="side-section">工作看板</div><button class="side-link" data-scroll-target="dashboard-overview">${icon("i-chart")}<span>数据概览</span></button><button class="side-link" data-scroll-target="dashboard-shortcuts">${icon("i-star")}<span>快捷卡片</span></button>`,
        portal: `<div class="side-section">门户区块</div><button class="side-link active" data-scroll-target="portal-overview">${icon("i-home")}<span>门户概览</span></button><button class="side-link" data-scroll-target="portal-personal">${icon("i-user")}<span>个人数据</span></button><button class="side-link" data-scroll-target="portal-systems">${icon("i-grid")}<span>信息系统</span></button><button class="side-link" data-scroll-target="portal-services">${icon("i-folder")}<span>服务分类</span></button><button class="side-link" data-scroll-target="portal-statistics">${icon("i-chart")}<span>系统统计</span></button>`,
        calendar: `<div class="side-section">日历区块</div><button class="side-link active" data-scroll-target="calendar-overview">${icon("i-calendar")}<span>日历总览</span></button><button class="side-link" data-scroll-target="calendar-overview">${icon("i-video")}<span>会议与日程</span></button><button class="side-link" data-scroll-target="calendar-overview">${icon("i-user")}<span>联系人与会议室</span></button>`,
        knowledge: `<div class="side-section">功能导航</div><button class="side-link active" data-kb-sub-link="qa">${icon("i-spark")}<span>知识问答</span></button><button class="side-link" data-kb-sub-link="library">${icon("i-folder")}<span>知识库管理</span></button>`,
        subsystem: `<div class="side-section">子系统</div><button class="side-link active" data-scroll-target="subsystemContent">${icon("i-grid")}<span>系统概览</span></button><button class="side-link" data-view-link="portal">${icon("i-home")}<span>返回门户</span></button><div class="side-section">关联内容</div><button class="side-link" data-open-asset-center="services">${icon("i-folder")}<span>关联服务</span></button><button class="side-link" data-open-asset-center="resources">${icon("i-file")}<span>关联资源</span></button>`,
        "notice-center": `<div class="side-section">内容中心</div><button class="side-link active" data-scroll-target="noticeCenterContent">${icon("i-message")}<span>公告列表</span></button><button class="side-link" data-view-link="portal">${icon("i-home")}<span>返回门户</span></button>`,
        "document-center": `<div class="side-section">内容中心</div><button class="side-link active" data-scroll-target="documentCenterContent">${icon("i-file")}<span>文档目录</span></button><button class="side-link" data-view-link="portal">${icon("i-home")}<span>返回门户</span></button>`,
        "resource-center": `<div class="side-section">内容中心</div><button class="side-link active" data-scroll-target="resourceCenterContent">${icon("i-folder")}<span>资源列表</span></button><button class="side-link" data-view-link="portal">${icon("i-home")}<span>返回门户</span></button>`,
        "service-center": `<div class="side-section">服务台</div><button class="side-link active" data-scroll-target="serviceCenterContent">${icon("i-folder")}<span>服务列表</span></button><button class="side-link" data-view-link="portal">${icon("i-home")}<span>返回门户</span></button>`,
        "news-center": `<div class="side-section">资讯中心</div><button class="side-link active" data-scroll-target="newsCenterContent">${icon("i-message")}<span>资讯列表</span></button><button class="side-link" data-view-link="portal">${icon("i-home")}<span>返回门户</span></button>`,
        "portal-dashboard": `<div class="side-section">经营看板</div><button class="side-link active" data-scroll-target="portalDashboardContent">${icon("i-chart")}<span>平台统计</span></button><button class="side-link" data-view-link="portal">${icon("i-home")}<span>返回门户</span></button>`,
        feishu: `<div class="side-section">飞书</div><button class="side-link active" data-scroll-target="feishu-overview">${icon("i-message")}<span>嵌入页面</span></button><button class="side-link" data-scroll-target="feishu-settings">${icon("i-settings")}<span>地址设置</span></button>`,
        dingtalk: `<div class="side-section">钉钉</div><button class="side-link active" data-scroll-target="dingtalk-overview">${icon("i-grid")}<span>嵌入页面</span></button><button class="side-link" data-scroll-target="dingtalk-settings">${icon("i-settings")}<span>地址设置</span></button>`,
        admin: `<div class="side-section">管理功能</div><button class="side-link active" data-admin-sub="users">${icon("i-settings")}<span>用户管理</span></button><button class="side-link" data-admin-sub="audit">${icon("i-file")}<span>审计日志</span></button><button class="side-link" data-admin-sub="aiquery">${icon("i-spark")}<span>AI查询记录</span></button><button class="side-link" data-admin-sub="sessions">${icon("i-lock")}<span>会话管理</span></button><button class="side-link" data-admin-sub="anomalies">${icon("i-chart")}<span>异常统计</span></button>`
      }[view];
      $("#sidebarContent").innerHTML = content;
      $$("#sidebarContent .side-link").forEach((button) => button.addEventListener("click", () => {
        button.title = button.textContent.trim();
        if (button.dataset.kbSubLink) {
          switchKnowledgeSubTab(button.dataset.kbSubLink);
          return;
        }
        if (button.dataset.adminSub) {
          switchAdminSubTab(button.dataset.adminSub);
          return;
        }
        if (button.dataset.viewLink) {
          setView(button.dataset.viewLink);
          return;
        }
        if (button.dataset.openAssetCenter) {
          renderAssetCenter(button.dataset.openAssetCenter);
          return;
        }
        if (button.dataset.scrollTarget) {
          scrollToModule(button.dataset.scrollTarget, button);
        }
      }));
      $$("#sidebarContent .side-link").forEach((button) => {
        button.title = button.textContent.trim();
      });
    }

    function escapeHTML(value) {
      return String(value).replace(/[&<>"']/g, (char) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
      }[char]));
    }

    function saveTasks() {
      var data = JSON.stringify(state.tasks);
      // Save to user-scoped key first, then unscoped as fallback
      _saveScoped(taskStorageKey, data);
      try { window.localStorage.setItem(taskStorageKey, data); } catch (e) {}
    }

    async function createTaskRemote(title, tag, dueTime) {
      return apiJson("/api/v1/tasks", {
        method: "POST",
        body: JSON.stringify({ title, tag, due_time: dueTime || null })
      });
    }

    async function updateTaskRemote(task) {
      return apiJson(`/api/v1/tasks/${task.id}`, {
        method: "PATCH",
        body: JSON.stringify({ title: task.title, tag: task.tag, due_time: task.dueTime || null, done: task.done })
      });
    }

    async function deleteTaskRemote(taskId) {
      return apiJson(`/api/v1/tasks/${taskId}`, { method: "DELETE" });
    }

    async function clearDoneTasksRemote() {
      return apiJson("/api/v1/tasks/clear-done", { method: "POST" });
    }

    function saveEvents() {
      var data = JSON.stringify(state.events);
      _saveScoped(eventStorageKey, data);
      try { window.localStorage.setItem(eventStorageKey, data); } catch (e) {}
    }

    async function createEventRemote(event) {
      return apiJson("/api/v1/calendar/events", {
        method: "POST",
        body: JSON.stringify(event)
      });
    }

    async function updateEventRemote(event) {
      return apiJson(`/api/v1/calendar/events/${event.id}`, {
        method: "PUT",
        body: JSON.stringify({ title: event.title, date: event.date, tone: event.tone })
      });
    }

    async function deleteEventRemote(eventId) {
      return apiJson(`/api/v1/calendar/events/${eventId}`, { method: "DELETE" });
    }

    function renderWorkbenchOverview() {
      const todoCount = state.tasks.filter((task) => !task.done).length;
      const doneCount = state.tasks.filter((task) => task.done).length;
      const todayScheduleCount = state.events.filter((event) => event.date === todayKey).length;
      const todoTarget = $("#overviewTodoCount");
      const doneTarget = $("#overviewDoneCount");
      const totalTarget = $("#overviewTaskCount");
      const scheduleTarget = $("#overviewTodaySchedule");
      const dashboardTodoTarget = $("#dashboardTodoCount");
      if (todoTarget) todoTarget.textContent = todoCount;
      if (doneTarget) doneTarget.textContent = doneCount;
      if (totalTarget) totalTarget.textContent = state.tasks.length;
      if (scheduleTarget) scheduleTarget.textContent = todayScheduleCount;
      if (dashboardTodoTarget) dashboardTodoTarget.textContent = `${todoCount} 项`;
    }

    function renderTasks() {
      const list = $("#taskList");
      const tasks = state.tasks.filter((task) => state.taskFilter === "all" || (state.taskFilter === "done" ? task.done : !task.done));
      $("#todoCount").textContent = state.tasks.filter((task) => !task.done).length;
      list.innerHTML = tasks.length ? tasks.map((task) => `<div class="task-row ${task.done ? "done" : ""}"><input type="checkbox" data-task-id="${task.id}" ${task.done ? "checked" : ""}/><span class="task-title">${escapeHTML(task.title)}</span><span class="task-tag">${escapeHTML(task.tag)}${task.dueTime ? `<span class="task-time">${escapeHTML(task.dueTime)}</span>` : ""}</span><button class="task-delete" type="button" data-delete-task="${task.id}" aria-label="删除任务 ${escapeHTML(task.title)}"><svg class="icon" style="width:14px;height:14px"><use href="#i-close"/></svg></button></div>`).join("") : `<div class="empty-state"><div><div class="empty-illustration"></div><strong>${state.taskFilter === "done" ? "还没有已完成任务" : "暂无待办任务"}</strong><div>${state.taskFilter === "done" ? "完成任务后会显示在这里。" : "当前没有需要处理的任务。"}</div><button class="empty-action" data-toast="${state.taskFilter === "done" ? "暂无已完成任务可查看" : "待办任务已刷新"}">${state.taskFilter === "done" ? "查看任务中心" : "刷新待办"}</button></div></div>`;
      $$("[data-task-id]").forEach((input) => input.addEventListener("change", (event) => {
        const task = state.tasks.find((item) => item.id === Number(event.target.dataset.taskId));
        task.done = event.target.checked;
        saveTasks();
        updateTaskRemote(task).catch((error) => console.warn("Task update stayed local.", error));
        renderTasks();
        renderNotifications();
        showToast(task.done ? "任务已完成" : "任务已恢复为未完成");
      }));
      $$("[data-delete-task]").forEach((button) => button.addEventListener("click", async () => {
        const taskId = Number(button.dataset.deleteTask);
        state.tasks = state.tasks.filter((task) => task.id !== taskId);
        // Track deletion so server tasks don't reappear on next bootstrap
        state.pendingDeletes.add(taskId);
        savePendingDeletes();
        saveTasks();
        try {
          await deleteTaskRemote(taskId);
          state.pendingDeletes.delete(taskId);
          savePendingDeletes();
        } catch (error) {
          console.warn("Task delete stayed local.", error);
        }
        renderTasks();
        renderNotifications();
        showToast("任务已删除");
      }));
      renderWorkbenchOverview();
      bindToasts();
    }

    function getOverdueTasks() {
      const now = new Date();
      const nowSec = now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
      return state.tasks.filter(task => {
        if (task.done || !task.dueTime) return false;
        if (task.tag !== "今天") return false;
        const [h, m] = task.dueTime.split(":").map(Number);
        if (isNaN(h) || isNaN(m)) return false;
        return nowSec > h * 3600 + m * 60;
      });
    }

    function renderNotifications() {
      const overdue = getOverdueTasks();
      const prevIds = state._lastOverdueIds;
      const nowIds = new Set(overdue.map(t => t.id));
      // T7: Use component API for overdue count (server notifications are separate)
      if (window.App && window.App.components && window.App.components.notificationBell) {
        // Don't overwrite server unread count with overdue count;
        // overdue tasks use toast only (see below)
      }
      // Toast only for genuinely new overdue tasks (skip initial load when prevIds is null)
      if (prevIds) {
        overdue.forEach(task => {
          if (!prevIds.has(task.id)) showToast(`⏰ 任务已过期：${task.title}`);
        });
      }
      state._lastOverdueIds = nowIds;
    }

    const assetViews = {
      notices: { view: "notice-center", target: "noticeCenterContent", title: "公告中心", endpoint: "/api/v1/portal/notices", detailKey: "id", nameKey: "title" },
      documents: { view: "document-center", target: "documentCenterContent", title: "文档中心", endpoint: "/api/v1/portal/documents", detailKey: "id", nameKey: "name" },
      resources: { view: "resource-center", target: "resourceCenterContent", title: "资源库", endpoint: "/api/v1/portal/resources", detailKey: "code", nameKey: "title" },
      services: { view: "service-center", target: "serviceCenterContent", title: "服务台", endpoint: "/api/v1/portal/services", detailKey: "code", nameKey: "title" },
      news: { view: "news-center", target: "newsCenterContent", title: "资讯中心", endpoint: "/api/v1/portal/news", detailKey: "id", nameKey: "title" },
    };

    const subsystemWorkbenches = {
      default: {
        title: "业务事项",
        columns: ["事项", "状态", "负责人", "更新时间"],
        records: [],
        related: ["关联公告", "关联文档", "关联资源", "关联服务"],
      },
      supervision: {
        title: "督办事项",
        columns: ["事项", "状态", "责任人", "截止时间"],
        records: [],
        related: ["办理规范", "督办公告", "责任清单"],
      },
      "teaching-cloud": {
        title: "教学运行",
        columns: ["事项", "状态", "负责单位", "更新时间"],
        records: [],
        related: ["教学通知", "课程文档", "教学服务"],
      },
      oa: {
        title: "待办流程",
        columns: ["流程", "状态", "处理人", "更新时间"],
        records: [],
        related: ["办公通知", "流程制度", "常用表单"],
      },
      website: {
        title: "站点发布",
        columns: ["站点事项", "状态", "负责人", "更新时间"],
        records: [],
        related: ["发布规范", "网站公告", "素材资源"],
      },
      party: {
        title: "党建台账",
        columns: ["事项", "状态", "责任组织", "更新时间"],
        records: [],
        related: ["学习资料", "活动公告", "工作手册"],
      },
      alumni: {
        title: "校友关系",
        columns: ["事项", "状态", "负责人", "更新时间"],
        records: [],
        related: ["活动公告", "联络模板", "服务资源"],
      },
      hr: {
        title: "人员服务",
        columns: ["服务事项", "状态", "经办人", "更新时间"],
        records: [],
        related: ["人事制度", "证明模板", "考勤说明"],
      },
      student: {
        title: "学生事务",
        columns: ["事务", "状态", "负责单位", "更新时间"],
        records: [],
        related: ["学生公告", "办事指南", "心理服务"],
      },
      employment: {
        title: "就业服务",
        columns: ["事项", "状态", "负责人", "更新时间"],
        records: [],
        related: ["招聘公告", "就业指导", "数据看板"],
      },
      "mental-health": {
        title: "心理服务",
        columns: ["事项", "状态", "负责单位", "更新时间"],
        records: [],
        related: ["心理资源", "预约说明", "关怀制度"],
      },
      finance: {
        title: "报销单",
        columns: ["财务事项", "状态", "经办人", "更新时间"],
        records: [],
        related: ["财务制度", "报销指南", "预算说明"],
      },
      estate: {
        title: "房间台账",
        columns: ["空间事项", "状态", "管理单位", "更新时间"],
        records: [],
        related: ["用房制度", "报修服务", "空间资料"],
      },
      assets: {
        title: "资产台账",
        columns: ["资产事项", "状态", "负责人", "更新时间"],
        records: [],
        related: ["资产制度", "报修工单", "盘点资料"],
      },
      "data-portal": {
        title: "指标看板",
        columns: ["数据主题", "状态", "归属部门", "更新时间"],
        records: [],
        related: ["经营看板", "数据资源", "指标口径"],
      },
      repair: {
        title: "报修工单",
        columns: ["工单", "状态", "处理人", "更新时间"],
        records: [],
        related: ["报修指南", "资产目录", "服务评价"],
      },
    };

    function normalizeSubsystem(item, index = 0) {
      if (typeof item === "string") {
        return { code: `system-${index + 1}`, name: item, category: "信息系统", description: `${item}的平台内部子系统入口。`, status: "active", entry_type: "internal", owner_department: "综合服务台", owner_name: "综合服务台", support_contact: "综合服务台", icon_tone: ["app-orange","app-purple","app-red","app-blue","app-green"][index % 5], common_actions: [{ label: "查看概览" }], related_resources: [] };
      }
      return { common_actions: [], related_resources: [], icon_tone: "app-blue", status: "active", entry_type: "internal", ...item };
    }

    function normalizeService(item, index = 0) {
      if (typeof item === "string") return { code: `service-${index + 1}`, title: item, category: "服务分类", description: `${item}的办理说明和材料要求。`, status: "active", contact: "综合服务台" };
      return item;
    }

    function normalizeNotice(item, index = 0) {
      if (typeof item === "string") return { id: index + 1, title: item, source: "门户公告", category: "公告", body: item };
      return item;
    }

    function normalizeNews(item, index = 0) {
      if (!item) return { id: index + 1, title: "", source: "资讯中心", category: "资讯", body: "" };
      if (item.id) return item;
      return { id: index + 1, body: item.title || "", published_at: item.date || "", category: (item.tags || [])[0] || "资讯", ...item };
    }

    function renderShortcuts() {
      $("#shortcutList").innerHTML = state.shortcuts.map(([title, desc, tone], index) => `<button class="shortcut" data-shortcut-index="${index}"><span class="app-icon ${tone}">${title.slice(0, 1)}</span><span><strong>${escapeHTML(title)}</strong><small>${escapeHTML(desc)}</small></span></button>`).join("");
      $$("[data-shortcut-index]").forEach((button) => button.addEventListener("click", () => openShortcut(Number(button.dataset.shortcutIndex))));
    }

    function openShortcut(index) {
      const item = state.shortcuts[index];
      if (!item) return;
      const title = item[0];
      const routes = { "公告": "notices", "日历": "calendar", "待办中心": "workspace", "融合门户": "portal", "智能问答": "knowledge", "服务": "services", "表单": "services", "会议": "calendar" };
      if (routes[title] && assetViews[routes[title]]) return renderAssetCenter(routes[title]);
      if (routes[title]) return setView(routes[title]);
      const subsystem = state.systems.map(normalizeSubsystem).find((system) => system.name.includes(title) || title.includes(system.name.slice(0, 2)));
      if (subsystem) return openSubsystem(subsystem.code);
      renderAssetCenter("resources");
    }

    function renderWorkspaceAssets() {
      const noticeList = $("#noticeList");
      if (noticeList) {
        const notices = state.notices.map(normalizeNotice).slice(0, 3);
        noticeList.innerHTML = notices.map((item) => `<button class="feed-item" data-open-asset="notices:${item.id}"><span class="feed-mark"><svg class="icon"><use href="#i-message"/></svg></span><span><span class="feed-title">${escapeHTML(item.title)}</span><span class="feed-meta"><span>${escapeHTML(item.source || "")}</span><span>${escapeHTML(item.category || "公告")}</span></span></span><span class="feed-time">${formatShortDate(item.published_at)}</span></button>`).join("");
      }
      const documentRows = $("#documentRows");
      if (documentRows) {
        documentRows.innerHTML = state.documents.slice(0, 4).map((item) => `<tr data-open-asset="documents:${item.id}"><td><button class="card-link" type="button"><span class="doc-name"><span class="file-type">${escapeHTML(item.file_type || "D")}</span>${escapeHTML(item.name)}</span></button></td><td>${escapeHTML(item.location || "")}</td><td>${escapeHTML(item.owner || "")}</td><td>${formatShortDate(item.updated_at)}</td></tr>`).join("");
      }
      const resourceList = $("#resourceList");
      if (resourceList) {
        resourceList.innerHTML = state.resources.slice(0, 4).map((item) => `<button class="resource-item" data-open-asset="resources:${item.code}"><span class="app-icon ${item.icon_tone || "app-blue"}">${escapeHTML(item.title || "").slice(0, 1)}</span><span><strong>${escapeHTML(item.title)}</strong><small>${escapeHTML(item.description || "")}</small></span></button>`).join("");
      }
      bindAssetOpeners();
      bindAssetCenterOpeners();
    }

    function formatShortDate(value) {
      if (!value) return "";
      const text = String(value);
      if (/^\d{4}-\d{2}-\d{2}/.test(text)) return text.slice(5, 10).replace("-", "/");
      return text;
    }

    async function fetchPortalPreferences() {
      const payload = await apiJson("/api/v1/portal/preferences");
      state.portalPreferences = payload;
      return payload;
    }

    async function savePortalPreferences(nextPreferences = state.portalPreferences) {
      const payload = await apiJson("/api/v1/portal/preferences", { method: "PUT", body: JSON.stringify(nextPreferences) });
      state.portalPreferences = payload;
      return payload;
    }

    async function fetchPortalDashboard() {
      const payload = await apiJson("/api/v1/portal/dashboard");
      state.portalDashboard = payload;
      renderPortalDashboard();
      return payload;
    }

    function renderPortalDashboard() {
      const dashboard = state.portalDashboard || {};
      const workspaceTarget = $("#dashboard-overview");
      if (workspaceTarget) {
        workspaceTarget.innerHTML = `<div class="workspace-metric"><strong>${dashboard.subsystems_total ?? state.systems.length}</strong><span>内部子系统</span></div><div class="workspace-metric"><strong>${dashboard.subsystems_active ?? 0}</strong><span>启用系统</span></div><div class="workspace-metric"><strong id="dashboardTodoCount">${state.tasks.filter((task) => !task.done).length} 项</strong><span>今日待办</span></div><div class="workspace-metric"><strong>${dashboard.visits_7d ?? 0}</strong><span>近 7 日访问</span></div>`;
      }
      const metricTarget = document.querySelector("#portal-statistics .metric-strip");
      if (metricTarget) {
        metricTarget.innerHTML = [
          ["subsystems_total", "内部子系统"],
          ["subsystems_active", "启用系统"],
          ["services_total", "服务事项"],
          ["documents_total", "平台文档"],
          ["visits_7d", "近 7 日访问"],
        ].map(([key, label]) => `<div class="metric"><strong>${dashboard[key] ?? 0}</strong><span>${label}</span></div>`).join("");
      }
      const target = $("#portalDashboardContent");
      if (target) {
        target.innerHTML = `<article class="internal-card"><div class="card-header"><div class="card-title">平台经营统计</div><button class="card-link" id="refreshPortalDashboard">刷新</button></div><div class="card-body"><div class="workspace-metrics"><div class="workspace-metric"><strong>${dashboard.subsystems_total ?? 0}</strong><span>内部子系统</span></div><div class="workspace-metric"><strong>${dashboard.notices_total ?? 0}</strong><span>公告</span></div><div class="workspace-metric"><strong>${dashboard.services_total ?? 0}</strong><span>服务</span></div><div class="workspace-metric"><strong>${dashboard.documents_total ?? 0}</strong><span>文档</span></div></div></div></article>`;
        $("#refreshPortalDashboard")?.addEventListener("click", () => fetchPortalDashboard().catch((error) => showToast(error.message || "看板刷新失败")));
      }
    }

    function renderSubsystems() {
      const matrix = $("#systemMatrix");
      if (!matrix) return;
      matrix.innerHTML = state.systems.map(normalizeSubsystem).map((system) => `<button class="system-item" data-subsystem-code="${escapeHTML(system.code)}"><span class="app-icon ${system.icon_tone}">${escapeHTML(system.name).slice(0, 1)}</span><span><strong>${escapeHTML(system.name)}</strong><small class="status-pill ${escapeHTML(system.entry_type)}">${system.entry_type === "internal" ? "已上线" : system.entry_type === "iframe" ? "外部接入" : "未开通"}</small></span></button>`).join("");
      $$("[data-subsystem-code]").forEach((button) => button.addEventListener("click", () => openSubsystem(button.dataset.subsystemCode)));
    }

    function renderSubsystemAction(action, index = 0) {
      const normalized = typeof action === "string" ? { label: action, kind: "overview" } : action || {};
      const kind = normalized.kind || (index === 0 ? "overview" : "resources");
      const label = normalized.label || "查看概览";
      const iconId = kind === "services" ? "i-folder" : kind === "resources" ? "i-file" : kind === "dashboard" ? "i-chart" : "i-grid";
      return `<button class="subsystem-action" type="button" data-subsystem-action="${escapeHTML(kind)}">${icon(iconId)}${escapeHTML(label)}</button>`;
    }

    const _enterpriseSubsystemCodes = new Set(["repair", "assets", "oa"]);

    async function getSubsystemWorkbench(code) {
      // Phase 2: fetch real enterprise data for repair/assets/oa
      if (_enterpriseSubsystemCodes.has(code)) {
        try {
          var resp = await apiJson("/api/v1/enterprise/subsystems/" + code + "/records");
          if (resp.ok) {
            var data = await resp.json();
            return {
              title: data.title || subsystemWorkbenches[code]?.title || "业务记录",
              columns: data.columns || [],
              records: (data.records || []).map(function (r) {
                return {
                  id: r.id,
                  title: r.title || r.name || "",
                  status: r.status || "",
                  owner: r.assignee || r.custodian || r.current_handler || "",
                  updated: (r.updated_at || "").slice(0, 10),
                  detail: _formatEnterpriseRecordDetail(code, r),
                  _raw: r,
                };
              }),
              metrics: data.metrics || {},
              related: [],
              _enterprise: true,
              _code: code,
            };
          }
        } catch (e) {
          // fall through to local fallback
        }
      }
      return subsystemWorkbenches[code] || subsystemWorkbenches.default;
    }

    function _formatEnterpriseRecordDetail(code, record) {
      if (code === "repair") {
        return "位置: " + (record.location || "-") + " | 优先级: " + (record.priority || "-") + " | 报修人: " + (record.requester_id || "-");
      }
      if (code === "assets") {
        return "编号: " + (record.asset_code || "-") + " | 分类: " + (record.category || "-") + " | 位置: " + (record.location || "-");
      }
      if (code === "oa") {
        return "类型: " + (record.flow_type || "-") + " | 发起人: " + (record.initiator_id || "-");
      }
      return "";
    }

    function subsystemStatusText(status) {
      return status === "active" ? "正常运行" : status === "maintenance" ? "维护中" : "已停用";
    }

    function renderSubsystemMetrics(workbench, system) {
      const records = workbench.records || [];
      const pending = records.filter((record) => /(待|进行|处理|审核|确认|分派|筹备|submitted|processing|pending)/.test(record.status || "")).length;
      const completed = records.filter((record) => /(已|正常|可访问|可办理|可提交|completed|approved|available|rated)/.test(record.status || "")).length;
      var createBtn = "";
      if (workbench._enterprise) {
        var code = workbench._code;
        var label = code === "repair" ? "新建工单" : code === "assets" ? "新建资产" : "新建流程";
        createBtn = '<div class="subsystem-metric"><button class="btn btn-primary btn-sm" id="enterpriseCreateBtn" data-enterprise-code="' + code + '">' + label + '</button></div>';
      }
      return '<div class="subsystem-metrics"><div class="subsystem-metric"><strong>' + records.length + '</strong><span>业务记录</span></div><div class="subsystem-metric"><strong>' + pending + '</strong><span>待处理</span></div><div class="subsystem-metric"><strong>' + completed + '</strong><span>已就绪</span></div><div class="subsystem-metric"><strong>' + subsystemStatusText(system.status) + '</strong><span>运行状态</span></div>' + createBtn + '</div>';
    }

    function renderSubsystemRecordList(workbench) {
      var columns = workbench.columns || subsystemWorkbenches.default.columns;
      var rows = workbench.records || [];
      // Phase 2: use column-based rendering for enterprise subsystems
      if (workbench._enterprise && rows.length > 0) {
        var colKeys = columns.slice(0, 5); // show first 5 columns
        return '<div id="subsystemRecords"><table class="subsystem-record-table"><thead><tr>' + colKeys.map(function (c) { return '<th>' + escapeHTML(c) + '</th>'; }).join("") + '</tr></thead><tbody>' + rows.map(function (record, index) {
          var cells = colKeys.map(function (col) {
            var val = record._raw ? record._raw[col] : record[col];
            if (val === null || val === undefined) val = "-";
            return '<td>' + escapeHTML(String(val)) + '</td>';
          }).join("");
          return '<tr><td><button type="button" data-subsystem-record="' + index + '">' + escapeHTML(record.title) + '</button></td>' + cells + '</tr>';
        }).join("") + '</tbody></table></div>';
      }
      return '<div id="subsystemRecords"><table class="subsystem-record-table"><thead><tr>' + columns.map(function (column) { return '<th>' + escapeHTML(column) + '</th>'; }).join("") + '</tr></thead><tbody>' + rows.map(function (record, index) { return '<tr><td><button type="button" data-subsystem-record="' + index + '">' + escapeHTML(record.title) + '</button></td><td>' + escapeHTML(record.status) + '</td><td>' + escapeHTML(record.owner) + '</td><td>' + escapeHTML(record.updated) + '</td></tr>'; }).join("") + '</tbody></table></div>';
    }

    function renderSubsystemRecordDetail(workbench, index = 0) {
      const record = (workbench.records || [])[index] || (workbench.records || [])[0];
      if (!record) return `<div class="subsystem-record-detail" id="subsystemRecordDetail">暂无业务记录。</div>`;
      return `<div class="subsystem-record-detail" id="subsystemRecordDetail"><strong>${escapeHTML(record.title)}</strong>${escapeHTML(record.detail || "当前业务记录可在本子系统内继续查看。")}</div>`;
    }

    function bindSubsystemRecordOpeners(workbench) {
      $$("[data-subsystem-record]").forEach((button) => {
        button.onclick = () => {
          const target = $("#subsystemRecordDetail");
          if (target) target.outerHTML = renderSubsystemRecordDetail(workbench, Number(button.dataset.subsystemRecord || 0));
        };
      });
      // Phase 2: enterprise create button
      var createBtn = document.getElementById("enterpriseCreateBtn");
      if (createBtn) {
        createBtn.onclick = function () {
          _showEnterpriseCreateForm(createBtn.dataset.enterpriseCode);
        };
      }
    }

    function _showEnterpriseCreateForm(code) {
      var titles = { repair: "新建报修工单", assets: "新建资产", oa: "新建OA流程" };
      var title = titles[code] || "新建";
      var fieldsHtml = "";
      if (code === "repair") {
        fieldsHtml = '<div class="field"><label>标题</label><input name="title" required maxlength="255"></div><div class="field"><label>位置</label><input name="location" required maxlength="255"></div><div class="field"><label>描述</label><textarea name="description" required rows="3"></textarea></div><div class="field"><label>优先级</label><select name="priority"><option value="normal">普通</option><option value="low">低</option><option value="high">高</option><option value="urgent">紧急</option></select></div>';
      } else if (code === "assets") {
        fieldsHtml = '<div class="field"><label>资产编号</label><input name="asset_code" required maxlength="128"></div><div class="field"><label>名称</label><input name="name" required maxlength="255"></div><div class="field"><label>分类</label><input name="category" required maxlength="128"></div><div class="field"><label>位置</label><input name="location" required maxlength="255"></div><div class="field"><label>保管人</label><input name="custodian" maxlength="128"></div>';
      } else if (code === "oa") {
        fieldsHtml = '<div class="field"><label>标题</label><input name="title" required maxlength="255"></div><div class="field"><label>流程类型</label><input name="flow_type" required maxlength="128"></div>';
      }
      var container = document.createElement("div");
      container.className = "modal-overlay";
      container.innerHTML = '<div class="modal-content"><div class="modal-header"><h2>' + title + '</h2><button class="modal-close-btn" id="enterpriseCreateClose">&times;</button></div><form id="enterpriseCreateForm"><div class="form-grid">' + fieldsHtml + '</div><div class="modal-actions"><button type="button" class="btn" id="enterpriseCreateCancel">取消</button><button type="submit" class="btn primary">提交</button></div></form></div>';
      document.body.appendChild(container);
      function close() { container.remove(); document.removeEventListener("keydown", onKey); }
      function onKey(e) { if (e.key === "Escape") close(); }
      document.addEventListener("keydown", onKey);
      container.addEventListener("click", function (e) { if (e.target === container) close(); });
      document.getElementById("enterpriseCreateClose").addEventListener("click", close);
      document.getElementById("enterpriseCreateCancel").addEventListener("click", close);
      document.getElementById("enterpriseCreateForm").addEventListener("submit", async function (e) {
        e.preventDefault();
        var formData = new FormData(e.target);
        var payload = {};
        formData.forEach(function (v, k) { payload[k] = v; });
        var endpoint = "";
        if (code === "repair") endpoint = "/api/v1/enterprise/repair/tickets";
        else if (code === "assets") endpoint = "/api/v1/enterprise/assets/items";
        else if (code === "oa") endpoint = "/api/v1/enterprise/oa/flows";
        try {
          var resp = await apiJson(endpoint, { method: "POST", body: JSON.stringify(payload) });
          if (resp.ok) {
            close();
            showToast("创建成功");
            navigateTo("subsystem", state.selectedSubsystem?.code || code);
          } else {
            var err = await resp.json();
            showToast(err.detail || "创建失败");
          }
        } catch (err) {
          showToast("网络错误");
        }
      });
    }

    function renderSubsystemRelatedPanel(system, workbench) {
      const related = workbench.related?.length ? workbench.related : (system.related_resources || []);
      return `<article class="internal-card subsystem-card"><div class="card-header"><div class="card-title">关联内容</div></div><div class="card-body"><ul class="subsystem-related-list">${related.map((item, index) => `<li><span>${escapeHTML(item)}</span><strong>${index + 1}</strong></li>`).join("")}</ul></div></article>`;
    }

    function handleSubsystemAction(kind) {
      const routes = {
        services: "services",
        resources: "resources",
        documents: "documents",
        notices: "notices",
        news: "news",
      };
      if (routes[kind]) {
        renderAssetCenter(routes[kind]);
        return;
      }
      if (kind === "dashboard") {
        setView("portal-dashboard");
        return;
      }
      const targetId = kind === "records" ? "subsystemRecords" : "subsystemContent";
      document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    async function openSubsystem(code) {
      try {
        const subsystem = await apiJson(`/api/v1/subsystems/${encodeURIComponent(code)}`);
        state.selectedSubsystem = normalizeSubsystem(subsystem);
        apiJson(`/api/v1/subsystems/${encodeURIComponent(code)}/visit`, { method: "POST" }).then((data) => {
          state.portalDashboard = { ...state.portalDashboard, visits_7d: data.visits_7d };
          renderPortalDashboard();
        }).catch(() => {});
        setView("subsystem");       // set view first (updates sidebar generically)
        await renderSubsystemView();      // then override sidebar with menu_items
      } catch (error) {
        showToast(error.message || "子系统暂不可用");
      }
    }

    async function renderSubsystemView() {
      const system = state.selectedSubsystem;
      if (!system) return;
      $("#subsystemTitle").textContent = system.name;
      $("#subsystemSummary").textContent = system.description || "平台内部子系统工作台";
      const menuItems = system.menu_items || [];

      // ── Disabled shell subsystem ─────────────────────────────────────
      if (system.entry_type === "disabled") {
        $("#subsystemContent").innerHTML =
          `<div style="display:flex;align-items:center;justify-content:center;min-height:320px">
            <div style="text-align:center">
              <div style="font-size:48px;margin-bottom:16px">🚧</div>
              <h2 style="margin:0 0 8px">${escapeHTML(system.name)}</h2>
              <p style="color:var(--gray)">该子系统尚未开放，敬请期待。</p>
              <p style="color:var(--gray);font-size:13px">归属：${escapeHTML(system.owner_department || "")}　·　支持：${escapeHTML(system.support_contact || "")}</p>
            </div>
          </div>`;
        renderSubsystemSidebar(system, []);
        return;
      }

      // ── Iframe shell subsystem ───────────────────────────────────────
      if (system.entry_type === "iframe") {
        var embedUrl = system.entry_url || "";
        if (embedUrl) {
          $("#subsystemContent").innerHTML =
            `<iframe src="${escapeHTML(embedUrl)}"
              style="width:100%;height:calc(100vh - 180px);border:none;border-radius:8px"
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
              title="${escapeHTML(system.name)}"></iframe>`;
        } else {
          $("#subsystemContent").innerHTML =
            `<div style="display:flex;align-items:center;justify-content:center;min-height:320px">
              <div style="text-align:center">
                <div style="font-size:48px;margin-bottom:16px">🔗</div>
                <h2 style="margin:0 0 8px">${escapeHTML(system.name)}</h2>
                <p style="color:var(--gray)">该子系统通过外部入口访问。</p>
                <p style="color:var(--gray);font-size:13px">请在管理后台配置入口地址。</p>
              </div>
            </div>`;
        }
        renderSubsystemSidebar(system, []);
        return;
      }

      // ── Dedicated view module ──────────────────────────────────────
      var viewModuleCode = system.code === "assets" ? "asset" : system.code;
      if (window.App && window.App.views && typeof window.App.views[viewModuleCode] === "object" &&
          typeof window.App.views[viewModuleCode].render === "function") {
        window.App.views[viewModuleCode].render($("#subsystemContent"), { system: system });
        renderSubsystemSidebar(system, menuItems);
        return;
      }

      // ── Deep internal subsystem with workbench ───────────────────────
      const workbench = await getSubsystemWorkbench(system.code);
      const actions = system.common_actions?.length ? system.common_actions : [{ label: "查看概览", kind: "overview" }, { label: "关联资源", kind: "resources" }, { label: "关联服务", kind: "services" }];
      $("#subsystemContent").innerHTML = `<div class="subsystem-workbench-layout"><main class="subsystem-main-stack"><article class="internal-card subsystem-card"><div class="card-header"><div class="card-title">${escapeHTML(workbench.title)}</div><span class="status-pill ${escapeHTML(system.status)}">${subsystemStatusText(system.status)}</span></div><div class="card-body"><p class="subsystem-summary-line">${escapeHTML(system.description || "")}</p>${renderSubsystemMetrics(workbench, system)}<div class="subsystem-action-toolbar">${actions.map(renderSubsystemAction).join("")}</div>${renderSubsystemRecordList(workbench)}${renderSubsystemRecordDetail(workbench)}</div></article></main><aside class="subsystem-side-stack"><article class="internal-card subsystem-card"><div class="card-header"><div class="card-title">系统信息</div></div><div class="card-body"><ul class="detail-list"><li><span>权限状态</span><strong>${system.entry_type === "internal" ? "平台内可访问" : "外部入口"}</strong></li><li><span>最近访问</span><strong>${formatShortDate(system.last_visited_at) || "暂无记录"}</strong></li><li><span>分类</span><strong>${escapeHTML(system.category || "")}</strong></li><li><span>归属部门</span><strong>${escapeHTML(system.owner_department || "")}</strong></li><li><span>负责人</span><strong>${escapeHTML(system.owner_name || "")}</strong></li><li><span>支持入口</span><strong>${escapeHTML(system.support_contact || "")}</strong></li></ul></div></article>${renderSubsystemRelatedPanel(system, workbench)}</aside></div>`;

      renderSubsystemSidebar(system, menuItems);

      $$("[data-subsystem-action]").forEach((button) => {
        button.onclick = () => handleSubsystemAction(button.dataset.subsystemAction);
      });
      bindSubsystemRecordOpeners(workbench);
    }

    function renderSubsystemSidebar(system, menuItems) {
      $("#sidebarTitle").textContent = system.name || "子系统";
      var html = "";
      if (menuItems && menuItems.length > 0) {
        for (var s = 0; s < menuItems.length; s++) {
          var section = menuItems[s];
          html += '<div class="side-section">' + escapeHTML(section.section || "") + '</div>';
          var items = section.items || [];
          for (var i = 0; i < items.length; i++) {
            var item = items[i];
            var iconName = item.icon || "i-file";
            html += '<button class="side-link" data-submenu-href="' + escapeHTML(item.href || "") + '"><svg class="icon"><use href="#' + iconName + '"/></svg><span>' + escapeHTML(item.label || item.code || "") + '</span></button>';
          }
        }
        html += '<div class="side-section"></div>';
      }
      html += '<button class="side-link" data-view-link="portal"><svg class="icon"><use href="#i-chevron-left"/></svg><span>返回门户</span></button>';
      $("#sidebarContent").innerHTML = html;

      $$("#sidebarContent .side-link").forEach(function (btn) {
        btn.addEventListener("click", function () {
          if (btn.dataset.viewLink) { setView(btn.dataset.viewLink); return; }
          if (btn.dataset.submenuHref) {
            $$("#sidebarContent .side-link").forEach(function (el) { el.classList.remove("active"); });
            btn.classList.add("active");
            window.location.hash = btn.dataset.submenuHref;
          }
        });
      });
    }

    async function renderAssetCenter(collection) {
      const config = assetViews[collection];
      if (!config) return;
      try {
        const payload = await apiJson(config.endpoint);
        state[collection] = Array.isArray(payload.items) ? payload.items : [];
      } catch (error) {
        console.warn("Portal asset list unavailable.", error);
      }
      const target = document.getElementById(config.target);
      const items = state[collection] || [];
      if (target) {
        target.innerHTML = `<article class="internal-card"><div class="card-header"><div class="card-title">${config.title}</div><button class="card-link" data-refresh-asset-center="${collection}">刷新</button></div><div class="card-body"><div class="asset-grid">${items.map((item, index) => renderAssetItem(collection, item, index)).join("")}</div></div></article><article class="internal-card" id="${collection}Detail"><div class="card-body"><p>选择一项查看详情。</p></div></article>`;
      }
      setView(config.view);
      bindAssetOpeners();
      $$("[data-refresh-asset-center]").forEach((button) => button.addEventListener("click", () => renderAssetCenter(button.dataset.refreshAssetCenter)));
    }

    function renderAssetItem(collection, item, index) {
      const config = assetViews[collection];
      const key = item[config.detailKey] ?? index + 1;
      const title = item[config.nameKey] || item.title || item.name || "";
      const desc = item.description || item.summary || item.body || item.source || item.location || "";
      return `<button class="asset-item" data-open-asset="${collection}:${key}"><strong>${escapeHTML(title)}</strong><p>${escapeHTML(desc).slice(0, 90)}</p><span class="asset-meta"><span>${escapeHTML(item.category || item.location || item.source || "")}</span><span>${formatShortDate(item.updated_at || item.published_at)}</span></span></button>`;
    }

    async function openPortalAsset(collection, key) {
      const config = assetViews[collection];
      if (!config) return;
      let target = document.getElementById(`${collection}Detail`);
      if (!target || state.activeView !== config.view) {
        await renderAssetCenter(collection);
        target = document.getElementById(`${collection}Detail`);
      }
      try {
        state.selectedAsset = await apiJson(`${config.endpoint}/${encodeURIComponent(key)}`);
      } catch (error) {
        showToast(error.message || "内容暂不可用");
        return;
      }
      const item = state.selectedAsset;
      if (target) {
        const title = item[config.nameKey] || item.title || item.name || "";
        const desc = item.body || item.summary || item.description || "";
        target.innerHTML = `<div class="card-header"><div class="card-title">${escapeHTML(title)}</div></div><div class="card-body"><p>${escapeHTML(desc)}</p><ul class="detail-list"><li><span>分类</span><strong>${escapeHTML(item.category || item.location || "")}</strong></li><li><span>负责人</span><strong>${escapeHTML(item.owner || item.contact || item.source || "")}</strong></li><li><span>更新时间</span><strong>${formatShortDate(item.updated_at || item.published_at)}</strong></li></ul></div>`;
      }
    }

    function bindAssetOpeners() {
      $$("[data-open-asset]").forEach((button) => {
        button.onclick = () => {
          const [collection, key] = button.dataset.openAsset.split(":");
          openPortalAsset(collection, key);
        };
      });
    }

    function bindAssetCenterOpeners() {
      $$("[data-open-asset-center]").forEach((button) => {
        button.onclick = () => renderAssetCenter(button.dataset.openAssetCenter);
      });
    }

    function getMonthCells(year, month) {
      const first = new Date(year, month, 1);
      const start = (first.getDay() + 6) % 7;
      const days = new Date(year, month + 1, 0).getDate();
      const prevDays = new Date(year, month, 0).getDate();
      return Array.from({ length: 42 }, (_, index) => {
        const dayIndex = index - start + 1;
        if (dayIndex < 1) return { day: prevDays + dayIndex, muted: true, date: new Date(year, month - 1, prevDays + dayIndex) };
        if (dayIndex > days) return { day: dayIndex - days, muted: true, date: new Date(year, month + 1, dayIndex - days) };
        return { day: dayIndex, muted: false, date: new Date(year, month, dayIndex) };
      });
    }

    function renderMiniCalendar(id) {
      const target = document.getElementById(id);
      if (!target) return;
      const interactive = id === "miniMonth" || id === "portalMonth";
      target.innerHTML = getMonthCells(state.year, state.month).map((cell) => {
        const key = dateKey(cell.date);
        const current = key === todayKey;
        const hasEvent = state.events.some((event) => event.date === key);
        const selected = key === state.selectedScheduleDate;
        const classes = `day ${cell.muted ? "muted" : ""} ${current ? "today" : ""} ${selected ? "selected" : ""} ${hasEvent ? "dot" : ""}`;
        if (!interactive) return `<span class="${classes}">${cell.day}</span>`;
        return `<button class="${classes}" type="button" data-schedule-date="${key}" aria-label="查看 ${key} 日程">${cell.day}</button>`;
      }).join("");
      if (interactive) {
        $$("[data-schedule-date]").forEach((button) => button.addEventListener("click", () => {
          state.selectedScheduleDate = button.dataset.scheduleDate;
          renderPortalSchedule();
          renderWorkbenchSchedule();
        }));
      }
    }

    function formatScheduleDate(key) {
      const date = new Date(`${key}T00:00:00`);
      const weekdays = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];
      return `${date.getMonth() + 1} 月 ${date.getDate()} 日 · ${weekdays[date.getDay()]}`;
    }

    function openEventModal(index = null) {
      state.editingEventIndex = index;
      const eventItem = index === null ? null : state.events[index];
      $("#eventModalTitle").textContent = index === null ? "添加日程" : "编辑日程";
      const deleteButton = $("#eventDeleteButton");
      if (deleteButton) deleteButton.hidden = index === null;
      $("#eventName").value = eventItem ? eventItem.title : "";
      $("#eventDate").value = eventItem ? eventItem.date : state.selectedScheduleDate;
      $("#eventNote").value = "";
      const tone = eventItem ? eventItem.tone : "blue";
      const toneInput = $(`[name="eventTone"][value="${tone}"]`) || $("[name=\"eventTone\"]");
      if (toneInput) toneInput.checked = true;
      $("#eventModal").classList.add("show");
    }

    function renderWorkbenchSchedule() {
      renderMiniCalendar("miniMonth");
      const panel = $("#workspaceSchedulePanel");
      if (!panel) return;
      panel.innerHTML = renderSchedulePanel(true, "暂无日程安排");
      bindScheduleActions(panel);
    }

    function renderPortalSchedule() {
      renderMiniCalendar("portalMonth");
      const panel = $("#portalSchedulePanel");
      if (!panel) return;
      panel.innerHTML = renderSchedulePanel(false, "暂无日程");
      bindScheduleActions(panel);
    }

    function renderSchedulePanel(includeActions, emptyLabel) {
      const events = state.events.map((event, index) => ({ ...event, index })).filter((event) => event.date === state.selectedScheduleDate);
      const actions = includeActions ? `<div class="quick-actions"><button class="quick-action" data-open-modal><svg class="icon"><use href="#i-calendar"/></svg>添加日程</button><button class="quick-action" data-toast="快速会议已准备"><svg class="icon"><use href="#i-video"/></svg>快速会议</button><button class="quick-action" data-toast="进入会议列表"><svg class="icon"><use href="#i-message"/></svg>加入会议</button></div>` : "";
      return `<div class="schedule-date">${formatScheduleDate(state.selectedScheduleDate)}</div>${events.length ? `<div class="schedule-list">${events.map((event) => `<button class="schedule-item ${event.tone}" data-edit-event="${event.index}"><span><strong>${event.title}</strong><span class="schedule-item-meta">${formatScheduleDate(event.date)}</span></span></button>`).join("")}</div>${actions}` : `<div class="schedule-empty"><strong>${emptyLabel}</strong>${actions}${includeActions ? "" : `<div>当前日期没有安排。</div>`}</div>`}`;
    }

    function bindScheduleActions(scope) {
      $$("[data-open-modal]", scope).forEach((element) => {
        element.onclick = () => openEventModal();
      });
      bindEventEditors(scope);
      $$("[data-toast]", scope).forEach((element) => {
        element.onclick = () => showToast(element.dataset.toast);
      });
    }

    function bindEventEditors(scope = document) {
      $$('[data-edit-event]', scope).forEach((element) => {
        element.onclick = () => openEventModal(Number(element.dataset.editEvent));
      });
    }

    function renderPortal() {
      renderPortalProfile();
      renderPortalNews();
      renderSubsystems();
      renderPortalServices();
      renderPortalDashboard();
      renderWorkspaceAssets();
      renderPortalSchedule();
      bindToasts();
      bindAssetCenterOpeners();
      bindPortalEditTriggers();
    }

    function getTimeGreeting() {
      var h = new Date().getHours();
      if (h < 6) return "夜深了";
      if (h < 12) return "上午好";
      if (h < 14) return "中午好";
      if (h < 18) return "下午好";
      return "晚上好";
    }

    function renderPortalProfile() {
      const container = document.querySelector("#portal-personal .card:first-child .card-body");
      if (!container) return;
      const p = state.portalProfile;
      // Only show personal data when logged in; use auth as source of truth
      const loggedIn = isLoggedIn();
      const authName = (_authUser && (_authUser.display_name || _authUser.username)) || "";
      const displayName = loggedIn ? (authName || p.name || "") : "";
      const email = loggedIn ? ((_authUser && _authUser.email) || p.email || "") : "";
      const nameTrimmed = (displayName || "").trim();
      const initial = nameTrimmed ? nameTrimmed.charAt(0) : "?";
      const greeting = getTimeGreeting();
      const nameLine = displayName ? `${escapeHTML(displayName)}，${greeting}` : "";
      const deptText = (loggedIn && p.department) ? `组织机构：${escapeHTML(p.department)}` : "";
      const emailText = email ? "已绑定" : "";
      container.innerHTML = `<div class="profile-box"><div class="profile-photo">${escapeHTML(initial)}</div><div><strong>${nameLine || "请登录查看个人信息"}</strong>${deptText ? `<p>${deptText}</p>` : ""}</div></div><div class="stat-stack"><div class="stat-tile"><small>我管理的资产</small><strong>&mdash;</strong></div><div class="stat-tile"><small>待处理任务</small><strong>&mdash;</strong></div><div class="stat-tile"><small>我的邮箱</small><strong>${emailText || "&mdash;"}</strong></div></div>`;
    }

    function renderPortalNews() {
      const container = document.querySelector("#portal-personal .card:nth-child(2) .news-list");
      if (!container) return;
      const subscribed = new Set(state.newsSubscriptions);
      const sourceLabelById = allNewsSourcesById;
      const news = (state.news.length ? state.news : portalNewsItems).map(normalizeNews);
      const items = news.filter((item) => !subscribed.size || subscribed.has(item.source) || subscribed.has(item.category) || subscribed.has(sourceLabelById[item.source]));
      container.innerHTML = (items.length ? items : news.slice(0, 4)).map((item) => `<button class="feed-item news-item" data-open-asset="news:${item.id}"><span class="feed-mark alt"><svg class="icon"><use href="#i-message"/></svg></span><span><span class="feed-title">${escapeHTML(item.title)}</span><span class="feed-meta"><span>${escapeHTML(sourceLabelById[item.source] || item.source || "")}</span><span>${escapeHTML(item.category || "")}</span></span></span><span class="feed-time">${formatShortDate(item.published_at || item.date)}</span></button>`).join("");
      bindAssetOpeners();
    }

    function renderPortalServices() {
      const container = $("#serviceItems");
      if (!container) return;
      const subscribed = new Set(state.serviceSubscriptions);
      const services = state.services.map(normalizeService);
      const filtered = services.filter((service) => !subscribed.size || subscribed.has(service.code) || subscribed.has(service.title));
      container.innerHTML = (filtered.length ? filtered : services).map((service, index) => `<button class="service-item" data-open-asset="services:${escapeHTML(service.code)}"><span class="app-icon ${service.icon_tone || ["app-green","app-orange","app-blue"][index % 3]}">${escapeHTML(service.title || "").slice(0, 1)}</span><span>${escapeHTML(service.title || "")}</span></button>`).join("");
      bindAssetOpeners();
    }

    function renderNewsSubModal() {
      const grid = $("#newsSubGrid");
      if (!grid) return;
      const subs = new Set(state.newsSubscriptions);
      const dynamicSources = (state.news || []).map(normalizeNews).map((item) => item.source).filter(Boolean);
      const sources = [...allNewsSources, ...dynamicSources.map((source) => ({ id: source, label: source }))];
      const uniqueSources = sources.filter((source, index, list) => list.findIndex((item) => item.id === source.id) === index);
      grid.innerHTML = uniqueSources.map(s => `<label class="sub-line"><input type="checkbox" value="${escapeHTML(s.id)}" ${(subs.has(s.id) || subs.has(s.label)) ? "checked" : ""} />${escapeHTML(s.label)}</label>`).join("");
    }

    function renderServiceSubModal() {
      const grid = $("#serviceSubGrid");
      if (!grid) return;
      const subs = new Set(state.serviceSubscriptions);
      grid.innerHTML = state.services.map(normalizeService).map((service) => `<label class="sub-line"><input type="checkbox" value="${escapeHTML(service.code)}" ${(subs.has(service.code) || subs.has(service.title)) ? "checked" : ""} />${escapeHTML(service.title)}</label>`).join("");
    }

    function updateMonthTitles() {
      const title = `${state.year} 年 ${state.month + 1} 月`;
      const miniTitle = $("#miniMonthTitle");
      const sideTitle = $("#sideMonthTitle");
      if (miniTitle) miniTitle.textContent = title;
      if (sideTitle) sideTitle.textContent = title;
      const calendarTitle = $("#calendarMonthTitle");
      if (calendarTitle) calendarTitle.textContent = title;
    }

    function renderCalendar() {
      updateMonthTitles();
      const cells = getMonthCells(state.year, state.month);
      const weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
      $("#calendarCanvas").innerHTML = `<div class="calendar-grid">${weekdays.map((day) => `<div class="calendar-weekday">${day}</div>`).join("")}${cells.map((cell) => {
        const key = dateKey(cell.date);
        const current = key === todayKey;
        const events = state.events.map((event, index) => ({ ...event, index })).filter((event) => event.date === key);
        return `<div class="calendar-cell ${cell.muted ? "muted" : ""}"><span class="date-number ${current ? "current" : ""}">${cell.day}</span>${events.map((event) => `<button class="event ${event.tone}" data-edit-event="${event.index}">${event.title}</button>`).join("")}</div>`;
      }).join("")}</div>`;
      renderMiniCalendar("sideMonth");
      bindEventEditors($("#calendarCanvas"));
      bindToasts();
    }

    function renderKnowledge(filter = state.kbFilter, query = "") {
      const lower = query.trim().toLowerCase();
      const items = state.knowledge.filter((item) => {
        const matchesFilter =
          filter === "all"
          || (filter === "disabled" ? !item.enabled : item.resource_type === filter && item.enabled);
        const haystack = `${item.display_name}${item.resource_id}${item.fastgpt_dataset_id || ""}${item.fastgpt_app_id || ""}`.toLowerCase();
        return matchesFilter && (!lower || haystack.includes(lower));
      });
      $("#kbGrid").innerHTML = items.length ? items.map(renderKnowledgeCard).join("") : `<div class="empty-state" style="grid-column:1/-1"><div><div class="empty-illustration"></div><strong>还没有可管理的知识库映射</strong><div>点击”同步 FastGPT”拉取数据集并保存映射。</div><button class="empty-action" id="emptyKbAction">刷新知识库</button></div></div>`;
      renderKnowledgeDatasetOptions();
      bindKnowledgeActions();
      bindToasts();
      const emptyKbAction = $("#emptyKbAction");
      if (emptyKbAction) emptyKbAction.addEventListener("click", () => fetchKnowledgeMappings(state.kbFilter, $("#kbSearchInput").value));
    }

    function renderKnowledgeCard(item) {
      const title = item.display_name || item.title || item.resource_id;
      const resourceId = item.fastgpt_dataset_id || item.resource_id;
      return `<article class="kb-card ${item.enabled ? "" : "disabled"}"><div class="kb-top"><span class="kb-cover app-purple">${escapeHTML(title).slice(0, 1)}</span><span><h3>${escapeHTML(title)}</h3><p>FastGPT Dataset</p></span></div><p>文件导入目标，FastGPT 负责切分、嵌入和向量检索。</p><div class="kb-meta"><span>${escapeHTML(resourceId || "")}</span><span>${item.enabled ? "启用" : "停用"}</span>${item.is_default_import_target ? "<span>默认导入</span>" : ""}${item.stale ? "<span>同步异常</span>" : ""}</div><div class="kb-actions"><button class="btn" data-kb-files="${escapeHTML(item.id)}" data-kb-files-dataset="${escapeHTML(item.fastgpt_dataset_id || "")}" data-kb-files-name="${escapeHTML(title)}">文件</button><button class="btn" data-knowledge-import="${escapeHTML(item.id)}">导入</button><button class="btn" data-knowledge-default="${escapeHTML(item.id)}">设为默认</button><button class="btn" data-knowledge-toggle="${escapeHTML(item.id)}">${item.enabled ? "停用" : "启用"}</button><button class="btn" data-knowledge-rename="${escapeHTML(item.id)}">重命名</button><button class="btn danger" data-knowledge-delete="${escapeHTML(item.id)}">删除本地映射</button></div></article>`;
    }

    async function fetchKnowledgeMappings(filter = state.kbFilter, query = "") {
      const payload = await apiJson("/api/v1/knowledge/mappings");
      state.knowledge = listItems(payload, []);
      renderKnowledge(filter, query);
    }

    function renderKnowledgeDatasetOptions() {
      const select = $("#knowledgeDatasetSelect");
      if (!select) return;
      const datasets = state.knowledge.filter((item) => item.fastgpt_dataset_id && item.enabled);
      select.innerHTML = datasets.length
        ? datasets.map((item) => `<option value="${escapeHTML(item.fastgpt_dataset_id)}" ${item.is_default_import_target ? "selected" : ""}>${escapeHTML(item.display_name || item.title)} · ${escapeHTML(item.fastgpt_dataset_id)}</option>`).join("")
        : `<option value="">暂无可导入的 FastGPT 知识库</option>`;
      select.disabled = datasets.length === 0;
    }

    async function updateKnowledgeMapping(id, patch) {
      const mappingId = encodeURIComponent(id);
      return apiJson(`/api/v1/knowledge/mappings/${mappingId}`, {
        method: "PATCH",
        body: JSON.stringify(patch)
      });
    }

    async function deleteKnowledgeMapping(id) {
      const mappingId = encodeURIComponent(id);
      return apiJson(`/api/v1/knowledge/mappings/${mappingId}`, { method: "DELETE" });
    }

    async function fetchKnowledgeImports() {
      const payload = await apiJson("/api/v1/knowledge/imports");
      state.knowledgeImports = listItems(payload, []);
      renderKnowledgeImports();
    }

    function renderKnowledgeImports() {
      const list = $("#knowledgeImportRecordList");
      if (!list) return;
      list.innerHTML = state.knowledgeImports.length
        ? state.knowledgeImports.slice(0, 8).map((item) => `<div class="import-record"><div><strong>${escapeHTML(item.file_name)}</strong><span>${escapeHTML(item.dataset_id)} · ${escapeHTML(item.collection_id || "未返回 collectionId")}</span></div><span>${escapeHTML(item.status)}</span></div>`).join("")
        : `<div class="import-record"><div><strong>暂无导入记录</strong><span>文件提交到 FastGPT 后会显示在这里。</span></div><span></span></div>`;
    }

    function renderKnowledgeSubTabs() {
      $$(".knowledge-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === `kb-panel-${state.knowledgeSubTab}`);
      });
    }

    function switchKnowledgeSubTab(tab) {
      state.knowledgeSubTab = tab;
      renderKnowledgeSubTabs();
      // Update sidebar active link
      $$("#sidebarContent .side-link").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.kbSubLink === tab);
      });
      if (tab === "library") {
        renderKnowledge();
        renderKnowledgeDatasetOptions();
        renderKnowledgeImports();
      } else if (tab === "qa") {
        renderChatSessions();
        renderChatTranscript();
        updateChatSendButton();
      }
    }

    function renderChatSessions() {
      const container = $("#chatSessionsList");
      if (!container) return;
      const sessions = state.chatSessions.sessions;
      const activeId = state.chatSessions.activeSessionId;
      if (!sessions.length) {
        container.innerHTML = `<div class="chat-sessions-empty">暂无会话，<br />点击"新建"开始对话</div>`;
        return;
      }
      container.innerHTML = sessions.map((s) => {
        const title = escapeHTML(s.title || "新会话");
        const time = (s.updatedAt || s.createdAt || "").slice(-11).replace(/^0/, "");
        const active = s.id === activeId ? " active" : "";
        return `<button class="session-item${active}" data-session-id="${s.id}">
          <span class="session-title">${title}</span>
          <span class="session-time">${escapeHTML(time)}</span>
          <span class="session-delete" data-session-delete="${s.id}" title="删除会话">&times;</span>
        </button>`;
      }).reverse().join("");
      bindSessionActions();
    }

    function bindSessionActions() {
      $$("[data-session-id]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          if (e.target.closest("[data-session-delete]")) return;
          switchChatSession(btn.dataset.sessionId);
        });
      });
      $$("[data-session-delete]").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          deleteChatSession(btn.dataset.sessionDelete);
        });
      });
    }

    async function fetchChatSessionsFromBackend() {
      try {
        const resp = await fetch(`${apiBaseUrl}/api/v1/chat/sessions`);
        if (!resp.ok) return;
        const data = await resp.json();
        if (!data.items || data.items.length === 0) return;

        for (const s of data.items) {
          // 跳过本地已存在的会话
          if (state.chatSessions.sessions.find((ls) => ls.id === s.id)) continue;

          // 拉取消息
          const msgResp = await fetch(`${apiBaseUrl}/api/v1/chat/sessions/${encodeURIComponent(s.id)}/messages`);
          if (!msgResp.ok) continue;
          const msgData = await msgResp.json();
          const messages = (msgData.items || []).map((m) => ({
            id: "m_bk_" + m.id,
            role: m.role,
            content: m.content,
            status: "completed",
            createdAt: (m.created_at || "").slice(11, 16),
          }));

          state.chatSessions.sessions.push({
            id: s.id,
            title: s.title || "",
            messages,
            createdAt: (s.created_at || "").slice(0, 10) + " " + (s.created_at || "").slice(11, 16),
            updatedAt: (s.updated_at || "").slice(0, 10) + " " + (s.updated_at || "").slice(11, 16),
          });
        }
        saveChatSessions();
        renderChatSessions();
      } catch {
        // 后端不可用时静默跳过，使用本地 localStorage 数据
      }
    }

    function createChatSession() {
      const now = new Date();
      const id = "s_" + Date.now();
      const session = {
        id,
        title: "",
        messages: [],
        createdAt: `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")} ${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}`,
        updatedAt: ""
      };
      state.chatSessions.sessions.push(session);
      state.chatSessions.activeSessionId = id;
      saveChatSessions();
      renderChatSessions();
      renderChatTranscript();
      $("#chatInput")?.focus();
    }

    function switchChatSession(id) {
      state.chatSessions.activeSessionId = id;
      saveChatSessions();
      renderChatSessions();
      renderChatTranscript();
      scrollChatToBottom();
    }

    function deleteChatSession(id) {
      const session = state.chatSessions.sessions.find((s) => s.id === id);
      if (!session || !window.confirm(`删除会话"${session.title || "新会话"}"？此操作不可恢复。`)) return;
      state.chatSessions.sessions = state.chatSessions.sessions.filter((s) => s.id !== id);
      if (state.chatSessions.activeSessionId === id) {
        state.chatSessions.activeSessionId = state.chatSessions.sessions.length > 0
          ? state.chatSessions.sessions[state.chatSessions.sessions.length - 1].id
          : null;
      }
      saveChatSessions();
      renderChatSessions();
      renderChatTranscript();
      showToast("会话已删除");
    }

    function getActiveSession() {
      const { activeSessionId, sessions } = state.chatSessions;
      return sessions.find((s) => s.id === activeSessionId) || null;
    }

    function renderChatTranscript() {
      const container = $("#chatTranscript");
      if (!container) return;
      const session = getActiveSession();
      if (!session || !session.messages.length) {
        container.innerHTML = `<div class="chat-empty">
          <div class="empty-icon-wrap"><svg class="icon" style="width:26px;height:26px"><use href="#i-spark"/></svg></div>
          <strong>开始新的对话</strong>
          <p>在下方输入问题，Enter 发送，Shift+Enter 换行</p>
        </div>`;
        return;
      }
      container.innerHTML = session.messages.map((m) => {
        const avatarChar = m.role === "user" ? "U" : "AI";
        const time = (m.createdAt || "").slice(-5) || "";
        const contentHTML = m.role === "assistant" && typeof marked !== "undefined"
          ? marked.parse(m.content || "")
          : escapeHTML(m.content || "").replace(/\n/g, "<br>");
        const statusHTML = m.role === "assistant" && m.status
          ? `<span class="chat-bubble-status ${m.status}">${m.status === "streaming" ? "生成中" : m.status === "completed" ? "已完成" : "失败"}</span>`
          : "";
        const cursorHTML = m.role === "assistant" && m.status === "streaming"
          ? `<span class="chat-streaming-cursor"></span>`
          : "";
        return `<div class="chat-bubble ${m.role}">
          <div class="chat-bubble-avatar">${avatarChar}</div>
          <div class="chat-bubble-body">
            <div class="chat-bubble-content">${contentHTML}${cursorHTML}</div>
            <div class="chat-bubble-meta"><span>${escapeHTML(time)}</span>${statusHTML}</div>
          </div>
        </div>`;
      }).join("");
      scrollChatToBottom();
    }

    function scrollChatToBottom() {
      const container = $("#chatTranscript");
      if (!container) return;
      requestAnimationFrame(() => { container.scrollTop = container.scrollHeight; });
    }

    function updateChatSendButton() {
      const btn = $("#chatSendBtn");
      const input = $("#chatInput");
      if (!btn || !input) return;
      const hasText = input.value.trim().length > 0;
      btn.disabled = !hasText;
      btn.classList.toggle("stop", state.isStreaming);
      btn.classList.toggle("loading", state.isStreaming);
      if (state.isStreaming) {
        btn.querySelector(".btn-label").textContent = "停止";
      } else {
        btn.querySelector(".btn-label").textContent = "发送";
      }
    }

    function syncMessageToBackend(sessionId, role, content, action, title) {
      // Fire-and-forget: 不阻塞 UI，失败了也不影响用户体验
      apiJson("/api/v1/chat/messages", {
        method: "POST",
        body: JSON.stringify({
          session_id: sessionId,
          role: role,
          content: content,
          action: action || null,
          title: title || null,
        }),
      }).catch(() => {}); // 静默失败，localStorage 始终是主要存储
    }

    async function sendChatMessage() {
      if (state.isStreaming) {
        stopChatStream();
        return;
      }
      const input = $("#chatInput");
      const question = input.value.trim();
      if (!question) return;

      // Ensure active session exists
      if (!state.chatSessions.activeSessionId || !state.chatSessions.sessions.find((s) => s.id === state.chatSessions.activeSessionId)) {
        createChatSession();
      }
      const session = getActiveSession();
      if (!session) return;

      // Auto-title: use first user message
      if (!session.title) {
        session.title = question.slice(0, 30) + (question.length > 30 ? "…" : "");
      }

      // Add user message
      const now = new Date();
      const timeStr = `${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}`;
      const userMsg = { id: "m_" + Date.now(), role: "user", content: question, createdAt: timeStr };
      session.messages.push(userMsg);
      session.updatedAt = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")} ${timeStr}`;
      saveChatSessions();

      // Add streaming assistant placeholder
      const assistantMsg = { id: "m_" + (Date.now() + 1), role: "assistant", content: "", status: "streaming", createdAt: "" };
      session.messages.push(assistantMsg);

      input.value = "";
      autoResizeChatInput();
      state.isStreaming = true;
      updateChatSendButton();
      renderChatSessions();
      renderChatTranscript();

      // Parse mode from input
      let mode = "auto";
      let finalQuestion = question;
      for (const prefix of ["/rag ", "/RAG ", "/chat ", "/CHAT "]) {
        if (finalQuestion.startsWith(prefix)) {
          mode = prefix.toLowerCase().startsWith("/rag") ? "rag" : "chat";
          finalQuestion = question.slice(prefix.length).trim();
          break;
        }
      }

      // Create AbortController for this request
      state.activeAbortController = new AbortController();

      try {
        const payload = await apiJson("/api/v1/knowledge/chat", {
          method: "POST",
          body: JSON.stringify({ question: finalQuestion, mode, session_id: session.id, command_mode: true }),
          signal: state.activeAbortController.signal
        });
        const raw = payload.answer || "未返回可展示的知识库回答。";
        assistantMsg.content = raw;
        assistantMsg.status = "completed";
        assistantMsg.createdAt = `${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}`;
        // 指令执行后自动刷新工作台数据，无需手动刷新页面
        if (payload.mode === "command" && payload.action !== "chat") {
          fetchPortalBootstrap().catch(() => {});
        }
      } catch (error) {
        if (error.name === "AbortError") {
          if (!assistantMsg.content) assistantMsg.content = "（已停止生成）";
          assistantMsg.status = "completed";
        } else {
          console.warn("Knowledge chat failed.", error);
          assistantMsg.content = "请求失败，请检查网络连接或后端服务状态。";
          assistantMsg.status = "failed";
        }
        assistantMsg.createdAt = `${String(now.getHours()).padStart(2,"0")}:${String(now.getMinutes()).padStart(2,"0")}`;
      }

      state.isStreaming = false;
      state.activeAbortController = null;
      saveChatSessions();
      updateChatSendButton();
      renderChatSessions();
      renderChatTranscript();
    }

    function stopChatStream() {
      if (state.activeAbortController) {
        state.activeAbortController.abort();
      }
    }

    function autoResizeChatInput() {
      const input = $("#chatInput");
      if (!input) return;
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 120) + "px";
    }

    function bindKnowledgeActions() {
      $$("[data-knowledge-import]").forEach((button) => button.addEventListener("click", () => {
        const item = state.knowledge.find((mapping) => mapping.id === button.dataset.knowledgeImport);
        if (item?.fastgpt_dataset_id) {
          $("#knowledgeDatasetSelect").value = item.fastgpt_dataset_id;
          openKnowledgeImport();
        }
      }));
      $$("[data-knowledge-toggle]").forEach((button) => button.addEventListener("click", async () => {
        const item = state.knowledge.find((mapping) => mapping.id === button.dataset.knowledgeToggle);
        if (!item) return;
        await updateKnowledgeMapping(item.id, { enabled: !item.enabled });
        await fetchKnowledgeMappings(state.kbFilter, $("#kbSearchInput").value);
        showToast(item.enabled ? "知识库已停用" : "知识库已启用");
      }));
      $$("[data-knowledge-default]").forEach((button) => button.addEventListener("click", async () => {
        await updateKnowledgeMapping(button.dataset.knowledgeDefault, { is_default_import_target: true });
        await fetchKnowledgeMappings(state.kbFilter, $("#kbSearchInput").value);
        showToast("默认导入知识库已更新");
      }));
      $$("[data-knowledge-rename]").forEach((button) => button.addEventListener("click", async () => {
        const item = state.knowledge.find((mapping) => mapping.id === button.dataset.knowledgeRename);
        if (!item) return;
        const nextName = window.prompt("显示名称", item.display_name || item.resource_id);
        if (!nextName || !nextName.trim()) return;
        await updateKnowledgeMapping(item.id, { display_name: nextName.trim() });
        await fetchKnowledgeMappings(state.kbFilter, $("#kbSearchInput").value);
        showToast("知识库名称已更新");
      }));
      $$("[data-knowledge-delete]").forEach((button) => button.addEventListener("click", async () => {
        const item = state.knowledge.find((mapping) => mapping.id === button.dataset.knowledgeDelete);
        if (!item || !window.confirm(`删除本地映射：${item.display_name || item.resource_id}？`)) return;
        await deleteKnowledgeMapping(item.id);
        await fetchKnowledgeMappings(state.kbFilter, $("#kbSearchInput").value);
        showToast("本地映射已删除");
      }));
      bindKbFileActions();
    }

    function bindKbFileActions() {
      $$("[data-kb-files]").forEach((button) => button.addEventListener("click", () => {
        const datasetId = button.dataset.kbFilesDataset;
        const kbName = button.dataset.kbFilesName;
        if (!datasetId) { showToast("该知识库未关联 FastGPT Dataset，请先同步"); return; }
        openKbFiles(datasetId, kbName);
      }));
    }

    async function openKbFiles(datasetId, kbName) {
      const modal = $("#kbFilesModal");
      const title = $("#kbFilesModalTitle");
      const kbNameEl = $("#kbFilesKbName");
      const list = $("#kbFilesList");
      const empty = $("#kbFilesEmpty");
      if (!modal || !list) return;
      title.textContent = `文件管理 · ${kbName}`;
      kbNameEl.textContent = kbName;
      list.innerHTML = `<div class="kb-files-loading">加载中...</div>`;
      empty.hidden = true;
      modal.classList.add("show");
      try {
        const payload = await apiJson(`/api/v1/knowledge/datasets/${encodeURIComponent(datasetId)}/files`);
        const items = payload.items || [];
        if (items.length === 0) {
          list.innerHTML = "";
          empty.hidden = false;
        } else {
          renderKbFilesList(items, datasetId);
        }
      } catch (error) {
        list.innerHTML = `<div class="kb-files-empty">加载失败：${error.message}</div>`;
        console.warn("Failed to list dataset files", error);
      }
    }

    function renderKbFilesList(files, datasetId) {
      const list = $("#kbFilesList");
      if (!list) return;
      list.innerHTML = files.map((f) => {
        const statusClass = f.status === "ready" ? "ready" : "";
        const statusLabel = { ready: "就绪", queued: "排队中", training: "训练中", unknown: "未知" }[f.status] || f.status;
        const fileName = f.file_name || f.collection_id || "未知文件";
        return `<div class="kb-file-row">
          <span class="kb-file-name" title="${escapeHTML(fileName)}">${escapeHTML(fileName)}</span>
          <span class="kb-file-status ${statusClass}">${statusLabel}</span>
          <button class="btn danger kb-file-delete" data-delete-file="${escapeHTML(f.collection_id)}" data-delete-name="${escapeHTML(fileName)}">删除</button>
        </div>`;
      }).join("");
      // Bind delete buttons
      $$("#kbFilesList .kb-file-delete").forEach((btn) => btn.addEventListener("click", async () => {
        const fileId = btn.dataset.deleteFile;
        const fileName = btn.dataset.deleteName;
        if (!window.confirm(`确认删除文件「${fileName}」？此操作不可恢复。`)) return;
        try {
          await apiJson(`/api/v1/knowledge/datasets/${encodeURIComponent(datasetId)}/files/${encodeURIComponent(fileId)}`, { method: "DELETE" });
          showToast(`已删除：${fileName}`);
          // Refresh the list
          const remaining = files.filter((f) => f.collection_id !== fileId);
          if (remaining.length === 0) {
            $("#kbFilesList").innerHTML = "";
            $("#kbFilesEmpty").hidden = false;
          } else {
            files.length = 0;
            files.push(...remaining);
            renderKbFilesList(files, datasetId);
          }
          // Also refresh imports
          fetchKnowledgeImports().catch(() => {});
        } catch (error) {
          showToast("文件删除失败");
          console.warn("Failed to delete file", error);
        }
      }));
    }

    function closeKbFilesModal() {
      const modal = $("#kbFilesModal");
      if (modal) modal.classList.remove("show");
    }

    async function syncKnowledgeMappings() {
      const status = $("#knowledgeSyncStatus");
      status.textContent = "正在从 FastGPT 同步数据集...";
      try {
        const payload = await apiJson("/api/v1/knowledge/sync", {
          method: "POST",
          body: JSON.stringify({})
        });
        await fetchKnowledgeMappings(state.kbFilter, $("#kbSearchInput").value);
        status.textContent = `同步完成：新增 ${payload.created || 0}，更新 ${payload.updated || 0}，共 ${payload.total || 0} 个映射。`;
        showToast("FastGPT 知识库已同步");
      } catch (error) {
        status.textContent = "同步失败，请检查 FastGPT real 模式、API Key 和服务地址。";
        showToast("FastGPT 同步失败");
        console.warn("Knowledge sync failed.", error);
      }
    }

    async function importKnowledgeFile(event) {
      event.preventDefault();
      const select = $("#knowledgeDatasetSelect");
      const input = $("#knowledgeImportFile");
      const status = $("#knowledgeImportStatus");
      const datasetId = select.value;
      const file = input.files && input.files[0];
      if (!datasetId) {
        showToast("请先选择目标知识库");
        return;
      }
      if (!file) {
        showToast("请先选择文件");
        return;
      }
      const formData = new FormData();
      formData.append("dataset_id", datasetId);
      formData.append("file", file);
      status.textContent = "正在上传到 FastGPT...";
      try {
        const payload = await apiJson("/api/v1/knowledge/import", {
          method: "POST",
          body: formData
        });
        status.textContent = `${payload.file_name || file.name} 已提交到 ${payload.dataset_id || datasetId}`;
        input.value = "";
        await fetchKnowledgeImports();
        await fetchKnowledgeMappings(state.kbFilter, $("#kbSearchInput").value);
        showToast("文件已提交到 FastGPT");
      } catch (error) {
        status.textContent = "导入失败，请检查 FastGPT 配置和服务状态。";
        showToast("文件导入失败");
        console.warn("Knowledge import failed.", error);
      }
    }

    function openKnowledgeImport() {
      switchKnowledgeSubTab("library");
      setTimeout(() => {
        const el = $("#knowledge-import");
        if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
        $("#knowledgeImportFile")?.focus();
      }, 150);
    }

    var _searchTimer = null;
    async function fetchGlobalSearch(query) {
      if (!query || query.length < 1) {
        $("#searchResults").innerHTML = `<div class="search-result"><strong>输入关键词开始搜索</strong><p>支持搜索子系统、公告、文档、报修、资产、OA 流程等</p></div>`;
        return;
      }
      var payload = await apiJson(`/api/v1/search?${new URLSearchParams({ q: query, limit: "20" }).toString()}`);
      var items = listItems(payload, []);

      // Group by type for category rendering
      var TYPE_LABELS = { subsystem: "子系统", notice: "公告", document: "文档", resource: "资源", service: "服务", repair: "报修", asset: "资产", oa: "OA流程", news: "资讯" };
      var groups = {};
      for (var i = 0; i < items.length; i++) {
        var t = items[i].type || "other";
        if (!groups[t]) groups[t] = [];
        groups[t].push(items[i]);
      }

      var html = "";
      var groupKeys = Object.keys(groups);
      for (var g = 0; g < groupKeys.length; g++) {
        var typeKey = groupKeys[g];
        var groupItems = groups[typeKey];
        html += '<div class="search-group-label">' + (TYPE_LABELS[typeKey] || typeKey) + ' <small>(' + groupItems.length + ')</small></div>';
        for (var j = 0; j < groupItems.length; j++) {
          var item = groupItems[j];
          var statusHtml = "";
          if (item.status) {
            try {
              statusHtml = window.App.components.statusBadge.render(item.status, "small");
            } catch (_) { statusHtml = '<span class="badge badge-small">' + escapeHTML(item.status) + '</span>'; }
          }
          html += (
            '<div class="search-result-item" data-search-href="' + escapeHTML(item.href || "#") + '">' +
            '<div class="search-result-text">' +
            '<div class="search-result-title">' + escapeHTML(item.title || "") + '</div>' +
            (item.subtitle ? '<div class="search-result-subtitle">' + escapeHTML(item.subtitle) + '</div>' : "") +
            '</div>' + statusHtml + '</div>'
          );
        }
      }

      if (!html) {
        html = '<div class="search-result"><strong>没有找到匹配结果</strong><p>换个关键词再试试。</p></div>';
      }

      $("#searchResults").innerHTML = html;

      // Click-to-navigate on result items
      $$("#searchResults .search-result-item").forEach(function (el) {
        el.addEventListener("click", function () {
          var href = el.getAttribute("data-search-href");
          if (href && href !== "#") {
            $("#searchModal").classList.remove("show");
            window.location.hash = href;
          }
        });
      });
    }

    function bindToasts() {
      $$("[data-toast]").forEach((element) => {
        element.onclick = () => showToast(element.dataset.toast);
      });
    }

    function bindModalTriggers() {
      $$("[data-open-modal]").forEach((element) => {
        element.onclick = () => openEventModal();
      });
    }

    function normalizeEmbedUrl(value, fallback) {
      const trimmed = value.trim();
      if (!trimmed) return fallback;
      return /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
    }

    function saveEmbedUrls() {
      var data = JSON.stringify(state.embedUrls);
      _saveScoped(embedStorageKey, data);
      try { window.localStorage.setItem(embedStorageKey, data); } catch (e) {}
    }

    async function saveEmbedUrlsRemote() {
      return apiJson("/api/v1/integrations/embed-urls", {
        method: "PUT",
        body: JSON.stringify(state.embedUrls)
      });
    }

    function applyEmbedUrl(key) {
      const input = $(`[data-embed-input="${key}"]`);
      const frame = $(`#${key}Frame`);
      if (!input || !frame) return;
      const nextUrl = normalizeEmbedUrl(input.value, defaultEmbedUrls[key]);
      state.embedUrls[key] = nextUrl;
      input.value = nextUrl;
      frame.src = nextUrl;
      saveEmbedUrls();
      saveEmbedUrlsRemote().catch((error) => console.warn("Embed URL update stayed local.", error));
      showToast(`${key === "feishu" ? "飞书" : "钉钉"}页面已载入`);
    }

    function renderEmbeds() {
      Object.keys(defaultEmbedUrls).forEach((key) => {
        const input = $(`[data-embed-input="${key}"]`);
        const frame = $(`#${key}Frame`);
        if (!input || !frame) return;
        input.value = state.embedUrls[key];
        frame.src = state.embedUrls[key];
      });
    }

    function bindEmbeds() {
      renderEmbeds();
      $$("[data-embed-apply]").forEach((button) => {
        button.addEventListener("click", () => applyEmbedUrl(button.dataset.embedApply));
      });
      $$("[data-embed-input]").forEach((input) => {
        input.addEventListener("keydown", (event) => {
          if (event.key === "Enter") applyEmbedUrl(input.dataset.embedInput);
        });
      });
      $$("[data-embed-refresh]").forEach((button) => {
        button.addEventListener("click", () => {
          const key = button.dataset.embedRefresh;
          const frame = $(`#${key}Frame`);
          if (!frame) return;
          frame.src = state.embedUrls[key];
          showToast(`${key === "feishu" ? "飞书" : "钉钉"}页面已刷新`);
        });
      });
      $$("[data-embed-open]").forEach((button) => {
        button.addEventListener("click", () => {
          const key = button.dataset.embedOpen;
          window.open(state.embedUrls[key], "_blank", "noopener,noreferrer");
        });
      });
    }

    function changeMonth(delta) {
      state.month += delta;
      if (state.month < 0) { state.month = 11; state.year -= 1; }
      if (state.month > 11) { state.month = 0; state.year += 1; }
      state.selectedScheduleDate = dateKey(new Date(state.year, state.month, 1));
      updateMonthTitles();
      renderWorkbenchSchedule();
      renderMiniCalendar("portalMonth");
      renderCalendar();
    }

    function closePopovers() { const n = $("#notificationDropdown"); if (n) n.classList.remove("show"); const u = $("#userPopover"); if (u) u.classList.remove("show"); }

    function closeEventModal() {
      state.editingEventIndex = null;
      const deleteButton = $("#eventDeleteButton");
      if (deleteButton) deleteButton.hidden = true;
      $("#eventModal").classList.remove("show");
      $("#eventForm").reset();
    }

    function deleteEditingEvent() {
      if (state.editingEventIndex === null) return;
      const eventItem = state.events[state.editingEventIndex];
      state.events.splice(state.editingEventIndex, 1);
      saveEvents();
      if (eventItem?.id) deleteEventRemote(eventItem.id).catch((error) => console.warn("Calendar delete stayed local.", error));
      closeEventModal();
      renderCalendar(); renderWorkbenchSchedule(); renderMiniCalendar("portalMonth");
      renderWorkbenchOverview();
      showToast("日程已删除");
    }

    function togglePortalEditMode() {
      state.portalEditMode = !state.portalEditMode;
      const portal = $("#portal");
      const gearBtn = $("#portalSettingsBtn");
      if (!gearBtn || !portal) return;
      gearBtn.classList.toggle("active", state.portalEditMode);
      portal.classList.toggle("portal-edit", state.portalEditMode);
      portal.querySelectorAll(".card").forEach(card => { card.draggable = state.portalEditMode; });
      if (state.portalEditMode) {
        const doneBtn = document.createElement("button");
        doneBtn.className = "btn portal-done-btn primary";
        doneBtn.textContent = "完成";
        doneBtn.id = "portalDoneBtn";
        doneBtn.addEventListener("click", togglePortalEditMode);
        gearBtn.parentNode.insertBefore(doneBtn, gearBtn.nextSibling);
        showToast("已进入门户编辑模式，拖动卡片可调整顺序");
      } else {
        const doneBtn = $("#portalDoneBtn");
        if (doneBtn) doneBtn.remove();
        showToast("门户布局已保存");
      }
    }

    function handleDragStart(event) {
      if (!state.portalEditMode) return;
      const card = event.target.closest(".card");
      if (!card) return;
      card.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", [...card.parentNode.children].indexOf(card));
      event.dataTransfer.setData("grid-id", card.parentNode.id);
    }

    function handleDragEnd(event) {
      const card = event.target.closest(".card");
      if (card) card.classList.remove("dragging");
      document.querySelectorAll(".card.drag-over").forEach(el => el.classList.remove("drag-over"));
    }

    function handleDragOver(event) {
      if (!state.portalEditMode) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      const target = event.target.closest(".card");
      if (target) target.classList.add("drag-over");
    }

    function handleDragLeave(event) {
      const target = event.target.closest(".card");
      if (target) target.classList.remove("drag-over");
    }

    function handleDrop(event) {
      event.preventDefault();
      if (!state.portalEditMode) return;
      const sourceIndex = Number(event.dataTransfer.getData("text/plain"));
      const sourceGridId = event.dataTransfer.getData("grid-id");
      const targetCard = event.target.closest(".card");
      if (!targetCard) return;
      targetCard.classList.remove("drag-over");
      const targetGrid = targetCard.parentNode;
      if (!targetGrid || sourceGridId !== targetGrid.id) {
        showToast("卡片只能在同一区域中拖动");
        return;
      }
      const children = [...targetGrid.children];
      const targetIndex = children.indexOf(targetCard);
      if (sourceIndex === targetIndex) return;
      const [movedCard] = children.splice(sourceIndex, 1);
      children.splice(targetIndex, 0, movedCard);
      children.forEach(child => targetGrid.appendChild(child));
      showToast("卡片已重新排序");
    }

    function bindPortalEditTriggers() {
      const gearBtn = $("#portalSettingsBtn");
      if (gearBtn) gearBtn.onclick = togglePortalEditMode;
      // Portal card button bindings
      const profileEditBtn = document.querySelector("#portal-personal .card:first-child .card-link");
      if (profileEditBtn) profileEditBtn.onclick = openProfileModal;
      const newsSubBtn = document.querySelector("#portal-personal .card:nth-child(2) .card-link");
      if (newsSubBtn) newsSubBtn.onclick = openNewsSubModal;
      const serviceSubBtn = document.querySelector("#portal-services .card:last-child .card-link");
      if (serviceSubBtn) serviceSubBtn.onclick = openServiceSubModal;
      // Drag handles and drag events
      document.querySelectorAll("#portal .card").forEach(card => {
        const header = card.querySelector(".card-header");
        if (header && !header.querySelector(".drag-handle")) {
          const handle = document.createElement("span");
          handle.className = "drag-handle";
          handle.innerHTML = `<svg class="icon"><use href="#i-grip"/></svg>`;
          header.insertBefore(handle, header.firstChild);
        }
        card.removeEventListener("dragstart", handleDragStart);
        card.removeEventListener("dragend", handleDragEnd);
        card.removeEventListener("dragover", handleDragOver);
        card.removeEventListener("dragleave", handleDragLeave);
        card.removeEventListener("drop", handleDrop);
        card.addEventListener("dragstart", handleDragStart);
        card.addEventListener("dragend", handleDragEnd);
        card.addEventListener("dragover", handleDragOver);
        card.addEventListener("dragleave", handleDragLeave);
        card.addEventListener("drop", handleDrop);
      });
    }

    function openProfileModal() {
      // Prefer auth data for identity fields; portal profile for local-only fields
      const authName = (_authUser && (_authUser.display_name || _authUser.username)) || "";
      const authEmail = (_authUser && _authUser.email) || "";
      const p = state.portalProfile;
      $("#profileName").value = authName || p.name || "";
      $("#profileDept").value = p.department || "";
      $("#profileEmail").value = authEmail || p.email || "";
      $("#profilePhone").value = p.phone || "";
      // Name and email come from auth — make read-only to prevent invisible edits
      var nameInput = $("#profileName");
      var emailInput = $("#profileEmail");
      if (authName) { nameInput.setAttribute("readonly", ""); nameInput.style.background = "#f5f6f8"; }
      else { nameInput.removeAttribute("readonly"); nameInput.style.background = ""; }
      if (authEmail) { emailInput.setAttribute("readonly", ""); emailInput.style.background = "#f5f6f8"; }
      else { emailInput.removeAttribute("readonly"); emailInput.style.background = ""; }
      $("#profileModal").classList.add("show");
    }

    function closeProfileModal() {
      $("#profileModal").classList.remove("show");
    }

    function syncProfileUI() {
      // Prefer auth user data, fall back to portal profile
      const loggedIn = isLoggedIn();
      const authName = (_authUser && (_authUser.display_name || _authUser.username)) || "";
      const name = authName || state.portalProfile.name || "";
      const dept = state.portalProfile.department || "";
      const nameTrimmed = (name || "").trim();
      const initial = nameTrimmed ? nameTrimmed.charAt(0) : "?";
      // Portal card body
      renderPortalProfile();
      // Topbar avatar + name (top-right corner of page)
      const avatar = $(".avatar");
      const userSpan = document.querySelector(".user-trigger span:not(.avatar)");
      if (avatar) avatar.textContent = initial;
      if (userSpan) userSpan.textContent = name || (loggedIn ? "用户" : "未登录");
      // Popover (shown when clicking top-right avatar)
      const popoverName = $("#popoverName");
      const popoverDept = $("#popoverDept");
      if (popoverName) popoverName.textContent = name || (loggedIn ? "用户" : "未登录");
      if (popoverDept) popoverDept.innerHTML = `${escapeHTML(dept || "")}<small>个人信息与账号设置</small>`;
      // Sidebar (bottom-left)
      const sidebarAvatar = $("#sidebarAvatar");
      const sidebarName = $("#sidebarName");
      if (sidebarAvatar) sidebarAvatar.textContent = initial;
      if (sidebarName) sidebarName.textContent = name || (loggedIn ? "用户" : "未登录");
    }

    function handleProfileSave(event) {
      event.preventDefault();
      // Preserve auth identity fields (name/email come from server)
      const authName = (_authUser && (_authUser.display_name || _authUser.username)) || "";
      const authEmail = (_authUser && _authUser.email) || "";
      state.portalProfile = {
        name: authName || $("#profileName").value.trim(),
        department: $("#profileDept").value.trim(),
        email: authEmail || $("#profileEmail").value.trim(),
        phone: $("#profilePhone").value.trim()
      };
      saveProfile();
      closeProfileModal();
      syncProfileUI();
      showToast("个人资料已保存");
    }

    function openNewsSubModal() {
      renderNewsSubModal();
      $("#newsSubModal").classList.add("show");
    }

    function closeNewsSubModal() {
      $("#newsSubModal").classList.remove("show");
    }

    async function saveNewsSubscriptions() {
      const checked = [...document.querySelectorAll("#newsSubGrid input:checked")].map(cb => cb.value);
      state.newsSubscriptions = checked;
      state.portalPreferences = { ...state.portalPreferences, news_subscriptions: checked };
      saveNewsSubs();
      try {
        await savePortalPreferences(state.portalPreferences);
        showToast("新闻订阅已更新");
      } catch (error) {
        showToast(error.message || "新闻订阅已保存到本地，后端同步失败");
      }
      closeNewsSubModal();
      renderPortalNews();
    }

    function openServiceSubModal() {
      renderServiceSubModal();
      $("#serviceSubModal").classList.add("show");
    }

    function closeServiceSubModal() {
      $("#serviceSubModal").classList.remove("show");
    }

    async function saveServiceSubscriptions() {
      const checked = [...document.querySelectorAll("#serviceSubGrid input:checked")].map(cb => cb.value);
      state.serviceSubscriptions = checked;
      state.portalPreferences = { ...state.portalPreferences, service_subscriptions: checked };
      saveServiceSubs();
      try {
        await savePortalPreferences(state.portalPreferences);
        showToast("服务订阅已更新");
      } catch (error) {
        showToast(error.message || "服务订阅已保存到本地，后端同步失败");
      }
      closeServiceSubModal();
      renderPortalServices();
    }

    sidebarToggle.addEventListener("click", () => {
      setSidebarCollapsed(!moduleSidebar.classList.contains("collapsed"));
    });
    sidebarResizer.setAttribute("aria-valuemin", "180");
    sidebarResizer.setAttribute("aria-valuemax", "380");
    sidebarResizer.setAttribute("aria-valuenow", "230");
    sidebarResizer.addEventListener("pointerdown", (event) => {
      if (moduleSidebar.classList.contains("collapsed")) return;
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = moduleSidebar.getBoundingClientRect().width;
      const handlePointerMove = (moveEvent) => setSidebarWidth(startWidth + moveEvent.clientX - startX);
      const stopResize = () => {
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", stopResize);
      };
      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", stopResize);
    });
    sidebarResizer.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const step = event.shiftKey ? 24 : 12;
      const width = moduleSidebar.getBoundingClientRect().width;
      setSidebarWidth(width + (event.key === "ArrowRight" ? step : -step));
    });
    $$(".global-tab").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
    $$("[data-view-link]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.viewLink)));
    bindModalTriggers();
    $$("[data-close-modal]").forEach((button) => button.addEventListener("click", () => closeEventModal()));
    $$("[data-close-search]").forEach((button) => button.addEventListener("click", () => $("#searchModal").classList.remove("show")));
    $$("[data-close-kb-files]").forEach((button) => button.addEventListener("click", () => closeKbFilesModal()));
    $("#kbFilesModal")?.addEventListener("click", (event) => { if (event.target === $("#kbFilesModal")) closeKbFilesModal(); });
    // Modal close / backdrop / submit bindings (static — modals always in DOM)
    $$("[data-close-profile]").forEach(el => el.addEventListener("click", closeProfileModal));
    $("#profileModal")?.addEventListener("click", (event) => { if (event.target === $("#profileModal")) closeProfileModal(); });
    $("#profileForm")?.addEventListener("submit", handleProfileSave);
    $$("[data-close-news-sub]").forEach(el => el.addEventListener("click", closeNewsSubModal));
    $("#newsSubModal")?.addEventListener("click", (event) => { if (event.target === $("#newsSubModal")) closeNewsSubModal(); });
    $("#saveNewsSubsBtn")?.addEventListener("click", saveNewsSubscriptions);
    $$("[data-close-service-sub]").forEach(el => el.addEventListener("click", closeServiceSubModal));
    $("#serviceSubModal")?.addEventListener("click", (event) => { if (event.target === $("#serviceSubModal")) closeServiceSubModal(); });
    $("#saveServiceSubsBtn")?.addEventListener("click", saveServiceSubscriptions);
    $("#kbFilesRefresh")?.addEventListener("click", () => {
      const modal = $("#kbFilesModal");
      if (!modal || !modal.classList.contains("show")) return;
      const kbNameEl = $("#kbFilesKbName");
      const list = $("#kbFilesList");
      if (!list) return;
      list.innerHTML = `<div class="kb-files-loading">加载中...</div>`;
      const title = $("#kbFilesModalTitle");
      const match = title?.textContent.match(/文件管理 · (.+)/);
      const kbName = match ? match[1] : "";
      // Re-fetch: the dataset_id is stored in an open state... we need to track it.
      // For now, find by kbName from the knowledge list.
      const item = state.knowledge.find((m) => (m.display_name || m.title || m.resource_id) === kbName);
      if (item?.fastgpt_dataset_id) {
        openKbFiles(item.fastgpt_dataset_id, kbName);
      } else {
        list.innerHTML = `<div class="kb-files-empty">无法刷新，请关闭后重试。</div>`;
      }
    });
    // ── T7: Notification bell (component-driven, API-backed) ─────────
    if (window.App && window.App.components && window.App.components.notificationBell) {
      App.components.notificationBell.init({
        buttonId: "notificationButton",
        badgeId: "notificationBadge",
        dropdownId: "notificationDropdown",
        onFetch: async function () {
          try {
            var token = getToken();
            if (!token) return;
            var resp = await fetch("/api/v1/notifications?limit=50", {
              headers: { "Authorization": "Bearer " + token },
            });
            if (!resp.ok) return;
            var data = await resp.json();
            App.components.notificationBell.renderList(data.items || []);
          } catch (e) { /* best-effort */ }
        },
        onMarkRead: async function (id) {
          try {
            var token = getToken();
            if (!token) return;
            await fetch("/api/v1/notifications/" + id + "/read", {
              method: "PUT",
              headers: { "Authorization": "Bearer " + token },
            });
            fetchUnreadCount();
          } catch (e) { /* best-effort */ }
        },
        onMarkAllRead: async function () {
          try {
            var token = getToken();
            if (!token) return;
            await fetch("/api/v1/notifications/read-all", { method: "PUT",
              headers: { "Authorization": "Bearer " + token },
            });
            fetchUnreadCount();
            App.components.notificationBell.renderList([]);
          } catch (e) { /* best-effort */ }
        },
      });
    }

    async function fetchUnreadCount() {
      try {
        var token = getToken();
        if (!token) return;
        var resp = await fetch("/api/v1/notifications/unread-count", {
          headers: { "Authorization": "Bearer " + token },
        });
        if (!resp.ok) return;
        var data = await resp.json();
        App.components.notificationBell.setCount(data.unread_count || 0);
      } catch (e) { /* best-effort */ }
    }

    // Start polling unread count (60s) + refresh on window focus
    if (window.App && window.App.components && window.App.components.notificationBell) {
      fetchUnreadCount();
      setInterval(fetchUnreadCount, 60000);
      window.addEventListener("focus", fetchUnreadCount);
    }

    $("#userButton").addEventListener("click", (event) => {
      event.stopPropagation(); closePopovers();
      if (!isLoggedIn()) {
        showLoginOverlay();
      } else {
        $("#userPopover").classList.toggle("show");
      }
    });
    $("#popoverDept").addEventListener("click", () => { closePopovers(); openProfileModal(); });
    document.addEventListener("click", (event) => { if (!event.target.closest(".popover") && !event.target.closest("#notificationButton") && !event.target.closest("#userButton")) closePopovers(); });
    $("#globalSearchButton").addEventListener("click", function () {
      $("#searchModal").classList.add("show");
      setTimeout(function () {
        var input = $("#globalSearchInput");
        input.value = "";
        input.focus();
        fetchGlobalSearch("").catch(function () {});
      }, 0);
    });

    // ── Auth form handlers ──────────────────────────────────
    $("#loginForm")?.addEventListener("submit", function(event) {
      event.preventDefault();
      var username = document.getElementById("loginUsername").value.trim();
      var password = document.getElementById("loginPassword").value;
      if (!username || !password) return;
      if (_loginMode === "register") {
        if (password.length < 8) {
          var errEl = document.getElementById("loginError");
          errEl.textContent = "密码至少需要 8 位字符";
          errEl.classList.add("show");
          return;
        }
        var displayName = document.getElementById("regDisplayName").value.trim() || null;
        var email = document.getElementById("regEmail").value.trim() || null;
        handleRegister(username, password, displayName, email);
      } else {
        handleLogin(username, password);
      }
    });

    $("#loginSwitchBtn")?.addEventListener("click", toggleLoginMode);

    $("#changePasswordForm")?.addEventListener("submit", function(event) {
      event.preventDefault();
      var currentPw = document.getElementById("cpCurrentPassword").value;
      var newPw = document.getElementById("cpNewPassword").value;
      var confirmPw = document.getElementById("cpConfirmPassword").value;
      if (!currentPw || !newPw || !confirmPw) return;
      if (newPw.length < 8) {
        var errEl = document.getElementById("changePasswordError");
        errEl.textContent = "新密码至少需要 8 位字符";
        errEl.classList.add("show");
        return;
      }
      if (newPw !== confirmPw) {
        var errEl2 = document.getElementById("changePasswordError");
        errEl2.textContent = "两次输入的密码不一致";
        errEl2.classList.add("show");
        return;
      }
      handleChangePassword(currentPw, newPw);
    });

    // Close login overlay on backdrop click
    document.getElementById("loginOverlay")?.addEventListener("click", function(event) {
      if (event.target === document.getElementById("loginOverlay")) {
        document.getElementById("loginOverlay").classList.remove("show");
      }
    });
    $("#globalSearchInput").addEventListener("input", function (event) {
      var query = event.target.value.trim();
      clearTimeout(_searchTimer);
      _searchTimer = setTimeout(function () {
        fetchGlobalSearch(query).catch(function (error) { console.warn("Global search failed.", error); });
      }, 250);
    });
    $("#logoutButton").addEventListener("click", () => { closePopovers(); handleLogout(); showToast("已安全退出当前会话"); });
    $("#miniPrev").addEventListener("click", () => changeMonth(-1)); $("#miniNext").addEventListener("click", () => changeMonth(1));
    $("#sidePrev").addEventListener("click", () => changeMonth(-1)); $("#sideNext").addEventListener("click", () => changeMonth(1));
    $("#calendarPrev").addEventListener("click", () => changeMonth(-1)); $("#calendarNext").addEventListener("click", () => changeMonth(1));
    $("#todayButton").addEventListener("click", () => {
      state.year = currentDate.getFullYear();
      state.month = currentDate.getMonth();
      state.selectedScheduleDate = todayKey;
      renderWorkbenchSchedule();
      renderMiniCalendar("portalMonth");
      renderCalendar();
      showToast("已回到今天");
    });
    $$("#calendarMode button").forEach((button) => button.addEventListener("click", () => {
      $$("#calendarMode button").forEach((item) => item.classList.remove("active")); button.classList.add("active");
      showToast(`${button.textContent}视图已切换`);
    }));
    $$("#calendarMode button").forEach((button) => button.addEventListener("click", () => {
      if (button.dataset.calendarMode !== "month") showToast(`${button.textContent}视图将在此处展示`);
    }));
    $$(".tab[data-task-filter]").forEach((button) => button.addEventListener("click", () => {
      $$(".tab[data-task-filter]").forEach((item) => item.classList.remove("active")); button.classList.add("active");
      state.taskFilter = button.dataset.taskFilter; renderTasks();
    }));
    $("#taskForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const titleInput = $("#taskTitle");
      const title = titleInput.value.trim();
      if (!title) {
        showToast("请先输入任务内容");
        titleInput.focus();
        return;
      }
      const tag = $("#taskTag").value;
      const dueTime = $("#taskTime").value || null;
      let task;
      try {
        task = await createTaskRemote(title, tag, dueTime);
        task = { ...task, dueTime: task.dueTime || task.due_time || dueTime };
      } catch (error) {
        console.warn("Task create stayed local.", error);
        task = { id: Date.now(), title, tag, dueTime, done: false };
      }
      state.tasks.unshift(task);
      state.taskFilter = "todo";
      $$(".tab[data-task-filter]").forEach((item) => item.classList.toggle("active", item.dataset.taskFilter === "todo"));
      titleInput.value = "";
      $("#taskTime").value = "";
      saveTasks();
      renderTasks();
      renderNotifications();
    });
    $("#clearDoneTasks").addEventListener("click", async () => {
      const before = state.tasks.length;
      const doneTasks = state.tasks.filter((task) => task.done);
      // Track deleted done-task IDs so they don't reappear on next bootstrap
      for (const task of doneTasks) {
        state.pendingDeletes.add(task.id);
      }
      state.tasks = state.tasks.filter((task) => !task.done);
      savePendingDeletes();
      saveTasks();
      try {
        await clearDoneTasksRemote();
        for (const task of doneTasks) {
          state.pendingDeletes.delete(task.id);
        }
        savePendingDeletes();
      } catch (error) {
        console.warn("Task cleanup stayed local.", error);
      }
      renderTasks();
      renderNotifications();
      showToast(before === state.tasks.length ? "没有可清理的已完成任务" : "已清理完成任务");
    });
    // Chat event handlers
    $("#chatSendBtn").addEventListener("click", () => { void sendChatMessage(); });
    $("#chatInput").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        if (!$("#chatSendBtn").disabled) { void sendChatMessage(); }
      }
    });
    $("#chatInput").addEventListener("input", () => { updateChatSendButton(); autoResizeChatInput(); });
    $("#newChatSession").addEventListener("click", () => createChatSession());

    // ── Admin panel bindings ──────────────────────────────────
    $("#adminAddUserBtn")?.addEventListener("click", openAdminUserModal);
    $("#adminRefreshBtn")?.addEventListener("click", function() { fetchAdminUsers().catch(function(){}); });
    $("#adminUserForm")?.addEventListener("submit", createAdminUser);
    $$("[data-close-admin-user]").forEach(function(el) { el.addEventListener("click", closeAdminUserModal); });
    $("#adminUserModal")?.addEventListener("click", function(event) { if (event.target === $("#adminUserModal")) closeAdminUserModal(); });
    $$("[data-close-admin-kb]").forEach(function(el) { el.addEventListener("click", closeAdminKbAuthModal); });
    $("#adminKbAuthModal")?.addEventListener("click", function(event) { if (event.target === $("#adminKbAuthModal")) closeAdminKbAuthModal(); });
    $$("[data-close-admin-reset-pwd]").forEach(function(el) { el.addEventListener("click", closeAdminResetPwdModal); });
    $("#adminResetPwdModal")?.addEventListener("click", function(event) { if (event.target === $("#adminResetPwdModal")) closeAdminResetPwdModal(); });
    $("#adminKbAuthSaveBtn")?.addEventListener("click", saveAdminKbAuth);

    // Admin search & pagination
    var _adminSearchTimer = null;
    $("#adminUserSearch")?.addEventListener("input", function() {
      clearTimeout(_adminSearchTimer);
      _adminSearchTimer = setTimeout(function() {
        _adminSearchTerm = $("#adminUserSearch").value.trim();
        _adminPage = 1;
        fetchAdminUsers().catch(function(){});
      }, 300);
    });
    $("#adminPagePrev")?.addEventListener("click", function() {
      if (_adminPage > 1) { _adminPage--; fetchAdminUsers().catch(function(){}); }
    });
    $("#adminPageNext")?.addEventListener("click", function() {
      var totalPages = Math.max(1, Math.ceil(_adminTotalUsers / _adminPageSize));
      if (_adminPage < totalPages) { _adminPage++; fetchAdminUsers().catch(function(){}); }
    });

    // Phase 6: Admin sub-tabs
    $$("#adminSubtabs .admin-subtab").forEach(function(btn) {
      btn.addEventListener("click", function() { switchAdminSubTab(btn.dataset.adminPanel); });
    });
    // Phase 6: Audit panel
    $("#adminAuditRefresh")?.addEventListener("click", function() { _adminAuditPage = 1; fetchAdminAudit(); });
    $("#adminAuditAction")?.addEventListener("input", function() { _adminAuditPage = 1; clearTimeout(_adminAuditTimer); _adminAuditTimer = setTimeout(fetchAdminAudit, 400); });
    $("#adminAuditDecision")?.addEventListener("change", function() { _adminAuditPage = 1; fetchAdminAudit(); });
    $("#adminAuditPagePrev")?.addEventListener("click", adminAuditPrev);
    $("#adminAuditPageNext")?.addEventListener("click", adminAuditNext);
    var _adminAuditTimer = null;
    // Phase 6: AI Query panel
    $("#adminAIQueryRefresh")?.addEventListener("click", function() { _adminAIQueryPage = 1; fetchAdminAIQueries(); });
    $("#adminAIQueryDecision")?.addEventListener("change", function() { _adminAIQueryPage = 1; fetchAdminAIQueries(); });
    $("#adminAIQueryRisk")?.addEventListener("change", function() { _adminAIQueryPage = 1; fetchAdminAIQueries(); });
    $("#adminAIQueryPagePrev")?.addEventListener("click", adminAIQueryPrev);
    $("#adminAIQueryPageNext")?.addEventListener("click", adminAIQueryNext);
    // Phase 6: Session panel
    $("#adminSessionRefresh")?.addEventListener("click", function() { _adminSessionPage = 1; fetchAdminSessions(); });
    $("#adminSessionActiveOnly")?.addEventListener("change", function() { _adminSessionPage = 1; fetchAdminSessions(); });
    $("#adminSessionPagePrev")?.addEventListener("click", adminSessionPrev);
    $("#adminSessionPageNext")?.addEventListener("click", adminSessionNext);
    // Phase 6: Anomaly panel
    $("#adminAnomalyRefresh")?.addEventListener("click", fetchAdminAnomalies);

    // Command hint chips: click to fill input with command template
    $$("#commandHints .command-hint-chip").forEach((chip) => chip.addEventListener("click", () => {
      const prefix = chip.dataset.cmd || "";
      const input = $("#chatInput");
      input.value = prefix;
      input.focus();
      // Place cursor at end of the template text
      input.setSelectionRange(input.value.length, input.value.length);
      autoResizeChatInput();
      updateChatSendButton();
    }));

    $("#knowledgeImportForm").addEventListener("submit", (event) => { void importKnowledgeFile(event); });
    $$("[data-open-knowledge-import]").forEach((button) => button.addEventListener("click", () => openKnowledgeImport()));
    $("#refreshKnowledge").addEventListener("click", () => {
      fetchKnowledgeMappings(state.kbFilter, $("#kbSearchInput").value).catch((error) => console.warn("Knowledge refresh failed.", error));
    });
    $$("#knowledge .knowledge-tabs button").forEach((button) => button.addEventListener("click", () => {
      $$("#knowledge .knowledge-tabs button").forEach((item) => item.classList.remove("active")); button.classList.add("active");
      state.kbFilter = button.dataset.kbFilter;
      fetchKnowledgeMappings(state.kbFilter, $("#kbSearchInput").value).catch((error) => {
        console.warn("Knowledge list stayed local.", error);
        renderKnowledge();
      });
    }));
    $("#kbSearchInput").addEventListener("input", (event) => {
      const query = event.target.value;
      fetchKnowledgeMappings(state.kbFilter, query).catch((error) => {
        console.warn("Knowledge search stayed local.", error);
        renderKnowledge(state.kbFilter, query);
      });
    });
    $("#eventDeleteButton").addEventListener("click", () => deleteEditingEvent());
    $("#eventForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      const title = $("#eventName").value.trim();
      const date = $("#eventDate").value;
      const tone = $("[name=\"eventTone\"]:checked").value;
      if (title && date) {
        const payload = { title, date, tone };
        if (state.editingEventIndex === null) {
          try {
            state.events.push(await createEventRemote(payload));
          } catch (error) {
            console.warn("Calendar create stayed local.", error);
            state.events.push({ title, date, tone });
          }
        } else {
          const current = state.events[state.editingEventIndex];
          const nextEvent = { ...current, ...payload };
          if (current?.id) {
            try {
              state.events[state.editingEventIndex] = await updateEventRemote(nextEvent);
            } catch (error) {
              console.warn("Calendar update stayed local.", error);
              state.events[state.editingEventIndex] = { title, date, tone };
            }
          } else {
            state.events[state.editingEventIndex] = { title, date, tone };
          }
        }
        saveEvents();
        const wasEditing = state.editingEventIndex !== null;
        state.editingEventIndex = null;
        $("#eventModal").classList.remove("show");
        event.target.reset();
        state.selectedScheduleDate = date;
        renderCalendar(); renderWorkbenchSchedule(); renderMiniCalendar("portalMonth");
        renderWorkbenchOverview();
        showToast(wasEditing ? "日程已更新" : "日程已保存");
      }
    });

    updatePlatformTime();
    window.setInterval(updatePlatformTime, 1000);
    window.setInterval(renderNotifications, 5000);
    renderTasks();
    renderNotifications();
    renderShortcuts();
    renderWorkbenchSchedule();
    renderPortal();
    syncProfileUI();
    renderCalendar();
    renderKnowledge();
    renderChatSessions();
    renderChatTranscript();
    updateChatSendButton();
    renderKnowledgeSubTabs();
    bindEmbeds();
    _initAuthReady.then(function() {
      fetchPortalBootstrap();
      fetchChatSessionsFromBackend();
      fetchKnowledgeMappings().catch(function(error) { console.warn("Knowledge mappings unavailable.", error); });
      fetchKnowledgeImports().catch(function(error) { console.warn("Knowledge imports unavailable.", error); });
    });
    updateMonthTitles();
    setView(window.location.hash.replace("#", "") || state.activeView, { isInit: true });
    bindToasts();
