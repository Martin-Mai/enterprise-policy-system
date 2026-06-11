import { createRouter, createWebHistory } from 'vue-router'
import { TOKEN_STORAGE_KEY } from '@/api/client'

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
      path: '/',
      redirect: '/chat',
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/chat',
    },
  ],
})

/** 全局路由守卫：未登录禁止访问 /chat，已登录自动跳转离开 /login */
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

  next()
})

export default router
