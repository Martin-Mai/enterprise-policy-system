/** 管理员仪表盘统计数据 */
export interface AdminStats {
  total_documents: number
  total_users: number
  today_qa_count: number
  /** 综合好评率，0~100 百分比 */
  positive_rate: number
  /** 近 7 天每日问答量，从最早到最近 */
  weekly_qa: number[]
  feedback_stats: {
    positive: number
    negative: number
  }
}

/** 热门引用文档项 */
export interface HotDocumentItem {
  file_name: string
  citation_count: number
}

/** 管理员文档列表项 */
export interface AdminDocumentItem {
  id: number
  file_name: string
  upload_time: string
  uploader_name: string
  chunk_count: number
  /** processing / active / deleting */
  status: string
}

/** 管理员文档分页响应 */
export interface AdminDocumentListResponse {
  total: number
  page: number
  page_size: number
  items: AdminDocumentItem[]
}

/** 审计日志列表项 */
export interface AdminAuditLogItem {
  id: number
  username: string
  question: string
  answer_summary: string
  citation_count: number
  citations: Record<string, unknown>[] | null
  created_at: string
}

/** 审计日志分页响应 */
export interface AdminAuditLogListResponse {
  total: number
  page: number
  page_size: number
  items: AdminAuditLogItem[]
}

/** 审计日志详情 */
export interface AdminAuditLogDetail {
  id: number
  username: string
  question: string
  answer: string
  retrieved_chunks: Record<string, unknown>[]
  citations: Record<string, unknown>[] | null
  created_at: string
}

/** 管理员反馈列表项 */
export interface AdminFeedbackItem {
  id: number
  message_id: number
  message_content: string
  username: string
  is_positive: boolean
  comment: string | null
  is_processed: boolean
  created_at: string
}

/** 管理员反馈列表响应 */
export interface AdminFeedbackListResponse {
  total: number
  items: AdminFeedbackItem[]
}

/** 异步删除受理响应 */
export interface AdminDeleteProcessingResponse {
  status: string
  message: string
}

/** 文档上传响应 */
export interface DocumentUploadResponse {
  doc_id: number
  file_name: string
  message: string
}
