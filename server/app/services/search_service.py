"""
混合检索服务模块
实现 ChromaDB 语义召回 + BM25 关键词召回 + RRF 倒数排名融合
"""

import logging
import re
import asyncio
from typing import Any, Dict, List, Optional, Tuple

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document, DocumentChunk
from app.services.document_processor import get_chroma_collection, get_embedding
from app.services.rerank_service import rerank_candidates

logger = logging.getLogger(__name__)

# RRF 融合常数 k
RRF_K: int = 60

# 短文本过滤阈值（字符数）；parent_child 下作用于 child 文本
MIN_CHUNK_LENGTH: int = 20
# BM25 索引长度上限见 settings.SEARCH_MAX_CHUNK_LENGTH（默认 800，应 >= CHILD_CHUNK_SIZE）

# 加权RRF权重
BM25_WEIGHT = 0.7
VECTOR_WEIGHT = 0.3

# 向量检索最低相似度阈值
MIN_VECTOR_SCORE = 0.45

# 业务核心关键词
CORE_BUSINESS_KEYWORDS = ["绩效", "考核", "等级", "D档", "S档", "A档", "B档", "C档", "强制分布"]

# 全局文本清洗正则
NOISE_PATTERNS = [
    re.compile(r"【压力测试专用.*?】"),
    re.compile(r"第 \d+ 页 / 共 \d+ 页"),
    re.compile(r"第 \d+页"),
    re.compile(r"\s+"),
]

def clean_text(text: str) -> str:
    """全局文本清洗函数"""
    if not text:
        return ""
    cleaned = text.strip()
    for pattern in NOISE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    return cleaned.strip()

def _tokenize(text: str) -> List[str]:
    """使用 jieba 对中文文本分词"""
    text = clean_text(text)
    return list(jieba.cut(text))

def _is_parent_child_mode() -> bool:
    return settings.CHUNK_STRATEGY == "parent_child"

def _max_index_chunk_length() -> int:
    return settings.SEARCH_MAX_CHUNK_LENGTH

def _extract_chunk_metadata(chunk: DocumentChunk) -> Dict[str, Any]:
    meta = chunk.metadata_json or {}
    result = {
        "doc_id": chunk.doc_id,
        "chunk_index": chunk.chunk_index,
        "file_name": str(meta.get("file_name", "")),
        "page_no": int(meta.get("page_no", 0)),
        "section_title": str(meta.get("section_title", "")),
    }
    chunk_role = meta.get("chunk_role")
    if chunk_role is not None:
        result["chunk_role"] = str(chunk_role)
    parent_chunk_index = meta.get("parent_chunk_index")
    if parent_chunk_index is not None:
        result["parent_chunk_index"] = int(parent_chunk_index)
    return result

def _resolve_mysql_chunk_id(
    chroma_id: str,
    metadata: Optional[Dict[str, Any]],
) -> str:
    """解析 Chroma 返回的 ID 为 MySQL 主键（优化：避免高频同步查库）"""
    meta = metadata or {}
    mysql_chunk_id = meta.get("mysql_chunk_id")
    if mysql_chunk_id is not None:
        return str(mysql_chunk_id)
    if str(chroma_id).isdigit():
        return str(chroma_id)
    
    doc_id = meta.get("doc_id")
    chunk_index = meta.get("chunk_index")
    if doc_id is not None and chunk_index is not None:
        # ⚠️ 警告：进入此分支说明写入 Chroma 时未带上 mysql_chunk_id 字段。
        # 生产环境下建议在数据导入时强制写入 mysql_chunk_id，彻底根治此处同步查库的隐患。
        db: Session = SessionLocal()
        try:
            chunk = (
                db.query(DocumentChunk)
                .filter(
                    DocumentChunk.doc_id == int(doc_id),
                    DocumentChunk.chunk_index == int(chunk_index),
                )
                .first()
            )
            if chunk is not None:
                return str(chunk.id)
        finally:
            db.close()
    return str(chroma_id)

