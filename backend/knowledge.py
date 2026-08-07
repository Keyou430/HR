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
from gateway_errors import GatewayError, map_httpx_errors
from hermes import HermesGatewayError, hermes_chat
from schemas import KnowledgeChatRequest, KnowledgeMappingUpdate
from session import get_db
from store import store

# Backward-compatible alias — prefer GatewayError for new code
KnowledgeGatewayError = GatewayError

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
    """灏嗗鏉傞棶棰樻媶鍒嗕负 2-3 涓嫭绔嬫悳绱㈡煡璇紝瑕嗙洊闂鐨勪笉鍚屾柟闈€傜煭闂鐩存帴杩斿洖鍘熸枃銆?""
    if len(question) <= 40:
        return [question]
    try:
        answer = await hermes_chat(
            settings=settings,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "灏嗙敤鎴烽棶棰樻媶鍒嗕负2-3涓嫭绔嬬殑鎼滅储鏌ヨ锛屾瘡涓煡璇㈣仛鐒﹂棶棰樼殑涓€涓牳蹇冩蹇垫垨鏂归潰銆?
                        "瑙勫垯锛氭瘡琛屼竴涓煡璇紝鐢ㄦ崲琛屽垎闅旓紝涓嶈缂栧彿銆佷笉瑕佽В閲娿€佷笉瑕佷换浣曞叾浠栨枃瀛椼€?
                        "姣忎釜鏌ヨ搴旂畝娲侊紙5-15瀛楋級锛屼娇鐢ㄩ棶棰樹腑鐨勫叧閿湳璇€?
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
    """浠?FastGPT 杩斿洖鐨?score 瀛楁涓畨鍏ㄦ彁鍙栫浉浼煎害鏁板€笺€?

    FastGPT 涓嶅悓鐗堟湰鍙兘杩斿洖: 瑁?float (0.85)銆乴ist ([{"value": 0.85}])銆佹垨 None銆?
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
    """鍔犺浇鏈€杩戠殑瀵硅瘽鍘嗗彶锛岃浆鎹负 Hermes API 娑堟伅鏍煎紡銆傜浉閭婚噸澶嶆秷鎭幓閲嶃€?

    When *user* is provided the store enforces session ownership 鈥?only the
    session owner can load the history (Phase 4 security fix).
    """
    if not session_id:
        return []
    try:
        data = store.get_chat_messages(session_id, limit=max_messages, user=user)
        messages = data.get("items", [])
        if not messages:
            return []
        # store 宸茬粡鎸?id DESC + LIMIT 杩斿洖鏈€杩?N 鏉★紙鍗囧簭鎺掑垪锛?
        recent = messages
        history: list[dict[str, str]] = []
        prev_content = ""
        for m in recent:
            if m.get("role") not in ("user", "assistant"):
                continue
            content = m["content"]
            # 璺宠繃鐩搁偦閲嶅锛堜慨澶嶆湡闂村彲鑳戒骇鐢熺殑鍙屼唤鏁版嵁锛?
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
    """鍦ㄦ湇鍔＄淇濆瓨涓€杞璇濓紙鐢ㄦ埛闂 + 鍔╂墜鍥炵瓟锛夈€傚悓姝ュ啓鍏ワ紝纭繚涓嬩竴杞姹傝兘鍔犺浇鍒板巻鍙层€?

    When *user_id* is provided the store enforces session ownership 鈥?only the
    session owner can write messages (Phase 4 security fix).
    """
    if not session_id:
        return
    try:
        store.save_chat_message(session_id, "user", question, action=action, user_id=user_id)
        store.save_chat_message(session_id, "assistant", answer, action=action, user_id=user_id)
    except Exception:
        logger.warning("Failed to save chat turn for session %s", session_id, exc_info=True)
        # 鎸佷箙鍖栧け璐ヤ笉褰卞搷瀵硅瘽鍔熻兘


