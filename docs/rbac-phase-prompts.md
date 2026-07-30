# Replica RBAC v2.0 分阶段实施、审查与验收提示词

> 适用项目：`D:\Replica`  
> 依据文档：[rbac-design-v2.md](D:\Replica\docs\rbac-design-v2.md)  
> 使用方式：每次只执行一个 Phase，先运行“实施提示词”，再运行“阶段审查提示词”，最后运行“阶段验收提示词”。

---

## 一、使用规则

### 1.1 执行顺序

```text
读取设计文档
  -> 执行当前 Phase 实施提示词
  -> 运行当前 Phase 审查提示词
  -> 修复审查发现的问题
  -> 执行当前 Phase 验收提示词
  -> 验收通过后进入下一 Phase
```

### 1.2 统一上下文

以下内容默认适用于所有提示词：

```text
你正在 D:\Replica 项目中工作。

项目结构：
- backend/: FastAPI + SQLAlchemy 后端
- frontend/: Vite/TypeScript 前端
- docs/rbac-design-v2.md: RBAC v2.0 设计与实施计划
- docs/rbac-phase-prompts.md: 当前提示词手册

必须遵守：
1. 读取文件必须使用 UTF-8 编码。
2. 开始修改前，先读取相关现有文件，不能凭空重写。
3. 只修改当前 Phase 明确允许的文件。
4. 不撤销或覆盖用户已有的无关修改。
5. 不使用 git reset --hard、git checkout --、Remove-Item 等破坏性操作。
6. 手工编辑文件使用 apply_patch。
7. 先写失败测试，再写最小实现，再运行测试。
8. 所有权限判断必须在后端执行，不能只依赖前端隐藏按钮。
9. 不把 LLM、Prompt、正则表达式作为唯一授权边界。
10. 未通过当前 Phase 验收前，不得提前实现下一 Phase。
11. 不自动安装网络依赖；若确实需要安装，先报告依赖和原因。
12. 完成后必须汇报：修改文件、测试命令、测试结果、未解决问题和下一步建议。
```

### 1.3 阶段状态规则

每个 Phase 只有以下三种状态：

```text
PENDING    尚未开始
IN_PROGRESS 正在实施
DONE       实施、审查、验收均通过
BLOCKED    存在外部阻塞，必须说明阻塞原因
```

如果测试失败，不得声称完成；如果发现设计矛盾，应停止修改并报告矛盾位置。

---

## 二、主控提示词

以下提示词用于启动一个阶段性执行代理。使用时，将它和对应 Phase 的实施提示词一起发送。

```text
你是 Replica 项目的资深全栈工程师和安全工程师。

你的任务是只完成当前指定的一个 Phase，不跨阶段扩展范围。

首先读取：
1. D:\Replica\docs\rbac-design-v2.md
2. D:\Replica\docs\rbac-phase-prompts.md
3. 当前 Phase 提示词中列出的所有现有文件

然后按以下顺序工作：
1. 汇报你理解的当前代码状态。
2. 列出当前 Phase 的实施任务和影响文件。
3. 写或补充失败测试。
4. 运行测试，确认测试确实覆盖了缺失行为。
5. 实现最小改动。
6. 运行当前 Phase 测试和相关回归测试。
7. 做一次自查：权限边界、异常处理、数据泄露、回归影响。
8. 输出阶段总结。

严格限制：
- 不修改无关模块。
- 不把权限判断放到前端作为唯一防线。
- 不把用户身份、角色或权限完整信任在客户端传回的数据中。
- 不在日志中记录密码、JWT、Refresh Token、完整敏感 query 或完整敏感回答。
- 不在没有授权检索结果时让模型自由回答内部业务问题。
- 不在测试未通过时继续扩大改动范围。

最终输出格式：

## 阶段状态
PENDING / IN_PROGRESS / DONE / BLOCKED

## 变更文件
- 文件路径：变更内容

## 测试
- 命令：
- 结果：

## 安全检查
- 是否默认拒绝：
- 是否存在对象级越权：
- 是否可能泄露敏感信息：

## 未解决问题
- 没有则写“无”

## 下一步
- 仅写当前 Phase 验收通过后的下一步
```

---

## 三、Phase 0：权限边界与基线测试

### 3.1 实施提示词

