<!-- src/views/MetricsQuery.vue -->
<template>
  <div class="metrics-page">
    <div class="page-header">
      <h1>监控指标查询</h1>
      <p class="page-desc">使用 PromQL 语句查询并可视化监控数据</p>
    </div>

    <el-card class="query-card">
      <el-form :inline="true" :model="queryForm" class="query-form">
        <el-form-item label="PromQL 查询语句">
          <el-input
            v-model="queryForm.query"
            placeholder="例如：up 或 node_cpu_seconds_total"
            style="width: 500px"
            clearable
          />
        </el-form-item>

        <el-form-item label="时间范围">
          <el-select v-model="queryForm.minutes" style="width: 160px">
            <el-option label="5分钟" :value="5" />
            <el-option label="15分钟" :value="15" />
            <el-option label="30分钟" :value="30" />
            <el-option label="1小时" :value="60" />
            <el-option label="6小时" :value="360" />
            <el-option label="12小时" :value="720" />
            <el-option label="24小时" :value="1440" />
          </el-select>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="fetchMetrics" :loading="loading">
            查询
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <div class="charts-container">
      <el-card class="chart-card custom-chart">
        <template #header>
          <div class="chart-header">
            <span>自定义监控曲线</span>
            <el-tag v-if="metricsData.resultType === 'matrix'">
              时间序列数量: {{ metricsData.result.length }}
            </el-tag>
          </div>
        </template>

        <div v-if="loading" class="loading-container">
          <el-loading text="加载中..." />
        </div>

        <div v-if="errorMsg" class="error-container">
          <el-alert title="查询失败" :description="errorMsg" type="error" show-icon />
        </div>

        <div ref="chartRef" class="chart-container" />
      </el-card>

      <el-card class="chart-card grafana-chart" v-if="showGrafana">
        <template #header>
          <div class="chart-header">
            <span>Grafana监控面板</span>
            <el-button type="text" size="small" @click="refreshGrafana">
              刷新面板
            </el-button>
          </div>
        </template>

        <div v-if="grafanaLoading" class="loading-container">
          <el-loading text="加载Grafana面板中..." />
        </div>

        <div class="grafana-container">
          <iframe
            :src="grafanaUrl"
            frameborder="0"
            class="grafana-iframe"
            @load="grafanaLoading = false"
          />
        </div>
      </el-card>
    </div>

    <el-empty v-if="!loading && !errorMsg && !metricsData.result.length" description="请输入查询条件并点击查询" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onUnmounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { promQueryRange } from '@/api/prom'

/** ========= types ========= */
interface PrometheusRangeSeries {
  metric: Record<string, string>
  values: [number, string][]
}
interface MetricsData {
  resultType: 'matrix' | 'vector' | 'scalar' | 'string'
  result: PrometheusRangeSeries[]
}
interface PromRawResp {
  status: 'success' | 'error'
  data?: { resultType: MetricsData['resultType']; result: any[] }
  errorType?: string
  error?: string
  warnings?: string[]
}

/** ========= route: 接预置 PromQL ========= */
const route = useRoute()

/**
 * MonitorOverview.vue 传：query.q (PromQL) + query.range (如 5m/15m/1h/6h/24h)
 * 这里转成 minutes 数字
 */
function rangeToMinutes(range: unknown): number | null {
  if (typeof range !== 'string' || !range.trim()) return null

  const s = range.trim()

  if (/^\d+$/.test(s)) return Number(s)

  const m = s.match(/^(\d+)\s*([mhd])$/i)
  if (!m) return null

  const n = Number(m[1])
  const unit = (m[2] ?? '').toLowerCase()

  if (!Number.isFinite(n) || n <= 0) return null
  if (unit === 'm') return n
  if (unit === 'h') return n * 60
  if (unit === 'd') return n * 1440
  return null
}

/**
 * 从 URL query 应用到表单
 * - q -> queryForm.query
 * - range -> queryForm.minutes
 */
