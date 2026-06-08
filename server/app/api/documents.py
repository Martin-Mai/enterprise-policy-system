"""
文档管理 API 路由模块
提供文档上传、列表查询与向量检索接口
"""

import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.document import (
    DocumentDeleteResponse,
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
    SearchResponse,
    SearchResultItem,
)
from app.services.document_processor import (
    ChromaDeleteError,
    DatabaseDeleteError,
    delete_document,
    process_document_background,
    search_documents,
)

router = APIRouter(prefix="/api/documents", tags=["文档管理"])

# 允许上传的文件扩展名
ALLOWED_EXTENSIONS = {".pdf", ".md"}


def _validate_upload_file(file: UploadFile, content: bytes) -> None:
    """
    校验上传文件类型与大小
    - 仅支持 .pdf / .md
    - 大小限制 10MB（可通过配置调整）
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持上传 .pdf 或 .md 文件",
        )

    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文件大小不能超过 {settings.MAX_UPLOAD_SIZE // (1024 * 1024)}MB",
        )


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="待上传的 PDF 或 Markdown 文件"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    上传文档接口（需登录）
    - 主线程：保存文件、写入 documents 表并立即返回 doc_id
    - 后台任务：解析、分块、向量化并写入 ChromaDB
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件名不能为空",
        )

    # 读取文件内容并校验
    content = await file.read()
    _validate_upload_file(file, content)

    # 确保存储目录存在
    settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    # 使用 UUID 生成唯一文件名，避免冲突
    suffix = Path(file.filename).suffix.lower()
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    stored_path = settings.STORAGE_DIR / stored_name

    # 将文件写入本地 storage 目录
    stored_path.write_bytes(content)

    # 插入 documents 表记录
    document = Document(
        file_name=file.filename,
        file_path=str(stored_path),
        uploaded_by=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # 提交后台任务：使用独立 DB Session 处理文档
    background_tasks.add_task(
        process_document_background,
        document.id,
        str(stored_path),
        file.filename,
    )

    return DocumentUploadResponse(
        doc_id=document.id,
        file_name=document.file_name,
        message="文档已上传，正在后台处理",
    )


@router.post("/{doc_id}/reprocess", response_model=DocumentUploadResponse)
async def reprocess_document(
    doc_id: int,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    重新处理已上传文档（需登录）
    清除旧分块后重新解析、分块并向量化，适用于修复历史脏数据
    """
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    if current_user.role != "admin" and document.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权重新处理该文档",
        )

    if not document.file_path or not Path(document.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文档源文件不存在，无法重新处理",
        )

    background_tasks.add_task(
        process_document_background,
        document.id,
        document.file_path,
        document.file_name,
    )

    return DocumentUploadResponse(
        doc_id=document.id,
        file_name=document.file_name,
        message="文档正在重新处理",
    )


@router.delete("/{doc_id}", response_model=DocumentDeleteResponse)
def delete_document_endpoint(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    删除文档接口（需登录）
    依次完成：权限校验 -> 磁盘文件清理 -> ChromaDB 向量擦除 -> MySQL 记录删除
    """
    # 【安全鉴权】先确认文档存在，再校验操作者是否有权删除
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文档不存在",
        )

    if current_user.role != "admin" and document.uploaded_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权删除该文档",
        )

    try:
        result = delete_document(db, document)
        return DocumentDeleteResponse(**result)
    except ChromaDeleteError as exc:
        # 向量库不可用或删除超时：保留 MySQL 记录，便于用户稍后重试
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"向量库清除失败，请稍后重试: {exc}",
        ) from exc
    except DatabaseDeleteError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"数据库删除失败: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文档删除过程中发生未知错误",
        ) from exc


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    分页查询文档列表（需登录）
    普通用户仅能看到自己上传的文档，管理员可查看全部
    """
    query = db.query(Document)

    # 非管理员只能查看自己上传的文档
    if current_user.role != "admin":
        query = query.filter(Document.uploaded_by == current_user.id)

    total = query.count()
    items = (
        query.order_by(Document.upload_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return DocumentListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[DocumentResponse.model_validate(item) for item in items],
    )


@router.get("/search", response_model=SearchResponse)
async def search_document_chunks(
    q: str = Query(..., min_length=1, description="检索关键词"),
    current_user: User = Depends(get_current_user),
):
    """
    向量检索接口（需登录）
    在 ChromaDB 中搜索与关键词最相关的 5 个文本分块
    """
    # q 参数仅用于校验登录态，检索本身基于向量相似度
    _ = current_user

    results = await search_documents(query=q, n_results=5)

    return SearchResponse(
        query=q,
        results=[SearchResultItem(**item) for item in results],
    )