```text
执行 Replica RBAC v2.0 的 Phase 0：权限边界确认与基线测试。

先读取：
- D:\Replica\docs\rbac-design-v2.md
- D:\Replica\backend\main.py
- D:\Replica\backend\portal.py
- D:\Replica\backend\tasks.py
- D:\Replica\backend\calendar_api.py
- D:\Replica\backend\knowledge.py
- D:\Replica\backend\search.py
- D:\Replica\backend\integrations.py
- D:\Replica\backend\schemas.py
- D:\Replica\backend\store.py
- D:\Replica\frontend\index.html
- D:\Replica\frontend\src\types\index.ts

本阶段目标：
1. 建立现有 API 的完整清单。
2. 为每个 API 标记 public、authenticated、permission_required 三种状态。
3. 固化 v2.0 权限命名和资源范围。
4. 增加当前系统的安全基线测试，但不改变现有业务行为。

允许创建或修改：
- backend/test_security_baseline.py
- docs/rbac-permission-matrix.md
- docs/rbac-design-v2.md（仅补充明确发现的接口差异）

禁止修改：
- backend/main.py
- backend/store.py
- backend/knowledge.py
- frontend/index.html
- 任何生产行为代码

实施要求：
1. 从 FastAPI router 和源码中逐项列出所有端点。
2. 基线测试至少覆盖：
   - `/health` 当前可访问。
   - 任务列表、创建、更新、删除端点的当前状态。
   - 日历列表、创建、更新、删除端点的当前状态。
   - 知识库 spaces、mappings、imports、chat 端点的当前状态。
   - integrations 和 search 端点的当前状态。
3. 权限矩阵必须包含：
   - super_admin
   - org_admin
   - dept_leader
   - dept_staff
   - external
4. 数据范围必须区分：
   - own
   - dept
   - org
   - public
5. 记录当前缺陷，但不要在本阶段修复。

测试命令：
Set-Location D:\Replica\backend
pytest -q test_security_baseline.py

完成条件：
- API 清单没有遗漏。
- 权限矩阵与 rbac-design-v2.md 一致。
- 基线测试全部通过。
- 未修改现有业务行为。
```

### 3.2 阶段审查提示词

```text
审查 Replica RBAC v2.0 Phase 0 的结果。

只审查，不修改代码。

读取：
- D:\Replica\docs\rbac-permission-matrix.md
- D:\Replica\backend\test_security_baseline.py
- D:\Replica\docs\rbac-design-v2.md
- backend 下所有 router 文件

重点检查：
1. 是否枚举了所有 API，包括动态路径和管理接口。
2. 是否把 health、公开资源和受保护资源正确区分。
3. 是否存在只在前端使用、后端无法验证的权限。
4. 是否遗漏知识库 import、sync、mapping update/delete 等高风险端点。
5. 角色、权限和数据范围名称是否与 v2.0 一致。
6. 基线测试是否验证了真实现状，而不是写成预期中的安全状态。
7. 测试是否可能因为 mock 过度而出现假通过。

输出：
- P0/P1/P2 问题，按严重性排序。
- 每个问题给出文件路径和行号。
- 明确说明是否允许进入 Phase 1。
```

### 3.3 阶段验收提示词

```text
验收 Replica RBAC v2.0 Phase 0。

执行：
1. Set-Location D:\Replica\backend
2. pytest -q test_security_baseline.py
3. python -m compileall .

验收标准：
- 测试通过。
- API 清单覆盖 portal、tasks、calendar、knowledge、search、integrations、health。
- 权限矩阵覆盖 5 个系统角色。
- 每个业务资源都有 own/dept/org/public 数据范围说明。
- 没有修改生产行为代码。

若任一项失败：
- 状态标记为 BLOCKED。
- 输出失败命令、错误摘要和阻塞原因。
- 不得进入 Phase 1。
```

---

## 四、Phase 1：Alembic 与数据迁移

### 4.1 实施提示词

```text
执行 Replica RBAC v2.0 的 Phase 1：Alembic 与数据迁移。

先读取：
- D:\Replica\docs\rbac-design-v2.md
- D:\Replica\backend\store.py
- D:\Replica\backend\session.py
- D:\Replica\backend\config.py
- D:\Replica\backend\requirements.txt
- D:\Replica\backend\replica_platform.db
- D:\Replica\backend\test_sqlite_store.py

本阶段目标：
1. 建立唯一的数据库 schema 管理机制。
2. 新增组织、部门、用户、成员关系、角色、权限、角色绑定、会话和审计表。
3. 为任务、日历和知识库映射增加数据归属字段。
4. 安全回填现有数据。

允许创建或修改：
- backend/alembic.ini
- backend/alembic/env.py
- backend/alembic/versions/*_rbac_base.py
- backend/authorization/permissions.py
- backend/test_migrations.py
- D:\Replica\backend\requirements.txt
- backend/config.py
- backend/store.py

实施要求：
1. 迁移必须可重复执行，不能依赖手工 SQL。
2. 生产环境不得通过 metadata.create_all 自动改变 schema。
3. 使用 SQLAlchemy DateTime(timezone=True) 表达时间；SQLite 通过现有兼容层保存 ISO 8601。
4. department_id 与 org_id 使用联合外键，禁止跨组织绑定部门。
5. 处理 NULL 参与 UNIQUE 时的重复绑定问题。
6. 创建默认组织 default、默认部门总部和 system_seed 用户。
7. 旧任务和日历回填为 system_seed + org 级可见。
8. 旧知识库回填为 internal + dept，并记录需要管理员复核。
9. 不删除任何现有业务数据。

测试优先：
- 先写空库 upgrade 测试。
- 再写已有 SQLite 数据库升级测试。
- 再写 downgrade 或回滚验证。

测试命令：
Set-Location D:\Replica\backend
pytest -q test_migrations.py test_sqlite_store.py
alembic upgrade head

完成条件：
- 空库升级成功。
- 现有库升级成功。
- 旧数据行数不减少。
- 迁移后 schema 与 rbac-design-v2.md 一致。
```

