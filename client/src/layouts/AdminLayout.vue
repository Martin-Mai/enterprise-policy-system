<script setup lang="ts">
import { computed, provide, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChatDotRound,
  DataAnalysis,
  Document,
  Expand,
  Fold,
  MessageBox,
  Tickets,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/authStore'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

/** 侧边栏折叠状态（向子页面注入，供 ECharts resize 联动） */
const collapsed = ref(false)
provide('adminSidebarCollapsed', collapsed)

/** 导航菜单项配置 */
const menuItems = [
  { path: '/admin/dashboard', title: '数据看板', icon: DataAnalysis },
  { path: '/admin/documents', title: '文档管理', icon: Document },
  { path: '/admin/audit-logs', title: '审计日志', icon: Tickets },
  { path: '/admin/feedbacks', title: '反馈中心', icon: MessageBox },
]

/** 当前激活菜单路径 */
const activePath = computed(() => route.path)

/** 返回前台聊天页 */
function goToChat(): void {
  router.push({ name: 'Chat' })
}
</script>

<template>
  <div class="admin-layout" :class="{ 'admin-layout--collapsed': collapsed }">
    <!-- 左侧独立菜单栏 -->
    <aside class="admin-sidebar">
      <div class="admin-sidebar__brand">
        <span v-if="!collapsed" class="brand-text">RAG 管理后台</span>
        <span v-else class="brand-icon">R</span>
      </div>

      <nav class="admin-sidebar__nav">
        <router-link
          v-for="item in menuItems"
          :key="item.path"
          :to="item.path"
          class="nav-item"
          :class="{ 'nav-item--active': activePath === item.path }"
        >
          <el-icon :size="18"><component :is="item.icon" /></el-icon>
          <span v-if="!collapsed" class="nav-item__text">{{ item.title }}</span>
        </router-link>
      </nav>

      <button class="admin-sidebar__toggle" @click="collapsed = !collapsed">
        <el-icon :size="16">
          <component :is="collapsed ? Expand : Fold" />
        </el-icon>
      </button>
    </aside>

    <!-- 右侧主内容区 -->
    <div class="admin-main">
      <header class="admin-header">
        <div class="admin-header__left">
          <h1 class="admin-header__title">企业受控级 RAG 管理系统</h1>
        </div>
        <div class="admin-header__right">
          <el-button
            type="primary"
            link
            :icon="ChatDotRound"
            class="eps-nav-link-btn"
            @click="goToChat"
          >
            返回知识库对话
          </el-button>
          <el-divider direction="vertical" />
          <el-avatar :size="28" class="admin-avatar">
            {{ authStore.user?.username?.charAt(0)?.toUpperCase() ?? 'A' }}
          </el-avatar>
          <span class="admin-username">{{ authStore.user?.username }}</span>
        </div>
      </header>

      <main class="admin-content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<style scoped>
.admin-layout {
  display: flex;
  height: 100%;
  background: #f8fafc;
}

/* ── 侧边栏 ── */
.admin-sidebar {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-right: 1px solid #e2e8f0;
  transition: width 0.25s ease;
  position: relative;
}

.admin-layout--collapsed .admin-sidebar {
  width: 64px;
}

.admin-sidebar__brand {
  padding: 20px 16px;
  border-bottom: 1px solid #e2e8f0;
}

.brand-text {
  font-size: 15px;
  font-weight: 600;
  color: #1e293b;
  letter-spacing: 0.02em;
}

.brand-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #2563eb;
  color: #fff;
  font-weight: 700;
  font-size: 14px;
}

.admin-sidebar__nav {
  flex: 1;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  color: #64748b;
  text-decoration: none;
  font-size: 14px;
  transition: background 0.15s, color 0.15s;
}

.nav-item:hover {
  background: #f1f5f9;
  color: #334155;
}

.nav-item--active {
  background: #eff6ff;
  color: #2563eb;
  font-weight: 500;
}

.admin-layout--collapsed .nav-item {
  justify-content: center;
  padding: 10px;
}

.nav-item__text {
  white-space: nowrap;
}

.admin-sidebar__toggle {
  margin: 8px;
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
  cursor: pointer;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
}

.admin-sidebar__toggle:hover {
  background: #f1f5f9;
}

/* ── 主内容区 ── */
.admin-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  background: #ffffff;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}

.admin-header__title {
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}

.admin-header__right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.admin-avatar {
  background: #2563eb;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.admin-username {
  font-size: 13px;
  color: #475569;
}

.admin-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>
