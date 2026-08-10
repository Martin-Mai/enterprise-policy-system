"""
管理员接口路由
包含需要管理员权限才能访问的接口：统计、文档、审计、反馈
"""

import json
import logging
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import SessionLocal, get_db
from app.models.audit_log import AuditLog
from app.models.document import Document, DocumentChunk
from app.models.feedback import Feedback
from app.models.message import Message
from app.models.user import User
from app.schemas.admin import (
    AdminAuditLogDetail,
    AdminClearAuditLogsResponse,
    AdminDeleteProcessingResponse,
    AdminDocumentItem,
    AdminDocumentListResponse,
    AdminStatsResponse,
    DocumentReindexResponse,
    FeedbackProcessedResponse,
    HotDocumentItem,
    HotDocumentsResponse,
)
from app.schemas.feedback import (
    AdminAuditLogItem,
    AdminAuditLogListResponse,
    AdminFeedbackItem,
    AdminFeedbackListResponse,
)
from app.schemas.user import UserResponse
from app.services.document_processor import delete_document_background, process_document_background
from app.services.search_service import get_bm25_index

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["管理员"])

ANSWER_SUMMARY_MAX_LEN: int = 200
# 热门文档聚合时最多扫描的近期审计记录条数
HOT_DOCS_SCAN_LIMIT: int = 500


def _parse_date_param(date_str: str, field_name: str) -> datetime:
    """将 YYYY-MM-DD 字符串解析为 datetime，解析失败时抛出 400"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} 格式无效，请使用 YYYY-MM-DD",
        ) from exc


def _safe_parse_citations(raw: Any) -> List[dict]:
    """
    安全解析 citations 字段
    兼容 ORM 已反序列化的 list、JSON 字符串及异常数据
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [c for c in raw if isinstance(c, dict)]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [c for c in parsed if isinstance(c, dict)]
        except (json.JSONDecodeError, TypeError):
            logger.warning("[Admin] citations JSON 解析失败，已跳过")
    return []


