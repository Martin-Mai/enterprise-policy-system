<script setup lang="ts">

import { onMounted, ref } from 'vue'

import { ElMessage, ElMessageBox } from 'element-plus'

import { Delete } from '@element-plus/icons-vue'

import { clearAllAuditLogs, fetchAuditLogDetail, fetchAuditLogs } from '@/api/admin'

import { useAuthStore } from '@/stores/authStore'

import type { AdminAuditLogDetail, AdminAuditLogItem } from '@/types/admin'

const authStore = useAuthStore()



/** 审计日志列表 */

const logs = ref<AdminAuditLogItem[]>([])

const loading = ref(false)

const total = ref(0)

const page = ref(1)

const pageSize = ref(20)



/** 筛选条件 */

const searchUsername = ref('')

const dateRange = ref<[Date, Date] | null>(null)



/** 抽屉详情 */

const drawerVisible = ref(false)

const drawerLoading = ref(false)

const detail = ref<AdminAuditLogDetail | null>(null)



/** 提问截断 40 字，回答摘要截断 60 字 */

function truncateText(text: string, maxLen: number): string {

  if (!text) return '—'

  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text

}



/** 加载审计日志 */

async function loadLogs(): Promise<void> {

  loading.value = true

  try {

    const params: Record<string, string | number> = {

      page: page.value,

      page_size: pageSize.value,

    }

    if (searchUsername.value.trim()) {

      params.username = searchUsername.value.trim()

    }

    if (dateRange.value) {

      params.start_date = formatDate(dateRange.value[0])

      params.end_date = formatDate(dateRange.value[1])

    }

    const res = await fetchAuditLogs(params)

    logs.value = res.items

    total.value = res.total

  } finally {

    loading.value = false

  }

}



/** 格式化为 YYYY-MM-DD */

function formatDate(d: Date): string {

  const y = d.getFullYear()

  const m = String(d.getMonth() + 1).padStart(2, '0')

  const day = String(d.getDate()).padStart(2, '0')

  return `${y}-${m}-${day}`

}



/** 格式化时间戳 */

function formatTime(iso: string): string {

  return new Date(iso).toLocaleString('zh-CN')

}



/** 搜索 / 筛选 */

function handleSearch(): void {

  page.value = 1

  void loadLogs()

}



const clearing = ref(false)



/** 二次确认后清空所有审计日志 */

async function handleClearAll(): Promise<void> {

  try {

    await ElMessageBox.confirm(

      '确定要清空所有审计日志吗？此操作不可撤销，所有问答追溯记录将被永久删除。',

      '清空确认',

      {

        confirmButtonText: '确认清空',

        cancelButtonText: '取消',

        type: 'warning',

        confirmButtonClass: 'el-button--danger',

        customClass: 'eps-confirm-dialog',

      },

    )

  } catch {

    return

  }



  clearing.value = true

  try {

    const res = await clearAllAuditLogs()

    ElMessage.success(res.message || '所有审计日志已清空')

    page.value = 1

    await loadLogs()

  } catch {

    ElMessage.error('清空失败，请稍后重试')

  } finally {

    clearing.value = false

  }

}



/** 分页切换 */

function handlePageChange(newPage: number): void {

  page.value = newPage

  void loadLogs()

}



/** 点击行打开右侧抽屉，展示完整检索源数据 */

async function handleRowClick(row: AdminAuditLogItem): Promise<void> {

  drawerVisible.value = true

  drawerLoading.value = true

  detail.value = null

  try {

    detail.value = await fetchAuditLogDetail(row.id)

  } finally {

    drawerLoading.value = false

  }

}



/** JSON 格式化展示 */

function formatJson(data: unknown): string {

  return JSON.stringify(data, null, 2)

}



onMounted(() => {

  void loadLogs()

})

</script>