### 4.2 阶段审查提示词

```text
审查 Replica RBAC v2.0 Phase 1 的数据库迁移。

只审查，不修改代码。

重点检查：
1. 是否存在 metadata.create_all 与 Alembic 双重管理。
2. migration 是否可重复执行。
3. downgrade 是否会误删现有业务数据。
4. 是否所有租户业务表都有 org_id。
5. 是否存在跨组织 department_id 绑定风险。
6. role_bindings 中 department_id 为 NULL 时是否会重复绑定。
7. 旧数据是否有明确 owner、org、visibility、sensitivity。
8. 是否把真实密码或默认弱密码写入生产种子。
9. 是否新增必要索引：
   - org_id
   - department_id
   - owner_id
   - created_at
10. SQLite 和 PostgreSQL 的字段行为是否一致。

输出：
- 数据完整性问题。
- 安全问题。
- 回滚问题。
- 是否允许进入 Phase 2。
```

### 4.3 阶段验收提示词

```text
验收 Replica RBAC v2.0 Phase 1。

执行：
Set-Location D:\Replica\backend
pytest -q test_migrations.py test_sqlite_store.py
alembic upgrade head
python -m compileall .

验收标准：
- 所有迁移测试通过。
- 新数据库可以从零升级到 head。
- 现有 SQLite 数据库升级后任务、日历、知识库记录仍存在。
- 默认组织、默认部门、system_seed、系统角色和权限存在。
- 迁移脚本不包含不可逆的无条件 DROP。
- 生产启动路径不再依赖自动 create_all 改表。

失败时停止，不得进入 Phase 2。
```

---

## 五、Phase 2：认证与会话

### 5.1 实施提示词

```text
执行 Replica RBAC v2.0 的 Phase 2：认证与会话。

先读取：
- D:\Replica\docs\rbac-design-v2.md
- D:\Replica\backend\config.py
- D:\Replica\backend\main.py
- D:\Replica\backend\schemas.py
- D:\Replica\backend\session.py
- D:\Replica\backend/requirements.txt
- frontend/package.json
- frontend/index.html
- frontend/src/types/index.ts

本阶段目标：
1. 实现用户名密码登录。
2. 实现短时 Access Token。
3. 实现 Refresh Token 轮换、撤销和退出登录。
4. 为 FastAPI 注入 current_user。
5. 前端具备最小登录态，但暂不实现完整权限 UI。

允许创建或修改：
- backend/auth/password.py
- backend/auth/tokens.py
- backend/auth/sessions.py
- backend/auth/dependencies.py
- backend/auth/router.py
- backend/test_auth.py
- backend/config.py
- backend/schemas.py
- backend/main.py
- D:\Replica\backend\requirements.txt
- frontend/src/auth/AuthContext.tsx
- frontend/src/auth/api.ts
- frontend/src/types/index.ts
- frontend/index.html

实施要求：
1. Access Token 默认有效期 15 分钟。
2. Refresh Token 只存哈希，不存明文。
3. Refresh Token 放 HttpOnly、Secure、SameSite Cookie。
4. Access Token 不放 localStorage。
5. users.token_version 变化后旧 Access Token 失效。
6. 禁用用户不能登录、刷新或访问受保护 API。
7. 登录失败不能返回“用户名不存在”或“密码错误”的区别性细节。
8. 登录接口要有基本的用户名/IP 限流设计。
9. 首次使用 system_seed 或默认管理员必须强制改密。
10. JWT payload 只存必要身份信息，不把完整权限列表作为可信授权来源。

API：
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me

测试优先覆盖：
- 正确密码登录。
- 错误密码登录。
- 用户禁用。
- Access Token 过期。
- Refresh Token 轮换。
- 旧 Refresh Token 重放。
- logout 后 refresh 失败。
- token_version 变化后旧 token 失败。
- 未认证请求获得 401。

测试命令：
Set-Location D:\Replica\backend
pytest -q test_auth.py
```

### 5.2 阶段审查提示词

```text
审查 Replica RBAC v2.0 Phase 2 的认证与会话实现。

只审查，不修改代码。

重点检查：
1. 密码是否以明文或可逆方式保存。
2. Refresh Token 是否只保存哈希。
3. Refresh Token 是否可重放。
4. logout、禁用用户、改密、改 token_version 是否立即生效。
5. JWT secret 是否有安全默认值。
6. JWT 是否放入了不应被客户端信任的权限数据。
7. Cookie 是否设置 HttpOnly、Secure、SameSite。
8. CORS 是否允许 null 或任意来源。
9. 401、403、422 的返回格式是否稳定。
10. 登录失败是否存在用户名枚举或敏感错误回显。
11. 前端是否把 Access Token 持久化到 localStorage。

输出：
- P0/P1/P2 问题。
- 具体文件和行号。
- 是否允许进入 Phase 3。
```

