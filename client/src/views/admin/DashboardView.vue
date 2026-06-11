<script setup lang="ts">
import {
  inject,
  onMounted,
  onUnmounted,
  ref,
  shallowRef,
  watch,
  type Ref,
} from 'vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import {
  ChatLineRound,
  Document,
  StarFilled,
  User,
} from '@element-plus/icons-vue'
import { fetchAdminStats, fetchHotDocuments } from '@/api/admin'
import type { AdminStats, HotDocumentItem } from '@/types/admin'

/** 仪表盘统计数据 */
const stats = ref<AdminStats | null>(null)
const hotDocs = ref<HotDocumentItem[]>([])
const loading = ref(true)

/** 图表 DOM 容器引用 */
const trendChartRef = ref<HTMLElement | null>(null)
const hotChartRef = ref<HTMLElement | null>(null)
const feedbackChartRef = ref<HTMLElement | null>(null)

/**
 * ECharts 实例必须使用 shallowRef，禁止深度代理
 * 防止 Vue3 响应式包裹导致图表卡顿与内存泄漏
 */
const trendChart = shallowRef<ECharts | null>(null)
const hotChart = shallowRef<ECharts | null>(null)
const feedbackChart = shallowRef<ECharts | null>(null)

/** 从 AdminLayout 注入侧边栏折叠状态 */
const sidebarCollapsed = inject<Ref<boolean>>('adminSidebarCollapsed')

/** ResizeObserver 实例，用于容器尺寸变化时自适应 */
let resizeObserver: ResizeObserver | null = null

/** 顶部指标卡配置 */
const metricCards = ref([
  { key: 'total_documents', label: '总文档数', icon: Document, color: '#2563EB', value: '—' },
  { key: 'total_users', label: '总用户数', icon: User, color: '#64748B', value: '—' },
  { key: 'today_qa_count', label: '今日问答', icon: ChatLineRound, color: '#2563EB', value: '—' },
  { key: 'positive_rate', label: '综合好评率', icon: StarFilled, color: '#10B981', value: '—' },
])

/** 生成近 7 天日期标签 */
function getWeekLabels(): string[] {
  const labels: string[] = []
  for (let i = 6; i >= 0; i--) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    labels.push(`${d.getMonth() + 1}/${d.getDate()}`)
  }
  return labels
}

/** 初始化近 7 天问答趋势折线图（左侧 60%） */
function initTrendChart(data: number[]): void {
  if (!trendChartRef.value) return
  if (trendChart.value) trendChart.value.dispose()

  const chart = echarts.init(trendChartRef.value)
  trendChart.value = chart

  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 16, right: 24, top: 32, bottom: 16, containLabel: true },
    xAxis: {
      type: 'category',
      data: getWeekLabels(),
      axisLine: { lineStyle: { color: '#E2E8F0' } },
      axisLabel: {
        color: '#64748B',
        fontSize: 12,
        interval: 0,
        rotate: 30,
      },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: { lineStyle: { color: '#F1F5F9' } },
      axisLabel: { color: '#64748B', fontSize: 12 },
    },
    series: [{
      name: '问答量',
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 6,
      lineStyle: { color: '#2563EB', width: 2 },
      itemStyle: { color: '#2563EB' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(37, 99, 235, 0.15)' },
          { offset: 1, color: 'rgba(37, 99, 235, 0)' },
        ]),
      },
      data,
    }],
  })
}

/** 初始化热门引用 Top 5 横向条形图（右上 40%） */
function initHotChart(items: HotDocumentItem[]): void {
  if (!hotChartRef.value) return
  if (hotChart.value) hotChart.value.dispose()

  const chart = echarts.init(hotChartRef.value)
  hotChart.value = chart

  const names = items.map((i) => i.file_name).reverse()
  const counts = items.map((i) => i.citation_count).reverse()

  chart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
    xAxis: {
      type: 'value',
      name: '引用次数',
      nameTextStyle: { color: '#94A3B8', fontSize: 11 },
      minInterval: 1,
      splitLine: { lineStyle: { color: '#F1F5F9' } },
      axisLabel: { color: '#64748B', fontSize: 11 },
    },
    yAxis: {
      type: 'category',
      data: names.length > 0 ? names : ['暂无数据'],
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#475569',
        fontSize: 11,
        width: 120,
        overflow: 'truncate',
        align: 'right',
      },
    },
    series: [{
      type: 'bar',
      data: counts.length > 0 ? counts : [0],
      barWidth: 14,
      itemStyle: { color: '#2563EB', borderRadius: [0, 4, 4, 0] },
    }],
  })
}

