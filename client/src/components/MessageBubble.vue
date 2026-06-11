<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import CitationList from './CitationList.vue'
import { renderMarkdown } from '@/utils/markdown'
import { submitFeedback } from '@/api/feedback'
import { useChatStore } from '@/stores/chatStore'
import type { ChatMessage } from '@/types/chat'

const props = defineProps<{
  message: ChatMessage
}>()

const chatStore = useChatStore()

const isUser = computed(() => props.message.role === 'user')
const isAssistant = computed(() => props.message.role === 'assistant')

/** AI 消息渲染后的 HTML */
const renderedHtml = computed(() => {
  if (!isAssistant.value || props.message.error) return ''
  return renderMarkdown(props.message.content)
})

/** 是否显示赞踩按钮（仅已落库的 assistant 消息） */
const showFeedback = computed(
  () => isAssistant.value && props.message.id > 0 && !props.message.streaming,
)

/** 提交赞踩反馈，支持无缝切换 */
async function handleFeedback(isPositive: boolean): Promise<void> {
  if (props.message.id <= 0) return

  try {
    await submitFeedback({
      message_id: props.message.id,
      is_positive: isPositive,
      comment: '',
    })
    chatStore.setMessageFeedback(props.message.id, isPositive)
    ElMessage.success(isPositive ? '感谢您的点赞！' : '反馈已记录，我们会持续改进')
  } catch {
    ElMessage.error('反馈提交失败，请稍后重试')
  }
}
</script>

<template>
  <div class="message-row" :class="{ 'message-row--user': isUser }">
    <div class="bubble-wrapper">
      <!-- 用户消息 -->
      <div v-if="isUser" class="bubble bubble--user">
        {{ message.content }}
      </div>

      <!-- AI 消息 -->
      <div v-else class="bubble bubble--assistant" :class="{ 'bubble--error': message.error }">
        <div v-if="message.error" class="error-text">
          {{ message.content }}
        </div>
        <div
          v-else
          class="markdown-body"
          v-html="renderedHtml"
        />
        <span v-if="message.streaming" class="cursor-blink">▍</span>

        <CitationList
          v-if="!message.streaming && message.citations?.length"
          :citations="message.citations"
        />
      </div>

      <!-- 赞踩互动 -->
      <div v-if="showFeedback" class="feedback-bar">
        <button
          class="feedback-btn"
          :class="{ active: message.feedbackPositive === true }"
          title="点赞"
          @click="handleFeedback(true)"
        >
          👍
        </button>
        <button
          class="feedback-btn"
          :class="{ active: message.feedbackPositive === false }"
          title="点踩"
          @click="handleFeedback(false)"
        >
          👎
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-row {
  display: flex;
  justify-content: flex-start;
  margin-bottom: 20px;
  padding: 0 24px;
}

.message-row--user {
  justify-content: flex-end;
}

.bubble-wrapper {
  max-width: 78%;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.message-row--user .bubble-wrapper {
  align-items: flex-end;
}

.bubble {
  padding: 14px 18px;
  border-radius: 16px;
  line-height: 1.75;
  font-size: 15px;
  word-break: break-word;
}

.bubble--user {
  background: var(--eps-user-bubble);
  color: #ffffff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 14px rgba(26, 86, 219, 0.25);
}

.bubble--assistant {
  background: var(--eps-assistant-bubble);
  color: #1e293b;
  border: 1px solid var(--eps-border);
  border-bottom-left-radius: 4px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  width: 100%;
}

.bubble--error {
  border-color: #fca5a5;
  background: #fef2f2;
}

.error-text {
  color: #dc2626;
  font-weight: 500;
}

.cursor-blink {
  display: inline-block;
  color: var(--eps-primary);
  animation: blink 0.8s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

.feedback-bar {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  padding-left: 4px;
}

.feedback-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--eps-border);
  border-radius: 8px;
  background: #fff;
  color: var(--eps-text-muted);
  cursor: pointer;
  transition: all 0.15s ease;
}

.feedback-btn:hover {
  border-color: var(--eps-primary);
  color: var(--eps-primary);
}

.feedback-btn.active {
  background: var(--eps-primary);
  border-color: var(--eps-primary);
  color: #fff;
}
</style>
