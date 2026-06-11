-- 003_fix_feedbacks_message_id_cascade.sql
-- 将 feedbacks.message_id 外键从 ON DELETE SET NULL 改为 ON DELETE CASCADE
-- message_id 列不允许为 NULL，SET NULL 会在删除消息时触发 IntegrityError

-- 先查询约束名（通常为 feedbacks_ibfk_1）：
-- SELECT CONSTRAINT_NAME, DELETE_RULE
-- FROM information_schema.REFERENTIAL_CONSTRAINTS
-- WHERE CONSTRAINT_SCHEMA = DATABASE()
--   AND TABLE_NAME = 'feedbacks'
--   AND REFERENCED_TABLE_NAME = 'messages';

ALTER TABLE feedbacks DROP FOREIGN KEY feedbacks_ibfk_1;

ALTER TABLE feedbacks
    ADD CONSTRAINT feedbacks_ibfk_1
        FOREIGN KEY (message_id) REFERENCES messages (id)
        ON DELETE CASCADE;
