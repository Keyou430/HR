# Replica RBAC v2.0 权限矩阵

> 版本 v1.0 | 2026-07-30 | 依据: rbac-design-v2.md  
> 状态: Phase 0 基线冻结，后续不随意改名

---

## 一、完整 API 清单

### 1.1 健康检查

| 方法 | 路径 | 文件 | 当前认证 | 目标认证 | 所需权限 | 数据范围 |
|------|------|------|----------|----------|----------|----------|
| GET | `/health` | main.py:42 | ❌ 无 | public | — | — |

### 1.2 门户 Bootstrap

| 方法 | 路径 | 文件 | 当前认证 | 目标认证 | 所需权限 | 数据范围 |
|------|------|------|----------|----------|----------|----------|
| GET | `/api/v1/portal/bootstrap` | portal.py:57 | ❌ 无 | authenticated | — | 按用户返回 |

### 1.3 任务 (Tasks)

| 方法 | 路径 | 文件 | 当前认证 | 目标认证 | 所需权限 | 数据范围 |
|------|------|------|----------|----------|----------|----------|
| GET | `/api/v1/tasks` | tasks.py:10 | ❌ 无 | authenticated | `task:view` | own/dept/org/public |
| POST | `/api/v1/tasks` | tasks.py:15 | ❌ 无 | authenticated | `task:create` | — (owner = current user) |
| PATCH | `/api/v1/tasks/{task_id}` | tasks.py:20 | ❌ 无 | authenticated | `task:update` | own/dept/org |
| DELETE | `/api/v1/tasks/{task_id}` | tasks.py:28 | ❌ 无 | authenticated | `task:delete` | own/dept/org |
| POST | `/api/v1/tasks/clear-done` | tasks.py:35 | ❌ 无 | authenticated | `task:delete` | own |

### 1.4 日历 (Calendar)

| 方法 | 路径 | 文件 | 当前认证 | 目标认证 | 所需权限 | 数据范围 |
|------|------|------|----------|----------|----------|----------|
| GET | `/api/v1/calendar/events` | calendar_api.py:10 | ❌ 无 | authenticated | `calendar:view` | own/dept/org/public |
| POST | `/api/v1/calendar/events` | calendar_api.py:15 | ❌ 无 | authenticated | `calendar:create` | — (owner = current user) |
| PUT | `/api/v1/calendar/events/{event_id}` | calendar_api.py:20 | ❌ 无 | authenticated | `calendar:update` | own/dept/org |
| DELETE | `/api/v1/calendar/events/{event_id}` | calendar_api.py:28 | ❌ 无 | authenticated | `calendar:delete` | own/dept/org |

### 1.5 知识库 (Knowledge)

| 方法 | 路径 | 文件 | 当前认证 | 目标认证 | 所需权限 | 数据范围 |
|------|------|------|----------|----------|----------|----------|
| GET | `/api/v1/knowledge/spaces` | knowledge.py:26 | ❌ 无 | authenticated | `kb:view` | org/dept/owner/visibility/sensitivity |
| GET | `/api/v1/knowledge/mappings` | knowledge.py:34 | ❌ 无 | authenticated | `kb:view` | org/dept/owner/visibility/sensitivity |
| PATCH | `/api/v1/knowledge/mappings/{mapping_id}` | knowledge.py:39 | ❌ 无 | authenticated | `kb:update` | org/dept/owner |
| DELETE | `/api/v1/knowledge/mappings/{mapping_id}` | knowledge.py:47 | ❌ 无 | authenticated | `kb:delete` | org/dept/owner |
| GET | `/api/v1/knowledge/imports` | knowledge.py:54 | ❌ 无 | authenticated | `kb:view` | org/dept/owner |
| POST | `/api/v1/knowledge/sync` | knowledge.py:59 | ❌ 无 | authenticated | `kb:import` | org/dept/owner |
| POST | `/api/v1/knowledge/chat` | knowledge.py:294 | ❌ 无 | authenticated | `kb:chat` | org/dept/owner/visibility/sensitivity |
| POST | `/api/v1/knowledge/import` | knowledge.py:408 | ❌ 无 | authenticated | `kb:import` | org/dept/owner |
| GET | `/api/v1/knowledge/datasets/{dataset_id}/files` | knowledge.py:638 | ❌ 无 | authenticated | `kb:view` | org/dept/owner |
| DELETE | `/api/v1/knowledge/datasets/{dataset_id}/files/{file_id}` | knowledge.py:669 | ❌ 无 | authenticated | `kb:delete` | org/dept/owner |

