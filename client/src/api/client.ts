import axios, { type AxiosInstance } from 'axios'

/** localStorage 中 JWT 令牌的键名 */
export const TOKEN_STORAGE_KEY = 'eps_access_token'

/** 去掉 baseURL 末尾多余的 /api，避免与接口路径 /api/... 重复拼接 */
function normalizeBaseURL(url: string): string {
  return url.replace(/\/api\/?$/, '')
}

/**
 * 解析 API 根地址
 * - 开发：默认 http://localhost:8000（不含 /api，/api 由各接口路径携带）
 * - 生产 Docker：VITE_API_BASE_URL 留空，走 Nginx 同域反代
 */
export function resolveApiBaseURL(): string {
  const envValue = import.meta.env.VITE_API_BASE_URL
  const raw =
    envValue !== undefined && envValue !== ''
      ? envValue
      : import.meta.env.DEV
        ? 'http://localhost:8000'
        : ''
  return normalizeBaseURL(raw)
}

/**
 * 创建统一的 Axios 实例
 * BaseURL 指向本地 FastAPI 后端
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: resolveApiBaseURL(),
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/** 请求拦截器：自动注入 Authorization Bearer Token */
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_STORAGE_KEY)
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

/** 响应拦截器：401 时清除本地令牌 */
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(TOKEN_STORAGE_KEY)
    }
    return Promise.reject(error)
  },
)

export default apiClient
