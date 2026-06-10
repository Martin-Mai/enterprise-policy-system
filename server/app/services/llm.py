"""
大模型服务模块
通过 httpx 异步流式调用本地 Ollama 生成接口
"""

import json
import logging
from typing import AsyncIterator

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class OllamaError(Exception):
    """Ollama 服务调用异常"""


async def stream_ollama_generate(prompt: str) -> AsyncIterator[str]:
    """
    异步流式请求 Ollama /api/generate 接口，逐 token 产出文本片段。

    Args:
        prompt: 完整 RAG Prompt 文本

    Yields:
        每次 yield 一个 token 片段（由 Ollama 返回的 response 字段）

    Raises:
        OllamaError: 网络超时、HTTP 错误或响应解析失败时抛出
    """
    payload = {
        "model": settings.OLLAMA_CHAT_MODEL,
        "prompt": prompt,
        "stream": True,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.OLLAMA_GENERATE_TIMEOUT) as client:
            async with client.stream(
                "POST",
                settings.OLLAMA_GENERATE_URL,
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning("[Ollama] 无法解析流式响应行: %s", line)
                        raise OllamaError("大模型服务响应超时") from exc

                    token: str = data.get("response", "")
                    if token:
                        yield token

                    if data.get("done"):
                        break
    except httpx.TimeoutException as exc:
        logger.exception("[Ollama] 流式生成超时: %s", exc)
        raise OllamaError("大模型服务响应超时") from exc
    except httpx.HTTPError as exc:
        logger.exception("[Ollama] 流式生成 HTTP 错误: %s", exc)
        raise OllamaError("大模型服务响应超时") from exc
    except OllamaError:
        raise
    except Exception as exc:
        logger.exception("[Ollama] 流式生成未知错误: %s", exc)
        raise OllamaError("大模型服务响应超时") from exc