<template>

  <div class="audit-view">

    <!-- 筛选栏：gap-4 紧凑排列 -->

    <div class="filter-card">

      <el-input

        v-model="searchUsername"

        placeholder="按用户名搜索"

        clearable

        class="filter-input"

        @keyup.enter="handleSearch"

        @clear="handleSearch"

      />

      <el-date-picker

        v-model="dateRange"

        type="daterange"

        range-separator="至"

        start-placeholder="开始日期"

        end-placeholder="结束日期"

        class="filter-date"

        @change="handleSearch"

      />

      <el-button type="primary" @click="handleSearch">查询</el-button>

      <el-button

        v-if="authStore.isAdmin"

        type="danger"

        plain

        :icon="Delete"

        :loading="clearing"

        class="clear-btn"

        @click="handleClearAll"

      >

        清空所有日志

      </el-button>

    </div>



    <!-- 审计表格 -->

    <div class="table-card">

      <el-table

        v-loading="loading"

        :data="logs"

        stripe

        style="width: 100%"

        highlight-current-row

        class="audit-table"

        @row-click="handleRowClick"

      >

        <el-table-column prop="username" label="用户名" width="120" show-overflow-tooltip />

        <el-table-column label="提问" min-width="200" show-overflow-tooltip>

          <template #default="{ row }">

            {{ truncateText(row.question, 40) }}

          </template>

        </el-table-column>

        <el-table-column label="回答摘要" min-width="240" show-overflow-tooltip>

          <template #default="{ row }">

            {{ truncateText(row.answer_summary, 60) }}

          </template>

        </el-table-column>

        <el-table-column label="引用数" width="90" align="center">

          <template #default="{ row }">

            <el-tag size="small" type="info" effect="plain">{{ row.citation_count }}</el-tag>

          </template>

        </el-table-column>

        <el-table-column label="时间" width="180" show-overflow-tooltip>

          <template #default="{ row }">

            {{ formatTime(row.created_at) }}

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



    <!-- 右侧抽屉：控制台级 JSON 详情（宽度 45%） -->

    <el-drawer

      v-model="drawerVisible"

      title="审计详情 · 检索链路"

      direction="rtl"

      size="45%"

      :destroy-on-close="true"

    >

      <div v-loading="drawerLoading" class="drawer-body">

        <template v-if="detail">

          <div class="detail-section">

            <h4>基本信息</h4>

            <div class="info-grid">

              <p><span class="info-label">用户</span>{{ detail.username }}</p>

              <p><span class="info-label">时间</span>{{ formatTime(detail.created_at) }}</p>

            </div>

            <p class="info-question"><span class="info-label">提问</span>{{ detail.question }}</p>

          </div>



          <div class="detail-section">

            <h4>完整回答</h4>

            <p class="answer-text">{{ detail.answer }}</p>

          </div>



          <div class="detail-section">

            <h4>retrieved_chunks</h4>

            <p class="section-desc">混合检索 Top-5 分块完整结构</p>

            <pre class="json-console">{{ formatJson(detail.retrieved_chunks) }}</pre>

          </div>



          <div class="detail-section">

            <h4>citations</h4>

            <p class="section-desc">解析并使用的有效引用列表</p>

            <pre class="json-console">{{ formatJson(detail.citations) }}</pre>

          </div>

        </template>

      </div>

    </el-drawer>

  </div>

</template>



<style scoped>

.audit-view {

  display: flex;

  flex-direction: column;

  gap: 16px;

}



.filter-card {

  display: flex;

  align-items: center;

  flex-wrap: wrap;

  gap: 16px;

  background: #ffffff;

  border: 1px solid #e2e8f0;

  border-radius: 8px;

  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);

  padding: 16px 20px;

}



.filter-input {

  width: 200px;

}



.filter-date {

  width: 280px;

}



.clear-btn {

  margin-left: auto;

}



.table-card {

  background: #ffffff;

  border: 1px solid #e2e8f0;

  border-radius: 8px;

  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);

  padding: 20px 24px;

}



.pagination-wrap {

  display: flex;

  justify-content: flex-end;

  margin-top: 16px;

}



.audit-table :deep(.el-table__row) {

  cursor: pointer;

}



.drawer-body {

  padding: 4px 0;

}



.detail-section {

  margin-bottom: 24px;

}



.detail-section h4 {

  font-size: 13px;

  font-weight: 600;

  color: #334155;

  margin-bottom: 8px;

}



.section-desc {

  font-size: 12px;

  color: #94a3b8;

  margin-bottom: 10px;

}



.info-grid {

  display: grid;

  grid-template-columns: 1fr 1fr;

  gap: 8px;

  margin-bottom: 8px;

}



.info-label {

  display: inline-block;

  width: 48px;

  color: #94a3b8;

  font-size: 13px;

}



.detail-section p {

  font-size: 13px;

  color: #475569;

  line-height: 1.6;

}



.info-question {

  margin-top: 4px;

}



.answer-text {

  font-size: 13px;

  color: #334155;

  line-height: 1.7;

  white-space: pre-wrap;

  padding: 12px 16px;

  background: #f8fafc;

  border: 1px solid #e2e8f0;

  border-radius: 8px;

}

</style>


