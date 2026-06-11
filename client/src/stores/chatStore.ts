import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  deleteConversation,
  fetchConversationMessages,
  fetchConversations,
  streamChat,
} from '@/api/chat'
import type { ChatMessage, ConversationItem, UserFeedback } from '@/types/chat'

/** 生成临时消息 ID（流式输出期间使用） */
let tempIdCounter = -1
function nextTempId(): number {
  tempIdCounter -= 1
  return tempIdCounter
}

/** 生成新的会话 UUID */
function generateSessionId(): string {
  return crypto.randomUUID()
}

export const useChatStore = defineStore('chat', () => {
  const conversations = ref<ConversationItem[]>([])
  const currentSessionId = ref<string | null>(null)
  const messages = ref<ChatMessage[]>([])
  const isStreaming = ref(false)
  const loadingConversations = ref(false)
  const loadingMessages = ref(false)

  /** 当前会话标题 */
  const currentTitle = computed(() => {
    if (!currentSessionId.value) return '新对话'
    const conv = conversations.value.find((c) => c.session_id === currentSessionId.value)
    return conv?.title || '新对话'
  })

  /** 当前 AbortController，用于中止流式请求 */
  let abortController: AbortController | null = null

  /** 加载会话列表 */
  async function loadConversations(): Promise<void> {
    loadingConversations.value = true
    try {
      conversations.value = await fetchConversations()
    } finally {
      loadingConversations.value = false
    }
  }

  /** 新建空白对话 */
  function createNewChat(): void {
    if (isStreaming.value) return
    currentSessionId.value = generateSessionId()
    messages.value = []
  }

  /** 切换并加载指定会话 */
  async function selectConversation(sessionId: string): Promise<void> {
    if (isStreaming.value || currentSessionId.value === sessionId) return

    currentSessionId.value = sessionId
    loadingMessages.value = true
    try {
      messages.value = await fetchConversationMessages(sessionId)
    } finally {
      loadingMessages.value = false
    }
  }

  /** 删除会话 */
  async function removeConversation(sessionId: string): Promise<void> {
    await deleteConversation(sessionId)
    conversations.value = conversations.value.filter((c) => c.session_id !== sessionId)

    if (currentSessionId.value === sessionId) {
      createNewChat()
    }
  }

  /**
   * 发送问题并启动 SSE 流式问答
   * @param question 用户输入
   * @param onScroll 每次 token 到达时触发滚动回调
   */
  async function sendMessage(
    question: string,
    onScroll?: () => void,
  ): Promise<void> {
    const trimmed = question.trim()
    if (!trimmed || isStreaming.value) return

    if (!currentSessionId.value) {
      currentSessionId.value = generateSessionId()
    }

    const sessionId = currentSessionId.value

    // 追加用户消息与空的助手占位消息
    const userMsg: ChatMessage = {
      id: nextTempId(),
      role: 'user',
      content: trimmed,
      created_at: new Date().toISOString(),
    }
    const assistantMsg: ChatMessage = {
      id: nextTempId(),
      role: 'assistant',
      content: '',
      streaming: true,
      created_at: new Date().toISOString(),
    }
    messages.value.push(userMsg, assistantMsg)
    const assistantIndex = messages.value.length - 1

    isStreaming.value = true
    abortController = new AbortController()

    try {
      await streamChat(
        { session_id: sessionId, question: trimmed },
        {
          onToken: (content: string) => {
            const msg = messages.value[assistantIndex]
            if (msg) {
              msg.content += content
            }
            onScroll?.()
          },
          onEnd: (event) => {
            const msg = messages.value[assistantIndex]
            if (msg) {
              msg.streaming = false
              msg.citations = event.citations
              if (event.message_id) {
                msg.id = event.message_id
              }
            }
            if (event.session_id) {
              currentSessionId.value = event.session_id
            }
            // 刷新侧边栏会话列表
            void loadConversations()
            onScroll?.()
          },
          onError: (message: string) => {
            const msg = messages.value[assistantIndex]
            if (msg) {
              msg.streaming = false
              msg.error = true
              msg.content = message || '大模型服务响应超时'
            }
            onScroll?.()
          },
        },
        abortController.signal,
      )
    } catch (err: unknown) {
      const msg = messages.value[assistantIndex]
      if (msg) {
        msg.streaming = false
        if (err instanceof DOMException && err.name === 'AbortError') {
          msg.aborted = true
          if (!msg.content) {
            msg.content = '生成已中止'
          } else {
            msg.content += '\n\n[已中止]'
          }
        } else {
          msg.error = true
          msg.content = err instanceof Error ? err.message : '请求失败，请稍后重试'
        }
      }
      onScroll?.()
    } finally {
      isStreaming.value = false
      abortController = null
      const msg = messages.value[assistantIndex]
      if (msg?.streaming) {
        msg.streaming = false
      }
    }
  }

  /** 主动中止流式生成 */
  function stopStreaming(): void {
    abortController?.abort()
  }

  /** 更新 Pinia 中指定消息的 user_feedback 状态（与后端字段对齐） */
  function setMessageFeedback(messageId: number, feedback: UserFeedback): void {
    const msg = messages.value.find((m) => m.id === messageId)
    if (msg) {
      msg.user_feedback = feedback
    }
  }

  return {
    conversations,
    currentSessionId,
    currentTitle,
    messages,
    isStreaming,
    loadingConversations,
    loadingMessages,
    loadConversations,
    createNewChat,
    selectConversation,
    removeConversation,
    sendMessage,
    stopStreaming,
    setMessageFeedback,
  }
})
