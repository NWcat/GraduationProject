<template>
  <div class="wall">
    <!-- 顶部栏 -->
    <div class="topbar">
      <div class="title">
        <div class="h1">K3s 监控大屏</div>
        <div class="sub">Prometheus 聚合总览 · {{ nowText }}</div>
      </div>

      <div class="actions">
        <div class="pill">
          <span class="label">Theme</span>
          <el-switch
            v-model="isDark"
            size="small"
            inline-prompt
            active-text="Dark"
            inactive-text="Light"
            @change="applyTheme"
          />
        </div>

        <div class="pill">
          <span class="label">Range</span>
          <el-select v-model="range" size="small" class="w140" @change="refresh">
            <el-option v-for="r in rangeOptions" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </div>

        <div class="pill">
          <span class="label">Auto</span>
          <el-switch v-model="autoRefresh" size="small" />
        </div>

        <el-button size="small" class="btn" :loading="loading" @click="refresh">
          <el-icon class="mr6"><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
    </div>

    <!-- 主体 -->
    <div class="grid">
      <!-- 左：KPI + 趋势 -->
      <div class="left">
        <!-- KPI -->
        <div class="kpis">
          <div class="kpi" :class="health.promOk ? 'ok' : 'bad'">
            <div class="k">Prometheus</div>
            <div class="v">{{ health.promOk ? 'OK' : 'DOWN' }}</div>
            <div class="t mono">sum(up) &gt; 0</div>
          </div>

          <div class="kpi">
            <div class="k">Nodes Ready</div>
            <div class="v">
              {{ health.nodesReady }}<span class="muted"> / {{ health.nodesTotal }}</span>
            </div>
            <div class="t">Ready/Total</div>
          </div>

          <div class="kpi warn">
            <div class="k">Alerts</div>
            <div class="v">
              {{ health.alertFiring }}<span class="muted"> firing</span>
              <span class="sep">·</span>
              {{ health.alertPending }}<span class="muted"> pending</span>
            </div>
            <div class="t mono">ALERTS</div>
          </div>

          <div class="kpi">
            <div class="k">CPU Used</div>
            <div class="v">{{ fmtPct(resource.cpuUsedPct) }}</div>
            <div class="t">cluster avg</div>
          </div>

          <div class="kpi">
            <div class="k">MEM Used</div>
            <div class="v">{{ fmtPct(resource.memUsedPct) }}</div>
            <div class="t">cluster sum</div>
          </div>

          <div class="kpi">
            <div class="k">FS Used</div>
            <div class="v">{{ fmtPct(resource.fsUsedPct) }}</div>
            <div class="t">node fs</div>
          </div>
        </div>

        <!-- 趋势 -->
        <div class="charts">
          <div class="panel">
            <div class="ph">
              <div class="pt">CPU 使用率趋势</div>
              <div class="pv mono">{{ fmtPct(resource.cpuUsedPct) }}</div>
            </div>
            <div ref="cpuRef" class="chart"></div>
          </div>

          <div class="panel">
            <div class="ph">
              <div class="pt">内存使用率趋势</div>
              <div class="pv mono">{{ fmtPct(resource.memUsedPct) }}</div>
            </div>
            <div ref="memRef" class="chart"></div>
          </div>

          <div class="panel">
            <div class="ph">
              <div class="pt">存储使用率趋势</div>
              <div class="pv mono">{{ fmtPct(resource.fsUsedPct) }}</div>
            </div>
            <div ref="fsRef" class="chart"></div>
          </div>
        </div>
      </div>

      <!-- 右：TopN -->
      <div class="right">
        <div class="topbox">
          <div class="tb-head">
            <div class="tb-title">Pod TopN</div>
            <el-radio-group v-model="topKind" size="small" class="seg">
              <el-radio-button label="cpu">CPU</el-radio-button>
              <el-radio-button label="mem">MEM</el-radio-button>
              <el-radio-button label="net">NET</el-radio-button>
            </el-radio-group>
          </div>

          <div class="tb-body">
            <div class="thead">
              <div>#</div>
              <div>namespace/pod</div>
              <div class="r">value</div>
            </div>

            <div v-if="topRows.length === 0" class="empty muted">
              TopN 暂无数据（可能缺 kube-state-metrics / cAdvisor 指标）
            </div>

            <div v-for="row in topRows" :key="row.rankKey" class="trow">
              <div class="mono">{{ row.rank }}</div>
              <div class="name">
                <div class="main mono">{{ row.ns }}/{{ row.pod }}</div>
                <div class="sub muted">{{ row.instance || '-' }}</div>
              </div>
              <div class="mono r">{{ row.valueText }}</div>
            </div>
          </div>
        </div>

        <div class="footnote">
          <div class="muted">数据源：Prometheus（{{ range }}）· 后端聚合：/api/monitor/overview</div>
        </div>
      </div>
    </div>

    <div v-if="err" class="err">
      <el-alert type="error" show-icon :closable="false" :title="'加载失败'" :description="err" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import type { ECharts } from 'echarts'
