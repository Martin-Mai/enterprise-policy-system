<script setup lang="ts">
import { ref, nextTick, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Setting, SwitchButton } from '@element-plus/icons-vue'
import MessageBubble from './MessageBubble.vue'
import ChatInput from './ChatInput.vue'
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

/** 发送消息 */
async function handleSend(): Promise<void> {
  const text = inputText.value.trim()
  if (!text) return

  inputText.value = ''
  await chatStore.sendMessage(text, () => {
    void scrollToBottom()
  })
}

/** 中止流式生成 */
function handleStop(): void {
  chatStore.stopStreaming()
}

/** 登出 */
function handleLogout(): void {
  authStore.logout()
  router.push({ name: 'Login' })
}

/** 进入管理后台 */
function goToAdmin(): void {
  router.push({ name: 'AdminDashboard' })
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
    <!-- 顶部栏：企业级克制白底 -->
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
        <!-- 与管理后台「返回知识库对话」按钮视觉对齐 -->
        <el-button
          v-if="authStore.isAdmin"
          type="primary"
          link
          :icon="Setting"
          class="eps-nav-link-btn"
          @click="goToAdmin"
        >
          进入管理后台
        </el-button>
        <el-button
          type="danger"
          plain
          size="small"
          :icon="SwitchButton"
          class="logout-btn"
          @click="handleLogout"
        >
          登出
        </el-button>
      </div>
    </header>

    <!-- 消息流：冷调微灰白背景 -->
    <div
      ref="messagesContainer"
      v-loading="chatStore.loadingMessages"
      class="messages-area"
    >
      <!-- 欢迎首屏：极简科技星芒徽标，去除玩具感机器人 -->
      <div v-if="chatStore.messages.length === 0" class="welcome">
        <div class="welcome__logo" aria-hidden="true">
          <svg
            class="welcome__svg"
            viewBox="0 0 80 80"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <!-- 外环：极细渐变双环 -->
            <circle
              cx="40"
              cy="40"
              r="28"
              stroke="url(#ringGrad)"
              stroke-width="1.5"
              stroke-dasharray="4 6"
              class="welcome__ring welcome__ring--outer"
            />
            <circle
              cx="40"
              cy="40"
              r="20"
              stroke="#1E293B"
              stroke-width="1.5"
              stroke-opacity="0.35"
              class="welcome__ring welcome__ring--inner"
            />
            <!-- 中心科技星芒 -->
            <g stroke="#1E293B" stroke-width="1.5" stroke-linecap="round">
              <line x1="40" y1="18" x2="40" y2="28" />
              <line x1="40" y1="52" x2="40" y2="62" />
              <line x1="18" y1="40" x2="28" y2="40" />
              <line x1="52" y1="40" x2="62" y2="40" />
              <line x1="24.5" y1="24.5" x2="31.5" y2="31.5" />
              <line x1="48.5" y1="48.5" x2="55.5" y2="55.5" />
              <line x1="55.5" y1="24.5" x2="48.5" y2="31.5" />
              <line x1="31.5" y1="48.5" x2="24.5" y2="55.5" />
            </g>
            <!-- 中心核心点：科技蓝 -->
            <circle cx="40" cy="40" r="4" fill="#3B82F6" class="welcome__core" />
            <defs>
              <linearGradient id="ringGrad" x1="12" y1="12" x2="68" y2="68">
                <stop offset="0%" stop-color="#1E293B" />
                <stop offset="100%" stop-color="#3B82F6" />
              </linearGradient>
            </defs>
          </svg>
        </div>
        <h3>欢迎使用企业知识库问答</h3>
        <p>基于 RAG 混合检索，为您提供精准、可溯源的专业回答</p>
      </div>

      <MessageBubble
        v-for="msg in chatStore.messages"
        :key="`${msg.id}-${msg.created_at}`"
        :message="msg"
      />
    </div>

    <!-- 悬浮智能输入卡片 -->
    <ChatInput
      v-model="inputText"
      :is-streaming="chatStore.isStreaming"
      @send="handleSend"
      @stop="handleStop"
    />
  </main>
</template>

<style scoped>
.chat-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  background: #f8fafc;
}

/* ── 顶部栏 ── */
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 28px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
}

.chat-header__title h2 {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.4;
}

.chat-header__subtitle {
  font-size: 14px;
  line-height: 1.6;
  color: #64748b;
}

.chat-header__user {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-avatar {
  background: linear-gradient(135deg, #1e293b, #3b82f6);
  color: #fff;
  font-weight: 600;
}

.username {
  font-size: 15px;
  color: #475569;
  font-weight: 500;
}

.logout-btn {
  font-size: 14px;
}

/* ── 消息区域 ── */
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 28px 0 12px;
  background: #f8fafc;
}

/* ── 欢迎首屏 ── */
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  padding: 48px 40px;
}

.welcome__logo {
  margin-bottom: 28px;
}

.welcome__svg {
  width: 80px;
  height: 80px;
}

/* 微弱呼吸闪烁：彰显受控、高智商的企业级质感 */
.welcome__core {
  animation: pulse-soft 3s ease-in-out infinite;
}

.welcome__ring--outer {
  animation: spin-slow 20s linear infinite;
  transform-origin: center;
}

.welcome__ring--inner {
  animation: spin-slow 30s linear infinite reverse;
  transform-origin: center;
}

@keyframes pulse-soft {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

@keyframes spin-slow {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.welcome h3 {
  font-size: 20px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 12px;
  line-height: 1.5;
}

.welcome p {
  font-size: 16px;
  line-height: 1.7;
  color: #64748b;
  max-width: 480px;
}
</style>