@router.post("/chat", dependencies=[Depends(require_permission("kb:chat"))])
async def knowledge_chat(
    payload: KnowledgeChatRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    settings = get_settings()

    # 鈹€鈹€ 瑙ｆ瀽闂锛氭敮鎸?/rag 鍜?/chat 鏂滄潬鍛戒护寮哄埗鎸囧畾妯″紡 鈹€鈹€
    question = payload.question.strip()
    forced_mode: str | None = None
    for prefix in ("/rag", "/RAG", "/chat", "/CHAT"):
        if question == prefix or question.startswith(prefix + " "):
            forced_mode = "rag" if prefix.lower() == "/rag" else "chat"
            question = question[len(prefix):].strip()
            break

    # 鈹€鈹€ 鎸囦护妯″紡锛氬皾璇曡瘑鍒苟鎵ц鎿嶄綔鎸囦护 鈹€鈹€
    # 闀挎枃鏈紙>200瀛楋級鍑犱箮涓嶅彲鑳芥槸鎿嶄綔鎸囦护锛岃烦杩囧垎绫讳互鑺傜渷 LLM 璋冪敤骞堕伩鍏嶈鍒?
    if payload.command_mode and not forced_mode:
        if len(question) <= 200:
            cmd = await classify_command(settings, question)
            if cmd.get("action") not in ("chat", None, ""):
                logger.info(
                    "knowledge_chat 鈥?COMMAND mode action=%s params=%s",
                    cmd.get("action"), cmd.get("params"),
                )
                result = execute_command(cmd)
                _save_chat_turn(payload.session_id, question, result["answer"], result.get("action"),
                                user_id=current_user["id"])
                return result
        else:
            logger.info("knowledge_chat 鈥?skipping command classification: question too long (%d chars)", len(question))

    # 鈹€鈹€ 鍔犺浇瀵硅瘽鍘嗗彶涓婁笅鏂囷紙浼犲叆 current_user 浠ュ己鍒朵細璇濇墍鏈夋潈妫€鏌ワ級鈹€鈹€
    history = _load_chat_history(payload.session_id, user=current_user)

    # 鈹€鈹€ 纭畾璇锋眰妯″紡 鈹€鈹€
    if forced_mode:
        requested_mode = forced_mode
    elif payload.mode in ("rag", "chat"):
        requested_mode = payload.mode
    else:
        requested_mode = "auto"

    logger.info(
        "knowledge_chat 鈥?mode=%s question=%r",
        requested_mode, question[:120],
    )

    # 鈹€鈹€ Phase 5: AI 瀹夊叏闃茬伀澧欑绾?鈹€鈹€
    # 澶勭悊椤哄簭: 璁よ瘉 鈫?kb:chat 鏉冮檺 鈫?鏁版嵁鑼冨洿 鈫?椋庨櫓鍒嗙被 鈫?鎺堟潈妫€绱?鈫?LLM 鐢熸垚 鈫?杈撳嚭妫€鏌?鈫?瀹¤
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
    """璋冪敤 FastGPT searchTest API 妫€绱㈡暟鎹泦涓殑鐩稿叧鏂囨。鐗囨銆?""
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
        raise HTTPException(status_code=422, detail="涓婁紶鏂囦欢涓嶈兘涓虹┖")

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


async def list_fastgpt_resources(settings: Settings) -> list[dict[str, Any]]:
    if settings.FASTGPT_MODE != "real":
        raise KnowledgeGatewayError(409, "FASTGPT_REAL_MODE_REQUIRED", "璇峰厛鍚敤 FastGPT real 妯″紡")
    if not settings.FASTGPT_API_KEY:
        raise KnowledgeGatewayError(409, "FASTGPT_NOT_CONFIGURED", "FastGPT API Key 鏈厤缃?)

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
        raise KnowledgeGatewayError(409, "FASTGPT_REAL_MODE_REQUIRED", "璇峰厛鍚敤 FastGPT real 妯″紡")
    if not settings.FASTGPT_API_KEY:
        raise KnowledgeGatewayError(409, "FASTGPT_NOT_CONFIGURED", "FastGPT API Key 鏈厤缃?)

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
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError) as exc:
        raise map_httpx_errors(exc, "FASTGPT", "FastGPT") from exc


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
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError) as exc:
        raise map_httpx_errors(exc, "FASTGPT", "FastGPT") from exc


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
    """鍒楀嚭 FastGPT 鐭ヨ瘑搴撲腑鐨勬枃浠讹紙collection锛夈€?

    Verifies that the user is authorised to access the dataset's knowledge
    mapping before forwarding the request to FastGPT (Phase 4 security fix).
    """
    # 鈹€鈹€ Authorisation: user must have access to the dataset's mapping 鈹€鈹€
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
    """鍒犻櫎 FastGPT 鐭ヨ瘑搴撲腑鐨勬枃浠讹紙collection锛夈€?""
    settings = get_settings()
    if settings.FASTGPT_MODE != "real":
        raise HTTPException(status_code=409, detail="璇峰厛鍚敤 FastGPT real 妯″紡")
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