/** 初始化用户反馈比例环形饼图（右下 40%） */
function initFeedbackChart(positive: number, negative: number): void {
  if (!feedbackChartRef.value) return
  if (feedbackChart.value) feedbackChart.value.dispose()

  const chart = echarts.init(feedbackChartRef.value)
  feedbackChart.value = chart

  const total = positive + negative

  chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: {
      orient: 'vertical',
      right: 16,
      top: 'center',
      textStyle: { color: '#64748B', fontSize: 12 },
      formatter: (name: string) => {
        const value = name === '点赞' ? positive : negative
        const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0.0'
        return `${name}  ${value} (${pct}%)`
      },
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['38%', '50%'],
      avoidLabelOverlap: true,
      label: {
        show: true,
        position: 'inside',
        formatter: '{d}%',
        fontSize: 11,
        color: '#fff',
      },
      labelLine: { show: false },
      data: [
        { name: '点赞', value: positive, itemStyle: { color: '#10B981' } },
        { name: '点踩', value: negative, itemStyle: { color: '#EF4444' } },
      ],
    }],
  })
}

/** 所有图表统一 resize */
function resizeAllCharts(): void {
  trendChart.value?.resize()
  hotChart.value?.resize()
  feedbackChart.value?.resize()
}

/** 加载仪表盘数据并渲染图表 */
async function loadDashboard(): Promise<void> {
  loading.value = true
  try {
    const [statsData, hotData] = await Promise.all([
      fetchAdminStats(),
      fetchHotDocuments(),
    ])
    stats.value = statsData
    hotDocs.value = hotData

    metricCards.value = metricCards.value.map((card) => {
      let value = '—'
      if (statsData) {
        const raw = statsData[card.key as keyof AdminStats]
        if (card.key === 'positive_rate') {
          value = `${raw}%`
        } else {
          value = String(raw)
        }
      }
      return { ...card, value }
    })

    initTrendChart(statsData.weekly_qa)
    initHotChart(hotData)
    initFeedbackChart(
      statsData.feedback_stats.positive,
      statsData.feedback_stats.negative,
    )
  } finally {
    loading.value = false
  }
}

/** 监听侧边栏展开/收缩，延迟 300ms 后 resize 防止图表缩在一角 */
if (sidebarCollapsed) {
  watch(sidebarCollapsed, () => {
    setTimeout(() => resizeAllCharts(), 300)
  })
}

onMounted(async () => {
  await loadDashboard()

  resizeObserver = new ResizeObserver(() => {
    resizeAllCharts()
  })
  const observeTarget = trendChartRef.value?.closest('.chart-row')
  if (observeTarget) {
    resizeObserver.observe(observeTarget)
  }
  window.addEventListener('resize', resizeAllCharts)
})

onUnmounted(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', resizeAllCharts)
  trendChart.value?.dispose()
  hotChart.value?.dispose()
  feedbackChart.value?.dispose()
})
</script>

<template>
  <div v-loading="loading" class="dashboard">
    <!-- 顶部 4 指标卡：栅格化布局 -->
    <el-row :gutter="16" class="metric-row">
      <el-col v-for="card in metricCards" :key="card.key" :xs="24" :sm="12" :lg="6">
        <div class="metric-card">
          <div class="metric-card__body">
            <p class="metric-card__label">{{ card.label }}</p>
            <p class="metric-card__value">{{ card.value }}</p>
          </div>
          <div
            class="metric-card__icon"
            :style="{ color: card.color, background: card.color + '14' }"
          >
            <el-icon :size="20"><component :is="card.icon" /></el-icon>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 图表区域：左 60% 折线 + 右 40% 柱/饼 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :xs="24" :lg="15">
        <div class="chart-card">
          <h3 class="chart-card__title">近 7 天问答趋势</h3>
          <div ref="trendChartRef" class="chart-container chart-container--tall" />
        </div>
      </el-col>
      <el-col :xs="24" :lg="9">
        <div class="chart-card chart-card--half">
          <h3 class="chart-card__title">热门引用 Top 5</h3>
          <div ref="hotChartRef" class="chart-container" />
        </div>
        <div class="chart-card chart-card--half">
          <h3 class="chart-card__title">用户反馈比例</h3>
          <div ref="feedbackChartRef" class="chart-container" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.dashboard {
  min-height: 400px;
}

.metric-row {
  margin-bottom: 16px;
}

.metric-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 20px 24px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
  margin-bottom: 16px;
}

.metric-card__label {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 8px;
}

.metric-card__value {
  font-size: 28px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.2;
}

.metric-card__icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.chart-card {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
  padding: 20px 24px;
  margin-bottom: 16px;
}

.chart-card__title {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 12px;
}

.chart-container {
  width: 100%;
  height: 220px;
}

.chart-container--tall {
  height: 480px;
}
</style>
