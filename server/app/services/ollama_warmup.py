"""
Ollama 模型后台预热模块
应用启动后异步加载 embedding 与 chat 模型，避免首次问答冷启动超时
"""

import logging
import time
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.services.document_processor import get_embedding

logger = logging.getLogger(__name__)

# pending | running | done | failed | skipped
_warmup_state: str = "pending"
_warmup_error: Optional[str] = None
_warmup_duration_s: Optional[float] = None


def get_warmup_status() -> Dict[str, Any]:
    """返回 Ollama warmup 状态，供就绪探针与运维日志使用"""
    return {
        "ollama_warmup": _warmup_state,
        "ollama_ready": _warmup_state in ("done", "skipped"),
        "ollama_warmup_error": _warmup_error,
        "ollama_warmup_duration_s": _warmup_duration_s,
    }


def is_ollama_ready() -> bool:
    return _warmup_state in ("done", "skipped")


async def _warmup_generate() -> bool:
    """短 prompt 非流式调用，加载 chat 模型并保持 keep_alive"""
    payload = {
        "model": settings.OLLAMA_CHAT_MODEL,
        "prompt": "warmup",
        "stream": False,
        "keep_alive": settings.OLLAMA_KEEP_ALIVE,
        "options": {"num_predict": 1},
    }
    try:
        async with httpx.AsyncClient(timeout=settings.OLLAMA_GENERATE_TIMEOUT) as client:
            response = await client.post(settings.OLLAMA_GENERATE_URL, json=payload)
            response.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("[Ollama] warmup generate 失败: %s", exc)
        return False


async def warmup_ollama_models() -> None:
    """
    后台预热 Ollama 双模型（embedding → chat）。
    失败不阻塞服务启动，首次真实请求仍会尝试加载。
    """
    global _warmup_state, _warmup_error, _warmup_duration_s

    if not settings.OLLAMA_WARMUP_ENABLED:
        _warmup_state = "skipped"
        logger.info("[Ollama] warmup 已禁用 (OLLAMA_WARMUP_ENABLED=false)")
        return

    _warmup_state = "running"
    start = time.monotonic()
    logger.info("[Ollama] warmup 开始...")

    embed_ok = False
    generate_ok = False

    try:
        embedding = await get_embedding("warmup")
        embed_ok = embedding is not None
        if embed_ok:
            logger.info("[Ollama] warmup embedding 完成")
        else:
            logger.warning("[Ollama] warmup embedding 失败")

        generate_ok = await _warmup_generate()
        if generate_ok:
            logger.info("[Ollama] warmup generate 完成")
        else:
            logger.warning("[Ollama] warmup generate 失败")

        _warmup_duration_s = round(time.monotonic() - start, 2)

        if embed_ok and generate_ok:
            _warmup_state = "done"
            logger.info("[Ollama] warmup done in %ss", _warmup_duration_s)
        else:
            _warmup_state = "failed"
            _warmup_error = (
                f"embedding={'ok' if embed_ok else 'fail'}, "
                f"generate={'ok' if generate_ok else 'fail'}"
            )
            logger.warning(
                "[Ollama] warmup 部分失败 (%ss): %s",
                _warmup_duration_s,
                _warmup_error,
            )
    except Exception as exc:
        _warmup_state = "failed"
        _warmup_error = str(exc)
        _warmup_duration_s = round(time.monotonic() - start, 2)
        logger.exception("[Ollama] warmup 异常: %s", exc)