### 1.6 搜索 (Search)

| 方法 | 路径 | 文件 | 当前认证 | 目标认证 | 所需权限 | 数据范围 |
|------|------|------|----------|----------|----------|----------|
| GET | `/api/v1/search` | search.py:9 | ❌ 无 | authenticated | `search:view` | org/dept/owner/visibility/sensitivity |

### 1.7 集成配置 (Integrations)

| 方法 | 路径 | 文件 | 当前认证 | 目标认证 | 所需权限 | 数据范围 |
|------|------|------|----------|----------|----------|----------|
| GET | `/api/v1/integrations/embed-urls` | integrations.py:10 | ❌ 无 | authenticated | `org:view` | org |
| PUT | `/api/v1/integrations/embed-urls` | integrations.py:15 | ❌ 无 | authenticated | `org:update` | org |

### 1.8 聊天会话 (Chat Sessions)

| 方法 | 路径 | 文件 | 当前认证 | 目标认证 | 所需权限 | 数据范围 |
|------|------|------|----------|----------|----------|----------|
| GET | `/api/v1/chat/sessions` | chat_api.py:11 | ❌ 无 | authenticated | — (user own data) | own |
| GET | `/api/v1/chat/sessions/{session_id}/messages` | chat_api.py:17 | ❌ 无 | authenticated | — (user own data) | own |
| POST | `/api/v1/chat/messages` | chat_api.py:23 | ❌ 无 | authenticated | — (user own data) | own |
| DELETE | `/api/v1/chat/sessions/{session_id}` | chat_api.py:37 | ❌ 无 | authenticated | — (user own data) | own |

---

## 二、角色-权限映射矩阵

### 2.1 角色定义

| 角色 code | 说明 |
|-----------|------|
| `super_admin` | 平台超级管理员 |
| `org_admin` | 组织管理员 |
| `dept_leader` | 部门负责人 |
| `dept_staff` | 部门员工 |
| `external` | 外部用户 |

### 2.2 权限 × 角色矩阵

> ✅ = 显式授予  ❌ = 未授予  🔶 = 数据范围进一步限制

