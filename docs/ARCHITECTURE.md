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
│  11 Alembic migrations  │  3-dim data scope (SQL filter)     │
└──────────────────────────────────────────────────────────────┘
```

## 二、核心技术决策

### RBAC + 数据隔离
- **5 角色**: super_admin, org_admin, dept_leader, dept_staff, external
- **53 权限码**: 9 组 (admin, portal, oa, hr, finance, asset, repair, knowledge, chat)
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
organizations ─── departments
     │                │
     ├── user_org_memberships
     └── user_department_memberships
              │
           users ─── user_role_bindings ─── roles ─── role_permissions ─── permissions
              │
     ┌────────┼────────┬──────────┬──────────┐
     │        │         │          │          │
  tasks   repair_    assets   oa_forms  notifications
          orders
```

## 四、子系统拓扑

| 类型 | 子系统 | 后端路由 | 前端视图 |
|------|--------|----------|----------|
| internal | OA | enterprise.py | views/oa.js |
| internal | HR | enterprise.py | views/hr.js |
| internal | Finance | enterprise.py | views/finance.js |
| internal | Asset | enterprise.py | views/asset.js |
| internal | Repair | enterprise.py | views/repair.js |
| internal | Website | enterprise.py | views/website.js |
| internal | Estate | enterprise.py | views/estate.js |
| internal | Employment | enterprise.py | views/employment.js |
| internal | Data Portal | enterprise.py | views/data-portal.js |
| iframe | Teaching Cloud | — | index.html iframe |
| disabled | Party/Alumni/Student/Mental | — | — |

## 五、API 层级

```
GET  /health                          # 健康检查
POST /api/v1/auth/login               # JWT 登录
POST /api/v1/auth/refresh             # Token 刷新

GET  /api/v1/subsystems               # 子系统列表
GET  /api/v1/portal/bootstrap         # 门户启动数据

GET  /api/v1/enterprise/{module}/*    # 企业模块 CRUD (13 模块)
GET  /api/v1/enterprise/export/{entity} # CSV 导出

GET  /api/v1/knowledge/*              # 知识库 (FastGPT RAG)
GET  /api/v1/chat/*                   # AI 聊天 (Hermes)
GET  /api/v1/search                   # 跨源搜索

GET  /api/v1/admin/*                  # 管理后台 (CRUD + 审计)
```

## 六、关键文件

| 文件 | 职责 |
|------|------|
| `backend/main.py` | FastAPI 应用入口，中间件注册 |
| `backend/store.py` | PortalStore 单体 |
| `backend/auth/dependencies.py` | 认证依赖注入 |
| `backend/authorization/sql_filters.py` | 数据隔离 SQL WHERE 注入 |
| `backend/audit/middleware.py` | 请求级审计日志 |
| `backend/ai_security/firewall.py` | AI 注入防火墙 |
| `frontend/src/app.js` | 主应用 |
| `frontend/src/components/` | 8 个 Web Components |
| `docker/compose.yml` | 生产 4 容器编排 |
| `.github/workflows/ci.yml` | CI/CD 流水线 |
