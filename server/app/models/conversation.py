"""
会话数据模型模块
定义 conversations 表的 ORM 映射
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base


class Conversation(Base):
    """
    会话表 ORM 模型
    记录用户的多轮对话会话元信息
    """

    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="所属用户 ID",
    )

    session_id = Column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        comment="会话 UUID",
    )

    title = Column(String(255), nullable=True, comment="会话标题")

    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")

    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
