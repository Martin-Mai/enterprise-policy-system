"""
会话管理 API 路由模块
提供历史会话列表、消息查询及删除接口
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.user import User
from app.schemas.conversation import (
    ConversationItem,
    ConversationListResponse,
    MessageItem,
    MessageListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["会话管理"])


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationListResponse:
    """
    获取当前登录用户的所有历史会话，按创建时间倒序排列。
    """
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )

    items = [
        ConversationItem(
            id=conv.id,
            session_id=conv.session_id,
            title=conv.title,
            created_at=conv.created_at,
        )
        for conv in conversations
    ]

    return ConversationListResponse(items=items)


@router.get("/{session_id}/messages", response_model=MessageListResponse)
def get_conversation_messages(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageListResponse:
    """
    获取指定会话的所有历史问答消息，按时间正序排列。
    """
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.session_id == session_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或无权访问",
        )

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    items = [
        MessageItem(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            citations=msg.citations,
            created_at=msg.created_at,
        )
        for msg in messages
    ]

    return MessageListResponse(session_id=session_id, items=items)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    删除指定会话及其全部消息（级联删除）。
    """
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.session_id == session_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="会话不存在或无权访问",
        )

    db.delete(conversation)
    db.commit()
    logger.info(
        "[Conversation] 会话已删除 | user_id=%s | session_id=%s",
        current_user.id,
        session_id,
    )
