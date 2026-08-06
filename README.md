# HR 智能工作台

统一组织数字化入口，集成督办、OA、人事、财务、资产、报修、网站群、房产、就业等 15 个子系统，提供智能知识库与 RBAC 权限管理。

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic |
| 数据库 | PostgreSQL 16 + pgvector (Docker/生产), SQLite (本地快速测试) |
| 前端 | Vanilla JS SPA, Web Components, Vite 8 |
| 认证 | JWT HS256 (access 15min + refresh 7d), bcrypt 12 rounds |
| RBAC | 5 角色, 53 权限码, 3 维度数据隔离 |
| AI | Hermes Gateway (DeepSeek), FastGPT 知识库, AI Security Firewall |
| 部署 | Docker Compose (4 容器), Nginx 反向代理, 自动备份 |

## 快速启动（Docker）

```bash
# 1. 克隆仓库
git clone https://github.com/Keyou430/HR.git
cd HR

# 2. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，填写必要配置

# 3. 启动开发环境
docker compose -f docker/compose.base.yml -f docker/compose.dev.yml up -d

# 4. 启动前端（另一个终端）
cd frontend && npm install && npm run dev

# 或 Windows 一键启动：
start-dev.bat
```

访问 `http://localhost:5173`，默认账户：

| 用户 | 密码 | 角色 |
|------|------|------|
| `admin` | `admin123` | 超级管理员 |
| `leader` | `Admin123!` | 部门领导 |
| `staff` | `Admin123!` | 普通员工 |
| `external` | `Admin123!` | 外部用户 |

API 文档：`http://localhost:8000/docs`

## 生产部署

```bash
# 构建并启动全部服务（api + postgres + nginx + 自动备份）
docker compose -f docker/compose.yml up -d

# 或从预构建镜像启动
docker pull ghcr.io/keyou430/hr:latest
```

## 子系统

| 子系统 | 代码 | 状态 |
|--------|------|------|
| 督办系统 | supervision | ✅ |
| OA 系统 | oa | ✅ |
| 人事系统 | hr | ✅ |
| 财务系统 | finance | ✅ |
| 资产管理系统 | assets | ✅ |
| 报修管理系统 | repair | ✅ |
| 数据门户 | data-portal | ✅ |
| 网站群 | website | ✅ |
| 房产管理系统 | estate | ✅ |
| 就业系统 | employment | ✅ |
| 教学云平台 | teaching-cloud | 🔗 外部入口 |
| 党建/校友/学工/心理 | party/alumni/student/mental-health | 🚧 规划中 |

## Makefile 命令

```bash
make dev          # 启动开发环境
make test         # 运行测试套件
make test-smoke   # 快速冒烟测试
make lint         # 代码检查
make format       # 自动格式化
make migrate      # 数据库迁移
make shell        # 进入 API 容器
make clean        # 清理缓存和容器
```

## CI/CD

每次 PR 自动运行：lint → test → security scan。合并到 main 后自动构建 Docker 镜像推送到 ghcr.io，并执行冒烟验证 + Trivy 容器安全扫描。版本 tag 自动生成 GitHub Release。

## 项目结构

```
HR/
├── backend/               # Python FastAPI
│   ├── alembic/           # 数据库迁移
│   ├── auth/              # JWT + RBAC
│   ├── audit/             # 审计日志
│   ├── ai_security/       # AI 防火墙
│   ├── routers/           # API 路由
│   ├── stores/            # 数据层 Mixin
│   └── test_*.py          # pytest (40+)
├── frontend/              # Vanilla JS SPA
│   └── src/
│       ├── app.js         # 主应用
│       ├── views/         # 子系统视图
│       └── components/    # Web Components
├── docker/                # Docker 配置
│   ├── Dockerfile         # 生产镜像
│   ├── Dockerfile.dev     # 开发镜像
│   ├── compose.yml        # 生产编排
│   ├── compose.dev.yml    # 开发编排
│   └── scripts/           # 容器脚本
├── .github/workflows/     # CI/CD 流水线
├── docs/                  # 设计文档
├── Makefile               # 开发命令
└── start-dev.bat          # Windows 一键启动
```

## 许可

Internal — 组织内部平台。CI/CD 流水线配置可参考 `.github/workflows/ci.yml`。
