/** 用户信息 */
export interface UserInfo {
  id: number
  username: string
  role: string
  created_at: string
}

/** 登录请求体 */
export interface LoginPayload {
  username: string
  password: string
}

/** 注册请求体 */
export interface RegisterPayload {
  username: string
  password: string
}

/** 登录响应 */
export interface TokenResponse {
  access_token: string
  token_type: string
}
