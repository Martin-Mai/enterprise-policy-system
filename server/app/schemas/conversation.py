"""
会话与历史消息数据模式模块
定义会话列表及消息查询的 Pydantic 响应模型
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConversationItem(BaseModel):
    """会话列表项"""

    id: int = Field(..., description="会话数据库 ID")
    session_id: str = Field(..., description="会话 UUID")
    title: Optional[str] = Field(default=None, description="会话标题")
    created_at: datetime = Field(..., description="创建时间")


class ConversationListResponse(BaseModel):
    """当前用户会话列表响应"""

    items: List[ConversationItem] = Field(..., description="会话列表，按时间倒序")


class MessageItem(BaseModel):
    """历史消息项"""

    id: int = Field(..., description="消息 ID")
    role: str = Field(..., description="消息角色：user / assistant")
    content: str = Field(..., description="消息正文")
    citations: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="引用来源元数据",
    )
    user_feedback: Optional[str] = Field(
        default=None,
        description='当前用户对该消息的赞踩状态："positive" | "negative" | null',
    )
    created_at: datetime = Field(..., description="创建时间")


class MessageListResponse(BaseModel):
    """指定会话的历史消息列表响应"""

    session_id: str = Field(..., description="会话 UUID")
    items: List[MessageItem] = Field(..., description="消息列表，按时间正序")
