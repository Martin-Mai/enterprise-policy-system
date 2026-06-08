"""
文档处理核心服务模块
负责文档解析、文本分块、Ollama 向量化及 ChromaDB 存储
"""

import asyncio
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import chromadb
import fitz  # PyMuPDF
import httpx
import markdown
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document, DocumentChunk

# 配置模块级日志
logger = logging.getLogger(__name__)


class ChromaDeleteError(Exception):
    """ChromaDB 向量删除失败时抛出，供 API 层转换为 503 响应"""


class DatabaseDeleteError(Exception):
    """MySQL 文档记录删除失败时抛出，供 API 层转换为 500 响应"""

# PDF 章节标题正则：匹配「第X章」「第X条」等常见中文法规格式
SECTION_TITLE_PATTERN = re.compile(
    r"(第[一二三四五六七八九十百千万零\d]+[章节条款节])"
)

# Markdown 标题行正则：匹配 # ~ ###### 开头的标题
MARKDOWN_HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")


# CJK 统一表意文字范围（含扩展 A 与兼容汉字）
_CJK_CHAR = r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]"
# 中文与全角标点之间常见的 PDF 断行
_CJK_PUNCT = r"[，。；：、（）【】《》「」『』]"


def clean_pdf_text(text: str) -> str:
    """
    清洗 PDF 提取的文本，去除中文字符间的多余换行符
    例如: "单\n笔\n超\n过" -> "单笔超过"
    """
    if not text:
        return text

    # 统一换行符，避免 \\r\\n 残留导致清洗失效
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 移除 CJK 字符之间的换行（PDF 竖排/逐字排版常见）
    cjk_break = re.compile(
        rf"(?<={_CJK_CHAR})\n(?={_CJK_CHAR})"
    )
    while True:
        cleaned = cjk_break.sub("", text)
        if cleaned == text:
            break
        text = cleaned

    # 移除 CJK 与全角标点之间的断行
    text = re.sub(rf"(?<={_CJK_CHAR})\n(?={_CJK_PUNCT})", "", text)
    text = re.sub(rf"(?<={_CJK_PUNCT})\n(?={_CJK_CHAR})", "", text)

    # 将剩余空白（含英文段落换行）折叠为单个空格
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _delete_chroma_vectors(doc_id: int) -> None:
    """
    从 ChromaDB 中删除指定文档的全部向量分块
    按 metadata 中的 doc_id 过滤，覆盖该文档所有 chunk_index，防止幽灵检索
    """
    collection = get_chroma_collection()
    try:
        collection.delete(where={"doc_id": doc_id})
        logger.info("ChromaDB 已按 doc_id=%s 清除向量数据", doc_id)
    except Exception as exc:
        # 部分 ChromaDB 版本对 where 条件支持不稳定，降级为按 id 列表删除
        logger.warning(
            "ChromaDB 按 doc_id 条件删除失败，尝试按 id 列表删除: doc_id=%s, error=%s",
            doc_id,
            exc,
        )
        try:
            existing = collection.get(where={"doc_id": doc_id}, include=[])
            ids = existing.get("ids") or []
            if ids:
                collection.delete(ids=ids)
                logger.info(
                    "ChromaDB 已通过 id 列表清除 doc_id=%s 的 %s 条向量",
                    doc_id,
                    len(ids),
                )
            else:
                logger.info("ChromaDB 中未找到 doc_id=%s 的向量，视为已清空", doc_id)
        except Exception as fallback_exc:
            logger.exception(
                "ChromaDB 删除 doc_id=%s 向量失败（含降级方案）: %s",
                doc_id,
                fallback_exc,
            )
            raise ChromaDeleteError(
                f"ChromaDB 连接或删除超时，doc_id={doc_id}"
            ) from fallback_exc


def _purge_document_chunks(db: Session, doc_id: int) -> None:
    """
    删除指定文档在 MySQL 与 ChromaDB 中的旧分块
    用于重新处理文档，避免检索命中未清洗的历史数据
    """
    _delete_chroma_vectors(doc_id)
    db.query(DocumentChunk).filter(DocumentChunk.doc_id == doc_id).delete()
    db.commit()


def _delete_physical_file(file_path: Optional[str]) -> bool:
    """
    物理删除磁盘上的文档源文件
    - 路径为空或文件不存在：记录警告并返回 False，不中断后续清理流程
    - 删除权限不足等 OS 错误：记录异常日志并抛出 OSError
    """
    if not file_path:
        logger.warning("文档 file_path 为空，跳过磁盘文件删除")
        return False

    if not os.path.exists(file_path):
        logger.warning("磁盘文件不存在，跳过删除: %s", file_path)
        return False

    try:
        os.remove(file_path)
        logger.info("已删除磁盘文件: %s", file_path)
        return True
    except OSError as exc:
        logger.exception("删除磁盘文件失败: %s, error=%s", file_path, exc)
        raise


