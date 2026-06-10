"""
管理员接口路由
包含需要管理员权限才能访问的接口
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.feedback import Feedback
from app.models.message import Message
from app.models.user import User
from app.schemas.feedback import (
    AdminAuditLogItem,
    AdminAuditLogListResponse,
    AdminFeedbackItem,
    AdminFeedbackListResponse,
)
from app.schemas.user import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["管理员"])

ANSWER_SUMMARY_MAX_LEN: int = 200


def _parse_date_param(date_str: str, field_name: str) -> datetime:
    """将 YYYY-MM-DD 字符串解析为 datetime，解析失败时抛出 400"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} 格式无效，请使用 YYYY-MM-DD",
        ) from exc


@router.get("/users", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> List[UserResponse]:
    """
    获取所有用户列表（仅管理员可访问）
    - 通过 require_admin 依赖注入进行管理员权限校验
    - 返回所有用户的列表信息（不含密码）
    """
    users = db.query(User).all()
    return users


@router.get("/audit-logs", response_model=AdminAuditLogListResponse)
def list_audit_logs(
    user_id: Optional[int] = Query(default=None, description="按用户 ID 筛选"),
    start_date: Optional[str] = Query(default=None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> AdminAuditLogListResponse:
    """
    分页查询 RAG 问答全链路审计日志（仅管理员可访问）。
    """
    try:
        query = db.query(AuditLog, User.username).join(
            User, AuditLog.user_id == User.id
        )

        if user_id is not None:
            query = query.filter(AuditLog.user_id == user_id)

        if start_date is not None:
            start_dt = _parse_date_param(start_date, "start_date")
            query = query.filter(AuditLog.created_at >= start_dt)

        if end_date is not None:
            end_dt = _parse_date_param(end_date, "end_date")
            # 包含 end_date 当天全天
            end_exclusive = end_dt.replace(hour=23, minute=59, second=59)
            query = query.filter(AuditLog.created_at <= end_exclusive)

        total = query.count()
        offset = (page - 1) * page_size
        rows = (
            query.order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        items: List[AdminAuditLogItem] = []
        for audit_log, username in rows:
            answer_text = audit_log.answer or ""
            items.append(
                AdminAuditLogItem(
                    id=audit_log.id,
                    username=username,
                    question=audit_log.question,
                    answer_summary=answer_text[:ANSWER_SUMMARY_MAX_LEN],
                    citations=audit_log.citations,
                    created_at=audit_log.created_at,
                )
            )

        return AdminAuditLogListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )

    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("[Admin] 审计日志查询失败 | error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="审计日志查询失败，请稍后重试",
        ) from exc


@router.get("/feedbacks", response_model=AdminFeedbackListResponse)
def list_feedbacks(
    is_positive: Optional[bool] = Query(
        default=None,
        description="按赞踩筛选：True=点赞，False=点踩",
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> AdminFeedbackListResponse:
    """
    查询用户反馈列表，关联展示被评价消息原文及提交者用户名（仅管理员可访问）。
    """
    try:
        query = (
            db.query(Feedback, Message.content, User.username)
            .join(Message, Feedback.message_id == Message.id)
            .join(User, Feedback.user_id == User.id)
        )

        if is_positive is not None:
            query = query.filter(Feedback.is_positive == is_positive)

        total = query.count()
        rows = query.order_by(Feedback.created_at.desc()).all()

        items: List[AdminFeedbackItem] = []
        for feedback, message_content, username in rows:
            items.append(
                AdminFeedbackItem(
                    id=feedback.id,
                    message_id=feedback.message_id,
                    message_content=message_content,
                    username=username,
                    is_positive=feedback.is_positive,
                    comment=feedback.comment,
                    created_at=feedback.created_at,
                )
            )

        return AdminFeedbackListResponse(total=total, items=items)

    except SQLAlchemyError as exc:
        logger.exception("[Admin] 反馈列表查询失败 | error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="反馈列表查询失败，请稍后重试",
        ) from exc
