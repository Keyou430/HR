"""Risk classifier for AI queries (Phase 5).

Labels every query with one of the standard risk labels using keyword
heuristics.  The classifier is **advisory only** — it never serves as
the sole authorization decision.  RBAC + data-scope filters are the
primary access controls.

Risk labels (from rbac-design-v2.md §9.1):
    GENERAL
    PERSONNEL_SENSITIVE
    FINANCIAL_SENSITIVE
    STRATEGIC_SENSITIVE
    CROSS_DEPT
    PROMPT_INJECTION
"""

from __future__ import annotations

import re
from typing import Any

# ── Risk label constants ──────────────────────────────────────────────

RISK_LABEL_GENERAL = "GENERAL"
RISK_LABEL_PERSONNEL_SENSITIVE = "PERSONNEL_SENSITIVE"
RISK_LABEL_FINANCIAL_SENSITIVE = "FINANCIAL_SENSITIVE"
RISK_LABEL_STRATEGIC_SENSITIVE = "STRATEGIC_SENSITIVE"
RISK_LABEL_CROSS_DEPT = "CROSS_DEPT"
RISK_LABEL_PROMPT_INJECTION = "PROMPT_INJECTION"

# ── Keyword tables ────────────────────────────────────────────────────
# Each label is associated with a list of (keyword, weight) pairs.
# Weights allow fine-tuning: a single mention of "salary" might be
# incidental, but "salary" + "all employees" is a stronger signal.

_KEYWORD_TABLES: dict[str, list[tuple[str, int]]] = {
    RISK_LABEL_PERSONNEL_SENSITIVE: [
        ("薪资", 4), ("工资", 4), ("薪酬", 4), ("薪水", 4),
        ("salary", 3), ("compensation", 3), ("payroll", 4),
        ("奖金", 3), ("bonus", 3),
        ("绩效", 3), ("考核", 3), ("performance review", 3),
        ("人事", 2), ("HR", 2),
        ("晋升", 3), ("开除", 3), ("解雇", 3), ("裁员", 4),
        ("招聘", 1), ("面试", 1),
        ("全组织", 2), ("全公司", 2), ("所有人", 2), ("all employees", 2),
    ],
    RISK_LABEL_FINANCIAL_SENSITIVE: [
        ("财务", 4), ("预算", 4), ("budget", 4),
        ("收入", 3), ("利润", 3), ("成本", 3), ("亏损", 3),
        ("revenue", 3), ("profit", 3), ("cost", 3),
        ("税务", 4), ("审计", 3), ("audit", 3),
        ("发票", 2), ("报销", 2),
        ("投标", 3), ("采购", 2), ("合同", 2),
        ("现金流", 4), ("cash flow", 4),
        ("财务报表", 4), ("financial statement", 4),
    ],
    RISK_LABEL_STRATEGIC_SENSITIVE: [
        ("战略", 4), ("strategy", 4),
        ("收购", 5), ("合并", 5), ("merger", 5), ("acquisition", 5),
        ("上市", 5), ("IPO", 5),
        ("融资", 4), ("funding", 4), ("股权", 4), ("equity", 4),
        ("商业模式", 3), ("business model", 3),
        ("竞品", 3), ("竞争对手", 3), ("competitor", 3),
        ("专利", 3), ("patent", 3),
        ("市场份额", 3), ("market share", 3),
    ],
}

# ── Cross-department detection ────────────────────────────────────────
# Matches patterns like "X部门" or "X dept" that differ from the user's
# own department name.

_CROSS_DEPT_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:其他|别的|隔壁|other|different)\s*(?:部门|团队|组|department|team)"),
    re.compile(r"(?:部门|department)\s*(?:[A-Za-z]{2,}|\S{2,})"),
    re.compile(r"(?:跨|cross[\s-])(?:部门|团队|组|department|team|org)"),
]

# Risk threshold: score ≥ this value assigns the label.
RISK_THRESHOLD: int = 4


def classify_risk(
    query: str,
    user_dept_name: str | None = None,
    injection_label: str | None = None,
) -> str:
    """Classify *query* into one of the standard risk labels.

    Args:
        query: Sanitised user input.
        user_dept_name: The user's department name (for CROSS_DEPT detection).
        injection_label: Pre-computed injection label from
            :func:`~ai_security.injection.detect_injection`.  If
            ``"PROMPT_INJECTION"``, it is returned immediately.

    Returns:
        One of the ``RISK_LABEL_*`` constants.  Returns ``RISK_LABEL_GENERAL``
        when no elevated risk is detected.
    """
    # Injection takes priority — if injection detection already flagged
    # this query, return immediately.
    if injection_label == RISK_LABEL_PROMPT_INJECTION:
        return RISK_LABEL_PROMPT_INJECTION

    scores: dict[str, int] = {}

    # ── Keyword scoring ────────────────────────────────────────────
    query_lower = query.lower()
    for label, keywords in _KEYWORD_TABLES.items():
        total = 0
        for kw, weight in keywords:
            if kw.lower() in query_lower:
                total += weight
        if total > 0:
            scores[label] = total

    # ── Cross-department detection ─────────────────────────────────
    if user_dept_name:
        for pattern in _CROSS_DEPT_PATTERNS:
            if pattern.search(query):
                scores[RISK_LABEL_CROSS_DEPT] = scores.get(RISK_LABEL_CROSS_DEPT, 0) + 3
                break

        # Also flag if the query mentions a department name different from
        # the user's own.  Matches "XX部" or "XX部门" and extracts XX.
        dept_mention_pattern = re.compile(r"(\S{2,10})(?:部门|部(?!门))")
        for m in dept_mention_pattern.finditer(query):
            mentioned = m.group(1)
            if mentioned and mentioned not in (user_dept_name, "所有", "全部", "all"):
                # Also compare against user's dept name stripped of 部/部门 suffix
                user_dept_base = re.sub(r"(?:部门|部)$", "", user_dept_name or "")
                if mentioned != user_dept_base:
                    scores[RISK_LABEL_CROSS_DEPT] = scores.get(RISK_LABEL_CROSS_DEPT, 0) + 10
                    break

    # ── Determine highest-risk label ───────────────────────────────
    if not scores:
        return RISK_LABEL_GENERAL

    best_label = max(scores, key=lambda k: scores[k])
    if scores[best_label] >= RISK_THRESHOLD:
        return best_label

    return RISK_LABEL_GENERAL


def describe_risk(label: str) -> str:
    """Return a human-readable description of a risk label."""
    return {
        RISK_LABEL_GENERAL: "一般查询",
        RISK_LABEL_PERSONNEL_SENSITIVE: "涉及人事/薪酬敏感信息",
        RISK_LABEL_FINANCIAL_SENSITIVE: "涉及财务敏感信息",
        RISK_LABEL_STRATEGIC_SENSITIVE: "涉及战略敏感信息",
        RISK_LABEL_CROSS_DEPT: "跨部门查询",
        RISK_LABEL_PROMPT_INJECTION: "提示注入尝试",
    }.get(label, "未知风险标签")