def delete_document(db: Session, document: Document) -> Dict[str, Any]:
    """
    完整删除文档闭环：磁盘文件 -> ChromaDB 向量 -> MySQL 记录
    DocumentChunk 表由 documents 外键 ondelete=CASCADE 自动级联删除
    """
    doc_id = document.id
    file_path = document.file_path
    file_deleted = False

    # 步骤 1：清理磁盘上的源文件（文件缺失时不阻断后续流程）
    try:
        file_deleted = _delete_physical_file(file_path)
    except OSError:
        # 磁盘删除失败时仍尝试清理向量库与数据库，避免留下可检索的幽灵数据
        logger.warning(
            "磁盘文件删除失败，将继续清除 doc_id=%s 的向量与数据库记录",
            doc_id,
        )

    # 步骤 2：清除 ChromaDB 中该文档的全部向量（失败则中止，保留 MySQL 记录供重试）
    try:
        _delete_chroma_vectors(doc_id)
    except ChromaDeleteError:
        raise
    except Exception as exc:
        logger.exception("ChromaDB 清除 doc_id=%s 向量时发生未知错误: %s", doc_id, exc)
        raise ChromaDeleteError(f"ChromaDB 清除失败，doc_id={doc_id}") from exc

    # 步骤 3：删除 MySQL documents 记录（document_chunks 由 CASCADE 自动清空）
    try:
        db.delete(document)
        db.commit()
        logger.info("MySQL 已删除 doc_id=%s 的文档记录及关联分块", doc_id)
    except Exception as exc:
        db.rollback()
        logger.exception("MySQL 删除 doc_id=%s 失败: %s", doc_id, exc)
        raise DatabaseDeleteError(f"MySQL 删除失败，doc_id={doc_id}") from exc

    return {
        "doc_id": doc_id,
        "message": "文档已彻底删除",
        "file_deleted": file_deleted,
        "chroma_deleted": True,
    }


def get_chroma_collection():
    """
    获取或创建 ChromaDB 持久化集合
    集合名称由配置项 CHROMA_COLLECTION_NAME 指定
    """
    # 确保 ChromaDB 数据目录存在
    settings.CHROMA_DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(settings.CHROMA_DATA_DIR))
    collection = client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def parse_pdf(file_path: str) -> List[Dict[str, Any]]:
    """
    使用 PyMuPDF 按页解析 PDF 文档
    - 逐页提取中文文本
    - 页码从 1 开始
    - 通过正则识别章节标题并传递给后续分块
    """
    segments: List[Dict[str, Any]] = []
    current_section_title = ""

    doc = fitz.open(file_path)
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            page_no = page_index + 1  # 页码从 1 开始
            page_text = page.get_text("text") or ""
            page_text = clean_pdf_text(page_text)  # 清洗多余换行

            if not page_text.strip():
                continue

            # 逐行扫描，更新当前章节标题
            for line in page_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                match = SECTION_TITLE_PATTERN.search(line)
                if match:
                    current_section_title = match.group(1)

            segments.append(
                {
                    "text": page_text.strip(),
                    "page_no": page_no,
                    "section_title": current_section_title,
                }
            )
    finally:
        doc.close()

    return segments


def parse_markdown(file_path: str) -> List[Dict[str, Any]]:
    """
    解析 Markdown 文档
    - 使用 markdown 库将内容转为 HTML 后再提取纯文本
    - 通过 # 层级识别章节标题
    - Markdown 无物理页码，page_no 统一设为 0
    """
    raw_content = Path(file_path).read_text(encoding="utf-8")
    segments: List[Dict[str, Any]] = []
    current_section_title = ""
    current_lines: List[str] = []

    def flush_segment() -> None:
        """将当前累积的文本段落写入 segments 列表"""
        nonlocal current_lines
        if not current_lines:
            return
        plain_text = "\n".join(current_lines).strip()
        if plain_text:
            segments.append(
                {
                    "text": plain_text,
                    "page_no": 0,
                    "section_title": current_section_title,
                }
            )
        current_lines = []

    for line in raw_content.splitlines():
        header_match = MARKDOWN_HEADER_PATTERN.match(line.strip())
        if header_match:
            # 遇到新标题时，先保存上一段落
            flush_segment()
            # 提取标题文本作为当前章节名
            current_section_title = header_match.group(2).strip()
            current_lines.append(current_section_title)
            continue

        # 非标题行：转为纯文本后追加
        html = markdown.markdown(line)
        plain_line = re.sub(r"<[^>]+>", "", html).strip()
        if plain_line:
            current_lines.append(plain_line)

    flush_segment()
    return segments


def split_text_segments(
    segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    使用 LangChain RecursiveCharacterTextSplitter 对文本段落进行分块
    - chunk_size=500, chunk_overlap=50
    - 每个 chunk 继承来源段落的 page_no 和 section_title
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        length_function=len,
    )

    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for segment in segments:
        text = segment.get("text", "")
        if not text.strip():
            continue

        page_no = segment.get("page_no", 0)
        section_title = segment.get("section_title", "")

        for piece in splitter.split_text(text):
            piece = piece.strip()
            if not piece:
                continue
            chunks.append(
                {
                    "chunk_text": piece,
                    "chunk_index": chunk_index,
                    "page_no": page_no,
                    "section_title": section_title,
                }
            )
            chunk_index += 1

    return chunks


