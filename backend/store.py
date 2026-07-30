from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from threading import RLock
from typing import Any, Iterator

from sqlalchemy import Boolean, Column, Integer, MetaData, String, Table, Text, delete, func, insert, select, text, update
from sqlalchemy.orm import Session

from config import get_settings
from session import get_engine, get_session_local


metadata = MetaData()

tasks_table = Table(
    "portal_tasks",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("title", String(255), nullable=False),
    Column("tag", String(32), nullable=False),
    Column("due_time", String(8), nullable=True),
    Column("done", Boolean, nullable=False, default=False),
)

events_table = Table(
    "portal_calendar_events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("date", String(10), nullable=False),
    Column("title", String(255), nullable=False),
    Column("tone", String(16), nullable=False),
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
    Column("last_synced_at", String(32), nullable=True),
    Column("last_imported_at", String(32), nullable=True),
    Column("stale", Boolean, nullable=False, default=False),
    Column("updated_at", String(32), nullable=False),
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
)


DEFAULT_EMBED_URLS = {
    "feishu": "https://www.feishu.cn/",
    "dingtalk": "https://www.dingtalk.com/",
}

DEFAULT_TASKS = [
    {"id": 1, "title": "完成季度工作复盘表", "tag": "今天", "due_time": "10:00", "done": False},
    {"id": 2, "title": "确认信息安全培训名单", "tag": "今天", "due_time": "15:00", "done": False},
    {"id": 3, "title": "整理部门知识库目录", "tag": "本周", "due_time": None, "done": False},
    {"id": 4, "title": "回复项目推进反馈", "tag": "本周", "due_time": None, "done": False},
    {"id": 5, "title": "更新服务目录", "tag": "已完成", "due_time": None, "done": True},
]

DEFAULT_EVENTS = [
    {"id": 1, "date": "2026-07-02", "title": "项目周会", "tone": "blue"},
    {"id": 2, "date": "2026-07-06", "title": "信息安全培训", "tone": "green"},
    {"id": 3, "date": "2026-07-10", "title": "季度复盘", "tone": "orange"},
    {"id": 4, "date": "2026-07-27", "title": "部门周例会", "tone": "blue"},
]

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

DEFAULT_SERVICES = [
    "教职工考勤",
    "教职工请假",
    "教职工信息变更管理",
    "离退休人员管理",
    "教职工进校",
    "教职工招聘",
    "在职教职工工资查询与统计",
    "在职证明",
    "因公外出报备申请",
]

DEFAULT_KNOWLEDGE: list[dict[str, Any]] = []

DEFAULT_NOTICES = [
    {"title": "关于 2026 年暑假安排的通知", "source": "党政办公室", "category": "公告", "time": "07/05 17:09"},
    {"title": "关于举办办公区人员、信息员培训会的通知", "source": "党政办公室", "category": "培训", "time": "07/03 12:11"},
]

DEFAULT_DOCUMENTS = [
    {"name": "2024 版课程教学大纲模板", "location": "我的云文档", "owner": "郝锐", "updated_at": "07/16", "file_type": "W"},
    {"name": "部门季度工作复盘表", "location": "团队文档", "owner": "教务办公室", "updated_at": "07/14", "file_type": "X"},
    {"name": "会议纪要模板", "location": "我的云文档", "owner": "行政中心", "updated_at": "07/12", "file_type": "P"},
]


def list_response(items: list[dict[str, Any]] | list[str]) -> dict[str, Any]:
    return {"items": deepcopy(items), "total": len(items)}


class PortalStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._ensure_schema()

    @contextmanager
    def _session(self) -> Iterator[Session]:
        self._ensure_schema()
        db = get_session_local()()
        try:
            yield db
        finally:
            db.close()

    def _ensure_schema(self) -> None:
        with self._lock:
            engine = get_engine()
            metadata.create_all(bind=engine)
            self._ensure_sqlite_columns(engine)
            session_local = get_session_local()
            with session_local() as db:
                # Only seed defaults once (never re-seed after user deletes data)
                tasks_seeded = db.scalar(
                    select(settings_table.c.value_json).where(settings_table.c.key == "tasks_seeded"),
                )
                if tasks_seeded is None and db.scalar(select(func.count()).select_from(tasks_table)) == 0:
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
                if events_seeded is None and db.scalar(select(func.count()).select_from(events_table)) == 0:
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
                db.commit()

    def _ensure_sqlite_columns(self, engine: Any) -> None:
        if not str(engine.url).startswith("sqlite"):
            return
        expected = {
            "knowledge_dataset_mappings": {
                "is_default_import_target": "BOOLEAN NOT NULL DEFAULT 0",
                "last_synced_at": "VARCHAR(32)",
                "last_imported_at": "VARCHAR(32)",
                "stale": "BOOLEAN NOT NULL DEFAULT 0",
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

    def _task_from_row(self, row: Any) -> dict[str, Any]:
        item = dict(row)
        item["done"] = bool(item["done"])
        return item

    def _event_from_row(self, row: Any) -> dict[str, Any]:
        return dict(row)

    def bootstrap_payload(self) -> dict[str, Any]:
        return {
            "workspace": {
                "tasks": self.list_tasks(),
                "shortcuts": DEFAULT_SHORTCUTS,
                "resources": list_response([
                    {"title": "制度手册", "description": "组织制度与办事指南", "tone": "app-red"},
                    {"title": "数据门户", "description": "经营与运营数据", "tone": "app-blue"},
                    {"title": "培训资料库", "description": "课程与培训材料", "tone": "app-orange"},
                    {"title": "服务目录", "description": "常用服务与申请入口", "tone": "app-green"},
                ]),
                "documents": list_response(DEFAULT_DOCUMENTS),
                "notices": list_response(DEFAULT_NOTICES),
            },
            "portal": {
                "profile": {
                    "name": "郝锐",
                    "department": "应用物理与材料学院",
                    "last_login": "2026-07-16 10:56",
                },
                "systems": list_response(DEFAULT_SYSTEMS),
                "services": list_response(DEFAULT_SERVICES),
                "news": list_response([
                    {"title": "组织数字化服务升级，统一门户上线新入口", "source": "企业资讯", "date": "07/24"},
                    {"title": "2026 年第二季度运营回顾与重点工作安排", "source": "运营中心", "date": "07/22"},
                    {"title": "知识资产沉淀计划启动，支持部门知识库共建", "source": "知识中心", "date": "07/18"},
                    {"title": "信息安全与数据合规培训报名通知", "source": "安全办公室", "date": "07/16"},
                ]),
            },
            "calendar": {"events": self.list_events()},
            "knowledge": {"spaces": self.list_knowledge_spaces()},
        }

    def list_tasks(self) -> dict[str, Any]:
        with self._session() as db:
            rows = db.execute(select(tasks_table).order_by(tasks_table.c.id.desc())).mappings().all()
            items = [self._task_from_row(row) for row in rows]
            return list_response(items)

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            with self._session() as db:
                result = db.execute(
                    insert(tasks_table).values(
                        title=payload["title"],
                        tag=payload.get("tag") or "今天",
                        due_time=payload.get("due_time") or None,
                        done=False,
                    ),
                )
                db.commit()
                task_id = int(result.inserted_primary_key[0])
                row = db.execute(select(tasks_table).where(tasks_table.c.id == task_id)).mappings().one()
                return self._task_from_row(row)

    def update_task(self, task_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            with self._session() as db:
                updates = {key: value for key, value in payload.items() if key in {"title", "tag", "due_time", "done"}}
                if updates:
                    db.execute(update(tasks_table).where(tasks_table.c.id == task_id).values(**updates))
                    db.commit()
                row = db.execute(select(tasks_table).where(tasks_table.c.id == task_id)).mappings().first()
                return self._task_from_row(row) if row else None

    def delete_task(self, task_id: int) -> bool:
        with self._lock:
            with self._session() as db:
                result = db.execute(delete(tasks_table).where(tasks_table.c.id == task_id))
                db.commit()
                return result.rowcount > 0

    def clear_done_tasks(self) -> int:
        with self._lock:
            with self._session() as db:
                result = db.execute(delete(tasks_table).where(tasks_table.c.done.is_(True)))
                db.commit()
                return int(result.rowcount or 0)

    def list_events(self) -> dict[str, Any]:
        with self._session() as db:
            rows = db.execute(select(events_table).order_by(events_table.c.date, events_table.c.id)).mappings().all()
            items = [self._event_from_row(row) for row in rows]
            return list_response(items)

    def create_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            with self._session() as db:
                result = db.execute(insert(events_table).values(**payload))
                db.commit()
                event_id = int(result.inserted_primary_key[0])
                row = db.execute(select(events_table).where(events_table.c.id == event_id)).mappings().one()
                return self._event_from_row(row)

    def update_event(self, event_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            with self._session() as db:
                db.execute(update(events_table).where(events_table.c.id == event_id).values(**payload))
                db.commit()
                row = db.execute(select(events_table).where(events_table.c.id == event_id)).mappings().first()
                return self._event_from_row(row) if row else None

    def delete_event(self, event_id: int) -> bool:
        with self._lock:
            with self._session() as db:
                result = db.execute(delete(events_table).where(events_table.c.id == event_id))
                db.commit()
                return result.rowcount > 0

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

    def list_knowledge_spaces(self, search: str = "", filter_: str = "all") -> dict[str, Any]:
        query = search.strip().lower()
        settings = get_settings()
        items = self._list_synced_knowledge_spaces()
        if not items:
            items = configured_knowledge_spaces(
                dataset_id=settings.FASTGPT_DEFAULT_DATASET_ID,
                app_id=settings.FASTGPT_DEFAULT_APP_ID or settings.FASTGPT_CHAT_APP_ID,
                display_name=settings.FASTGPT_DEFAULT_DISPLAY_NAME,
                mode=settings.FASTGPT_MODE,
            )
        items = [
            item for item in items
            if (filter_ == "all" or item["type"] == filter_)
            and (not query or query in f"{item['title']}{item['owner']}{item['desc']}{item.get('fastgpt_dataset_id') or ''}{item.get('fastgpt_app_id') or ''}".lower())
        ]
        return list_response(items)

    def _list_synced_knowledge_spaces(self) -> list[dict[str, Any]]:
        with self._session() as db:
            rows = db.execute(
                select(knowledge_mappings_table)
                .where(knowledge_mappings_table.c.enabled.is_(True))
                .order_by(knowledge_mappings_table.c.display_name),
            ).mappings().all()
            return [knowledge_space_from_mapping(row) for row in rows]

    def list_knowledge_mappings(self) -> dict[str, Any]:
        with self._session() as db:
            rows = db.execute(
                select(knowledge_mappings_table)
                .order_by(knowledge_mappings_table.c.resource_type.desc(), knowledge_mappings_table.c.display_name),
            ).mappings().all()
            return list_response([knowledge_mapping_from_row(row) for row in rows])

    def update_knowledge_mapping(self, mapping_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            with self._session() as db:
                row = db.execute(
                    select(knowledge_mappings_table)
                    .where(knowledge_mappings_table.c.id == mapping_id),
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
                    db.execute(
                        update(knowledge_mappings_table)
                        .where(knowledge_mappings_table.c.resource_type == "dataset")
                        .values(is_default_import_target=False),
                    )
                    updates["is_default_import_target"] = True
                elif payload.get("is_default_import_target") is False:
                    updates["is_default_import_target"] = False
                db.execute(
                    update(knowledge_mappings_table)
                    .where(knowledge_mappings_table.c.id == mapping_id)
                    .values(**updates),
                )
                db.commit()
                next_row = db.execute(
                    select(knowledge_mappings_table)
                    .where(knowledge_mappings_table.c.id == mapping_id),
                ).mappings().one()
                return knowledge_mapping_from_row(next_row)

    def delete_knowledge_mapping(self, mapping_id: str) -> bool:
        with self._lock:
            with self._session() as db:
                result = db.execute(
                    delete(knowledge_mappings_table)
                    .where(knowledge_mappings_table.c.id == mapping_id),
                )
                db.commit()
                return bool(result.rowcount)

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
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._session() as db:
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

    def list_knowledge_imports(self) -> dict[str, Any]:
        with self._session() as db:
            rows = db.execute(
                select(knowledge_import_records_table)
                .order_by(knowledge_import_records_table.c.id.desc()),
            ).mappings().all()
            return list_response([dict(row) for row in rows])

    def delete_knowledge_import_by_collection(self, collection_id: str) -> None:
        """删除指定 collection_id 的导入记录。"""
        with self._lock:
            with self._session() as db:
                db.execute(
                    knowledge_import_records_table.delete()
                    .where(knowledge_import_records_table.c.collection_id == collection_id),
                )
                db.commit()

    def search(self, query: str) -> dict[str, Any]:
        needle = query.strip().lower()
        sources: list[dict[str, str]] = []
        sources.extend({"type": "知识库", "title": item["title"], "description": item["desc"]} for item in self.list_knowledge_spaces()["items"])
        sources.extend({"type": "文档", "title": item["name"], "description": item["location"]} for item in DEFAULT_DOCUMENTS)
        sources.extend({"type": "公告", "title": item["title"], "description": item["source"]} for item in DEFAULT_NOTICES)
        sources.extend({"type": "服务", "title": name, "description": "服务分类"} for name in DEFAULT_SERVICES)
        items = [item for item in sources if not needle or needle in f"{item['title']}{item['description']}{item['type']}".lower()]
        return list_response(items[:20])


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
