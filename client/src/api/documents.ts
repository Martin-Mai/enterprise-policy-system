import apiClient from './client'
import type { DocumentUploadResponse } from '@/types/admin'

/**
 * 上传文档（支持 PDF / Markdown）
 * 使用 onUploadProgress 回调实时追踪上传进度
 */
export async function uploadDocument(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<DocumentUploadResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const { data } = await apiClient.post<DocumentUploadResponse>(
    '/api/documents/upload',
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
      onUploadProgress: (event) => {
        if (event.total && onProgress) {
          onProgress(Math.round((event.loaded / event.total) * 100))
        }
      },
    },
  )
  return data
}