class BM25Index:
    """BM25 内存索引单例（热更新与业务过滤完美结合版）"""

    _instance: Optional["BM25Index"] = None

    def __new__(cls) -> "BM25Index":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._bm25: Optional[BM25Okapi] = None
        self._chunk_ids: List[str] = []
        self._chunk_texts: List[str] = []
        self._chunk_metadata: Dict[str, Dict[str, Any]] = {}
        self._parent_texts: Dict[Tuple[int, int], str] = {}
        self._initialized = True
        self.refresh_index()

    def refresh_index(self) -> None:
        """无缝热更新索引（自动排除 deleting 状态文档的分块）"""
        db: Session = SessionLocal()
        try:
            chunks = (
                db.query(DocumentChunk)
                .join(Document, DocumentChunk.doc_id == Document.id)
                .filter(Document.status == "active")
                .order_by(DocumentChunk.id.asc())
                .all()
            )
            if not chunks:
                logger.info("[BM25Index] MySQL 为空，跳过索引构建")
                return

            new_chunk_ids: List[str] = []
            new_chunk_texts: List[str] = []
            new_chunk_metadata: Dict[str, Dict[str, Any]] = {}
            new_parent_texts: Dict[Tuple[int, int], str] = {}
            tokenized_corpus: List[List[str]] = []
            skipped_count = 0
            max_chunk_length = _max_index_chunk_length()
            parent_child_mode = _is_parent_child_mode()

            for chunk in chunks:
                meta = chunk.metadata_json or {}
                chunk_role = meta.get("chunk_role")

                if parent_child_mode:
                    if chunk_role == "parent":
                        parent_idx = meta.get("parent_chunk_index")
                        if parent_idx is not None:
                            new_parent_texts[(chunk.doc_id, int(parent_idx))] = clean_text(
                                chunk.chunk_text
                            )
                        continue
                    if chunk_role != "child":
                        skipped_count += 1
                        continue

                chunk_text = clean_text(chunk.chunk_text)
                if "压力测试专用" in chunk_text and len(chunk_text) > max_chunk_length:
                    skipped_count += 1
                    continue
                if len(chunk_text) < MIN_CHUNK_LENGTH or len(chunk_text) > max_chunk_length:
                    skipped_count += 1
                    continue

                chunk_id = str(chunk.id)
                new_chunk_ids.append(chunk_id)
                new_chunk_texts.append(chunk_text)
                new_chunk_metadata[chunk_id] = _extract_chunk_metadata(chunk)
                tokenized_corpus.append(_tokenize(chunk_text))

            if skipped_count > 0:
                logger.info("[BM25Index] 已跳过 %d 个噪声/超长/过短文本块", skipped_count)
            if not tokenized_corpus:
                logger.warning("[BM25Index] 过滤后无可索引文本块")
                return

            new_bm25 = BM25Okapi(tokenized_corpus)
            
            # 原子性替换引用，确保线上无缝切换
            self._bm25 = new_bm25
            self._chunk_ids = new_chunk_ids
            self._chunk_texts = new_chunk_texts
            self._chunk_metadata = new_chunk_metadata
            self._parent_texts = new_parent_texts
            
            logger.info(
                "[BM25Index] 索引热刷新完成，当前共有 %d 个文本块，parent 缓存 %d 条",
                len(self._chunk_ids),
                len(self._parent_texts),
            )
        except Exception as exc:
            logger.exception("[BM25Index] 索引刷新失败: %s", exc)
        finally:
            db.close()

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """基于大候选池的业务硬过滤检索（防止过早截断）"""
        if not self._bm25 or not self._chunk_ids:
            return []

        try:
            query = clean_text(query)
            query_tokens = _tokenize(query)
            if not query_tokens:
                return []

            scores = self._bm25.get_scores(query_tokens)
            ranked_indices = sorted(range(len(scores)), key=lambda idx: scores[idx], reverse=True)

            results: List[Dict[str, Any]] = []
            has_core_kw = any(kw in query for kw in CORE_BUSINESS_KEYWORDS)

            for idx in ranked_indices:
                if len(results) >= limit:
                    break
                score = float(scores[idx])
                if score <= 0:
                    continue

                chunk_text = self._chunk_texts[idx]
                # 硬性过滤
                if has_core_kw and not any(kw in chunk_text for kw in CORE_BUSINESS_KEYWORDS):
                    continue

                chunk_id = self._chunk_ids[idx]
                results.append({
                    "chunk_id": chunk_id,
                    "text": chunk_text,
                    "score": round(score, 4),
                    "metadata": self._chunk_metadata.get(chunk_id, {}),
                })
            return results
        except Exception as exc:
            logger.exception("[BM25Index] 检索失败: %s", exc)
            return []

    def get_chunk_info(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        if chunk_id not in self._chunk_metadata:
            return None
        try:
            idx = self._chunk_ids.index(chunk_id)
            return {"text": self._chunk_texts[idx], **self._chunk_metadata[chunk_id]}
        except ValueError:
            return None

    def get_parent_text(self, doc_id: int, parent_chunk_index: int) -> Optional[str]:
        """parent_child 模式下按 doc_id + parent_chunk_index 取 parent 文本"""
        return self._parent_texts.get((doc_id, parent_chunk_index))

def get_bm25_index() -> BM25Index:
    return BM25Index()


def _chroma_query_rows(results: Dict[str, Any], field: str) -> List[Any]:
    """从 Chroma query 结果中安全取出单 query 对应的结果行（Chroma 可能返回 null）"""
    value = results.get(field)
    if not value or not isinstance(value, (list, tuple)):
        return []
    first = value[0]
    return list(first) if first is not None else []


async def chroma_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """ChromaDB 语义召回（过滤 deleting 状态文档）"""
    try:
        query = clean_text(query)
        query_embedding = await get_embedding(query)
        if query_embedding is None:
            return []

        collection = get_chroma_collection()
        if collection.count() == 0:
            return []

        # 获取 deleting 状态文档 ID，用于过滤幽灵检索
        deleting_doc_ids: set[int] = set()
        db: Session = SessionLocal()
        try:
            rows = (
                db.query(Document.id)
                .filter(Document.status == "deleting")
                .all()
            )
            deleting_doc_ids = {row[0] for row in rows}
        finally:
            db.close()

        # 扩大检索深度，给后续的硬阈值过滤留足缓冲空间
        search_limit = max(limit * 3, 30)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=search_limit,
            include=["documents", "metadatas", "distances"],
        )

        search_items: List[Dict[str, Any]] = []

        if not results:
            return []

        ids = _chroma_query_rows(results, "ids")
        documents = _chroma_query_rows(results, "documents")
        metadatas = _chroma_query_rows(results, "metadatas")
        distances = _chroma_query_rows(results, "distances")

        if not ids or not documents:
            return []

        if len(distances) < len(ids):
            distances = list(distances) + [1.0] * (len(ids) - len(distances))
        if len(metadatas) < len(ids):
            metadatas = list(metadatas) + [{}] * (len(ids) - len(metadatas))

        parent_child_mode = _is_parent_child_mode()

        for chunk_id, doc_text, metadata, distance in zip(ids, documents, metadatas, distances):
            if len(search_items) >= limit:
                break

            meta = metadata or {}
            if parent_child_mode and meta.get("chunk_role") != "child":
                continue

            doc_id = meta.get("doc_id")
            if doc_id is not None and int(doc_id) in deleting_doc_ids:
                continue

            doc_text = clean_text(doc_text)
            dist_val = float(distance)

            score = round(1.0 - dist_val if dist_val <= 1.0 else max(0.0, 1.0 - (dist_val / 2)), 4)

            if score < MIN_VECTOR_SCORE:
                continue

            # 统一解析 chunk_id
            real_chunk_id = _resolve_mysql_chunk_id(str(chunk_id), meta)

            search_items.append({
                "chunk_id": str(real_chunk_id),
                "text": doc_text,
                "score": score,
                "metadata": meta,
            })
        return search_items
    except Exception as exc:
        logger.exception("[ChromaSearch] 检索失败: %s", exc)
        return []

