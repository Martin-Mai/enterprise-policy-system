"""
文档相关 Pydantic 数据模型
用于 API 请求/响应的数据校验与序列化
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    """文档详情响应模型"""

    id: int = Field(..., description="文档 ID")
    file_name: str = Field(..., description="原始文件名")
    file_path: Optional[str] = Field(None, description="文件存储路径")
    upload_time: datetime = Field(..., description="上传时间")
    uploaded_by: int = Field(..., description="上传者用户 ID")

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """文档分页列表响应模型"""

    total: int = Field(..., description="文档总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页条数")
    items: List[DocumentResponse] = Field(..., description="文档列表")


class DocumentUploadResponse(BaseModel):
    """文档上传成功响应模型"""

    doc_id: int = Field(..., description="新创建文档 ID")
    file_name: str = Field(..., description="原始文件名")
    message: str = Field(default="文档已上传，正在后台处理", description="提示信息")


class DocumentDeleteResponse(BaseModel):
    """文档删除成功响应模型"""

    doc_id: int = Field(..., description="已删除的文档 ID")
    message: str = Field(default="文档已彻底删除", description="提示信息")
    file_deleted: bool = Field(..., description="磁盘源文件是否已成功删除")
    chroma_deleted: bool = Field(..., description="ChromaDB 向量是否已清除")


class SearchResultItem(BaseModel):
    """单条向量检索结果"""

    chunk_text: str = Field(..., description="匹配的分块文本")
    file_name: str = Field(..., description="来源文件名")
    page_no: int = Field(..., description="页码（Markdown 文件默认为 0）")
    score: float = Field(..., description="相似度得分，越高越相关")


class SearchResponse(BaseModel):
    """向量检索响应模型"""

    query: str = Field(..., description="检索关键词")
    results: List[SearchResultItem] = Field(default_factory=list, description="检索结果列表")