@router.get("/users", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> List[UserResponse]:
    """获取所有用户列表（仅管理员可访问）"""
    users = db.query(User).all()
    return users


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> AdminStatsResponse:
    """
    仪表盘核心统计数据
    使用 SQL 聚合查询，避免全表 Python 计数
    """
    _ = current_admin
    try:
        # 文档总数（排除删除中状态）
        total_documents = (
            db.query(func.count(Document.id))
            .filter(Document.status != "deleting")
            .scalar()
            or 0
        )

        # 用户总数
        total_users = db.query(func.count(User.id)).scalar() or 0

        # 今日问答次数：使用数据库本地日期的 func.date + func.current_date，排除时区干扰
        today_qa_count = (
            db.query(func.count(AuditLog.id))
            .filter(func.date(AuditLog.created_at) == func.current_date())
            .scalar()
            or 0
        )

        # 近 7 天折线图锚点：以数据库当前日期为基准
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        # 反馈赞踩统计
        feedback_rows = (
            db.query(Feedback.is_positive, func.count(Feedback.id))
            .group_by(Feedback.is_positive)
            .all()
        )
        positive_count = 0
        negative_count = 0
        for is_positive, count in feedback_rows:
            if is_positive:
                positive_count = count
            else:
                negative_count = count

        # 好评率 = positive / (positive + negative) * 100，零反馈时安全返回 0.0
        total_feedback = positive_count + negative_count
        if total_feedback == 0:
            positive_rate = 0.0
        else:
            positive_rate = round(positive_count / total_feedback * 100, 1)

        # 近 7 天每日问答量（从 6 天前到今天，共 7 天）
        weekly_qa: List[int] = []
        for day_offset in range(6, -1, -1):
            day_start = today_start - timedelta(days=day_offset)
            day_end = day_start + timedelta(days=1)
            day_count = (
                db.query(func.count(AuditLog.id))
                .filter(
                    AuditLog.created_at >= day_start,
                    AuditLog.created_at < day_end,
                )
                .scalar()
                or 0
            )
            weekly_qa.append(day_count)

        return AdminStatsResponse(
            total_documents=total_documents,
            total_users=total_users,
            today_qa_count=today_qa_count,
            positive_rate=positive_rate,
            weekly_qa=weekly_qa,
            feedback_stats={"positive": positive_count, "negative": negative_count},
        )

    except SQLAlchemyError as exc:
        logger.exception("[Admin] 统计数据查询失败 | error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="统计数据查询失败，请稍后重试",
        ) from exc


@router.get("/hot-documents", response_model=HotDocumentsResponse)
def get_hot_documents(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> HotDocumentsResponse:
    """
    热门引用文档 Top 5
    从近期 audit_logs 记录在 Python 侧安全解析 citations 并 Counter 汇总
    避免跨版本 JSON_TABLE 联查引发崩溃
    """
    _ = current_admin
    try:
        recent_logs = (
            db.query(AuditLog.citations)
            .filter(AuditLog.citations.isnot(None))
            .order_by(AuditLog.created_at.desc())
            .limit(HOT_DOCS_SCAN_LIMIT)
            .all()
        )

        counter: Counter[str] = Counter()
        for (citations_raw,) in recent_logs:
            for citation in _safe_parse_citations(citations_raw):
                file_name = citation.get("file_name")
                if file_name:
                    counter[str(file_name)] += 1

        top_items = counter.most_common(5)
        return HotDocumentsResponse(
            items=[
                HotDocumentItem(file_name=name, citation_count=count)
                for name, count in top_items
            ]
        )

    except SQLAlchemyError as exc:
        logger.exception("[Admin] 热门文档查询失败 | error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="热门文档查询失败，请稍后重试",
        ) from exc


@router.get("/documents", response_model=AdminDocumentListResponse)
def list_admin_documents(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> AdminDocumentListResponse:
    """管理员文档列表，含上传者、分块数与状态"""
    _ = current_admin
    try:
        base_query = (
            db.query(
                Document,
                User.username,
                func.count(DocumentChunk.id).label("chunk_count"),
            )
            .join(User, Document.uploaded_by == User.id)
            .outerjoin(DocumentChunk, DocumentChunk.doc_id == Document.id)
            .group_by(Document.id, User.username)
        )

        total = db.query(func.count(Document.id)).scalar() or 0
        offset = (page - 1) * page_size
        rows = (
            base_query.order_by(Document.upload_time.desc())
            .offset(offset)
            .limit(page_size)
            .all()
        )

        items: List[AdminDocumentItem] = []
        for document, username, chunk_count in rows:
            items.append(
                AdminDocumentItem(
                    id=document.id,
                    file_name=document.file_name,
                    upload_time=document.upload_time,
                    uploader_name=username,
                    chunk_count=chunk_count or 0,
                    status=document.status or "active",
                )
            )

        return AdminDocumentListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items,
        )

    except SQLAlchemyError as exc:
        logger.exception("[Admin] 文档列表查询失败 | error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文档列表查询失败，请稍后重试",
        ) from exc


@router.delete("/documents/{doc_id}", response_model=AdminDeleteProcessingResponse)
def admin_delete_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> AdminDeleteProcessingResponse:
    """
    防抖状态机级联删除
    1. 立即将 status 置为 deleting（前台检索自动过滤）
    2. 返回 processing 响应
    3. BackgroundTasks 异步执行物理删除
    """
    _ = current_admin
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    if document.status == "deleting":
        return AdminDeleteProcessingResponse(
            status="processing",
            message="文档已在删除队列中，请稍候...",
        )

    # 步骤 1：标记为删除中，确保检索层立即过滤
    document.status = "deleting"
    db.commit()
    # 立即刷新 BM25 索引，排除 deleting 文档分块
    get_bm25_index().refresh_index()
    logger.info("[AdminDelete] doc_id=%s 已标记为 deleting，提交后台级联删除", doc_id)

    # 步骤 2：投入后台任务执行完整删除链
    background_tasks.add_task(delete_document_background, doc_id)

    return AdminDeleteProcessingResponse(
        status="processing",
        message="文档正在后台安全注销...",
    )


@router.post("/documents/reindex/{doc_id}", response_model=DocumentReindexResponse)
def reindex_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> DocumentReindexResponse:
    """
    重新向量化文档：清除旧分块后按当前 CHUNK_STRATEGY 重新 parse + split + embed。
    批量重建请使用 server/scripts/reindex_all_documents.py。
    """
    _ = current_admin
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    if document.status == "deleting":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文档正在删除中，无法重新向量化",
        )

    if document.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅 active 状态文档可重建索引",
        )

    if not document.file_path or not Path(document.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文档源文件不存在，无法重新向量化",
        )

    background_tasks.add_task(
        process_document_background,
        doc_id,
        document.file_path,
        document.file_name,
    )

    logger.info(
        "[AdminReindex] doc_id=%s file_name=%s 重建索引任务已提交",
        doc_id,
        document.file_name,
    )

    return DocumentReindexResponse(
        status="processing",
        message=f"文档「{document.file_name}」重建索引任务已提交",
    )


