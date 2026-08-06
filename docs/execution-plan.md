# Replica Phase 2–4 详细执行计划

> **目的**: 零基础上手，按步骤执行即可完成 Phase 2-4 全部开发任务。
> **前置阅读**: `docs/handover.md`（项目全貌）、`docs/phase1-setup.md`（环境搭建）

---

## 〇、开始之前

### 环境确认

```bash
cd D:\Replica\backend
python --version          # 需要 3.12+ (推荐 3.12，3.14 有 pytest capture 兼容问题)
pip install -r requirements.txt
alembic upgrade head
python -m pytest test_subsystems_phase1.py -q   # 确认 24 passed
```

### 核心原则

1. **每次只改一个模块** — 后端路由 → Store → Schema → 前端视图 → 测试，按顺序做。
2. **每完成一步就跑测试** — `python -m pytest <test_file> -q -s`。
3. **遵循已有模式** — 不要发明新模式。本文档给出了每种代码的模板，照抄改参数即可。
4. **权限是强制的** — 每个写端点都要挂 `require_permission`，读端点要传 `user` 给 store 做 scope 过滤。

---

## 一、代码模式速查

### 1.1 后端路由模式

参照 `backend/routers/notifications.py` 和 `backend/subsystems.py`：

```python
# routers/enterprise.py
from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from auth.dependencies import get_current_user, require_permission
from schemas import RepairTicketCreate, RepairTicketUpdate   # 新建 schema
from store import store

router = APIRouter(prefix="/api/v1/enterprise", tags=["enterprise"])

# ── 列表（需要认证 + scope 过滤）─────────────────────────────
@router.get("/repair/tickets")
def list_repair_tickets(
    status_filter: str = Query(default="", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_repair_tickets(
        current_user, status=status_filter, limit=limit, offset=offset,
    )

# ── 详情 ────────────────────────────────────────────────────
@router.get("/repair/tickets/{ticket_id}")
def get_repair_ticket(
    ticket_id: int,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    ticket = store.get_repair_ticket(current_user, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="工单不存在或无权访问")
    return ticket

# ── 新建（需要写权限）────────────────────────────────────────
@router.post("/repair/tickets", status_code=status.HTTP_201_CREATED)
def create_repair_ticket(
    payload: RepairTicketCreate,
    current_user: dict[str, Any] = Depends(require_permission("repair:create")),
) -> dict[str, Any]:
    return store.create_repair_ticket(payload.model_dump(), user=current_user)

# ── 更新（需要写权限 + scope 检查）───────────────────────────
@router.patch("/repair/tickets/{ticket_id}")
def update_repair_ticket(
    ticket_id: int,
    payload: RepairTicketUpdate,
    current_user: dict[str, Any] = Depends(require_permission("repair:update")),
) -> dict[str, Any]:
    updated = store.update_repair_ticket(ticket_id, payload.model_dump(exclude_unset=True), user=current_user)
    if updated is None:
        raise HTTPException(status_code=404, detail="工单不存在或无权操作")
    return updated
```

### 1.2 Store 方法模式

参照 `backend/stores/repair.py` 已有 stub，扩展业务方法：

```python
# stores/repair.py 扩展
from sqlalchemy import func, select, update

# 单条查询（带 scope）
def get_repair_ticket(self, user: dict[str, Any], ticket_id: int) -> dict[str, Any] | None:
    with self._session() as db:
        ctx = self._build_scope_context(user, db)
        scope = self._scope_filter(ctx, self._enterprise_repair_tickets_table)
        row = db.execute(
            select(self._enterprise_repair_tickets_table)
            .where(self._enterprise_repair_tickets_table.c.id == ticket_id)
            .where(scope)
        ).mappings().first()
        return self._stringify_dt(dict(row)) if row else None

# 状态机操作（带锁 + 验证）
def assign_ticket(self, ticket_id: int, assignee: str, user: dict[str, Any]) -> dict[str, Any] | None:
    with self._lock:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            scope = self._scope_single(ctx, self._enterprise_repair_tickets_table, ticket_id)
            existing = db.execute(
                select(self._enterprise_repair_tickets_table).where(scope)
            ).mappings().first()
            if existing is None or existing["status"] != "submitted":
                return None
            now = self._now_iso()
            db.execute(
                update(self._enterprise_repair_tickets_table).where(scope).values(
                    status="assigned", assignee=assignee, updated_at=now,
                )
            )
            db.commit()
            row = db.execute(
                select(self._enterprise_repair_tickets_table).where(scope)
            ).mappings().first()
            return self._stringify_dt(dict(row)) if row else None
```

