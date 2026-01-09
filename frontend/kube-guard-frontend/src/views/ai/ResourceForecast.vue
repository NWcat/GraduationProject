<!-- src/views/ai/CpuForecast.vue -->
<template>
  <div class="page">
    <div class="page-head">
      <div>
        <div class="page-title">资源预测</div>
        <div class="page-subtitle">节点 CPU / 节点内存 / Pod CPU 时间序列预测（Prophet）</div>
      </div>

      <div class="head-actions">
        <el-button :loading="loading" @click="refreshActive">
          <el-icon class="mr6"><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <el-card shadow="never" class="card">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <!-- 节点 CPU -->
        <el-tab-pane label="节点 CPU" name="nodeCpu">
          <div class="filters">
            <el-input v-model="nodeCpuForm.node" class="w260" placeholder="节点名，如 k3s-master" clearable />
            <el-input-number v-model="nodeCpuForm.history_minutes" :min="30" :max="10080" controls-position="right" />
            <span class="hint">历史(min)</span>
            <el-input-number v-model="nodeCpuForm.horizon_minutes" :min="10" :max="1440" controls-position="right" />
            <span class="hint">预测(min)</span>
            <el-input-number v-model="nodeCpuForm.step" :min="10" :max="3600" controls-position="right" />
            <span class="hint">步长(s)</span>

            <el-button type="primary" :loading="loading" @click="loadNodeCpu">查询</el-button>

            <el-tag v-if="nodeCpuResp?.metrics?.note" type="info" class="ml8">
              {{ nodeCpuResp.metrics.note }}
            </el-tag>
          </div>

          <div ref="cpuChartRef" class="chart"></div>

          <el-alert
            class="mt16"
            :type="cpuConclusion.type"
            show-icon
            :closable="false"
            title="运维结论"
            :description="cpuConclusion.text"
          />
        </el-tab-pane>

        <!-- 节点 内存 -->
        <el-tab-pane label="节点内存" name="nodeMem">
          <div class="filters">
            <el-input v-model="nodeMemForm.node" class="w260" placeholder="节点名，如 k3s-master" clearable />
            <el-input-number v-model="nodeMemForm.history_minutes" :min="30" :max="10080" controls-position="right" />
            <span class="hint">历史(min)</span>
            <el-input-number v-model="nodeMemForm.horizon_minutes" :min="10" :max="1440" controls-position="right" />
            <span class="hint">预测(min)</span>
            <el-input-number v-model="nodeMemForm.step" :min="10" :max="3600" controls-position="right" />
            <span class="hint">步长(s)</span>

            <el-button type="primary" :loading="loading" @click="loadNodeMem">查询</el-button>

            <el-tag v-if="nodeMemResp?.metrics?.note" type="info" class="ml8">
              {{ nodeMemResp.metrics.note }}
            </el-tag>
          </div>

          <div ref="memChartRef" class="chart"></div>

          <el-alert
            class="mt16"
            :type="memConclusion.type"
            show-icon
            :closable="false"
            title="运维结论"
            :description="memConclusion.text"
          />
        </el-tab-pane>

        <!-- Pod CPU -->
        <el-tab-pane label="Pod CPU" name="podCpu">
          <div class="filters">
            <el-input v-model="podCpuForm.namespace" class="w220" placeholder="namespace，如 default" clearable />
            <el-input v-model="podCpuForm.pod" class="w300" placeholder="pod 名，如 nginx-xxx" clearable />
            <el-input-number v-model="podCpuForm.history_minutes" :min="30" :max="10080" controls-position="right" />
            <span class="hint">历史(min)</span>
            <el-input-number v-model="podCpuForm.horizon_minutes" :min="10" :max="1440" controls-position="right" />
            <span class="hint">预测(min)</span>
            <el-input-number v-model="podCpuForm.step" :min="10" :max="3600" controls-position="right" />
            <span class="hint">步长(s)</span>

            <el-button type="primary" :loading="loading" @click="loadPodCpu">查询</el-button>

            <el-tag v-if="podCpuResp?.metrics?.note" type="info" class="ml8">
              {{ podCpuResp.metrics.note }}
            </el-tag>

            <el-tag v-if="podCpuResp?.meta?.limit_mcpu" type="success" class="ml8">
              limit: {{ Number(podCpuResp.meta.limit_mcpu).toFixed(0) }} mCPU
            </el-tag>
          </div>

          <div ref="podChartRef" class="chart"></div>

          <el-alert
            class="mt16"
            :type="podConclusion.type"
            show-icon
            :closable="false"
            title="运维结论"
            :description="podConclusion.text"
          />
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { fetchCpuForecast, fetchMemForecast, fetchPodCpuForecast } from '@/api/ai'
import type { CpuForecastResp, MemForecastResp, PodCpuForecastResp } from '@/api/ai'

