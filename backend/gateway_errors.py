"""Shared gateway error types and httpx error mapping.

Used by hermes.py and knowledge.py to avoid duplicating the same
httpx exception → GatewayError conversion in every upstream caller.
"""

from __future__ import annotations

import httpx


class GatewayError(Exception):
    """Base exception for upstream gateway failures (Hermes, FastGPT, etc.)."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def map_httpx_errors(exc: Exception, prefix: str, label: str) -> GatewayError:
    """Map httpx exceptions to GatewayError with consistent status codes.

    Args:
        exc: The caught exception (ConnectError / TimeoutException /
             HTTPStatusError / ValueError).
        prefix: Error code prefix, e.g. ``"HERMES"`` or ``"FASTGPT"``.
        label: Human-readable service name, e.g. ``"Hermes"`` or ``"FastGPT"``.

    Returns:
        A GatewayError with the appropriate status code and message.

    Raises:
        The original exception if it is not a recognised httpx error type.
    """
    if isinstance(exc, httpx.ConnectError):
        return GatewayError(503, f"{prefix}_NOT_STARTED", f"{label} 服务未启动或不可达")
    if isinstance(exc, httpx.TimeoutException):
        return GatewayError(504, f"{prefix}_TIMEOUT", f"{label} 调用超时")
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code in {401, 403}:
            return GatewayError(401, f"{prefix}_UNAUTHORIZED", f"{label} 鉴权失败或 API Key 无效")
        return GatewayError(502, f"{prefix}_UPSTREAM_ERROR", f"{label} API 返回 HTTP {status_code}")
    if isinstance(exc, ValueError):
        return GatewayError(502, f"{prefix}_INVALID_RESPONSE", f"{label} 返回了无法解析的响应")
    raise exc
