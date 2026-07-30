import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from config import Settings, get_settings
from hermes import HermesGatewayError, hermes_chat
from schemas import KnowledgeChatRequest, KnowledgeMappingUpdate
from store import store

logger = logging.getLogger("replica.knowledge")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(_handler)
    logger.propagate = False


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get("/spaces")
async def list_knowledge_spaces(
    search: str = "",
    filter: str = Query(default="all"),  # noqa: A002
) -> dict:
    return store.list_knowledge_spaces(search=search, filter_=filter)


@router.get("/mappings")
async def list_knowledge_mappings() -> dict[str, Any]:
    return store.list_knowledge_mappings()


@router.patch("/mappings/{mapping_id:path}")
async def update_knowledge_mapping(mapping_id: str, payload: KnowledgeMappingUpdate) -> dict[str, Any]:
    item = store.update_knowledge_mapping(mapping_id, payload.model_dump(exclude_unset=True))
    if item is None:
        raise HTTPException(status_code=404, detail="knowledge mapping not found")
    return item


@router.delete("/mappings/{mapping_id:path}")
async def delete_knowledge_mapping(mapping_id: str) -> dict[str, bool]:
    if not store.delete_knowledge_mapping(mapping_id):
        raise HTTPException(status_code=404, detail="knowledge mapping not found")
    return {"ok": True}


@router.get("/imports")
async def list_knowledge_imports() -> dict[str, Any]:
    return store.list_knowledge_imports()


@router.post("/sync")
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
        if 1 <= len(queries) <= 5:
            logger.info("Query split result: %r", queries)
            return queries[:3]
    except HermesGatewayError:
        logger.warning("Query split failed, using original question")
    return [question]


async def _classify_intent(settings: Settings, question: str) -> str:
    """调用 Hermes 判断问题是否需要检索知识库。返回 'retrieve' 或 'chat'。"""
    try:
        answer = await hermes_chat(
            settings=settings,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "判断用户问题类型，只回复一个词：\n"
                        "- retrieve：需要检索专业知识库（学术概念、制度分析、文献内容、理论推理等）\n"
                        "- chat：日常问题、操作指南、生活常识、闲聊问候等通用对话\n\n"
                        "只回复 retrieve 或 chat，不要任何其他文字。"
                    ),
                },
                {"role": "user", "content": question},
            ],
        )
        result = answer.strip().lower()
        if "retrieve" in result:
            return "retrieve"
        return "chat"
    except HermesGatewayError:
        logger.warning("Intent classification failed, defaulting to retrieve")
        return "retrieve"


async def _rag_pipeline(
    settings: Settings,
    question: str,
    enabled_spaces: list[dict[str, Any]],
    kb_names: str,
) -> dict[str, Any]:
    """执行完整的 RAG 检索+生成管线，返回 answer 和 sources。"""
    # Step 0: 查询拆分
    search_queries = await _build_search_queries(settings, question)
    logger.info("RAG step0 split — %d queries: %s", len(search_queries), search_queries)

    # Step 1: 多查询检索 + 去重
    seen_ids: set[str] = set()
    context_chunks: list[dict[str, Any]] = []
    for query in search_queries:
        for space in enabled_spaces:
            dataset_id = space.get("fastgpt_dataset_id")
            if not dataset_id:
                continue
            try:
                chunks = await search_fastgpt_dataset(
                    settings=settings,
                    dataset_id=dataset_id,
                    query=query,
                    top_k=10,
                    similarity=0.2,
                )
                new_count = 0
                for chunk in chunks:
                    chunk["_kb_title"] = space.get("title", dataset_id)
                    cid = chunk.get("id", chunk.get("q", "")[:32])
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        context_chunks.append(chunk)
                        new_count += 1
                logger.info(
                    "RAG step1 search — kb=%r query=%r hits=%d new=%d",
                    space.get("title"), query[:40], len(chunks), new_count,
                )
            except KnowledgeGatewayError:
                logger.warning("RAG step1 search FAILED — kb=%r", space.get("title"), exc_info=True)

    logger.info("RAG step1 done — total_chunks=%d", len(context_chunks))

    # Step 2: 构建上下文
    if context_chunks:
        context_blocks: list[str] = []
        for i, c in enumerate(context_chunks[:20], 1):
            source = c.get("sourceName", "未知文档")
            kb = c.get("_kb_title", "未知")
            text = c.get("q", "")
            context_blocks.append(
                f"### 片段 {i} [{kb} · {source}]\n{text}\n"
            )
        context_text = "\n".join(context_blocks)
        system_prompt = (
            f"你是知识库助手。请**仅基于**以下检索到的文档片段回答用户问题。\n\n"
            f"## 检索结果\n\n{context_text}\n\n"
            f"## 严格回答格式（必须遵守）\n\n"
            f"1. **引用文段**：从上述片段中挑选与问题直接相关的段落原文，逐条列出。每条标注「来源文档」。"
            f"不要概括、不要改写——必须引用片段中的原句。\n"
            f"2. **结论**：基于引用的文段，用1-2段给出你的分析结论。\n"
            f"3. **禁止**：不要写「缺少信息」「无法回答」「建议补充」等内容。"
            f"即使片段不完美匹配，也要基于现有内容给出最佳分析。"
        )
    else:
        system_prompt = (
            f"你是 Replica 协同门户的知识库助手。"
            f"当前可用的知识库包括：{kb_names}。"
            f"本次未检索到与问题直接相关的文档，请基于你的知识回答用户问题。"
        )

    # Step 3: 调用 LLM
    logger.info("RAG step3 llm — model=%s prompt_chars=%d", settings.HERMES_MODEL, len(system_prompt))
    try:
        answer = await hermes_chat(
            settings=settings,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
        )
        logger.info("RAG step3 done — answer_chars=%d", len(answer))
    except HermesGatewayError:
        logger.warning("RAG step3 llm FAILED — falling back", exc_info=True)
        if context_chunks:
            answer = (
                f"AI 服务暂时不可用。以下是从知识库检索到的相关内容摘要：\n\n"
                + "\n".join(
                    f"- [{c.get('_kb_title', '未知')}] {c.get('q', '')[:200]}..."
                    for c in context_chunks[:5]
                )
            )
        else:
            answer = f"已基于{kb_names}检索：{question}。建议先查看服务目录、制度手册和部门复盘材料。"

    return {
        "answer": answer,
        "sources": [
            {"title": c.get("_kb_title", ""), "document": c.get("sourceName", ""), "score": (c.get("score") or [{}])[0].get("value", 0) if c.get("score") else 0}
            for c in context_chunks[:10]
        ],
    }