### 1.3 Schema 模式

参照 `backend/schemas.py` 现有定义：

```python
# schemas.py 新增
from pydantic import BaseModel, Field

class RepairTicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    location: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=2000)
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|urgent)$")

class RepairTicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = Field(default=None,
        pattern=r"^(submitted|assigned|processing|completed|rated)$")
    priority: str | None = Field(default=None,
        pattern=r"^(low|normal|high|urgent)$")
    assignee: str | None = Field(default=None, max_length=128)

class RepairTicketRate(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)

class RepairStats(BaseModel):
    total: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    avg_rating: float | None
```

### 1.4 测试模式

参照 `backend/test_subsystems_phase1.py` 完整 fixture + `backend/test_security_contract.py` 权限矩阵模式。

关键：每个测试文件定义自己的 `client` fixture（覆盖 conftest），模板如下：

```python
# test_repair_phase2.py
from __future__ import annotations
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from alembic import command
from alembic.config import Config
from auth.password import hash_password
from sqlalchemy import create_engine, text
from main import app

USERNAME = "repair_test"
PASSWORD = "repair-test-456"

def _alembic_config(db_path: str) -> Config:
    ini_path = str(BACKEND_ROOT / "alembic.ini")
    cfg = Config(ini_path)
    cfg.file_config.read(ini_path, encoding="utf-8")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return cfg

def _upgrade(db_path: str, revision: str = "head") -> None:
    command.upgrade(_alembic_config(db_path), revision)

def _create_user(db_url, username, password, display_name, role_code="dept_staff",
                 org_id="default", dept_id="HQ") -> int:
    # ... 复制 test_subsystems_phase1.py 的 _create_user 函数 ...

def _login(client, username, password) -> str:
    # ... 复制 ...

def _auth(token) -> dict:
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test_repair.db"
    db_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-for-repair-phase2!")
    monkeypatch.setenv("AUDIT_ENABLED", "false")
    from config import get_settings; get_settings.cache_clear()
    import session as sess_mod
    sess_mod._engine = sess_mod._engine_url = sess_mod._SessionLocal = None
    _upgrade(str(db_path), "head")
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("INSERT OR IGNORE INTO orgs (id, name, is_active, created_at) "
                          "VALUES ('default', '默认组织', 1, '2026-08-05T00:00:00')"))
    engine.dispose()
    _create_user(db_url, USERNAME, PASSWORD, "Test User", role_code="super_admin")
    from auth.router import _login_attempts; _login_attempts.clear()
    with TestClient(app, cookies={}) as c:
        yield c
    sess_mod._engine = sess_mod._engine_url = sess_mod._SessionLocal = None
    get_settings.cache_clear()

# ── 测试类 ─────────────────────────────────────────────────────
class TestRepairTicketCRUD:
    def test_create_ticket_requires_auth(self, client):
        resp = client.post("/api/v1/enterprise/repair/tickets", json={"title": "test"})
        assert resp.status_code == 401

    def test_create_ticket_succeeds(self, client):
        token = _login(client, USERNAME, PASSWORD)
        resp = client.post("/api/v1/enterprise/repair/tickets",
                          json={"title": "投影仪故障", "location": "A203",
                                "description": "无法开机", "priority": "high"},
                          headers=_auth(token))
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "投影仪故障"
        assert data["status"] == "submitted"
```

### 1.5 前端视图模式

