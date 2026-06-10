"""
流式问答 API 路由模块
提供 SSE 多轮对话 + RAG 强引用来源接口
"""

import json
import logging
import uuid
from typing import Any, AsyncIterator, Dict, List

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.chat import ChatRequest, Citation
from app.services.chat_service import (
    build_rag_prompt,
    log_audit_background,
    parse_citations,
    persist_chat_messages,
    prepare_conversation_and_history,
)
from app.services.llm import OllamaError, stream_ollama_generate
from app.services.search_service import hybrid_search

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["流式问答"])


def _citations_for_sse(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将落库 citations 转为 SSE 结束事件的 Citation 字段"""
    result: List[Dict[str, Any]] = []
    for item in citations:
        result.append({
            "chunk_id": item["chunk_id"],
            "file_name": item["file_name"],
            "page_no": item["page_no"],
            "section_title": item["section_title"],
            "text_preview": item["text_preview"],
            **({"inferred": item["inferred"]} if item.get("inferred") else {}),
        })
    return result


@router.post("/stream")
async def chat_stream(
    request: Request,
    background_tasks: BackgroundTasks,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    SSE 流式问答接口

    事件类型：
    - token: 逐 token 推送模型输出
    - end: 流结束并返回 citations
    - error: Ollama 服务异常
    """
    session_id = body.session_id or str(uuid.uuid4())
    question = body.question.strip()

    conversation_id, session_id, history_text, history_count = await run_in_threadpool(
        prepare_conversation_and_history,
        current_user.id,
        session_id,
        question,
    )

    # 完整保留混合检索原始 Top-5 分块，供后台审计落库使用
    retrieved_chunks: List[Dict[str, Any]] = await hybrid_search(question, limit=5)
    prompt = build_rag_prompt(question, history_text, retrieved_chunks)

    logger.info(
        "[SSE Chat] Session: %s | History Chunks: %d | Retrieval Count: %d",
        session_id,
        history_count,
        len(retrieved_chunks),
    )

    async def event_generator() -> AsyncIterator[str]:
        full_answer: str = ""
        disconnected: bool = False
        ollama_error: bool = False
        citations: List[Dict[str, Any]] = []

        try:
            async for token in stream_ollama_generate(prompt):
                if await request.is_disconnected():
                    disconnected = True
                    logger.warning("[SSE Chat] 客户端断开 | session_id=%s", session_id)
                    break

                full_answer += token
                payload = json.dumps(
                    {"type": "token", "content": token},
                    ensure_ascii=False,
                )
                yield f"data: {payload}\n\n"

        except OllamaError as exc:
            ollama_error = True
            logger.error("[SSE Chat] Ollama 异常 | session_id=%s | %s", session_id, exc)
            error_payload = json.dumps(
                {"type": "error", "message": "大模型服务响应超时"},
                ensure_ascii=False,
            )
            yield f"data: {error_payload}\n\n"

        finally:
            answer_to_save = full_answer
            if disconnected:
                answer_to_save = (
                    full_answer + "[用户中断]" if full_answer else "[用户中断]"
                )

            persist_success: bool = False
            if question:
                citations = (
                    parse_citations(answer_to_save, retrieved_chunks)
                    if answer_to_save
                    else []
                )
                try:
                    await run_in_threadpool(
                        persist_chat_messages,
                        conversation_id,
                        question,
                        answer_to_save,
                        citations,
                    )
                    persist_success = True
                except Exception as exc:
                    logger.exception(
                        "[SSE Chat] 落库失败 | session_id=%s | error=%s",
                        session_id,
                        exc,
                    )

                # 消息落库成功后，非阻塞投递后台审计任务，不影响 SSE 吐字
                if persist_success and answer_to_save:
                    background_tasks.add_task(
                        log_audit_background,
                        current_user.id,
                        question,
                        retrieved_chunks,
                        answer_to_save,
                        citations,
                    )

            if not disconnected and not ollama_error and answer_to_save:
                end_citations = [Citation(**item).model_dump(exclude_none=True) for item in _citations_for_sse(citations)]
                end_payload = json.dumps(
                    {"type": "end", "citations": end_citations},
                    ensure_ascii=False,
                )
                yield f"data: {end_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )
