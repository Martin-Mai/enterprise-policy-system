"""
ChromaDB 向量 ID 迁移脚本

将旧格式 ID（{doc_id}_{chunk_index}）迁移为 MySQL document_chunks 表主键 id（字符串）。

用法（在 server 目录下执行）：
    python -m scripts.migrate_chroma_chunk_ids

可选参数：
    --dry-run   仅预览迁移计划，不实际写入 ChromaDB
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

# 确保可从 server 根目录导入 app 包
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.core.database import SessionLocal
from app.models.document import DocumentChunk
from app.services.document_processor import get_chroma_collection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# 旧 ID 格式：{doc_id}_{chunk_index}，例如 5_0、12_3
OLD_ID_PATTERN = re.compile(r"^(\d+)_(\d+)$")


def _is_new_format_id(chroma_id: str) -> bool:
    """新格式 ID 为纯数字字符串，对应当前 MySQL 主键"""
    return chroma_id.isdigit()


def _parse_old_id(chroma_id: str) -> Optional[Tuple[int, int]]:
    """解析旧格式 ID，返回 (doc_id, chunk_index)"""
    match = OLD_ID_PATTERN.match(chroma_id)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _lookup_mysql_chunk_id(doc_id: int, chunk_index: int) -> Optional[int]:
    """根据 doc_id + chunk_index 查找 MySQL document_chunks 主键"""
    db = SessionLocal()
    try:
        chunk = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.doc_id == doc_id,
                DocumentChunk.chunk_index == chunk_index,
            )
            .first()
        )
        return chunk.id if chunk else None
    finally:
        db.close()


def migrate_chroma_ids(dry_run: bool = False) -> Dict[str, int]:
    """
    执行 ChromaDB ID 迁移
    返回统计信息：total / migrated / skipped / failed / orphaned
    """
    collection = get_chroma_collection()
    existing = collection.get(include=["embeddings", "documents", "metadatas"])

    ids: List[str] = existing.get("ids") or []
    embeddings = existing.get("embeddings") or []
    documents = existing.get("documents") or []
    metadatas = existing.get("metadatas") or []

    stats = {
        "total": len(ids),
        "migrated": 0,
        "skipped": 0,
        "failed": 0,
        "orphaned": 0,
    }

    if not ids:
        logger.info("ChromaDB 集合为空，无需迁移")
        return stats

    for chroma_id, embedding, document, metadata in zip(
        ids, embeddings, documents, metadatas
    ):
        if _is_new_format_id(chroma_id):
            stats["skipped"] += 1
            continue

        parsed = _parse_old_id(chroma_id)
        if parsed is None:
            logger.warning("无法识别的 Chroma ID 格式，跳过: %s", chroma_id)
            stats["failed"] += 1
            continue

        doc_id, chunk_index = parsed
        mysql_id = _lookup_mysql_chunk_id(doc_id, chunk_index)
        if mysql_id is None:
            logger.warning(
                "MySQL 中未找到对应分块，标记为孤立向量: chroma_id=%s, doc_id=%s, chunk_index=%s",
                chroma_id,
                doc_id,
                chunk_index,
            )
            stats["orphaned"] += 1
            if not dry_run:
                collection.delete(ids=[chroma_id])
            continue

        new_id = str(mysql_id)
        new_metadata: Dict[str, Any] = dict(metadata or {})
        new_metadata.setdefault("doc_id", doc_id)
        new_metadata.setdefault("chunk_index", chunk_index)
        new_metadata["mysql_chunk_id"] = mysql_id

        if dry_run:
            logger.info(
                "[DRY-RUN] %s -> %s (doc_id=%s, chunk_index=%s)",
                chroma_id,
                new_id,
                doc_id,
                chunk_index,
            )
            stats["migrated"] += 1
            continue

        try:
            collection.delete(ids=[chroma_id])
            collection.upsert(
                ids=[new_id],
                embeddings=[embedding],
                documents=[document],
                metadatas=[new_metadata],
            )
            logger.info("已迁移: %s -> %s", chroma_id, new_id)
            stats["migrated"] += 1
        except Exception as exc:
            logger.exception("迁移失败: %s -> %s, error=%s", chroma_id, new_id, exc)
            stats["failed"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="迁移 ChromaDB 向量 ID 至 MySQL 主键格式")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅预览迁移计划，不实际修改 ChromaDB",
    )
    args = parser.parse_args()

    logger.info("开始 ChromaDB ID 迁移（dry_run=%s）", args.dry_run)
    stats = migrate_chroma_ids(dry_run=args.dry_run)
    logger.info(
        "迁移完成 | total=%s migrated=%s skipped=%s failed=%s orphaned=%s",
        stats["total"],
        stats["migrated"],
        stats["skipped"],
        stats["failed"],
        stats["orphaned"],
    )


if __name__ == "__main__":
    main()
