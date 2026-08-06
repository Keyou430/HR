"""AI Security Layer (Phase 5).

Provides defence-in-depth for the Hermes + FastGPT RAG pipeline:

1. **injection** — deterministic prompt-injection detection (regex patterns)
2. **classifier** — risk labelling (keyword heuristics, advisory only)
3. **retrieval_policy** — authorised knowledge-space filtering
4. **sanitizer** — input / output sanitisation
5. **firewall** — orchestrator that enforces the full pipeline

.. note::
   The risk classifier is an **advisory** tool.  Authorization decisions
   are made by the RBAC + ABAC layers (function permissions + data scope).
   The classifier labels queries for audit and can trigger additional
   safeguards (e.g. forcing RAG mode), but it never *grants* access.
"""

from ai_security.injection import detect_injection, InjectionResult
from ai_security.classifier import classify_risk, RISK_LABEL_GENERAL, RISK_LABEL_PROMPT_INJECTION
from ai_security.retrieval_policy import (
    get_authorized_spaces,
    filter_authorized_chunks,
    build_safe_prompt,
)
from ai_security.sanitizer import (
    sanitize_input,
    sanitize_output,
    validate_sources,
)
from ai_security.firewall import (
    ai_security_pipeline,
    FirewallResult,
)

__all__ = [
    "detect_injection",
    "InjectionResult",
    "classify_risk",
    "RISK_LABEL_GENERAL",
    "RISK_LABEL_PROMPT_INJECTION",
    "get_authorized_spaces",
    "filter_authorized_chunks",
    "build_safe_prompt",
    "sanitize_input",
    "sanitize_output",
    "validate_sources",
    "ai_security_pipeline",
    "FirewallResult",
]
