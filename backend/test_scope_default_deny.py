"""Unknown scope policies and missing identities must fail closed."""

from dataclasses import replace

import pytest
from fastapi import HTTPException
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, insert, select

from authorization.scope import AccessContext, can_access_resource
from authorization.sql_filters import knowledge_visibility_filter, task_visibility_filter
from conftest import TEST_USERS, auth_headers, login
from store import store
from stores.base import BaseStore


def context(*, super_admin=False, org_ids=None, dept_ids=None):
    return AccessContext(
        user_id=1, username="scope", roles=["super_admin" if super_admin else "dept_staff"],
        permissions=[], default_org_id="org-a", default_dept_id=None,
        is_super_admin=super_admin, org_ids={"org-a"} if org_ids is None else org_ids,
        visible_dept_ids=set() if dept_ids is None else dept_ids,
    )


def scope_table(name):
    return Table(
        name, MetaData(), Column("id", Integer, primary_key=True),
        Column("org_id", String), Column("department_id", String),
        Column("owner_id", Integer), Column("visibility", String), Column("sensitivity", String),
    )


def matching_ids(table, clause, rows=None):
    engine = create_engine("sqlite://")
    table.metadata.create_all(engine)
    try:
        with engine.begin() as db:
            db.execute(insert(table), rows or [{
                "id": 1, "org_id": "org-a", "department_id": "dept-a", "owner_id": 1,
                "visibility": "private", "sensitivity": "normal",
            }])
            return list(db.scalars(select(table.c.id).where(clause)))
    finally:
        engine.dispose()


@pytest.mark.parametrize("user", [None, {}, {"id": None}, {"id": True}, {"id": "system"},
                                 {"system": True}, {"roles": ["super_admin"]}])
def test_missing_identity_cannot_build_context(user):
    with pytest.raises(HTTPException) as exc:
        BaseStore()._build_scope_context(user, None)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("name", ["portal_tasks", "knowledge_dataset_mappings", "unregistered_resources"])
@pytest.mark.parametrize("single", [False, True])
def test_missing_context_never_returns_rows(name, single):
    table = scope_table(name)
    base = BaseStore()
    clause = base._scope_single(None, table, 1) if single else base._scope_filter(None, table)
    assert matching_ids(table, clause) == []


@pytest.mark.parametrize("super_admin", [False, True])
@pytest.mark.parametrize("single", [False, True])
def test_unknown_table_never_returns_rows(super_admin, single):
    table = scope_table("unregistered_resources")
    ctx = context(super_admin=super_admin)
    base = BaseStore()
    clause = base._scope_single(ctx, table, 1) if single else base._scope_filter(ctx, table)
    assert matching_ids(table, clause) == []


@pytest.mark.parametrize("super_admin", [False, True])
@pytest.mark.parametrize("visibility", [None, "", "invented"])
def test_unknown_visibility_is_denied_to_owner_and_admin(super_admin, visibility):
    assert not can_access_resource(context(super_admin=super_admin), "org-a", "dept-a", 1, visibility)


@pytest.mark.parametrize("builder", [task_visibility_filter, knowledge_visibility_filter])
@pytest.mark.parametrize("super_admin", [False, True])
def test_unknown_row_policy_is_denied_by_sql(builder, super_admin):
    table = scope_table("portal_tasks" if builder is task_visibility_filter else "knowledge_dataset_mappings")
    rows = [
        {"id": 1, "owner_id": 1, "visibility": "invented", "sensitivity": "normal"},
        {"id": 2, "owner_id": 1, "visibility": "public", "sensitivity": "invented"},
    ]
    assert matching_ids(table, builder(context(super_admin=super_admin), table), rows) == []


def test_department_scope_requires_matching_organisation():
    ctx = context(dept_ids={"dept-a"})
    assert not can_access_resource(ctx, "org-b", "dept-a", 2, "dept")
    assert not can_access_resource(replace(ctx, org_ids=set()), "org-a", "dept-a", 2, "dept")
    table = scope_table("knowledge_dataset_mappings")
    rows = [{"id": 1, "org_id": "org-a", "department_id": "dept-a", "owner_id": 2,
             "visibility": "dept", "sensitivity": "normal"}]
    assert matching_ids(table, knowledge_visibility_filter(replace(ctx, org_ids=set()), table), rows) == []


