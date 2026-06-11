import apiClient, { TOKEN_STORAGE_KEY } from './client'
import type {
  ChatMessage,
  ChatStreamRequest,
  ConversationItem,
  SseEvent,
} from '@/types/chat'

/** 会话列表响应 */
interface ConversationListResponse {
  items: ConversationItem[]
}

/** 历史消息列表响应 */
interface MessageListResponse {
  session_id: string
  items: ChatMessage[]
}

/**
 * 获取当前用户的所有历史会话（按时间倒序）
 */
export async function fetchConversations(): Promise<ConversationItem[]> {
  const { data } = await apiClient.get<ConversationListResponse>('/api/conversations')
  return data.items
}

/**
 * 获取指定会话的历史消息（按时间正序）
 */
export async function fetchConversationMessages(sessionId: string): Promise<ChatMessage[]> {
  const { data } = await apiClient.get<MessageListResponse>(
    `/api/conversations/${sessionId}/messages`,
  )
  return data.items
}

/** 删除指定会话 */
export async function deleteConversation(sessionId: string): Promise<void> {
  await apiClient.delete(`/api/conversations/${sessionId}`)
}

/** SSE 流式回调 */
export interface StreamCallbacks {
  onToken: (content: string) => void
  onEnd: (event: Extract<SseEvent, { type: 'end' }>) => void
  onError: (message: string) => void
}

/**
 * 使用 fetch + ReadableStream 消费 SSE 流式问答
 * 内置 UTF-8 断裂缓冲区，防止中文乱码与粘包
 */
export async function streamChat(
  payload: ChatStreamRequest,
  callbacks: StreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)

  const response = await fetch('http://localhost:8000/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload),
    signal,
  })

  if (!response.ok) {
    const errText = await response.text()
    throw new Error(errText || `请求失败 (${response.status})`)
  }

  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('浏览器不支持 ReadableStream')
  }

  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // 按 SSE 标准 \n\n 分隔符切分完整事件块
      let separatorIndex = buffer.indexOf('\n\n')
      while (separatorIndex !== -1) {
        const rawEvent = buffer.slice(0, separatorIndex)
        buffer = buffer.slice(separatorIndex + 2)

        const lines = rawEvent.split('\n')
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue

          const jsonStr = line.slice(6).trim()
          if (!jsonStr) continue

          try {
            const event = JSON.parse(jsonStr) as SseEvent
            if (event.type === 'token') {
              callbacks.onToken(event.content)
            } else if (event.type === 'end') {
              callbacks.onEnd(event)
            } else if (event.type === 'error') {
              callbacks.onError(event.message)
            }
          } catch {
            // 忽略非完整 JSON（理论上 buffer 机制已规避）
          }
        }

        separatorIndex = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.releaseLock()
  }
}
