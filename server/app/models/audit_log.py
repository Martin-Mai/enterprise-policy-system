"""
审计日志数据模型模块
定义 audit_logs 表的 ORM 映射，记录每次 RAG 问答的全链路追溯信息
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class AuditLog(Base):
    """
    审计日志表 ORM 模型
    存储用户提问、检索分块、模型回答及引用等完整审计轨迹
    """

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="提问用户 ID",
    )

    question = Column(Text, nullable=False, comment="用户原始提问")

    retrieved_chunks = Column(
        JSON,
        nullable=False,
        comment="混合检索 Top-5 分块完整结构（含 chunk_id、text、file_name 等）",
    )

    answer = Column(Text, nullable=False, comment="大模型生成的完整回答")

    citations = Column(
        JSON,
        nullable=True,
        comment="解析并使用的有效引用列表",
    )

    confidence_score = Column(
        Float,
        nullable=True,
        comment="Top-1 检索置信度分数（rerank_score 或 final_rrf_score）",
    )

    gate_decision = Column(
        String(16),
        nullable=True,
        comment="置信度门控决策：normal / cautious / refuse",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        comment="审计记录创建时间",
    )

    user = relationship("User", backref="audit_logs")