### 5.3 阶段验收提示词

```text
验收 Replica RBAC v2.0 Phase 2。

执行：
Set-Location D:\Replica\backend
pytest -q test_auth.py
python -m compileall .

Set-Location D:\Replica\frontend
npm test
npm run build

验收标准：
- 正常登录、错误登录、禁用账号测试全部通过。
- Refresh Token 轮换和撤销测试全部通过。
- 未认证访问受保护依赖返回 401。
- 前端构建成功。
- Access Token 不出现在 localStorage。
- Refresh Cookie 的安全属性存在。
- 默认管理员改密策略存在。
```

---

## 六、Phase 3：RBAC 功能权限

### 6.1 实施提示词

```text
执行 Replica RBAC v2.0 的 Phase 3：RBAC 功能权限。

先读取：
- D:\Replica\docs\rbac-design-v2.md
- D:\Replica\docs\rbac-permission-matrix.md
- backend/auth/dependencies.py
- backend/auth/router.py
- backend/main.py
- backend/portal.py
- backend/tasks.py
- backend/calendar_api.py
- backend/knowledge.py
- backend/search.py
- backend/integrations.py

本阶段目标：
1. 实现显式 role_permissions 权限判断。
2. 实现 PermissionChecker。
3. 保护所有业务 router。
4. 完成前端权限上下文和基础入口控制。

允许创建或修改：
- backend/authorization/rbac.py
- backend/authorization/checks.py
- backend/authorization/permissions.py
- backend/test_rbac.py
- backend/main.py
- backend/portal.py
- backend/tasks.py
- backend/calendar_api.py
- backend/knowledge.py
- backend/search.py
- backend/integrations.py
- frontend/src/auth/AuthContext.tsx
- frontend/src/auth/permissions.ts
- frontend/src/types/index.ts
- frontend/index.html

实施要求：
1. 受保护 router 默认依赖 get_current_user。
2. admin router 必须显式 require user/admin 权限。
3. 权限检查从数据库或服务端上下文计算，不信任客户端传来的 role。
4. 不使用 role priority 自动继承。
5. `super_admin` 也必须产生审计事件。
6. 无权限返回 403；不存在资源可以按接口策略返回 404 防止资源枚举。
7. 本阶段只做功能权限，不提前实现复杂数据范围。
8. 前端权限控制只能隐藏/禁用 UI，不能替代后端校验。

测试至少覆盖：
- 5 个角色对每类权限的允许/拒绝矩阵。
- 未认证、已认证但无权限、拥有权限三种情况。
- 管理后台入口和 API。
- knowledge import/sync/mapping update/delete。
- integrations 修改接口。

测试命令：
Set-Location D:\Replica\backend
pytest -q test_rbac.py
```

### 6.2 阶段审查提示词

```text
审查 Replica RBAC v2.0 Phase 3。

只审查，不修改代码。

重点检查：
1. 是否有业务 router 仍然没有认证依赖。
2. 是否只保护了 GET，遗漏 POST/PATCH/PUT/DELETE。
3. 是否把前端传入的 role、permissions 当作后端可信来源。
4. 是否存在 role priority 隐式继承。
5. 是否把 super_admin 作为无审计的布尔绕过。
6. 是否遗漏知识库同步、文件导入和删除接口。
7. 是否把 Phase 4 的对象级数据权限误当成已完成。
8. 403 和 404 的使用是否泄露资源存在性。
9. 测试是否覆盖拒绝路径，而不是只测试成功路径。

输出：
- 遗漏的端点。
- 越权风险。
- 测试缺口。
- 是否允许进入 Phase 4。
```

### 6.3 阶段验收提示词

```text
验收 Replica RBAC v2.0 Phase 3。

执行：
Set-Location D:\Replica\backend
pytest -q test_rbac.py test_auth.py
python -m compileall .

Set-Location D:\Replica\frontend
npm test
npm run build

验收标准：
- 5 个角色的功能权限矩阵测试通过。
- 所有业务写接口都有后端权限检查。
- knowledge import、sync、mapping update/delete 都受保护。
- integrations 配置修改受保护。
- 前端无权限入口状态与 `/auth/me` 一致。
- 未认证和无权限请求均能稳定返回。
```

---

## 七、Phase 4：对象级数据隔离与防 IDOR

### 7.1 实施提示词

