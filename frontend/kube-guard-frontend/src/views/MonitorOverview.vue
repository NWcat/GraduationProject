<!-- src/views/MonitorOverview.vue -->
<template>
  <div class="monitor-page">
    <!-- 顶部：标题 + 操作 -->
    <div class="page-head">
      <div>
        <div class="page-title">监控总览</div>
        <div class="page-subtitle">
          聚合 Prometheus 指标，快速了解集群健康、资源使用与热点 TopN（可跳转到节点/负载/指标查询页）
        </div>
      </div>

      <div class="head-actions">
        <el-select v-model="timeRange" class="w160" @change="handleRangeChange">
          <el-option v-for="r in rangeOptions" :key="r.value" :label="r.label" :value="r.value" />
        </el-select>

        <el-button :loading="loading" @click="refresh">
          <el-icon class="mr6"><Refresh /></el-icon>
          刷新
        </el-button>

        <el-button type="primary" plain @click="goMetrics({ q: 'up', range: timeRange })">
          <el-icon class="mr6"><Search /></el-icon>
          打开指标查询
        </el-button>
      </div>
    </div>

    <!-- Row 1：健康概览 -->
    <div class="grid grid-3">
      <el-card shadow="never" class="card">
        <template #header>
          <div class="card-head">
            <div class="card-title">集群健康</div>
            <el-button link type="primary" @click="goMetrics({ q: 'up', range: timeRange })">
              查看详情
            </el-button>
          </div>
        </template>

        <div class="kv">
          <div class="k">Prometheus 状态</div>
          <div class="v">
            <StatusPill :status="health.promStatus" />
          </div>

          <div class="k">节点在线</div>
          <div class="v">
            <span class="mono">{{ health.nodesReady }}</span>
            <span class="muted"> / {{ health.nodesTotal }}</span>
            <el-button link type="primary" class="ml10" @click="goNodes({ status: 'ready' })">节点</el-button>
          </div>

          <div class="k">工作负载正常</div>
          <div class="v">
            <span class="mono">{{ health.workloadsOkRate }}%</span>
            <span class="muted">（Ready/Desired）</span>
            <el-button link type="primary" class="ml10" @click="goWorkloads({ kind: 'deployment' })">负载</el-button>
          </div>

          <div class="k">告警</div>
          <div class="v">
            <span class="mono">{{ health.alertFiring }}</span>
            <span class="muted"> firing · </span>
            <span class="mono">{{ health.alertPending }}</span>
            <span class="muted"> pending</span>
            <el-button link type="primary" class="ml10" @click="scrollToAlerts">定位</el-button>
          </div>
        </div>

        <el-divider />
        <div class="hint">
          后端建议：健康卡可聚合 <span class="mono">up</span>、节点 Ready、Deployment/STS Ready、Alertmanager 告警数量。
        </div>
      </el-card>

      <el-card shadow="never" class="card">
        <template #header>
          <div class="card-head">
            <div class="card-title">资源概览</div>
            <el-button link type="primary" @click="goMetrics({ q: promPresets.clusterCpuUsage, range: timeRange })">
              PromQL
            </el-button>
          </div>
        </template>

        <div class="meters">
          <MeterRow
            title="CPU 使用率"
            :value="resource.cpuUsedPct"
            suffix="%"
            :note="resource.cpuNote"
            :tone="meterTone(resource.cpuUsedPct)"
            @click="goMetrics({ q: promPresets.clusterCpuUsage, range: timeRange })"
          />
          <MeterRow
            title="内存使用率"
            :value="resource.memUsedPct"
            suffix="%"
            :note="resource.memNote"
            :tone="meterTone(resource.memUsedPct)"
            @click="goMetrics({ q: promPresets.clusterMemUsage, range: timeRange })"
          />
          <MeterRow
            title="存储使用率"
            :value="resource.fsUsedPct"
            suffix="%"
            :note="resource.fsNote"
            :tone="meterTone(resource.fsUsedPct)"
            @click="goMetrics({ q: promPresets.clusterFsUsage, range: timeRange })"
          />
          <MeterRow
            title="网络带宽（峰值）"
            :value="resource.netPeakPct"
            suffix="%"
            :note="resource.netNote"
            :tone="meterTone(resource.netPeakPct)"
            @click="goMetrics({ q: promPresets.clusterNetPeak, range: timeRange })"
          />
        </div>

        <el-divider />
        <div class="hint">
          点击每一行会跳转到「监控指标查询」并带上预置 PromQL。
        </div>
      </el-card>

      <el-card shadow="never" class="card">
        <template #header>
          <div class="card-head">
            <div class="card-title">快速入口</div>
          </div>
        </template>

        <div class="quick">
          <div class="quick-item" @click="goNodes({})">
            <div class="qi-title">节点列表</div>
            <div class="qi-desc">查看节点状态、资源与异常节点</div>
          </div>
          <div class="quick-item" @click="goWorkloads({ kind: 'deployment' })">
            <div class="qi-title">应用负载</div>
            <div class="qi-desc">统一管理 Deployment/StatefulSet/Pod</div>
          </div>
          <div class="quick-item" @click="goMetrics({ q: 'up', range: timeRange })">
            <div class="qi-title">指标查询</div>
            <div class="qi-desc">PromQL 查询与自定义曲线</div>
          </div>
        </div>

        <el-divider />
        <div class="hint">
          监控总览建议做成“指挥台”：只展示关键结论 + 一键跳转深入。
        </div>
      </el-card>
    </div>

    <!-- Row 2：TopN + 告警 -->
    <div class="grid grid-2">
      <el-card shadow="never" class="card">
        <template #header>
          <div class="card-head">
            <div class="card-title">TopN（热点｜业务 Pod）</div>
            <div class="head-right">
              <el-radio-group v-model="topKind" size="small">
                <el-radio-button label="cpu">CPU</el-radio-button>
                <el-radio-button label="mem">内存</el-radio-button>
                <el-radio-button label="net">网络</el-radio-button>
              </el-radio-group>

              <el-button link type="primary" class="ml10" @click="goMetrics({ q: topPromql, range: timeRange })">
                以 PromQL 打开
              </el-button>
            </div>
          </div>
        </template>

        <el-table :data="topRows" stripe height="360" v-loading="loading">
          <el-table-column prop="rank" label="#" width="60" />
          <el-table-column prop="name" label="Pod" min-width="240" show-overflow-tooltip />
          <el-table-column prop="namespace" label="命名空间" width="160">
            <template #default="{ row }">
              <span class="mono">{{ row.namespace || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="value" label="数值" width="140">
            <template #default="{ row }">
              <span class="mono">{{ row.value }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <div class="ops">
                <el-button size="small" @click="jumpByTopRow(row)">定位</el-button>
                <el-button size="small" @click="goMetrics({ q: row.promql, range: timeRange })">指标</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <el-divider />
        <div class="hint">
          这里使用 <span class="mono">container_*</span> 指标做 Pod TopN，因此会显示业务命名空间（namespace）。
        </div>
      </el-card>

      <el-card shadow="never" class="card" ref="alertsCardRef">
        <template #header>
          <div class="card-head">
            <div class="card-title">告警（概览）</div>
            <div class="head-right">
              <el-button link type="primary" @click="goMetrics({ q: promPresets.alertsCount, range: timeRange })">
                指标
              </el-button>
              <el-button link type="primary" @click="refresh">刷新</el-button>
            </div>
          </div>
        </template>

        <div class="alerts">
          <el-alert
            v-if="health.alertFiring > 0"
            title="存在 firing 告警"
            type="error"
            show-icon
            :closable="false"
            class="alert-item"
          >
            <template #default>
              <div class="alert-body">
                <div class="muted">
                  当前 firing 数量：<span class="mono">{{ health.alertFiring }}</span>（可点击“指标”查看详情）
                </div>
                <div class="alert-actions">
                  <el-button size="small" @click="goMetrics({ q: promPresets.alertsCount, range: timeRange })"
                    >查看指标</el-button
                  >
                </div>
              </div>
            </template>
          </el-alert>

          <el-alert
            v-else
            title="暂无 firing 告警"
            type="success"
            show-icon
            :closable="false"
            class="alert-item"
          >
            <template #default>
              <div class="alert-body">
                <div class="muted">pending：<span class="mono">{{ health.alertPending }}</span></div>
              </div>
            </template>
          </el-alert>

          <div v-if="health.alertFiring === 0 && health.alertPending === 0" class="empty muted">
            暂无告警
          </div>
        </div>

        <el-divider />
        <div class="hint">
          后端建议：对接 Alertmanager / Prometheus <span class="mono">ALERTS</span> 指标，
          或做一个 <span class="mono">/api/alerts</span> 聚合接口。
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch, defineComponent, h } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import { fetchPromOverview } from '@/api/prom'



type PillStatus = 'ok' | 'warning' | 'bad' | 'unknown'
type TopKind = 'cpu' | 'mem' | 'net'

type TopRow = {
  rank: number
  name: string
  namespace?: string
  value: string
  scope: 'node' | 'pod'
  promql: string
  jump: { to: 'nodes' | 'workloads'; query: Record<string, any> }
}

type PromVectorItem = {
  metric: Record<string, string>
  value: [number, string]
}

type OverviewResp = {
  status: 'success' | 'error'
  data?: {
    health: {
      promOk: boolean
      nodesTotal: number
      nodesReady: number
      alertFiring: number
      alertPending: number
    }
    resource: {
      cpuUsedPct: number
      memUsedPct: number
      fsUsedPct: number
    }
    // ✅ 新版后端：podTop
    podTop: {
      cpu: any
      mem: any
      net: any
    }
    range: { minutes: number }
  }
  error?: string
}

const router = useRouter()
const loading = ref(false)

/** 时间范围（overview 的 range 参数） */
const rangeOptions = [
  { label: '最近 5 分钟', value: '5m' },
  { label: '最近 15 分钟', value: '15m' },
  { label: '最近 1 小时', value: '1h' },
  { label: '最近 6 小时', value: '6h' },
  { label: '最近 24 小时', value: '24h' },
]
const timeRange = ref<string>('15m')

/** PromQL 预置 */
const promPresets = {
  clusterCpuUsage: '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m])))',
  clusterMemUsage: '100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))',
  clusterFsUsage:
    '100 * (1 - (node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes{fstype!~"tmpfs|overlay"}))',
  clusterNetPeak:
    'topk(1, rate(node_network_receive_bytes_total[5m]) + rate(node_network_transmit_bytes_total[5m]))',
  alertsCount: 'sum(ALERTS{alertstate="firing"})',
}

/** 健康：真实数据 */
const health = reactive({
  promStatus: 'unknown' as PillStatus,
  nodesReady: 0,
  nodesTotal: 0,
  workloadsOkRate: 0,
  alertFiring: 0,
  alertPending: 0,
})

/** 资源概览：真实数据 */
const resource = reactive({
  cpuUsedPct: 0,
  memUsedPct: 0,
  fsUsedPct: 0,
  netPeakPct: 0,
  cpuNote: '',
  memNote: '',
  fsNote: '',
  netNote: '',
})

/** TopN：Pod 维度（业务命名空间） */
const topKind = ref<TopKind>('cpu')

const topPromql = computed(() => {
  if (topKind.value === 'cpu') {
    return `topk(10, sum by (namespace,pod) (rate(container_cpu_usage_seconds_total{container!="",pod!=""}[5m])))`
  }
  if (topKind.value === 'mem') {
    return `topk(10, sum by (namespace,pod) (container_memory_working_set_bytes{container!="",pod!=""})) / 1024 / 1024`
  }
  return `topk(10, sum by (namespace,pod) (rate(container_network_receive_bytes_total{pod!=""}[5m]) + rate(container_network_transmit_bytes_total{pod!=""}[5m]))) / 1024`
})

const topRows = ref<TopRow[]>([])

const podTop = reactive<{ cpu: PromVectorItem[]; mem: PromVectorItem[]; net: PromVectorItem[] }>({
  cpu: [],
  mem: [],
  net: [],
})

/** refs */
const alertsCardRef = ref<HTMLElement | null>(null)

function meterTone(v: number): 'good' | 'warn' | 'bad' {
  if (v < 70) return 'good'
  if (v < 85) return 'warn'
  return 'bad'
}

function safePct(n: any): number {
  const x = Number(n)
  if (!Number.isFinite(x)) return 0
  return Math.max(0, Math.min(100, x))
}

function noteForPct(v: number, kind: 'cpu' | 'mem' | 'fs' | 'net') {
  if (kind === 'net') {
    if (v < 50) return '带宽有余量'
    if (v < 80) return '带宽占用中等'
    return '带宽偏高，注意瓶颈'
  }
  if (v < 60) return '整体使用正常'
  if (v < 80) return '使用偏高，关注热点'
  return '使用较高，建议排查/扩容'
}

/** 跳转工具 */
function goNodes(query: Record<string, any>) {
  router.push({ path: '/nodes', query })
}
function goWorkloads(query: Record<string, any>) {
  router.push({ path: '/workloads', query })
}
function goMetrics(query: Record<string, any>) {
  router.push({ path: '/metrics', query })
}

function scrollToAlerts() {
  nextTick(() => {
    const el = alertsCardRef.value
    if (!el) return
    ;(el as any).$el?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  })
}

function jumpByTopRow(row: TopRow) {
  if (row.jump.to === 'nodes') return goNodes(row.jump.query)
  return goWorkloads(row.jump.query)
}

/** 解析 Prometheus JSON => vector items */
function normalizeTop(raw: any): PromVectorItem[] {
  const result = (raw?.data?.result || []) as PromVectorItem[]
  return Array.isArray(result) ? result : []
}

function fmtPodValue(kind: TopKind, v: number) {
  if (kind === 'cpu') return `${v.toFixed(3)} core`
  if (kind === 'mem') return `${v.toFixed(0)} MiB`
  return `${v.toFixed(0)} KB/s`
}

function applyTopFromOverview() {
  const list = podTop[topKind.value] || []
  topRows.value = list.map((it, idx) => {
    const metric = it.metric || {}
    const ns = metric.namespace || '-'
    const pod = metric.pod || metric.pod_name || 'unknown'
    const rawVal = Number(it.value?.[1] ?? 0)

    return {
      rank: idx + 1,
      name: pod,
      namespace: ns,
      value: fmtPodValue(topKind.value, rawVal),
      scope: 'pod',
      promql: topPromql.value,
      jump: { to: 'workloads', query: { kind: 'pod', namespace: ns, keyword: pod } },
    } as TopRow
  })
}

/** range 改变 */
function handleRangeChange() {
  refresh()
}

async function refresh() {
  loading.value = true
  try {
    const resp = await fetchPromOverview(timeRange.value)
    const raw: OverviewResp = resp.data

    if (raw.status !== 'success' || !raw.data) {
      ElMessage.error(raw.error || '获取总览失败')
      return
    }

    const d = raw.data

    // health
    health.nodesTotal = d.health.nodesTotal ?? 0
    health.nodesReady = d.health.nodesReady ?? 0
    health.alertFiring = d.health.alertFiring ?? 0
    health.alertPending = d.health.alertPending ?? 0
    health.promStatus = d.health.promOk ? 'ok' : 'bad'

    // workloadsOkRate：先用 Ready 节点比例占位
    health.workloadsOkRate = health.nodesTotal > 0 ? Math.round((health.nodesReady / health.nodesTotal) * 100) : 0

    // resource
    resource.cpuUsedPct = safePct(d.resource.cpuUsedPct)
    resource.memUsedPct = safePct(d.resource.memUsedPct)
    resource.fsUsedPct = safePct(d.resource.fsUsedPct)

    resource.cpuNote = noteForPct(resource.cpuUsedPct, 'cpu')
    resource.memNote = noteForPct(resource.memUsedPct, 'mem')
    resource.fsNote = noteForPct(resource.fsUsedPct, 'fs')

    // ✅ podTop（业务命名空间 TopN）
    podTop.cpu = normalizeTop(d.podTop.cpu)
    podTop.mem = normalizeTop(d.podTop.mem)
    podTop.net = normalizeTop(d.podTop.net)

    // netPeakPct：用 net Top1 做一个“相对百分比”用于 UI
    const netFirst = podTop.net?.[0]
    const netValKb = Number(netFirst?.value?.[1] ?? 0) // KB/s
    const refKb = 200 * 1024 // 200MB/s -> KB/s
    resource.netPeakPct = safePct((netValKb / refKb) * 100)
    resource.netNote = noteForPct(resource.netPeakPct, 'net')

    applyTopFromOverview()
    ElMessage.success('已刷新')
  } catch (e: any) {
    ElMessage.error(e?.message || '刷新失败（请检查后端 /api/prom/overview）')
  } finally {
    loading.value = false
  }
}

const StatusPill = defineComponent({
  name: 'StatusPill',
  props: { status: { type: String, required: true } }, // ok | warning | bad | unknown
  setup(props) {
    const text = computed(() => {
      if (props.status === 'ok') return '正常'
      if (props.status === 'warning') return '注意'
      if (props.status === 'bad') return '异常'
      return '未知'
    })
    const cls = computed(() => `pill pill-${props.status}`)

    return () =>
      h('span', { class: cls.value }, [
        h('span', { class: 'dot' }),
        h('span', { class: 'txt' }, text.value),
      ])
  },
})

const MeterRow = defineComponent({
  name: 'MeterRow',
  emits: ['click'],
  props: {
    title: { type: String, required: true },
    value: { type: Number, required: true },
    suffix: { type: String, default: '%' },
    note: { type: String, default: '' },
    tone: { type: String, default: 'good' }, // good | warn | bad
    digits: { type: Number, default: 1 }, // ✅ 保留几位小数
  },
  setup(props, { emit }) {
    const barCls = computed(() => `bar bar-${props.tone}`)
    const pct = computed(() => Math.max(0, Math.min(100, Number(props.value) || 0)))

    const showVal = computed(() => {
      const n = Number(props.value)
      if (!Number.isFinite(n)) return '-'
      return n.toFixed(props.digits)
    })

    return () =>
      h(
        'div',
        { class: 'meter', onClick: () => emit('click') },
        [
          h('div', { class: 'm-head' }, [
            h('div', { class: 'm-title' }, props.title),
            h('div', { class: 'm-val mono' }, `${showVal.value}${props.suffix}`),
          ]),
          h('div', { class: 'm-bar' }, [
            h('div', { class: barCls.value, style: { width: `${pct.value}%` } }),
          ]),
          h('div', { class: 'm-note muted' }, props.note),
        ]
      )
  },
})


/** 切换 topKind 立即更新表格 */
watch(topKind, () => applyTopFromOverview())

/** 初始化 */
refresh()
</script>

<!-- <script lang="ts">
/**
 * 子组件：状态胶囊 / 进度条行（不用 JSX）
 */
import { defineComponent } from 'vue'

export const StatusPill = defineComponent({
  name: 'StatusPill',
  props: {
    status: { type: String, required: true }, // ok | warning | bad | unknown
  },
  setup(props) {
    const text = computed(() => {
      if (props.status === 'ok') return '正常'
      if (props.status === 'warning') return '注意'
      if (props.status === 'bad') return '异常'
      return '未知'
    })
    const cls = computed(() => `pill pill-${props.status}`)
    return { text, cls }
  },
  template: `
    <span :class="cls">
      <span class="dot"></span>
      <span class="txt">{{ text }}</span>
    </span>
  `,
})

export const MeterRow = defineComponent({
  name: 'MeterRow',
  emits: ['click'],
  props: {
    title: { type: String, required: true },
    value: { type: Number, required: true },
    suffix: { type: String, default: '%' },
    note: { type: String, default: '' },
    tone: { type: String, default: 'good' }, // good | warn | bad
  },
  setup(props, { emit }) {
    const barCls = computed(() => `bar bar-${props.tone}`)
    const pct = computed(() => Math.max(0, Math.min(100, props.value)))
    return { barCls, pct, emit }
  },
  template: `
    <div class="meter" @click="emit('click')">
      <div class="m-head">
        <div class="m-title">{{ title }}</div>
        <div class="m-val mono">{{ value }}{{ suffix }}</div>
      </div>
      <div class="m-bar">
        <div :class="barCls" :style="{ width: pct + '%' }"></div>
      </div>
      <div class="m-note muted">{{ note }}</div>
    </div>
  `,
})
</script> -->

<style scoped>
.monitor-page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 顶部 */
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.page-title {
  font-size: 16px;
  font-weight: 800;
  color: #111827;
}
.page-subtitle {
  font-size: 12px;
  color: #6b7280;
  margin-top: 2px;
  line-height: 1.6;
}
.head-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.w160 {
  width: 160px;
}

/* grid */
.grid {
  display: grid;
  gap: 14px;
}
.grid-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.grid-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

/* card */
.card {
  border-radius: 12px;
  border: 1px solid #e5e7eb;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.card-title {
  font-weight: 800;
  color: #111827;
}
.head-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* kv */
.kv {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 10px 12px;
  align-items: center;
}
.k {
  color: #6b7280;
  font-size: 12px;
}
.v {
  color: #111827;
  font-size: 13px;
}

.hint {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.6;
}

/* quick */
.quick {
  display: grid;
  gap: 10px;
}
.quick-item {
  border: 1px solid #eef2f7;
  border-radius: 12px;
  padding: 12px;
  background: #fbfdff;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease;
}
.quick-item:hover {
  background: #f5f9ff;
  border-color: #dbeafe;
  transform: translateY(-1px);
}
.qi-title {
  font-weight: 800;
  color: #111827;
}
.qi-desc {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
}

/* table ops */
.ops {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* alerts */
.alerts {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.alert-item :deep(.el-alert__content) {
  width: 100%;
}
.alert-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.alert-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.empty {
  padding: 10px 0;
}

/* meter */
.meters {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.meter {
  border: 1px solid #eef2f7;
  border-radius: 12px;
  padding: 12px;
  background: #fbfdff;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}
.meter:hover {
  background: #f5f9ff;
  border-color: #dbeafe;
}
.m-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}
.m-title {
  font-weight: 700;
  color: #111827;
}
.m-val {
  font-size: 13px;
  color: #111827;
}
.m-bar {
  height: 8px;
  border-radius: 999px;
  background: #eef2f7;
  overflow: hidden;
  margin-top: 8px;
}
.bar {
  height: 100%;
  border-radius: 999px;
}
.bar-good {
  background: rgba(34, 197, 94, 0.75);
}
.bar-warn {
  background: rgba(245, 158, 11, 0.75);
}
.bar-bad {
  background: rgba(239, 68, 68, 0.75);
}
.m-note {
  margin-top: 6px;
}

/* status pill */
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid transparent;
}
.pill .dot {
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.9;
}
.pill-ok {
  color: #059669;
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.25);
}
.pill-warning {
  color: #d97706;
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.25);
}
.pill-bad {
  color: #dc2626;
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.25);
}
.pill-unknown {
  color: #64748b;
  background: rgba(100, 116, 139, 0.1);
  border-color: rgba(100, 116, 139, 0.25);
}

/* helpers */
.muted {
  color: #6b7280;
  font-size: 12px;
}
.mr6 {
  margin-right: 6px;
}
.ml10 {
  margin-left: 10px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono',
    'Courier New', monospace;
}

@media (max-width: 1280px) {
  .grid-3 {
    grid-template-columns: 1fr;
  }
  .grid-2 {
    grid-template-columns: 1fr;
  }
  .w160 {
    width: 100%;
  }
}
</style>
