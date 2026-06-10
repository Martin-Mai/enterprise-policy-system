"""
用户反馈数据模型模块
定义 feedbacks 表的 ORM 映射，记录用户对 AI 回答的赞踩及评语
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Feedback(Base):
    """
    用户反馈表 ORM 模型
    每个用户对每条 AI 消息仅允许存在一条反馈（联合唯一约束）
    """

    __tablename__ = "feedbacks"

    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="unique_user_message"),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    message_id = Column(
        Integer,
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="被评价的 AI 消息 ID",
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="提交反馈的用户 ID",
    )

    is_positive = Column(
        Boolean,
        nullable=False,
        comment="True=点赞，False=点踩",
    )

    comment = Column(
        Text,
        nullable=True,
        comment="用户具体评语或吐槽，可为空",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        comment="反馈提交时间",
    )

    message = relationship("Message", backref="feedbacks")
    user = relationship("User", backref="feedbacks")