```javascript
// views/repair.js
window.App = window.App || {};
window.App.views = window.App.views || {};

window.App.views.repair = {
  render: function(container, system) {
    container.innerHTML = `
      <div class="repair-view">
        <div class="view-toolbar">
          <h2>工单管理</h2>
          <button class="btn primary" id="newTicketBtn">+ 新建工单</button>
        </div>
        <div id="ticketFilters"></div>
        <div id="ticketList"></div>
      </div>`;
    this.bindEvents();
    this.loadTickets();
  },

  loadTickets: async function(filters = {}) {
    const params = new URLSearchParams(filters).toString();
    const resp = await apiJson(`/api/v1/enterprise/repair/tickets?${params}`);
    this.renderTicketTable(resp.items);
  },
  // ...更多方法
};
```

---

## 二、Phase 2a — 报修系统（2-3 天）

### 业务规则

```
工单生命周期:
  submitted ──派单──→ assigned ──处理──→ processing ──完成──→ completed ──评价──→ rated

权限要求:
  新建: repair:create    派单: repair:assign    处理: repair:update
  完成: repair:close      评价: repair:update    查看: enterprise:records:view
```

### Step 1: 扩展 Schema（30 min）

**文件**: `backend/schemas.py` — 在文件末尾追加 `RepairTicketCreate`、`RepairTicketUpdate`、`RepairTicketRate`、`RepairStats` 四个类（模板见 1.3 节）。

**验证**: `python -c "from schemas import RepairTicketCreate; print(RepairTicketCreate(title='test'))"`

### Step 2: 扩展 Store（1 hr）

**文件**: `backend/stores/repair.py`

保留现有的 `list_repair_tickets` / `create_repair_ticket` / `update_repair_ticket`（已可用），新增 6 个方法：

| 方法 | 说明 | 关键逻辑 |
|---|---|---|
| `get_repair_ticket(user, ticket_id)` | 单条查询 | scope filter + id 匹配 |
| `list_repair_tickets(user, status, priority, limit, offset)` | 筛选列表 | 重载现有方法，加 status/priority 过滤 + 分页 |
| `assign_ticket(ticket_id, assignee, user)` | 派单 | 状态验证 submitted → assigned |
| `complete_ticket(ticket_id, user)` | 完成 | 状态验证 assigned/processing → completed |
| `rate_ticket(ticket_id, rating, comment, user)` | 评价 | 状态验证 completed → rated |
| `repair_stats(user)` | 统计 | 聚合 by_status / by_priority / avg_rating |

**模板**: 见 1.2 节。每个方法遵循 `with self._lock → with self._session() → scope filter → 验证 → update → commit → 返回` 模式。

**验证**: `python -c "from store import store; print(dir(store))"` 确认新方法可见。

### Step 3: 创建路由（1.5 hr）

**文件**: `backend/routers/enterprise.py`（新建）

| 方法 | 路径 | 权限 | Store 方法 |
|---|---|---|---|
| GET | `/repair/tickets` | 认证即可 | `list_repair_tickets` |
| GET | `/repair/tickets/{id}` | 认证即可 | `get_repair_ticket` |
| POST | `/repair/tickets` | `repair:create` | `create_repair_ticket` |
| PATCH | `/repair/tickets/{id}` | `repair:update` | `update_repair_ticket` |
| POST | `/repair/tickets/{id}/assign` | `repair:assign` | `assign_ticket` |
| POST | `/repair/tickets/{id}/complete` | `repair:close` | `complete_ticket` |
| POST | `/repair/tickets/{id}/rate` | `repair:update` | `rate_ticket` |
| GET | `/repair/stats` | 认证即可 | `repair_stats` |

**注册到 main.py**: 在 `from routers.notifications import router as notifications_router` 之后添加：

```python
from routers.enterprise import router as enterprise_router
```

在 `app.include_router(notifications_router)` 之后添加：

```python
app.include_router(enterprise_router)
```

**验证**: 启动 `python main.py` → 打开 `http://localhost:8000/docs` 确认 enterprise 分组下有 8 个新端点。

### Step 4: 前端视图（1 day）

**文件**: `frontend/src/views/repair.js`（替换空壳）

实现以下功能：