type AlertType = 'success' | 'warning' | 'error' | 'info'

const activeTab = ref<'nodeCpu' | 'nodeMem' | 'podCpu'>('nodeCpu')
const loading = ref(false)

// ====== 表单默认值（你可以换成真实默认节点/namespace/pod）======
const nodeCpuForm = ref({
  node: 'k3s-master',
  history_minutes: 240,
  horizon_minutes: 120,
  step: 60
})

const nodeMemForm = ref({
  node: 'k3s-master',
  history_minutes: 240,
  horizon_minutes: 120,
  step: 60
})

const podCpuForm = ref({
  namespace: 'default',
  pod: '',
  history_minutes: 240,
  horizon_minutes: 120,
  step: 60
})

// ====== 响应数据 ======
const nodeCpuResp = ref<CpuForecastResp | null>(null)
const nodeMemResp = ref<MemForecastResp | null>(null)
const podCpuResp = ref<PodCpuForecastResp | null>(null)

// ====== 图表 refs ======
const cpuChartRef = ref<HTMLDivElement>()
const memChartRef = ref<HTMLDivElement>()
const podChartRef = ref<HTMLDivElement>()

let cpuChart: echarts.ECharts | null = null
let memChart: echarts.ECharts | null = null
let podChart: echarts.ECharts | null = null

function ensureChart(dom?: HTMLDivElement, exist?: echarts.ECharts | null) {
  if (!dom) return null
  if (exist) return exist
  return echarts.init(dom)
}

function toSeriesHistoryPercent(history: { ts: number; value: number }[]) {
  return history.map(p => [p.ts * 1000, Number(p.value.toFixed(2))])
}

function toSeriesForecastBand(forecast: { ts: number; yhat: number; yhat_lower: number; yhat_upper: number }[]) {
  const yhat = forecast.map(p => [p.ts * 1000, Number(p.yhat.toFixed(2))])
  const upper = forecast.map(p => [p.ts * 1000, Number(p.yhat_upper.toFixed(2))])
  const lower = forecast.map(p => [p.ts * 1000, Number(p.yhat_lower.toFixed(2))])
  return { yhat, upper, lower }
}

function renderPercentChart(
  chart: echarts.ECharts,
  title: string,
  history: any[],
  forecast: any[],
  upper: any[],
  lower: any[]
) {
  chart.setOption({
    title: { text: title, left: 'left', textStyle: { fontSize: 14 } },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v: number) => `${v}%`
    },
    legend: { data: ['历史', '预测', '预测区间'] },
    grid: { left: 48, right: 24, top: 48, bottom: 40 },
    xAxis: { type: 'time' },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { formatter: '{value}%' }
    },
    series: [
      { name: '历史', type: 'line', data: history, smooth: true, lineStyle: { width: 2 }, symbolSize: 5 },
      { name: '预测', type: 'line', data: forecast, smooth: true, lineStyle: { type: 'dashed' }, symbolSize: 5 },
      { name: '预测区间', type: 'line', data: upper, lineStyle: { opacity: 0 }, stack: 'confidence', symbol: 'none' },
      {
        name: '预测区间',
        type: 'line',
        data: lower,
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(100, 149, 237, 0.25)' },
        stack: 'confidence',
        symbol: 'none'
      }
    ]
  })
}