| 权限 code | super_admin | org_admin | dept_leader | dept_staff | external |
|-----------|-------------|-----------|-------------|------------|----------|
| `user:view` | ✅ | ✅ (本组织) | 🔶 (本部门) | ❌ | ❌ |
| `user:create` | ✅ | ✅ (本组织) | ❌ | ❌ | ❌ |
| `user:update` | ✅ | ✅ (本组织) | ❌ | ❌ | ❌ |
| `user:disable` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `user:assign_role` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `org:view` | ✅ | ✅ (本组织) | 🔶 (本部门) | 🔶 | ❌ |
| `org:update` | ✅ | ✅ (本组织) | ❌ | ❌ | ❌ |
| `dept:view` | ✅ | ✅ (本组织) | ✅ (本部门及下级) | 🔶 (本部门) | ❌ |
| `dept:update` | ✅ | ✅ (本组织) | ❌ | ❌ | ❌ |
| `system:config` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `audit:view` | ✅ | ✅ (本组织) | ❌ | ❌ | ❌ |
| `task:view` | ✅ | ✅ (本组织) | ✅ (本部门及下级) | ✅ (own) | 🔶 (public only) |
| `task:create` | ✅ | ✅ (本组织) | ✅ (本部门) | ✅ | ❌ |
| `task:update` | ✅ | ✅ (本组织) | ✅ (本部门) | ✅ (own) | ❌ |
| `task:delete` | ✅ | ✅ (本组织) | ✅ (本部门) | ✅ (own) | ❌ |
| `calendar:view` | ✅ | ✅ (本组织) | ✅ (本部门及下级) | ✅ (own) | 🔶 (public only) |
| `calendar:create` | ✅ | ✅ (本组织) | ✅ (本部门) | ✅ | ❌ |
| `calendar:update` | ✅ | ✅ (本组织) | ✅ (本部门) | ✅ (own) | ❌ |
| `calendar:delete` | ✅ | ✅ (本组织) | ✅ (本部门) | ✅ (own) | ❌ |
| `kb:view` | ✅ | ✅ (本组织) | ✅ (本部门及下级) | ✅ (own/dept) | 🔶 (public only) |
| `kb:create` | ✅ | ✅ (本组织) | ❌ | ❌ | ❌ |
| `kb:update` | ✅ | ✅ (本组织) | ✅ (本部门) | ❌ | ❌ |
| `kb:delete` | ✅ | ✅ (本组织) | ❌ | ❌ | ❌ |
| `kb:import` | ✅ | ✅ (本组织) | ✅ (本部门) | ❌ | ❌ |
| `kb:chat` | ✅ | ✅ (本组织) | ✅ (本部门) | ✅ (authorized KB) | ❌ |
| `kb:chat_sensitive` | ✅ | ✅ (本组织) | ❌ | ❌ | ❌ |
| `search:view` | ✅ | ✅ (本组织) | ✅ (本部门及下级) | ✅ (own/dept) | 🔶 (public only) |
| `notice:view` | ✅ | ✅ (本组织) | ✅ (本部门及下级) | ✅ (own/dept) | 🔶 (public only) |
| `notice:create` | ✅ | ✅ (本组织) | ✅ (本部门) | ❌ | ❌ |
| `notice:update` | ✅ | ✅ (本组织) | ✅ (本部门) | ❌ | ❌ |
| `notice:delete` | ✅ | ✅ (本组织) | ❌ | ❌ | ❌ |

---

## 三、数据范围策略

### 3.1 策略定义

| 数据范围 | 含义 | SQL 过滤逻辑 |
|----------|------|-------------|
| `own` | 仅本人创建/拥有的数据 | `owner_id = :current_user_id` |
| `dept` | 本部门及下级部门数据 | `department_id IN (:visible_dept_ids)` |
| `org` | 本组织数据 | `org_id = :current_org_id` |
| `public` | 所有已登录用户或外部用户可见 | `visibility = 'public'` |

### 3.2 各角色默认数据范围

| 角色 | 查看范围 | 修改范围 | 删除范围 |
|------|----------|----------|----------|
| `super_admin` | 全平台 | 全平台 | 全平台 |
| `org_admin` | 本组织 (org) | 本组织 | 本组织 |
| `dept_leader` | 本部门 + 下级部门 (dept) + public | 本部门 + 下级部门 | 本部门 |
| `dept_staff` | own + dept (只读) + public | own | own |
| `external` | public only | — | — |

### 3.3 各业务资源可见性默认值

| 资源 | visibility 默认 | sensitivity 默认 | 说明 |
|------|----------------|------------------|------|
| 任务 (tasks) | `private` | `normal` | 默认仅 owner 可见 |
| 日历 (calendar events) | `private` | `normal` | 默认仅 owner 可见 |
| 知识库映射 (knowledge mappings) | `dept` | `internal` | 默认部门可见 |
| 搜索 (search results) | 继承源资源 | 继承源资源 | 按源资源过滤 |

---

## 四、当前安全状态 (Phase 0 基线)

### 4.1 当前缺失

所有业务端点目前均为 **无需认证即可访问**：
- ❌ 无身份认证机制
- ❌ 无 JWT / Access Token
- ❌ 无 Refresh Token / 会话管理
- ❌ 无 RBAC 功能权限检查
- ❌ 无对象级数据隔离 (IDOR 防护)
- ❌ 无组织/部门数据隔离
- ❌ AI 知识库 /chat 无授权检索
- ❌ 无审计日志