function applyFromRouteQuery() {
  const qq = route.query.q
  const rr = route.query.range

  if (typeof qq === 'string' && qq.trim()) {
    queryForm.value.query = qq
  }

  const minutes = rangeToMinutes(rr)
  if (!minutes || !Number.isFinite(minutes)) return

  const allow = [5, 15, 30, 60, 360, 720, 1440] as const

  if ((allow as readonly number[]).includes(minutes)) {
    queryForm.value.minutes = minutes
    return
  }

  let best: number = allow[0]
  let bestDiff = Math.abs(minutes - best)

  for (const a of allow) {
    const d = Math.abs(minutes - a)
    if (d < bestDiff) {
      best = a
      bestDiff = d
    }
  }

  queryForm.value.minutes = best
}

/** ========= state ========= */
const queryForm = ref({
  query: 'up',
  minutes: 5,
})

const loading = ref(false)
const errorMsg = ref('')
const metricsData = ref<MetricsData>({
  resultType: 'matrix',
  result: [],
})

const chartRef = ref<HTMLDivElement | null>(null)
let chartInstance: ECharts | null = null

// Grafana
const grafanaUrl = ref(
  'http://192.168.100.10:32393/d/fac67cfbe174d3ef53eb473d73d9212f/node-exporter-use-method-node?orgId=1&from=2025-11-18T09:34:28.450Z&to=2025-11-18T10:34:28.450Z&timezone=utc&var-datasource=prometheus&var-cluster=&var-instance=192.168.100.10:9100&refresh=30s&viewPanel=panel-2'
)
const grafanaLoading = ref(true)
const showGrafana = ref(true)

/** ========= helpers ========= */
/**
 * ✅ 关键修复：Prometheus 每条 time series 最大点数 ~11000
 * rangeSeconds / step <= 11000
 */
const PROM_MAX_POINTS = 11000

function calcStepByRangeSeconds(rangeSeconds: number) {
  const minStep = 15 // 兜底：至少 15s，避免 1s/0s 触发爆点
  if (!Number.isFinite(rangeSeconds) || rangeSeconds <= 0) return minStep
  const step = Math.ceil(rangeSeconds / PROM_MAX_POINTS)
  return Math.max(minStep, step)
}

function calcStepByMinutes(minutes: number) {
  return calcStepByRangeSeconds(minutes * 60)
}

const handleResize = () => chartInstance?.resize()

const initChart = async () => {
  for (let i = 0; i < 3; i++) {
    await nextTick()
    if (chartRef.value) break
    await new Promise((resolve) => setTimeout(resolve, 100))
  }

  if (!chartRef.value) {
    ElMessage.error('图表初始化失败：容器不存在')
    return false
  }

  if (chartInstance) return true

  chartInstance = echarts.init(chartRef.value)
  window.addEventListener('resize', handleResize)
  return true
}

const drawChart = () => {
  if (!chartInstance) return
  const seriesList = metricsData.value.result || []
  if (seriesList.length === 0) return

  chartInstance.clear()

  const first = seriesList[0]
  if (!first?.values?.length) {
    ElMessage.info('时间序列数据为空')
    return
  }

  const timeLabels = first.values.map(([ts]) => new Date(ts * 1000).toLocaleTimeString())

  const series = seriesList.map((item, idx) => {
    const data = item.values.map(([, v]) => Number.parseFloat(v) || 0)
    const metricLabels = Object.entries(item.metric || {})
      .map(([k, v]) => `${k}=${v}`)
      .join(', ')
      .slice(0, 60)

    return {
      name: metricLabels || `指标${idx + 1}`,
      type: 'line',
      data,
      showSymbol: false,
      smooth: true,
      lineStyle: { width: 2 },
    }
  })

  chartInstance.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: series.map((s: any) => s.name), top: 10, left: 'center', maxHeight: 60 },
    grid: { left: '5%', right: '5%', bottom: '15%', top: '20%', containLabel: true },
    xAxis: {
      type: 'category',
      data: timeLabels,
      axisLabel: { rotate: 45, interval: Math.ceil(timeLabels.length / 15) },
    },
    yAxis: { type: 'value', scale: true },
    series,
  })
}

