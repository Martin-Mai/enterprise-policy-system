"""
用户反馈 API 路由模块
提供对 AI 回答的赞踩提交与所有权校验
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.conversation import Conversation
from app.models.feedback import Feedback
from app.models.message import Message
from app.models.user import User
from app.schemas.feedback import FeedbackCreate, FeedbackSubmitResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["用户反馈"])


@router.post("", response_model=FeedbackSubmitResponse)
def submit_feedback(
    body: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FeedbackSubmitResponse:
    """
    提交或更新用户对 AI 消息的赞踩反馈（幂等 Upsert）。

    通过 messages -> conversations 联查校验消息归属，防止水平越权。
    """
    # 联查校验：消息必须属于当前登录用户，且为 assistant 角色
    owned_message = (
        db.query(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .filter(
            Message.id == body.message_id,
            Conversation.user_id == current_user.id,
            Message.role == "assistant",
        )
        .first()
    )

    if owned_message is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权对该消息提交反馈",
        )

    try:
        existing = (
            db.query(Feedback)
            .filter(
                Feedback.user_id == current_user.id,
                Feedback.message_id == body.message_id,
            )
            .first()
        )

        if existing is not None:
            existing.is_positive = body.is_positive
            existing.comment = body.comment
            db.commit()
            logger.info(
                "[Feedback] 反馈已更新 | user_id=%s | message_id=%s | is_positive=%s",
                current_user.id,
                body.message_id,
                body.is_positive,
            )
        else:
            feedback = Feedback(
                message_id=body.message_id,
                user_id=current_user.id,
                is_positive=body.is_positive,
                comment=body.comment,
            )
            db.add(feedback)
            db.commit()
            logger.info(
                "[Feedback] 反馈已新建 | user_id=%s | message_id=%s | is_positive=%s",
                current_user.id,
                body.message_id,
                body.is_positive,
            )

        return FeedbackSubmitResponse(message="反馈提交成功")

    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "[Feedback] 反馈提交失败 | user_id=%s | message_id=%s | error=%s",
            current_user.id,
            body.message_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="反馈提交失败，请稍后重试",
        ) from exc
