import axios, { type AxiosInstance } from 'axios'

/** localStorage 中 JWT 令牌的键名 */
export const TOKEN_STORAGE_KEY = 'eps_access_token'

/**
 * 创建统一的 Axios 实例
 * BaseURL 指向本地 FastAPI 后端
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: 'http://localhost:8000',
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