@router.get("/audit-logs", response_model=AdminAuditLogListResponse)
def list_audit_logs(
    user_id: Optional[int] = Query(default=None, description="按用户 ID 筛选"),
    username: Optional[str] = Query(default=None, description="按用户名模糊搜索"),
    start_date: Optional[str] = Query(default=None, description="起始日期 YYYY-MM-DD"),
    end_date: Optional[str] = Query(default=None, description="结束日期 YYYY-MM-DD"),
    page: int = Query(default=1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页条数"),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> AdminAuditLogListResponse:
    """分页查询 RAG 问答全链路审计日志（仅管理员可访问）"""
    try:
        query = db.query(AuditLog, User.username).join(
            User, AuditLog.user_id == User.id
        )

        if user_id is not None:
            query = query.filter(AuditLog.user_id == user_id)

        if username:
            query = query.filter(User.username.like(f"%{username.strip()}%"))

        if start_date is not None:
            start_dt = _parse_date_param(start_date, "start_date")
            query = query.filter(AuditLog.created_at >= start_dt)

        if end_date is not None:
            end_dt = _parse_date_param(end_date, "end_date")
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
        for audit_log, uname in rows:
            answer_text = audit_log.answer or ""
            citations = audit_log.citations
            citation_count = len(citations) if isinstance(citations, list) else 0
            items.append(
                AdminAuditLogItem(
                    id=audit_log.id,
                    username=uname,
                    question=audit_log.question,
                    answer_summary=answer_text[:ANSWER_SUMMARY_MAX_LEN],
                    citation_count=citation_count,
                    citations=citations,
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


@router.delete("/audit-logs", response_model=AdminClearAuditLogsResponse)
def clear_audit_logs(
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> AdminClearAuditLogsResponse:
    """清空 audit_logs 表全部记录（仅管理员可访问）"""
    try:
        db.execute(text("TRUNCATE TABLE audit_logs"))
        db.commit()
        logger.info(
            "[Admin] 审计日志已全部清空 | admin_id=%s username=%s",
            current_admin.id,
            current_admin.username,
        )
        return AdminClearAuditLogsResponse(
            status="success",
            message="所有审计日志已清空",
        )
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("[Admin] 审计日志清空失败 | error=%s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="审计日志清空失败，请稍后重试",
        ) from exc


@router.get("/audit-logs/{log_id}", response_model=AdminAuditLogDetail)
def get_audit_log_detail(
    log_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> AdminAuditLogDetail:
    """获取单条审计日志详情，含完整 retrieved_chunks 与 citations"""
    _ = current_admin
    row = (
        db.query(AuditLog, User.username)
        .join(User, AuditLog.user_id == User.id)
        .filter(AuditLog.id == log_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="审计记录不存在",
        )

    audit_log, username = row
    retrieved = audit_log.retrieved_chunks
    if not isinstance(retrieved, list):
        retrieved = []

    return AdminAuditLogDetail(
        id=audit_log.id,
        username=username,
        question=audit_log.question,
        answer=audit_log.answer,
        retrieved_chunks=retrieved,
        citations=audit_log.citations,
        created_at=audit_log.created_at,
    )


@router.get("/feedbacks", response_model=AdminFeedbackListResponse)
def list_feedbacks(
    is_positive: Optional[bool] = Query(
        default=None,
        description="按赞踩筛选：True=点赞，False=点踩",
    ),
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> AdminFeedbackListResponse:
    """查询用户反馈列表，关联展示被评价消息原文及提交者用户名"""
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
        for feedback, message_content, uname in rows:
            items.append(
                AdminFeedbackItem(
                    id=feedback.id,
                    message_id=feedback.message_id,
                    message_content=message_content,
                    username=uname,
                    is_positive=feedback.is_positive,
                    comment=feedback.comment,
                    is_processed=feedback.is_processed,
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


def _mark_feedback_resolved(
    feedback_id: int,
    db: Session,
) -> FeedbackProcessedResponse:
    """标记反馈为已处理的共用逻辑"""
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="反馈记录不存在",
        )

    feedback.is_processed = True
    db.commit()

    return FeedbackProcessedResponse(
        id=feedback.id,
        is_processed=True,
        message="已标记为已处理",
    )


@router.patch("/feedbacks/{feedback_id}/resolve", response_model=FeedbackProcessedResponse)
def resolve_feedback(
    feedback_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> FeedbackProcessedResponse:
    """标记反馈为已处理（闭环管理入口）"""
    _ = current_admin
    return _mark_feedback_resolved(feedback_id, db)


@router.patch("/feedbacks/{feedback_id}/processed", response_model=FeedbackProcessedResponse)
def mark_feedback_processed(
    feedback_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(require_admin),
) -> FeedbackProcessedResponse:
    """标记反馈为已处理（兼容旧路径）"""
    _ = current_admin
    return _mark_feedback_resolved(feedback_id, db)
