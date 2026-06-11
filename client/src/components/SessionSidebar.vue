<script setup lang="ts">
import { onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, Delete, ChatDotRound } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chatStore'

const chatStore = useChatStore()

onMounted(() => {
  void chatStore.loadConversations()
})

/** 格式化会话创建时间 */
function formatTime(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const isToday = date.toDateString() === now.toDateString()
  if (isToday) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

/** 删除会话（二次确认） */
async function handleDelete(sessionId: string, event: Event): Promise<void> {
  event.stopPropagation()
  try {
    await ElMessageBox.confirm('确定删除该会话？删除后不可恢复。', '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await chatStore.removeConversation(sessionId)
  } catch {
    // 用户取消
  }
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar__header">
      <el-button
        type="primary"
        class="new-chat-btn"
        :icon="Plus"
        :disabled="chatStore.isStreaming"
        @click="chatStore.createNewChat()"
      >
        新建对话
      </el-button>
    </div>

    <div v-loading="chatStore.loadingConversations" class="sidebar__list">
      <div
        v-for="conv in chatStore.conversations"
        :key="conv.session_id"
        class="session-card"
        :class="{ 'session-card--active': conv.session_id === chatStore.currentSessionId }"
        @click="chatStore.selectConversation(conv.session_id)"
      >
        <div class="session-card__icon">
          <el-icon><ChatDotRound /></el-icon>
        </div>
        <div class="session-card__body">
          <p class="session-card__title">{{ conv.title || '未命名对话' }}</p>
          <span class="session-card__time">{{ formatTime(conv.created_at) }}</span>
        </div>
        <button
          class="session-card__delete"
          title="删除会话"
          @click="handleDelete(conv.session_id, $event)"
        >
          <el-icon><Delete /></el-icon>
        </button>
      </div>

      <div v-if="!chatStore.loadingConversations && chatStore.conversations.length === 0" class="empty-hint">
        暂无历史会话，点击上方按钮开始
      </div>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 25%;
  min-width: 260px;
  max-width: 360px;
  height: 100%;
  background: var(--eps-sidebar-bg);
  border-right: 1px solid var(--eps-border);
  display: flex;
  flex-direction: column;
}

.sidebar__header {
  padding: 20px 16px 12px;
}

.new-chat-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  border-radius: 10px;
  background: linear-gradient(135deg, #1a56db 0%, #0e7490 100%);
  border: none;
}

.new-chat-btn:hover {
  opacity: 0.92;
}

.sidebar__list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px 16px;
}

.session-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 14px;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  margin-bottom: 6px;
  position: relative;
  border: 1px solid transparent;
  background: #ffffff;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
}

.session-card:hover {
  background: #f1f5f9;
}

.session-card--active {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
}

.session-card__icon {
  color: var(--eps-primary);
  font-size: 18px;
  flex-shrink: 0;
}

.session-card__body {
  flex: 1;
  min-width: 0;
}

.session-card__title {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-card__time {
  font-size: 13px;
  line-height: 1.5;
  color: var(--eps-text-muted);
}

.session-card__delete {
  opacity: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
}

.session-card:hover .session-card__delete {
  opacity: 1;
}

.session-card__delete:hover {
  background: #fee2e2;
  color: #dc2626;
}

.empty-hint {
  text-align: center;
  color: var(--eps-text-muted);
  font-size: 15px;
  line-height: 1.6;
  padding: 32px 16px;
}
</style>
