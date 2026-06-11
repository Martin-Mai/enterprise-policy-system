-- 002_add_document_status_and_feedback_processed.sql
-- 为 documents 表添加 status 字段，为 feedbacks 表添加 is_processed 字段
-- 注意：MySQL 不支持 ADD COLUMN IF NOT EXISTS，若列已存在会报错，可忽略或先检查

ALTER TABLE documents
    ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'
        COMMENT '文档状态：processing / active / deleting';

CREATE INDEX idx_documents_status ON documents (status);

ALTER TABLE feedbacks
    ADD COLUMN is_processed TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '管理员是否已处理该反馈';