def test_public_resources_remain_explicit_and_sensitivity_checked():
    table = scope_table("portal_documents")
    rows = [
        {"id": 1, "org_id": "org-b", "owner_id": 2, "visibility": "public", "sensitivity": "normal"},
        {"id": 2, "org_id": "org-b", "owner_id": 2, "visibility": "public", "sensitivity": "sensitive"},
        {"id": 3, "org_id": "org-b", "owner_id": 2, "visibility": "private", "sensitivity": "normal"},
    ]
    user = {"id": 1, "roles": ["external"], "default_org_id": "org-a"}
    clause = BaseStore()._portal_visibility_clause(user, table, None)
    assert matching_ids(table, clause, rows) == [1]
    with pytest.raises(HTTPException) as exc:
        BaseStore()._portal_visibility_clause(None, table, None)
    assert exc.value.status_code == 401


def test_portal_unknown_table_denied_even_to_super_admin():
    table = scope_table("unregistered_resources")
    user = {"id": 1, "roles": ["super_admin"]}
    assert matching_ids(table, BaseStore()._portal_visibility_clause(user, table, None)) == []


@pytest.fixture
def user(client):
    token = login(client, TEST_USERS["dept_staff"]["username"], TEST_USERS["dept_staff"]["password"])
    client.headers.update(auth_headers(token))
    store._ensure_schema()
    return client.get("/api/v1/auth/me").json()


@pytest.mark.parametrize("method,kwargs", [
    ("list_tasks", {}), ("create_task", {"payload": {"title": "denied"}}),
    ("update_task", {"task_id": 1, "payload": {"title": "denied"}}),
    ("delete_task", {"task_id": 1}), ("clear_done_tasks", {}),
    ("list_events", {}), ("create_event", {"payload": {"title": "denied", "date": "2026-10-14"}}),
    ("list_portal_assets", {"collection": "documents"}), ("list_subsystems", {}),
    ("list_knowledge_mappings", {}), ("list_knowledge_imports", {}),
    ("record_knowledge_import", {"dataset_id": "missing", "file_name": "denied", "status": "success", "collection_id": "c"}),
    ("delete_knowledge_import_by_collection", {"collection_id": "c"}),
    ("sync_knowledge_mappings", {"resources": []}),
    ("list_chat_sessions", {}), ("get_chat_messages", {"session_id": "unknown"}),
    ("delete_chat_session", {"session_id": "unknown"}),
    ("save_chat_message", {"session_id": "unknown", "role": "user", "content": "denied"}),
])
def test_store_operations_require_identity(user, method, kwargs):
    with pytest.raises(HTTPException) as exc:
        getattr(store, method)(**kwargs)
    assert exc.value.status_code == 401


@pytest.mark.parametrize("actor", [None, "overdue_scanner", {"system": True}, {"roles": ["super_admin"]}])
@pytest.mark.parametrize("method,kwargs", [
    ("find_overdue_tasks", {}), ("mark_task_overdue_notified", {"task_id": 1}),
    ("create_notification", {"user_id": 1, "title": "forged"}),
])
def test_forged_system_actor_is_denied(user, actor, method, kwargs):
    with pytest.raises(HTTPException) as exc:
        getattr(store, method)(actor=actor, **kwargs)
    assert exc.value.status_code == 403


def test_explicit_system_actor_runs_overdue_task_flow(user):
    from authorization.system import SystemActor

    task = store.create_task({"title": "overdue", "deadline": "2000-01-01T00:00:00"}, user=user)
    tasks = store.find_overdue_tasks(actor=SystemActor.OVERDUE_SCANNER)
    assert task["id"] in {item["id"] for item in tasks}
    store.mark_task_overdue_notified(task["id"], actor=SystemActor.OVERDUE_SCANNER)
    notification = store.create_notification(
        user_id=user["id"], title="overdue", actor=SystemActor.OVERDUE_SCANNER,
    )
    assert notification["user_id"] == user["id"]
    assert task["id"] not in {item["id"] for item in store.find_overdue_tasks(actor=SystemActor.OVERDUE_SCANNER)}
    assert notification["id"] in {item["id"] for item in store.list_notifications(user)["items"]}
    with pytest.raises(HTTPException) as exc:
        store.find_overdue_tasks(actor=SystemActor.ROLE_NOTIFIER)
    assert exc.value.status_code == 403