```text
执行 Replica RBAC v2.0 的 Phase 4：对象级数据隔离与防 IDOR。

先读取：
- D:\Replica\docs\rbac-design-v2.md
- backend/store.py
- backend/tasks.py
- backend/calendar_api.py
- backend/knowledge.py
- backend/search.py
- backend/authorization/rbac.py
- backend/authorization/checks.py
- backend/test_rbac.py

本阶段目标：
1. 实现 own/dept/org/public 数据范围。
2. 将组织、部门、所有人、可见性和敏感级别加入查询条件。
3. 防止通过 ID 直接读取、修改或删除他人资源。
4. 让 bootstrap、搜索和知识库列表也遵守数据范围。

允许创建或修改：
- backend/authorization/scope.py
- backend/authorization/sql_filters.py
- backend/test_data_scope.py
- backend/test_idor.py
- backend/store.py
- backend/tasks.py
- backend/calendar_api.py
- backend/knowledge.py
- backend/search.py
- backend/portal.py
- backend/schemas.py
- frontend/index.html
- frontend/src/types/index.ts

实施要求：
1. 所有列表查询在 SQL 层过滤，不允许先查全量再在 Python 中过滤。
2. 所有 update/delete 的 WHERE 条件必须包含组织和对象级权限条件。
3. 任务、日历、知识库映射统一使用：
   - org_id
   - department_id
   - owner_id
   - visibility
   - sensitivity
4. 部门负责人可以查看本部门及下级部门，但不能查看其他部门。
5. 组织管理员只能访问本组织，除非同时具备平台级权限。
6. external 只能访问 public。
7. 搜索结果不得泄露无权访问资源的标题、owner 或知识库名称。
8. bootstrap_payload 必须根据 user 返回，不得继续返回所有默认数据。
9. 对不存在资源和无权资源采用统一策略，避免 ID 枚举。

推荐接口：
get_access_context(user, org_id)
get_visible_department_ids(context)
task_visibility_filter(context)
calendar_visibility_filter(context)
knowledge_visibility_filter(context)

测试优先覆盖：
- 用户 A 无法读取用户 B 的 private 任务。
- 用户 A 无法 PATCH/DELETE 用户 B 的任务。
- 部门负责人只能访问本部门和子部门。
- 组织管理员不能访问其他组织。
- external 看不到 internal/private。
- 搜索和 bootstrap 不泄露越权资源。

测试命令：
Set-Location D:\Replica\backend
pytest -q test_data_scope.py test_idor.py test_rbac.py
```

### 7.2 阶段审查提示词

```text
审查 Replica RBAC v2.0 Phase 4 的对象级授权。

只审查，不修改代码。

重点检查：
1. 是否存在“先按 ID 查询，再在 Python 判断”的 TOCTOU/IDOR 风险。
2. update/delete 是否把权限条件放入 SQL WHERE。
3. 是否有任意列表接口仍返回全量数据。
4. 是否有搜索、bootstrap、错误消息泄露资源标题或 owner。
5. department_id 是否与 org_id 一起校验。
6. visibility='dept' 是否真的按部门树过滤。
7. external 是否可能通过参数切换 scope。
8. 客户端是否可以提交任意 owner_id、org_id、department_id。
9. 用户默认组织和当前请求组织是否混淆。
10. 是否存在管理员跨组织越权的隐式路径。

请优先检查：
- backend/store.py
- backend/tasks.py
- backend/calendar_api.py
- backend/knowledge.py
- backend/search.py

输出：
- 每个越权路径的复现步骤。
- 影响范围。
- 是否允许进入 Phase 5。
```

### 7.3 阶段验收提示词

```text
验收 Replica RBAC v2.0 Phase 4。

执行：
Set-Location D:\Replica\backend
pytest -q test_data_scope.py test_idor.py test_rbac.py test_portal_api.py
python -m compileall .

验收标准：
- private、dept、org、public 四种数据范围测试通过。
- IDOR 测试全部通过。
- 用户不能修改请求体中的 owner_id、org_id 或 department_id 来越权。
- 跨组织访问被拒绝。
- 搜索结果和 bootstrap 不泄露越权资源。
- 现有任务、日历、知识库正常功能回归通过。

任何一条越权测试失败，状态必须为 BLOCKED。
```

---

## 八、Phase 5：AI 安全与授权检索

### 8.1 实施提示词

