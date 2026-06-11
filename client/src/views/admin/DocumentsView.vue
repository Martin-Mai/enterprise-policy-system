<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Loading, Refresh, UploadFilled } from '@element-plus/icons-vue'
import {
  deleteAdminDocument,
  fetchAdminDocuments,
  reindexDocument,
} from '@/api/admin'
import { uploadDocument } from '@/api/documents'
import type { AdminDocumentItem } from '@/types/admin'

/** 文档列表数据 */
const documents = ref<AdminDocumentItem[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

/** 上传进度（0~100，-1 表示未上传） */
const uploadProgress = ref(-1)
const uploading = ref(false)

/** 正在删除的文档 ID 集合 */
const deletingIds = ref<Set<number>>(new Set())

/** 正在重新向量化的文档 ID 集合 */
const reindexingIds = ref<Set<number>>(new Set())

/** 删除后轮询定时器 */
const deletePollTimers = new Map<number, ReturnType<typeof setTimeout>>()

/** 状态标签映射 */
const statusMap: Record<string, { label: string; type: 'success' | 'warning' | 'info' | 'danger' }> = {
  active: { label: '正常', type: 'success' },
  processing: { label: '处理中', type: 'warning' },
  deleting: { label: '删除中...', type: 'danger' },
}

/** 加载文档列表 */
async function loadDocuments(): Promise<void> {
  loading.value = true
  try {
    const res = await fetchAdminDocuments(page.value, pageSize.value)
    documents.value = res.items
    total.value = res.total
    // 清理已从列表消失的删除中 ID
    const currentIds = new Set(res.items.map((d) => d.id))
    deletingIds.value.forEach((id) => {
      if (!currentIds.has(id)) deletingIds.value.delete(id)
    })
  } finally {
    loading.value = false
  }
}

/** 分页切换 */
function handlePageChange(newPage: number): void {
  page.value = newPage
  void loadDocuments()
}

/** 格式化时间 */
function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN')
}

/** 拖拽/选择文件上传，on-progress 实时更新顶部进度条 */
async function handleUpload(file: File): Promise<boolean> {
  const ext = file.name.split('.').pop()?.toLowerCase()
  if (!ext || !['pdf', 'md'].includes(ext)) {
    ElMessage.error('仅支持 PDF 和 Markdown 文件')
    return false
  }

  uploading.value = true
  uploadProgress.value = 0
  try {
    await uploadDocument(file, (percent) => {
      uploadProgress.value = percent
    })
    ElMessage.success({
      message: `「${file.name}」上传成功，正在后台向量化处理`,
      duration: 3000,
    })
    await loadDocuments()
  } catch {
    ElMessage.error('上传失败，请重试')
  } finally {
    uploading.value = false
    uploadProgress.value = -1
  }
  return false
}

/** 删除后 3 秒延迟刷新，平稳过渡界面 */
function scheduleDeleteRefresh(docId: number): void {
  const existing = deletePollTimers.get(docId)
  if (existing) clearTimeout(existing)

  const timer = setTimeout(() => {
    deletePollTimers.delete(docId)
    void loadDocuments()
  }, 3000)
  deletePollTimers.set(docId, timer)
}

/** 二次确认后删除文档，立即本地更新为「删除中...」 */
async function handleDelete(row: AdminDocumentItem): Promise<void> {
  if (row.status === 'deleting' || deletingIds.value.has(row.id)) return

  try {
    await ElMessageBox.confirm(
      `确定要删除文档「${row.file_name}」吗？此操作不可撤销，向量索引将在后台安全清除。`,
      '删除确认',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'el-button--danger',
        customClass: 'eps-confirm-dialog',
      },
    )
  } catch {
    return
  }

  deletingIds.value.add(row.id)
  const idx = documents.value.findIndex((d) => d.id === row.id)
  if (idx >= 0) documents.value[idx].status = 'deleting'

  try {
    const res = await deleteAdminDocument(row.id)
    ElMessage.success(res.message)
    scheduleDeleteRefresh(row.id)
  } catch {
    ElMessage.error('删除请求失败')
    deletingIds.value.delete(row.id)
    if (idx >= 0) documents.value[idx].status = row.status
  }
}

