"""Deterministic prompt-injection detection (Phase 5).

Uses regex patterns and keyword scoring — **not** an LLM call — so it is
fast, deterministic, and cannot be socially engineered at the model level.

.. warning::
   This is a defence-*in-depth* measure.  It must never be the sole
   authorization boundary.  RBAC + data scope are the primary controls.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ── Injection patterns ────────────────────────────────────────────────
# Each pattern is a (regex, weight) tuple.  Weights accumulate; a total
# score ≥ INJECTION_THRESHOLD triggers a PROMPT_INJECTION label.

_INJECTION_PATTERNS: list[tuple[re.Pattern, int]] = [
    # ── Direct instruction overrides ────────────────────────────────
    (re.compile(r"忽略\s*(?:之前|上述|所有|任何)的?\s*(?:规则|指令|限制|约束|提示)"), 5),
    (re.compile(r"ignore\s+(?:all\s+)?(?:previous|above|the)\s+(?:instructions?|rules?|constraints?|prompts?)", re.IGNORECASE), 5),
    (re.compile(r"forget\s+(?:everything|all|(?:all\s+)?previous|above|the)", re.IGNORECASE), 4),
    (re.compile(r"disregard\s+(?:all\s+)?(?:previous|above)", re.IGNORECASE), 4),
    (re.compile(r"忘记\s*(?:之前|所有|全部|一切)?\s*(?:的?\s*)?(?:规则|指令|限制|约束|对话|内容)", re.IGNORECASE), 5),
    (re.compile(r"忘掉\s*(?:之前|所有|全部|一切)?\s*(?:的?\s*)?(?:规则|指令|限制|约束|对话|内容)", re.IGNORECASE), 5),
    (re.compile(r"不要\s*(?:遵守|遵循|按照|理会)\s*(?:规则|指令|限制)", re.IGNORECASE), 4),

    # ── System prompt extraction attempts ──────────────────────────
    (re.compile(r"(?:system|系统)\s*(?:prompt|提示|指令|消息|message)"), 3),
    (re.compile(r"(?:输出|泄露|暴露|告诉我|打印|显示|print|output|reveal|leak|show)\s*(?:你?的?\s*)?(?:系统|原始|初始)?\s*(?:提示|指令|prompt|instructions?)"), 5),
    (re.compile(r"(?:what|tell\s+me|show\s+me)\s+(?:your|the)\s+(?:system\s+)?(?:prompt|instructions?)", re.IGNORECASE), 5),

    # ── Role-playing / persona injection ───────────────────────────
    (re.compile(r"(?:扮演|假装|现在你是|从现在开始你是|pretend|act\s+as|you\s+are\s+now)\s*(?:一个|一名|一位)?\s*(?:角色|CEO|管理员|admin|developer)"), 5),
    (re.compile(r"DAN\b|do\s+anything\s+now", re.IGNORECASE), 5),
    (re.compile(r"jailbreak|越狱", re.IGNORECASE), 5),

    # ── Encoding / obfuscation ─────────────────────────────────────
    (re.compile(r"base64\s*(?:编码|解码|输出|encode|decode|output)", re.IGNORECASE), 4),
    (re.compile(r"(?:用|使用|以|in)\s*(?:base64|十六进制|hex|morse|rot13)", re.IGNORECASE), 3),
    (re.compile(r"(?:绕过|bypass|circumvent)\s*(?:过滤|检测|审查|filter|detection|censor)", re.IGNORECASE), 4),

    # ── Data exfiltration attempts ─────────────────────────────────
    (re.compile(r"(?:列出|告诉我|有哪些|list|tell\s+me|what\s+are)\s*(?:所有|全部的?|the)?\s*(?:知识库|数据库|数据集|knowledge\s*base|dataset)", re.IGNORECASE), 5),
    (re.compile(r"(?:导出|下载|export|download)\s*(?:所有|全部|all)", re.IGNORECASE), 2),
    (re.compile(r"不要\s*(?:说|告诉|提及|提到)\s*(?:你|我).*?(?:知识库|检索|RAG)", re.IGNORECASE), 3),
    (re.compile(r"don'?t\s+(?:say|tell|mention)\s+(?:you|that\s+you).*?(?:knowledge|retriev|RAG)", re.IGNORECASE), 3),

    # ── Prompt-leak patterns ───────────────────────────────────────
    (re.compile(r"(?:你被|你的|you\s+are|your)\s*(?:设定|配置|编程|programming|configure)"), 3),
    (re.compile(r"(?:谁|who)\s*(?:创建|开发|制造|编程|created|developed|made|programmed)\s*(?:了你|你|you)", re.IGNORECASE), 2),
    (re.compile(r"(?:返回|回复|return|reply\s+with).*?(?:JSON|XML|format|格式)", re.IGNORECASE), 1),

    # ── Direct model-manipulation ──────────────────────────────────
    (re.compile(r"(?:你是一个|你是)[^。]*(?:大语言模型|语言模型|LLM|AI|人工智能)"), 2),
    (re.compile(r"(?:作为|as\s+an?)\s*(?:AI|语言模型|language\s+model)", re.IGNORECASE), 1),
]

# Score threshold above which a query is flagged as PROMPT_INJECTION.
INJECTION_THRESHOLD: int = 5


@dataclass
class InjectionResult:
    """Outcome of :func:`detect_injection`."""

    is_injection: bool = False
    score: int = 0
    matched_patterns: list[str] = field(default_factory=list)
    label: str = "GENERAL"


def detect_injection(query: str) -> InjectionResult:
    """Run all injection patterns against *query* and return a scored result.

    Args:
        query: The user's input text (already sanitised by :func:`sanitize_input`).

    Returns:
        An ``InjectionResult`` with ``is_injection=True`` when the cumulative
        pattern score meets or exceeds ``INJECTION_THRESHOLD``.
    """
    total = 0
    matched: list[str] = []
    for pattern, weight in _INJECTION_PATTERNS:
        if pattern.search(query):
            total += weight
            matched.append(pattern.pattern)

    is_inj = total >= INJECTION_THRESHOLD
    return InjectionResult(
        is_injection=is_inj,
        score=total,
        matched_patterns=matched,
        label="PROMPT_INJECTION" if is_inj else "GENERAL",
    )
