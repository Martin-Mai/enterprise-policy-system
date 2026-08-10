"""
重建文档索引脚本

按当前 CHUNK_STRATEGY 与分块参数，对 active 文档重新 parse → split → embed。
适用于切换 flat / parent_child 策略或调整 CHUNK_* 参数后批量重建。

用法（在 server 目录下执行）：
    python -m scripts.reindex_all_documents
    python -m scripts.reindex_all_documents --doc-id 3
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List

SERVER_DIR = Path(__file__).resolve().parent.parent
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document, DocumentChunk
from app.services.document_processor import process_document_background
from app.services.search_service import get_bm25_index

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def _load_active_doc_ids(single_doc_id: int | None) -> List[int]:
    db = SessionLocal()
    try:
        if single_doc_id is not None:
            document = (
                db.query(Document)
                .filter(Document.id == single_doc_id, Document.status == "active")
                .first()
            )
            if document is None:
                logger.error("doc_id=%s 不存在或 status 非 active", single_doc_id)
                return []
            return [single_doc_id]

        rows = (
            db.query(Document.id)
            .filter(Document.status == "active")
            .order_by(Document.id.asc())
            .all()
        )
        return [row[0] for row in rows]
    finally:
        db.close()


def reindex_one(doc_id: int) -> bool:
    """重建单文档索引，成功返回 True"""
    db = SessionLocal()
    try:
        document = (
            db.query(Document)
            .filter(Document.id == doc_id, Document.status == "active")
            .first()
        )
        if document is None:
            logger.error("doc_id=%s 不存在或非 active，跳过", doc_id)
            return False
        if not document.file_path or not Path(document.file_path).exists():
            logger.error(
                "doc_id=%s 源文件不存在，跳过 | file_path=%s",
                doc_id,
                document.file_path,
            )
            return False
        file_path = document.file_path
        file_name = document.file_name
    finally:
        db.close()

    logger.info(
        "开始重建 doc_id=%s file=%s | strategy=%s",
        doc_id,
        file_name,
        settings.CHUNK_STRATEGY,
    )
    try:
        process_document_background(doc_id, file_path, file_name)
    except Exception:
        logger.exception("doc_id=%s 重建过程异常", doc_id)
        return False

    db = SessionLocal()
    try:
        chunk_count = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.doc_id == doc_id)
            .count()
        )
        if chunk_count == 0:
            logger.error("doc_id=%s 重建后无分块，视为失败", doc_id)
            return False
        logger.info("doc_id=%s 重建成功，共 %d 个分块", doc_id, chunk_count)
        return True
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="重建 active 文档的 parse/split/embed 索引")
    parser.add_argument(
        "--doc-id",
        type=int,
        default=None,
        help="仅重建指定 doc_id（须为 status=active）",
    )
    args = parser.parse_args()

    doc_ids = _load_active_doc_ids(args.doc_id)
    if not doc_ids:
        logger.error("无可重建文档，退出")
        sys.exit(1)

    total = len(doc_ids)
    failed: List[int] = []
    logger.info(
        "索引重建启动 | strategy=%s | 待处理=%d 篇",
        settings.CHUNK_STRATEGY,
        total,
    )

    for index, doc_id in enumerate(doc_ids, start=1):
        logger.info("进度 %d/%d | doc_id=%s", index, total, doc_id)
        if not reindex_one(doc_id):
            failed.append(doc_id)

    get_bm25_index().refresh_index()
    success_count = total - len(failed)
    logger.info(
        "索引重建完成 | strategy=%s | total=%d | success=%d | failed=%s",
        settings.CHUNK_STRATEGY,
        total,
        success_count,
        failed if failed else "[]",
    )

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
