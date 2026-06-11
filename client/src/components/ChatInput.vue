<script setup lang="ts">
import { ref } from 'vue'
import { Promotion, VideoPause } from '@element-plus/icons-vue'

/** 双向绑定输入文本 */
const modelValue = defineModel<string>({ default: '' })

const props = defineProps<{
  /** 是否正在流式生成（切换为中止按钮） */
  isStreaming: boolean
  /** 是否禁用输入 */
  disabled?: boolean
}>()

const emit = defineEmits<{
  send: []
  stop: []
}>()

/** 内部 textarea 引用，用于聚焦 */
const textareaRef = ref<{ focus: () => void } | null>(null)

/** 发送或中止 */
function handleAction(): void {
  if (props.isStreaming) {
    emit('stop')
    return
  }
  emit('send')
}

/** Enter 发送，Shift+Enter 换行 */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    handleAction()
  }
}

/** 暴露 focus 方法供父组件调用 */
defineExpose({
  focus: () => textareaRef.value?.focus(),
})
</script>

<template>
  <!-- 悬浮智能输入卡片：与屏幕边缘留出呼吸间距 -->
  <div class="chat-input-card">
    <div class="chat-input-card__inner">
      <el-input
        ref="textareaRef"
        v-model="modelValue"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="输入您的问题…（Enter 发送，Shift+Enter 换行）"
        resize="none"
        :disabled="disabled || isStreaming"
        class="chat-input-card__textarea"
        @keydown="handleKeydown"
      />

      <!-- 右侧发送 / 中止按钮 -->
      <el-button
        class="chat-input-card__send"
        :class="{ 'chat-input-card__send--stop': isStreaming }"
        :type="isStreaming ? 'danger' : 'primary'"
        :icon="isStreaming ? VideoPause : Promotion"
        circle
        @click="handleAction"
      />
    </div>

    <p class="chat-input-card__hint">
      回答将附带可展开的参考来源，支持 Markdown 与代码高亮
    </p>
  </div>
</template>

<style scoped>
/* ── 悬浮卡片容器 ── */
.chat-input-card {
  flex-shrink: 0;
  padding: 0 24px 24px;
  background: transparent;
}

.chat-input-card__inner {
  display: flex;
  align-items: flex-end;
  gap: 14px;
  padding: 16px 18px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05);
}

/* ── 自适应 textarea ── */
.chat-input-card__textarea {
  flex: 1;
}

.chat-input-card__textarea :deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  padding: 4px 8px;
  font-size: 16px;
  line-height: 1.7;
  color: #1e293b;
  background: transparent;
  min-height: 52px;
}

.chat-input-card__textarea :deep(.el-textarea__inner::placeholder) {
  font-size: 15px;
  color: #94a3b8;
  padding-left: 2px;
}

.chat-input-card__textarea :deep(.el-textarea__inner:focus) {
  box-shadow: none;
}

/* ── 科技蓝发送按钮 ── */
.chat-input-card__send {
  width: 46px !important;
  height: 46px !important;
  flex-shrink: 0;
  background: #3b82f6 !important;
  border: none !important;
  box-shadow: 0 2px 8px rgba(59, 130, 246, 0.35);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.chat-input-card__send:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.45);
}

.chat-input-card__send--stop {
  background: #ef4444 !important;
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
}

.chat-input-card__send--stop:hover {
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
}

/* ── 底部提示 ── */
.chat-input-card__hint {
  margin-top: 10px;
  text-align: center;
  font-size: 13px;
  line-height: 1.6;
  color: #94a3b8;
}
</style>
