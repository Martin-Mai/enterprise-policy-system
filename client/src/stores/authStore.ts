import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchCurrentUser, loginUser, registerUser } from '@/api/auth'
import { TOKEN_STORAGE_KEY } from '@/api/client'
import type { LoginPayload, RegisterPayload, UserInfo } from '@/types/auth'

const USER_STORAGE_KEY = 'eps_user_info'

/** 从 localStorage 读取缓存的用户信息 */
function loadCachedUser(): UserInfo | null {
  const raw = localStorage.getItem(USER_STORAGE_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as UserInfo
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_STORAGE_KEY))
  const user = ref<UserInfo | null>(loadCachedUser())
  const loading = ref(false)

  const isLoggedIn = computed(() => !!token.value)

  /** 持久化令牌 */
  function persistToken(accessToken: string): void {
    token.value = accessToken
    localStorage.setItem(TOKEN_STORAGE_KEY, accessToken)
  }

  /** 持久化用户信息 */
  function persistUser(userInfo: UserInfo): void {
    user.value = userInfo
    localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(userInfo))
  }

  /** 清除登录态 */
  function clearAuth(): void {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    localStorage.removeItem(USER_STORAGE_KEY)
  }

  /** 用户登录 */
  async function login(payload: LoginPayload): Promise<void> {
    loading.value = true
    try {
      const tokenRes = await loginUser(payload)
      persistToken(tokenRes.access_token)
      const userInfo = await fetchCurrentUser()
      persistUser(userInfo)
    } finally {
      loading.value = false
    }
  }

  /** 用户注册（注册后自动登录） */
  async function register(payload: RegisterPayload): Promise<void> {
    loading.value = true
    try {
      await registerUser(payload)
      await login({ username: payload.username, password: payload.password })
    } finally {
      loading.value = false
    }
  }

  /** 登出 */
  function logout(): void {
    clearAuth()
  }

  /** 应用启动时尝试恢复用户资料 */
  async function hydrateUser(): Promise<void> {
    if (!token.value) return
    try {
      const userInfo = await fetchCurrentUser()
      persistUser(userInfo)
    } catch {
      clearAuth()
    }
  }

  return {
    token,
    user,
    loading,
    isLoggedIn,
    login,
    register,
    logout,
    hydrateUser,
    clearAuth,
  }
})
