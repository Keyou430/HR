# Replica — 智能工作台基础平台

统一组织数字化入口，集成督办、OA、人事、财务、资产、报修等子系统，提供智能知识库与 RBAC 权限管理。

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.14, FastAPI, SQLAlchemy, Alembic |
| 数据库 | SQLite (dev), PostgreSQL + pgvector (prod) |
| 前端 | Vanilla JS (IIFE + Modal), Canvas API, Vite |
| 认证 | JWT (access + refresh tokens) |
| AI | Hermes Gateway (FastGPT 集成), AI Security Firewall |

## 快速启动

```bash
# 后端
cd backend
python -m venv venv
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000

# 前端
cd frontend
npm install
npx vite
```

访问 `http://localhost:5173`，默认账户 `admin` / `admin123`。

## 子系统

| 子系统 | 代码 | 类型 | 状态 |
|--------|------|------|------|
| 督办系统 | supervision | internal | ✅ 已激活 |
| OA 系统 | oa | internal | ✅ 已激活 |
| 人事系统 | hr | internal | ✅ 已激活 |
| 财务系统 | finance | internal | ✅ 已激活 |
| 资产管理系统 | assets | internal | ✅ 已激活 |
| 报修管理系统 | repair | internal | ✅ 已激活 |
| 数据门户 | data-portal | internal | ✅ 已激活 |
| 网站群 | website | internal | ✅ Phase 4 |
| 房产管理系统 | estate | internal | ✅ Phase 4 |
| 就业系统 | employment | internal | ✅ Phase 4 |
| 一体化教学云平台 | teaching-cloud | iframe | 🔗 外部入口 |
| 党建系统 | party | disabled | 🚧 规划中 |
| 校友系统 | alumni | disabled | 🚧 规划中 |
| 学工系统 | student | disabled | 🚧 规划中 |
| 心理系统 | mental-health | disabled | 🚧 规划中 |

## API 概览

| 路由 | 说明 |
|------|------|
| `POST /api/v1/auth/login` | 登录获取 token |
| `GET /api/v1/subsystems` | 子系统列表（含 menu_items） |
| `GET /api/v1/enterprise/{module}/*` | 企业模块 CRUD |
| `GET /api/v1/enterprise/export/{entity}` | CSV 数据导出 |
| `GET /api/v1/knowledge/*` | 知识库检索与导入 |
| `GET /api/v1/admin/*` | 管理后台 |
| `GET /health` | 健康检查 |

## 项目结构

```
backend/
  alembic/          # 数据库迁移（011 revisions）
  auth/             # 认证与授权（JWT, RBAC）
  audit/            # 审计日志中间件
  ai_security/      # AI 防火墙、脱敏
  routers/          # FastAPI 路由
  stores/           # 数据存储 Mixin 层
  schemas.py        # Pydantic 模型
  store.py          # PortalStore 单体
  main.py           # 应用入口
frontend/
  index.html        # SPA 入口
  src/
    app.js          # 主应用
    views/          # 子系统视图
    components/     # 可复用组件
    auth/           # 认证模块
docs/               # 设计文档与执行计划
```

## 许可

Internal use — 组织内部平台。
