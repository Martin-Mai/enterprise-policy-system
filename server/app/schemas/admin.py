"""
管理员仪表盘与文档管理 Pydantic 数据模型
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AdminStatsResponse(BaseModel):
    """仪表盘核心统计数据"""

    total_documents: int = Field(..., description="文档总数（不含删除中）")
    total_users: int = Field(..., description="注册用户总数")
    today_qa_count: int = Field(..., description="今日问答次数")
    positive_rate: float = Field(..., description="综合好评率（0~100 百分比）")
    weekly_qa: List[int] = Field(..., description="近 7 天每日问答量，从最早到最近")
    feedback_stats: Dict[str, int] = Field(
        ...,
        description="反馈统计，含 positive / negative 计数",
    )


class HotDocumentItem(BaseModel):
    """热门引用文档项"""

    file_name: str = Field(..., description="文档文件名")
    citation_count: int = Field(..., description="被 RAG 引用总次数")


class HotDocumentsResponse(BaseModel):
    """热门文档 Top 5 响应"""

    items: List[HotDocumentItem] = Field(default_factory=list, description="热门文档列表")


class AdminDeleteProcessingResponse(BaseModel):
    """异步删除受理响应"""

    status: str = Field(default="processing", description="处理状态")
    message: str = Field(..., description="提示信息")


class AdminDocumentItem(BaseModel):
    """管理员文档列表项"""

    id: int = Field(..., description="文档 ID")
    file_name: str = Field(..., description="原始文件名")
    upload_time: datetime = Field(..., description="上传时间")
    uploader_name: str = Field(..., description="上传者用户名")
    chunk_count: int = Field(..., description="分块数量")
    status: str = Field(..., description="文档状态：active / processing / deleting")


class AdminDocumentListResponse(BaseModel):
    """管理员文档分页列表"""

    total: int = Field(..., description="文档总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页条数")
    items: List[AdminDocumentItem] = Field(default_factory=list, description="文档列表")


class AdminAuditLogDetail(BaseModel):
    """审计日志详情（含完整检索源数据）"""

    id: int = Field(..., description="审计记录 ID")
    username: str = Field(..., description="提问用户用户名")
    question: str = Field(..., description="用户原始提问")
    answer: str = Field(..., description="模型完整回答")
    retrieved_chunks: List[Dict[str, Any]] = Field(
        ...,
        description="混合检索 Top-5 分块完整结构",
    )
    citations: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="解析并使用的有效引用列表",
    )
    created_at: datetime = Field(..., description="审计记录创建时间")


class FeedbackProcessedResponse(BaseModel):
    """反馈标记已处理响应"""

    id: int = Field(..., description="反馈记录 ID")
    is_processed: bool = Field(..., description="是否已处理")
    message: str = Field(default="已标记为已处理", description="操作结果提示")


class DocumentReindexResponse(BaseModel):
    """文档重新向量化响应（骨架接口）"""

    status: str = Field(default="success", description="处理状态")
    message: str = Field(..., description="操作结果提示")


class AdminClearAuditLogsResponse(BaseModel):
    """清空审计日志响应"""

    status: str = Field(default="success", description="处理状态")
    message: str = Field(..., description="操作结果提示")
