-- ============================================================
-- 文档管理与向量化模块 - 数据库迁移脚本
-- 适用于 MySQL，可在无 Alembic 环境下手动执行
-- ============================================================

-- 创建 documents 表
CREATE TABLE IF NOT EXISTS documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    file_name VARCHAR(255) NOT NULL COMMENT '原始文件名',
    file_path VARCHAR(500) NULL COMMENT '文件存储路径',
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    uploaded_by INT NOT NULL COMMENT '上传者用户 ID',
    INDEX ix_documents_id (id),
    INDEX ix_documents_uploaded_by (uploaded_by),
    CONSTRAINT fk_documents_uploaded_by
        FOREIGN KEY (uploaded_by) REFERENCES users (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档表';

-- 创建 document_chunks 表
CREATE TABLE IF NOT EXISTS document_chunks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    doc_id INT NOT NULL COMMENT '所属文档 ID',
    chunk_text TEXT NOT NULL COMMENT '分块文本内容',
    chunk_index INT NOT NULL COMMENT '分块序号',
    metadata_json JSON NULL COMMENT '分块元数据 JSON',
    INDEX ix_document_chunks_id (id),
    INDEX ix_document_chunks_doc_id (doc_id),
    CONSTRAINT fk_document_chunks_doc_id
        FOREIGN KEY (doc_id) REFERENCES documents (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档分块表';
