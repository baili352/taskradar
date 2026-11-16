"""OpenAI 兼容 chat/completions 客户端，统一处理超时与安全错误。"""

import logging
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)

from app.core.config import settings

logger = logging.getLogger(__name__)
_NO_KEY_PLACEHOLDER = "local-no-key"


class AIError(Exception):
    """可直接展示给用户的安全大模型错误。"""


class _CompatibleClient(AsyncOpenAI):
    @property
    def auth_headers(self) -> dict[str, str]:
        # AsyncOpenAI 要求非空 api_key；无密钥本地服务不能因此发送伪密钥。
        if self.api_key == _NO_KEY_PLACEHOLDER:
            return {}
        return super().auth_headers


def _safe_error(exc: Exception) -> AIError:
    if isinstance(exc, APITimeoutError):
        return AIError("大模型服务响应超时，请稍后重试或检查服务状态。")
    if isinstance(exc, AuthenticationError):
        return AIError("大模型服务鉴权失败，请检查 backend/.env 中的密钥配置。")
    if isinstance(exc, RateLimitError):
        return AIError("大模型服务触发限流，请稍后重试。")
    if isinstance(exc, APIConnectionError):
        return AIError("无法连接大模型服务，请检查服务地址、网络或本地模型是否已启动。")
    if isinstance(exc, APIStatusError):
        return AIError(f"大模型服务返回错误（HTTP {exc.status_code}），请检查模型和服务配置。")
    return AIError("大模型服务调用失败，请检查配置或稍后重试。")


async def _request(
    messages: list[dict[str, str]], *, json_output: bool, max_tokens: int
) -> str:
    if not settings.ai_configured:
        raise AIError("尚未配置 AI_BASE_URL 和 AI_MODEL。")

    options: dict[str, Any] = {
        "model": settings.ai_model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": max_tokens,
    }
    if json_output:
        options["response_format"] = {"type": "json_object"}

    try:
        async with _CompatibleClient(
            api_key=settings.ai_api_key.strip() or _NO_KEY_PLACEHOLDER,
            base_url=settings.ai_base_url.strip(),
            timeout=settings.ai_timeout_seconds,
            max_retries=min(max(settings.ai_max_retries, 0), 1),
        ) as client:
            response = await client.chat.completions.create(**options)
        content = response.choices[0].message.content if response.choices else None
        if not isinstance(content, str) or not content.strip():
            raise AIError("大模型服务返回了空响应。")
        return content.strip()
    except AIError:
        raise
    except (OpenAIError, OSError, ValueError) as exc:
        logger.error("大模型请求失败：%s", type(exc).__name__)
        raise _safe_error(exc) from None
    except Exception as exc:
        logger.error("大模型请求出现未预期错误：%s", type(exc).__name__)
        raise AIError("大模型服务调用失败，请检查配置或稍后重试。") from None


async def request_analysis_json(system_prompt: str, user_prompt: str) -> str:
    """请求 JSON 对象输出，不在日志中记录提示词或文档内容。"""
    return await _request(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        json_output=True,
        max_tokens=4096,
    )


async def test_ai_connection() -> None:
    """仅发送短提示测试连通性，不发送任何文档内容。"""
    await _request(
        [
            {"role": "system", "content": "你是连通性检查助手。"},
            {"role": "user", "content": "只回复 OK。"},
        ],
        json_output=False,
        max_tokens=8,
    )