1. **工单列表** — `<data-table>` 展示（标题/位置/状态/优先级/负责人/更新时间），状态用 `<status-badge>` 组件
2. **筛选栏** — 状态下拉 + 优先级下拉
3. **新建工单** — `<app-drawer>` 抽屉表单（标题/位置/描述/优先级选择）
4. **工单详情** — `<app-modal>` 弹窗展示全字段 + 操作按钮行
5. **派单** — 输入框填写派单人 + 确认
6. **评价** — 5 星点击 + 文字评论 + 提交
7. **统计看板** — 4 个指标卡片（总数/待处理/已完成/平均评分）

**集成到 app.js**: 修改 `openSubsystem()` 函数，在对 `renderSubsystemView()` 调用前插入子系统路由分派：

```javascript
// app.js: openSubsystem() 方法内，setView("subsystem") 之后添加:
var viewModules = { repair: "/src/views/repair.js", asset: "/src/views/asset.js", oa: "/src/views/oa.js" };
if (viewModules[code] && window.App && window.App.views && window.App.views[code]) {
    window.App.views[code].render($("#subsystemContent"), system);
    renderSubsystemSidebar(system, menuItems);
    return;
}
```

同时确保 `index.html` 在 `<script src="/src/app.js">` 之前加载视图脚本（或由 app.js 动态 import）。

**验证**: 打开前端 → 点击报修系统 → 工单列表显示 → 新建 → 派单 → 完成 → 评价 全流程可用。

### Step 5: 测试（4 hr）

**文件**: `backend/test_repair_phase2.py`（新建，模板见 1.4 节）

4 个测试类，~25 tests：

| 类 | 测试数 | 覆盖 |
|---|---|---|
| `TestRepairTicketCRUD` | 6 | 新建/列表/详情/更新/404/401 |
| `TestRepairTicketWorkflow` | 6 | 完整生命周期 + 非法状态流转拒绝 + 权限拒绝 |
| `TestRepairStats` | 3 | 统计返回计数 + scope 隔离 + 空数据 |
| `TestRepairScopeIsolation` | 4 | 跨 org 不可见 + 跨 dept 不可见 + 无权操作他人数据 |

**验证**: `python -m pytest test_repair_phase2.py -q -s` → 全部通过。

---

## 三、Phase 2b — 资产系统（2 天）

### 业务规则

```
资产状态:
  available → borrowed → available    （借用→归还）
  available → maintenance → available （维修→恢复）
  any → scrapped                       （报废终态）

权限: asset:create / asset:borrow / asset:update / asset:delete
```

### Step 1: Migration 007（30 min）

```bash
cd backend
alembic revision -m "Phase 2: asset borrow records"
# 编辑生成的文件
```

新建 `asset_borrow_records` 表，列：
`id / asset_id(FK) / user_id(FK) / borrow_date / expected_return_date / actual_return_date / status(borrowed\|returned) / purpose / org_id / department_id / created_at / updated_at`

在 `store.py` 的 metadata 中添加 `_asset_borrow_records_table` 表定义（参照 `_enterprise_asset_items_table` 模式）。

### Step 2: Schema（30 min）

追加到 `schemas.py`：`AssetItemCreate`、`AssetItemUpdate`、`AssetBorrowRequest`、`AssetStats`

### Step 3: Store（1 hr）

**文件**: `backend/stores/asset.py`

新增：`get_asset_item`、`list_asset_items`（带 status/category 筛选 + 分页）、`borrow_asset`（创建借用记录 + 改状态）、`return_asset`（更新借用记录 + 恢复状态）、`asset_stats`

### Step 4: 路由（1 hr）