import { fetchMonitorOverview } from '@/api/monitor'

/** =========================
 *  Types: 修复 TS 报错核心
 * ========================= */
type ApiStatus = 'success' | 'error'

type SeriesPoint = [number, number] // [tsSeconds, value]

type MonitorHealth = {
  promOk: boolean
  nodesTotal: number
  nodesReady: number
  alertFiring: number
  alertPending: number
}

type MonitorResource = {
  cpuUsedPct: number
  memUsedPct: number
  fsUsedPct: number
}

type TopMetric = Record<string, string | undefined>

type TopItem = {
  rank?: number
  value?: number
  valueText?: string
  metric?: TopMetric
}

type MonitorOverviewData = {
  time?: { now?: string }
  health: MonitorHealth
  resource: MonitorResource
  trends: {
    cpuUsedPct: SeriesPoint[]
    memUsedPct: SeriesPoint[]
    fsUsedPct: SeriesPoint[]
  }
  top: {
    podCpu: TopItem[]
    podMem: TopItem[]
    podNet: TopItem[]
  }
}

type ApiResp<T> = { status: ApiStatus; data: T; message?: string }

/** =========================
 *  UI State
 * ========================= */
type TopKind = 'cpu' | 'mem' | 'net'
const rangeOptions = [
  { label: '最近 5 分钟', value: '5m' },
  { label: '最近 15 分钟', value: '15m' },
  { label: '最近 1 小时', value: '1h' },
  { label: '最近 6 小时', value: '6h' },
  { label: '最近 24 小时', value: '24h' },
]

const loading = ref(false)
const err = ref('')
const range = ref('15m')
const autoRefresh = ref(true)
const topKind = ref<TopKind>('cpu')
const nowText = ref('—')

/** =========================
 *  Theme: Dark/Light
 * ========================= */
const isDark = ref<boolean>((localStorage.getItem('mw_theme') || 'dark') === 'dark')

function applyTheme() {
  const theme = isDark.value ? 'dark' : 'light'
  localStorage.setItem('mw_theme', theme)
  document.documentElement.setAttribute('data-theme', theme)
  // 主题切换后重绘图表（颜色会变）
  renderCharts()
}

onMounted(() => applyTheme())

/** =========================
 *  Data models
 * ========================= */
const health = reactive<MonitorHealth>({
  promOk: false,
  nodesTotal: 0,
  nodesReady: 0,
  alertFiring: 0,
  alertPending: 0,
})

const resource = reactive<MonitorResource>({
  cpuUsedPct: 0,
  memUsedPct: 0,
  fsUsedPct: 0,
})

const trends = reactive({
  cpu: [] as SeriesPoint[],
  mem: [] as SeriesPoint[],
  fs: [] as SeriesPoint[],
})

const top = reactive({
  cpu: [] as TopItem[],
  mem: [] as TopItem[],
  net: [] as TopItem[],
})

const topRows = computed(() => {
  const src = topKind.value === 'cpu' ? top.cpu : topKind.value === 'mem' ? top.mem : top.net
  return (src || []).map((x: TopItem, idx: number) => {
    const m = x.metric || {}
    const ns = (m.namespace as string) || '-'
    const pod = (m.pod as string) || (m.pod_name as string) || '-'
    const instance = (m.instance as string) || (m.node as string) || ''
    const rank = x.rank ?? (idx + 1)
    return {
      rank,
      rankKey: `${rank}-${ns}-${pod}-${instance}-${topKind.value}`,
      ns,
      pod,
      instance,
      valueText: x.valueText ?? (typeof x.value === 'number' ? String(x.value) : '-'),
    }
  })
})

function fmtPct(v: number) {
  if (v === null || v === undefined || Number.isNaN(v)) return '-'
  return `${Number(v).toFixed(1)}%`
}

