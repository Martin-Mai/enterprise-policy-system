import { createRouter, createWebHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { TOKEN_STORAGE_KEY } from '@/api/client'

/** localStorage 中用户信息的键名（与 authStore 保持一致） */
const USER_STORAGE_KEY = 'eps_user_info'

/** 从缓存读取用户角色 */
function getCachedUserRole(): string | null {
  const raw = localStorage.getItem(USER_STORAGE_KEY)
  if (!raw) return null
  try {
    const user = JSON.parse(raw) as { role?: string }
    return user.role ?? null
  } catch {
    return null
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresAuth: false },
    },
    {
      path: '/chat',
      name: 'Chat',
      component: () => import('@/views/ChatPage.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin',
      component: () => import('@/layouts/AdminLayout.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
      redirect: '/admin/dashboard',
      children: [
        {
          path: 'dashboard',
          name: 'AdminDashboard',
          component: () => import('@/views/admin/DashboardView.vue'),
        },
        {
          path: 'documents',
          name: 'AdminDocuments',
          component: () => import('@/views/admin/DocumentsView.vue'),
        },
        {
          path: 'audit-logs',
          name: 'AdminAuditLogs',
          component: () => import('@/views/admin/AuditLogsView.vue'),
        },
        {
          path: 'feedbacks',
          name: 'AdminFeedbacks',
          component: () => import('@/views/admin/FeedbacksView.vue'),
        },
      ],
    },
    {
      path: '/',
      redirect: '/chat',
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/chat',
    },
  ],
})

/**
 * 全局路由守卫
 * 1. 未登录禁止访问受保护路由
 * 2. 非 admin 角色禁止访问 /admin 及其子路由
 */
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem(TOKEN_STORAGE_KEY)
  const isLoggedIn = !!token

  if (to.meta.requiresAuth && !isLoggedIn) {
    next({ name: 'Login' })
    return
  }

  if (to.name === 'Login' && isLoggedIn) {
    next({ name: 'Chat' })
    return
  }

  // 管理员路由鉴权：角色非 admin 一律拦截
  if (to.meta.requiresAdmin) {
    const role = getCachedUserRole()
    if (role !== 'admin') {
      ElMessage.error('鉴权失败：您无权访问管理系统')
      next({ name: 'Chat' })
      return
    }
  }

  next()
})

export default router