function renderPodCpuChart(
  chart: echarts.ECharts,
  title: string,
  unit: string,
  history: any[],
  forecast: any[],
  upper: any[],
  lower: any[],
  limitMcpu?: number | null
) {
  chart.setOption({
    title: { text: title, left: 'left', textStyle: { fontSize: 14 } },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        // params: array
        const lines: string[] = []
        if (params?.length) {
          const ts = new Date(params[0].value[0]).toLocaleString()
          lines.push(ts)
          for (const it of params) {
            const v = it.value?.[1]
            if (typeof v === 'number') {
              let extra = ''
              if (limitMcpu && (it.seriesName === '历史' || it.seriesName === '预测')) {
                const pct = (v / limitMcpu) * 100
                extra = `（${pct.toFixed(1)}% of limit）`
              }
              lines.push(`${it.marker}${it.seriesName}: ${v.toFixed(1)} ${unit} ${extra}`)
            }
          }
        }
        return lines.join('<br/>')
      }
    },
    legend: { data: ['历史', '预测', '预测区间'] },
    grid: { left: 56, right: 24, top: 48, bottom: 40 },
    xAxis: { type: 'time' },
    yAxis: {
      type: 'value',
      min: 0,
      axisLabel: { formatter: (v: number) => `${v}` }
    },
    series: [
      { name: '历史', type: 'line', data: history, smooth: true, lineStyle: { width: 2 }, symbolSize: 5 },
      { name: '预测', type: 'line', data: forecast, smooth: true, lineStyle: { type: 'dashed' }, symbolSize: 5 },
      { name: '预测区间', type: 'line', data: upper, lineStyle: { opacity: 0 }, stack: 'confidence', symbol: 'none' },
      {
        name: '预测区间',
        type: 'line',
        data: lower,
        lineStyle: { opacity: 0 },
        areaStyle: { color: 'rgba(100, 149, 237, 0.25)' },
        stack: 'confidence',
        symbol: 'none'
      }
    ]
  })
}

function peakOfForecast(forecast: { yhat: number; yhat_upper: number }[]) {
  let peak = 0
  for (const p of forecast || []) {
    peak = Math.max(peak, p.yhat, p.yhat_upper)
  }
  return peak
}

function conclusionByPercent(peak: number, resName: string): { type: AlertType; text: string } {
  if (!isFinite(peak) || peak <= 0) {
    return { type: 'info', text: `${resName} 预测数据不足或预测值接近 0，请检查历史点数/采集链路。` }
  }
  if (peak < 60) return { type: 'success', text: `${resName} 预测峰值约 ${peak.toFixed(1)}%，处于安全区间，无需扩容。` }
  if (peak < 80) return { type: 'warning', text: `${resName} 预测峰值约 ${peak.toFixed(1)}%，可能接近高负载，建议提前评估扩容/限流。` }
  return { type: 'error', text: `${resName} 预测峰值约 ${peak.toFixed(1)}%，高风险！建议提前扩容或启用自愈策略。` }
}

function conclusionByPodCpu(peakMcpu: number, limitMcpu?: number | null) {
  if (!isFinite(peakMcpu) || peakMcpu <= 0) {
    return { type: 'info' as AlertType, text: `Pod CPU 预测数据不足或预测值接近 0，请检查 cadvisor 指标采集。` }
  }
  if (limitMcpu && limitMcpu > 0) {
    const pct = (peakMcpu / limitMcpu) * 100
    if (pct < 60) return { type: 'success' as AlertType, text: `预测峰值约 ${peakMcpu.toFixed(1)} mCPU（${pct.toFixed(1)}% of limit），安全。` }
    if (pct < 80) return { type: 'warning' as AlertType, text: `预测峰值约 ${peakMcpu.toFixed(1)} mCPU（${pct.toFixed(1)}% of limit），建议关注并准备扩容/副本数提升。` }
    return { type: 'error' as AlertType, text: `预测峰值约 ${peakMcpu.toFixed(1)} mCPU（${pct.toFixed(1)}% of limit），高风险！建议提前扩容/加副本。` }
  }
  // 没有 limit，就按经验阈值给个结论（你也可改成按 request/节点核数）
  if (peakMcpu < 300) return { type: 'success' as AlertType, text: `预测峰值约 ${peakMcpu.toFixed(1)} mCPU，整体偏低。` }
  if (peakMcpu < 700) return { type: 'warning' as AlertType, text: `预测峰值约 ${peakMcpu.toFixed(1)} mCPU，可能接近瓶颈，建议关注。` }
  return { type: 'error' as AlertType, text: `预测峰值约 ${peakMcpu.toFixed(1)} mCPU，高风险，建议扩容/加副本。` }
}

// ====== computed 结论 ======
const cpuConclusion = computed(() => {
  const peak = peakOfForecast(nodeCpuResp.value?.forecast || [])
  return conclusionByPercent(peak, '节点 CPU')
})

const memConclusion = computed(() => {
  const peak = peakOfForecast(nodeMemResp.value?.forecast || [])
  return conclusionByPercent(peak, '节点内存')
})