def rrf_fusion(
    chroma_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    limit: int = 5,
    k: int = RRF_K,
) -> List[Dict[str, Any]]:
    """加权 RRF 双路融合（已修复 chunk_id 覆盖 Bug）"""
    rrf_scores: Dict[str, float] = {}
    result_cache: Dict[str, Dict[str, Any]] = {}

    # 向量检索分支
    for rank, item in enumerate(chroma_results, start=1):
        chunk_id = str(item["chunk_id"])
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + VECTOR_WEIGHT * (1.0 / (k + rank))
        result_cache.setdefault(chunk_id, item)

    # BM25检索分支（🛠️ 已修复：正确读取 item["chunk_id"]）
    for rank, item in enumerate(bm25_results, start=1):
        chunk_id = str(item["chunk_id"])
        rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + BM25_WEIGHT * (1.0 / (k + rank))
        result_cache.setdefault(chunk_id, item)

    sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)[:limit]

    fused: List[Dict[str, Any]] = []
    for chunk_id in sorted_ids:
        cached = result_cache.get(chunk_id, {})
        fused.append({
            "chunk_id": chunk_id,
            "final_rrf_score": round(rrf_scores[chunk_id], 6),
            "text": cached.get("text", ""),
            "metadata": cached.get("metadata", {}),
        })
    return fused