```text
执行 Replica RBAC v2.0 的 Phase 5：AI 安全与授权检索。

先读取：
- D:\Replica\docs\rbac-design-v2.md
- backend/knowledge.py
- backend/hermes.py
- backend/config.py
- backend/schemas.py
- backend/authorization/scope.py
- backend/authorization/sql_filters.py
- backend/test_knowledge_api.py

本阶段目标：
1. 让 AI 只能检索授权知识库和授权片段。
2. 禁止低权限用户使用 direct chat 绕过授权检索。
3. 将风险分类器定位为辅助风险判断，不作为唯一授权依据。
4. 增加输入注入检测、输出检查和 AI 审计。

允许创建或修改：
- backend/ai_security/injection.py
- backend/ai_security/classifier.py
- backend/ai_security/retrieval_policy.py
- backend/ai_security/sanitizer.py
- backend/ai_security/firewall.py
- backend/test_ai_security.py
- backend/test_knowledge_authorized_rag.py
- backend/knowledge.py
- backend/hermes.py
- backend/config.py
- backend/schemas.py

实施要求：
1. 处理顺序必须是：
   认证 -> kb:chat 权限 -> 数据范围 -> 风险分类 -> 授权检索 -> LLM 生成 -> 输出检查。
2. 无检索结果时不得让模型基于通用知识回答内部业务问题。
3. 低权限用户不能通过 `/chat`、`mode=chat`、`/rag` 或 scope 参数绕过策略。
4. LLM 只能看到授权片段，不得看到未授权 dataset 名称。
5. 输出 sources 只能来自授权检索结果。
6. 如果 FastGPT 不支持可靠 metadata 过滤，必须用 dataset 分层策略。
7. 查询长度、单用户频率、单次检索数量必须有限制。
8. 审计只记录 query_hash、snippet、risk_label、decision 和资源数量。
9. 不记录完整敏感 query、完整 prompt、完整 response。
10. 文档片段必须被标记为不可信数据，不能执行其中的指令。

风险标签：
GENERAL
PERSONNEL_SENSITIVE
FINANCIAL_SENSITIVE
STRATEGIC_SENSITIVE
CROSS_DEPT
PROMPT_INJECTION

测试优先覆盖：
- 低权限用户查询全组织薪资。
- 部门负责人查询其他部门财务。
- 用户尝试忽略系统规则。
- 用户要求输出 system prompt。
- 无检索结果时禁止自由回答。
- Hermes 分类服务异常时安全降级。
- FastGPT 返回未授权片段时后端丢弃。

测试命令：
Set-Location D:\Replica\backend
pytest -q test_ai_security.py test_knowledge_authorized_rag.py test_knowledge_api.py
```

### 8.2 阶段审查提示词

```text
审查 Replica RBAC v2.0 Phase 5 的 AI 安全实现。

只审查，不修改代码。

重点检查：
1. 是否把 LLM 分类结果直接当作 allow/deny 授权结果。
2. 是否存在 direct chat 绕过数据范围。
3. 无检索结果时是否允许模型自由回答内部问题。
4. FastGPT 返回结果是否经过后端授权过滤。
5. sources 是否可能暴露未授权知识库名称。
6. 低权限用户是否可以通过 mode、scope、斜杠命令切换策略。
7. Prompt 中是否注入了过多用户角色、组织或系统信息。
8. 检索文档中的恶意指令是否可能被当成系统指令。
9. 审计日志是否记录了完整敏感 query 或 response。
10. Hermes/FastGPT 异常时是否 fail-open。
11. 输出正则是否被错误地当成绝对安全保证。

必须给出至少 5 个越权或提示注入复现输入，并说明预期结果。

输出：
- 数据泄露风险。
- 策略绕过路径。
- 日志泄露风险。
- 是否允许进入 Phase 6。
```

### 8.3 阶段验收提示词

```text
验收 Replica RBAC v2.0 Phase 5。

执行：
Set-Location D:\Replica\backend
pytest -q test_ai_security.py test_knowledge_authorized_rag.py test_knowledge_api.py
python -m compileall .

验收标准：
- 未授权知识库不会进入检索请求。
- 未授权片段不会进入 Hermes prompt。
- sources 不包含未授权资源。
- direct chat 不能绕过 kb:chat 和数据范围。
- 分类器失败时不会放行敏感请求。
- 无检索结果时不会使用通用模型知识回答内部问题。
- 5 类以上提示注入输入均被拒绝或安全降级。
- AI 日志不保存完整敏感 query 和 response。

任何真实数据可能进入未授权 prompt，状态必须为 BLOCKED。
```

---

## 九、Phase 6：审计、监控与管理后台

### 9.1 实施提示词

```text
执行 Replica RBAC v2.0 的 Phase 6：审计、监控与管理后台。

先读取：
- D:\Replica\docs\rbac-design-v2.md
- backend/main.py
- backend/auth/dependencies.py
- backend/authorization/checks.py
- backend/knowledge.py
- backend/config.py
- frontend/index.html
- frontend/src/types/index.ts

本阶段目标：
1. 记录认证、授权、资源操作和 AI 决策。
2. 管理员可以查看用户、角色、权限、审计和 AI 记录。
3. 支持禁用用户和使会话失效。
4. 建立最小异常统计。

允许创建或修改：
- backend/audit/models.py
- backend/audit/logger.py
- backend/audit/middleware.py
- backend/admin_api.py
- backend/test_audit.py
- backend/test_admin_api.py
- backend/main.py
- backend/config.py
- frontend/src/admin/*
- frontend/src/types/index.ts
- frontend/index.html

审计字段至少包含：
- request_id
- user_id
- org_id
- department_id
- action
- resource_type
- resource_id
- decision
- reason
- status
- ip_address
- user_agent
- created_at

实施要求：
1. 不记录 Authorization header、密码、Refresh Token。
2. AI query 默认记录 hash 和短摘要，不记录完整响应。
3. 审计查询 API 本身必须受 audit:view 保护。
4. 审计失败不能阻塞普通业务请求，但安全阻断事件必须可靠记录。
5. 管理员修改角色、禁用用户、删除资源必须记录 before/after 摘要。
6. 增加分页、时间范围和 action 筛选。
7. 管理后台前端只显示当前用户有权操作的功能。

测试：
- 未授权用户不能查审计。
- 组织管理员不能查看其他组织审计。
- 禁用用户后旧 session 失效。
- 403 和 AI block 都会产生审计事件。
- 审计日志不包含秘密凭据。

测试命令：
Set-Location D:\Replica\backend
pytest -q test_audit.py test_admin_api.py
```