/** =========================
 *  ECharts
 * ========================= */
const cpuRef = ref<HTMLDivElement | null>(null)
const memRef = ref<HTMLDivElement | null>(null)
const fsRef = ref<HTMLDivElement | null>(null)

let cpuChart: ECharts | null = null
let memChart: ECharts | null = null
let fsChart: ECharts | null = null

function palette() {
  const dark = isDark.value
  return {
    axis: dark ? 'rgba(255,255,255,0.55)' : 'rgba(15,23,42,0.55)',
    line: dark ? 'rgba(110,168,255,0.95)' : 'rgba(37,99,235,0.95)',
    grid: dark ? 'rgba(255,255,255,0.08)' : 'rgba(15,23,42,0.10)',
    axisLine: dark ? 'rgba(255,255,255,0.14)' : 'rgba(15,23,42,0.14)',
    tooltipBg: dark ? 'rgba(10,14,26,0.92)' : 'rgba(255,255,255,0.96)',
    tooltipBorder: dark ? 'rgba(255,255,255,0.12)' : 'rgba(15,23,42,0.12)',
    tooltipText: dark ? 'rgba(255,255,255,0.90)' : 'rgba(15,23,42,0.90)',
  }
}

function buildSparkOption(series: SeriesPoint[], name: string) {
  const p = palette()
  const xs = series.map(([ts]) => new Date(ts * 1000).toLocaleTimeString())
  const ys = series.map(([, v]) => v)

  return {
    tooltip: {
      trigger: 'axis',
      backgroundColor: p.tooltipBg,
      borderColor: p.tooltipBorder,
      textStyle: { color: p.tooltipText, fontSize: 12 },
      axisPointer: { type: 'line' },
    },
    grid: { left: 14, right: 10, top: 10, bottom: 18, containLabel: true },
    xAxis: {
      type: 'category',
      data: xs,
      axisLabel: { color: p.axis, fontSize: 10, interval: Math.ceil(xs.length / 6) },
      axisLine: { lineStyle: { color: p.axisLine } },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: p.axis, fontSize: 10 },
      axisLine: { show: false },
      splitLine: { lineStyle: { color: p.grid } },
    },
    series: [
      {
        name,
        type: 'line',
        data: ys,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2, color: p.line },
        areaStyle: { opacity: 0.08 },
      },
    ],
  }
}

async function initCharts() {
  await nextTick()
  if (cpuRef.value && !cpuChart) cpuChart = echarts.init(cpuRef.value)
  if (memRef.value && !memChart) memChart = echarts.init(memRef.value)
  if (fsRef.value && !fsChart) fsChart = echarts.init(fsRef.value)
  window.addEventListener('resize', resizeCharts)
}

function resizeCharts() {
  cpuChart?.resize()
  memChart?.resize()
  fsChart?.resize()
}

function renderCharts() {
  if (!cpuChart || !memChart || !fsChart) return
  cpuChart.setOption(buildSparkOption(trends.cpu, 'cpu'), true)
  memChart.setOption(buildSparkOption(trends.mem, 'mem'), true)
  fsChart.setOption(buildSparkOption(trends.fs, 'fs'), true)
}

/** =========================
 *  Refresh: 修复 “resp.status 是 number” 的根因
 *  - axios Response.status 是 number
 *  - 正确判断：resp.data.status
 * ========================= */
function unwrap<T>(resp: any): ApiResp<T> {
  // 兼容两种：fetchMonitorOverview 可能返回 {status,data} 或 AxiosResponse<{status,data}>
  if (resp && typeof resp === 'object') {
    if ('status' in resp && (resp.status === 'success' || resp.status === 'error') && 'data' in resp) {
      return resp as ApiResp<T>
    }
    if ('data' in resp && resp.data && typeof resp.data === 'object' && 'status' in resp.data && 'data' in resp.data) {
      return resp.data as ApiResp<T>
    }
  }
  // 兜底：避免 TS 炸
  return { status: 'error', data: {} as T, message: 'Invalid response shape' }
}


function formatCNTime(input?: string | number | Date | null): string {
  if (input == null) return '—'
  const dt = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(dt.getTime())) return '—'

  // 强制中国时区（东八区）
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(dt)
}

function formatLocalTime(dt = new Date()): string {
  // 本机时区（用户电脑）
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(dt)
}


