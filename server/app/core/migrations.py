"""
轻量级数据库 schema 补丁
在应用启动时检测并补齐 ORM 已定义但物理表缺失的列（create_all 不会 ALTER 已有表）
"""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.database import Base

logger = logging.getLogger(__name__)


def _column_exists(engine: Engine, table: str, column: str) -> bool:
    """检查当前库中指定表是否已有某列"""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = :table_name
                  AND COLUMN_NAME = :column_name
                """
            ),
            {"table_name": table, "column_name": column},
        )
        return (result.scalar() or 0) > 0


def _fk_delete_rule(
    engine: Engine, table: str, referenced_table: str, column: str
) -> str | None:
    """查询指定外键列的 ON DELETE 规则，不存在则返回 None"""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT rc.DELETE_RULE
                FROM information_schema.KEY_COLUMN_USAGE kcu
                JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
                  ON kcu.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
                 AND kcu.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA
                WHERE kcu.TABLE_SCHEMA = DATABASE()
                  AND kcu.TABLE_NAME = :table_name
                  AND kcu.COLUMN_NAME = :column_name
                  AND kcu.REFERENCED_TABLE_NAME = :referenced_table
                LIMIT 1
                """
            ),
            {
                "table_name": table,
                "column_name": column,
                "referenced_table": referenced_table,
            },
        )
        row = result.fetchone()
        return row[0] if row else None


def _fk_constraint_name(
    engine: Engine, table: str, referenced_table: str, column: str
) -> str | None:
    """查询指定外键列的约束名"""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT kcu.CONSTRAINT_NAME
                FROM information_schema.KEY_COLUMN_USAGE kcu
                WHERE kcu.TABLE_SCHEMA = DATABASE()
                  AND kcu.TABLE_NAME = :table_name
                  AND kcu.COLUMN_NAME = :column_name
                  AND kcu.REFERENCED_TABLE_NAME = :referenced_table
                LIMIT 1
                """
            ),
            {
                "table_name": table,
                "column_name": column,
                "referenced_table": referenced_table,
            },
        )
        row = result.fetchone()
        return row[0] if row else None


def _index_exists(engine: Engine, table: str, index: str) -> bool:
    """检查当前库中指定表是否已有某索引"""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT COUNT(*)
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = :table_name
                  AND INDEX_NAME = :index_name
                """
            ),
            {"table_name": table, "index_name": index},
        )
        return (result.scalar() or 0) > 0


def run_schema_patches(engine: Engine) -> None:
    """
    补齐 documents.status 与 feedbacks.is_processed 列
    兼容已有 MySQL 实例，可重复调用（列已存在则跳过）
    """
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        if not _column_exists(engine, "documents", "status"):
            logger.info("[Migration] 为 documents 表添加 status 列")
            conn.execute(
                text(
                    """
                    ALTER TABLE documents
                    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'
                        COMMENT '文档状态：processing / active / deleting'
                    """
                )
            )
            if not _index_exists(engine, "documents", "idx_documents_status"):
                conn.execute(
                    text("CREATE INDEX idx_documents_status ON documents (status)")
                )
            logger.info("[Migration] documents.status 列已就绪")

        if not _column_exists(engine, "feedbacks", "is_processed"):
            logger.info("[Migration] 为 feedbacks 表添加 is_processed 列")
            conn.execute(
                text(
                    """
                    ALTER TABLE feedbacks
                    ADD COLUMN is_processed TINYINT(1) NOT NULL DEFAULT 0
                        COMMENT '管理员是否已处理该反馈'
                    """
                )
            )
            logger.info("[Migration] feedbacks.is_processed 列已就绪")

        delete_rule = _fk_delete_rule(engine, "feedbacks", "messages", "message_id")
        if delete_rule and delete_rule != "CASCADE":
            constraint_name = _fk_constraint_name(
                engine, "feedbacks", "messages", "message_id"
            )
            if constraint_name:
                logger.info(
                    "[Migration] 修正 feedbacks.message_id 外键为 ON DELETE CASCADE"
                    "（当前为 %s）",
                    delete_rule,
                )
                conn.execute(
                    text(
                        f"ALTER TABLE feedbacks DROP FOREIGN KEY `{constraint_name}`"
                    )
                )
                conn.execute(
                    text(
                        f"""
                        ALTER TABLE feedbacks
                            ADD CONSTRAINT `{constraint_name}`
                                FOREIGN KEY (message_id) REFERENCES messages (id)
                                ON DELETE CASCADE
                        """
                    )
                )
                logger.info("[Migration] feedbacks.message_id 外键已改为 CASCADE")
