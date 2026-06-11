"""
消息数据模型模块
定义 messages 表的 ORM 映射
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Message(Base):
    """
    消息表 ORM 模型
    存储会话中的用户与助手消息及引用元数据
    """

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属会话 ID",
    )

    role = Column(String(16), nullable=False, comment="消息角色：user / assistant")

    content = Column(Text, nullable=False, comment="消息完整文本")

    citations = Column(JSON, nullable=True, comment="引用元数据 JSON 数组")

    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    conversation = relationship("Conversation", back_populates="messages")
    feedbacks = relationship(
        "Feedback",
        back_populates="message",
        cascade="all, delete-orphan",
    )