/** ========= main action ========= */
const fetchMetrics = async () => {
  const q = queryForm.value.query?.trim()
  if (!q) {
    ElMessage.warning('请输入PromQL查询语句')
    return
  }

  loading.value = true
  errorMsg.value = ''

  try {
    const minutes = Number(queryForm.value.minutes) || 5
    const end = Math.floor(Date.now() / 1000)
    const start = end - minutes * 60

    // ✅ 关键：按真实 rangeSeconds 动态算 step，避免 11000 points
    const rangeSeconds = end - start
    const step = calcStepByRangeSeconds(rangeSeconds)

    // 可选：调试用，确认 step 没有变成 1/0/undefined
    // console.log('[prom range]', { start, end, minutes, rangeSeconds, step, q })

    const resp = await promQueryRange({ query: q, start, end, step })
    const raw: PromRawResp = resp.data

    if (raw.status === 'success') {
      const d = raw.data || { resultType: 'matrix', result: [] }
      metricsData.value = {
        resultType: (d.resultType as any) || 'matrix',
        result: (d.result as any) || [],
      }
      const ok = await initChart()
      if (ok) drawChart()
    } else {
      errorMsg.value = raw.error || '查询失败'
    }
  } catch (err: any) {
    errorMsg.value = err?.message || '网络异常'
  } finally {
    loading.value = false
  }
}

const refreshGrafana = () => {
  grafanaLoading.value = true
  const baseUrl = grafanaUrl.value.split('?')[0]
  const queryParams = grafanaUrl.value.split('?')[1] || ''
  grafanaUrl.value = `${baseUrl}?${queryParams}${queryParams ? '&' : ''}refresh=${Date.now()}`
}

/** ========= lifecycle ========= */
onMounted(() => {
  applyFromRouteQuery()
  fetchMetrics()

  setTimeout(() => {
    if (grafanaLoading.value) {
      ElMessage.warning('Grafana面板加载超时，请检查服务是否运行')
    }
  }, 10000)
})

watch(
  () => route.query,
  () => {
    const beforeQ = queryForm.value.query
    const beforeM = queryForm.value.minutes

    applyFromRouteQuery()

    const changed = queryForm.value.query !== beforeQ || queryForm.value.minutes !== beforeM
    if (changed) {
      fetchMetrics()
    }
  },
  { deep: true }
)

watch(
  () => queryForm.value.minutes,
  () => fetchMetrics()
)

watch(
  () => metricsData.value,
  () => {
    if (chartInstance) drawChart()
  },
  { deep: true }
)

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  chartInstance?.dispose()
  chartInstance = null
})
</script>


<style scoped>
.metrics-page {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: 100vh;
}
.page-header {
  margin-bottom: 24px;
}
.query-card {
  margin-bottom: 20px;
  background: #fff;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.query-form {
  padding: 16px 20px;
}
.charts-container {
  display: flex;
  gap: 20px;
  width: 100%;
}
.chart-card {
  flex: 1;
  background: #fff;
  min-height: 500px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.chart-container,
.grafana-container {
  width: 100% !important;
  height: 450px !important;
}
.grafana-iframe {
  width: 100%;
  height: 100%;
  min-height: 450px;
}
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 450px;
}
.error-container {
  padding: 20px;
}

@media (max-width: 1200px) {
  .charts-container {
    flex-direction: column;
  }
}
@media (max-width: 768px) {
  .el-input {
    width: 100% !important;
  }
  .chart-container,
  .grafana-container {
    height: 350px !important;
  }
  .loading-container {
    height: 350px;
  }
}
</style>
