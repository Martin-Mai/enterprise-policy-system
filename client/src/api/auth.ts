import apiClient from './client'
import type {
  LoginPayload,
  RegisterPayload,
  TokenResponse,
  UserInfo,
} from '@/types/auth'

/** 用户注册 */
export async function registerUser(payload: RegisterPayload): Promise<UserInfo> {
  const { data } = await apiClient.post<UserInfo>('/api/auth/register', payload)
  return data
}

/** 用户登录，返回 JWT 令牌 */
export async function loginUser(payload: LoginPayload): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/api/auth/login', payload)
  return data
}

/** 获取当前登录用户信息 */
export async function fetchCurrentUser(): Promise<UserInfo> {
  const { data } = await apiClient.get<UserInfo>('/api/auth/me')
  return data
}