def test_unowned_chat_session_cannot_be_claimed_or_read(user):
    from store import chat_messages_table, chat_sessions_table

    with store._session() as db:
        db.execute(insert(chat_sessions_table).values(id="legacy", title="legacy", user_id=None,
                                                     created_at="2026-10-14", updated_at="2026-10-14"))
        db.execute(insert(chat_messages_table).values(session_id="legacy", role="user", content="private",
                                                     created_at="2026-10-14"))
        db.commit()
    assert store.get_chat_messages("legacy", user=user)["items"] == []
    store.save_chat_message("legacy", "user", "injected", user_id=user["id"])
    assert not store.delete_chat_session("legacy", user=user)
    with store._session() as db:
        assert db.scalar(select(chat_sessions_table.c.user_id).where(chat_sessions_table.c.id == "legacy")) is None
        assert db.scalars(select(chat_messages_table.c.content).where(chat_messages_table.c.session_id == "legacy")).all() == ["private"]


@pytest.mark.parametrize("method,kwargs", [
    ("find_overdue_tasks", {}), ("mark_task_overdue_notified", {"task_id": 1}),
    ("create_notification", {"user_id": 1, "title": "denied"}),
])
def test_omitting_system_actor_is_denied(user, method, kwargs):
    with pytest.raises(HTTPException) as exc:
        getattr(store, method)(**kwargs)
    assert exc.value.status_code == 403


def test_system_actor_grants_no_generic_scope():
    from authorization.system import SystemActor

    table = scope_table("portal_tasks")
    assert matching_ids(table, BaseStore()._scope_filter(SystemActor.OVERDUE_SCANNER, table)) == []
    with pytest.raises(HTTPException) as exc:
        BaseStore()._build_scope_context(SystemActor.OVERDUE_SCANNER, None)
    assert exc.value.status_code == 401


def test_unknown_table_cannot_be_created(user):
    with pytest.raises(HTTPException) as exc:
        store._enterprise_create(scope_table("unregistered_resources"), {}, user=user)
    assert exc.value.status_code == 403


def test_unmapped_dataset_cannot_receive_import_records(user):
    from store import knowledge_import_records_table

    with pytest.raises(HTTPException) as exc:
        store.record_knowledge_import(dataset_id="unmapped", file_name="private", status="success",
                                      collection_id="forged", user=user)
    assert exc.value.status_code == 403
    with store._session() as db:
        assert db.scalar(select(knowledge_import_records_table.c.id)
                         .where(knowledge_import_records_table.c.dataset_id == "unmapped")) is None


def test_global_sync_requires_super_admin(user):
    with pytest.raises(HTTPException) as exc:
        store.sync_knowledge_mappings([], user=user)
    assert exc.value.status_code == 403


def test_owned_chat_session_remains_usable(user):
    store.save_chat_message("owned", "user", "mine", user_id=user["id"])
    assert store.get_chat_messages("owned", user=user)["items"][0]["content"] == "mine"
    assert "owned" in {item["id"] for item in store.list_chat_sessions(user=user)["items"]}
    foreign = {**user, "id": user["id"] + 10000}
    assert store.get_chat_messages("owned", user=foreign)["items"] == []
    assert not store.delete_chat_session("owned", user=foreign)
    assert store.delete_chat_session("owned", user=user)


@pytest.mark.parametrize("policy", [{"visibility": "invented"}, {"sensitivity": "invented"}])
def test_system_scanner_rejects_unknown_row_policy(user, policy):
    from sqlalchemy import update

    from authorization.system import SystemActor
    from store import tasks_table

    task = store.create_task({"title": "invalid policy", "deadline": "2000-01-01T00:00:00"}, user=user)
    with store._session() as db:
        db.execute(update(tasks_table).where(tasks_table.c.id == task["id"]).values(**policy))
        db.commit()
    assert task["id"] not in {item["id"] for item in store.find_overdue_tasks(actor=SystemActor.OVERDUE_SCANNER)}
    store.mark_task_overdue_notified(task["id"], actor=SystemActor.OVERDUE_SCANNER)
    with store._session() as db:
        row = db.execute(select(tasks_table).where(tasks_table.c.id == task["id"])).mappings().one()
        assert row["overdue_notified_at"] is None
        assert row["status"] is None
