from typing import Any
import os

import httpx

from config import Settings
from gateway_errors import GatewayError, map_httpx_errors

# Backward-compatible alias — prefer GatewayError for new code
HermesGatewayError = GatewayError


def _resolve_api_key(settings: Settings) -> str | None:
    """解析 API Key：优先使用配置值，否则回退到 DEEPSEEK_API_KEY 环境变量。"""
    if settings.HERMES_API_KEY:
        return settings.HERMES_API_KEY
    return os.environ.get("DEEPSEEK_API_KEY")


async def hermes_chat(
    settings: Settings,
    messages: list[dict[str, str]],
) -> str:
    """调用 Hermes Chat Completions API，返回 AI 回复文本。"""
    if settings.HERMES_MODE == "mock":
        question = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                question = msg.get("content", "")
                break
        return (
            f"[Hermes mock] 这是一个模拟回复。您的问题「{question[:80]}」已收到，"
            f"请将 HERMES_MODE 设为 real 并配置 HERMES_BASE_URL 以获取真实 AI 回复。"
        )

    return await _hermes_chat_real(settings, messages)


async def _hermes_chat_real(
    settings: Settings,
    messages: list[dict[str, str]],
) -> str:
    api_key = _resolve_api_key(settings)
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body: dict[str, Any] = {
        "model": settings.HERMES_MODEL,
        "messages": messages,
        "stream": False,
    }
    if settings.HERMES_PROFILE:
        body["profile"] = settings.HERMES_PROFILE

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(settings.HERMES_TIMEOUT_SECONDS)) as client:
            response = await client.post(
                f"{settings.HERMES_BASE_URL.rstrip('/')}/v1/chat/completions",
                headers=headers,
                json=body,
            )
        response.raise_for_status()
        payload = response.json()
    except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError, ValueError) as exc:
        raise map_httpx_errors(exc, "HERMES", "Hermes") from exc

    if isinstance(payload, dict):
        choices: list[dict[str, Any]] = payload.get("choices", [])
        if choices:
            message: dict[str, Any] = choices[0].get("message", {})
            content = message.get("content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()

    raise HermesGatewayError(502, "HERMES_EMPTY_RESPONSE", "Hermes 返回了空回复")
