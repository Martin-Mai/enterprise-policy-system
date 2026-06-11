"""
文档数据模型模块
定义 documents 与 document_chunks 表的 ORM 映射
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Document(Base):
    """
    文档表 ORM 模型
    记录用户上传的 PDF / Markdown 文件元信息
    """

    __tablename__ = "documents"

    # 主键，自增整数
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 原始文件名
    file_name = Column(String(255), nullable=False, comment="原始文件名")

    # 文件在服务器上的存储路径
    file_path = Column(String(500), nullable=True, comment="文件存储路径")

    # 上传时间，默认为当前 UTC 时间
    upload_time = Column(DateTime, default=datetime.utcnow, comment="上传时间")

    # 上传者用户 ID，外键关联 users 表
    uploaded_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="上传者用户 ID",
    )

    # 文档生命周期状态：processing（处理中）/ active（正常）/ deleting（删除中）
    status = Column(
        String(20),
        nullable=False,
        default="active",
        index=True,
        comment="文档状态：processing / active / deleting",
    )

    # 关联的分块记录，删除文档时级联删除所有分块
    chunks = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentChunk(Base):
    """
    文档分块表 ORM 模型
    存储文本分块内容及元数据，便于检索与调试
    """

    __tablename__ = "document_chunks"

    # 主键，自增整数
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # 所属文档 ID，外键关联 documents 表，级联删除
    doc_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属文档 ID",
    )

    # 分块文本内容
    chunk_text = Column(Text, nullable=False, comment="分块文本内容")

    # 分块序号，从 0 开始递增
    chunk_index = Column(Integer, nullable=False, comment="分块序号")

    # 分块元数据（页码、章节标题等），以 JSON 格式存储
    metadata_json = Column(JSON, nullable=True, comment="分块元数据 JSON")

    # 反向关联到所属文档
    document = relationship("Document", back_populates="chunks")
