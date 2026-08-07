# HR 智能工作台 — 系统架构

## 一、整体架构

```
┌──────────────────────────────────────────────────────────────┐
│                     Nginx (:80)                               │
│  静态资源缓存 + SPA路由 + API反向代理 + 速率限制 + 安全头     │
└──────────────────────┬───────────────────────────────────────┘
                       │ /api/*
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                  FastAPI (:8000)                               │
│  ┌──────────┬───────────┬───────────┬──────────────────────┐ │
│  │ Auth     │ RBAC      │ Audit     │ AI Security Firewall │ │
│  │ JWT+bcrypt│ 53 perms │ middleware│ injection/sanitizer  │ │
│  └──────────┴───────────┴───────────┴──────────────────────┘ │
│  ┌──────────┬───────────┬───────────┬──────────────────────┐ │
│  │ Routers  │ Stores    │ Hermes    │ Knowledge (FastGPT)  │ │
│  │ admin/   │ Mixin层   │ Gateway   │ RAG + scope filter   │ │
│  │ enterprise│           │ (DeepSeek)│                       │ │
│  └──────────┴───────────┴───────────┴──────────────────────┘ │
└──────────────────────┬───────────────────────────────────────┘
                       │ SQLAlchemy ORM
                       ▼
┌──────────────────────────────────────────────────────────────┐
│              PostgreSQL 16 + pgvector                         │
│  14 Alembic migrations  │  3-dim data scope (SQL filter)     │
└──────────────────────────────────────────────────────────────┘
```

## 二、核心技术决策

### RBAC + 数据隔离
- **5 角色**: super_admin, org_admin, dept_leader, dept_staff, external
- **54 权限码**: 18 组 (admin_users, admin_roles, admin_audit, admin_news, admin_notices, portal, oa, hr, finance, asset, repair, knowledge, chat, notifications, tasks, calendar, integrations, search)
- **3 维度数据隔离**: org → dept → owner，SQL 查询层自动注入 WHERE 条件
- **JWT 双 token**: access_token (15min) + refresh_token (7d, HttpOnly cookie)

### 后端架构
- **Mixin 模式 Store**: `PortalStore` 继承 `PortalMixin`, `SubsystemMixin`, `SearchMixin` 等
- **审计日志**: 中间件自动记录 + 显式 `audit_log()` 调用，90 天保留
- **AI 安全**: 注入检测 (SQL/命令/路径遍历) + 查询脱敏 + 速率限制

### 前端架构
- **无框架 SPA**: 原生 Web Components (8 个组件)，hash 路由
- **认证 Context**: `authContext.ts` 管理 token + 权限 + 刷新逻辑
- **响应式**: 3 断点 (>1024 / 768-1024 / <768)

### 部署架构
- **4 容器**: postgres + api (FastAPI) + nginx + pgbackup (6h 自动备份)
- **安全**: Nginx 安全头 (CSP, HSTS, X-Frame, XSS) + 速率限制 + 非 root 用户
- **健康检查**: 3 级 (liveness 200 / readiness DB check 503 / 异常处理器 JSON)

## 三、数据模型（核心表）

```
orgs ─── departments
 │              │
 ├── user_org_memberships
 └── user_department_memberships
          │
       users ─── role_bindings ─── roles ─── role_permissions ─── permissions
          │
 ┌────────┼────────┬──────────┬──────────────┬──────────────┐
 │        │         │          │              │              │
tasks  enterprise_ enterprise_ enterprise_   notifications
       repair_     asset_      oa_flows
       tickets     items
```

## 四、子系统拓扑

| 状态 | 子系统 | 编码 | 后端路由 | 前端视图 |
|------|--------|------|----------|----------|
| active | 办公行政(OA) | oa | enterprise.py | views/oa.js |
| active | 督办管理 | supervision | enterprise.py | — |
| active | 人力资源(HR) | hr | enterprise.py | views/hr.js |
| active | 财务管理 | finance | enterprise.py | views/finance.js |
| active | 维修服务 | repair | enterprise.py | views/repair.js |
| active | 数据中台 | data-portal | enterprise.py | views/data-portal.js |
| disabled | 招聘管理 | recruitment | — | — |
| disabled | 培训发展 | training | — | — |
| disabled | 员工关怀 | wellness | — | — |
| disabled | 客户关系(CRM) | crm | — | — |
| disabled | 企业资源(ERP) | erp | — | — |
| disabled | 服务台 | service-desk | — | — |
| disabled | 供应链 | supply-chain | — | — |
| disabled | 固定资产 | fixed-assets | — | — |
| disabled | 厂区物业 | facility | — | — |
| disabled | 党建风控 | party | — | — |

> **注意**: 以下子系统已在 migration 014 中移除（STALE_CODES）：
> teaching-cloud, website, alumni, student, employment, mental-health, estate, assets
> 对应的前端视图 asset.js, employment.js, estate.js, website.js 已删除。

## 五、API 层级

```
GET  /health                          # 健康检查
POST /api/v1/auth/login               # JWT 登录
POST /api/v1/auth/refresh             # Token 刷新

GET  /api/v1/subsystems               # 子系统列表
GET  /api/v1/portal/bootstrap         # 门户启动数据

GET  /api/v1/enterprise/{module}/*    # 企业模块 CRUD
GET  /api/v1/enterprise/export/{entity} # CSV 导出

GET  /api/v1/knowledge/*              # 知识库 (FastGPT RAG)
GET  /api/v1/chat/*                   # AI 聊天 (Hermes)
GET  /api/v1/search                   # 跨源搜索

GET  /api/v1/tasks/*                  # 任务管理 (CRUD)
GET  /api/v1/calendar/events/*        # 日程管理 (CRUD)
GET  /api/v1/notifications/*          # 通知中心 + SSE push
GET  /api/v1/integrations/*           # 第三方集成 (飞书/钉钉)

GET  /api/v1/admin/*                  # 管理后台 (CRUD + 审计)
POST /auth/register                   # 用户注册
POST /auth/change-password            # 修改密码
```

## 六、关键文件

| 文件 | 职责 |
|------|------|
| `backend/main.py` | FastAPI 应用入口，中间件注册 |
| `backend/store.py` | PortalStore 单体 |
| `backend/auth/dependencies.py` | 认证依赖注入 |
| `backend/authorization/sql_filters.py` | 数据隔离 SQL WHERE 注入 |
| `backend/audit/middleware.py` | 请求级审计日志 |
| `backend/audit/logger.py` | 审计日志写入 + 过期清理 |
| `backend/ai_security/firewall.py` | AI 注入防火墙 |
| `backend/gateway_errors.py` | 共享网关错误类型与 httpx 映射 |
| `frontend/src/app.js` | 主应用 |
| `frontend/src/components/` | 8 个 UI 组件模块 |
| `frontend/biome.json` | 前端代码规范配置 |
| `docker/compose.yml` | 生产 4 容器编排 |
| `.github/workflows/ci.yml` | CI/CD 流水线 |
