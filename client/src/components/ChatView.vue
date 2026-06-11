<script setup lang="ts">
import { ref, nextTick, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Promotion, VideoPause, SwitchButton } from '@element-plus/icons-vue'
import MessageBubble from './MessageBubble.vue'
import { useAuthStore } from '@/stores/authStore'
import { useChatStore } from '@/stores/chatStore'

const authStore = useAuthStore()
const chatStore = useChatStore()
const router = useRouter()

const inputText = ref('')
const messagesContainer = ref<HTMLElement | null>(null)

/** 强制滚动到底部 */
async function scrollToBottom(): Promise<void> {
  await nextTick()
  const el = messagesContainer.value
  if (el) {
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }
}

/** 发送或中止 */
async function handleSendOrStop(): Promise<void> {
  if (chatStore.isStreaming) {
    chatStore.stopStreaming()
    return
  }

  const text = inputText.value.trim()
  if (!text) return

  inputText.value = ''
  await chatStore.sendMessage(text, () => {
    void scrollToBottom()
  })
}

/** 键盘：Enter 发送，Shift+Enter 换行 */
function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    void handleSendOrStop()
  }
}

/** 登出 */
function handleLogout(): void {
  authStore.logout()
  router.push({ name: 'Login' })
}

onMounted(() => {
  chatStore.createNewChat()
})

watch(
  () => chatStore.messages.length,
  () => {
    void scrollToBottom()
  },
)
</script>

<template>
  <main class="chat-view">
    <!-- 顶部栏 -->
    <header class="chat-header">
      <div class="chat-header__title">
        <h2>{{ chatStore.currentTitle }}</h2>
        <span class="chat-header__subtitle">企业知识库智能问答</span>
      </div>
      <div class="chat-header__user">
        <el-avatar :size="32" class="user-avatar">
          {{ authStore.user?.username?.charAt(0)?.toUpperCase() ?? 'U' }}
        </el-avatar>
        <span class="username">{{ authStore.user?.username }}</span>
        <el-button
          type="danger"
          plain
          size="small"
          :icon="SwitchButton"
          @click="handleLogout"
        >
          登出
        </el-button>
      </div>
    </header>

    <!-- 消息流 -->
    <div
      ref="messagesContainer"
      v-loading="chatStore.loadingMessages"
      class="messages-area"
    >
      <div v-if="chatStore.messages.length === 0" class="welcome">
        <div class="welcome__icon">🤖</div>
        <h3>欢迎使用企业知识库问答</h3>
        <p>基于 RAG 混合检索，为您提供精准、可溯源的专业回答</p>
      </div>

      <MessageBubble
        v-for="msg in chatStore.messages"
        :key="`${msg.id}-${msg.created_at}`"
        :message="msg"
      />
    </div>

    <!-- 底部输入区 -->
    <footer class="input-area">
      <div class="input-wrapper">
        <el-input
          v-model="inputText"
          type="textarea"
          :rows="3"
          placeholder="输入您的问题…（Enter 发送，Shift+Enter 换行）"
          resize="none"
          :disabled="chatStore.isStreaming"
          @keydown="handleKeydown"
        />
        <el-button
          class="send-btn"
          :type="chatStore.isStreaming ? 'danger' : 'primary'"
          :icon="chatStore.isStreaming ? VideoPause : Promotion"
          circle
          size="large"
          @click="handleSendOrStop"
        />
      </div>
      <p class="input-hint">回答将附带可展开的参考来源，支持 Markdown 与代码高亮</p>
    </footer>
  </main>
</template>

<style scoped>
.chat-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  background: var(--eps-bg);
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: #ffffff;
  border-bottom: 1px solid var(--eps-border);
  flex-shrink: 0;
}

.chat-header__title h2 {
  font-size: 18px;
  font-weight: 600;
  color: #1e293b;
}

.chat-header__subtitle {
  font-size: 12px;
  color: var(--eps-text-muted);
}

.chat-header__user {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  background: linear-gradient(135deg, #1a56db, #0e7490);
  color: #fff;
  font-weight: 600;
}

.username {
  font-size: 14px;
  color: #475569;
  font-weight: 500;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
}

.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--eps-text-muted);
  text-align: center;
  padding: 40px;
}

.welcome__icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.welcome h3 {
  font-size: 20px;
  color: #334155;
  margin-bottom: 8px;
}

.welcome p {
  font-size: 14px;
}

.input-area {
  padding: 16px 24px 20px;
  background: #ffffff;
  border-top: 1px solid var(--eps-border);
  flex-shrink: 0;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}

.input-wrapper :deep(.el-textarea__inner) {
  border-radius: 12px;
  padding: 12px 16px;
  font-size: 15px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.send-btn {
  width: 48px !important;
  height: 48px !important;
  flex-shrink: 0;
  background: linear-gradient(135deg, #1a56db 0%, #0e7490 100%);
  border: none;
}

.send-btn.el-button--danger {
  background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%);
}

.input-hint {
  font-size: 11px;
  color: var(--eps-text-muted);
  margin-top: 8px;
  text-align: center;
}
</style>
