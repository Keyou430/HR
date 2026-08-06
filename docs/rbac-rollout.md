# Replica RBAC v2.0 上线部署指南 (Rollout)

> 版本: 1.0 | 日期: 2026-08-03 | Phase 7 交付物

---

## 一、前置条件

### 1.1 环境要求

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.12+ | 后端运行环境 |
| PostgreSQL | 16+ | 生产数据库（SQLite 仅用于开发） |
| Node.js | 22+ | 前端构建 |
| 反向代理 | nginx / Caddy | 生产环境推荐 |

### 1.2 依赖安装

```bash
# 后端
cd backend
pip install -r requirements.txt

# 前端
cd frontend
npm ci
```

### 1.3 环境变量

生产环境 `.env` 文件必须配置以下变量：

```bash
# ── 必填 ──
ENVIRONMENT=production
DEBUG=false
JWT_SECRET_KEY=<openssl rand -hex 32 生成的值>
DATABASE_URL=postgresql+psycopg://user:password@host:5432/replica

# ── CORS — 仅允许明确前端域名 ──
CORS_ORIGINS=https://your-domain.com,https://admin.your-domain.com

# ── 强烈建议 ──
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
BCRYPT_ROUNDS=12

# ── AI 安全 ──
HERMES_MODE=real
HERMES_BASE_URL=https://hermes.internal/api
FASTGPT_MODE=real
FASTGPT_BASE_URL=https://fastgpt.internal/api

# ── 审计 ──
AUDIT_ENABLED=true
AUDIT_RECORD_AUTH_DENIED=true
AUDIT_RETENTION_DAYS=90
```

**警告**: 生产环境不得使用默认 `JWT_SECRET_KEY`，应用启动时将拒绝启动。

---

## 二、数据库迁移

### 2.1 备份数据库

```bash
# PostgreSQL
pg_dump -h <host> -U <user> -d replica > replica_backup_$(date +%Y%m%d_%H%M%S).sql

# SQLite (开发环境)
cp backend/replica_platform.db backend/replica_platform_backup_$(date +%Y%m%d_%H%M%S).db
```

### 2.2 执行迁移

```bash
cd backend
alembic upgrade head
```

### 2.3 验证迁移

```bash
cd backend
alembic current    # 应显示最新版本号
alembic check      # 检查是否有未应用的迁移
```

---

## 三、种子数据

首次部署后，系统自动创建以下种子数据：

| 实体 | 默认值 | 说明 |
|------|--------|------|
| 组织 | `default` | 默认组织 |
| 部门 | `HQ` (总部) | 默认根部门 |
| 角色 | `super_admin`, `org_admin`, `dept_leader`, `dept_staff`, `external` | 5个系统角色 |
| 权限 | 30个权限码 | 按 `resource:action` 命名 |

### 3.1 创建初始管理员

通过注册接口创建首个管理员用户后，手动提升为 `super_admin`：

```sql
-- 将用户 ID=1 绑定 super_admin 角色
INSERT INTO role_bindings (user_id, role_id, org_id, department_id, created_at)
SELECT 1, id, 'default', 'HQ', datetime('now')
FROM roles WHERE code = 'super_admin';
```

---

## 四、灰度上线步骤

推荐按以下顺序分阶段上线：

### 阶段 1: 基础设施部署 (预计 0.5 天)
1. 部署 PostgreSQL 数据库
2. 配置环境变量和反向代理
3. 执行 `alembic upgrade head`
4. 验证健康检查 `GET /health` 返回 200

### 阶段 2: 认证上线 (预计 0.5 天)
1. 创建初始管理员和测试用户
2. 导入组织/部门结构
3. 开放登录、刷新、登出接口
4. **业务 API 仍保持开放**（可逐步加认证依赖）

### 阶段 3: 功能权限收紧 (预计 1 天)
1. 为各角色分配权限
2. 所有写接口加入权限检查
3. 验证: 各角色只能访问授权接口

### 阶段 4: 数据隔离上线 (预计 1 天)
1. 确认所有业务数据具有 `org_id`、`department_id`、`owner_id`
2. 确认旧数据回填完成（默认归属 `system_seed`）
3. 开启读接口数据范围过滤
4. 开启写接口对象级权限
5. 验证: 用户不能跨 org/dept/owner 访问数据

### 阶段 5: AI 安全上线 (预计 0.5 天)
1. 确认知识库 `visibility` 和 `sensitivity` 正确
2. 开启 AI 安全防火墙（注入检测、风险分类、授权检索）
3. 验证: 低权限用户不能越权查询

### 阶段 6: 审计与管理后台 (预计 0.5 天)
1. 确认审计中间件已注册
2. 确认管理后台 API 受 `super_admin` 保护
3. 设置审计日志保留策略

---

## 五、验证清单

上线后逐项验证：

### 5.1 认证
- [ ] 未登录访问受保护 API → 401
- [ ] 错误密码登录 → 401 (不区分用户不存在/密码错误)
- [ ] 禁用用户登录 → 401
- [ ] Refresh Token 轮换后旧 token 失效
- [ ] Logout 后 Refresh Token 失效
- [ ] 角色变更后旧 Access Token 立即失效

### 5.2 权限
- [ ] `external` 只能访问 public 资源
- [ ] `dept_staff` 不能访问管理后台
- [ ] `dept_leader` 不能访问其他部门
- [ ] `org_admin` 不能跨组织访问
- [ ] `super_admin` 可以访问所有数据

### 5.3 安全
- [ ] CORS 仅返回已配置域名
- [ ] Refresh Cookie 属性: HttpOnly, Secure, SameSite
- [ ] Access Token 不在响应体中以外的地方出现
- [ ] 审计日志不含密码、Token、完整敏感内容
- [ ] AI 拒绝响应不含未授权知识库名称

### 5.4 性能
- [ ] 健康检查端点响应 < 100ms
- [ ] 登录接口响应 < 500ms
- [ ] 审计查询单次不超过 1000 条

---

## 六、监控建议

| 监控项 | 指标 | 告警阈值 |
|--------|------|----------|
| 登录失败率 | `auth.login.failed` / 分钟 | > 20/分钟 |
| 403 拒绝率 | 审计日志 `decision=deny` / 分钟 | > 50/分钟 |
| AI 拦截率 | AI 查询 `decision=blocked` / 小时 | > 30/小时 |
| 审计写入失败 | `replica.audit` WARNING 级别日志 | 任何出现 |
| JWT 密钥默认值 | 启动日志 CRITICAL | 立即告警 |