async function refresh() {
  loading.value = true
  err.value = ''
  try {
    const raw = await fetchMonitorOverview({ range: range.value })
    const resp = unwrap<MonitorOverviewData>(raw)

    if (resp.status !== 'success') {
      err.value = resp.message || '后端返回非 success'
      return
    }

    const d = resp.data

    nowText.value = d.time?.now ? formatCNTime(d.time.now) : formatLocalTime()

    health.promOk = !!d.health?.promOk
    health.nodesTotal = d.health?.nodesTotal ?? 0
    health.nodesReady = d.health?.nodesReady ?? 0
    health.alertFiring = d.health?.alertFiring ?? 0
    health.alertPending = d.health?.alertPending ?? 0

    resource.cpuUsedPct = d.resource?.cpuUsedPct ?? 0
    resource.memUsedPct = d.resource?.memUsedPct ?? 0
    resource.fsUsedPct = d.resource?.fsUsedPct ?? 0

    trends.cpu = d.trends?.cpuUsedPct ?? []
    trends.mem = d.trends?.memUsedPct ?? []
    trends.fs = d.trends?.fsUsedPct ?? []

    top.cpu = d.top?.podCpu ?? []
    top.mem = d.top?.podMem ?? []
    top.net = d.top?.podNet ?? []

    await initCharts()
    renderCharts()
  } catch (e: any) {
    err.value = e?.response?.data?.detail || e?.message || '网络异常'
  } finally {
    loading.value = false
  }
}

/** =========================
 *  Auto refresh: 修复重复 setInterval（只留一个）
 * ========================= */
let timer: any = null

function startTimer() {
  stopTimer()
  timer = setInterval(() => {
    if (autoRefresh.value && !loading.value) refresh()
  }, 10_000)
}

function stopTimer() {
  if (timer) clearInterval(timer)
  timer = null
}

watch(autoRefresh, () => startTimer())

onMounted(async () => {
  await refresh()
  startTimer()
})

onUnmounted(() => {
  stopTimer()
  window.removeEventListener('resize', resizeCharts)
  cpuChart?.dispose()
  memChart?.dispose()
  fsChart?.dispose()
  cpuChart = memChart = fsChart = null
})
</script>

<style scoped>
/* ========= Theme Tokens (global via html[data-theme]) ========= */
:global(html[data-theme="dark"]) {
  --bg: #070b14;
  --bg2: #0b1224;
  --card: rgba(255, 255, 255, 0.04);
  --card2: rgba(255, 255, 255, 0.06);
  --border: rgba(255, 255, 255, 0.10);
  --text: rgba(255, 255, 255, 0.90);
  --muted: rgba(255, 255, 255, 0.55);
  --muted2: rgba(255, 255, 255, 0.40);
  --shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
  --good: rgba(46, 229, 157, 0.9);
  --warn: rgba(255, 204, 102, 0.9);
  --bad: rgba(255, 93, 93, 0.9);
}

:global(html[data-theme="light"]) {
  --bg: #f6f7fb;
  --bg2: #ffffff;
  --card: #ffffff;
  --card2: #fafbff;
  --border: rgba(15, 23, 42, 0.10);
  --text: rgba(15, 23, 42, 0.92);
  --muted: rgba(15, 23, 42, 0.62);
  --muted2: rgba(15, 23, 42, 0.46);
  --shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  --good: rgba(16, 185, 129, 0.95);
  --warn: rgba(245, 158, 11, 0.95);
  --bad: rgba(239, 68, 68, 0.95);
}

/* ========= Layout ========= */
.wall {
  height: 100vh;
  width: 100vw;
  background: radial-gradient(1200px 600px at 20% 10%, rgba(59, 130, 246, 0.14), transparent 60%),
    radial-gradient(900px 500px at 90% 30%, rgba(34, 197, 94, 0.10), transparent 60%),
    linear-gradient(180deg, var(--bg), var(--bg2));
  color: var(--text);
  padding: 16px 18px;
  box-sizing: border-box;
  overflow: hidden;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 12px;
}

.title .h1 {
  font-size: 20px;
  font-weight: 900;
  letter-spacing: 0.5px;
}
.title .sub {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
}

.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--card);
  box-shadow: var(--shadow);
  backdrop-filter: blur(8px);
}
.pill .label {
  font-size: 12px;
  color: var(--muted);
}
.w140 {
  width: 140px;
}