const podConclusion = computed(() => {
  const peak = peakOfForecast(podCpuResp.value?.forecast || [])
  const limit = podCpuResp.value?.meta?.limit_mcpu ?? null
  return conclusionByPodCpu(peak, limit)
})

// ====== 数据加载 ======
async function loadNodeCpu() {
  if (!nodeCpuForm.value.node) return ElMessage.warning('请输入节点名')
  loading.value = true
  try {
    const { data } = await fetchCpuForecast({ ...nodeCpuForm.value })
    nodeCpuResp.value = data

    cpuChart = ensureChart(cpuChartRef.value!, cpuChart)
    const history = toSeriesHistoryPercent(data.history || [])
    const { yhat, upper, lower } = toSeriesForecastBand(data.forecast || [])
    renderPercentChart(cpuChart!, '节点 CPU 使用率（%）', history, yhat, upper, lower)
  } catch (e: any) {
    ElMessage.error(e?.message || '节点 CPU 预测失败')
  } finally {
    loading.value = false
  }
}

async function loadNodeMem() {
  if (!nodeMemForm.value.node) return ElMessage.warning('请输入节点名')
  loading.value = true
  try {
    const { data } = await fetchMemForecast({ ...nodeMemForm.value })
    nodeMemResp.value = data

    memChart = ensureChart(memChartRef.value!, memChart)
    const history = toSeriesHistoryPercent(data.history || [])
    const { yhat, upper, lower } = toSeriesForecastBand(data.forecast || [])
    renderPercentChart(memChart!, '节点内存使用率（%）', history, yhat, upper, lower)
  } catch (e: any) {
    ElMessage.error(e?.message || '节点内存预测失败')
  } finally {
    loading.value = false
  }
}

async function loadPodCpu() {
  if (!podCpuForm.value.namespace) return ElMessage.warning('请输入 namespace')
  if (!podCpuForm.value.pod) return ElMessage.warning('请输入 pod 名')
  loading.value = true
  try {
    const { data } = await fetchPodCpuForecast({ ...podCpuForm.value })
    podCpuResp.value = data

    podChart = ensureChart(podChartRef.value!, podChart)
    const history = (data.history || []).map(p => [p.ts * 1000, Number(p.value.toFixed(2))])
    const { yhat, upper, lower } = toSeriesForecastBand(data.forecast || [])
    const unit = data.meta?.unit || 'mCPU'
    const limit = data.meta?.limit_mcpu ?? null

    renderPodCpuChart(
      podChart!,
      `Pod CPU 使用量（${unit}）`,
      unit,
      history,
      yhat,
      upper,
      lower,
      limit
    )
  } catch (e: any) {
    ElMessage.error(e?.message || 'Pod CPU 预测失败')
  } finally {
    loading.value = false
  }
}

function refreshActive() {
  if (activeTab.value === 'nodeCpu') return loadNodeCpu()
  if (activeTab.value === 'nodeMem') return loadNodeMem()
  return loadPodCpu()
}

function onTabChange() {
  // 切换 Tab 时把图 resize 一下，避免容器宽度变化导致图显示异常
  setTimeout(() => {
    cpuChart?.resize()
    memChart?.resize()
    podChart?.resize()
  }, 0)
}

// resize 监听
function handleResize() {
  cpuChart?.resize()
  memChart?.resize()
  podChart?.resize()
}

onMounted(async () => {
  window.addEventListener('resize', handleResize)
  // 默认先拉节点CPU
  await loadNodeCpu()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  cpuChart?.dispose()
  memChart?.dispose()
  podChart?.dispose()
  cpuChart = null
  memChart = null
  podChart = null
})
</script>

<style scoped>
.page { padding: 16px; }

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}

.page-title { font-size: 20px; font-weight: 700; }
.page-subtitle { color: #8a8f98; margin-top: 4px; font-size: 13px; }

.card { border-radius: 10px; }

.filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 12px;
}

.hint {
  color: #8a8f98;
  font-size: 12px;
  margin-left: -6px;
  margin-right: 6px;
}

.chart { height: 420px; width: 100%; }

.mt16 { margin-top: 16px; }
.mr6 { margin-right: 6px; }
.ml8 { margin-left: 8px; }

.w220 { width: 220px; }
.w260 { width: 260px; }
.w300 { width: 300px; }
</style>
