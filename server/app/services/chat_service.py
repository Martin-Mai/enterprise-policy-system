"""
聊天业务服务模块
处理会话生命周期、历史上下文构建、引用解析与同步数据库持久化
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.audit_log import AuditLog
from app.models.conversation import Conversation
from app.models.message import Message
from app.services.llm import (
    NUMERICAL_COMPLIANCE_AUDIT_PROTOCOL,
    PLAIN_TEXT_MATH_FORMAT_PROTOCOL,
)

logger = logging.getLogger(__name__)

# 历史上下文：默认最近 5 轮（10 条消息），超 3000 字时缩减为 3 轮（6 条）
MAX_HISTORY_ROUNDS: int = 5
MAX_HISTORY_MESSAGES: int = MAX_HISTORY_ROUNDS * 2
FALLBACK_HISTORY_ROUNDS: int = 3
FALLBACK_HISTORY_MESSAGES: int = FALLBACK_HISTORY_ROUNDS * 2
MAX_HISTORY_CHARS: int = 3000

# RAG 参考资料传入 LLM 的单条长度上限（parent_child 下 text 为 parent 级上下文）
MAX_RAG_CHUNK_CHARS: int = 2000

REFUSAL_MESSAGE = "未找到相关信息"

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def prepare_conversation_and_history(
    user_id: int,
    session_id: str,
    question: str,
) -> Tuple[int, str, str, int]:
    """
    获取或创建会话，并构建多轮对话历史上下文（同步，供线程池调用）。

    Returns:
        (conversation_id, session_id, history_text, history_message_count)
    """
    db: Session = SessionLocal()
    try:
        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.session_id == session_id,
                Conversation.user_id == user_id,
            )
            .first()
        )

        if conversation is None:
            title = question[:15] if question else None
            conversation = Conversation(
                user_id=user_id,
                session_id=session_id,
                title=title,
            )
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            logger.info(
                "[SSE Chat] 新建会话 | user_id=%s | session_id=%s",
                user_id,
                session_id,
            )

        messages = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
            .all()
        )

        history_text, history_count = build_history_context(messages)
        return conversation.id, session_id, history_text, history_count
    finally:
        db.close()


def build_history_context(
    messages: List[Message],
) -> Tuple[str, int]:
    """
    将历史消息格式化为标准上下文文本，并做字符数滑动窗口裁剪。

    Returns:
        (history_text, used_message_count)
    """
    if not messages:
        return "", 0

    recent = messages[-MAX_HISTORY_MESSAGES:]
    history_text = _format_messages(recent)

    if len(history_text) > MAX_HISTORY_CHARS:
        recent = messages[-FALLBACK_HISTORY_MESSAGES:]
        history_text = _format_messages(recent)

    return history_text, len(recent)


def _format_messages(messages: List[Message]) -> str:
    """将消息列表格式化为「用户/助手」交替文本"""
    parts: List[str] = []
    for msg in messages:
        if msg.role == "user":
            parts.append(f"用户: {msg.content}")
        elif msg.role == "assistant":
            parts.append(f"助手: {msg.content}")
    if not parts:
        return ""
    return "\n".join(parts) + "\n"


def _truncate_for_prompt(text: str, max_chars: int = MAX_RAG_CHUNK_CHARS) -> str:
    """parent 级上下文过长时截断，避免撑爆 prompt"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…（节选）"


def build_rag_prompt(
    question: str,
    history: str,
    chunks: List[Dict[str, Any]],
    mode: str = "normal",
) -> str:
    """构建 RAG 强约束 Prompt；text 字段在 parent_child 下已为 parent 级上下文"""
    ref_lines: List[str] = []
    for index, chunk in enumerate(chunks, start=1):
        file_name = chunk.get("file_name", "")
        page_no = chunk.get("page_no", 0)
        chunk_text = _truncate_for_prompt(chunk.get("text", ""))
        ref_lines.append(f"[{index}] 文档：{file_name} 第{page_no}页: {chunk_text}")

    refs_text = "\n".join(ref_lines) if ref_lines else "（无参考资料）"
    history_section = history.strip() if history.strip() else "（无历史对话）"

    cautious_section = ""
    if mode == "cautious":
        cautious_section = (
            "\n【谨慎模式补充】：\n"
            "参考资料可能不足或与企业内部文档无关。若无法从资料中可靠回答，"
            f'请仅回复："{REFUSAL_MESSAGE}"，不要编造。\n'
            "对于与企业文档无关的问题（如天气、股价、写诗、加密货币等），"
            f'也必须仅回复："{REFUSAL_MESSAGE}"。\n'
        )

    return (
        "你是一个严谨的企业内部知识库助手。请严格基于以下参考资料回答用户的问题。\n\n"
        "【核心合规红线】：\n"
        f'1. 如果参考资料不足、不相关或无法推导出答案，请明确且仅说明："{REFUSAL_MESSAGE}"。'
        "绝对禁止凭借自身知识编造、胡扯或幻觉任何公司制度。\n"
        "2. 与企业内部文档无关的通用问题（如天气、股价、写诗、加密货币、娱乐八卦等），"
        f'必须仅回复："{REFUSAL_MESSAGE}"，不得调用自身知识作答。\n'
        "3. 回答时，必须在提及相关知识点的句尾，强制附上对应的参考资料引用编号（例如：...报销上限为500元[1]）。\n"
        "4. 当用户明确表示「未休/未使用/从未消耗」时，必须输出制度规定的【全额总额度】，"
        "严禁凭空假设已消耗量并做减法（如 10-5=5）。\n"
        f"{cautious_section}\n"
        f"{PLAIN_TEXT_MATH_FORMAT_PROTOCOL}\n\n"
        f"{NUMERICAL_COMPLIANCE_AUDIT_PROTOCOL}\n\n"
        f"【参考资料】：\n{refs_text}\n\n"
        f"【对话历史】：\n{history_section}\n\n"
        f"用户问题：{question}\n"
        "请给出准确、简洁的专业公文风回答，并在涉及到的答案末尾或句尾清晰标注引用编号（如 [1]）。"
    )


