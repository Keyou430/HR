# 平台数据范围政策

对应工单：#34。更新日期：2026-10-14。唯一负责人：Keyou430。

## 默认拒绝

普通 Store 调用必须传入认证依赖取得的 `user`；聊天消息保存必须传入服务端取得的 `user_id`。省略、空身份和非整数用户 ID 返回 401。`AccessContext` 仅由可信认证结果构建，不能使用 HTTP 请求体中的身份或角色声明构建。

底层 SQL 范围过滤器遇到缺少上下文、非 `AccessContext` 对象或未登记表时返回恒假条件。单对象过滤同样拒绝未知表，企业创建拒绝未登记的企业资源。未知 `visibility` 或 `sensitivity` 不触发默认策略，超级管理员也不能绕过未知政策。

## 已登记资源

表名登记位于 `backend/stores/base.py`；可见性与敏感级别登记位于 `backend/authorization/scope.py`。

| 资源 | 列表范围 | 单对象范围 |
| --- | --- | --- |
| `portal_tasks`、`portal_calendar_events` | 当前所有者；超级管理员可查看已声明政策的全部记录 | 当前所有者；超级管理员例外 |
| `knowledge_dataset_mappings` | 所有者或明确声明的 public/org/dept 可见性，并检查敏感级别 | 相同可见性与敏感级别政策 |
| `portal_subsystems`、`portal_notices`、`portal_documents`、`portal_resources`、`portal_news` | public/org/dept/private 政策与敏感级别；部门范围必须同时核对组织 | 门户详情复用相同政策 |
| `enterprise_repair_tickets`、`enterprise_asset_items`、`enterprise_oa_flows`、`hr_requests`、`finance_claims`、`finance_budgets`、`cms_sites`、`estate_spaces`、`job_postings` | 保持现有所有者范围；超级管理员例外 | 保持现有逐对象可见性与敏感级别政策 |
| 知识导入记录 | 通过可见数据集映射限定；无映射的旧记录仅超级管理员可读/清理 | 写入必须关联可见映射；清理同时受映射及指定数据集约束 |
| 聊天会话与消息 | 仅认证用户自己拥有的会话 | 相同所有者要求；无主旧会话不能被任意用户读取、认领或删除 |
| 通知与子系统访问记录 | 通知按目标用户隔离；访问记录同时要求可见子系统，超级管理员可查看全局 | 通知修改与删除必须匹配当前用户 |

这些登记不替代路由上的操作权限检查。组织管理员、部门用户和外部用户继续执行已有 RBAC 规则；部门可见性同时校验组织。新增资源必须先声明公共范围政策，再接入列表和逐对象操作。

## 公开内容例外

门户内容与知识映射中的 `visibility="public"` 是明确的公开内容政策，仍要求有效认证身份并执行敏感级别检查。调用语义为 `list_portal_assets(..., user=current_user)` 或对应的知识查询。任务与日历保持所有者隔离，不因 public 标记向其他用户开放。

当前没有通过省略 `user` 获得匿名数据的入口。未来如需匿名访问，应独立声明资源、可返回字段和调用契约，不能恢复无上下文全量查询。

## 系统任务例外

`backend/authorization/system.py` 声明进程内部的 `SystemActor` 枚举；系统操作按对象身份校验，HTTP 字符串、字典、布尔标志与角色声明不能替代枚举对象。

| 主体 | 允许操作 | 生产调用方 |
| --- | --- | --- |
| `SystemActor.OVERDUE_SCANNER` | `find_overdue_tasks`、`mark_task_overdue_notified`、`create_notification` | 后端 lifespan 注册的逾期扫描回调 |
| `SystemActor.ROLE_NOTIFIER` | `create_notification` | 管理员角色变更通知生产方 |

例：`store.find_overdue_tasks(actor=SystemActor.OVERDUE_SCANNER)`。逾期扫描及标记同样拒绝未知行可见性或敏感级别。系统主体不具备通用 SQL 数据范围，不能传给普通用户 Store 接口取得全局数据。数据库初始化和迁移是独立内部路径，不通过省略用户调用普通 CRUD。

知识全局同步要求 `user` 为超级管理员。全局嵌入地址配置保留既有 `system:config` 路由授权；它不是用户资源范围查询。

## 验证与边界

`backend/test_scope_default_deny.py` 覆盖缺少身份、未知表、未知行政策、组织与部门交叉校验、公开内容、伪造系统主体、系统操作范围、合法逾期通知流程及聊天所有者隔离。受影响入口同时回归 #31–#33 和通知接口；结果记录在 #34 完成记录与排期中。

本工单不引入数据库迁移。逾期状态与通知的原子保存仍按 #44 排期处理。无主旧聊天会话默认拒绝访问，如需恢复，应在确认归属后通过独立迁移处理，不能让请求自行认领。

验收结果（2026-10-14）：72 个新增用例；相关入口分批合计 298 个唯一用例全部通过。控制全量起始基线为 646 通过/117 失败（763 个），扩大运行为 717 通过/116 失败（833 个）；最后收紧系统任务行政策后复跑 20 个受影响用例，补充 2 个新场景，按测试标识合并共 719 通过/116 失败（835 个唯一用例）。没有新增失败，原有角色变更通知失败已修复。四个已有收集异常脚本继续排除；旧通知、迁移及持久化断言保留。12 个修改涉及的 Python 文件编译通过，Ruff 无新增诊断（原有 45 项保留），Git 差异检查通过。完整记录保存在基线 artifact 的 issue34/regression-comparison.json。