.btn {
  border-radius: 999px !important;
  border: 1px solid var(--border) !important;
  background: var(--card) !important;
  color: var(--text) !important;
}

.grid {
  display: grid;
  grid-template-columns: 1.45fr 0.9fr;
  gap: 14px;
  height: calc(100vh - 72px);
}

.left {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.right {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* ========= Cards ========= */
.kpis {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.kpi {
  border-radius: 16px;
  border: 1px solid var(--border);
  background: linear-gradient(180deg, var(--card), var(--card2));
  box-shadow: var(--shadow);
  padding: 12px 12px;
  backdrop-filter: blur(8px);
}

.kpi.ok {
  border-color: color-mix(in srgb, var(--good) 45%, transparent);
}
.kpi.bad {
  border-color: color-mix(in srgb, var(--bad) 45%, transparent);
}
.kpi.warn {
  border-color: color-mix(in srgb, var(--warn) 45%, transparent);
}

.k {
  font-size: 12px;
  color: var(--muted);
}
.v {
  margin-top: 6px;
  font-size: 26px;
  font-weight: 950;
  letter-spacing: 0.3px;
}
.t {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted2);
}
.sep {
  margin: 0 8px;
  color: color-mix(in srgb, var(--muted) 55%, transparent);
}

/* ========= Trend Panels ========= */
.charts {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  flex: 1;
  min-height: 280px;
}

.panel {
  border-radius: 16px;
  border: 1px solid var(--border);
  background: linear-gradient(180deg, var(--card), var(--card2));
  box-shadow: var(--shadow);
  padding: 10px 10px;
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(8px);
}

.ph {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 6px;
}
.pt {
  font-weight: 900;
  font-size: 12px;
}
.pv {
  font-weight: 900;
  font-size: 12px;
  color: var(--muted);
}
.chart {
  width: 100%;
  flex: 1;
}

/* ========= TopN ========= */
.topbox {
  border-radius: 16px;
  border: 1px solid var(--border);
  background: linear-gradient(180deg, var(--card), var(--card2));
  box-shadow: var(--shadow);
  padding: 12px 12px;
  flex: 1;
  min-height: 420px;
  display: flex;
  flex-direction: column;
  backdrop-filter: blur(8px);
}

.tb-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.tb-title {
  font-weight: 950;
}

.tb-body {
  margin-top: 10px;
  overflow: auto;
  padding-right: 4px;
}

.thead,
.trow {
  display: grid;
  grid-template-columns: 44px 1fr 130px;
  gap: 10px;
  align-items: center;
}

.thead {
  font-size: 12px;
  color: var(--muted);
  padding: 6px 2px;
  border-bottom: 1px solid color-mix(in srgb, var(--border) 70%, transparent);
  position: sticky;
  top: 0;
  background: color-mix(in srgb, var(--bg2) 92%, transparent);
  backdrop-filter: blur(6px);
}

.trow {
  padding: 10px 2px;
  border-bottom: 1px dashed color-mix(in srgb, var(--border) 70%, transparent);
  transition: background 0.12s ease;
}
.trow:hover {
  background: color-mix(in srgb, var(--card2) 70%, transparent);
}

.name .main {
  font-weight: 900;
}
.name .sub {
  margin-top: 4px;
  font-size: 12px;
}

.r {
  text-align: right;
}

.empty {
  padding: 12px 2px;
}

.footnote {
  border-radius: 16px;
  border: 1px solid var(--border);
  background: linear-gradient(180deg, var(--card), var(--card2));
  box-shadow: var(--shadow);
  padding: 10px 12px;
  backdrop-filter: blur(8px);
}

.err {
  position: absolute;
  left: 18px;
  right: 18px;
  bottom: 14px;
}

.muted {
  color: var(--muted);
  font-size: 12px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}
.mr6 {
  margin-right: 6px;
}

/* ========= ElementPlus dark/light small tweaks ========= */
:deep(.el-select__wrapper) {
  border-radius: 10px;
}
:deep(.el-radio-button__inner) {
  border-radius: 10px;
}

/* ========= Responsive ========= */
@media (max-width: 1280px) {
  .grid {
    grid-template-columns: 1fr;
    height: auto;
    overflow: auto;
  }
  .charts {
    grid-template-columns: 1fr;
  }
  .kpis {
    grid-template-columns: 1fr;
  }
}
</style>
