import apiClient from './client'
import type { FeedbackPayload, FeedbackResponse } from '@/types/feedback'

/**
 * 提交或更新用户对 AI 消息的赞踩反馈
 */
export async function submitFeedback(payload: FeedbackPayload): Promise<FeedbackResponse> {
  const { data } = await apiClient.post<FeedbackResponse>('/api/feedback', payload)
  return data
}