### 4.2 当前已知风险

| 风险 | 严重度 | 涉及端点 |
|------|--------|----------|
| 任意用户可读取/修改/删除所有任务 | P0 | `/api/v1/tasks/*` |
| 任意用户可读取/修改/删除所有日历事件 | P0 | `/api/v1/calendar/events/*` |
| 任意用户可修改知识库映射和导入文件 | P0 | `/api/v1/knowledge/mappings/*`, `/api/v1/knowledge/import` |
| 任意用户可直接调用 AI 知识库问答 | P1 | `/api/v1/knowledge/chat` |
| 任意用户可修改集成嵌入 URL | P1 | `/api/v1/integrations/embed-urls` |
| 任意用户可访问/删除任意聊天会话 | P1 | `/api/v1/chat/sessions/*` |
| 知识库同步无权限控制 | P1 | `/api/v1/knowledge/sync` |
| 搜索结果无数据范围过滤 | P1 | `/api/v1/search` |
| bootstrap 返回全量数据，无用户区分 | P2 | `/api/v1/portal/bootstrap` |

---

## 五、API-权限映射速查 (用于 Phase 3 实现)

```python
# Endpoints requiring a specific permission code (Phase 3).
ENDPOINT_PERMISSION_MAP: dict[tuple[str, str], str | None] = {
    # -- tasks --
    ("GET",    "/api/v1/tasks"):                              "task:view",
    ("POST",   "/api/v1/tasks"):                              "task:create",
    ("PATCH",  "/api/v1/tasks/{task_id}"):                    "task:update",
    ("DELETE", "/api/v1/tasks/{task_id}"):                    "task:delete",
    ("POST",   "/api/v1/tasks/clear-done"):                   "task:delete",
    # -- calendar --
    ("GET",    "/api/v1/calendar/events"):                     "calendar:view",
    ("POST",   "/api/v1/calendar/events"):                     "calendar:create",
    ("PUT",    "/api/v1/calendar/events/{event_id}"):          "calendar:update",
    ("DELETE", "/api/v1/calendar/events/{event_id}"):          "calendar:delete",
    # -- knowledge --
    ("GET",    "/api/v1/knowledge/spaces"):                    "kb:view",
    ("GET",    "/api/v1/knowledge/mappings"):                  "kb:view",
    ("PATCH",  "/api/v1/knowledge/mappings/{mapping_id}"):     "kb:update",
    ("DELETE", "/api/v1/knowledge/mappings/{mapping_id}"):     "kb:delete",
    ("GET",    "/api/v1/knowledge/imports"):                   "kb:view",
    ("POST",   "/api/v1/knowledge/sync"):                      "kb:import",
    ("POST",   "/api/v1/knowledge/chat"):                      "kb:chat",
    ("POST",   "/api/v1/knowledge/import"):                    "kb:import",
    ("GET",    "/api/v1/knowledge/datasets/{dataset_id}/files"): "kb:view",
    ("DELETE", "/api/v1/knowledge/datasets/{dataset_id}/files/{file_id}"): "kb:delete",
    # -- search --
    ("GET",    "/api/v1/search"):                              "search:view",
    # -- integrations --
    ("GET",    "/api/v1/integrations/embed-urls"):             "org:view",
    ("PUT",    "/api/v1/integrations/embed-urls"):             "org:update",
}

# Endpoints requiring authentication but NO specific permission code.
# These need Depends(get_current_user) but not PermissionChecker.
AUTHENTICATED_ONLY_ENDPOINTS: set[tuple[str, str]] = {
    ("GET",  "/api/v1/portal/bootstrap"),
    ("GET",  "/api/v1/chat/sessions"),
    ("GET",  "/api/v1/chat/sessions/{session_id}/messages"),
    ("POST", "/api/v1/chat/messages"),
    ("DELETE", "/api/v1/chat/sessions/{session_id}"),
}

# Public endpoints — no authentication required.
PUBLIC_ENDPOINTS: set[tuple[str, str]] = {
    ("GET", "/health"),
}
```
