# Replica RBAC v2.0 回滚指南 (Rollback)

> 版本: 1.0 | 日期: 2026-08-03 | Phase 7 交付物

---

## 一、回滚原则

1. **数据库迁移必须可逆**: 所有 Alembic 迁移提供 `downgrade()` 函数。
2. **回滚前必须备份**: 回滚前先对当前数据库做完整备份。
3. **业务连续性优先**: 回滚期间前端显示"维护中"页面。
4. **分步回滚**: 按上线相反顺序逐步回滚，每步验证。

---

## 二、数据库回滚

### 2.1 查看当前版本

```bash
cd backend
alembic current
```

输出示例:
```
INFO  [alembic.runtime.migration] Current revision(s):
003 (head)
```

### 2.2 备份当前数据库

```bash
# PostgreSQL
pg_dump -h <host> -U <user> -d replica > replica_pre_rollback_$(date +%Y%m%d_%H%M%S).sql

# SQLite
cp backend/replica_platform.db backend/replica_platform_pre_rollback_$(date +%Y%m%d_%H%M%S).db
```

### 2.3 回滚到指定版本

```bash
cd backend

# 回滚一个版本
alembic downgrade -1

# 回滚到指定版本
alembic downgrade <revision_id>

# 回滚到初始状态（空库）
alembic downgrade base
```

### 2.4 当前迁移版本说明

| 版本 | 说明 | 回滚影响 |
|------|------|----------|
| `003` | Chat session user scoping | 移除 `chat_sessions.user_id` 列，不影响已有消息 |
| `002` | Auth additions (`must_change_password`) | 移除 `users.must_change_password` 列 |
| `001` | RBAC base schema | **⚠️ 回滚将删除所有 RBAC 表和数据归属列** |

**警告**: 从 `001` 回滚会影响所有新增的权限、角色、组织、部门数据。必须确认以下数据已备份：
- `orgs`, `departments` 表
- `roles`, `permissions`, `role_permissions`, `role_bindings` 表
- `users`, `user_org_memberships`, `user_department_memberships` 表
- `auth_sessions`, `audit_logs`, `ai_query_logs` 表
- 业务表中新增的 `org_id`, `department_id`, `owner_id`, `visibility`, `sensitivity` 列

---

## 三、应用层回滚

### 3.1 关闭 AI 安全策略

当 AI 安全策略导致误拒时，可通过配置降级：

```bash
# .env
AI_SECURITY_ENABLE_INJECTION_DETECTION=false
```

或者降低风险分类的严格程度（需修改 `ai_security/classifier.py` 中的关键词列表）。

### 3.2 关闭数据隔离 (紧急)

如果数据隔离过滤条件导致用户无法正常访问数据：

```python
# authorization/sql_filters.py 中临时返回 True（无过滤）
# ⚠️ 这会暴露所有数据，仅作为紧急回滚手段
```

更安全的做法：将有问题的用户角色临时提升为 `org_admin` 或 `super_admin`。

### 3.3 关闭认证 (紧急回滚)

```python
# 在 auth/dependencies.py 的 get_current_user 中临时返回 anonymous 用户
# ⚠️ 这会移除所有认证，仅作为紧急回滚手段
```

### 3.4 恢复旧版前端

```bash
cd frontend

# 恢复旧版本构建产物
git checkout <old-commit> -- dist/

# 或重新部署上一版本的构建产物
```

---

## 四、代码回滚

### 4.1 恢复到指定 Git 提交

```bash
# 查看提交历史
git log --oneline -10

# 恢复到上一版本（保留本地修改）
git revert <commit-hash>

# 或直接检出旧版本（会丢失本地修改）
git checkout <old-tag>
```

### 4.2 标签参考

| 标签 | 描述 |
|------|------|
| `v1.1.0` | RBAC 安全加固 + 聊天持久化 + 管理后台 |
| `v1.0.0` | 第一版 — 智能工作台基础平台 |

---

## 五、数据恢复

### 5.1 从备份恢复 PostgreSQL

```bash
# 1. 删除现有数据库（谨慎！）
dropdb -h <host> -U <user> replica

# 2. 创建空库
createdb -h <host> -U <user> replica

# 3. 恢复备份
psql -h <host> -U <user> -d replica < replica_backup_YYYYMMDD_HHMMSS.sql
```

### 5.2 从备份恢复 SQLite

```bash
cp backend/replica_platform_backup_YYYYMMDD_HHMMSS.db backend/replica_platform.db
```

### 5.3 验证恢复

```bash
cd backend
alembic current                     # 确认迁移版本
python -c "
from session import get_session_local
db = get_session_local()()
result = db.execute('SELECT COUNT(*) FROM users').fetchone()
print(f'Users: {result[0]}')
db.close()
"
```

---

## 六、回滚场景与操作步骤

### 场景 A: 迁移执行失败

**症状**: `alembic upgrade head` 报错

**操作**:
1. 确认错误原因（字段冲突、约束冲突等）
2. 如果迁移已部分执行，回滚到上一版本:
   ```bash
   alembic downgrade -1
   ```
3. 修复迁移脚本后重新执行

### 场景 B: 新版本权限过严导致用户无法工作

**症状**: 大量用户反馈 403 错误

**操作**:
1. 检查审计日志确认影响范围:
   ```sql
   SELECT action, COUNT(*) FROM audit_logs
   WHERE decision='deny' AND created_at > datetime('now', '-1 hour')
   GROUP BY action ORDER BY COUNT(*) DESC;
   ```
2. 临时提升受影响角色权限:
   ```sql
   -- 为 dept_staff 角色添加缺失的权限
   INSERT INTO role_permissions (role_id, permission_id)
   SELECT r.id, p.id FROM roles r, permissions p
   WHERE r.code = 'dept_staff' AND p.code = '<missing_permission>';
   ```
3. 重新部署修复版本

### 场景 C: AI 防火墙误拦正常查询

**症状**: 正常知识库查询被拒绝

**操作**:
1. 临时关闭注入检测:
   ```bash
   AI_SECURITY_ENABLE_INJECTION_DETECTION=false
   ```
2. 检查被拦截查询的审计日志:
   ```sql
   SELECT query_snippet, blocked_reason, COUNT(*)
   FROM ai_query_logs
   WHERE decision='blocked'
   GROUP BY query_snippet ORDER BY COUNT(*) DESC LIMIT 20;
   ```
3. 调整 `ai_security/injection.py` 中的匹配模式或阈值

### 场景 D: 性能下降

**症状**: API 响应时间显著增加

**操作**:
1. 检查审计表大小:
   ```sql
   SELECT COUNT(*) FROM audit_logs;
   ```
2. 如果审计表过大，清理旧记录:
   ```sql
   DELETE FROM audit_logs WHERE created_at < datetime('now', '-90 days');
   ```
3. 检查 PostgreSQL 索引:
   ```sql
   SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'audit_logs';
   ```

---

## 七、联系人与升级路径

| 角色 | 联系方式 | 职责 |
|------|----------|------|
| 后端负责人 | — | 数据库迁移、API 故障 |
| 前端负责人 | — | 前端构建、部署 |
| 安全负责人 | — | 权限异常、安全事件 |
| DevOps | — | 基础设施、监控 |