def build_cautious_rag_prompt(
    question: str,
    history: str,
    chunks: List[Dict[str, Any]],
) -> str:
    """构建 cautious 模式 RAG Prompt（兼容别名）"""
    return build_rag_prompt(question, history, chunks, mode="cautious")


def parse_citations(
    full_answer: str,
    chunks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    从助手回答中逆向解析引用编号，映射回检索 Chunk。

    若模型未写出任何 [n] 编号，则默认将全部 Top-K 作为引用并标注 inferred=True。
    """
    if not chunks:
        return []

    matched_numbers = _CITATION_PATTERN.findall(full_answer)
    used_indices = sorted(
        {
            int(num)
            for num in matched_numbers
            if 1 <= int(num) <= len(chunks)
        }
    )

    auto_inferred = False
    if not used_indices:
        used_indices = list(range(1, len(chunks) + 1))
        auto_inferred = True
        logger.info("[SSE Chat] 模型未标注引用编号，回退为全部 Top-%d 引用", len(chunks))

    citations: List[Dict[str, Any]] = []
    for index in used_indices:
        chunk = chunks[index - 1]
        preview_source = chunk.get("child_text") or chunk.get("text", "")
        citations.append({
            "chunk_id": str(chunk.get("chunk_id", "")),
            "file_name": str(chunk.get("file_name", "")),
            "page_no": int(chunk.get("page_no", 0)),
            "section_title": str(chunk.get("section_title", "")),
            "text_preview": preview_source[:200],
            "inferred": auto_inferred if auto_inferred else None,
        })

    return citations


def persist_chat_messages(
    conversation_id: int,
    question: str,
    answer: str,
    citations: List[Dict[str, Any]],
) -> Optional[int]:
    """
    原子持久化一轮问答（user + assistant 两条消息），同步供线程池调用。

    Returns:
        助手消息的数据库 ID；无内容可落库时返回 None。
    """
    if not question and not answer:
        return None

    db: Session = SessionLocal()
    try:
        user_message = Message(
            conversation_id=conversation_id,
            role="user",
            content=question,
            citations=None,
        )
        assistant_message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            citations=citations or None,
        )
        db.add(user_message)
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        logger.info(
            "[SSE Chat] 消息落库成功 | conversation_id=%s | assistant_message_id=%s | citations=%d",
            conversation_id,
            assistant_message.id,
            len(citations),
        )
        return assistant_message.id
    except Exception as exc:
        db.rollback()
        logger.exception(
            "[SSE Chat] 消息落库失败 | conversation_id=%s | error=%s",
            conversation_id,
            exc,
        )
        raise
    finally:
        db.close()


def log_audit_background(
    user_id: int,
    question: str,
    retrieved_chunks: List[Dict[str, Any]],
    answer: str,
    citations: List[Dict[str, Any]],
    confidence_score: Optional[float] = None,
    gate_decision: Optional[str] = None,
) -> None:
    """
    后台异步审计落库（由 FastAPI BackgroundTasks 在独立线程中延迟执行）。

    【线程安全红线】：禁止复用请求级 db 会话，必须在函数内部独立创建并关闭连接。
    """
    with SessionLocal() as db:
        try:
            audit_record = AuditLog(
                user_id=user_id,
                question=question,
                retrieved_chunks=retrieved_chunks,
                answer=answer,
                citations=citations or None,
                confidence_score=confidence_score,
                gate_decision=gate_decision,
            )
            db.add(audit_record)
            db.commit()
            logger.info(
                "[AuditLog] 审计日志入库成功 | user_id=%s | audit_id=%s | chunks=%d | citations=%d | gate=%s | score=%s",
                user_id,
                audit_record.id,
                len(retrieved_chunks),
                len(citations),
                gate_decision,
                confidence_score,
            )
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception(
                "[AuditLog] 审计日志入库失败 | user_id=%s | error=%s",
                user_id,
                exc,
            )
