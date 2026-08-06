from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from typing import Any, Iterator

from sqlalchemy import Boolean, Column, Float, Integer, MetaData, String, Table, Text, and_, delete, func, insert, or_, select, text, update
from sqlalchemy.orm import Session

from config import get_settings
from session import get_engine, get_session_local
from stores.base import BaseStore
from stores.portal import PortalMixin
from stores.subsystems import SubsystemsMixin
from stores.search import SearchMixin
from stores.repair import RepairMixin
from stores.asset import AssetMixin
from stores.notifications import NotificationMixin
from stores.oa import OaMixin
from stores.hr import HrMixin
from stores.finance import FinanceMixin
from stores.portal_subsystems import WebsiteMixin, EstateMixin, EmploymentMixin


metadata = MetaData()

tasks_table = Table(
    "portal_tasks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("tag", String(32), nullable=False),
    Column("deadline", String(32), nullable=True),
    Column("done", Boolean, nullable=False, default=False),
    Column("status", String(32), nullable=True),
    Column("overdue_notified_at", String(32), nullable=True),
    Column("created_at", String(32), nullable=True),
    Column("updated_at", String(32), nullable=True),
    # ── RBAC data-attribution columns ────────────────────────────
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="private"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

events_table = Table(
    "portal_calendar_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", String(10), nullable=False),
    Column("title", String(255), nullable=False),
    Column("tone", String(16), nullable=False),
    Column("status", String(32), nullable=True),
    Column("created_at", String(32), nullable=True),
    Column("updated_at", String(32), nullable=True),
    # ── RBAC data-attribution columns ────────────────────────────
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="private"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

settings_table = Table(
    "portal_settings",
    metadata,
    Column("key", String(128), primary_key=True),
    Column("value_json", Text, nullable=False),
)

knowledge_mappings_table = Table(
    "knowledge_dataset_mappings",
    metadata,
    Column("id", String(160), primary_key=True),
    Column("resource_type", String(16), nullable=False),
    Column("resource_id", String(128), nullable=False),
    Column("display_name", String(255), nullable=False),
    Column("fastgpt_app_id", String(128), nullable=True),
    Column("fastgpt_dataset_id", String(128), nullable=True),
    Column("permission_scope", String(16), nullable=False, default="team"),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("is_default_import_target", Boolean, nullable=False, default=False),
    Column("status", String(32), nullable=True),
    Column("last_synced_at", String(32), nullable=True),
    Column("last_imported_at", String(32), nullable=True),
    Column("stale", Boolean, nullable=False, default=False),
    Column("updated_at", String(32), nullable=False),
    # ── Phase 4: RBAC data-attribution columns ──────────────────
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="dept"),
    Column("sensitivity", String(16), nullable=False, default="internal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

knowledge_import_records_table = Table(
    "knowledge_import_records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("mapping_id", String(160), nullable=True),
    Column("dataset_id", String(128), nullable=False),
    Column("file_name", String(255), nullable=False),
    Column("status", String(32), nullable=False),
    Column("collection_id", String(128), nullable=True),
    Column("error_message", Text, nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

chat_sessions_table = Table(
    "chat_sessions",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("title", String(255), nullable=False, default=""),
    # ── Phase 4: user-level data isolation ─────────────────────
    Column("user_id", Integer, nullable=True),
    Column("status", String(32), nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

chat_messages_table = Table(
    "chat_messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(64), nullable=False),
    Column("role", String(16), nullable=False),
    Column("content", Text, nullable=False),
    Column("action", String(32), nullable=True),
    Column("status", String(32), nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

portal_subsystems_table = Table(
    "portal_subsystems",
    metadata,
    Column("code", String(64), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("category", String(64), nullable=False),
    Column("description", Text, nullable=False),
    Column("status", String(32), nullable=False, default="active"),
    Column("entry_type", String(32), nullable=False, default="internal"),
    Column("owner_department", String(128), nullable=False),
    Column("owner_name", String(128), nullable=False),
    Column("support_contact", String(128), nullable=False),
    Column("icon_tone", String(32), nullable=False, default="app-blue"),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("is_featured", Boolean, nullable=False, default=False),
    Column("common_actions_json", Text, nullable=False),
    Column("related_resources_json", Text, nullable=False),
    Column("menu_items_json", Text, nullable=False, default="[]"),
    Column("approval_chain_json", Text, nullable=False, default="[]"),
    Column("entry_url", String(512), nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

portal_subsystem_visits_table = Table(
    "portal_subsystem_visits",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("subsystem_code", String(64), nullable=False),
    Column("user_id", Integer, nullable=True),
    Column("visited_at", String(32), nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

portal_notices_table = Table(
    "portal_notices",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("source", String(128), nullable=False),
    Column("category", String(64), nullable=False),
    Column("body", Text, nullable=False),
    Column("pinned", Boolean, nullable=False, default=False),
    Column("published_at", String(32), nullable=False),
    Column("read_count", Integer, nullable=False, default=0),
    Column("status", String(32), nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
)

portal_documents_table = Table(
    "portal_documents",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("location", String(128), nullable=False),
    Column("owner", String(128), nullable=False),
    Column("file_type", String(16), nullable=False),
    Column("summary", Text, nullable=False),
    Column("status", String(32), nullable=True),
    Column("updated_at", String(32), nullable=False),
    Column("favorite_count", Integer, nullable=False, default=0),
    Column("visit_count", Integer, nullable=False, default=0),
    Column("created_at", String(32), nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
    # External integration fields (reserved for Feishu/WPS cloud docs)
    Column("external_id", String(256), nullable=True),
    Column("external_source", String(32), nullable=True),
    Column("external_url", String(1024), nullable=True),
)

portal_resources_table = Table(
    "portal_resources",
    metadata,
    Column("code", String(64), primary_key=True),
    Column("title", String(255), nullable=False),
    Column("category", String(64), nullable=False),
    Column("description", String(255), nullable=False),
    Column("body", Text, nullable=False),
    Column("owner", String(128), nullable=False),
    Column("icon_tone", String(32), nullable=False, default="app-blue"),
    Column("pinned", Boolean, nullable=False, default=False),
    Column("status", String(32), nullable=True),
    Column("updated_at", String(32), nullable=False),
    Column("created_at", String(32), nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

portal_services_table = Table(
    "portal_services",
    metadata,
    Column("code", String(64), primary_key=True),
    Column("title", String(255), nullable=False),
    Column("category", String(64), nullable=False),
    Column("description", Text, nullable=False),
    Column("materials", Text, nullable=False),
    Column("audience", String(128), nullable=False),
    Column("contact", String(128), nullable=False),
    Column("status", String(32), nullable=False, default="active"),
    Column("subscribed_count", Integer, nullable=False, default=0),
    Column("updated_at", String(32), nullable=False),
    Column("created_at", String(32), nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

portal_news_table = Table(
    "portal_news",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("source", String(128), nullable=False),
    Column("category", String(64), nullable=False),
    Column("body", Text, nullable=False),
    Column("pinned", Boolean, nullable=False, default=False),
    Column("status", String(32), nullable=True),
    Column("published_at", String(32), nullable=False),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

portal_user_preferences_table = Table(
    "portal_user_preferences",
    metadata,
    Column("user_id", Integer, primary_key=True),
    Column("preferences_json", Text, nullable=False),
    Column("status", String(32), nullable=True),
    Column("updated_at", String(32), nullable=False),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

enterprise_repair_tickets_table = Table(
    "enterprise_repair_tickets",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("location", String(255), nullable=False),
    Column("description", Text, nullable=False),
    Column("priority", String(16), nullable=False, default="normal"),
    Column("status", String(32), nullable=False, default="submitted"),
    Column("assignee", String(128), nullable=True),
    Column("requester_id", Integer, nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
    Column("rating", Integer, nullable=True),
    Column("completed_at", String(32), nullable=True),
)

enterprise_asset_items_table = Table(
    "enterprise_asset_items",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asset_code", String(128), nullable=False),
    Column("name", String(255), nullable=False),
    Column("category", String(128), nullable=False),
    Column("location", String(255), nullable=False),
    Column("status", String(32), nullable=False, default="available"),
    Column("custodian", String(128), nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

enterprise_oa_flows_table = Table(
    "enterprise_oa_flows",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("flow_type", String(128), nullable=False),
    Column("status", String(32), nullable=False, default="pending"),
    Column("initiator_id", Integer, nullable=True),
    Column("current_handler", String(128), nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
)

asset_borrow_records_table = Table(
    "asset_borrow_records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("asset_id", Integer, nullable=False),
    Column("user_id", Integer, nullable=False),
    Column("borrow_date", String(32), nullable=False),
    Column("expected_return_date", String(32), nullable=True),
    Column("actual_return_date", String(32), nullable=True),
    Column("status", String(32), nullable=False, default="borrowed"),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
)

oa_approval_records_table = Table(
    "oa_approval_records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("flow_id", Integer, nullable=False),
    Column("approver_id", Integer, nullable=False),
    Column("step_order", Integer, nullable=False),
    Column("action", String(32), nullable=True),
    Column("comment", Text, nullable=True),
    Column("created_at", String(32), nullable=False),
)

# ── Phase 3: HR & Finance ───────────────────────────────────────────

hr_requests_table = Table(
    "hr_requests",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("request_type", String(32), nullable=False),
    Column("status", String(32), nullable=False, default="pending"),
    Column("applicant_id", Integer, nullable=True),
    Column("content_json", Text, nullable=True),
    Column("approved_by", Integer, nullable=True),
    Column("approved_at", String(32), nullable=True),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
)

finance_claims_table = Table(
    "finance_claims",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("amount", Float, nullable=True),
    Column("status", String(32), nullable=False, default="pending"),
    Column("applicant_id", Integer, nullable=True),
    Column("budget_id", Integer, nullable=True),
    Column("current_handler", String(128), nullable=True),
    Column("description", Text, nullable=True),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
)

finance_budgets_table = Table(
    "finance_budgets",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("category", String(128), nullable=False),
    Column("amount_total", Float, nullable=False, default=0.0),
    Column("amount_used", Float, nullable=False, default=0.0),
    Column("fiscal_year", Integer, nullable=False),
    Column("description", Text, nullable=True),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
)

finance_approval_records_table = Table(
    "finance_approval_records",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("claim_id", Integer, nullable=False),
    Column("approver_id", Integer, nullable=False),
    Column("step_order", Integer, nullable=False),
    Column("action", String(32), nullable=True),
    Column("comment", Text, nullable=True),
    Column("created_at", String(32), nullable=False),
)

# ── Phase 4 T17: Website, Estate, Employment ───────────────────────────

cms_sites_table = Table(
    "cms_sites",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("domain", String(255), nullable=True),
    Column("category", String(128), nullable=False),
    Column("status", String(32), nullable=False, default="draft"),
    Column("owner_dept", String(128), nullable=True),
    Column("columns_json", Text, nullable=True),
    Column("description", Text, nullable=True),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
)

estate_spaces_table = Table(
    "estate_spaces",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("name", String(255), nullable=False),
    Column("code", String(128), nullable=False),
    Column("category", String(64), nullable=False),
    Column("building", String(128), nullable=True),
    Column("floor", String(32), nullable=True),
    Column("area_sqm", Float, nullable=True),
    Column("status", String(32), nullable=False, default="vacant"),
    Column("department_id", String(64), nullable=True),
    Column("description", Text, nullable=True),
    Column("contact_person", String(128), nullable=True),
    Column("org_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
)

job_postings_table = Table(
    "job_postings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("company_name", String(255), nullable=False),
    Column("position_category", String(64), nullable=False),
    Column("salary_range", String(128), nullable=True),
    Column("location", String(255), nullable=True),
    Column("requirements", Text, nullable=True),
    Column("status", String(32), nullable=False, default="open"),
    Column("contact_info", String(255), nullable=True),
    Column("description", Text, nullable=True),
    Column("posted_date", String(32), nullable=True),
    Column("deadline", String(32), nullable=True),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("owner_id", Integer, nullable=True),
    Column("visibility", String(16), nullable=False, default="org"),
    Column("sensitivity", String(16), nullable=False, default="normal"),
    Column("created_by", Integer, nullable=True),
    Column("updated_by", Integer, nullable=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
)

orgs_table = Table(
    "orgs",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("name", String(128), nullable=False),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
)

departments_table = Table(
    "departments",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("org_id", String(64), nullable=False),
    Column("name", String(128), nullable=False),
    Column("parent_id", String(64), nullable=True),
    Column("path", String(512), nullable=False, default=""),
    Column("level", Integer, nullable=False, default=0),
    Column("sort_order", Integer, nullable=False, default=0),
    Column("is_active", Boolean, nullable=False, default=True),
    Column("created_at", String(32), nullable=False),
    Column("updated_at", String(32), nullable=False),
)

notifications_table = Table(
    "notifications",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", Integer, nullable=False),
    Column("title", String(255), nullable=False),
    Column("content", Text, nullable=True),
    Column("type", String(32), nullable=False, default="info"),
    Column("reference_type", String(64), nullable=True),
    Column("reference_id", String(128), nullable=True),
    Column("is_read", Boolean, nullable=False, default=False),
    Column("org_id", String(64), nullable=True),
    Column("department_id", String(64), nullable=True),
    Column("created_at", String(32), nullable=False),
)

DEFAULT_EMBED_URLS = {
    "feishu": "https://www.feishu.cn/",
    "dingtalk": "https://www.dingtalk.com/",
}

# Phase 4: DEFAULT_TASKS now include RBAC attribution columns.
DEFAULT_TASKS: list[dict[str, Any]] = []  # No hardcoded seed tasks

DEFAULT_EVENTS: list[dict[str, Any]] = []  # No hardcoded seed events

DEFAULT_SHORTCUTS = [
    ["公告", "通知中心", "app-orange"],
    ["智能问答", "AI 助手", "app-purple"],
    ["会议", "会议管理", "app-blue"],
    ["表单", "流程申请", "app-cyan"],
    ["轻审批", "审批中心", "app-red"],
    ["笔记", "我的笔记", "app-orange"],
    ["汇报", "工作汇报", "app-blue"],
    ["日历", "日程管理", "app-blue"],
    ["待办中心", "任务管理", "app-green"],
    ["融合门户", "门户首页", "app-red"],
]

DEFAULT_SYSTEMS = [
    "督办系统",
    "一体化教学云平台",
    "OA 系统",
    "网站群",
    "党建系统",
    "校友系统",
    "人事系统",
    "学工系统",
    "就业系统",
    "心理系统",
    "财务系统",
    "房产管理系统",
    "资产管理系统",
    "数据门户",
    "报修管理系统",
]

DEFAULT_SERVICES: list[dict[str, Any]] = [
    # 人事服务
    {"code": "hr-attendance", "title": "教职工考勤", "category": "人事服务", "description": "教职工日常考勤记录、异常申诉与月度汇总查询。", "materials": "身份证明、考勤异常说明", "audience": "全校教职工", "contact": "人事处服务台", "status": "active"},
    {"code": "hr-leave", "title": "教职工请假", "category": "人事服务", "description": "教职工病假、事假、婚假等各类请假申请与审批。", "materials": "身份证明、请假证明材料", "audience": "全校教职工", "contact": "人事处服务台", "status": "active"},
    {"code": "hr-certificate", "title": "在职证明", "category": "人事服务", "description": "在线申请开具在职证明、收入证明等。", "materials": "身份证明、申请用途说明", "audience": "全校教职工", "contact": "人事处服务台", "status": "active"},
    # 学生服务
    {"code": "stu-enrollment", "title": "新生报到注册", "category": "学生服务", "description": "新生入学资格审核、信息登记与报到注册。", "materials": "录取通知书、身份证明", "audience": "全体学生", "contact": "教务处服务台", "status": "active"},
    {"code": "stu-award", "title": "奖助学金申请", "category": "学生服务", "description": "国家级、校级奖助学金的申报、评审与发放管理。", "materials": "成绩单、家庭经济情况证明", "audience": "全体学生", "contact": "学生处服务台", "status": "active"},
    {"code": "stu-leave", "title": "学生请假", "category": "学生服务", "description": "学生课程请假、离校申请与审批。", "materials": "身份证明、请假证明材料", "audience": "全体学生", "contact": "教务处服务台", "status": "active"},
    # 信息服务
    {"code": "info-wifi", "title": "校园网络开通", "category": "信息服务", "description": "校园有线/无线网络账户开通与认证。", "materials": "身份证明、设备MAC地址", "audience": "全校师生", "contact": "信息中心服务台", "status": "active"},
    {"code": "info-vpn", "title": "VPN 申请", "category": "信息服务", "description": "校外访问校内资源的VPN账号申请。", "materials": "身份证明", "audience": "全校师生", "contact": "信息中心服务台", "status": "active"},
    {"code": "info-account", "title": "统一账号管理", "category": "信息服务", "description": "校园统一身份认证账号的开通、重置与注销。", "materials": "身份证明", "audience": "全校师生", "contact": "信息中心服务台", "status": "active"},
    # 财务资产
    {"code": "fin-salary", "title": "工资查询", "category": "财务资产", "description": "教职工月度工资条、年终奖金与个税明细查询。", "materials": "身份证明", "audience": "全校教职工", "contact": "财务处服务台", "status": "active"},
    {"code": "fin-reimburse", "title": "费用报销", "category": "财务资产", "description": "差旅费、办公费等日常费用报销申请与审批。", "materials": "发票原件、费用明细、审批单", "audience": "全校师生", "contact": "财务处服务台", "status": "active"},
    {"code": "asset-borrow", "title": "资产借用", "category": "财务资产", "description": "教学设备、实验器材等固定资产的借用申请。", "materials": "身份证明、借用说明", "audience": "全校师生", "contact": "资产管理处服务台", "status": "active"},
    # 教学科研
    {"code": "teach-course", "title": "课程调整申请", "category": "教学科研", "description": "教师调课、停课、补课申请的提交与审批。", "materials": "课程信息、调整原因说明", "audience": "全校教师", "contact": "教务处服务台", "status": "active"},
    {"code": "teach-lab", "title": "实验室预约", "category": "教学科研", "description": "教学实验室、科研实验室的在线预约与使用管理。", "materials": "实验方案、安全承诺书", "audience": "全校师生", "contact": "实验室管理处服务台", "status": "active"},
    {"code": "res-project", "title": "科研项目申报", "category": "教学科研", "description": "国家级、省部级科研项目的申报、立项与进度管理。", "materials": "项目申报书、预算表", "audience": "全校教师", "contact": "科研处服务台", "status": "active"},
]

DEFAULT_KNOWLEDGE: list[dict[str, Any]] = []

DEFAULT_NOTICES: list[dict[str, Any]] = []  # No hardcoded seed notices

DEFAULT_DOCUMENTS: list[dict[str, Any]] = []  # No hardcoded seed documents

DEFAULT_REPAIR_TICKETS: list[dict[str, Any]] = []  # No hardcoded seed repair tickets

DEFAULT_ASSET_ITEMS: list[dict[str, Any]] = []  # No hardcoded seed asset items

DEFAULT_OA_FLOWS: list[dict[str, Any]] = []  # No hardcoded seed OA flows

_PORTAL_BASE = {
    "org_id": "default",
    "department_id": "HQ",
    "owner_id": 1,
    "visibility": "org",
    "sensitivity": "normal",
}

DEFAULT_SUBSYSTEMS = [
    ("supervision", "督办系统", "运营管理", "跟踪重点事项、责任人和办理进度。", "党政办公室", "综合服务台", "app-orange"),
    ("teaching-cloud", "一体化教学云平台", "教学科研", "课程、教学计划和教学运行数据管理。", "教务办公室", "教学服务台", "app-purple"),
    ("oa", "OA 系统", "协同办公", "流程、通知、文件流转和组织协同工作入口。", "党政办公室", "OA 支持", "app-blue"),
    ("website", "网站群", "宣传门户", "站点内容、栏目和发布状态管理。", "宣传办公室", "网站支持", "app-green"),
    ("party", "党建系统", "组织建设", "组织活动、学习资料和党建工作台账。", "组织办公室", "党建支持", "app-red"),
    ("alumni", "校友系统", "外联服务", "校友信息、活动和联络服务管理。", "校友办公室", "校友服务台", "app-orange"),
    ("hr", "人事系统", "人事服务", "人员信息、证明、考勤和请假服务。", "人事处", "人事服务台", "app-green"),
    ("student", "学工系统", "学生服务", "学生事务、奖助、就业与心理服务入口。", "学生工作部", "学生服务台", "app-blue"),
    ("employment", "就业系统", "学生服务", "招聘信息、就业数据和就业指导服务。", "就业中心", "就业服务台", "app-purple"),
    ("mental-health", "心理系统", "学生服务", "心理预约、测评和关怀记录入口。", "心理中心", "心理服务台", "app-green"),
    ("finance", "财务系统", "财务资产", "预算、报销、工资查询和财务事项入口。", "财务处", "财务服务台", "app-orange"),
    ("estate", "房产管理系统", "财务资产", "空间、房产和用房信息管理。", "资产与后勤处", "房产服务台", "app-blue"),
    ("assets", "资产管理系统", "财务资产", "资产目录、借用、盘点和维修入口。", "资产与后勤处", "资产服务台", "app-red"),
    ("data-portal", "数据门户", "数据运营", "组织指标、经营数据和专题看板。", "信息中心", "数据服务台", "app-cyan"),
    ("repair", "报修管理系统", "统一服务", "故障报修、派单、处理和满意度反馈。", "后勤服务中心", "报修服务台", "app-green"),
]

DEFAULT_SUBSYSTEM_ACTIONS = {
    "supervision": [
        {"label": "督办事项", "kind": "records"},
        {"label": "责任清单", "kind": "records"},
        {"label": "办理进度", "kind": "dashboard"},
    ],
    "teaching-cloud": [
        {"label": "课程运行", "kind": "records"},
        {"label": "调停课记录", "kind": "records"},
        {"label": "教学通知", "kind": "notices"},
    ],
    "oa": [
        {"label": "待办流程", "kind": "records"},
        {"label": "文件流转", "kind": "documents"},
        {"label": "办公通知", "kind": "notices"},
    ],
    "website": [
        {"label": "站点列表", "kind": "records"},
        {"label": "待审稿件", "kind": "records"},
        {"label": "发布统计", "kind": "dashboard"},
    ],
    "party": [
        {"label": "组织活动", "kind": "records"},
        {"label": "学习资料", "kind": "resources"},
        {"label": "工作台账", "kind": "documents"},
    ],
    "alumni": [
        {"label": "校友名录", "kind": "records"},
        {"label": "活动管理", "kind": "records"},
        {"label": "联络记录", "kind": "records"},
    ],
    "hr": [
        {"label": "证明申请", "kind": "records"},
        {"label": "请假考勤", "kind": "records"},
        {"label": "人事资料", "kind": "documents"},
    ],
    "student": [
        {"label": "学生事务", "kind": "records"},
        {"label": "奖助事项", "kind": "records"},
        {"label": "学生服务", "kind": "services"},
    ],
    "employment": [
        {"label": "招聘信息", "kind": "records"},
        {"label": "宣讲会", "kind": "records"},
        {"label": "就业数据", "kind": "dashboard"},
    ],
    "mental-health": [
        {"label": "咨询预约", "kind": "records"},
        {"label": "测评记录", "kind": "records"},
        {"label": "心理资源", "kind": "resources"},
    ],
    "finance": [
        {"label": "报销单", "kind": "records"},
        {"label": "预算项目", "kind": "records"},
        {"label": "财务文档", "kind": "documents"},
    ],
    "estate": [
        {"label": "房间台账", "kind": "records"},
        {"label": "用房申请", "kind": "records"},
        {"label": "维修关联", "kind": "services"},
    ],
    "assets": [
        {"label": "资产目录", "kind": "records"},
        {"label": "借用申请", "kind": "records"},
        {"label": "维修记录", "kind": "services"},
    ],
    "data-portal": [
        {"label": "指标看板", "kind": "dashboard"},
        {"label": "专题数据", "kind": "records"},
        {"label": "数据资源", "kind": "resources"},
    ],
    "repair": [
        {"label": "新建报修", "kind": "records"},
        {"label": "工单列表", "kind": "records"},
        {"label": "服务评价", "kind": "dashboard"},
    ],
}

DEFAULT_MENU_ITEMS = {
    "supervision": [
        {"section": "督办事项", "items": [
            {"code": "items", "label": "全部事项", "icon": "i-list", "href": "#/subsystem/supervision/items"},
            {"code": "new-item", "label": "新建督办", "icon": "i-plus", "href": "#/subsystem/supervision/items/new"},
            {"code": "my-items", "label": "我的督办", "icon": "i-user", "href": "#/subsystem/supervision/items/my"},
        ]},
        {"section": "责任清单", "items": [
            {"code": "units", "label": "责任单位", "icon": "i-grid", "href": "#/subsystem/supervision/units"},
            {"code": "progress", "label": "办理进度", "icon": "i-chart", "href": "#/subsystem/supervision/progress"},
        ]},
        {"section": "统计分析", "items": [
            {"code": "stats", "label": "办结统计", "icon": "i-bar-chart", "href": "#/subsystem/supervision/stats"},
            {"code": "overdue", "label": "逾期分析", "icon": "i-alert", "href": "#/subsystem/supervision/overdue"},
        ]},
    ],
    "oa": [
        {"section": "流程中心", "items": [
            {"code": "todo", "label": "待办流程", "icon": "i-clock", "href": "#/subsystem/oa/flows/todo"},
            {"code": "done", "label": "已办流程", "icon": "i-check", "href": "#/subsystem/oa/flows/done"},
            {"code": "my-flows", "label": "我发起的", "icon": "i-user", "href": "#/subsystem/oa/flows/my"},
        ]},
        {"section": "文件管理", "items": [
            {"code": "files", "label": "文件流转", "icon": "i-file", "href": "#/subsystem/oa/files"},
            {"code": "docs", "label": "公文管理", "icon": "i-doc", "href": "#/subsystem/oa/docs"},
        ]},
        {"section": "办公辅助", "items": [
            {"code": "meetings", "label": "会议管理", "icon": "i-calendar", "href": "#/subsystem/oa/meetings"},
            {"code": "notices", "label": "通知公告", "icon": "i-bell", "href": "#/subsystem/oa/notices"},
        ]},
    ],
    "hr": [
        {"section": "证明申请", "items": [
            {"code": "cert-employment", "label": "在职证明", "icon": "i-file", "href": "#/subsystem/hr/certificates/employment"},
            {"code": "cert-income", "label": "收入证明", "icon": "i-file", "href": "#/subsystem/hr/certificates/income"},
            {"code": "cert-other", "label": "其他证明", "icon": "i-file", "href": "#/subsystem/hr/certificates/other"},
        ]},
        {"section": "考勤请假", "items": [
            {"code": "leave", "label": "请假申请", "icon": "i-edit", "href": "#/subsystem/hr/leave"},
            {"code": "attendance", "label": "考勤记录", "icon": "i-list", "href": "#/subsystem/hr/attendance"},
            {"code": "overtime", "label": "加班申请", "icon": "i-clock", "href": "#/subsystem/hr/overtime"},
        ]},
        {"section": "人员信息", "items": [
            {"code": "staff", "label": "人员档案", "icon": "i-users", "href": "#/subsystem/hr/staff"},
            {"code": "dept-info", "label": "部门信息", "icon": "i-grid", "href": "#/subsystem/hr/departments"},
        ]},
    ],
    "finance": [
        {"section": "报销管理", "items": [
            {"code": "claims", "label": "报销申请", "icon": "i-edit", "href": "#/subsystem/finance/claims"},
            {"code": "my-claims", "label": "我的报销", "icon": "i-user", "href": "#/subsystem/finance/claims/my"},
            {"code": "claim-approve", "label": "报销审批", "icon": "i-check", "href": "#/subsystem/finance/claims/approve"},
        ]},
        {"section": "预算管理", "items": [
            {"code": "budget", "label": "预算项目", "icon": "i-list", "href": "#/subsystem/finance/budgets"},
            {"code": "budget-exec", "label": "预算执行", "icon": "i-chart", "href": "#/subsystem/finance/budgets/exec"},
        ]},
        {"section": "材料清单", "items": [
            {"code": "materials", "label": "费用材料", "icon": "i-file", "href": "#/subsystem/finance/materials"},
            {"code": "receipts", "label": "票据管理", "icon": "i-doc", "href": "#/subsystem/finance/receipts"},
        ]},
    ],
    "assets": [
        {"section": "资产管理", "items": [
            {"code": "items", "label": "资产台账", "icon": "i-list", "href": "#/subsystem/asset/items"},
            {"code": "new-item", "label": "资产入库", "icon": "i-plus", "href": "#/subsystem/asset/items/new"},
        ]},
        {"section": "借用管理", "items": [
            {"code": "borrow", "label": "借用申请", "icon": "i-edit", "href": "#/subsystem/asset/borrow"},
            {"code": "borrow-records", "label": "借用记录", "icon": "i-file", "href": "#/subsystem/asset/borrow/records"},
            {"code": "return", "label": "归还管理", "icon": "i-check", "href": "#/subsystem/asset/return"},
        ]},
        {"section": "盘点维护", "items": [
            {"code": "inventory", "label": "资产盘点", "icon": "i-search", "href": "#/subsystem/asset/inventory"},
            {"code": "repair-link", "label": "维修关联", "icon": "i-tool", "href": "#/subsystem/asset/repair"},
        ]},
    ],
    "repair": [
        {"section": "工单管理", "items": [
            {"code": "tickets", "label": "全部工单", "icon": "i-list", "href": "#/subsystem/repair/tickets"},
            {"code": "new-ticket", "label": "新建报修", "icon": "i-plus", "href": "#/subsystem/repair/tickets/new"},
            {"code": "my-tickets", "label": "我的报修", "icon": "i-user", "href": "#/subsystem/repair/tickets/my"},
        ]},
        {"section": "派单处理", "items": [
            {"code": "assign", "label": "待派工单", "icon": "i-send", "href": "#/subsystem/repair/tickets/assign"},
            {"code": "processing", "label": "处理中", "icon": "i-clock", "href": "#/subsystem/repair/tickets/processing"},
        ]},
        {"section": "统计评价", "items": [
            {"code": "stats", "label": "工单统计", "icon": "i-chart", "href": "#/subsystem/repair/stats"},
            {"code": "feedback", "label": "服务评价", "icon": "i-star", "href": "#/subsystem/repair/feedback"},
        ]},
    ],
    "data-portal": [
        {"section": "数据看板", "items": [
            {"code": "overview", "label": "数据概览", "icon": "i-chart", "href": "#/subsystem/data-portal/overview"},
            {"code": "metrics", "label": "指标详情", "icon": "i-list", "href": "#/subsystem/data-portal/metrics"},
            {"code": "trends", "label": "趋势分析", "icon": "i-bar-chart", "href": "#/subsystem/data-portal/trends"},
        ]},
        {"section": "专题数据", "items": [
            {"code": "tickets-data", "label": "工单数据", "icon": "i-file", "href": "#/subsystem/data-portal/tickets"},
            {"code": "assets-data", "label": "资产数据", "icon": "i-file", "href": "#/subsystem/data-portal/assets"},
            {"code": "flows-data", "label": "流程数据", "icon": "i-file", "href": "#/subsystem/data-portal/flows"},
        ]},
        {"section": "数据资源", "items": [
            {"code": "exports", "label": "数据导出", "icon": "i-download", "href": "#/subsystem/data-portal/exports"},
            {"code": "reports", "label": "报表配置", "icon": "i-settings", "href": "#/subsystem/data-portal/reports"},
        ]},
    ],
    # ── Phase 4 T17: website, estate, employment ────────────────────────
    "website": [
        {"section": "站点管理", "items": [
            {"code": "sites", "label": "全部站点", "icon": "i-list", "href": "#/subsystem/website/sites"},
            {"code": "new-site", "label": "新建站点", "icon": "i-plus", "href": "#/subsystem/website/sites/new"},
            {"code": "drafts", "label": "草稿箱", "icon": "i-edit", "href": "#/subsystem/website/sites/drafts"},
        ]},
        {"section": "栏目内容", "items": [
            {"code": "columns", "label": "栏目管理", "icon": "i-grid", "href": "#/subsystem/website/columns"},
            {"code": "pages", "label": "页面管理", "icon": "i-file", "href": "#/subsystem/website/pages"},
        ]},
        {"section": "发布统计", "items": [
            {"code": "published", "label": "已发布站点", "icon": "i-check", "href": "#/subsystem/website/published"},
            {"code": "stats", "label": "站点统计", "icon": "i-chart", "href": "#/subsystem/website/stats"},
        ]},
    ],
    "estate": [
        {"section": "空间管理", "items": [
            {"code": "spaces", "label": "全部空间", "icon": "i-list", "href": "#/subsystem/estate/spaces"},
            {"code": "new-space", "label": "新增空间", "icon": "i-plus", "href": "#/subsystem/estate/spaces/new"},
            {"code": "occupied", "label": "已占用", "icon": "i-check", "href": "#/subsystem/estate/spaces/occupied"},
        ]},
        {"section": "用房信息", "items": [
            {"code": "by-building", "label": "按楼栋", "icon": "i-grid", "href": "#/subsystem/estate/by-building"},
            {"code": "vacant", "label": "空置空间", "icon": "i-info", "href": "#/subsystem/estate/vacant"},
        ]},
        {"section": "统计分析", "items": [
            {"code": "stats", "label": "用房统计", "icon": "i-chart", "href": "#/subsystem/estate/stats"},
            {"code": "maintenance", "label": "维护记录", "icon": "i-tool", "href": "#/subsystem/estate/maintenance"},
        ]},
    ],
    "employment": [
        {"section": "岗位管理", "items": [
            {"code": "postings", "label": "全部岗位", "icon": "i-list", "href": "#/subsystem/employment/postings"},
            {"code": "new-posting", "label": "发布岗位", "icon": "i-plus", "href": "#/subsystem/employment/postings/new"},
            {"code": "openings", "label": "在招岗位", "icon": "i-eye", "href": "#/subsystem/employment/postings/open"},
        ]},
        {"section": "招聘企业", "items": [
            {"code": "companies", "label": "企业信息", "icon": "i-grid", "href": "#/subsystem/employment/companies"},
            {"code": "positions", "label": "职位分类", "icon": "i-tag", "href": "#/subsystem/employment/positions"},
        ]},
        {"section": "就业统计", "items": [
            {"code": "stats", "label": "招聘统计", "icon": "i-chart", "href": "#/subsystem/employment/stats"},
            {"code": "closed", "label": "已关闭", "icon": "i-check", "href": "#/subsystem/employment/closed"},
        ]},
    ],
}

DEFAULT_SUBSYSTEM_APPROVAL_CHAINS: dict[str, list[dict[str, Any]]] = {
    "repair":  [{"role": "dept_leader", "level": 1}],
    "oa":      [{"role": "dept_leader", "level": 1}, {"role": "org_admin", "level": 2}],
    "hr":      [{"role": "dept_leader", "level": 1}],
    "finance": [{"role": "dept_leader", "level": 1}, {"role": "org_admin", "level": 2}],
}

# Shell subsystems configured as disabled (Phase 2) or iframe entries.
# Deep subsystems (oa/hr/finance/assets/repair/supervision) remain entry_type=internal.
SHELL_SUBSYSTEM_ENTRY = {
    "teaching-cloud":   ("iframe", ""),
    # Phase 4 T17: website, estate, employment activated as internal
    "website":          ("internal", None),
    "party":            ("disabled", None),
    "alumni":           ("disabled", None),
    "student":          ("disabled", None),
    "employment":       ("internal", None),
    "mental-health":    ("disabled", None),
    "estate":           ("internal", None),
}

DEFAULT_NEWS: list[dict[str, Any]] = []  # No hardcoded seed news


# ═════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════


def _alembic_has_run(engine: Any) -> bool:
    """Return True if the alembic_version table exists (i.e. Alembic migrations have been applied).

    When Alembic manages the schema we must NOT call metadata.create_all()
    because that would recreate tables the migration already created or altered.

    Uses SQLAlchemy's dialect-agnostic inspector so this works on both
    SQLite (dev) and PostgreSQL (prod).
    """
    try:
        from sqlalchemy import inspect
        return inspect(engine).has_table("alembic_version")
    except Exception:
        return False


# ═════════════════════════════════════════════════════════════════════
# PortalStore
# ═════════════════════════════════════════════════════════════════════


class PortalStore(
    BaseStore,
    PortalMixin,
    SubsystemsMixin,
    SearchMixin,
    RepairMixin,
    AssetMixin,
    OaMixin,
    HrMixin,
    FinanceMixin,
    WebsiteMixin,
    EstateMixin,
    EmploymentMixin,
    NotificationMixin,
):
    """Unified store singleton — Table definitions + metadata live at module level."""

    def __init__(self) -> None:
        super().__init__()  # BaseStore sets self._lock
        # Expose table refs for mixins (they access via self._*_table)
        self._portal_subsystems_table = portal_subsystems_table
        self._portal_subsystem_visits_table = portal_subsystem_visits_table
        self._portal_notices_table = portal_notices_table
        self._portal_documents_table = portal_documents_table
        self._portal_resources_table = portal_resources_table
        self._portal_services_table = portal_services_table
        self._portal_news_table = portal_news_table
        self._portal_user_preferences_table = portal_user_preferences_table
        self._orgs_table = orgs_table
        self._departments_table = departments_table
        self._enterprise_repair_tickets_table = enterprise_repair_tickets_table
        self._enterprise_asset_items_table = enterprise_asset_items_table
        self._enterprise_oa_flows_table = enterprise_oa_flows_table
        self._asset_borrow_records_table = asset_borrow_records_table
        self._oa_approval_records_table = oa_approval_records_table
        self._hr_requests_table = hr_requests_table
        self._finance_claims_table = finance_claims_table
        self._finance_budgets_table = finance_budgets_table
        self._finance_approval_records_table = finance_approval_records_table
        self._cms_sites_table = cms_sites_table
        self._estate_spaces_table = estate_spaces_table
        self._job_postings_table = job_postings_table
        self._notifications_table = notifications_table
        self._ensure_schema()

    @contextmanager
    def _session(self) -> Iterator[Session]:
        """Override BaseStore._session — ensure schema before every session."""
        self._ensure_schema()
        db = get_session_local()()
        try:
            yield db
        finally:
            db.close()

    def _ensure_schema(self) -> None:
        with self._lock:
            engine = get_engine()
            # Phase 1: if Alembic has been run, skip DDL (create_all / ensure columns)
            # so we don't conflict with migration-managed schema.  Data seeding
            # still runs so the app has default content out of the box.
            alembic_managed = _alembic_has_run(engine)
            if not alembic_managed:
                metadata.create_all(bind=engine)
                self._ensure_sqlite_columns(engine)
            else:
                self._ensure_portal_asset_tables(engine)
            self._seed_defaults(engine)

    def _ensure_portal_asset_tables(self, engine: Any) -> None:
        portal_tables = [
            portal_subsystems_table,
            portal_subsystem_visits_table,
            portal_notices_table,
            portal_documents_table,
            portal_resources_table,
            portal_services_table,
            portal_news_table,
            portal_user_preferences_table,
            enterprise_repair_tickets_table,
            enterprise_asset_items_table,
            enterprise_oa_flows_table,
            asset_borrow_records_table,
            oa_approval_records_table,
            hr_requests_table,
            finance_claims_table,
            finance_budgets_table,
            finance_approval_records_table,
            cms_sites_table,
            estate_spaces_table,
            job_postings_table,
        ]
        for table in portal_tables:
            table.create(bind=engine, checkfirst=True)

    def _seed_defaults(self, engine: Any) -> None:
        """Seed default tasks, events, and embed URLs if not already present."""
        session_local = get_session_local()
        with session_local() as db:
            tasks_seeded = db.scalar(
                select(settings_table.c.value_json).where(settings_table.c.key == "tasks_seeded"),
            )
            if DEFAULT_TASKS and tasks_seeded is None and db.scalar(select(func.count()).select_from(tasks_table)) == 0:
                db.execute(insert(tasks_table), DEFAULT_TASKS)
                db.execute(
                    insert(settings_table).values(
                        key="tasks_seeded",
                        value_json=json.dumps("true", ensure_ascii=False),
                    ),
                )
            events_seeded = db.scalar(
                select(settings_table.c.value_json).where(settings_table.c.key == "events_seeded"),
            )
            if DEFAULT_EVENTS and events_seeded is None and db.scalar(select(func.count()).select_from(events_table)) == 0:
                db.execute(insert(events_table), DEFAULT_EVENTS)
                db.execute(
                    insert(settings_table).values(
                        key="events_seeded",
                        value_json=json.dumps("true", ensure_ascii=False),
                    ),
                )
            for key, value in DEFAULT_EMBED_URLS.items():
                existing = db.scalar(
                    select(settings_table.c.value_json).where(settings_table.c.key == key),
                )
                if existing is None:
                    db.execute(
                        insert(settings_table).values(
                            key=key,
                            value_json=json.dumps(value, ensure_ascii=False),
                        ),
                    )
            now = datetime.now(timezone.utc).isoformat()
            if db.scalar(select(func.count()).select_from(portal_subsystems_table)) == 0:
                db.execute(insert(portal_subsystems_table), [
                    {
                        **_PORTAL_BASE,
                        "code": code,
                        "name": name,
                        "category": category,
                        "description": description,
                        "status": "active",
                        "entry_type": SHELL_SUBSYSTEM_ENTRY.get(code, ("internal", None))[0],
                        "entry_url": SHELL_SUBSYSTEM_ENTRY.get(code, ("internal", None))[1],
                        "owner_department": owner_department,
                        "owner_name": owner_department,
                        "support_contact": support_contact,
                        "icon_tone": tone,
                        "sort_order": index,
                        "is_featured": index < 6,
                        "common_actions_json": json.dumps(
                            DEFAULT_SUBSYSTEM_ACTIONS.get(code, [{"label": "查看概览", "kind": "overview"}]),
                            ensure_ascii=False,
                        ),
                        "related_resources_json": json.dumps(["制度手册", "服务目录"], ensure_ascii=False),
                        "menu_items_json": json.dumps(
                            DEFAULT_MENU_ITEMS.get(code, []), ensure_ascii=False,
                        ),
                        "approval_chain_json": json.dumps(
                            DEFAULT_SUBSYSTEM_APPROVAL_CHAINS.get(code, []), ensure_ascii=False,
                        ),
                        "created_at": now,
                        "updated_at": now,
                    }
                    for index, (code, name, category, description, owner_department, support_contact, tone)
                    in enumerate(DEFAULT_SUBSYSTEMS, start=1)
                ])
            generic_action_labels = {"查看概览", "查看关联服务", "查看关联资源"}
            for code, *_ in DEFAULT_SUBSYSTEMS:
                desired_actions = DEFAULT_SUBSYSTEM_ACTIONS.get(code)
                if not desired_actions:
                    continue
                current_json = db.scalar(
                    select(portal_subsystems_table.c.common_actions_json)
                    .where(portal_subsystems_table.c.code == code)
                )
                try:
                    current_actions = json.loads(current_json or "[]")
                except json.JSONDecodeError:
                    current_actions = []
                current_labels = {str(action.get("label", "")) for action in current_actions if isinstance(action, dict)}
                desired_labels = {action["label"] for action in desired_actions}
                if current_labels.issubset(generic_action_labels) or not desired_labels.issubset(current_labels):
                    db.execute(
                        update(portal_subsystems_table)
                        .where(portal_subsystems_table.c.code == code)
                        .values(
                            common_actions_json=json.dumps(desired_actions, ensure_ascii=False),
                            updated_at=now,
                        )
                    )
            # Idempotent: update menu_items_json for deep subsystems on existing DBs.
            # Wrapped in try/except because columns may not exist yet on dev DBs
            # that haven't run migration 005 (Alembic adds them later).
            try:
                for code in DEFAULT_MENU_ITEMS:
                    current_menu = db.scalar(
                        select(portal_subsystems_table.c.menu_items_json)
                        .where(portal_subsystems_table.c.code == code)
                    )
                    try:
                        parsed = json.loads(current_menu or "[]")
                    except json.JSONDecodeError:
                        parsed = []
                    desired_menu = DEFAULT_MENU_ITEMS[code]
                    if parsed != desired_menu:
                        db.execute(
                            update(portal_subsystems_table)
                            .where(portal_subsystems_table.c.code == code)
                            .values(
                                menu_items_json=json.dumps(desired_menu, ensure_ascii=False),
                                updated_at=now,
                            )
                        )
            except Exception:
                pass  # column missing — migration 005 not yet applied

            # Idempotent: update entry_type/entry_url for shell subsystems on existing DBs.
            try:
                for code, (entry_type, entry_url) in SHELL_SUBSYSTEM_ENTRY.items():
                    current = db.execute(
                        select(portal_subsystems_table.c.entry_type, portal_subsystems_table.c.entry_url)
                        .where(portal_subsystems_table.c.code == code)
                    ).first()
                    if current and (current.entry_type != entry_type or current.entry_url != entry_url):
                        db.execute(
                            update(portal_subsystems_table)
                            .where(portal_subsystems_table.c.code == code)
                            .values(entry_type=entry_type, entry_url=entry_url, updated_at=now)
                        )
            except Exception:
                pass  # entry_url column missing — migration 005 not yet applied

            # Idempotent: update approval_chain_json for subsystems on existing DBs.
            try:
                for code, chain in DEFAULT_SUBSYSTEM_APPROVAL_CHAINS.items():
                    current = db.scalar(
                        select(portal_subsystems_table.c.approval_chain_json)
                        .where(portal_subsystems_table.c.code == code)
                    )
                    desired = json.dumps(chain, ensure_ascii=False)
                    if (current or "[]") != desired:
                        db.execute(
                            update(portal_subsystems_table)
                            .where(portal_subsystems_table.c.code == code)
                            .values(
                                approval_chain_json=desired,
                                updated_at=now,
                            )
                        )
            except Exception:
                pass  # column missing — migration 012 not yet applied

            if DEFAULT_NOTICES and db.scalar(select(func.count()).select_from(portal_notices_table)) == 0:
                db.execute(insert(portal_notices_table), [
                    {
                        **_PORTAL_BASE,
                        "title": item["title"],
                        "source": item["source"],
                        "category": item["category"],
                        "body": f"{item['title']}。请相关部门按通知要求完成后续工作，并在统一门户中查看办理进展。",
                        "pinned": index == 0,
                        "published_at": f"2026-{item['time'][:2]}-{item['time'][3:5]}T{item['time'][6:]}:00",
                        "read_count": 0,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for index, item in enumerate(DEFAULT_NOTICES)
                ])
            if DEFAULT_DOCUMENTS and db.scalar(select(func.count()).select_from(portal_documents_table)) == 0:
                db.execute(insert(portal_documents_table), [
                    {
                        **_PORTAL_BASE,
                        "name": item["name"],
                        "location": item["location"],
                        "owner": item["owner"],
                        "file_type": item["file_type"],
                        "summary": f"{item['name']}用于门户内协作、查阅和知识沉淀。",
                        "updated_at": f"2026-{item['updated_at'][:2]}-{item['updated_at'][3:]}T09:00:00",
                        "favorite_count": 0,
                        "visit_count": 0,
                        "created_at": now,
                    }
                    for item in DEFAULT_DOCUMENTS
                ])
            if DEFAULT_SERVICES:
                for item in DEFAULT_SERVICES:
                    existing = db.scalar(
                        select(portal_services_table.c.code).where(
                            portal_services_table.c.code == item["code"]
                        )
                    )
                    values = {
                        **_PORTAL_BASE,
                        **item,
                        "subscribed_count": 0,
                        "updated_at": now,
                        "created_at": now,
                    }
                    if existing is None:
                        db.execute(insert(portal_services_table).values(values))
                    else:
                        update_vals = {k: v for k, v in item.items() if k in portal_services_table.c}
                        update_vals["updated_at"] = now
                        db.execute(
                            update(portal_services_table)
                            .where(portal_services_table.c.code == item["code"])
                            .values(**update_vals)
                        )
            if DEFAULT_NEWS and db.scalar(select(func.count()).select_from(portal_news_table)) == 0:
                db.execute(insert(portal_news_table), [
                    {
                        **_PORTAL_BASE,
                        "title": item["title"],
                        "source": item["source"],
                        "category": item["category"],
                        "body": f"{item['title']}。详情将在资讯中心持续更新。",
                        "pinned": index == 0,
                        "published_at": f"{item['published_at']}T09:00:00",
                        "created_at": now,
                        "updated_at": now,
                    }
                    for index, item in enumerate(DEFAULT_NEWS)
                ])
            if DEFAULT_REPAIR_TICKETS and db.scalar(select(func.count()).select_from(enterprise_repair_tickets_table)) == 0:
                db.execute(insert(enterprise_repair_tickets_table), [
                    {
                        **_PORTAL_BASE,
                        **item,
                        "requester_id": 1,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for item in DEFAULT_REPAIR_TICKETS
                ])
            if DEFAULT_ASSET_ITEMS and db.scalar(select(func.count()).select_from(enterprise_asset_items_table)) == 0:
                db.execute(insert(enterprise_asset_items_table), [
                    {
                        **_PORTAL_BASE,
                        **item,
                        "owner_id": 1,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for item in DEFAULT_ASSET_ITEMS
                ])
            if DEFAULT_OA_FLOWS and db.scalar(select(func.count()).select_from(enterprise_oa_flows_table)) == 0:
                db.execute(insert(enterprise_oa_flows_table), [
                    {
                        **_PORTAL_BASE,
                        **item,
                        "initiator_id": 1,
                        "owner_id": 1,
                        "created_at": now,
                        "updated_at": now,
                    }
                    for item in DEFAULT_OA_FLOWS
                ])
            self._seed_dev_users(db, now)
            db.commit()

    def _seed_dev_users(self, db: Any, now: str) -> None:
        """Idempotent: create dev/test users matching Docker seed_dev.py."""
        try:
            from auth.password import hash_password

            DEV_USERS = [
                {"username": "admin", "password": "admin123", "display_name": "Administrator",
                 "email": "admin@hr.example.com", "role": "super_admin"},
                {"username": "org_admin", "password": "Admin123!", "display_name": "Organization Admin",
                 "email": "org_admin@hr.example.com", "role": "org_admin"},
                {"username": "leader", "password": "Admin123!", "display_name": "Department Leader",
                 "email": "leader@hr.example.com", "role": "dept_leader"},
                {"username": "staff", "password": "Admin123!", "display_name": "Department Staff",
                 "email": "staff@hr.example.com", "role": "dept_staff"},
                {"username": "staff2", "password": "staff123", "display_name": "Staff 2",
                 "email": "staff2@hr.example.com", "role": "dept_staff"},
                {"username": "external", "password": "Admin123!", "display_name": "External User",
                 "email": "external@hr.example.com", "role": "external"},
            ]

            role_ids: dict[str, int] = {}
            rows = db.execute(
                text("SELECT id, code FROM roles")
            ).fetchall()
            for row in rows:
                role_ids[row[1]] = row[0]

            if not role_ids:
                return

            for user_def in DEV_USERS:
                existing = db.execute(
                    text("SELECT id FROM users WHERE username = :un"),
                    {"un": user_def["username"]},
                ).fetchone()
                if existing is not None:
                    continue

                pwd_hash = hash_password(user_def["password"])
                result = db.execute(
                    text(
                        "INSERT INTO users (username, password_hash, display_name, email, "
                        "is_active, token_version, must_change_password, created_at, updated_at) "
                        "VALUES (:un, :pw, :dn, :em, 1, 1, 0, :ts, :ts)"
                    ),
                    {"un": user_def["username"], "pw": pwd_hash,
                     "dn": user_def["display_name"], "em": user_def["email"], "ts": now},
                )
                user_id = result.lastrowid

                db.execute(
                    text("INSERT INTO user_org_memberships (user_id, org_id, is_default, created_at) "
                         "VALUES (:uid, 'default', 1, :ts)"),
                    {"uid": user_id, "ts": now},
                )
                db.execute(
                    text("INSERT INTO user_department_memberships (user_id, org_id, department_id, "
                         "is_primary, created_at) VALUES (:uid, 'default', 'HQ', 1, :ts)"),
                    {"uid": user_id, "ts": now},
                )
                role_id = role_ids.get(user_def["role"])
                if role_id:
                    db.execute(
                        text("INSERT INTO role_bindings (user_id, role_id, org_id, department_id, created_at) "
                             "VALUES (:uid, :rid, 'default', 'HQ', :ts)"),
                        {"uid": user_id, "rid": role_id, "ts": now},
                    )
        except Exception:
            pass  # Non-critical

    def _ensure_sqlite_columns(self, engine: Any) -> None:
        if not str(engine.url).startswith("sqlite"):
            return
        expected = {
            "portal_tasks": {
                "deadline": "VARCHAR(32)",
                "overdue_notified_at": "VARCHAR(32)",
                # Phase 4: RBAC attribution columns
                "org_id": "VARCHAR(64)",
                "department_id": "VARCHAR(64)",
                "owner_id": "INTEGER",
                "visibility": "VARCHAR(16) NOT NULL DEFAULT 'private'",
                "sensitivity": "VARCHAR(16) NOT NULL DEFAULT 'normal'",
            },
            "portal_calendar_events": {
                # Phase 4: RBAC attribution columns
                "org_id": "VARCHAR(64)",
                "department_id": "VARCHAR(64)",
                "owner_id": "INTEGER",
                "visibility": "VARCHAR(16) NOT NULL DEFAULT 'private'",
                "sensitivity": "VARCHAR(16) NOT NULL DEFAULT 'normal'",
            },
            "knowledge_dataset_mappings": {
                "is_default_import_target": "BOOLEAN NOT NULL DEFAULT 0",
                "last_synced_at": "VARCHAR(32)",
                "last_imported_at": "VARCHAR(32)",
                "stale": "BOOLEAN NOT NULL DEFAULT 0",
                # Phase 4: RBAC attribution columns
                "org_id": "VARCHAR(64)",
                "department_id": "VARCHAR(64)",
                "owner_id": "INTEGER",
                "visibility": "VARCHAR(16) NOT NULL DEFAULT 'dept'",
                "sensitivity": "VARCHAR(16) NOT NULL DEFAULT 'internal'",
            },
            "chat_sessions": {
                # Phase 4: user-level data isolation
                "user_id": "INTEGER",
            },
        }
        with engine.begin() as conn:
            for table_name, columns in expected.items():
                existing = {
                    row[1]
                    for row in conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
                }
                for column_name, definition in columns.items():
                    if column_name not in existing:
                        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"))

    # ── Row helpers ───────────────────────────────────────────────

    def _asset_table(self, collection: str) -> Table:
        tables = {
            "notices": portal_notices_table,
            "documents": portal_documents_table,
            "resources": portal_resources_table,
            "services": portal_services_table,
            "news": portal_news_table,
        }
        if collection not in tables:
            raise KeyError(collection)
        return tables[collection]

    @property
    def embed_urls(self) -> dict[str, str]:
        with self._session() as db:
            rows = db.execute(select(settings_table)).mappings().all()
            data = deepcopy(DEFAULT_EMBED_URLS)
            for row in rows:
                try:
                    value = json.loads(row["value_json"])
                except json.JSONDecodeError:
                    continue
                if row["key"] in data and isinstance(value, str):
                    data[row["key"]] = value
            return data

    # ═════════════════════════════════════════════════════════════
    # Bootstrap
    # ═════════════════════════════════════════════════════════════

    def portal_dashboard(self, user: dict[str, Any] | None = None) -> dict[str, int]:
        with self._session() as db:
            visible_subsystems = self.list_subsystems(user=user)["items"]
            visits_7d = db.scalar(select(func.count()).select_from(portal_subsystem_visits_table)) or 0
        return {
            "subsystems_total": len(visible_subsystems),
            "subsystems_active": sum(1 for item in visible_subsystems if item["status"] == "active"),
            "subsystems_maintenance": sum(1 for item in visible_subsystems if item["status"] == "maintenance"),
            "notices_total": self.list_portal_assets("notices", user=user)["total"],
            "services_total": self.list_portal_assets("services", user=user)["total"],
            "documents_total": self.list_portal_assets("documents", user=user)["total"],
            "news_total": self.list_portal_assets("news", user=user)["total"],
            "today_tasks": self.list_tasks(user=user)["total"],
            "today_events": self.list_events(user=user)["total"],
            "visits_7d": int(visits_7d),
        }

    def enterprise_workbench(self, code: str, user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        configs = {
            "repair": {
                "title": "报修工单",
                "columns": ["工单", "状态", "处理人", "更新时间"],
                "collection": self.list_repair_tickets,
                "map": lambda item: {
                    "title": item["title"],
                    "status": item["status"],
                    "owner": item.get("assignee") or "待分派",
                    "updated": item["updated_at"][:10],
                    "detail": item["description"],
                },
            },
            "assets": {
                "title": "资产台账",
                "columns": ["资产", "状态", "保管人", "更新时间"],
                "collection": self.list_asset_items,
                "map": lambda item: {
                    "title": item["name"],
                    "status": item["status"],
                    "owner": item.get("custodian") or "未指定",
                    "updated": item["updated_at"][:10],
                    "detail": f"{item['asset_code']} · {item['category']} · {item['location']}",
                },
            },
            "oa": {
                "title": "待办流程",
                "columns": ["流程", "状态", "当前处理人", "更新时间"],
                "collection": self.list_oa_flows,
                "map": lambda item: {
                    "title": item["title"],
                    "status": item["status"],
                    "owner": item.get("current_handler") or "待分派",
                    "updated": item["updated_at"][:10],
                    "detail": f"{item['flow_type']} · 当前节点：{item.get('current_handler') or '待分派'}",
                },
            },
        }
        config = configs.get(code)
        if config is None:
            return None
        items = config["collection"](user=user)["items"]
        records = [config["map"](item) for item in items]
        pending = sum(1 for item in records if item["status"] in {"submitted", "pending", "processing", "borrowed"})
        return {
            "code": code,
            "title": config["title"],
            "columns": config["columns"],
            "records": records,
            "metrics": {
                "total": len(records),
                "pending": pending,
                "ready": len(records) - pending,
            },
        }

    def bootstrap_payload(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "workspace": {
                "tasks": self.list_tasks(user=user),
                "shortcuts": DEFAULT_SHORTCUTS,
                "resources": self.list_portal_assets("resources", user=user),
                "documents": self.list_portal_assets("documents", user=user),
                "notices": self.list_portal_assets("notices", user=user),
                "dashboard": self.portal_dashboard(user=user),
            },
            "portal": {
                "profile": {
                    "name": user.get("display_name") or "郝锐" if user else "郝锐",
                    "department": user.get("default_dept_id") or "" if user else "应用物理与材料学院",
                    "last_login": user.get("last_login_at") or "" if user else "2026-07-16 10:56",
                },
                "systems": self.list_subsystems(user=user),
                "services": self.list_portal_assets("services", user=user),
                "news": self.list_portal_assets("news", user=user),
                "preferences": self.get_portal_preferences(user=user),
                "dashboard": self.portal_dashboard(user=user),
            },
            "calendar": {"events": self.list_events(user=user)},
            "knowledge": {"spaces": self.list_knowledge_spaces(user=user)},
        }

    # ═════════════════════════════════════════════════════════════
    # Tasks
    # ═════════════════════════════════════════════════════════════

    def list_tasks(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            stmt = (
                select(tasks_table)
                .where(self._scope_filter(ctx, tasks_table))
                .order_by(tasks_table.c.id.desc())
            )
            rows = db.execute(stmt).mappings().all()
            items = [self._task_from_row(row) for row in rows]
            return self.list_response(items)

    def create_task(self, payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            with self._session() as db:
                values = {
                    "title": payload["title"],
                    "tag": payload.get("tag") or "今天",
                    "deadline": payload.get("deadline") or None,
                    "done": False,
                    "overdue_notified_at": None,
                }
                # Phase 4: set attribution from user context.
                # NEVER trust client-supplied org_id / department_id / owner_id /
                # visibility / sensitivity — always derive from the server-side
                # AccessContext so a user cannot inject attribution columns via
                # extra JSON fields (defence-in-depth; the Pydantic schema already
                # strips unknown fields, but the store layer must not rely on that).
                if user is not None:
                    ctx = self._build_scope_context(user, db)
                    values["org_id"] = ctx.default_org_id if ctx else "default"
                    values["department_id"] = ctx.default_dept_id if ctx else "HQ"
                    values["owner_id"] = ctx.user_id if ctx else None
                    values["visibility"] = "private"
                    values["sensitivity"] = "normal"
                else:
                    values.setdefault("org_id", "default")
                    values.setdefault("department_id", "HQ")
                    values.setdefault("visibility", "private")
                    values.setdefault("sensitivity", "normal")

                result = db.execute(insert(tasks_table).values(**values))
                db.commit()
                task_id = int(result.inserted_primary_key[0])

                # Re-read through scope filter so the response is consistent
                scope_clause = self._scope_single(ctx, tasks_table, task_id) if user is not None else (tasks_table.c.id == task_id)
                row = db.execute(select(tasks_table).where(scope_clause)).mappings().first()
                if row is None:
                    # Shouldn't happen (just created by this user), but be defensive
                    row = db.execute(select(tasks_table).where(tasks_table.c.id == task_id)).mappings().one()
                return self._task_from_row(row)

    def update_task(self, task_id: int, payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                scope_clause = self._scope_single(ctx, tasks_table, task_id)

                # Verify access before mutating
                existing = db.execute(
                    select(tasks_table).where(scope_clause)
                ).mappings().first()
                if existing is None:
                    return None  # Not found or not authorized (uniform response)

                updates = {key: value for key, value in payload.items() if key in {"title", "tag", "deadline", "done"}}
                # When deadline changes, reset overdue tracking so the task can be re-notified
                if "deadline" in updates and updates["deadline"] != (existing.get("deadline") or None):
                    updates["overdue_notified_at"] = None
                    # Re-evaluate status: clear "overdue" if deadline moved to the future
                    if existing.get("status") == "overdue":
                        updates["status"] = None
                # When done toggled, reflect in status
                if "done" in updates:
                    if updates["done"]:
                        updates["status"] = "completed"
                    else:
                        # Re-evaluate: if deadline still past, stay overdue
                        dl = updates.get("deadline") or existing.get("deadline")
                        if dl and dl < self._now_iso():
                            updates["status"] = "overdue"
                        else:
                            updates["status"] = None
                if updates:
                    db.execute(
                        update(tasks_table)
                        .where(scope_clause)
                        .values(**updates),
                    )
                    db.commit()

                row = db.execute(select(tasks_table).where(scope_clause)).mappings().first()
                return self._task_from_row(row) if row else None

    def delete_task(self, task_id: int, user: dict[str, Any] | None = None) -> bool:
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                scope_clause = self._scope_single(ctx, tasks_table, task_id)

                result = db.execute(delete(tasks_table).where(scope_clause))
                db.commit()
                return result.rowcount > 0

    def clear_done_tasks(self, user: dict[str, Any] | None = None) -> int:
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                # Scope the mass-delete to user-visible tasks that are done.
                result = db.execute(
                    delete(tasks_table)
                    .where(tasks_table.c.done.is_(True))
                    .where(self._scope_filter(ctx, tasks_table)),
                )
                db.commit()
                return int(result.rowcount or 0)

    def find_overdue_tasks(self) -> list[dict[str, Any]]:
        """Return undone tasks whose deadline has passed but not yet notified.

        Used by the APScheduler overdue scanner. Returns the raw row dict
        so the scanner can create notifications and update statuses.
        """
        now = self._now_iso()
        with self._session() as db:
            rows = db.execute(
                select(tasks_table).where(
                    and_(
                        tasks_table.c.done.is_(False),
                        tasks_table.c.deadline.isnot(None),
                        tasks_table.c.deadline < now,
                        tasks_table.c.overdue_notified_at.is_(None),
                    )
                )
            ).mappings().all()
            return [self._task_from_row(row) for row in rows]

    def mark_task_overdue_notified(self, task_id: int) -> None:
        """Set overdue_notified_at and status='overdue' for a task."""
        now = self._now_iso()
        with self._session() as db:
            db.execute(
                update(tasks_table)
                .where(tasks_table.c.id == task_id)
                .values(overdue_notified_at=now, status="overdue")
            )
            db.commit()

    # ═════════════════════════════════════════════════════════════
    # Calendar Events
    # ═════════════════════════════════════════════════════════════

    def list_events(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            stmt = (
                select(events_table)
                .where(self._scope_filter(ctx, events_table))
                .order_by(events_table.c.date, events_table.c.id)
            )
            rows = db.execute(stmt).mappings().all()
            items = [self._event_from_row(row) for row in rows]
            return self.list_response(items)

    def create_event(self, payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            with self._session() as db:
                # Extract only known-safe fields — never copy the full payload
                # into values because that would allow client-supplied attribution
                # columns (org_id, owner_id, etc.) to leak through if the Pydantic
                # schema ever adds them.
                values = {
                    "title": payload["title"],
                    "date": payload["date"],
                    "tone": payload.get("tone", "blue"),
                }
                # Phase 4: set attribution from user context.
                # Same defence-in-depth rationale as create_task above.
                if user is not None:
                    ctx = self._build_scope_context(user, db)
                    values["org_id"] = ctx.default_org_id if ctx else "default"
                    values["department_id"] = ctx.default_dept_id if ctx else "HQ"
                    values["owner_id"] = ctx.user_id if ctx else None
                    values["visibility"] = "private"
                    values["sensitivity"] = "normal"
                else:
                    values.setdefault("org_id", "default")
                    values.setdefault("department_id", "HQ")
                    values.setdefault("visibility", "private")
                    values.setdefault("sensitivity", "normal")

                result = db.execute(insert(events_table).values(**values))
                db.commit()
                event_id = int(result.inserted_primary_key[0])

                scope_clause = self._scope_single(ctx, events_table, event_id) if user is not None else (events_table.c.id == event_id)
                row = db.execute(select(events_table).where(scope_clause)).mappings().first()
                if row is None:
                    row = db.execute(select(events_table).where(events_table.c.id == event_id)).mappings().one()
                return self._event_from_row(row)

    def update_event(self, event_id: int, payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                scope_clause = self._scope_single(ctx, events_table, event_id)

                existing = db.execute(
                    select(events_table).where(scope_clause)
                ).mappings().first()
                if existing is None:
                    return None

                # Phase 4 F4: allowlist mutable fields to prevent injection of
                # attribution columns (org_id, owner_id, etc.) via the payload.
                updates = {
                    key: value for key, value in payload.items()
                    if key in {"title", "date", "tone"}
                }
                if updates:
                    db.execute(
                        update(events_table)
                        .where(scope_clause)
                        .values(**updates),
                    )
                    db.commit()

                row = db.execute(select(events_table).where(scope_clause)).mappings().first()
                return self._event_from_row(row) if row else None

    def delete_event(self, event_id: int, user: dict[str, Any] | None = None) -> bool:
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                scope_clause = self._scope_single(ctx, events_table, event_id)

                result = db.execute(delete(events_table).where(scope_clause))
                db.commit()
                return result.rowcount > 0

    # ═════════════════════════════════════════════════════════════
    # Embed URLs
    # ═════════════════════════════════════════════════════════════

    def update_embed_urls(self, payload: dict[str, Any]) -> dict[str, str]:
        with self._lock:
            with self._session() as db:
                for key in ["feishu", "dingtalk"]:
                    value = payload.get(key)
                    if isinstance(value, str) and value.strip():
                        value_json = json.dumps(value.strip(), ensure_ascii=False)
                        existing = db.scalar(select(settings_table.c.key).where(settings_table.c.key == key))
                        if existing is None:
                            db.execute(insert(settings_table).values(key=key, value_json=value_json))
                        else:
                            db.execute(
                                update(settings_table)
                                .where(settings_table.c.key == key)
                                .values(value_json=value_json),
                            )
                db.commit()
            return self.embed_urls

    # ═════════════════════════════════════════════════════════════
    # Knowledge spaces & mappings
    # ═════════════════════════════════════════════════════════════

    def list_knowledge_spaces(
        self,
        search: str = "",
        filter_: str = "all",
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        query = search.strip().lower()
        settings = get_settings()
        items = self._list_synced_knowledge_spaces(user=user)
        if not items:
            items = configured_knowledge_spaces(
                dataset_id=settings.FASTGPT_DEFAULT_DATASET_ID,
                app_id=settings.FASTGPT_DEFAULT_APP_ID or settings.FASTGPT_CHAT_APP_ID,
                display_name=settings.FASTGPT_DEFAULT_DISPLAY_NAME,
                mode=settings.FASTGPT_MODE,
            )
        # filter_: "all" → no filter; "dataset"/"app" → filter by resource_type;
        # "team"/"org"/"private"/"public" → pass-through for permission_scope values
        _resource_types = {"dataset", "app"}
        items = [
            item for item in items
            if (filter_ == "all" or filter_ in _resource_types and item["type"] == filter_
                or filter_ not in _resource_types)  # pass-through for permission_scope values
            and (not query or query in f"{item['title']}{item['owner']}{item['desc']}{item.get('fastgpt_dataset_id') or ''}{item.get('fastgpt_app_id') or ''}".lower())
        ]
        return self.list_response(items)

    def _list_synced_knowledge_spaces(
        self,
        user: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            stmt = (
                select(knowledge_mappings_table)
                .where(knowledge_mappings_table.c.enabled.is_(True))
                .where(self._scope_filter(ctx, knowledge_mappings_table))
                .order_by(knowledge_mappings_table.c.display_name)
            )
            rows = db.execute(stmt).mappings().all()
            return [knowledge_space_from_mapping(row) for row in rows]

    def list_knowledge_mappings(
        self,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._session() as db:
            ctx = self._build_scope_context(user, db)
            stmt = (
                select(knowledge_mappings_table)
                .where(self._scope_filter(ctx, knowledge_mappings_table))
                .order_by(knowledge_mappings_table.c.resource_type.desc(), knowledge_mappings_table.c.display_name)
            )
            rows = db.execute(stmt).mappings().all()
            return self.list_response([knowledge_mapping_from_row(row) for row in rows])

    def update_knowledge_mapping(
        self,
        mapping_id: str,
        payload: dict[str, Any],
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                scope_clause = self._scope_single(ctx, knowledge_mappings_table, mapping_id)

                row = db.execute(
                    select(knowledge_mappings_table).where(scope_clause)
                ).mappings().first()
                if row is None:
                    return None

                updates: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
                for key in ["display_name", "enabled", "permission_scope"]:
                    if key in payload and payload[key] is not None:
                        updates[key] = payload[key]
                if payload.get("is_default_import_target") is True:
                    if row["resource_type"] != "dataset":
                        return None
                    # Phase 4 F2: scope the clear to the user's visible datasets
                    # so an org_admin in one org cannot affect another org's mappings.
                    db.execute(
                        update(knowledge_mappings_table)
                        .where(knowledge_mappings_table.c.resource_type == "dataset")
                        .where(self._scope_filter(ctx, knowledge_mappings_table))
                        .values(is_default_import_target=False),
                    )
                    updates["is_default_import_target"] = True
                elif payload.get("is_default_import_target") is False:
                    updates["is_default_import_target"] = False

                db.execute(
                    update(knowledge_mappings_table)
                    .where(scope_clause)
                    .values(**updates),
                )
                db.commit()

                next_row = db.execute(
                    select(knowledge_mappings_table).where(scope_clause)
                ).mappings().first()
                return knowledge_mapping_from_row(next_row) if next_row else None

    def delete_knowledge_mapping(
        self,
        mapping_id: str,
        user: dict[str, Any] | None = None,
    ) -> bool:
        with self._lock:
            with self._session() as db:
                ctx = self._build_scope_context(user, db)
                scope_clause = self._scope_single(ctx, knowledge_mappings_table, mapping_id)

                result = db.execute(
                    delete(knowledge_mappings_table).where(scope_clause),
                )
                db.commit()
                return bool(result.rowcount)

    # ═════════════════════════════════════════════════════════════
    # Knowledge sync & import records
    # ═════════════════════════════════════════════════════════════

    def sync_knowledge_mappings(self, resources: list[dict[str, Any]]) -> dict[str, Any]:
        created = 0
        updated = 0
        mapping_ids: list[str] = []
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._session() as db:
                db.execute(update(knowledge_mappings_table).values(stale=True, updated_at=now))
                for resource in resources:
                    resource_id = resource["id"]
                    resource_type = resource["resource_type"]
                    mapping_id = f"{resource_type}:{resource_id}"
                    values = {
                        "id": mapping_id,
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "display_name": resource.get("display_name") or resource.get("name") or resource_id,
                        "fastgpt_app_id": resource_id if resource_type == "app" else None,
                        "fastgpt_dataset_id": resource_id if resource_type == "dataset" else None,
                        "permission_scope": "team",
                        "enabled": True,
                        "is_default_import_target": False,
                        "last_synced_at": now,
                        "stale": False,
                        "updated_at": now,
                        # Phase 4: default attribution for synced resources
                        "org_id": "default",
                        "department_id": "HQ",
                        "owner_id": 1,
                        "visibility": "dept",
                        "sensitivity": "internal",
                    }
                    existing = db.scalar(
                        select(knowledge_mappings_table.c.id)
                        .where(knowledge_mappings_table.c.id == mapping_id),
                    )
                    if existing is None:
                        db.execute(insert(knowledge_mappings_table).values(**values))
                        created += 1
                    else:
                        db.execute(
                            update(knowledge_mappings_table)
                            .where(knowledge_mappings_table.c.id == mapping_id)
                            .values(
                                resource_type=values["resource_type"],
                                resource_id=values["resource_id"],
                                display_name=values["display_name"],
                                fastgpt_app_id=values["fastgpt_app_id"],
                                fastgpt_dataset_id=values["fastgpt_dataset_id"],
                                last_synced_at=now,
                                stale=False,
                                updated_at=now,
                            ),
                        )
                        updated += 1
                    mapping_ids.append(mapping_id)
                db.commit()
        return {
            "created": created,
            "updated": updated,
            "total": len(mapping_ids),
            "mapping_ids": mapping_ids,
        }

    def record_knowledge_import(
        self,
        *,
        dataset_id: str,
        file_name: str,
        status: str,
        collection_id: str | None,
        error_message: str | None = None,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._session() as db:
                # Phase 4 P2-1: scope the mapping lookup to datasets the user
                # can access.  Without this a user with kb:import could create
                # import records for datasets outside their data scope.
                if user is not None:
                    ctx = self._build_scope_context(user, db)
                    mapping = db.execute(
                        select(knowledge_mappings_table)
                        .where(knowledge_mappings_table.c.fastgpt_dataset_id == dataset_id)
                        .where(self._scope_filter(ctx, knowledge_mappings_table))
                    ).mappings().first()
                else:
                    mapping = db.execute(
                        select(knowledge_mappings_table)
                        .where(knowledge_mappings_table.c.fastgpt_dataset_id == dataset_id),
                    ).mappings().first()
                mapping_id = mapping["id"] if mapping else None
                result = db.execute(
                    insert(knowledge_import_records_table).values(
                        mapping_id=mapping_id,
                        dataset_id=dataset_id,
                        file_name=file_name,
                        status=status,
                        collection_id=collection_id,
                        error_message=error_message,
                        created_at=now,
                    ),
                )
                if mapping_id:
                    db.execute(
                        update(knowledge_mappings_table)
                        .where(knowledge_mappings_table.c.id == mapping_id)
                        .values(last_imported_at=now, updated_at=now),
                    )
                db.commit()
                record_id = int(result.inserted_primary_key[0])
                row = db.execute(
                    select(knowledge_import_records_table)
                    .where(knowledge_import_records_table.c.id == record_id),
                ).mappings().one()
                return dict(row)

    def list_knowledge_imports(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        """List knowledge import records scoped to the user's visible mappings.

        Joins against knowledge_dataset_mappings so a user can only see import
        records that belong to datasets within their data scope (Phase 4 F3).
        When *user* is None the old full-list behaviour is preserved for
        internal / seed paths.
        """
        with self._session() as db:
            if user is not None:
                ctx = self._build_scope_context(user, db)
                # Join import records ↔ mappings and apply the visibility filter
                # on the mappings side so we only return imports for datasets the
                # user is authorised to see.
                stmt = (
                    select(knowledge_import_records_table)
                    .select_from(
                        knowledge_import_records_table.join(
                            knowledge_mappings_table,
                            knowledge_import_records_table.c.mapping_id == knowledge_mappings_table.c.id,
                            isouter=True,
                        )
                    )
                    .where(
                        or_(
                            # Import records linked to a visible mapping
                            self._scope_filter(ctx, knowledge_mappings_table),
                            # Import records with no mapping (mapping_id IS NULL)
                            # still need to be visible — only super_admin / internal
                            # users see unlinked records.
                            and_(
                                knowledge_import_records_table.c.mapping_id.is_(None),
                                ctx.is_super_admin,
                            ),
                        )
                    )
                    .order_by(knowledge_import_records_table.c.id.desc())
                )
            else:
                stmt = (
                    select(knowledge_import_records_table)
                    .order_by(knowledge_import_records_table.c.id.desc())
                )
            rows = db.execute(stmt).mappings().all()
            return self.list_response([self._stringify_dt(dict(row)) for row in rows])

    def delete_knowledge_import_by_collection(
        self, collection_id: str,
        user: dict[str, Any] | None = None,
    ) -> None:
        """删除指定 collection_id 的导入记录。

        Phase 4 P2-2: when *user* is provided only delete import records
        linked to mappings the user can see.
        """
        with self._lock:
            with self._session() as db:
                if user is not None:
                    ctx = self._build_scope_context(user, db)
                    # Only delete records whose mapping is in the user's scope
                    visible_mapping_ids = {
                        r[0] for r in db.execute(
                            select(knowledge_mappings_table.c.id)
                            .where(self._scope_filter(ctx, knowledge_mappings_table))
                        ).fetchall()
                    }
                    db.execute(
                        knowledge_import_records_table.delete()
                        .where(knowledge_import_records_table.c.collection_id == collection_id)
                        .where(
                            or_(
                                knowledge_import_records_table.c.mapping_id.in_(visible_mapping_ids),
                                knowledge_import_records_table.c.mapping_id.is_(None),
                            )
                        ),
                    )
                else:
                    db.execute(
                        knowledge_import_records_table.delete()
                        .where(knowledge_import_records_table.c.collection_id == collection_id),
                    )
                db.commit()

    # ═════════════════════════════════════════════════════════════
    # Chat persistence  (Phase 4: user-level scoping)
    # ═════════════════════════════════════════════════════════════

    def save_chat_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        action: str | None = None,
        title: str | None = None,
        created_at: str | None = None,
        user_id: int | None = None,
    ) -> None:
        """保存一条聊天消息，同时 upsert 会话。

        When *user_id* is provided the session is scoped to that user:
        new sessions record the owner; existing sessions are validated
        for ownership before accepting messages.
        """
        now = created_at or datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._session() as db:
                # Upsert session
                existing_row = db.execute(
                    select(chat_sessions_table.c.id, chat_sessions_table.c.user_id)
                    .where(chat_sessions_table.c.id == session_id)
                ).mappings().first()

                if existing_row is None:
                    db.execute(
                        insert(chat_sessions_table).values(
                            id=session_id,
                            title=title or "",
                            user_id=user_id,
                            created_at=now,
                            updated_at=now,
                        )
                    )
                else:
                    # Ownership check: if the session belongs to a different
                    # user, reject (silently — don't leak session existence).
                    if user_id is not None and existing_row["user_id"] is not None:
                        if existing_row["user_id"] != user_id:
                            return  # silently drop — don't write to foreign session
                    values: dict[str, Any] = {"updated_at": now}
                    if title:
                        values["title"] = title
                    # If the session has no owner yet (backfilled to NULL),
                    # claim it for this user.
                    if existing_row["user_id"] is None and user_id is not None:
                        values["user_id"] = user_id
                    db.execute(
                        update(chat_sessions_table)
                        .where(chat_sessions_table.c.id == session_id)
                        .values(**values),
                    )
                # Insert message
                db.execute(
                    insert(chat_messages_table).values(
                        session_id=session_id,
                        role=role,
                        content=content,
                        action=action,
                        created_at=now,
                    )
                )
                db.commit()

    def list_chat_sessions(self, user: dict[str, Any] | None = None) -> dict[str, Any]:
        """列出当前用户的聊天会话，按更新时间倒序。

        When *user* is None the full list is returned (internal / seed path).
        """
        with self._session() as db:
            stmt = select(chat_sessions_table).order_by(chat_sessions_table.c.updated_at.desc())
            if user is not None:
                stmt = stmt.where(chat_sessions_table.c.user_id == user["id"])
            rows = db.execute(stmt).mappings().all()
            return self.list_response([self._stringify_dt(dict(row)) for row in rows])

    def get_chat_messages(
        self, session_id: str, limit: int = 0,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """获取指定会话的消息。

        When *user* is provided the session must belong to that user or
        the response is empty (uniform with nonexistent sessions to
        prevent ID enumeration).
        """
        with self._session() as db:
            # Verify ownership first
            if user is not None:
                session = db.execute(
                    select(chat_sessions_table.c.user_id)
                    .where(chat_sessions_table.c.id == session_id)
                ).mappings().first()
                if session is None:
                    return self.list_response([])
                if session["user_id"] is not None and session["user_id"] != user["id"]:
                    return self.list_response([])  # uniform empty — don't leak existence

            stmt = (
                select(chat_messages_table)
                .where(chat_messages_table.c.session_id == session_id)
                .order_by(chat_messages_table.c.id.desc())
            )
            if limit > 0:
                stmt = stmt.limit(limit)
            rows = db.execute(stmt).mappings().all()
            # 按 id 升序返回（时间顺序），因为我们用 desc 查询
            result = [dict(row) for row in rows]
            result.reverse()
            return self.list_response(result)

    def delete_chat_session(
        self, session_id: str,
        user: dict[str, Any] | None = None,
    ) -> bool:
        """删除会话及其所有消息。

        When *user* is provided the session must belong to that user.
        Returns False when the session doesn't exist or isn't owned by
        *user* (uniform response).
        """
        with self._lock:
            with self._session() as db:
                if user is not None:
                    session = db.execute(
                        select(chat_sessions_table.c.user_id)
                        .where(chat_sessions_table.c.id == session_id)
                    ).mappings().first()
                    if session is None:
                        return False
                    if session["user_id"] is not None and session["user_id"] != user["id"]:
                        return False  # uniform — don't leak existence

                db.execute(
                    delete(chat_messages_table).where(chat_messages_table.c.session_id == session_id)
                )
                result = db.execute(
                    delete(chat_sessions_table).where(chat_sessions_table.c.id == session_id)
                )
                db.commit()
                return result.rowcount > 0


# ═════════════════════════════════════════════════════════════════════
# Module-level helpers (unchanged signatures)
# ═════════════════════════════════════════════════════════════════════


def configured_knowledge_spaces(
    *,
    dataset_id: str | None,
    app_id: str | None,
    display_name: str,
    mode: str,
) -> list[dict[str, Any]]:
    if not dataset_id:
        return []
    return [
        {
            "id": dataset_id,
            "title": display_name or dataset_id,
            "owner": "FastGPT",
            "desc": "来自 FastGPT 配置的真实知识库，可用于文件导入、嵌入和向量检索。",
            "type": "public",
            "meta": f"{dataset_id} · {mode}",
            "tone": "app-purple",
            "fastgpt_dataset_id": dataset_id,
            "fastgpt_app_id": app_id,
        },
    ]


def knowledge_space_from_mapping(row: Any) -> dict[str, Any]:
    resource_type = row["resource_type"]
    resource_id = row["resource_id"]
    is_dataset = resource_type == "dataset"
    return {
        "id": row["id"],
        "title": row["display_name"],
        "owner": "FastGPT 数据集" if is_dataset else "FastGPT 应用",
        "desc": "可导入文件并由 FastGPT 完成嵌入和向量检索。" if is_dataset else "可用于 FastGPT 问答或检索应用。",
        "type": "public",
        "meta": f"{resource_id} · synced",
        "tone": "app-purple" if is_dataset else "app-blue",
        "fastgpt_dataset_id": row["fastgpt_dataset_id"],
        "fastgpt_app_id": row["fastgpt_app_id"],
        "resource_type": row["resource_type"],
        "enabled": bool(row["enabled"]),
        "is_default_import_target": bool(row["is_default_import_target"]),
        "last_synced_at": row["last_synced_at"],
        "last_imported_at": row["last_imported_at"],
        "stale": bool(row["stale"]),
        # ── Phase 5: attribution fields for retrieval_policy ─────
        "org_id": row.get("org_id"),
        "department_id": row.get("department_id"),
        "owner_id": row.get("owner_id"),
        "visibility": row.get("visibility", "dept"),
        "sensitivity": row.get("sensitivity", "internal"),
    }


def knowledge_mapping_from_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "resource_type": row["resource_type"],
        "resource_id": row["resource_id"],
        "display_name": row["display_name"],
        "fastgpt_app_id": row["fastgpt_app_id"],
        "fastgpt_dataset_id": row["fastgpt_dataset_id"],
        "permission_scope": row["permission_scope"],
        "enabled": bool(row["enabled"]),
        "is_default_import_target": bool(row["is_default_import_target"]),
        "last_synced_at": row["last_synced_at"],
        "last_imported_at": row["last_imported_at"],
        "stale": bool(row["stale"]),
        "updated_at": row["updated_at"],
    }


store = PortalStore()