在 `routers/enterprise.py` 追加 7 个资产端点（参照 Phase 2a 模式）：

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/assets/items` | 认证 |
| GET | `/assets/items/{id}` | 认证 |
| POST | `/assets/items` | `asset:create` |
| PATCH | `/assets/items/{id}` | `asset:update` |
| POST | `/assets/items/{id}/borrow` | `asset:borrow` |
| POST | `/assets/items/{id}/return` | `asset:borrow` |
| GET | `/assets/stats` | 认证 |

### Step 5: 前端（1 day）

**文件**: `frontend/src/views/asset.js`

- 资产台账（搜索+分类筛选+状态标签+分页）
- 资产详情弹窗（借用历史时间线）
- 借用/归还操作（抽屉表单）

### Step 6: 测试（3 hr）

**文件**: `backend/test_asset_phase2.py` — 4 类 ~25 tests

---

## 四、Phase 2c — OA 系统（2 天）

### 业务规则

```
流程状态: pending → processing → approved / rejected
权限: oa:create / oa:update / oa:delete
```

### Step 1: Migration 008（30 min）

新建 `oa_approval_records` 表：`id / flow_id(FK) / approver_id(FK) / action(approved\|rejected) / comment / org_id / department_id / created_at`

在 `store.py` 中添加表定义。

### Step 2: Schema（30 min）

`OaFlowCreate`、`OaFlowUpdate`、`OaApprovalAction`、`OaFlowStats`

### Step 3: Store（1 hr）

**文件**: `backend/stores/oa.py`

新增：`get_oa_flow`、`list_oa_flows`（带 status/flow_type 筛选 + 分页）、`approve_flow`（状态验证 + 创建审批记录）、`my_pending_flows`（current_user 是 current_handler）、`my_initiated_flows`（current_user 是 initiator）、`my_handled_flows`（出现在 approval_records 中）

### Step 4: 路由（1 hr）

在 `routers/enterprise.py` 追加 8 个 OA 端点：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/oa/flows` | 全部流程 |
| GET | `/oa/flows/{id}` | 详情+审批链 |
| POST | `/oa/flows` | 发起 |
| PATCH | `/oa/flows/{id}` | 更新 |
| POST | `/oa/flows/{id}/approve` | 审批 |
| GET | `/oa/flows/my-pending` | 我的待办 |
| GET | `/oa/flows/my-initiated` | 我发起的 |
| GET | `/oa/flows/my-handled` | 我已办 |

### Step 5: 前端（1 day）

**文件**: `frontend/src/views/oa.js`

- 三栏 Tab 切换（待办/已办/我发起）
- 流程详情（审批链可视化 + 时间线）
- 发起流程表单
- 审批操作（通过/驳回 + 意见）

### Step 6: 测试（3 hr）

**文件**: `backend/test_oa_phase2.py` — ~25 tests

---

## 五、Phase 3 — 人事 + 财务 + 数据门户

### Phase 3a: 人事系统（3 天）

#### Migration 009

```python
# hr_requests 表:
#   id / title / request_type(certificate|attendance|leave) /
#   status(pending|processing|approved|rejected) /
#   applicant_id(FK users) / org_id / department_id /
#   content_json(表单数据存 JSON) / approved_by / approved_at /
#   created_at / updated_at / created_by / updated_by
```

#### 后端端点

| 方法 | 路径 | 权限 |
|---|---|---|
| GET | `/enterprise/hr/requests` | 认证（scope: dept_leader 看部门, staff 看自己） |
| POST | `/enterprise/hr/requests` | `hr:create` |
| GET | `/enterprise/hr/requests/{id}` | 认证 |
| PATCH | `/enterprise/hr/requests/{id}` | `hr:update`（审批） |
| GET | `/enterprise/hr/requests/my-pending` | 认证 |
| GET | `/enterprise/hr/requests/my-initiated` | 认证 |
| GET | `/enterprise/hr/staff?dept_id=` | 认证（scope 严格控制：staff 仅看自己，leader 看部门，含薪资字段仅 org_admin+） |

#### 前端

**文件**: `frontend/src/views/hr.js` — 申请列表 + 发起申请 + 审批 + 人员信息查询

### Phase 3b: 财务系统（3 天）

#### Migration 010

两张表：`finance_claims`（报销） + `finance_budgets`（预算）

#### 后端端点

**报销**:
| 方法 | 路径 |
|---|---|
| GET | `/enterprise/finance/claims` |
| POST | `/enterprise/finance/claims` |
| GET | `/enterprise/finance/claims/{id}` |
| PATCH | `/enterprise/finance/claims/{id}` |

**预算**:
| 方法 | 路径 |
|---|---|
| GET | `/enterprise/finance/budgets` |
| POST | `/enterprise/finance/budgets` |
| GET | `/enterprise/finance/stats` |

