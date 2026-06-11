/** 引用来源元数据 */
export interface Citation {
  chunk_id: string
  file_name: string
  page_no: number
  section_title: string
  text_preview: string
  inferred?: boolean
}

/** 聊天消息（前端展示模型） */
export interface ChatMessage {
  /** 数据库消息 ID，流式生成中可能为临时负数 */
  id: number
  role: 'user' | 'assistant'
  content: string
  citations?: Citation[]
  created_at?: string
  /** 是否正在流式输出 */
  streaming?: boolean
  /** 是否被用户中止 */
  aborted?: boolean
  /** 是否发生错误 */
  error?: boolean
  /** 本地赞踩状态：true=赞，false=踩，undefined=未操作 */
  feedbackPositive?: boolean
}

/** 会话列表项 */
export interface ConversationItem {
  id: number
  session_id: string
  title: string | null
  created_at: string
}

/** 流式问答请求 */
export interface ChatStreamRequest {
  session_id?: string
  question: string
}

/** SSE 事件：token 增量 */
export interface SseTokenEvent {
  type: 'token'
  content: string
}

/** SSE 事件：流结束 */
export interface SseEndEvent {
  type: 'end'
  citations: Citation[]
  message_id: number | null
  session_id: string
}

/** SSE 事件：错误 */
export interface SseErrorEvent {
  type: 'error'
  message: string
}

export type SseEvent = SseTokenEvent | SseEndEvent | SseErrorEvent
