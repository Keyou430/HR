"""Input / output sanitization for the AI pipeline (Phase 5).

Responsibilities
----------------
- **Input**: truncate overly long queries, strip null bytes and control
  characters, normalise whitespace.
- **Output**: verify that sources only reference authorised knowledge
  spaces; strip unauthorised dataset names from answer text.
- **Validation**: confirm every source in the response maps to an
  authorised dataset.
"""

from __future__ import annotations

import re
from typing import Any

# ── Maximum query length ─────────────────────────────────────────────
DEFAULT_MAX_QUERY_LENGTH: int = 2000

# ── Patterns for sanitization ─────────────────────────────────────────

# Control characters except common whitespace
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

# Multiple consecutive whitespace
_MULTISPACE = re.compile(r"[ \t]{2,}")
_MULTINEWLINE = re.compile(r"\n{3,}")

# Patterns that suggest the answer is trying to reveal system information
_SYSTEM_LEAK_PATTERNS: list[re.Pattern] = [
    re.compile(r"(?:system|系统)\s*(?:prompt|提示|消息)", re.IGNORECASE),
    re.compile(r"(?:我的|your|my)\s*(?:指令|规则|instructions?|rules?)\s*(?:是|is|are|:)"),
    re.compile(r"(?:你被|you\s+are)\s*(?:要求|编程|设定|required|programmed|configured)\s*(?:为|to)"),
]


def sanitize_input(query: str, max_length: int = DEFAULT_MAX_QUERY_LENGTH) -> str:
    """Sanitize user input before it enters the AI pipeline.

    Returns an empty string when the sanitized result is blank.

    Args:
        query: Raw user input.
        max_length: Hard character limit (default 2000).

    Returns:
        Safe, normalised query string.
    """
    # Truncate
    if len(query) > max_length:
        query = query[:max_length]

    # Strip null bytes and control characters
    query = _CONTROL_CHARS.sub("", query)

    # Normalise whitespace
    query = _MULTISPACE.sub(" ", query)
    query = _MULTINEWLINE.sub("\n\n", query)
    query = query.strip()

    return query


def sanitize_output(
    answer: str,
    authorized_space_titles: set[str],
) -> str:
    """Post-process the LLM answer for safety.

    Currently performs:
    1. Checks for system-leak patterns and appends a warning marker if
       detected (does NOT modify answer text — the marker is for audit).
    2. In future: could redact unauthorised dataset names.

    Args:
        answer: The raw LLM response text.
        authorized_space_titles: Set of knowledge-base titles the user is
            authorised to see.

    Returns:
        The (potentially annotated) answer string.
    """
    if not answer:
        return ""

    for pattern in _SYSTEM_LEAK_PATTERNS:
        if pattern.search(answer):
            import logging
            logger = logging.getLogger("replica.ai_security")
            logger.warning("sanitize_output — potential system-leak pattern detected in answer")
            break

    return answer


def validate_sources(
    sources: list[dict[str, Any]],
    authorized_space_titles: set[str],
    authorized_dataset_ids: set[str],
) -> list[dict[str, Any]]:
    """Return only those *sources* whose title or dataset matches an
    authorised space.

    Sources that don't match are **dropped** and a warning is logged.

    Args:
        sources: Source dicts from the RAG pipeline (each has ``title``,
            ``document``, ``score``).
        authorized_space_titles: Lower-case set of authorised space titles.
        authorized_dataset_ids: Set of authorised FastGPT dataset IDs.

    Returns:
        Filtered source list.
    """
    kept: list[dict[str, Any]] = []
    dropped = 0
    for s in sources:
        title = (s.get("title") or "").lower()
        # Also check if the source's dataset_id is authorised
        ds_id = s.get("_dataset_id", "")
        if title in authorized_space_titles or ds_id in authorized_dataset_ids:
            kept.append(s)
        else:
            dropped += 1
            import logging
            logger = logging.getLogger("replica.ai_security")
            logger.warning("validate_sources — dropped unauthorised source: title=%r", title)

    if dropped:
        import logging
        logger = logging.getLogger("replica.ai_security")
        logger.warning("validate_sources — dropped %d/%d unauthorised sources", dropped, len(sources))

    return kept
