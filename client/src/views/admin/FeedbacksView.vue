<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, CircleClose } from '@element-plus/icons-vue'
import { fetchAdminFeedbacks, resolveFeedback } from '@/api/admin'
import type { AdminFeedbackItem } from '@/types/admin'

/** 反馈列表 */
const feedbacks = ref<AdminFeedbackItem[]>([])
const loading = ref(false)

/** 筛选：全部 / 点赞 / 点踩 */
const filterType = ref<'all' | 'positive' | 'negative'>('all')

/** 加载反馈列表 */
async function loadFeedbacks(): Promise<void> {
  loading.value = true
  try {
    const isPositive =
      filterType.value === 'positive'
        ? true
        : filterType.value === 'negative'
          ? false
          : undefined
    const res = await fetchAdminFeedbacks(isPositive)
    feedbacks.value = res.items
  } finally {
    loading.value = false
  }
}

/** 格式化时间 */
function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN')
}

/** 标记已处理：成功后原地更新按钮与行背景 */
async function handleResolve(row: AdminFeedbackItem): Promise<void> {
  if (row.is_processed) return
  try {
    await resolveFeedback(row.id)
    row.is_processed = true
    ElMessage.success('已标记为已处理')
  } catch {
    ElMessage.error('操作失败，请重试')
  }
}

/**
 * 表格行样式：
 * - 点踩行 → 极淡粉红警示色 #FEF2F2
 * - 已处理行 → 背景淡化
 */
function rowClassName({ row }: { row: AdminFeedbackItem }): string {
  const classes: string[] = []
  if (!row.is_positive) classes.push('row-negative')
  if (row.is_processed) classes.push('row-processed')
  return classes.join(' ')
}

onMounted(() => {
  void loadFeedbacks()
})
</script>

<template>
  <div class="feedbacks-view">
    <!-- 筛选栏 -->
    <div class="filter-card">
      <el-radio-group v-model="filterType" @change="loadFeedbacks">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="positive">点赞</el-radio-button>
        <el-radio-button value="negative">点踩</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 反馈表格 -->
    <div class="table-card">
      <el-table
        v-loading="loading"
        :data="feedbacks"
        stripe
        style="width: 100%"
        :row-class-name="rowClassName"
      >
        <el-table-column label="类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              :type="row.is_positive ? 'success' : 'danger'"
              size="small"
              effect="light"
            >
              <el-icon style="margin-right: 2px">
                <component :is="row.is_positive ? CircleCheck : CircleClose" />
              </el-icon>
              {{ row.is_positive ? '点赞' : '点踩' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="username" label="用户" width="120" show-overflow-tooltip />
        <el-table-column prop="message_content" label="被评价回答" min-width="280" show-overflow-tooltip />
        <el-table-column label="评语" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.comment || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="时间" width="180" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="130" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.is_processed"
              type="primary"
              link
              size="small"
              @click="handleResolve(row)"
            >
              标记已处理
            </el-button>
            <el-button
              v-else
              type="info"
              link
              size="small"
              disabled
            >
              已处理
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.feedbacks-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
  padding: 16px 20px;
}

.table-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
  padding: 20px 24px;
}

/* 点踩行：极淡粉红警示色，表头不受影响 */
:deep(.row-negative > td.el-table__cell) {
  background-color: #fef2f2 !important;
}

:deep(.row-negative:hover > td.el-table__cell) {
  background-color: #fee2e2 !important;
}

/* 已处理行：背景淡化，体现闭环管理 */
:deep(.row-processed > td.el-table__cell) {
  opacity: 0.55;
}

:deep(.row-processed.row-negative > td.el-table__cell) {
  background-color: #fff5f5 !important;
  opacity: 0.7;
}
</style>
