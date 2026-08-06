"""AI Security Firewall — orchestrator for the Phase 5 pipeline.

Enforces the processing order mandated by rbac-design-v2.md §9.1::

    auth → kb:chat permission → data scope → risk classify →
    authorised retrieval → LLM generation → output check → audit

Key invariants
--------------
1. The risk classifier is **advisory** — authorization comes from RBAC + data scope.
2. No retrieval results → no free-form answering for non-GENERAL questions.
3. Users without ``kb:chat_sensitive`` cannot force ``chat`` mode.
4. All document chunks are marked as untrusted data in the prompt.
5. Output sources are validated against authorised knowledge spaces.
6. Audit logs contain only query_hash, snippet, risk_label, decision, resource count.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from authorization.scope import AccessContext, get_access_context
from ai_security.injection import detect_injection, InjectionResult
from ai_security.classifier import (
    classify_risk,
    RISK_LABEL_GENERAL,
    RISK_LABEL_PROMPT_INJECTION,
    describe_risk,
)
from ai_security.retrieval_policy import (
    get_authorized_spaces,
    filter_authorized_chunks,
    build_safe_prompt,
    MAX_CHUNKS_IN_PROMPT,
)
from ai_security.sanitizer import (
    sanitize_input,
    sanitize_output,
    validate_sources,
    DEFAULT_MAX_QUERY_LENGTH,
)

logger = logging.getLogger("replica.ai_security.firewall")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(_h)
    logger.propagate = False

# ── Audit logger (structured, no sensitive data) ────────────────────
_audit_logger = logging.getLogger("replica.ai_security.audit")
_audit_logger.setLevel(logging.INFO)
if not _audit_logger.handlers:
    _ah = logging.StreamHandler()
    _ah.setFormatter(logging.Formatter("%(asctime)s [AUDIT] %(message)s", datefmt="%H:%M:%S"))
    _audit_logger.addHandler(_ah)
    _audit_logger.propagate = False

# ── Policy version (bumped when rules change) ────────────────────────
POLICY_VERSION: str = "2.0.0"


@dataclass
class FirewallResult:
    """Output of :func:`ai_security_pipeline`."""

    decision: str  # "allowed" | "blocked" | "degraded"
    answer: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "rag"
    risk_label: str = RISK_LABEL_GENERAL
    blocked_reason: str = ""
    accessible_resource_count: int = 0


# ═════════════════════════════════════════════════════════════════════
# Main entry point
# ═════════════════════════════════════════════════════════════════════


async def ai_security_pipeline(
    *,
    settings: Any,
    user: dict[str, Any],
    db: Any,  # sqlalchemy.orm.Session
    question: str,
    mode: str,  # "auto" | "rag" | "chat"
    scope: str,  # "all" | "dataset" | "app" | ...
    session_id: str | None,
    store: Any,
    history: list[dict[str, str]] | None = None,
    hermes_chat_fn: Any = None,
    search_fastgpt_fn: Any = None,
) -> FirewallResult:
    """Run the complete AI security pipeline.

    Args:
        settings: Application settings (config.Settings).
        user: Authenticated user dict from ``get_current_user``.
        db: SQLAlchemy Session for building AccessContext.
        question: Raw user input.
        mode: Requested mode (``"auto"``, ``"rag"``, ``"chat"``).
        scope: Knowledge-space scope filter.
        session_id: Chat session ID (for audit correlation).
        store: The application store instance.
        history: Prior conversation turns.
        hermes_chat_fn: Async callable for Hermes (injected for testability).
        search_fastgpt_fn: Async callable for FastGPT search (injected for testability).

    Returns:
        A :class:`FirewallResult` ready to return to the client.
    """
    t_start = time.monotonic()

    # ── Resolve dependencies ───────────────────────────────────────
    if hermes_chat_fn is None:
        from hermes import hermes_chat as _hc
        hermes_chat_fn = _hc
    if search_fastgpt_fn is None:
        from knowledge import search_fastgpt_dataset as _sds
        search_fastgpt_fn = _sds

    history = history or []

    # ═════════════════════════════════════════════════════════════
    # Step 1: Sanitize input
    # ═════════════════════════════════════════════════════════════
    max_len = getattr(settings, "AI_SECURITY_MAX_QUERY_LENGTH", DEFAULT_MAX_QUERY_LENGTH)
    question = sanitize_input(question, max_len)
    if not question:
        return FirewallResult(
            decision="blocked",
            answer="请输入有效的问题。",
            blocked_reason="empty_query",
        )

    # ═════════════════════════════════════════════════════════════
    # Step 2: Injection detection
    # ═════════════════════════════════════════════════════════════
    inj_result = detect_injection(question)
    if inj_result.is_injection:
        _write_audit(
            user=user,
            question=question,
            risk_label=RISK_LABEL_PROMPT_INJECTION,
            decision="blocked",
            blocked_reason=f"prompt_injection score={inj_result.score}",
            response_time_ms=int((time.monotonic() - t_start) * 1000),
            settings=settings,
            db=db,
        )
        logger.warning(
            "Prompt injection detected — score=%d patterns=%s",
            inj_result.score, inj_result.matched_patterns,
        )
        return FirewallResult(
            decision="blocked",
            answer="抱歉，您的输入包含不被允许的指令模式。请重新描述您的问题。",
            risk_label=RISK_LABEL_PROMPT_INJECTION,
            blocked_reason="prompt_injection",
        )

    # ═════════════════════════════════════════════════════════════
    # Step 3: Build AccessContext
    # ═════════════════════════════════════════════════════════════
    ctx = get_access_context(user, db)

    # ═════════════════════════════════════════════════════════════
    # Step 4: Get authorised knowledge spaces
    # ═════════════════════════════════════════════════════════════
    spaces = store.list_knowledge_spaces(filter_=scope, user=user)["items"]
    enabled_spaces = [s for s in spaces if s.get("enabled", True)]
    authorized_spaces = get_authorized_spaces(enabled_spaces, ctx)

    if not authorized_spaces:
        _write_audit(
            user=user,
            question=question,
            risk_label=RISK_LABEL_GENERAL,
            decision="blocked",
            blocked_reason="no_authorized_knowledge_base",
            accessible_resource_count=0,
            response_time_ms=int((time.monotonic() - t_start) * 1000),
            settings=settings,
            db=db,
        )
        return FirewallResult(
            decision="blocked",
            answer="抱歉，您当前没有可访问的知识库。请联系管理员开通权限。",
            blocked_reason="no_authorized_knowledge_base",
        )

    auth_dataset_ids: set[str] = {
        s["fastgpt_dataset_id"]
        for s in authorized_spaces
        if s.get("fastgpt_dataset_id")
    }

    # ═════════════════════════════════════════════════════════════
    # Step 5: Risk classification (advisory)
    # ═════════════════════════════════════════════════════════════
    user_dept_name = user.get("default_dept_name") or ""
    risk_label = classify_risk(
        question,
        user_dept_name=user_dept_name,
        injection_label=inj_result.label,
    )
    logger.info(
        "Risk classified — user=%r label=%s desc=%r",
        user.get("username"), risk_label, describe_risk(risk_label),
    )

    # ═════════════════════════════════════════════════════════════
    # Step 6: Resolve effective mode
    # ═════════════════════════════════════════════════════════════
    user_has_sensitive = ctx.has_sensitive_access()
    effective_mode = _resolve_mode(
        requested_mode=mode,
        risk_label=risk_label,
        user_has_sensitive=user_has_sensitive,
    )
    logger.info(
        "Mode resolved — requested=%s effective=%s risk=%s has_sensitive=%s",
        mode, effective_mode, risk_label, user_has_sensitive,
    )

    # ═════════════════════════════════════════════════════════════
    # Step 7: Execute (RAG or chat)
    # ═════════════════════════════════════════════════════════════
    answer: str
    sources: list[dict[str, Any]]
    was_blocked_by_retrieval: bool = False

    if effective_mode == "rag":
        answer, sources = await _execute_rag(
            settings=settings,
            question=question,
            authorized_spaces=authorized_spaces,
            auth_dataset_ids=auth_dataset_ids,
            risk_label=risk_label,
            history=history,
            hermes_chat_fn=hermes_chat_fn,
            search_fastgpt_fn=search_fastgpt_fn,
        )
        # Detect if _execute_rag returned a safe-rejection (no authorised
        # chunks for a non-GENERAL query) — mark for audit accuracy.
        if not sources and answer and (
            "未找到" in answer or "未检索到" in answer
        ):
            was_blocked_by_retrieval = True
    else:
        answer, sources = await _execute_chat(
            settings=settings,
            question=question,
            history=history,
            hermes_chat_fn=hermes_chat_fn,
        )

    # ═════════════════════════════════════════════════════════════
    # Step 8: Output sanitization
    # ═════════════════════════════════════════════════════════════
    authorized_titles: set[str] = {
        (s.get("title") or "").lower() for s in authorized_spaces
    }
    safe_answer = sanitize_output(answer, authorized_titles)
    safe_sources = validate_sources(sources, authorized_titles, auth_dataset_ids)

    # ═════════════════════════════════════════════════════════════
    # Step 9: Audit
    # ═════════════════════════════════════════════════════════════
    elapsed_ms = int((time.monotonic() - t_start) * 1000)
    _write_audit(
        user=user,
        question=question,
        risk_label=risk_label,
        decision="blocked" if was_blocked_by_retrieval else "allowed",
        blocked_reason="no_authorized_retrieval_results" if was_blocked_by_retrieval else "",
        accessible_resource_count=len(authorized_spaces),
        response_time_ms=elapsed_ms,
        settings=settings,
        db=db,
    )

    return FirewallResult(
        decision="allowed",
        answer=safe_answer,
        sources=safe_sources,
        mode=effective_mode,
        risk_label=risk_label,
        accessible_resource_count=len(authorized_spaces),
    )


# ═════════════════════════════════════════════════════════════════════
# Internal helpers
# ═════════════════════════════════════════════════════════════════════


def _resolve_mode(
    requested_mode: str,
    risk_label: str,
    user_has_sensitive: bool,
) -> str:
    """Determine the effective execution mode.

    Rules (from rbac-design-v2.md §9.2):
    1. Users **without** ``kb:chat_sensitive`` cannot force ``chat`` mode.
       Their ``/chat``, ``mode=chat`` requests are overridden to ``rag``.
    2. Users **with** ``kb:chat_sensitive`` can use any mode.
    3. ``auto`` mode always defers to RAG for non-GENERAL queries.
    4. PROMPT_INJECTION is already blocked before reaching here.
    """
    is_chat_request = requested_mode in ("chat",)
    is_rag_request = requested_mode in ("rag",)

    if is_chat_request and not user_has_sensitive:
        logger.info("_resolve_mode — overriding chat→rag (user lacks kb:chat_sensitive)")
        return "rag"

    if is_rag_request:
        return "rag"

    if is_chat_request:
        # User has kb:chat_sensitive — allow chat mode
        return "chat"

    # auto mode
    if risk_label == RISK_LABEL_GENERAL:
        return "chat"
    return "rag"


async def _execute_rag(
    *,
    settings: Any,
    question: str,
    authorized_spaces: list[dict[str, Any]],
    auth_dataset_ids: set[str],
    risk_label: str,
    history: list[dict[str, str]],
    hermes_chat_fn: Any,
    search_fastgpt_fn: Any,
) -> tuple[str, list[dict[str, Any]]]:
    """Execute the RAG retrieval + generation pipeline."""
    from knowledge import _build_search_queries as build_queries

    # ── Query splitting ─────────────────────────────────────────
    search_queries = await build_queries(settings, question)
    logger.info("RAG queries — %d: %s", len(search_queries), search_queries)

    # ── Multi-query retrieval with dedup ────────────────────────
    seen_ids: set[str] = set()
    raw_chunks: list[dict[str, Any]] = []
    for query in search_queries:
        for space in authorized_spaces:
            dataset_id = space.get("fastgpt_dataset_id")
            if not dataset_id:
                continue
            try:
                chunks = await search_fastgpt_fn(
                    settings=settings,
                    dataset_id=dataset_id,
                    query=query,
                    top_k=10,
                    similarity=0.2,
                )
                for chunk in chunks:
                    chunk["_kb_title"] = space.get("title", dataset_id)
                    chunk["_dataset_id"] = dataset_id
                    cid = chunk.get("id", chunk.get("q", "")[:32])
                    if cid not in seen_ids:
                        seen_ids.add(cid)
                        raw_chunks.append(chunk)
            except Exception:
                logger.warning(
                    "RAG search FAILED — kb=%r", space.get("title"), exc_info=True,
                )

    logger.info("RAG retrieval — raw_chunks=%d", len(raw_chunks))

    # ── Post-retrieval chunk filtering ──────────────────────────
    authorized_chunks = filter_authorized_chunks(raw_chunks, auth_dataset_ids)
    logger.info(
        "RAG chunk filter — authorized=%d dropped=%d",
        len(authorized_chunks), len(raw_chunks) - len(authorized_chunks),
    )

    # ── No-chunks decision ──────────────────────────────────────
    if not authorized_chunks:
        if risk_label == RISK_LABEL_GENERAL:
            # General question, no chunks — use generic system prompt
            system_prompt = (
                "你是 Replica 协同门户的智能助手。请用中文回答用户问题，简洁、准确、有帮助。"
                "如果是操作指南类问题，请给出分步骤说明。"
            )
        else:
            # Internal business question with no authorised results → block
            logger.warning(
                "_execute_rag — blocking non-GENERAL query with no results; risk=%s",
                risk_label,
            )
            return (
                "抱歉，当前授权知识库中未找到与该问题相关的信息。"
                "建议联系知识库管理员补充相关资料，或尝试用不同的关键词搜索。",
                [],
            )
    else:
        system_prompt = build_safe_prompt(question, authorized_chunks, authorized_spaces)

    # ── LLM call ────────────────────────────────────────────────
    try:
        answer = await hermes_chat_fn(
            settings=settings,
            messages=[
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": question},
            ],
        )
    except Exception:
        logger.warning("RAG LLM call FAILED", exc_info=True)
        if authorized_chunks:
            answer = (
                "AI 服务暂时不可用。以下是从授权知识库检索到的相关内容摘要：\n\n"
                + "\n".join(
                    f"- [{c.get('_kb_title', '未知')}] {c.get('q', '')[:200]}..."
                    for c in authorized_chunks[:5]
                )
            )
        else:
            answer = "AI 服务暂时不可用，请稍后重试。"

    # ── Build sources ───────────────────────────────────────────
    sources: list[dict[str, Any]] = []
    for c in authorized_chunks[:10]:
        sources.append({
            "title": c.get("_kb_title", ""),
            "document": c.get("sourceName", ""),
            "score": _extract_score(c.get("score")),
        })

    return answer, sources


async def _execute_chat(
    *,
    settings: Any,
    question: str,
    history: list[dict[str, str]],
    hermes_chat_fn: Any,
) -> tuple[str, list[dict[str, Any]]]:
    """Execute a direct-chat (non-RAG) LLM call."""
    system_prompt = (
        "你是 Replica 协同门户的智能助手。请用中文回答用户问题，简洁、准确、有帮助。"
        "如果是操作指南类问题，请给出分步骤说明。"
        "你可以看到完整的对话历史，请基于上下文连贯地回答。\n\n"
        "## 重要约束\n"
        "1. 对于涉及本组织内部业务（制度、人事、薪资、财务、战略、绩效）的问题，"
        "如果你没有从授权数据源获取信息，**必须**明确告知用户你无法确认该信息，"
        "而不是凭空编造或基于训练数据猜测。\n"
        "2. 如果用户询问的是通用知识（技术概念、行业标准、公共信息），可以正常回答。\n"
        "3. **禁止**编造具体的内部业务数据、数字、人名、部门名或政策细节。"
    )
    try:
        answer = await hermes_chat_fn(
            settings=settings,
            messages=[
                {"role": "system", "content": system_prompt},
                *history,
                {"role": "user", "content": question},
            ],
        )
    except Exception:
        logger.warning("Chat LLM call FAILED", exc_info=True)
        answer = "AI 服务暂时不可用，请稍后重试。"

    return answer, []


def _extract_score(score: Any) -> float:
    """Safe score extraction from FastGPT response (copied from knowledge.py)."""
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


def _write_audit(
    *,
    user: dict[str, Any],
    question: str,
    risk_label: str,
    decision: str,
    blocked_reason: str = "",
    accessible_resource_count: int = 0,
    response_time_ms: int = 0,
    settings: Any = None,
    db: Any = None,
) -> None:
    """Write a structured AI audit log entry.

    **Never** records the full query or full response — only a hash and
    a truncated snippet (per rbac-design-v2.md §6.3).

    Writes to both the application log (structured JSON via stdlib logging)
    and the ``ai_query_logs`` database table (via ``AuditLogger.record_ai_query``).
    """
    import json

    query_hash = hashlib.sha256(question.encode("utf-8")).hexdigest()[:64]
    snippet_len = getattr(settings, "AI_SECURITY_LOG_SNIPPET_LENGTH", 256) if settings else 256
    snippet = question[:snippet_len] if len(question) > snippet_len else question

    record = {
        "query_hash": query_hash,
        "query_snippet": snippet,
        "risk_label": risk_label,
        "policy_version": POLICY_VERSION,
        "decision": decision,
        "blocked_reason": blocked_reason,
        "user_id": user.get("id"),
        "username": user.get("username"),
        "org_id": user.get("default_org_id"),
        "accessible_resource_count": accessible_resource_count,
        "response_time_ms": response_time_ms,
    }
    _audit_logger.info(json.dumps(record, ensure_ascii=False))

    # ── Persist to ai_query_logs database table ──────────────────
    if db is not None:
        import uuid
        try:
            from audit.logger import audit_logger as _db_audit

            _db_audit.record_ai_query(
                db,
                request_id=uuid.uuid4().hex[:16],
                user_id=user.get("id") or 0,
                org_id=user.get("default_org_id"),
                department_id=user.get("default_dept_id"),
                query_hash=query_hash,
                query_snippet=snippet,
                risk_label=risk_label,
                policy_version=POLICY_VERSION,
                decision=decision,
                blocked_reason=blocked_reason,
                accessible_resource_count=accessible_resource_count,
                response_time_ms=response_time_ms,
            )
        except Exception:
            logger.warning(
                "Failed to persist AI query audit to DB — user_id=%s decision=%s",
                user.get("id"), decision, exc_info=True,
            )