### 9.2 阶段审查提示词

```text
审查 Replica RBAC v2.0 Phase 6。

只审查，不修改代码。

重点检查：
1. 审计中是否出现密码、JWT、Refresh Token 或完整敏感文本。
2. 审计查看接口是否可能被低权限用户访问。
3. 组织管理员是否能读取其他组织审计。
4. before/after 是否包含不应暴露的字段。
5. 异步写审计失败时是否静默丢失安全事件。
6. 审计 middleware 是否重复记录、阻塞请求或吞掉异常。
7. 管理员接口是否存在水平越权。
8. 禁用账号是否立即使会话失效。
9. 审计查询是否支持分页和时间范围，避免一次性加载全表。

输出：
- 审计泄露问题。
- 管理后台越权问题。
- 审计完整性问题。
- 是否允许进入 Phase 7。
```

### 9.3 阶段验收提示词

```text
验收 Replica RBAC v2.0 Phase 6。

执行：
Set-Location D:\Replica\backend
pytest -q test_audit.py test_admin_api.py
python -m compileall .

Set-Location D:\Replica\frontend
npm test
npm run build

验收标准：
- 认证失败、授权拒绝、资源操作、AI 拦截均有审计记录。
- 审计查询权限正确。
- 用户禁用后 session 立即失效。
- 管理后台构建成功。
- 审计不保存密码、token、完整敏感问答。
- 审计列表支持分页和筛选。
```

---

## 十、Phase 7：E2E、加固与上线准备

### 10.1 实施提示词

```text
执行 Replica RBAC v2.0 的 Phase 7：E2E、加固与上线准备。

先读取：
- D:\Replica\docs\rbac-design-v2.md
- D:\Replica\docs\rbac-phase-prompts.md
- backend 下全部 test_*.py
- frontend/package.json
- frontend/index.html
- backend/config.py
- backend/main.py

本阶段目标：
1. 验证从登录到业务操作的全链路。
2. 验证不同角色的访问边界。
3. 验证 AI 越权查询被拦截。
4. 完成生产配置和回滚文档。

允许创建或修改：
- backend/test_security_contract.py
- frontend/tests/*
- docs/rbac-rollout.md
- docs/rbac-rollback.md
- backend/config.py
- backend/main.py
- frontend/index.html
- frontend/src/*

E2E 场景必须包含：
1. dept_staff 登录后只能看到自己的任务和允许的部门数据。
2. dept_staff 访问他人任务 ID 被拒绝。
3. dept_leader 可以访问本部门和下级部门。
4. dept_leader 不能访问其他部门敏感数据。
5. org_admin 可以访问本组织数据。
6. org_admin 不能跨组织访问。
7. external 只能访问 public。
8. 管理员禁用用户后，旧会话立即失效。
9. dept_staff 通过 AI 查询全组织薪资被拦截。
10. AI 拒绝结果不会泄露未授权知识库名称。

生产加固：
- CORS 仅允许明确前端域名。
- 生产关闭 debug/reload。
- 确认 JWT_SECRET_KEY 不使用默认值。
- 确认 Refresh Cookie 使用 Secure。
- 确认日志不会输出 Authorization header。
- 确认数据库备份和 Alembic rollback 文档存在。

测试命令：
Set-Location D:\Replica\backend
pytest -q
python -m compileall .

Set-Location D:\Replica\frontend
npm test
npm run build
```

### 10.2 阶段审查提示词

```text
审查 Replica RBAC v2.0 Phase 7 的上线准备。

只审查，不修改代码。

重点检查：
1. 是否所有受保护端点都被安全合约测试覆盖。
2. 是否存在只在单元测试通过、但跨模块失败的流程。
3. 是否覆盖 horizontal privilege escalation 和 vertical privilege escalation。
4. 是否覆盖 AI direct chat、scope 参数、prompt injection 绕过。
5. 是否存在生产默认配置、宽松 CORS 或 debug 模式。
6. 是否有迁移、备份、回滚和恢复说明。
7. 是否能在干净环境中复现部署。
8. 是否有失败时的安全降级方案。

输出：
- 上线阻断问题。
- 高风险遗留问题。
- 可接受的低风险问题。
- 是否建议上线。
```

