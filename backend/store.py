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
    # 閳光偓閳光偓 RBAC data-attribution columns 閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓
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
    # 閳光偓閳光偓 RBAC data-attribution columns 閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓
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
    # 閳光偓閳光偓 Phase 4: RBAC data-attribution columns 閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓
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
    # 閳光偓閳光偓 Phase 4: user-level data isolation 閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓
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

# 閳光偓閳光偓 Phase 3: HR & Finance 閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓

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

# 閳光偓閳光偓 Phase 4 T17: Website, Estate, Employment 閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓

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
    ["閸忣剙鎲?, "闁氨鐓℃稉顓炵妇", "app-orange"],
    ["閺呴缚鍏橀梻顔剧摕", "AI 閸斺晜澧?, "app-purple"],
    ["娴兼俺顔?, "娴兼俺顔呯粻锛勬倞", "app-blue"],
    ["鐞涖劌宕?, "濞翠胶鈻奸悽瀹狀嚞", "app-cyan"],
    ["鏉炶顓搁幍?, "鐎光剝澹掓稉顓炵妇", "app-red"],
    ["缁楁棁顔?, "閹存垹娈戠粭鏃囶唶", "app-orange"],
    ["濮瑰洦濮?, "瀹搞儰缍斿Ч鍥ㄥГ", "app-blue"],
    ["閺冦儱宸?, "閺冦儳鈻肩粻锛勬倞", "app-blue"],
    ["瀵板懎濮欐稉顓炵妇", "娴犺濮熺粻锛勬倞", "app-green"],
    ["閾诲秴鎮庨梻銊﹀煕", "闂傘劍鍩涙＃鏍€?, "app-red"],
]

DEFAULT_SYSTEMS = [
    # 閸旂偛鍙曠悰灞炬杺缁?
    "OA 缁崵绮?,
    "閻絽濮欑化鑽ょ埠",
    # 娴滃搫濮忕紒鍕矏缁?
    "HR 娴滆桨绨?,
    "閹锋稖浠?,
    "閸╃顔?,
    "閸涙ê浼愰崗铏偓鈧?,
    # 缂佸繗鎯€娑撴艾濮熺猾?
    "CRM",
    "ERP",
    "閸烆喖鎮楀銉ュ礋",
    "娓氭稑绨查柧鍓ф晸娴?,
    # 鐠愩垼绁崥搴″珶 & 閺€顖涙嫼缁?
    "鐠愩垹濮?,
    "閸ュ搫鐣剧挧鍕獓",
    "閸樺倸灏悧鈺€绗?,
    "閹躲儰鎱?,
    "閺佺増宓佹稉顓炲酱",
    "閸忔艾缂撴搴㈠付",
]

DEFAULT_NEWS: list[dict[str, Any]] = []  # No hardcoded seed news

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
    # 閸旂偛鍙曠悰灞炬杺缁?
    ("oa", "OA", "閸旂偛鍙曠悰灞炬杺缁?, "閸忣剚鏋冨ù浣芥祮閵嗕焦绁︾粙瀣吀閹靛箍鈧線鈧氨鐓￠崗顒€鎲＄粵澶婂礂閸氬苯濮欓崗顑跨娴ｆ挸瀵查獮鍐插酱", "鐞涘本鏂傜粻锛勬倞闁?, "OA 閺€顖涘瘮", "app-blue"),
    ("supervision", "閻絽濮?, "閸旂偛鍙曠悰灞炬杺缁?, "闁插秶鍋ｅ銉ょ稊娴犺濮熼崚鍡毿掗妴浣界箻鎼达箒鎷烽煪顏傗偓浣界煑娴犳槒鎯ょ€圭偟娈戦梻顓犲箚缁狅紕鎮婄化鑽ょ埠", "鐞涘本鏂傜粻锛勬倞闁?, "缂佺厧鎮庨張宥呭閸?, "app-blue"),
    # 娴滃搫濮忕紒鍕矏缁?
    ("hr", "HR 娴滆桨绨?, "娴滃搫濮忕紒鍕矏缁?, "缂佸嫮绮愰弸鑸电€妴浣稿弳鏉烆剝鐨熺粋姹団偓浣告値閸氬本銆傚鍫涒偓浣锋眽娴滃鐔€绾偓閺佺増宓佹稉顓炵妇", "娴滃搫濮忕挧鍕爱闁?, "娴滆桨绨ㄩ張宥呭閸?, "app-green"),
    ("recruitment", "閹锋稖浠?, "娴滃搫濮忕紒鍕矏缁?, "闂団偓濮瑰倸褰傜敮鍐︹偓浣虹暆閸樺棛鐡柅澶堚偓渚€娼扮拠鏇炵暔閹烘帇鈧礁缍嶉悽銊ヮ吀閹电懓鍙忓ù浣衡柤缁狅紕鎮?, "娴滃搫濮忕挧鍕爱闁?, "閹锋稖浠掗張宥呭閸?, "app-green"),
    ("training", "閸╃顔?, "娴滃搫濮忕紒鍕矏缁?, "鐠囧墽鈻肩粻锛勬倞閵嗕礁鐓跨拋顓☆吀閸掓帇鈧礁顒熼崚鍡欑埠鐠伮扳偓浣告躬缁惧灝顒熸稊鐘辩瑢閼板啳鐦?, "娴滃搫濮忕挧鍕爱闁?, "閸╃顔勯張宥呭閸?, "app-green"),
    ("wellness", "閸涙ê浼愰崗铏偓鈧?, "娴滃搫濮忕紒鍕矏缁?, "閻㈢喐妫╃粊婵堫洿閵嗕浇濡弮銉ь洿閸掆斂鈧礁浠存惔宄板彠閹偓閵嗕礁鎲冲銉ュ簻閸斺晙绗岄幇蹇氼潌閸欏秹顩?, "娴滃搫濮忕挧鍕爱闁?, "閸忚櫕鈧偓閺堝秴濮熼崣?, "app-green"),
    # 缂佸繗鎯€娑撴艾濮熺猾?
    ("crm", "CRM", "缂佸繗鎯€娑撴艾濮熺猾?, "鐎广垺鍩涙穱鈩冧紖缁狅紕鎮婇妴浣告櫌閺堥缚鎷烽煪顏傗偓浣告値閸氬瞼顓搁悶鍡愨偓渚€鏀㈤崬顔界础閺傛鍨庨弸?, "鏉╂劘鎯€缁狅紕鎮婇柈?, "CRM 閺€顖涘瘮", "app-orange"),
    ("erp", "ERP", "缂佸繗鎯€娑撴艾濮熺猾?, "闁插洩鍠橀妴浣哥氨鐎涙ǜ鈧胶鏁撴禍褑顓搁崚鎺嬧偓浣藉窛濡偓缁涘绱掓稉姘崇カ濠ф劒绔存担鎾冲缁狅紕鎮?, "鏉╂劘鎯€缁狅紕鎮婇柈?, "ERP 閺€顖涘瘮", "app-orange"),
    ("service-desk", "閸烆喖鎮楀銉ュ礋", "缂佸繗鎯€娑撴艾濮熺猾?, "鐎广垺鍩涢幎銉ゆ叏閵嗕礁浼愰崡鏇炲瀻闁板秲鈧焦婀囬崝陇绐￠煪顏傗偓浣瑰姬閹板繐瀹抽崶鐐额問闂傤厾骞?, "鏉╂劘鎯€缁狅紕鎮婇柈?, "閸烆喖鎮楅弨顖涘瘮", "app-orange"),
    ("supply-chain", "娓氭稑绨查柧鍓ф晸娴?, "缂佸繗鎯€娑撴艾濮熺猾?, "娓氭稑绨查崯鍡楀礂閸氬被鈧胶澧块弬娆撴付濮瑰倶鈧焦甯撴禍褑鐨熸惔锔衡偓浣哄⒖濞翠浇绐￠煪顏嗩吀閻?, "鏉╂劘鎯€缁狅紕鎮婇柈?, "娓氭稑绨查柧鐐暜閹?, "app-orange"),
    # 鐠愩垼绁崥搴″珶 & 閺€顖涙嫼缁?
    ("finance", "鐠愩垹濮?, "鐠愩垼绁崥搴″珶 & 閺€顖涙嫼缁?, "閹槒澶勯妴浣哥安閺€璺虹安娴犳ǜ鈧線顣╃粻妤冾吀閹貉佲偓浣藉偍閸斺剝濮ょ悰銊ょ瑢閸掑棙鐎?, "閸氬骸瀚熸穱婵嬫闁?, "鐠愩垹濮熼張宥呭閸?, "app-purple"),
    ("fixed-assets", "閸ュ搫鐣剧挧鍕獓", "鐠愩垼绁崥搴″珶 & 閺€顖涙嫼缁?, "鐠у嫪楠囬崗銉ョ氨閵嗕線顣悽銊ｂ偓浣界殶閹枫劊鈧胶娲忛悙骞库偓浣瑰Г鎼寸喎鍙忛悽鐔锋嚒閸涖劍婀＄粻锛勬倞", "閸氬骸瀚熸穱婵嬫闁?, "鐠у嫪楠囬張宥呭閸?, "app-purple"),
    ("facility", "閸樺倸灏悧鈺€绗?, "鐠愩垼绁崥搴″珶 & 閺€顖涙嫼缁?, "閸樺倸灏粚娲？閵嗕浇顔曟径鍥啎閺傚鈧礁鐣ㄦ穱婵嗚窗閺屻儯鈧胶璞㈤崠鏍︾箽濞蹭胶顓搁悶?, "閸氬骸瀚熸穱婵嬫闁?, "閻椻晙绗熼張宥呭閸?, "app-purple"),
    ("repair", "閹躲儰鎱?, "鐠愩垼绁崥搴″珶 & 閺€顖涙嫼缁?, "鐠佹儳顦弫鍛存閹躲儰鎱ㄩ妴浣规烦瀹搞儯鈧胶娣穱顔款唶瑜版洏鈧礁顦禒鍓侇吀閻炲棛娈戠紒鐔剁楠炲啿褰?, "閸氬骸瀚熸穱婵嬫闁?, "閹躲儰鎱ㄩ張宥呭閸?, "app-purple"),
    ("data-portal", "閺佺増宓佹稉顓炲酱", "鐠愩垼绁崥搴″珶 & 閺€顖涙嫼缁?, "閺佺増宓佸Ч鍥粵閵嗕焦涓嶉悶鍡愨偓浣哥磻閸欐垯鈧焦婀囬崝锛勬畱缂佺喍绔撮弫鐗堝祦鎼存洖楠?, "閸氬骸瀚熸穱婵嬫闁?, "閺佺増宓侀張宥呭閸?, "app-purple"),
    ("party", "閸忔艾缂撴搴㈠付", "鐠愩垼绁崥搴″珶 & 閺€顖涙嫼缁?, "缂佸嫮绮愰悽鐔告た閵嗕礁鍘风拹鍦吀閻炲棎鈧礁绮旈弨鎸庢殌閼插眰鈧礁鎮庣憴鍕吀鐠佲€茬瑢妞嬪酣娅撴０鍕劅", "鐞涘本鏂傜粻锛勬倞闁?, "閸忔艾缂撻弨顖涘瘮", "app-purple"),
]

DEFAULT_SUBSYSTEM_ACTIONS = {
    "oa": [
        {"label": "瀵板懎濮欏ù浣衡柤", "kind": "records"},
        {"label": "閺傚洣娆㈠ù浣芥祮", "kind": "documents"},
        {"label": "閸旂偛鍙曢柅姘辩叀", "kind": "notices"},
    ],
    "supervision": [
        {"label": "閻絽濮欐禍瀣€?, "kind": "records"},
        {"label": "鐠愶絼鎹㈠〒鍛礋", "kind": "records"},
        {"label": "閸旂偟鎮婃潻娑樺", "kind": "dashboard"},
    ],
    "hr": [
        {"label": "娴滃搫鎲冲锝嗩攳", "kind": "records"},
        {"label": "鐠囧嘲浜ｉ懓鍐ㄥ珶", "kind": "records"},
        {"label": "鐠囦焦妲戦悽瀹狀嚞", "kind": "records"},
    ],
    "recruitment": [
        {"label": "閹锋稖浠掗棁鈧Ч?, "kind": "records"},
        {"label": "缁犫偓閸樺棛鐡柅?, "kind": "records"},
        {"label": "瑜版洜鏁ょ€光剝澹?, "kind": "records"},
    ],
    "training": [
        {"label": "閸╃顔勭拋鈥冲灊", "kind": "records"},
        {"label": "閸︺劎鍤庣€涳缚绡?, "kind": "records"},
        {"label": "鐎涳箑鍨庣紒鐔活吀", "kind": "dashboard"},
    ],
    "wellness": [
        {"label": "濞茶濮╃粻锛勬倞", "kind": "records"},
        {"label": "缁傚繐鍩勯崣鎴炴杹", "kind": "records"},
        {"label": "閹板繗顫嗛崣宥夘洯", "kind": "records"},
    ],
    "crm": [
        {"label": "鐎广垺鍩涚粻锛勬倞", "kind": "records"},
        {"label": "閸熷棙婧€鏉╁€熼嚋", "kind": "records"},
        {"label": "闁库偓閸烆喖鍨庨弸?, "kind": "dashboard"},
    ],
    "erp": [
        {"label": "闁插洩鍠樼粻锛勬倞", "kind": "records"},
        {"label": "鎼存挸鐡ㄧ粻锛勬倞", "kind": "records"},
        {"label": "閻㈢喍楠囩拋鈥冲灊", "kind": "records"},
    ],
    "service-desk": [
        {"label": "瀹搞儱宕熼崚妤勩€?, "kind": "records"},
        {"label": "閺堝秴濮熺捄鐔婚嚋", "kind": "records"},
        {"label": "濠娾剝鍓版惔锕佺槑娴?, "kind": "dashboard"},
    ],
    "supply-chain": [
        {"label": "娓氭稑绨查崯鍡欘吀閻?, "kind": "records"},
        {"label": "閻椻晜鏋￠棁鈧Ч?, "kind": "records"},
        {"label": "閻椻晜绁︾捄鐔婚嚋", "kind": "records"},
    ],
    "finance": [
        {"label": "閹躲儵鏀㈢粻锛勬倞", "kind": "records"},
        {"label": "妫板嫮鐣荤粻鈩冨付", "kind": "records"},
        {"label": "鐠愩垹濮熼幎銉ㄣ€?, "kind": "dashboard"},
    ],
    "fixed-assets": [
        {"label": "鐠у嫪楠囬崣鎷屽", "kind": "records"},
        {"label": "妫板棛鏁ょ拫鍐╁", "kind": "records"},
        {"label": "閻╂鍋ｇ粻锛勬倞", "kind": "records"},
    ],
    "facility": [
        {"label": "缁屾椽妫跨粻锛勬倞", "kind": "records"},
        {"label": "鐠佹儳顦拋鐐煢", "kind": "records"},
        {"label": "瀹糕剝鐓＄拋鏉跨秿", "kind": "records"},
    ],
    "repair": [
        {"label": "閺傛澘缂撻幎銉ゆ叏", "kind": "records"},
        {"label": "瀹搞儱宕熼崚妤勩€?, "kind": "records"},
        {"label": "閺堝秴濮熺拠鍕幆", "kind": "dashboard"},
    ],
    "data-portal": [
        {"label": "閹稿洦鐖ｉ惇瀣緲", "kind": "dashboard"},
        {"label": "娑撴捇顣介弫鐗堝祦", "kind": "records"},
        {"label": "閺佺増宓佺挧鍕爱", "kind": "resources"},
    ],
    "party": [
        {"label": "缂佸嫮绮愰悽鐔告た", "kind": "records"},
        {"label": "閸忔俺鍨傜粻锛勬倞", "kind": "records"},
        {"label": "妞嬪孩甯剁€孤ゎ吀", "kind": "records"},
    ],
}

DEFAULT_MENU_ITEMS: dict[str, list[dict[str, Any]]] = {
    # 閳光偓閳光偓 閸旂偛鍙曠悰灞炬杺缁?閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓
    "oa": [
        {"section": "濞翠胶鈻兼稉顓炵妇", "items": [
            {"code": "todo", "label": "瀵板懎濮欏ù浣衡柤", "icon": "i-clock", "href": "#/subsystem/oa/flows/todo"},
            {"code": "done", "label": "瀹告彃濮欏ù浣衡柤", "icon": "i-check", "href": "#/subsystem/oa/flows/done"},
            {"code": "my-flows", "label": "閹存垵褰傜挧椋庢畱", "icon": "i-user", "href": "#/subsystem/oa/flows/my"},
        ]},
        {"section": "閺傚洣娆㈢粻锛勬倞", "items": [
            {"code": "files", "label": "閺傚洣娆㈠ù浣芥祮", "icon": "i-file", "href": "#/subsystem/oa/files"},
            {"code": "docs", "label": "閸忣剚鏋冪粻锛勬倞", "icon": "i-doc", "href": "#/subsystem/oa/docs"},
        ]},
        {"section": "閸旂偛鍙曟潏鍛И", "items": [
            {"code": "meetings", "label": "娴兼俺顔呯粻锛勬倞", "icon": "i-calendar", "href": "#/subsystem/oa/meetings"},
            {"code": "notices", "label": "闁氨鐓￠崗顒€鎲?, "icon": "i-bell", "href": "#/subsystem/oa/notices"},
        ]},
    ],
    "supervision": [
        {"section": "閻絽濮欐禍瀣€?, "items": [
            {"code": "items", "label": "閸忋劑鍎存禍瀣€?, "icon": "i-list", "href": "#/subsystem/supervision/items"},
            {"code": "new-item", "label": "閺傛澘缂撻惈锝呭", "icon": "i-plus", "href": "#/subsystem/supervision/items/new"},
            {"code": "my-items", "label": "閹存垹娈戦惈锝呭", "icon": "i-user", "href": "#/subsystem/supervision/items/my"},
        ]},
        {"section": "鐠愶絼鎹㈠〒鍛礋", "items": [
            {"code": "units", "label": "鐠愶絼鎹㈤崡鏇氱秴", "icon": "i-grid", "href": "#/subsystem/supervision/units"},
            {"code": "progress", "label": "閸旂偟鎮婃潻娑樺", "icon": "i-chart", "href": "#/subsystem/supervision/progress"},
        ]},
        {"section": "缂佺喕顓搁崚鍡樼€?, "items": [
            {"code": "stats", "label": "閸旂偟绮ㄧ紒鐔活吀", "icon": "i-bar-chart", "href": "#/subsystem/supervision/stats"},
            {"code": "overdue", "label": "闁偓婀￠崚鍡樼€?, "icon": "i-alert", "href": "#/subsystem/supervision/overdue"},
        ]},
    ],
    # 閳光偓閳光偓 娴滃搫濮忕紒鍕矏缁?閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓
    "hr": [
        {"section": "鐠囦焦妲戦悽瀹狀嚞", "items": [
            {"code": "cert-employment", "label": "閸︺劏浜寸拠浣规", "icon": "i-file", "href": "#/subsystem/hr/certificates/employment"},
            {"code": "cert-income", "label": "閺€璺哄弳鐠囦焦妲?, "icon": "i-file", "href": "#/subsystem/hr/certificates/income"},
            {"code": "cert-other", "label": "閸忔湹绮拠浣规", "icon": "i-file", "href": "#/subsystem/hr/certificates/other"},
        ]},
        {"section": "閼板啫瀚熺拠宄颁海", "items": [
            {"code": "leave", "label": "鐠囧嘲浜ｉ悽瀹狀嚞", "icon": "i-edit", "href": "#/subsystem/hr/leave"},
            {"code": "attendance", "label": "閼板啫瀚熺拋鏉跨秿", "icon": "i-list", "href": "#/subsystem/hr/attendance"},
            {"code": "overtime", "label": "閸旂姷褰悽瀹狀嚞", "icon": "i-clock", "href": "#/subsystem/hr/overtime"},
        ]},
        {"section": "娴滃搫鎲虫穱鈩冧紖", "items": [
            {"code": "staff", "label": "娴滃搫鎲冲锝嗩攳", "icon": "i-users", "href": "#/subsystem/hr/staff"},
            {"code": "dept-info", "label": "闁劑妫穱鈩冧紖", "icon": "i-grid", "href": "#/subsystem/hr/departments"},
        ]},
    ],
    # recruitment, training, wellness 閳?menu items deferred
    # 閳光偓閳光偓 鐠愩垼绁崥搴″珶 & 閺€顖涙嫼缁?閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓
    "finance": [
        {"section": "閹躲儵鏀㈢粻锛勬倞", "items": [
            {"code": "claims", "label": "閹躲儵鏀㈤悽瀹狀嚞", "icon": "i-edit", "href": "#/subsystem/finance/claims"},
            {"code": "my-claims", "label": "閹存垹娈戦幎銉╂敘", "icon": "i-user", "href": "#/subsystem/finance/claims/my"},
            {"code": "claim-approve", "label": "閹躲儵鏀㈢€光剝澹?, "icon": "i-check", "href": "#/subsystem/finance/claims/approve"},
        ]},
        {"section": "妫板嫮鐣荤粻锛勬倞", "items": [
            {"code": "budget", "label": "妫板嫮鐣绘い鍦窗", "icon": "i-list", "href": "#/subsystem/finance/budgets"},
            {"code": "budget-exec", "label": "妫板嫮鐣婚幍褑顢?, "icon": "i-chart", "href": "#/subsystem/finance/budgets/exec"},
        ]},
        {"section": "閺夋劖鏋″〒鍛礋", "items": [
            {"code": "materials", "label": "鐠愬湱鏁ら弶鎰灐", "icon": "i-file", "href": "#/subsystem/finance/materials"},
            {"code": "receipts", "label": "缁併劍宓佺粻锛勬倞", "icon": "i-doc", "href": "#/subsystem/finance/receipts"},
        ]},
    ],
    "repair": [
        {"section": "瀹搞儱宕熺粻锛勬倞", "items": [
            {"code": "tickets", "label": "閸忋劑鍎村銉ュ礋", "icon": "i-list", "href": "#/subsystem/repair/tickets"},
            {"code": "new-ticket", "label": "閺傛澘缂撻幎銉ゆ叏", "icon": "i-plus", "href": "#/subsystem/repair/tickets/new"},
            {"code": "my-tickets", "label": "閹存垹娈戦幎銉ゆ叏", "icon": "i-user", "href": "#/subsystem/repair/tickets/my"},
        ]},
        {"section": "濞叉儳宕熸径鍕倞", "items": [
            {"code": "assign", "label": "瀵板懏娣冲銉ュ礋", "icon": "i-send", "href": "#/subsystem/repair/tickets/assign"},
            {"code": "processing", "label": "婢跺嫮鎮婃稉?, "icon": "i-clock", "href": "#/subsystem/repair/tickets/processing"},
        ]},
        {"section": "缂佺喕顓哥拠鍕幆", "items": [
            {"code": "stats", "label": "瀹搞儱宕熺紒鐔活吀", "icon": "i-chart", "href": "#/subsystem/repair/stats"},
            {"code": "feedback", "label": "閺堝秴濮熺拠鍕幆", "icon": "i-star", "href": "#/subsystem/repair/feedback"},
        ]},
    ],
    "data-portal": [
        {"section": "閺佺増宓侀惇瀣緲", "items": [
            {"code": "overview", "label": "閺佺増宓佸鍌濐潔", "icon": "i-chart", "href": "#/subsystem/data-portal/overview"},
            {"code": "metrics", "label": "閹稿洦鐖ｇ拠锔藉剰", "icon": "i-list", "href": "#/subsystem/data-portal/metrics"},
            {"code": "trends", "label": "鐡掑濞嶉崚鍡樼€?, "icon": "i-bar-chart", "href": "#/subsystem/data-portal/trends"},
        ]},
        {"section": "娑撴捇顣介弫鐗堝祦", "items": [
            {"code": "tickets-data", "label": "瀹搞儱宕熼弫鐗堝祦", "icon": "i-file", "href": "#/subsystem/data-portal/tickets"},
            {"code": "assets-data", "label": "鐠у嫪楠囬弫鐗堝祦", "icon": "i-file", "href": "#/subsystem/data-portal/assets"},
            {"code": "flows-data", "label": "濞翠胶鈻奸弫鐗堝祦", "icon": "i-file", "href": "#/subsystem/data-portal/flows"},
        ]},
        {"section": "閺佺増宓佺挧鍕爱", "items": [
            {"code": "exports", "label": "閺佺増宓佺€电厧鍤?, "icon": "i-download", "href": "#/subsystem/data-portal/exports"},
            {"code": "reports", "label": "閹躲儴銆冮柊宥囩枂", "icon": "i-settings", "href": "#/subsystem/data-portal/reports"},
        ]},
    ],
}

DEFAULT_SUBSYSTEM_APPROVAL_CHAINS: dict[str, list[dict[str, Any]]] = {
    "repair":  [{"role": "dept_leader", "level": 1}],
    "oa":      [{"role": "dept_leader", "level": 1}, {"role": "org_admin", "level": 2}],
    "hr":      [{"role": "dept_leader", "level": 1}],
    "finance": [{"role": "dept_leader", "level": 1}, {"role": "org_admin", "level": 2}],
    "supervision": [{"role": "dept_leader", "level": 1}],
    "data-portal": [{"role": "org_admin", "level": 1}],
}

# Shell subsystems 閳?disabled for not-yet-implemented systems.
# Active internal subsystems: oa, supervision, hr, finance, repair, data-portal
SHELL_SUBSYSTEM_ENTRY = {
    "recruitment":      ("disabled", None),
    "training":         ("disabled", None),
    "wellness":         ("disabled", None),
    "crm":              ("disabled", None),
    "erp":              ("disabled", None),
    "service-desk":     ("disabled", None),
    "supply-chain":     ("disabled", None),
    "fixed-assets":     ("disabled", None),
    "facility":         ("disabled", None),
    "party":            ("disabled", None),
}



# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?
# Helpers
# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?


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


# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?
# PortalStore
# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?


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
    """Unified store singleton 閳?Table definitions + metadata live at module level."""

    def __init__(self) -> None:
        super().__init__()  # BaseStore sets self._lock
        # Expose table refs for mixins (they access via self._*_table)
        self._portal_subsystems_table = portal_subsystems_table
        self._portal_subsystem_visits_table = portal_subsystem_visits_table
        self._portal_notices_table = portal_notices_table
        self._portal_documents_table = portal_documents_table
        self._portal_resources_table = portal_resources_table
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
        """Override BaseStore._session 閳?ensure schema before every session."""
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
            # Upsert subsystems: insert new codes, update existing ones in-place
            for index, (code, name, category, description, owner_department, support_contact, tone) in enumerate(DEFAULT_SUBSYSTEMS, start=1):
                existing_code = db.scalar(
                    select(portal_subsystems_table.c.code).where(portal_subsystems_table.c.code == code)
                )
                values = {
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
                        DEFAULT_SUBSYSTEM_ACTIONS.get(code, [{"label": "閺屻儳婀呭鍌濐潔", "kind": "overview"}]),
                        ensure_ascii=False,
                    ),
                    "related_resources_json": json.dumps(["閸掕泛瀹抽幍瀣斀", "閺堝秴濮熼惄顔肩秿"], ensure_ascii=False),
                    "menu_items_json": json.dumps(
                        DEFAULT_MENU_ITEMS.get(code, []), ensure_ascii=False,
                    ),
                    "approval_chain_json": json.dumps(
                        DEFAULT_SUBSYSTEM_APPROVAL_CHAINS.get(code, []), ensure_ascii=False,
                    ),
                    "updated_at": now,
                }
                if existing_code is None:
                    values["created_at"] = now
                    db.execute(insert(portal_subsystems_table).values(values))
                else:
                    db.execute(
                        update(portal_subsystems_table)
                        .where(portal_subsystems_table.c.code == code)
                        .values(**values)
                    )
            generic_action_labels = {"閺屻儳婀呭鍌濐潔", "閺屻儳婀呴崗瀹犱粓閺堝秴濮?, "閺屻儳婀呴崗瀹犱粓鐠у嫭绨?}
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
                pass  # column missing 閳?migration 005 not yet applied

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
                pass  # entry_url column missing 閳?migration 005 not yet applied

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
                pass  # column missing 閳?migration 012 not yet applied

            if DEFAULT_NOTICES and db.scalar(select(func.count()).select_from(portal_notices_table)) == 0:
                db.execute(insert(portal_notices_table), [
                    {
                        **_PORTAL_BASE,
                        "title": item["title"],
                        "source": item["source"],
                        "category": item["category"],
                        "body": f"{item['title']}閵嗗倽顕惄绋垮彠闁劑妫幐澶愨偓姘辩叀鐟曚焦鐪扮€瑰本鍨氶崥搴ｇ敾瀹搞儰缍旈敍灞借嫙閸︺劎绮烘稉鈧梻銊﹀煕娑擃厽鐓￠惇瀣閻炲棜绻樼仦鏇樷偓?,
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
                        "summary": f"{item['name']}閻劋绨梻銊﹀煕閸愬懎宕楁担婧库偓浣圭叀闂冨懎鎷伴惌銉ㄧ槕濞屽绌╅妴?,
                        "updated_at": f"2026-{item['updated_at'][:2]}-{item['updated_at'][3:]}T09:00:00",
                        "favorite_count": 0,
                        "visit_count": 0,
                        "created_at": now,
                    }
                    for item in DEFAULT_DOCUMENTS
                ])
            if DEFAULT_NEWS and db.scalar(select(func.count()).select_from(portal_news_table)) == 0:
                db.execute(insert(portal_news_table), [
                    {
                        **_PORTAL_BASE,
                        "title": item["title"],
                        "source": item["source"],
                        "category": item["category"],
                        "body": f"{item['title']}閵嗗倽顕涢幆鍛殺閸︺劏绁拋顖欒厬韫囧啯瀵旂紒顓熸纯閺傝埇鈧?,
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

    # 閳光偓閳光偓 Row helpers 閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓閳光偓

    def _asset_table(self, collection: str) -> Table:
        tables = {
            "notices": portal_notices_table,
            "documents": portal_documents_table,
            "resources": portal_resources_table,
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

    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?
    # Bootstrap
    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?

    def portal_dashboard(self, user: dict[str, Any] | None = None) -> dict[str, int]:
        with self._session() as db:
            visible_subsystems = self.list_subsystems(user=user)["items"]
            visits_7d = db.scalar(select(func.count()).select_from(portal_subsystem_visits_table)) or 0
        return {
            "subsystems_total": len(visible_subsystems),
            "subsystems_active": sum(1 for item in visible_subsystems if item["status"] == "active"),
            "subsystems_maintenance": sum(1 for item in visible_subsystems if item["status"] == "maintenance"),
            "notices_total": self.list_portal_assets("notices", user=user)["total"],
            "documents_total": self.list_portal_assets("documents", user=user)["total"],
            "news_total": self.list_portal_assets("news", user=user)["total"],
            "today_tasks": self.list_tasks(user=user)["total"],
            "today_events": self.list_events(user=user)["total"],
            "visits_7d": int(visits_7d),
        }

    def enterprise_workbench(self, code: str, user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        configs = {
            "repair": {
                "title": "閹躲儰鎱ㄥ銉ュ礋",
                "columns": ["瀹搞儱宕?, "閻樿埖鈧?, "婢跺嫮鎮婃禍?, "閺囧瓨鏌婇弮鍫曟？"],
                "collection": self.list_repair_tickets,
                "map": lambda item: {
                    "title": item["title"],
                    "status": item["status"],
                    "owner": item.get("assignee") or "瀵板懎鍨庡ú?,
                    "updated": item["updated_at"][:10],
                    "detail": item["description"],
                },
            },
            "assets": {
                "title": "鐠у嫪楠囬崣鎷屽",
                "columns": ["鐠у嫪楠?, "閻樿埖鈧?, "娣囨繄顓告禍?, "閺囧瓨鏌婇弮鍫曟？"],
                "collection": self.list_asset_items,
                "map": lambda item: {
                    "title": item["name"],
                    "status": item["status"],
                    "owner": item.get("custodian") or "閺堫亝瀵氱€?,
                    "updated": item["updated_at"][:10],
                    "detail": f"{item['asset_code']} 璺?{item['category']} 璺?{item['location']}",
                },
            },
            "oa": {
                "title": "瀵板懎濮欏ù浣衡柤",
                "columns": ["濞翠胶鈻?, "閻樿埖鈧?, "瑜版挸澧犳径鍕倞娴?, "閺囧瓨鏌婇弮鍫曟？"],
                "collection": self.list_oa_flows,
                "map": lambda item: {
                    "title": item["title"],
                    "status": item["status"],
                    "owner": item.get("current_handler") or "瀵板懎鍨庡ú?,
                    "updated": item["updated_at"][:10],
                    "detail": f"{item['flow_type']} 璺?瑜版挸澧犻懞鍌滃仯閿涙item.get('current_handler') or '瀵板懎鍨庡ú?}",
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
                    "name": user.get("display_name") or "闁繈鏀? if user else "闁繈鏀?,
                    "department": user.get("default_dept_id") or "" if user else "鎼存梻鏁ら悧鈺冩倞娑撳孩娼楅弬娆忣劅闂?,
                    "last_login": user.get("last_login_at") or "" if user else "2026-07-16 10:56",
                },
                "systems": self.list_subsystems(user=user),
                "news": self.list_portal_assets("news", user=user),
                "preferences": self.get_portal_preferences(user=user),
                "dashboard": self.portal_dashboard(user=user),
            },
            "calendar": {"events": self.list_events(user=user)},
            "knowledge": {"spaces": self.list_knowledge_spaces(user=user)},
        }

    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?
    # Tasks
    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?

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
                    "tag": payload.get("tag") or "娴犲﹤銇?,
                    "deadline": payload.get("deadline") or None,
                    "done": False,
                    "overdue_notified_at": None,
                }
                # Phase 4: set attribution from user context.
                # NEVER trust client-supplied org_id / department_id / owner_id /
                # visibility / sensitivity 閳?always derive from the server-side
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

    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?
    # Calendar Events
    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?

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
                # Extract only known-safe fields 閳?never copy the full payload
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

    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?
    # Embed URLs
    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?

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

    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?
    # Knowledge spaces & mappings
    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?

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
        # filter_: "all" 閳?no filter; "dataset"/"app" 閳?filter by resource_type;
        # "team"/"org"/"private"/"public" 閳?pass-through for permission_scope values
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

    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?
    # Knowledge sync & import records
    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?

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
                # Join import records 閳?mappings and apply the visibility filter
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
                            # still need to be visible 閳?only super_admin / internal
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
        """閸掔娀娅庨幐鍥х暰 collection_id 閻ㄥ嫬顕遍崗銉唶瑜版洏鈧?

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

    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?
    # Chat persistence  (Phase 4: user-level scoping)
    # 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?

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
        """娣囨繂鐡ㄦ稉鈧弶陇浜版径鈺傜Х閹垽绱濋崥灞炬 upsert 娴兼俺鐦介妴?

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
                    # user, reject (silently 閳?don't leak session existence).
                    if user_id is not None and existing_row["user_id"] is not None:
                        if existing_row["user_id"] != user_id:
                            return  # silently drop 閳?don't write to foreign session
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
        """閸掓鍤ぐ鎾冲閻劍鍩涢惃鍕喊婢垛晙绱扮拠婵撶礉閹稿娲块弬鐗堟闂傛潙鈧帒绨妴?

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
        """閼惧嘲褰囬幐鍥х暰娴兼俺鐦介惃鍕Х閹垬鈧?

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
                    return self.list_response([])  # uniform empty 閳?don't leak existence

            stmt = (
                select(chat_messages_table)
                .where(chat_messages_table.c.session_id == session_id)
                .order_by(chat_messages_table.c.id.desc())
            )
            if limit > 0:
                stmt = stmt.limit(limit)
            rows = db.execute(stmt).mappings().all()
            # 閹?id 閸楀洤绨潻鏂挎礀閿涘牊妞傞梻鎾€庢惔蹇ョ礆閿涘苯娲滄稉鐑樺灉娴狀剛鏁?desc 閺屻儴顕?            result = [dict(row) for row in rows]
            result.reverse()
            return self.list_response(result)

    def delete_chat_session(
        self, session_id: str,
        user: dict[str, Any] | None = None,
    ) -> bool:
        """閸掔娀娅庢导姘崇樈閸欏﹤鍙鹃幍鈧張澶嬬Х閹垬鈧?

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
                        return False  # uniform 閳?don't leak existence

                db.execute(
                    delete(chat_messages_table).where(chat_messages_table.c.session_id == session_id)
                )
                result = db.execute(
                    delete(chat_sessions_table).where(chat_sessions_table.c.id == session_id)
                )
                db.commit()
                return result.rowcount > 0


# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?
# Module-level helpers (unchanged signatures)
# 閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳烘劏鏅查埡鎰ㄦ櫜閳?


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
            "desc": "閺夈儴鍤?FastGPT 闁板秶鐤嗛惃鍕埂鐎圭偟鐓＄拠鍡楃氨閿涘苯褰查悽銊ょ艾閺傚洣娆㈢€电厧鍙嗛妴浣哥サ閸忋儱鎷伴崥鎴﹀櫤濡偓缁鳖潿鈧?,
            "type": "public",
            "meta": f"{dataset_id} 璺?{mode}",
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
        "owner": "FastGPT 閺佺増宓侀梿? if is_dataset else "FastGPT 鎼存梻鏁?,
        "desc": "閸欘垰顕遍崗銉︽瀮娴犺泛鑻熼悽?FastGPT 鐎瑰本鍨氬畵灞藉弳閸滃苯鎮滈柌蹇旑梾缁鳖潿鈧? if is_dataset else "閸欘垳鏁ゆ禍?FastGPT 闂傤喚鐡熼幋鏍梾缁便垹绨查悽銊ｂ偓?,
        "type": "public",
        "meta": f"{resource_id} 璺?synced",
        "tone": "app-purple" if is_dataset else "app-blue",
        "fastgpt_dataset_id": row["fastgpt_dataset_id"],
        "fastgpt_app_id": row["fastgpt_app_id"],
        "resource_type": row["resource_type"],
        "enabled": bool(row["enabled"]),
        "is_default_import_target": bool(row["is_default_import_target"]),
        "last_synced_at": row["last_synced_at"],
        "last_imported_at": row["last_imported_at"],
        "stale": bool(row["stale"]),
        # 閳光偓閳光偓 Phase 5: attribution fields for retrieval_policy 閳光偓閳光偓閳光偓閳光偓閳光偓
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
