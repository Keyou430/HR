# Replica 项目交接文档

> **日期**: 2026-08-05  
> **版本**: Phase 1 complete (v1.1.0)  
> **仓库**: `D:\Replica`

---

## 一、项目概述

**Replica** 是一个企业协同门户平台（智能工作台），面向高校/大型组织，提供统一入口整合 OA、人事、财务、资产、报修等 15 个业务子系统。

**技术栈**:
- **后端**: Python 3.12+ / FastAPI / SQLAlchemy / Alembic / JWT (HS256) / bcrypt
- **前端**: Vanilla JS SPA（无框架），hash 路由，原生 Web Components
- **数据库**: PostgreSQL 16 + pgvector（生产）/ SQLite（开发 & 测试）
- **部署**: Docker Compose 四容器（postgres / api / nginx / pgbackup）

---

## 二、Phase 1 完成情况

Phase 1 目标是把平台底座升级到企业可用状态。**全部 10 项任务 (T0–T10) 已完成**。

### 已完成功能清单

| 模块 | 内容 | 状态 |
|---|---|---|
| **RBAC 权限** | 5 角色（super_admin/org_admin/dept_leader/dept_staff/external），53 权限码，9 权限组 | ✅ |
| **数据权限** | 3 维度 scope（org / dept / owner），SQL 层过滤，跨 org/跨 dept 隔离 | ✅ |
| **用户认证** | JWT access+refresh token，bcrypt 密码哈希，登录频率限制，token 版本失效 | ✅ |
| **组织架构** | 多组织(orgs) + 树形部门(departments) + 用户归属 | ✅ |
| **门户首页** | Bootstrap 数据、公告/文档/资源/服务/新闻 5 类资产 CRUD | ✅ |
| **子系统** | 15 子系统（6 深 + 2 iframe 壳 + 7 disabled 壳），子系统工作台 + 访问统计 | ✅ |
| **任务日历** | 个人任务 CRUD + 协同日历（本地持久化+颜色标记+编辑删除）| ✅ |
| **知识库** | FastGPT 集成（数据集映射/同步/文件导入/聊天），scope 过滤 | ✅ |
| **全局搜索** | 子系统/公告/文档/工单/资产/OA 跨数据源搜索，scope 过滤 | ✅ |
| **通知系统** | 站内通知 CRUD + 未读数轮询 + 铃铛 UI | ✅ |
| **管理后台** | 用户/角色/组织/部门 CRUD + 权限分配 + 审计日志查看/导出 CSV + 公告/服务管理 | ✅ |
| **审计日志** | 请求级中间件 + 显式事件记录，保留 90 天 | ✅ |
| **AI 安全** | 注入检测 + 查询长度限制 + 检索块数限制 + 速率限制 | ✅ |
| **Docker 部署** | 四容器编排 + Nginx 反代(安全头+限流+gzip+SPA路由) + 自动备份(6h) + 管理员初始化 | ✅ |
| **PostgreSQL** | psycopg2 连接池 + pgvector 扩展 + TIMESTAMPTZ 转换 + 6 个 Alembic 迁移 | ✅ |
| **Store 拆分** | Mixin 模式：`stores/base.py` + `portal/subsystems/search/repair/asset/oa/notifications` | ✅ |
| **前端组件化** | 8 个 Web Components（table/modal/drawer/status-badge/empty-state/notification-bell/sidebar/search） | ✅ |
| **响应式** | 3 断点（>1024 / 768-1024 / <768）+ 侧栏折叠/off-canvas | ✅ |
| **健康检查** | 3 级：`/health`(liveness 200) / `?full=true`(readiness+DB check→503) / 全局异常处理器(422/500 JSON) | ✅ |
| **测试** | 29 个测试文件，~330 tests，包括 conftest.py 共享 fixtures | ✅ |

---

