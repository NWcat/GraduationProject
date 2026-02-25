<template>
  <div class="page">
    <div class="page-head">
      <div>
        <div class="page-title">任务分析</div>
        <div class="page-subtitle">任务执行统计、成功率分析、历史时间线</div>
      </div>
      <div class="actions">
        <el-button @click="refresh" :loading="statsLoading">刷新统计</el-button>
      </div>
    </div>

    <!-- 统计卡片 -->
    <el-row :gutter="20">
      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card">
          <template #header>
            <div class="card-header">
              <span>总任务数</span>
            </div>
          </template>
          <div class="stat-value">{{ stats.total }}</div>
          <div class="stat-subtitle">最近 {{ days }} 天</div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card success">
          <template #header>
            <div class="card-header">
              <span>成功任务</span>
            </div>
          </template>
          <div class="stat-value">{{ stats.success }}</div>
          <div class="stat-subtitle">成功率: {{ (stats.success_rate * 100).toFixed(1) }}%</div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card failed">
          <template #header>
            <div class="card-header">
              <span>失败任务</span>
            </div>
          </template>
          <div class="stat-value">{{ stats.failed }}</div>
          <div class="stat-subtitle">失败率: {{ ((stats.failed / stats.total) * 100).toFixed(1) }}%</div>
        </el-card>
      </el-col>

      <el-col :xs="24" :sm="12" :md="6">
        <el-card class="stat-card">
          <template #header>
            <div class="card-header">
              <span>平均耗时</span>
            </div>
          </template>
          <div class="stat-value">{{ (stats.avg_duration / 1000).toFixed(1) }}s</div>
          <div class="stat-subtitle">其他: 取消{{ stats.cancelled }}, 暂停{{ stats.paused }}</div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 统计过滤和图表 -->
    <el-card shadow="never" class="card mt20">
      <template #header>
        <div class="card-header">
          <span>统计详情</span>
          <el-select v-model="filterType" clearable class="ml20" style="width: 200px" placeholder="按任务类型过滤">
            <el-option label="所有类型" :value="undefined" />
            <el-option label="AI 执行" value="ai_execute" />
            <el-option label="AI 预测" value="ai_forecast" />
            <el-option label="AI 建议" value="ai_suggestions" />
          </el-select>
          <el-select v-model="days" class="ml10" style="width: 120px" @change="refresh">
            <el-option label="最近 7 天" :value="7" />
            <el-option label="最近 14 天" :value="14" />
            <el-option label="最近 30 天" :value="30" />
            <el-option label="最近 90 天" :value="90" />
          </el-select>
        </div>
      </template>

      <!-- 按类型统计表格 -->
      <div v-if="Object.keys(stats.by_type || {}).length > 0" class="mb30">
        <h4>按任务类型统计</h4>
        <el-table :data="typeStatsData" stripe size="small">
          <el-table-column prop="type" label="任务类型" width="150" />
          <el-table-column prop="total" label="总数" width="100" />
          <el-table-column prop="success" label="成功" width="100" />
          <el-table-column prop="failed" label="失败" width="100" />
          <el-table-column label="成功率" width="100">
            <template #default="{ row }">
              <el-progress :percentage="row.total > 0 ? (row.success / row.total) * 100 : 0" :color="getColor" />
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 按日期统计表格 -->
      <div v-if="(stats.by_day || []).length > 0">
        <h4>按日期统计</h4>
        <el-table :data="stats.by_day" stripe size="small" max-height="300">
          <el-table-column prop="day" label="日期" width="120" />
          <el-table-column prop="total" label="总数" width="80" />
          <el-table-column prop="success" label="成功" width="80" />
          <el-table-column prop="failed" label="失败" width="80" />
          <el-table-column label="成功率" width="150">
            <template #default="{ row }">
              <el-progress :percentage="row.total > 0 ? (row.success / row.total) * 100 : 0" :color="getColor" />
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <!-- 执行历史时间线 -->
    <el-card shadow="never" class="card mt20">
      <template #header>
        <div class="card-header">
          <span>执行历史时间线</span>
          <el-button size="small" @click="loadHistory" :loading="historyLoading">加载更多</el-button>
        </div>
      </template>

      <el-timeline v-if="timeline.length > 0">
        <el-timeline-item
          v-for="(item, index) in timeline"
          :key="index"
          :timestamp="formatTimestamp(item.timestamp)"
          placement="top"
          :type="getEventType(item.event, item.status)"
        >
          <p>
            <b>{{ item.task_id }}</b>
            <el-tag :type="getStatusType(item.status)">{{ item.status }}</el-tag>
          </p>
          <p class="mono">{{ getEventLabel(item.event) }}</p>
        </el-timeline-item>
      </el-timeline>
      <el-empty v-else description="暂无历史数据" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { getTaskStats, getTaskHistory } from '@/api/tasks_advanced'