**关键安全策略**: 金额字段仅 `finance:view` 权限可见；审批链 4 级。

#### 前端

**文件**: `frontend/src/views/finance.js`

### Phase 3c: 数据门户（2 天）

#### 后端

新增 `GET /enterprise/data-portal/overview` 聚合端点：

```python
# 返回值结构
{
    "subsystem_count": 15,
    "active_users_7d": 42,
    "total_tickets": 128,
    "total_assets": 356,
    "total_flows": 89,
    "notices_count": 15,
    "documents_count": 23,
    "trends": {
        "visits": [{"date": "2026-08-01", "count": 120}, ...],
        "tickets_created": [...],
        "tickets_completed": [...]
    }
}
```

#### 前端

将 `data-portal` 从 iframe 占位改为真实视图。6 个指标卡片 + 趋势折线图（引入 Chart.js CDN 或 Canvas 手绘）+ 子系统状态表。

---

## 六、Phase 4 — 生产交付就绪

| # | 任务 | 工期 | 核心动作 |
|---|---|---|---|
| **T17** | 壳子系统按需激活 | 3-5 天 | 选 2-3 个 disabled 壳改 internal + 配 menu_items + 建 store stub + 前端视图 |
| **T18** | 教学云平台对接 | 2 天 | 配置 `teaching-cloud` 的 `entry_url` + SSO + 更新 nginx CSP frame-src |
| **T19** | 数据导入导出 | 1 天 | CSV 批量导入 + 各实体导出 + 审计归档 |
| **T20** | 性能优化 | 2 天 | 慢查询索引 + 前端虚拟滚动 + 静态资源 hash 缓存 |
| **T21** | 监控告警 | 1 天 | Sentry SDK + Prometheus metrics + Uptime 监控 |
| **T22** | 文档完善 | 1 天 | 用户手册（按角色）+ API 文档 description + 运维手册 |
| **T23** | 安全审计 | 1 天 | pip-audit + npm audit + OWASP ZAP 扫描 + 渗透测试清单 |

---

## 七、每步验证清单

```bash
# 1. 导入无报错
python -c "from store import store; from routers.enterprise import router"

# 2. 对应测试全绿
python -m pytest test_<module>_phase2.py -q -s

# 3. 不破坏已有测试
python -m pytest test_subsystems_phase1.py test_admin_api.py test_search_phase1.py -q -s

# 4. Swagger 可见新端点
# 启动服务 → http://localhost:8000/docs

# 5. 前端冒烟
# 打开 index.html → 登录 → 进入子系统 → CRUD 全流程
```

---

## 八、常见坑

| # | 问题 | 原因 | 解决 |
|---|---|---|---|
| 1 | `ImportError: cannot import name` | 新方法没在 PortalStore 类中注册 | 确认 mixin 方法签名正确，PortalStore 继承了该 mixin |
| 2 | `404 subsystem not found` | `status="disabled"` 时路由返回 404 | shell 子系统 `status="active"` 仅 `entry_type="disabled"` |
| 3 | 测试间污染 | SQLite 文件未隔离 | 每个文件用 `tmp_path` 创建独立 DB |
| 4 | 测试慢 | 审计中间件每次写日志 | 测试设 `monkeypatch.setenv("AUDIT_ENABLED", "false")` |
| 5 | pytest capture 崩溃 (Python 3.14) | pytest + 3.14 不兼容 | 加 `-s` 参数 |
| 6 | 前端视图不更新 | `renderSubsystemView()` 优先级覆盖 | 在 `openSubsystem()` 中先判断视图模块再 fallback |
| 7 | CSP 阻止 iframe | nginx `frame-src` 缺域名 | 修改 `nginx/default.conf` 的 CSP |
| 8 | 403 但权限码正确 | `require_permission` 依赖未正确挂载 | 确认 `Depends(require_permission("xxx"))` 在函数签名中 |
| 9 | Scope 不过滤 | `_scope_filter` 对未知表返回 `True`（不过滤）| 在 `_scope_filter` 的已知表集合中添加新表名 |
