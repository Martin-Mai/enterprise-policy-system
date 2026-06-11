/** 反馈提交请求体 */
export interface FeedbackPayload {
  message_id: number
  is_positive: boolean
  comment: string
}

/** 反馈提交响应 */
export interface FeedbackResponse {
  message: string
}
