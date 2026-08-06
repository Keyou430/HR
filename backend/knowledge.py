import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from ai_security.firewall import ai_security_pipeline
from auth.dependencies import get_current_user, require_permission
from commands import classify_command, execute_command
from config import Settings, get_settings
from hermes import HermesGatewayError, hermes_chat
from schemas import KnowledgeChatRequest, KnowledgeMappingUpdate
from session import get_db
from store import store

logger = logging.getLogger("replica.knowledge")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(_handler)
    logger.propagate = False


router = APIRouter(
    prefix="/api/v1/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(require_permission("kb:view"))],
)


@router.get("/spaces")
async def list_knowledge_spaces(
    search: str = "",
    filter: str = Query(default="all"),  # noqa: A002
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict:
    return store.list_knowledge_spaces(search=search, filter_=filter, user=current_user)


@router.get("/mappings")
async def list_knowledge_mappings(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_knowledge_mappings(user=current_user)


@router.patch("/mappings/{mapping_id:path}",
              dependencies=[Depends(require_permission("kb:update"))])
async def update_knowledge_mapping(
    mapping_id: str,
    payload: KnowledgeMappingUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    item = store.update_knowledge_mapping(mapping_id, payload.model_dump(exclude_unset=True), user=current_user)
    if item is None:
        raise HTTPException(status_code=404, detail="knowledge mapping not found")
    return item


@router.delete("/mappings/{mapping_id:path}",
               dependencies=[Depends(require_permission("kb:delete"))])
async def delete_knowledge_mapping(
    mapping_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, bool]:
    if not store.delete_knowledge_mapping(mapping_id, user=current_user):
        raise HTTPException(status_code=404, detail="knowledge mapping not found")
    return {"ok": True}


@router.get("/imports")
async def list_knowledge_imports(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    return store.list_knowledge_imports(user=current_user)


@router.post("/sync", dependencies=[Depends(require_permission("kb:import"))])
async def sync_knowledge_mappings() -> dict[str, Any]:
    settings = get_settings()
    try:
        resources = await list_fastgpt_resources(settings)
        return store.sync_knowledge_mappings(resources)
    except KnowledgeGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


async def _build_search_queries(settings: Settings, question: str) -> list[str]:
    """将复杂问题拆分为 2-3 个独立搜索查询，覆盖问题的不同方面。短问题直接返回原文。"""
    if len(question) <= 40:
        return [question]
    try:
        answer = await hermes_chat(
            settings=settings,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "将用户问题拆分为2-3个独立的搜索查询，每个查询聚焦问题的一个核心概念或方面。"
                        "规则：每行一个查询，用换行分隔，不要编号、不要解释、不要任何其他文字。"
                        "每个查询应简洁（5-15字），使用问题中的关键术语。"
                    ),
                },
                {"role": "user", "content": question},
            ],
        )
        queries = [q.strip() for q in answer.strip().split("\n") if q.strip()]
        if len(queries) >= 1:
            logger.info("Query split result: %r", queries)
            return queries[:3]
    except HermesGatewayError:
        logger.warning("Query split failed, using original question")
    return [question]


def _extract_score(score: Any) -> float:
    """从 FastGPT 返回的 score 字段中安全提取相似度数值。

    FastGPT 不同版本可能返回: 裸 float (0.85)、list ([{"value": 0.85}])、或 None。
    """
    if score is None:
        return 0.0
    if isinstance(score, (int, float)):
        return float(score)
    if isinstance(score, list) and len(score) > 0:
        first = score[0]
        if isinstance(first, dict):
            val = first.get("value", 0)
            return float(val) if val is not None else 0.0
        if isinstance(first, (int, float)):
            return float(first)
    if isinstance(score, dict):
        val = score.get("value", 0)
        return float(val) if val is not None else 0.0
    return 0.0


def _load_chat_history(
    session_id: str | None,
    max_messages: int = 12,
    user: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """加载最近的对话历史，转换为 Hermes API 消息格式。相邻重复消息去重。

    When *user* is provided the store enforces session ownership — only the
    session owner can load the history (Phase 4 security fix).
    """
    if not session_id:
        return []
    try:
        data = store.get_chat_messages(session_id, limit=max_messages, user=user)
        messages = data.get("items", [])
        if not messages:
            return []
        # store 已经按 id DESC + LIMIT 返回最近 N 条（升序排列）
        recent = messages
        history: list[dict[str, str]] = []
        prev_content = ""
        for m in recent:
            if m.get("role") not in ("user", "assistant"):
                continue
            content = m["content"]
            # 跳过相邻重复（修复期间可能产生的双份数据）
            if content == prev_content and m["role"] == (history[-1]["role"] if history else ""):
                continue
            prev_content = content
            history.append({"role": m["role"], "content": content})
        return history
    except Exception:
        logger.warning("Failed to load chat history for session %s", session_id, exc_info=True)
        return []


def _save_chat_turn(
    session_id: str | None,
    question: str,
    answer: str,
    action: str | None = None,
    user_id: int | None = None,
) -> None:
    """在服务端保存一轮对话（用户问题 + 助手回答）。同步写入，确保下一轮请求能加载到历史。

    When *user_id* is provided the store enforces session ownership — only the
    session owner can write messages (Phase 4 security fix).
    """
    if not session_id:
        return
    try:
        store.save_chat_message(session_id, "user", question, action=action, user_id=user_id)
        store.save_chat_message(session_id, "assistant", answer, action=action, user_id=user_id)
    except Exception:
        logger.warning("Failed to save chat turn for session %s", session_id, exc_info=True)
        # 持久化失败不影响对话功能


@router.post("/chat", dependencies=[Depends(require_permission("kb:chat"))])
async def knowledge_chat(
    payload: KnowledgeChatRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()

    # ── 解析问题：支持 /rag 和 /chat 斜杠命令强制指定模式 ──
    question = payload.question.strip()
    forced_mode: str | None = None
    for prefix in ("/rag", "/RAG", "/chat", "/CHAT"):
        if question == prefix or question.startswith(prefix + " "):
            forced_mode = "rag" if prefix.lower() == "/rag" else "chat"
            question = question[len(prefix):].strip()
            break

    # ── 指令模式：尝试识别并执行操作指令 ──
    # 长文本（>200字）几乎不可能是操作指令，跳过分类以节省 LLM 调用并避免误判
    if payload.command_mode and not forced_mode:
        if len(question) <= 200:
            cmd = await classify_command(settings, question)
            if cmd.get("action") not in ("chat", None, ""):
                logger.info(
                    "knowledge_chat — COMMAND mode action=%s params=%s",
                    cmd.get("action"), cmd.get("params"),
                )
                result = execute_command(cmd)
                _save_chat_turn(payload.session_id, question, result["answer"], result.get("action"),
                                user_id=current_user["id"])
                return result
        else:
            logger.info("knowledge_chat — skipping command classification: question too long (%d chars)", len(question))

    # ── 加载对话历史上下文（传入 current_user 以强制会话所有权检查）──
    history = _load_chat_history(payload.session_id, user=current_user)

    # ── 确定请求模式 ──
    if forced_mode:
        requested_mode = forced_mode
    elif payload.mode in ("rag", "chat"):
        requested_mode = payload.mode
    else:
        requested_mode = "auto"

    logger.info(
        "knowledge_chat — mode=%s question=%r",
        requested_mode, question[:120],
    )

    # ── Phase 5: AI 安全防火墙管线 ──
    # 处理顺序: 认证 → kb:chat 权限 → 数据范围 → 风险分类 → 授权检索 → LLM 生成 → 输出检查 → 审计
    fw_result = await ai_security_pipeline(
        settings=settings,
        user=current_user,
        db=db,
        question=question,
        mode=requested_mode,
        scope=payload.scope,
        session_id=payload.session_id,
        store=store,
        history=history,
    )

    response: dict[str, Any] = {
        "answer": fw_result.answer,
        "sources": fw_result.sources,
        "mode": fw_result.mode,
    }

    _save_chat_turn(payload.session_id, question, fw_result.answer, fw_result.mode,
                    user_id=current_user["id"])
    return response


async def search_fastgpt_dataset(
    *,
    settings: Settings,
    dataset_id: str,
    query: str,
    top_k: int = 5,
    similarity: float = 0.3,
) -> list[dict[str, Any]]:
    """调用 FastGPT searchTest API 检索数据集中的相关文档片段。"""
    if settings.FASTGPT_MODE != "real":
        return []
    if not settings.FASTGPT_API_KEY:
        return []

    payload, _ = await request_fastgpt_json(
        settings=settings,
        method="POST",
        path="/core/dataset/searchTest",
        json_body={
            "datasetId": dataset_id,
            "text": query,
            "limit": top_k,
            "similarity": similarity,
            "searchMode": "embedding",
        },
    )
    items: list[dict[str, Any]] = payload.get("data", {}).get("list", [])
    return items


@router.post("/import", status_code=status.HTTP_202_ACCEPTED,
              dependencies=[Depends(require_permission("kb:import"))])
async def import_knowledge_file(
    dataset_id: str = Form(min_length=1),
    file: UploadFile = File(),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="上传文件不能为空")

    settings = get_settings()
    try:
        result = await import_file_to_fastgpt(
            settings=settings,
            dataset_id=dataset_id,
            file_name=file.filename or "knowledge-file",
            content=content,
            content_type=file.content_type or "application/octet-stream",
        )
        store.record_knowledge_import(
            dataset_id=dataset_id,
            file_name=result["file_name"],
            status=result["status"],
            collection_id=extract_collection_id(result.get("fastgpt_response")),
            user=current_user,
        )
        return result
    except KnowledgeGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


class KnowledgeGatewayError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


async def list_fastgpt_resources(settings: Settings) -> list[dict[str, Any]]:
    if settings.FASTGPT_MODE != "real":
        raise KnowledgeGatewayError(409, "FASTGPT_REAL_MODE_REQUIRED", "请先启用 FastGPT real 模式")
    if not settings.FASTGPT_API_KEY:
        raise KnowledgeGatewayError(409, "FASTGPT_NOT_CONFIGURED", "FastGPT API Key 未配置")

    dataset_payload, _ = await request_fastgpt_json(
        settings=settings,
        method="POST",
        path="/core/dataset/list?parentId=",
        json_body={"parentId": ""},
    )
    resources = normalize_fastgpt_resources(dataset_payload, "dataset")
    return dedupe_fastgpt_resources(resources)


async def import_file_to_fastgpt(
    *,
    settings: Settings,
    dataset_id: str,
    file_name: str,
    content: bytes,
    content_type: str,
) -> dict[str, Any]:
    if settings.FASTGPT_MODE != "real":
        raise KnowledgeGatewayError(409, "FASTGPT_REAL_MODE_REQUIRED", "请先启用 FastGPT real 模式")
    if not settings.FASTGPT_API_KEY:
        raise KnowledgeGatewayError(409, "FASTGPT_NOT_CONFIGURED", "FastGPT API Key 未配置")

    data = {
        "datasetId": dataset_id,
        "parentId": None,
        "trainingType": "chunk",
        "chunkSize": 512,
        "chunkSplitter": "",
        "qaPrompt": "",
        "metadata": {"source": "replica"},
    }
    response_payload = await request_fastgpt_file_import(
        settings=settings,
        file_name=file_name,
        content=content,
        content_type=content_type,
        data=data,
    )
    return {
        "dataset_id": dataset_id,
        "file_name": file_name,
        "status": "queued",
        "fastgpt_response": response_payload,
    }


async def request_fastgpt_file_import(
    *,
    settings: Settings,
    file_name: str,
    content: bytes,
    content_type: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {settings.FASTGPT_API_KEY}"}
    files = {
        "file": (file_name, content, content_type),
        "data": (None, json.dumps(data, ensure_ascii=False), "application/json"),
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.FASTGPT_TIMEOUT_SECONDS)) as client:
            response = await client.post(
                f"{settings.FASTGPT_BASE_URL.rstrip('/')}/core/dataset/collection/create/localFile",
                headers=headers,
                files=files,
            )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            return payload
        return {"data": payload}
    except httpx.ConnectError as exc:
        raise KnowledgeGatewayError(503, "FASTGPT_NOT_STARTED", "FastGPT 服务未启动或不可达") from exc
    except httpx.TimeoutException as exc:
        raise KnowledgeGatewayError(504, "FASTGPT_TIMEOUT", "FastGPT 文件导入超时") from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code in {401, 403}:
            raise KnowledgeGatewayError(401, "FASTGPT_UNAUTHORIZED", "FastGPT 鉴权失败或 API Key 无效") from exc
        raise KnowledgeGatewayError(502, "FASTGPT_UPSTREAM_ERROR", f"FastGPT API 返回 HTTP {status_code}") from exc
    except ValueError as exc:
        raise KnowledgeGatewayError(502, "FASTGPT_INVALID_RESPONSE", "FastGPT 返回了无法解析的响应") from exc


def extract_collection_id(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ["collectionId", "collection_id", "id", "_id"]:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            nested = extract_collection_id(value)
            if nested:
                return nested
    elif isinstance(payload, list):
        for item in payload:
            nested = extract_collection_id(item)
            if nested:
                return nested
    return None


async def request_fastgpt_json(
    *,
    settings: Settings,
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str | None]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.FASTGPT_API_KEY}",
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.FASTGPT_TIMEOUT_SECONDS)) as client:
            response = await client.request(
                method,
                f"{settings.FASTGPT_BASE_URL.rstrip('/')}{path}",
                headers=headers,
                json=json_body,
            )
        response.raise_for_status()
        payload = response.json()
        trace_id = response.headers.get("x-trace-id") or response.headers.get("x-request-id")
        if isinstance(payload, dict):
            return payload, trace_id
        return {"data": payload}, trace_id
    except httpx.ConnectError as exc:
        raise KnowledgeGatewayError(503, "FASTGPT_NOT_STARTED", "FastGPT 服务未启动或不可达") from exc
    except httpx.TimeoutException as exc:
        raise KnowledgeGatewayError(504, "FASTGPT_TIMEOUT", "FastGPT 调用超时") from exc
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code in {401, 403}:
            raise KnowledgeGatewayError(401, "FASTGPT_UNAUTHORIZED", "FastGPT 鉴权失败或 API Key 无效") from exc
        raise KnowledgeGatewayError(502, "FASTGPT_UPSTREAM_ERROR", f"FastGPT API 返回 HTTP {status_code}") from exc
    except ValueError as exc:
        raise KnowledgeGatewayError(502, "FASTGPT_INVALID_RESPONSE", "FastGPT 返回了无法解析的响应") from exc


def normalize_fastgpt_resources(payload: dict[str, Any], resource_type: str) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    for item in collect_resource_candidates(payload):
        resource_id = first_str(item, ["id", "_id", "appId", "datasetId"])
        if not resource_id:
            continue
        name = first_str(item, ["name", "title", "datasetName", "appName"]) or resource_id
        resources.append({
            "id": resource_id,
            "name": name,
            "resource_type": resource_type,
            "display_name": name,
        })
    return resources


def collect_resource_candidates(node: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if first_str(node, ["id", "_id", "appId", "datasetId"]):
            candidates.append(node)
        for key in ["data", "list", "items", "records", "apps", "datasets"]:
            value = node.get(key)
            if isinstance(value, (dict, list)):
                candidates.extend(collect_resource_candidates(value))
    elif isinstance(node, list):
        for item in node:
            candidates.extend(collect_resource_candidates(item))
    return candidates


def dedupe_fastgpt_resources(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for resource in resources:
        key = (resource["resource_type"], resource["id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(resource)
    return deduped


@router.get("/datasets/{dataset_id}/files")
async def list_dataset_files(
    dataset_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """列出 FastGPT 知识库中的文件（collection）。

    Verifies that the user is authorised to access the dataset's knowledge
    mapping before forwarding the request to FastGPT (Phase 4 security fix).
    """
    # ── Authorisation: user must have access to the dataset's mapping ──
    mappings = store.list_knowledge_mappings(user=current_user)["items"]
    authorized_ids = {m.get("fastgpt_dataset_id") for m in mappings if m.get("fastgpt_dataset_id")}
    if dataset_id not in authorized_ids:
        raise HTTPException(status_code=404, detail="dataset not found")

    settings = get_settings()
    if settings.FASTGPT_MODE != "real":
        return {"items": [], "total": 0}
    try:
        payload, _ = await request_fastgpt_json(
            settings=settings,
            method="POST",
            path="/core/dataset/collection/listV2",
            json_body={"datasetId": dataset_id, "offset": 0, "pageSize": 30},
        )
        raw = payload.get("data", {})
        items: list[dict[str, Any]] = []
        # Handle both dict-shaped and list-shaped FastGPT responses
        if isinstance(raw, list):
            raw_items = raw
            total = len(raw)
        elif isinstance(raw, dict):
            raw_items = raw.get("list") or raw.get("items") or raw.get("data") or []
            total = raw.get("total", len(raw_items))
        else:
            raw_items = []
            total = 0
        if isinstance(raw_items, list):
            for col in raw_items:
                if isinstance(col, dict):
                    items.append({
                        "collection_id": col.get("id", col.get("_id", "")),
                        "file_name": col.get("file_name", col.get("name", col.get("sourceName", ""))),
                        "status": col.get("status", "unknown"),
                        "chunk_size": col.get("chunkSize"),
                        "created_at": col.get("createTime", col.get("created_at")),
                    })
        return {"items": items, "total": total}
    except KnowledgeGatewayError:
        logger.warning("Failed to list collections for dataset %s", dataset_id, exc_info=True)
        return {"items": [], "total": 0}


@router.delete("/datasets/{dataset_id}/files/{file_id}",
               dependencies=[Depends(require_permission("kb:delete"))])
async def delete_dataset_file(
    dataset_id: str, file_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """删除 FastGPT 知识库中的文件（collection）。"""
    settings = get_settings()
    if settings.FASTGPT_MODE != "real":
        raise HTTPException(status_code=409, detail="请先启用 FastGPT real 模式")
    try:
        payload, _ = await request_fastgpt_json(
            settings=settings,
            method="DELETE",
            path=f"/core/dataset/collection/delete?id={file_id}",
        )
        # Also clean up local import records for this collection
        store.delete_knowledge_import_by_collection(file_id, user=current_user)
        return {"ok": True, "fastgpt_response": payload}
    except KnowledgeGatewayError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


def first_str(item: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