/** 重新向量化 */
async function handleReindex(row: AdminDocumentItem): Promise<void> {
  if (reindexingIds.value.has(row.id) || row.status === 'deleting') return

  reindexingIds.value.add(row.id)
  try {
    const res = await reindexDocument(row.id)
    ElMessage.success(res.message)
    await loadDocuments()
  } catch {
    ElMessage.error('重新向量化失败，请重试')
  } finally {
    reindexingIds.value.delete(row.id)
  }
}

/** 删除中行样式 */
function deletingRowClass({ row }: { row: AdminDocumentItem }): string {
  return row.status === 'deleting' || deletingIds.value.has(row.id) ? 'row-deleting' : ''
}

onMounted(() => {
  void loadDocuments()
})

onUnmounted(() => {
  deletePollTimers.forEach((timer) => clearTimeout(timer))
  deletePollTimers.clear()
})
</script>

<template>
  <div class="documents-view">
    <!-- 上传卡片：顶部精细进度条 -->
    <div class="upload-card">
      <el-progress
        v-if="uploadProgress >= 0"
        :percentage="uploadProgress"
        :stroke-width="3"
        :show-text="uploadProgress < 100"
        class="upload-progress"
        color="#2563EB"
      />
      <el-upload
        drag
        :auto-upload="true"
        :show-file-list="false"
        accept=".pdf,.md"
        :disabled="uploading"
        :before-upload="handleUpload"
      >
        <el-icon class="upload-icon" :size="36"><UploadFilled /></el-icon>
        <div class="upload-text">
          将 PDF / Markdown 文件拖拽到此处，或 <em>点击上传</em>
        </div>
        <template #tip>
          <p class="upload-tip">支持 .pdf、.md 格式，单文件最大 10MB</p>
        </template>
      </el-upload>
    </div>

    <!-- 文档表格 -->
    <div class="table-card">
      <el-table
        v-loading="loading"
        :data="documents"
        stripe
        style="width: 100%"
        :row-class-name="deletingRowClass"
      >
        <el-table-column prop="file_name" label="文件名" min-width="200" show-overflow-tooltip />
        <el-table-column label="上传时间" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ formatTime(row.upload_time) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="uploader_name" label="上传人" width="120" show-overflow-tooltip />
        <el-table-column label="分块数" width="100" align="center">
          <template #default="{ row }">
            <el-tag type="info" size="small" effect="plain">{{ row.chunk_count }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="130" align="center">
          <template #default="{ row }">
            <el-tag
              :type="statusMap[row.status]?.type ?? 'info'"
              size="small"
              :effect="row.status === 'deleting' ? 'dark' : 'light'"
            >
              <el-icon
                v-if="row.status === 'deleting' || deletingIds.has(row.id)"
                class="is-loading status-icon"
              >
                <Loading />
              </el-icon>
              {{ statusMap[row.status]?.label ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              size="small"
              :icon="Refresh"
              :loading="reindexingIds.has(row.id)"
              :disabled="row.status === 'deleting' || deletingIds.has(row.id)"
              @click="handleReindex(row)"
            >
              重新向量化
            </el-button>
            <el-button
              type="danger"
              link
              size="small"
              :icon="Delete"
              :disabled="row.status === 'deleting' || deletingIds.has(row.id)"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          background
          @current-change="handlePageChange"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.documents-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.upload-card,
.table-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
  padding: 20px 24px;
}

.upload-progress {
  margin-bottom: 16px;
}

.upload-icon {
  color: #2563eb;
  margin-bottom: 8px;
}

.upload-text {
  font-size: 14px;
  color: #64748b;
}

.upload-text em {
  color: #2563eb;
  font-style: normal;
  font-weight: 500;
}

.upload-tip {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 8px;
}

.status-icon {
  margin-right: 4px;
  vertical-align: middle;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

:deep(.row-deleting) {
  opacity: 0.65;
}
</style>