const stats = ref({
  total: 0,
  success: 0,
  failed: 0,
  cancelled: 0,
  paused: 0,
  success_rate: 0,
  avg_duration: 0,
  by_type: {} as Record<string, any>,
  by_day: [] as any[]
})

const timeline = ref<any[]>([])
const filterType = ref<string | undefined>()
const days = ref(7)
const statsLoading = ref(false)
const historyLoading = ref(false)

const typeStatsData = computed(() => {
  const items = Object.entries(stats.value.by_type || {}).map(([type, data]: [string, any]) => ({
    type: type === 'ai_execute' ? 'AI 执行' : type === 'ai_forecast' ? 'AI 预测' : 'AI 建议',
    total: data.total || 0,
    success: data.success || 0,
    failed: data.failed || 0
  }))
  return items
})

function getColor(percentage: number): string | { color: string }[] {
  if (percentage >= 90) return '#67C23A'
  if (percentage >= 70) return '#409EFF'
  if (percentage >= 50) return '#E6A23C'
  return '#F56C6C'
}

function formatTimestamp(ts: number): string {
  const date = new Date(ts * 1000)
  return date.toLocaleString('zh-CN')
}

function getEventType(event: string, status?: string): string {
  if (event === 'task_completed') {
    if (status === 'SUCCESS') return 'success'
    if (status === 'FAILED') return 'danger'
    if (status === 'CANCELLED') return ''
  }
  return 'primary'
}

function getStatusType(status: string): string {
  if (status === 'SUCCESS') return 'success'
  if (status === 'FAILED') return 'danger'
  if (status === 'RUNNING') return 'info'
  if (status === 'CANCELLED') return ''
  return ''
}

function getEventLabel(event: string): string {
  switch (event) {
    case 'task_created':
      return '任务创建'
    case 'task_started':
      return '任务开始执行'
    case 'task_completed':
      return '任务执行完成'
    default:
      return event
  }
}

async function refresh() {
  statsLoading.value = true
  try {
    const response = await getTaskStats(filterType.value, days.value)
    if (response.data.code === 0) {
      stats.value = response.data.data
    }
  } catch (err) {
    ElMessage.error('加载统计数据失败')
  } finally {
    statsLoading.value = false
  }
  await loadHistory()
}

async function loadHistory() {
  historyLoading.value = true
  try {
    const response = await getTaskHistory(days.value, filterType.value)
    if (response.data.code === 0) {
      timeline.value = response.data.data.timeline || []
    }
  } catch (err) {
    ElMessage.error('加载历史数据失败')
  } finally {
    historyLoading.value = false
  }
}

onMounted(() => {
  refresh()
})
</script>

<style scoped>
.page {
  padding: 20px;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  font-size: 24px;
  font-weight: bold;
  margin-bottom: 4px;
}

.page-subtitle {
  font-size: 12px;
  color: #909399;
}

.actions {
  display: flex;
  gap: 10px;
}

.stat-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  text-align: center;
  min-height: 120px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.stat-card.success {
  background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%);
}

.stat-card.failed {
  background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);
}

.stat-value {
  font-size: 32px;
  font-weight: bold;
  margin: 10px 0;
}

.stat-subtitle {
  font-size: 12px;
  opacity: 0.8;
}

.card {
  margin-top: 20px;
}

.mt20 {
  margin-top: 20px !important;
}

.ml20 {
  margin-left: 20px;
}

.ml10 {
  margin-left: 10px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.mb30 {
  margin-bottom: 30px;
}

h4 {
  margin: 0 0 15px 0;
  color: #333;
}

.mono {
  font-family: monospace;
  font-size: 12px;
  color: #666;
  margin: 5px 0 0 0;
}
</style>
