"""
聊天数据模式模块
定义流式问答接口的请求与响应 Pydantic 模型
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """流式问答请求模型"""

    session_id: Optional[str] = Field(default=None, description="会话 ID，为空时后端自动生成")
    question: str = Field(..., min_length=1, description="用户问题")


class Citation(BaseModel):
    """引用来源元数据"""

    chunk_id: str = Field(..., description="分块 ID")
    file_name: str = Field(..., description="文档文件名")
    page_no: int = Field(..., description="页码")
    section_title: str = Field(..., description="章节标题")
    text_preview: str = Field(..., description="分块文本预览（前 200 字符）")
    inferred: Optional[bool] = Field(
        default=None,
        description="是否为模型未标注引用时的自动推断",
    )