@router.post("/chat")
async def knowledge_chat(payload: KnowledgeChatRequest) -> dict:
    settings = get_settings()
    spaces = store.list_knowledge_spaces(filter_=payload.scope)["items"]
    enabled_spaces = [s for s in spaces if s.get("enabled", True)]
    kb_names = "、".join(item["title"] for item in enabled_spaces[:5]) or "全部知识库"

    # 解析问题：支持 /rag 和 /chat 斜杠命令强制指定模式
    question = payload.question.strip()
    forced_mode: str | None = None
    for prefix in ("/rag ", "/RAG ", "/chat ", "/CHAT "):
        if question.startswith(prefix):
            forced_mode = "rag" if prefix.lower().startswith("/rag") else "chat"
            question = question[len(prefix):].strip()
            break

    # 确定运行模式
    if forced_mode:
        run_mode = forced_mode
    elif payload.mode in ("rag", "chat"):
        run_mode = payload.mode
    else:
        # auto: Hermes 智能判断
        run_mode = await _classify_intent(settings, question)

    logger.info(
        "knowledge_chat — mode=%s question=%r kb_count=%d",
        run_mode, question[:120], len(enabled_spaces),
    )

    # 分支：通用对话
    if run_mode == "chat":
        logger.info("CHAT mode — direct LLM call")
        try:
            answer = await hermes_chat(
                settings=settings,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是 Replica 协同门户的智能助手。请用中文回答用户问题，简洁、准确、有帮助。"
                            "如果是操作指南类问题，请给出分步骤说明。"
                        ),
                    },
                    {"role": "user", "content": question},
                ],
            )
        except HermesGatewayError:
            answer = "AI 服务暂时不可用，请稍后重试。"
        return {"answer": answer, "sources": [], "mode": "chat"}

    # 分支：RAG 检索增强
    result = await _rag_pipeline(settings, question, enabled_spaces, kb_names)
    result["mode"] = "rag"
    return result


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


@router.post("/import", status_code=status.HTTP_202_ACCEPTED)
async def import_knowledge_file(
    dataset_id: str = Form(min_length=1),
    file: UploadFile = File(),
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
async def list_dataset_files(dataset_id: str) -> dict[str, Any]:
    """列出 FastGPT 知识库中的文件（collection）。"""
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
        raw_items = raw.get("list") or raw.get("items") or raw.get("data") or []
        if isinstance(raw_items, list):
            for col in raw_items:
                items.append({
                    "collection_id": col.get("id", col.get("_id", "")),
                    "file_name": col.get("file_name", col.get("name", col.get("sourceName", ""))),
                    "status": col.get("status", "unknown"),
                    "chunk_size": col.get("chunkSize"),
                    "created_at": col.get("createTime", col.get("created_at")),
                })
        return {"items": items, "total": raw.get("total", len(items))}
    except KnowledgeGatewayError:
        logger.warning("Failed to list collections for dataset %s", dataset_id, exc_info=True)
        return {"items": [], "total": 0}


@router.delete("/datasets/{dataset_id}/files/{file_id}")
async def delete_dataset_file(dataset_id: str, file_id: str) -> dict[str, Any]:
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
        store.delete_knowledge_import_by_collection(file_id)
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
