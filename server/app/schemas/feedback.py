"""
反馈与审计数据模式模块
定义用户反馈提交及管理员查询的 Pydantic 模型
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    """用户提交反馈请求模型"""

    message_id: int = Field(..., description="被评价的 AI 消息 ID")
    is_positive: bool = Field(..., description="True=点赞，False=点踩")
    comment: Optional[str] = Field(default=None, description="可选评语或吐槽")


class FeedbackSubmitResponse(BaseModel):
    """反馈提交成功响应"""

    message: str = Field(..., description="操作结果提示")


class AdminAuditLogItem(BaseModel):
    """管理员审计日志列表项"""

    id: int = Field(..., description="审计记录 ID")
    username: str = Field(..., description="提问用户用户名")
    question: str = Field(..., description="用户原始提问")
    answer_summary: str = Field(..., description="回答摘要（前 200 字符）")
    citations: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="完整引用列表",
    )
    created_at: datetime = Field(..., description="审计记录创建时间")


class AdminAuditLogListResponse(BaseModel):
    """管理员审计日志分页响应"""

    total: int = Field(..., description="符合条件的总记录数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页条数")
    items: List[AdminAuditLogItem] = Field(..., description="审计日志列表")


class AdminFeedbackItem(BaseModel):
    """管理员反馈列表项"""

    id: int = Field(..., description="反馈记录 ID")
    message_id: int = Field(..., description="被评价消息 ID")
    message_content: str = Field(..., description="被评价的 AI 回答原文")
    username: str = Field(..., description="提交反馈的用户名")
    is_positive: bool = Field(..., description="True=点赞，False=点踩")
    comment: Optional[str] = Field(default=None, description="用户评语")
    created_at: datetime = Field(..., description="反馈提交时间")


class AdminFeedbackListResponse(BaseModel):
    """管理员反馈列表响应"""

    total: int = Field(..., description="符合条件的总记录数")
    items: List[AdminFeedbackItem] = Field(..., description="反馈列表")
