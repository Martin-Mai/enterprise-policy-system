import apiClient from './client'
import type {
  AdminAuditLogDetail,
  AdminAuditLogListResponse,
  AdminDeleteProcessingResponse,
  AdminDocumentListResponse,
  AdminFeedbackListResponse,
  AdminStats,
  HotDocumentItem,
} from '@/types/admin'

/** 获取仪表盘核心统计数据 */
export async function fetchAdminStats(): Promise<AdminStats> {
  const { data } = await apiClient.get<AdminStats>('/api/admin/stats')
  return data
}

/** 获取热门引用文档 Top 5 */
export async function fetchHotDocuments(): Promise<HotDocumentItem[]> {
  const { data } = await apiClient.get<{ items: HotDocumentItem[] }>(
    '/api/admin/hot-documents',
  )
  return data.items
}

/** 获取管理员文档列表 */
export async function fetchAdminDocuments(
  page = 1,
  pageSize = 20,
): Promise<AdminDocumentListResponse> {
  const { data } = await apiClient.get<AdminDocumentListResponse>(
    '/api/admin/documents',
    { params: { page, page_size: pageSize } },
  )
  return data
}

/** 异步级联删除文档 */
export async function deleteAdminDocument(
  docId: number,
): Promise<AdminDeleteProcessingResponse> {
  const { data } = await apiClient.delete<AdminDeleteProcessingResponse>(
    `/api/admin/documents/${docId}`,
  )
  return data
}

/** 分页查询审计日志 */
export async function fetchAuditLogs(params: {
  username?: string
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}): Promise<AdminAuditLogListResponse> {
  const { data } = await apiClient.get<AdminAuditLogListResponse>(
    '/api/admin/audit-logs',
    { params },
  )
  return data
}

/** 获取审计日志详情 */
export async function fetchAuditLogDetail(
  logId: number,
): Promise<AdminAuditLogDetail> {
  const { data } = await apiClient.get<AdminAuditLogDetail>(
    `/api/admin/audit-logs/${logId}`,
  )
  return data
}

/** 清空所有审计日志 */
export async function clearAllAuditLogs(): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.delete<{ status: string; message: string }>(
    '/api/admin/audit-logs',
  )
  return data
}

/** 获取反馈列表 */
export async function fetchAdminFeedbacks(
  isPositive?: boolean,
): Promise<AdminFeedbackListResponse> {
  const { data } = await apiClient.get<AdminFeedbackListResponse>(
    '/api/admin/feedbacks',
    { params: isPositive !== undefined ? { is_positive: isPositive } : {} },
  )
  return data
}

/** 重新向量化文档 */
export async function reindexDocument(
  docId: number,
): Promise<{ status: string; message: string }> {
  const { data } = await apiClient.post<{ status: string; message: string }>(
    `/api/admin/documents/reindex/${docId}`,
  )
  return data
}

/** 标记反馈为已处理 */
export async function resolveFeedback(
  feedbackId: number,
): Promise<{ id: number; is_processed: boolean; message: string }> {
  const { data } = await apiClient.patch(
    `/api/admin/feedbacks/${feedbackId}/resolve`,
  )
  return data
}