### 10.3 阶段验收提示词

```text
验收 Replica RBAC v2.0 Phase 7。

执行：
Set-Location D:\Replica\backend
pytest -q
python -m compileall .

Set-Location D:\Replica\frontend
npm test
npm run build

验收标准：
- 后端全部测试通过。
- 前端测试和构建通过。
- 安全合约测试覆盖所有业务 router。
- 五个角色的关键路径全部通过。
- 关键越权、IDOR、AI 注入测试全部通过。
- 生产配置检查通过。
- 迁移、备份、回滚文档齐全。
- 没有 P0/P1 未解决问题。

只有满足全部条件，才能将 Phase 7 标记为 DONE。
```

---

## 十一、跨阶段总审查提示词

当所有 Phase 完成后使用。

```text
对 Replica RBAC v2.0 做一次最终代码审查。

项目目录：D:\Replica
设计文档：D:\Replica\docs\rbac-design-v2.md
阶段提示词：D:\Replica\docs\rbac-phase-prompts.md

审查目标：
1. 找出真实安全漏洞，而不是做风格评价。
2. 优先检查越权、数据泄露、认证绕过、IDOR、AI prompt injection 和审计泄露。
3. 检查设计文档、数据库 schema、后端实现、前端行为和测试是否一致。

必须检查：
- 未认证访问。
- 垂直越权：普通员工调用管理员能力。
- 水平越权：用户 A 访问用户 B 数据。
- 跨组织访问。
- 跨部门访问。
- owner_id/org_id/department_id 客户端篡改。
- 资源 ID 枚举。
- 搜索和 bootstrap 泄露。
- knowledge direct chat 绕过。
- FastGPT 未授权片段注入。
- 审计中出现密码、token 或敏感原文。
- Refresh Token 重放。
- 角色变更后旧 token 是否失效。
- CORS、Cookie、JWT secret 和 debug 配置。

输出格式：

## Findings
按 P0、P1、P2 排序。
每条包含：
- 标题
- 严重性
- 文件路径和行号
- 复现步骤
- 影响
- 修复建议

## Open Questions
只列出会影响安全或上线的未决问题。

## Residual Risk
列出修复后仍然存在的风险。

## Final Verdict
APPROVE / APPROVE_WITH_RISKS / BLOCK
```

---

## 十二、最终上线验收总提示词

```text
对 Replica RBAC v2.0 执行最终上线验收。

不要修改代码，只执行检查和测试。

检查文件：
- D:\Replica\docs\rbac-design-v2.md
- D:\Replica\docs\rbac-phase-prompts.md
- backend
- frontend

执行：
1. Set-Location D:\Replica\backend
2. pytest -q
3. python -m compileall .
4. alembic current
5. alembic check
6. Set-Location D:\Replica\frontend
7. npm test
8. npm run build

必须确认：
- 所有受保护 API 默认拒绝。
- 所有写接口具备功能权限和对象级授权。
- 所有租户数据具备 org_id。
- 所有部门数据具备 department_id 或明确 public/org 规则。
- 所有资源访问不能依赖客户端 role。
- AI 只处理授权检索结果。
- 无检索结果时不会自由回答内部业务问题。
- 完整敏感 query 和 response 不进入普通日志。
- Refresh Token 可撤销且不可重放。
- 管理员禁用用户后会话失效。
- 无 P0/P1 问题。

最终输出：

## Test Summary
- 后端：
- 前端：
- 数据库迁移：

## Security Summary
- 认证：
- RBAC：
- 对象级授权：
- AI 安全：
- 审计：

## Release Decision
GO / NO-GO

如果是 NO-GO，列出阻断问题和重新验收条件。
```

---

## 十三、代理执行时的统一汇报模板

```text
## Phase
Phase N: 阶段名称

## Status
IN_PROGRESS / DONE / BLOCKED

## Files Changed
- absolute/path/to/file

## Tests Run
```powershell
命令
```

## Test Result
- PASS / FAIL
- 关键输出

## Security Review
- Authentication:
- Function Permission:
- Object Permission:
- Tenant Isolation:
- AI Data Boundary:
- Audit Leakage:

## Known Issues
- 无则写“无”

## Scope Check
- 是否修改了下一阶段内容：是/否
- 是否修改了无关文件：是/否

## Next Step
- 只有当前阶段验收通过后才能填写下一阶段。
```

---

## 十四、执行建议

推荐执行方式：

```text
每个 Phase 开一个独立任务
  -> 发送主控提示词
  -> 发送本 Phase 实施提示词
  -> 等待实施代理完成
  -> 发送本 Phase 审查提示词
  -> 修复审查问题
  -> 发送本 Phase 验收提示词
  -> 验收通过后再开启下一 Phase
```

不要把 Phase 0～7 一次性发送给一个代理。权限、迁移和 AI 安全之间存在大量跨模块依赖，一次性执行会让代理扩大修改范围，也会降低问题定位和回滚能力。