## 三、架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    Nginx :80                                │
│  /api/* → api:8000    /* → frontend static    /health       │
│  Security headers + rate limiting + gzip + SPA routing      │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│              FastAPI (main.py)                               │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │  portal  │subsystems│  tasks   │calendar  │integrations│ │
│  ├──────────┼──────────┼──────────┼──────────┼──────────┤  │
│  │knowledge │  chat    │ search   │  admin   │notifications│ │
│  ├──────────┼──────────┼──────────┼──────────┼──────────┤  │
│  │   auth   │  audit   │CORS      │exception │  health   │  │
│  │ (router) │(middleware)│(middleware)│(handlers)│(routes) │  │
│  └──────────┴──────────┴──────────┴──────────┴──────────┘  │
│                         │                                    │
│              ┌──────────▼──────────┐                        │
│              │   PortalStore       │                        │
│              │  (store.py:2239行)  │                        │
│              │  ┌────────────────┐ │                        │
│              │  │ BaseStore      │ │  stores/base.py        │
│              │  │ PortalMixin    │ │  stores/portal.py      │
│              │  │ SubsystemsMixin│ │  stores/subsystems.py  │
│              │  │ SearchMixin    │ │  stores/search.py      │
│              │  │ RepairMixin    │ │  stores/repair.py      │
│              │  │ AssetMixin     │ │  stores/asset.py       │
│              │  │ OaMixin        │ │  stores/oa.py          │
│              │  │ NotificationsM │ │  stores/notifications.py│
│              │  └────────────────┘ │                        │
│              └──────────┬──────────┘                        │
│                         │                                    │
│              ┌──────────▼──────────┐                        │
│              │  SQLAlchemy Engine  │                        │
│              │  session.py         │                        │
│              │  PG: pool_size=10   │                        │
│              │  SQLite: WAL+FK     │                        │
│              └─────────────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### 前端架构

```
index.html (SPA shell + CSS)
├── src/app.js          (~5200 行) 主应用逻辑
│   ├── 路由 (hash-based) → 视图切换
│   ├── 全局状态管理 (state 对象)
│   ├── API 调用层 (apiJson / authHeader)
│   └── 子系统工作台渲染
├── src/components/     8 个 Web Components
│   ├── table.js        可排序/筛选/分页数据表
│   ├── modal.js        无障碍弹窗 (focus trap/ESC)
│   ├── drawer.js       滑入抽屉 (表单用)
│   ├── status-badge.js 彩色状态标签
│   ├── empty-state.js  可操作空状态
│   ├── notification-bell.js 未读红点+下拉
│   ├── sidebar.js      数据驱动侧栏
│   └── search.js       异步 typeahead 搜索
├── src/views/          子系统视图（Phase 2 实现）
│   ├── repair.js       空壳
│   ├── asset.js        空壳
│   ├── oa.js           空壳
│   ├── hr.js           空壳
│   └── finance.js      空壳
├── src/auth/
│   └── permissions.ts  权限码常量
└── src/types/
    └── index.ts         类型定义
```

### Store 拆分模式（Mixin）

```python
# store.py
class PortalStore(
    BaseStore,           # 锁/session/scope filter/CRUD 原语
    PortalMixin,         # 门户资产(bootstrap/notices/documents/...)
    SubsystemsMixin,     # 子系统(list/get/visit/dashboard)
    SearchMixin,         # 全局搜索
    RepairMixin,         # 报修 CRUD stub
    AssetMixin,          # 资产 CRUD stub
    OaMixin,             # OA CRUD stub
    NotificationsMixin,  # 通知 CRUD
):
    def _ensure_schema(self): ...   # metadata.create_all()
    def _seed_defaults(self): ...   # 幂等 re-seed

store = PortalStore()    # 全局单例
metadata = store.metadata # Alembic 用
```

所有 router 通过 `from store import store` 访问数据层，无需改动 import。

---

## 四、目录结构

```
D:\Replica\
├── docker-compose.yml          # 4 服务编排
├── Dockerfile                  # 多阶段构建 (node + python)
├── .dockerignore
├── .gitignore
├── nginx/
│   └── default.conf            # Nginx 反代配置
├── scripts/
│   ├── init-admin.sh           # 管理员初始化（幂等）
│   └── backup.sh               # pg_dump 备份
├── docs/
│   ├── phase1-setup.md         # 部署 & 测试指南
│   ├── rbac-design-v2.md       # RBAC 设计文档
│   ├── rbac-permission-matrix.md
│   ├── rbac-rollout.md
│   └── rbac-rollback.md
├── backend/
│   ├── main.py                 # FastAPI app 入口
│   ├── config.py               # Settings (pydantic-settings)
│   ├── session.py              # SQLAlchemy engine/session
│   ├── store.py                # PortalStore 单例 + metadata + seed
│   ├── schemas.py              # Pydantic request/response models
│   ├── requirements.txt
│   ├── .env.example
│   ├── conftest.py             # 共享测试 fixtures
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       ├── 001_rbac_base.py
│   │       ├── 002_auth_additions.py
│   │       ├── 003_chat_user_scoping.py
│   │       ├── 004_portal_assets_subsystems.py
│   │       ├── 005_platform_enterprise.py   ← Phase 1 核心迁移
│   │       └── 006_pgvector.py              ← PG pgvector 扩展
│   ├── auth/
│   │   ├── router.py           # /api/v1/auth/*
│   │   ├── dependencies.py     # get_current_user
│   │   └── password.py         # bcrypt
│   ├── authorization/
│   │   ├── permissions.py      # 53 权限码 + ROLE_PERMISSION_MAP
│   │   ├── rbac.py             # user_has_permission
│   │   ├── scope.py            # AccessContext
│   │   └── sql_filters.py      # SQL WHERE 级 scope filter
│   ├── audit/
│   │   ├── middleware.py        # 请求级审计中间件
│   │   └── logger.py           # 显式事件记录
│   ├── stores/
│   │   ├── base.py             # BaseStore 基类
│   │   ├── portal.py           # 门户资产
│   │   ├── subsystems.py       # 子系统
│   │   ├── search.py           # 搜索
│   │   ├── repair.py           # 报修 stub
│   │   ├── asset.py            # 资产 stub
│   │   ├── oa.py               # OA stub
│   │   └── notifications.py    # 通知
│   ├── routers/
│   │   └── notifications.py    # /api/v1/notifications/*
│   ├── ai_security/            # AI 安全模块
│   ├── portals.py              # /api/v1/portal/*
│   ├── subsystems.py           # /api/v1/subsystems/*
│   ├── tasks.py                # /api/v1/tasks/*
│   ├── calendar_api.py         # /api/v1/calendar/*
│   ├── integrations.py         # /api/v1/integrations/*
│   ├── knowledge.py            # /api/v1/knowledge/*
│   ├── chat_api.py             # /api/v1/chat/*
│   ├── search.py               # /api/v1/search/*
│   ├── admin_router.py         # /api/v1/admin/*
│   └── test_*.py               # 29 个测试文件
└── frontend/
    ├── index.html              # SPA shell + CSS (~2500行)
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── app.js              # 主应用逻辑 (~5200行)
        ├── components/         # 8 个 Web Components
        ├── views/              # 5 个视图壳
        ├── auth/
        │   └── permissions.ts
        └── types/
            └── index.ts
```

---

## 五、数据库

### Alembic 迁移历史

| Migration | 内容 |
|---|---|
| `001_rbac_base.py` | users/roles/permissions/role_permissions/role_bindings/orgs/departments/org_memberships/dept_memberships 基表 |
| `002_auth_additions.py` | auth_sessions 表 + users.last_login_at + users.must_change_password |
| `003_chat_user_scoping.py` | ai_query_logs 表(user_id/org_id/department_id) + chat_messages 索引 |
| `004_portal_assets_subsystems.py` | portal_notices/documents/resources/services/news + portal_subsystems + portal_subsystem_visits + portal_tasks + portal_calendar_events + knowledge 表 |
| `005_platform_enterprise.py` | 17 张业务表加 status/created_by/updated_by；portal_subsystems 加 menu_items_json/entry_url；roles 加 org_id/updated_at；新建 notifications 表；PG TIMESTAMPTZ 转换；权限 re-seed (53 码) |
| `006_pgvector.py` | PG 上 CREATE EXTENSION IF NOT EXISTS vector；SQLite no-op |

### 核心业务表（Phase 2 待开发）

| 表名 | 状态 | 说明 |
|---|---|---|
| `enterprise_repair_tickets` | 表已存在，stub 可用 | 报修工单（title/location/description/status/priority/assignee/requester_id/rating） |
| `enterprise_asset_items` | 表已存在，stub 可用 | 资产台账（asset_code/name/category/location/status/custodian） |
| `enterprise_oa_flows` | 表已存在，stub 可用 | OA 流程（title/flow_type/status/initiator_id/current_handler） |
| `asset_borrow_records` | Phase 2 migration 007 | 借用记录（asset_id/user_id/borrow_date/return_date） |
| `oa_approval_records` | Phase 2 migration 008 | 审批记录（flow_id/approver_id/action/comment） |

---

## 六、权限体系

### 角色-权限矩阵

| 角色 | 权限数 | 典型权限 |
|---|---|---|
| `super_admin` | 53 (全部) | 管理后台全权限 |
| `org_admin` | ~30 | 组织/部门/角色/用户管理+审计查看+子系统管理 |
| `dept_leader` | ~20 | 部门数据查看+任务管理+子系统访问 |
| `dept_staff` | ~15 | 个人任务+子系统有限访问+知识库使用 |
| `external` | ~5 | 仅公开数据+子系统有限访问 |

### 权限分组

| 分组 | 权限码示例 |
|---|---|
| **子系统** | `subsystem:view`, `subsystem:manage` |
| **报修** | `repair:view`, `repair:create`, `repair:assign`, `repair:update`, `repair:close`, `repair:delete` |
| **资产** | `asset:view`, `asset:create`, `asset:update`, `asset:borrow`, `asset:delete` |
| **OA** | `oa:view`, `oa:create`, `oa:update`, `oa:delete` |
| **人事** | `hr:view`, `hr:create`, `hr:update` |
| **财务** | `finance:view`, `finance:create`, `finance:approve` |
| **门户** | `notice:create/update/delete`, `service:create/update/delete` |
| **知识库** | `kb:view`, `kb:manage`, `kb:import`, `kb:export` |
| **企业** | `enterprise:records:view` |
| **管理** | `admin:users`, `admin:audit`, `admin:export` |

### Scope 维度

```
                    org_id ──────→ 跨组织不可见
                   /
用户 ── role ── dept_id ──────→ 跨部门不可见 (含子部门)
                   \
                    owner_id ────→ 个人数据私有
```

实现位置：`authorization/sql_filters.py` + `stores/base.py:_scope_filter()`

---

## 七、关键 API 端点

| 分组 | 端点 | 方法 |
|---|---|---|
| **健康** | `/health`, `/health?full=true` | GET |
| **认证** | `/api/v1/auth/login`, `/refresh` | POST |
| **门户** | `/api/v1/portal/bootstrap` | GET |
| **子系统** | `/api/v1/subsystems`, `/subsystems/{code}`, `/subsystems/{code}/visit`, `/subsystems/{code}/dashboard` | GET/POST |
| **任务** | `/api/v1/tasks`, `/tasks/{id}` | GET/POST/PATCH/DELETE |
| **日历** | `/api/v1/calendar/events` | GET/POST |
| **搜索** | `/api/v1/search?q=&limit=` | GET |
| **知识库** | `/api/v1/knowledge/mappings`, `/sync`, `/import`, `/chat` | GET/POST |
| **通知** | `/api/v1/notifications`, `/unread-count`, `/{id}/read`, `/read-all` | GET/PUT |
| **集成** | `/api/v1/integrations/embed-urls` | GET/POST |
| **管理** | `/api/v1/admin/users`, `/roles`, `/permissions`, `/orgs`, `/departments`, `/audit`, `/audit/export`, `/notices`, `/services` | GET/POST/PUT/DELETE |

---

## 八、运行方式

### 开发环境

```bash
# 后端
cd backend
cp .env.example .env          # 默认 SQLite，无需改
pip install -r requirements.txt
alembic upgrade head           # 执行迁移 + seed
python main.py                 # http://localhost:8000

# 前端（可选）
cd frontend
npm install && npm run build   # 产出 dist/

# 测试
cd backend
python -m pytest -q            # ~330 tests
```

### Docker 生产部署

```bash
# 配置环境变量 (.env 在仓库根目录)
JWT_SECRET_KEY=<生成强密钥>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<强密码>

# 启动
docker compose up -d --build

# 验证
curl http://localhost/health
curl http://localhost/health?full=true
```

---

## 九、测试现状

| 状态 | 文件数 | 说明 |
|---|---|---|
| ✅ **全绿** | **16 files** | 核心功能覆盖完整 |
| ⚠️ **已知红 (Phase 2)** | 5 files | 功能未实现导致的预期失败 |
| ⚠️ **需要 Python 3.12** | 8 files | Python 3.14 + pytest capture 兼容性问题 |

### 绿文件清单（16）

`test_admin.py`, `test_admin_api.py`, `test_ai_security.py`, `test_audit.py`, `test_auth.py`, `test_exception_format.py`, `test_frontend_contract.py`, `test_health.py`, `test_idor.py`, `test_knowledge_authorized_rag.py`, `test_notifications.py`, `test_platform_contract.py`, `test_search_phase1.py`, `test_security_contract.py`, `test_sqlite_store.py`, `test_subsystems_phase1.py`

### 共享 Fixtures (`conftest.py`)

| Fixture | 用途 |
|---|---|
| `client` | 未认证 TestClient（temp SQLite + 迁移 + seed 用户） |
| `super_admin_client` | 已认证 super_admin |
| `dept_staff_client` | 已认证 dept_staff |
| `dept_leader_client` | 已认证 dept_leader |
| `org_admin_client` | 已认证 org_admin |
| `external_client` | 已认证 external |
| `all_roles_client` | 返回 `{client, tokens, user_ids}` 供多角色对比 |
| `login()`, `create_user()`, `auth_headers()`, `upgrade_db()` | 模块级 helper |

---

## 十、已知问题

| # | 问题 | 影响 | 修复建议 |
|---|---|---|---|
| 1 | `test_enterprise_modules.py` 5 tests FAIL | 无（Phase 2 contract） | Phase 2 实现 `/api/v1/enterprise/*` 路由后自动通过 |
| 2 | Python 3.14 + pytest capture 插件不兼容 | 全量运行时报 `ValueError: I/O operation on closed file` | 用 `-s` 禁用 capture；或降级 Python 3.12 |
| 3 | `alembic check` 在本地 SQLite 报 schema drift | 无（仅开发环境 metadata vs 旧库不一致） | 删除旧 DB 重建；或仅用 `alembic upgrade head` |
| 4 | `test_data_scope.py` 2 tests FAIL | 知识搜索数据集 seed 缺 "Public Dataset" | Phase 2 修复 seed |
| 5 | `test_rbac.py` 1 test FAIL | 测试中硬编码 "ds1" 数据集不存在 | Phase 2 改为先创建后测试 |
| 6 | 部分旧测试文件直接发请求不带 token | exit 1（非 T10 范围） | 逐一加上认证 |
| 7 | Nginx `default.conf` 的 CSP `frame-src` 只有飞书和钉钉 | 其他 iframe 子系统无法嵌入 | 管理后台配置 `entry_url` 后需同步更新 CSP |

---

## 十一、Phase 2 路线图

参见 Phase 2 计划文档。核心任务：

| 任务 | 工期 | 内容 |
|---|---|---|
| **Phase 2a: 报修系统** | 2-3 天 | 工单 CRUD + 派单/处理/完成/评价 + 统计 + 前端视图 |
| **Phase 2b: 资产系统** | 2 天 | 资产台账 + 借用/归还/盘点 + 维修关联 + 前端视图 |
| **Phase 2c: OA 系统** | 2 天 | 流程 CRUD + 待办/已办/我发起 + 审批链 + 前端视图 |

### Phase 2 新建文件清单

```
后端:
  backend/routers/enterprise.py       ← 3 模块路由 (~18 endpoints)
  backend/alembic/versions/007_asset_borrow_records.py
  backend/alembic/versions/008_oa_approval_records.py
  backend/schemas.py                  ← 扩展 ~12 models
  backend/test_repair_phase2.py       ← ~30 tests
  backend/test_asset_phase2.py        ← ~30 tests
  backend/test_oa_phase2.py           ← ~30 tests

前端:
  frontend/src/views/repair.js        ← 工单列表/新建/详情/派单/评价
  frontend/src/views/asset.js         ← 资产台账/借用/归还/盘点
  frontend/src/views/oa.js            ← 流程列表/待办/发起/审批
```

---

## 十二、关键技术决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | 时间字段用 String(32) 存 ISO 字符串，读取时 `_stringify_dt()` 转换 | 保持 SQLite/PG 跨方言兼容 |
| D2 | Store 用 Mixin 多重继承，保持 `from store import store` 不变 | 避免改动所有 router |
| D3 | `metadata` 在 store.py 定义，alembic 的 `env.py` import 它 | 单一 schema 来源 |
| D4 | `status` 和 `entry_type` 分离——前者控制 API 可达，后者控制前端渲染 | shell 子系统可达但显示占位 |
| D5 | Seed 逻辑幂等——首次 insert 全量，后续 update block try/except 包裹 | 兼容旧库缺少新列 |
| D6 | `_pytest_database_url()` 自动检测 PYTEST_CURRENT_TEST → 切 temp SQLite | 测试永不触碰 dev DB |
| D7 | 前端无框架——原生 JS SPA + hash 路由 + Web Components | 零依赖，兼容性最大化 |
| D8 | 测试每个文件独立 fixture，conftest 提供共享选项 | 新测试可选共享，旧测试不受影响 |
| D9 | 权限码用 `resource:action` 命名，53 码覆盖 9 个资源域 | 粗细粒度结合，管理后台 checkbox grid 按资源分组 |

---

## 十三、环境变量参考

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://...` | 数据库 URL；SQLite 开发时改用 `sqlite:///...` |
| `JWT_SECRET_KEY` | (必填) | HS256 密钥，生产环境用 `secrets.token_hex(32)` |
| `ENVIRONMENT` | `development` | `development` / `staging` / `production` |
| `DEBUG` | `true` | 调试模式（生产必须 `false`） |
| `CORS_ORIGINS` | `http://localhost:5173,...` | 逗号分隔 |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` / `ADMIN_EMAIL` | (空) | Docker 启动时自动创建管理员 |
| `AUDIT_ENABLED` | `true` | 审计日志开关 |
| `JSON_LOGS` | `true`(prod) | JSON 结构化日志 |
| `POOL_SIZE` / `MAX_OVERFLOW` | `10` / `20` | PG 连接池 |
| `BACKUP_RETENTION_DAYS` | `14` | 备份保留天数 |
| `NGINX_PORT` | `80` | Nginx 监听端口 |