async def get_embedding(text: str) -> Optional[List[float]]:
    """
    调用 Ollama 嵌入 API 获取文本向量
    - 模型：nomic-embed-text
    - 使用 httpx.AsyncClient 异步请求
    - 包含异常捕获与日志记录
    """
    payload = {
        "model": settings.OLLAMA_EMBEDDING_MODEL,
        "prompt": text,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(settings.OLLAMA_EMBEDDING_URL, json=payload)
            response.raise_for_status()
            data = response.json()
            embedding = data.get("embedding")
            if not embedding:
                logger.error("Ollama 返回数据中缺少 embedding 字段: %s", data)
                return None
            return embedding
    except httpx.HTTPError as exc:
        logger.exception("调用 Ollama 向量化接口失败: %s", exc)
        return None
    except Exception as exc:
        logger.exception("向量化过程中发生未知错误: %s", exc)
        return None


def _parse_document(file_path: str, file_name: str) -> List[Dict[str, Any]]:
    """根据文件扩展名选择对应的解析器"""
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(file_path)
    if suffix == ".md":
        return parse_markdown(file_path)
    raise ValueError(f"不支持的文件类型: {suffix}")


async def _embed_and_store_chunks(
    db: Session,
    doc_id: int,
    file_name: str,
    chunks: List[Dict[str, Any]],
) -> None:
    """
    对分块进行向量化，并写入 ChromaDB 与 document_chunks 表
    """
    collection = get_chroma_collection()

    for chunk in chunks:
        chunk_index = chunk["chunk_index"]
        chunk_text = chunk["chunk_text"]
        page_no = chunk.get("page_no", 0)
        section_title = chunk.get("section_title", "")

        # 调用 Ollama 获取向量
        embedding = await get_embedding(chunk_text)
        if embedding is None:
            logger.warning(
                "文档 %s 分块 %s 向量化失败，跳过该分块",
                doc_id,
                chunk_index,
            )
            continue

        chunk_id = f"{doc_id}_{chunk_index}"
        metadata = {
            "doc_id": doc_id,
            "page_no": page_no,
            "section_title": section_title,
            "file_name": file_name,
        }

        # 写入 ChromaDB
        collection.upsert(
            ids=[chunk_id],
            embeddings=[embedding],
            documents=[chunk_text],
            metadatas=[metadata],
        )

        # 写入 MySQL document_chunks 表
        db_chunk = DocumentChunk(
            doc_id=doc_id,
            chunk_text=chunk_text,
            chunk_index=chunk_index,
            metadata_json=metadata,
        )
        db.add(db_chunk)

    db.commit()


def process_document_background(doc_id: int, file_path: str, file_name: str) -> None:
    """
    后台任务入口：解析文档并完成分块、向量化、入库
    注意：必须使用独立的 DB Session，保证线程安全
    """
    db = SessionLocal()
    try:
        logger.info("开始处理文档 doc_id=%s, file=%s", doc_id, file_name)

        # 确认文档记录存在
        document = db.query(Document).filter(Document.id == doc_id).first()
        if not document:
            logger.error("文档 doc_id=%s 不存在，终止处理", doc_id)
            return

        # 清除旧分块，避免重新处理时检索仍返回历史脏数据
        _purge_document_chunks(db, doc_id)

        # 解析文档为文本段落
        segments = _parse_document(file_path, file_name)
        if not segments:
            logger.warning("文档 doc_id=%s 未解析到有效文本", doc_id)
            return

        # 文本分块
        chunks = split_text_segments(segments)
        if not chunks:
            logger.warning("文档 doc_id=%s 分块结果为空", doc_id)
            return

        # 向量化并存储（在同步上下文中运行异步函数）
        asyncio.run(_embed_and_store_chunks(db, doc_id, file_name, chunks))

        logger.info(
            "文档 doc_id=%s 处理完成，共 %s 个分块",
            doc_id,
            len(chunks),
        )
    except Exception as exc:
        db.rollback()
        logger.exception("文档 doc_id=%s 后台处理失败: %s", doc_id, exc)
    finally:
        db.close()


async def search_documents(query: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """
    向量检索：将查询文本向量化后在 ChromaDB 中搜索相似分块
    返回包含 chunk_text、file_name、page_no、score 的结果列表
    """
    query_embedding = await get_embedding(query)
    if query_embedding is None:
        logger.error("检索关键词向量化失败: %s", query)
        return []

    collection = get_chroma_collection()

    # 集合为空时直接返回
    if collection.count() == 0:
        return []

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    search_items: List[Dict[str, Any]] = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for doc_text, metadata, distance in zip(documents, metadatas, distances):
        # ChromaDB 使用 cosine 距离，转换为相似度得分（1 - distance）
        score = round(max(0.0, 1.0 - float(distance)), 4)
        search_items.append(
            {
                "chunk_text": doc_text,
                "file_name": metadata.get("file_name", ""),
                "page_no": int(metadata.get("page_no", 0)),
                "score": score,
            }
        )

    return search_items