def _enrich_results(fused_results: List[Dict[str, Any]], bm25_index: BM25Index) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    parent_child_mode = _is_parent_child_mode()

    for item in fused_results:
        chunk_id = str(item["chunk_id"])
        chunk_info = bm25_index.get_chunk_info(chunk_id)
        metadata = item.get("metadata") or {}

        if chunk_info:
            child_text = chunk_info["text"]
            file_name = chunk_info["file_name"]
            page_no = chunk_info["page_no"]
            section_title = chunk_info["section_title"]
            doc_id = int(chunk_info.get("doc_id", metadata.get("doc_id", 0)))
            parent_chunk_index = chunk_info.get("parent_chunk_index", metadata.get("parent_chunk_index"))
        else:
            child_text = item.get("text", "")
            file_name = str(metadata.get("file_name", ""))
            page_no = int(metadata.get("page_no", 0))
            section_title = str(metadata.get("section_title", ""))
            doc_id = int(metadata.get("doc_id", 0))
            parent_chunk_index = metadata.get("parent_chunk_index")

        if parent_child_mode:
            if parent_chunk_index is not None:
                parent_chunk_index = int(parent_chunk_index)
            parent_text = (
                bm25_index.get_parent_text(doc_id, parent_chunk_index)
                if parent_chunk_index is not None
                else None
            )
            llm_text = parent_text if parent_text else child_text
            if parent_chunk_index is not None and not parent_text:
                logger.warning(
                    "[HybridSearch] 未找到 parent 文本 | doc_id=%s parent_chunk_index=%s child_id=%s",
                    doc_id,
                    parent_chunk_index,
                    chunk_id,
                )

            row = {
                "chunk_id": chunk_id,
                "text": llm_text,
                "child_text": child_text,
                "chunk_role": "child",
                "parent_chunk_index": parent_chunk_index,
                "final_rrf_score": item["final_rrf_score"],
                "file_name": file_name,
                "page_no": page_no,
                "section_title": section_title,
            }
            if "rerank_score" in item:
                row["rerank_score"] = item["rerank_score"]
            enriched.append(row)
            continue

        row = {
            "chunk_id": chunk_id,
            "text": child_text,
            "final_rrf_score": item["final_rrf_score"],
            "file_name": file_name,
            "page_no": page_no,
            "section_title": section_title,
        }
        if "rerank_score" in item:
            row["rerank_score"] = item["rerank_score"]
        enriched.append(row)
    return enriched

async def _coarse_candidates(
    query: str, final_k: int
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """粗排候选池：双路 Top-N 召回 + RRF 融合（阶段 B 用 RRF 分占位）"""
    per_route_limit = max(settings.SEARCH_COARSE_RECALL_LIMIT, final_k * 2)
    chroma_hits, bm25_hits = await _parallel_retrieve(query, per_route_limit)

    if not chroma_hits and not bm25_hits:
        return [], chroma_hits, bm25_hits

    fused = rrf_fusion(chroma_hits, bm25_hits, limit=per_route_limit)
    fused = [r for r in fused if len(r.get("text", "").strip()) >= MIN_CHUNK_LENGTH]
    candidates = fused[:per_route_limit]
    return candidates, chroma_hits, bm25_hits


async def _select_for_llm(
    query: str, candidates: List[Dict[str, Any]], k: int
) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    return await run_in_threadpool(rerank_candidates, query, candidates, k)


async def hybrid_search(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """双路混合检索主入口"""
    try:
        candidates, chroma_hits, bm25_hits = await _coarse_candidates(query, final_k=limit)
        selected = await _select_for_llm(query, candidates, k=limit)

        logger.info(
            "[HybridSearch] Query: %s | Coarse: %d | Rerank: %d | Chroma Hits: %d | BM25 Hits: %d",
            query,
            len(candidates),
            len(selected),
            len(chroma_hits),
            len(bm25_hits),
        )
        if not selected:
            return []

        return _enrich_results(selected, get_bm25_index())
    except Exception as exc:
        logger.exception("[HybridSearch] 混合检索失败: %s", exc)
        return []

async def _parallel_retrieve(query: str, limit: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """并行执行双路召回（BM25 进线程池避免阻塞）"""
    bm25_index = get_bm25_index()
    chroma_task = chroma_search(query, limit=limit)
    bm25_task = asyncio.to_thread(bm25_index.search, query, limit=limit)
    chroma_results, bm25_results = await asyncio.gather(chroma_task, bm25_task)
    return chroma_results, bm25_results
