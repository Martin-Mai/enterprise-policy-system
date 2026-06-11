<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import CitationList from './CitationList.vue'
import { renderMarkdown } from '@/utils/markdown'
import { revokeFeedback, submitFeedback } from '@/api/feedback'
import { useChatStore } from '@/stores/chatStore'
import type { ChatMessage, UserFeedback } from '@/types/chat'

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

/**
 * 点赞高亮：直接绑定 Pinia Store 中消息的 user_feedback 字段
 * 禁止使用局部临时变量维护赞踩状态
 */
const isPositiveActive = computed(
  () => props.message.user_feedback === 'positive',
)

/** 点踩高亮：同上，绑定 Store 中的 user_feedback */
const isNegativeActive = computed(
  () => props.message.user_feedback === 'negative',
)

/**
 * 赞踩交互：支持点亮、取消、无缝切换
 * - 再次点击已激活项 → 撤销反馈
 * - 点击对立项 → 切换并更新后端
 */
async function handleFeedback(isPositive: boolean): Promise<void> {
  if (props.message.id <= 0) return

  const targetFeedback: UserFeedback = isPositive ? 'positive' : 'negative'
  const currentFeedback = props.message.user_feedback

  try {
    if (currentFeedback === targetFeedback) {
      // 再次点击同一按钮 → 撤销
      await revokeFeedback(props.message.id)
      chatStore.setMessageFeedback(props.message.id, null)
      ElMessage.success('已取消反馈')
    } else {
      // 新建或切换赞踩：弹出可选评语输入框
      let comment = ''
      try {
        const { value } = await ElMessageBox.prompt('', '补充反馈意见（可选）', {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPlaceholder: '请输入您的评价，例如：回答清晰、计算错误等',
        })
        comment = value?.trim() ?? ''
      } catch {
        // 用户点击取消，comment 传空字符串
        comment = ''
      }

      const res = await submitFeedback({
        message_id: props.message.id,
        is_positive: isPositive,
        comment,
      })
      const nextFeedback = res.user_feedback ?? targetFeedback
      chatStore.setMessageFeedback(props.message.id, nextFeedback)
      ElMessage.success('反馈已提交')
    }
  } catch {
    ElMessage.error('反馈提交失败，请稍后重试')
  }
}
</script>

<template>
  <div class="message-row" :class="{ 'message-row--user': isUser }">
    <div class="bubble-wrapper">
      <!-- 用户消息气泡 -->
      <div v-if="isUser" class="bubble bubble--user">
        {{ message.content }}
      </div>

      <!-- AI 消息气泡 -->
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

      <!-- 赞踩栏：高亮状态绑定 Store 中的 user_feedback -->
      <div v-if="showFeedback" class="feedback-bar">
        <button
          class="feedback-btn"
          :class="{ 'feedback-btn--active-positive': isPositiveActive }"
          title="点赞"
          @click="handleFeedback(true)"
        >
          👍
        </button>
        <button
          class="feedback-btn"
          :class="{ 'feedback-btn--active-negative': isNegativeActive }"
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
  margin-bottom: 24px;
  padding: 0 28px;
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

/* ── 气泡基础：15-16px 字号 + 1.7 行高 ── */
.bubble {
  padding: 16px 20px;
  border-radius: 12px;
  line-height: 1.7;
  font-size: 16px;
  word-break: break-word;
}

.bubble--user {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  color: #ffffff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
}

.bubble--assistant {
  background: #ffffff;
  color: #1e293b;
  border: 1px solid #e2e8f0;
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
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
  color: #3b82f6;
  animation: blink 0.8s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

/* ── 赞踩按钮 ── */
.feedback-bar {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  padding-left: 4px;
}

.feedback-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.15s ease;
  opacity: 0.75;
}

.feedback-btn:hover {
  border-color: #3b82f6;
  opacity: 1;
}

/* 点赞激活：科技蓝高亮 */
.feedback-btn--active-positive {
  background: #eff6ff;
  border-color: #3b82f6;
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.2);
  opacity: 1;
}

/* 点踩激活：克制灰红 */
.feedback-btn--active-negative {
  background: #fef2f2;
  border-color: #f87171;
  box-shadow: 0 0 0 1px rgba(248, 113, 113, 0.2);
  opacity: 1;
}
</style>
