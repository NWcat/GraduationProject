<!-- src/views/Overview.vue -->
<template>
  <div class="overview-root">
    <div class="overview-layout">
      <!-- 左侧主内容 -->
      <div class="overview-main">
        <!-- 集群概览 -->
        <el-card shadow="never" class="section-card overview-card">
          <div class="section-header">
            <div class="section-title">集群概览</div>
            <div class="section-subtitle">当前集群运行状态一览</div>
          </div>

          <el-skeleton v-if="loading" :rows="6" animated />
          <el-alert v-else-if="errorMsg" :title="errorMsg" type="error" show-icon :closable="false" />

          <div v-else class="overview-grid">
            <div v-for="item in overviewStatsView" :key="item.key" class="stat-card">
              <div class="stat-icon-wrapper">
                <el-icon class="stat-icon">
                  <component :is="item.icon" />
                </el-icon>
              </div>
              <div class="stat-content">
                <div class="stat-value">
                  {{ item.value }}
                  <span v-if="item.unit" class="stat-unit">{{ item.unit }}</span>
                </div>
                <div class="stat-label">{{ item.label }}</div>
                <div class="stat-desc">{{ item.desc }}</div>
              </div>
            </div>
          </div>
        </el-card>

        <!-- 容量与负载 -->
        <el-card shadow="never" class="section-card capacity-card">
          <div class="section-header">
            <div class="section-title">容量与负载</div>
            <div class="section-subtitle">
              聚合展示集群资源使用率，便于快速判断是否需要扩容或优化
            </div>
          </div>

          <el-skeleton v-if="loading" :rows="5" animated />
          <el-alert v-else-if="errorMsg" :title="errorMsg" type="error" show-icon :closable="false" />

          <div v-else class="capacity-grid">
            <div v-for="item in capacityStats" :key="item.key" class="capacity-item">
              <div class="capacity-header">
                <div class="capacity-label">{{ item.label }}</div>
                <div class="capacity-value">
                  {{ item.value }}<span class="capacity-unit">{{ item.unit }}</span>
                </div>
              </div>
              <div class="capacity-bar">
                <div
                  class="capacity-bar-inner"
                  :style="{ width: item.value + '%'}"
                  :class="{
                    'capacity-ok': item.value <= 70,
                    'capacity-warn': item.value > 70 && item.value <= 90,
                    'capacity-danger': item.value > 90
                  }"
                />
              </div>
              <div class="capacity-desc">{{ item.desc }}</div>
            </div>
          </div>
        </el-card>

        <!-- 运维态势 & 工具 -->
        <div class="bottom-grid">
          <!-- 运维态势 -->
          <el-card shadow="never" class="section-card ops-card">
            <div class="section-header">
              <div class="section-title">运维态势</div>
              <div class="section-subtitle">
                最近 24 小时内的告警、变更和发布情况摘要
              </div>
            </div>

            <el-skeleton v-if="loading" :rows="5" animated />
            <el-alert v-else-if="errorMsg" :title="errorMsg" type="error" show-icon :closable="false" />

            <ul v-else class="ops-list">
              <li class="ops-item" v-for="item in opsSummary" :key="item.title">
                <span class="ops-dot" :class="'level-' + item.level"></span>
                <div class="ops-item-main">
                  <div class="ops-item-title">{{ item.title }}</div>
                  <div class="ops-item-desc">{{ item.desc }}</div>
                </div>
                <span class="ops-item-extra">{{ item.extra }}</span>
              </li>
            </ul>
          </el-card>

          <!-- 工具入口 -->
          <el-card shadow="never" class="section-card tools-card">
            <div class="section-header">
              <div class="section-title">工具</div>
              <div class="section-subtitle">运维高频操作入口</div>
            </div>

            <div class="tools-grid">
              <el-card
                v-for="tool in toolEntries"
                :key="tool.key"
                shadow="hover"
                class="tool-card"
                body-class="tool-card-body"
                @click="goTool(tool.key)"
              >
                <div class="tool-main">
                  <el-icon class="tool-icon">
                    <component :is="tool.icon" />
                  </el-icon>
                  <div class="tool-content">
                    <div class="tool-title">{{ tool.title }}</div>
                    <div class="tool-desc">{{ tool.desc }}</div>
                  </div>
                </div>
                <el-link type="primary" :underline="false" class="tool-link">
                  进入
                </el-link>
              </el-card>
            </div>
          </el-card>
        </div>
      </div>

      <!-- 右侧：当前集群卡片 -->
      <aside class="overview-side">
        <el-card shadow="never" class="cluster-card">
          <div class="cluster-header">
            <div class="cluster-name">
              <span class="cluster-badge">主集群</span>
              <span class="cluster-title">{{ cluster.basic.name }}</span>
            </div>
            <div class="cluster-status" :class="'cluster-' + cluster.basic.status">
              <span class="status-dot" :class="'dot-' + cluster.basic.status"></span>
              {{ clusterStatusText }}
            </div>
          </div>

          <div class="cluster-desc">
            该集群由平台自动接入，当前展示为聚合概览。
          </div>

          <div class="cluster-section-title">基本信息</div>
          <el-descriptions :column="1" size="small" class="cluster-desc-table" border>
            <el-descriptions-item label="集群类型">
              {{ cluster.basic.clusterType || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="Kubernetes 版本">
              {{ cluster.basic.k8sVersion || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="平台版本">
              {{ cluster.basic.platformVersion || '-' }}
            </el-descriptions-item>
            <el-descriptions-item label="所在机房">
              {{ cluster.basic.location || '-' }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="cluster-section-title mt-16">资源概况</div>
          <div class="cluster-metrics">
            <div class="metric-item" @click="go('/nodes')">
              <div class="metric-label">节点</div>
              <div class="metric-value">{{ cluster.resources.nodes }}</div>
            </div>
            <div class="metric-item" @click="go('/tenants')">
              <div class="metric-label">命名空间</div>
              <div class="metric-value">{{ cluster.resources.namespaces }}</div>
            </div>
            <div class="metric-item" @click="go('/workloads')">
              <div class="metric-label">Pod</div>
              <div class="metric-value">{{ cluster.resources.pods }}</div>
            </div>
            <div class="metric-item" @click="go('/metrics')">
              <div class="metric-label">告警规则</div>
              <div class="metric-value">{{ cluster.resources.alertRules ?? 0 }}</div>
            </div>
          </div>

          <div class="cluster-section-title mt-16">集群健康摘要</div>
          <ul class="health-list">
            <li v-for="(h, idx) in cluster.health" :key="idx" class="health-item">
              <span class="indicator" :class="h.level"></span>
              {{ h.text }}
            </li>
            <li v-if="cluster.health.length === 0" class="health-item">
              <span class="indicator ok"></span>
              暂无健康项（后端未返回）
            </li>
          </ul>
        </el-card>
      </aside>
    <!-- 巡检弹窗 -->
    <el-dialog v-model="inspectVisible" title="一键巡检" width="780px">
      <div v-if="inspectLoading">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <div style="font-size:12px;color:#6b7280;">
            正在巡检中… {{ inspectProgressText }}
          </div>
          <div style="font-size:12px;color:#6b7280;">
            {{ inspectedCount }}/{{ totalCount }}
          </div>
        </div>
        <el-progress :percentage="inspectProgress" :stroke-width="10" status="success" />
        <el-skeleton :rows="6" animated style="margin-top:12px;" />
      </div>

      <div v-else>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <div style="font-size:12px;color:#6b7280;">
            更新时间：{{ inspectReport?.updatedAt || '-' }}
            <span v-if="inspectReport?.durationMs"> · 耗时 {{ inspectReport.durationMs }}ms</span>
            <span v-if="inspectReport?.runId"> · runId: {{ inspectReport.runId }}</span>
          </div>

          <div v-if="inspectReport?.summary" style="display:flex;gap:8px;align-items:center;">
            <el-tag type="success">OK {{ inspectReport.summary.ok }}</el-tag>
            <el-tag type="warning">WARN {{ inspectReport.summary.warn }}</el-tag>
            <el-tag type="danger">ERROR {{ inspectReport.summary.error }}</el-tag>
            <el-tag>SKIP {{ inspectReport.summary.skip }}</el-tag>
          </div>
        </div>

        <el-empty v-if="!inspectShownItems.length" description="暂无巡检项" />

        <!-- 巡检项列表 + 进度条（逐项展示） -->
        <div v-else>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <div style="font-size:12px;color:#6b7280;">
              巡检进度：{{ inspectedCount }}/{{ totalCount }}（完成后可下载报告）
            </div>
            <el-progress :percentage="inspectProgress" :stroke-width="10" />
          </div>

          <el-timeline>
            <el-timeline-item
              v-for="it in inspectShownItems"
              :key="it.key"
              :type="it.level === 'ok' ? 'success' : it.level === 'warn' ? 'warning' : it.level === 'skip' ? 'info' : 'danger'"
              :timestamp="it.title"
            >
              <div style="color:#374151;margin-bottom:6px;">
                {{ it.detail || '-' }}
              </div>

              <div v-if="it.suggestion" style="color:#6b7280;font-size:12px;margin-bottom:6px;">
                建议：{{ it.suggestion }}
              </div>

              <div style="display:flex;gap:8px;align-items:center;">
                <el-tag
                  size="small"
                  :type="it.level === 'ok' ? 'success' : it.level === 'warn' ? 'warning' : it.level === 'skip' ? 'info' : 'danger'"
                >
                  {{ it.level.toUpperCase() }}
                </el-tag>
                <span style="color:#9ca3af;font-size:12px;">
                  {{ (it.durationMs ?? 0) }}ms
                </span>

                <el-button
                  v-if="it.evidence && Object.keys(it.evidence).length"
                  size="small"
                  text
                  type="primary"
                  @click="openEvidence(it)"
                >
                  查看 evidence
                </el-button>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </div>

      <template #footer>
        <div style="display:flex;justify-content:space-between;align-items:center;width:100%;">
          <div style="display:flex;gap:8px;align-items:center;">
            <el-button :disabled="inspectLoading" @click="inspectVisible = false">关闭</el-button>
          </div>

          <div style="display:flex;gap:8px;align-items:center;">
            <el-button
              :disabled="inspectLoading"
              type="primary"
              plain
              @click="startInspection()"
            >
              重新巡检
            </el-button>

            <el-button
              v-if="inspectReport?.reportUrl"
              :disabled="inspectLoading || inspectProgress < 100"
              type="success"
              @click="downloadInspectionReport()"
            >
              下载巡检报告（HTML）
            </el-button>

            <el-button
              v-if="inspectReport?.jsonUrl"
              :disabled="inspectLoading || inspectProgress < 100"
              type="info"
              plain
              @click="downloadInspectionJson()"
            >
              下载 JSON
            </el-button>
          </div>
        </div>
      </template>

      <!-- evidence 弹窗 -->
      <el-dialog v-model="evidenceVisible" title="Evidence" width="760px" append-to-body>
        <pre style="max-height:420px;overflow:auto;background:#0b1220;color:#e5e7eb;padding:12px;border-radius:8px;">
    {{ evidenceText }}
        </pre>
        <template #footer>
          <el-button @click="evidenceVisible = false">关闭</el-button>
        </template>
      </el-dialog>
    </el-dialog>

    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import {
  Collection,
  Tickets,
  Cpu,
  Box,
  Histogram,
  Connection,
  Bell,
  TrendCharts,
  Clock,
  Monitor,
  Document,
  WarningFilled,
} from '@element-plus/icons-vue'

import { fetchOverview, type OverviewResponse } from '@/api/overview'
import { downloadKubeconfig, runInspection, type InspectItem, type InspectReport } from '@/api/tools'

const router = useRouter()
const loading = ref(false)
const errorMsg = ref('')

/** ✅ 默认占位（无假数据） */
const overviewStats = ref<OverviewResponse['overviewStats']>([])
const capacityStats = ref<OverviewResponse['capacityStats']>([])
const opsSummary = ref<OverviewResponse['opsSummary']>([])
const cluster = reactive<OverviewResponse['cluster']>({
  basic: {
    name: 'host',
    status: 'running',
    clusterType: '',
    k8sVersion: '',
    platformVersion: '',
    location: '',
  },
  resources: {
    nodes: 0,
    namespaces: 0,
    pods: 0,
    alertRules: 0,
  },
  health: [],
})

/** 图标映射 */
const iconMap: Record<string, any> = {
  projects: Collection,
  namespaces: Tickets,
  nodes: Cpu,
  workloads: Box,
  pods: Histogram,
  services: Connection,
  alerts24h: Bell,
  runningPercent: TrendCharts,
}

const overviewStatsView = computed(() =>
  overviewStats.value.map((x) => ({
    ...x,
    icon: iconMap[x.key] || Collection,
  }))
)

const clusterStatusText = computed(() => {
  if (cluster.basic.status === 'running') return '运行中'
  if (cluster.basic.status === 'warning') return '异常'
  return '离线'
})

async function load() {
  loading.value = true
  errorMsg.value = ''
  try {
    const resp = await fetchOverview()
    overviewStats.value = resp.overviewStats || []
    capacityStats.value = resp.capacityStats || []
    opsSummary.value = resp.opsSummary || []
    cluster.basic = { ...cluster.basic, ...(resp.cluster?.basic || {}) }
    cluster.resources = { ...cluster.resources, ...(resp.cluster?.resources || {}) }
    cluster.health = resp.cluster?.health || []
  } catch (e: any) {
    errorMsg.value = '加载失败：/api/overview 未返回或网络异常'
  } finally {
    loading.value = false
  }
}

function saveBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  window.URL.revokeObjectURL(url)
}

async function handleDownloadKubeconfig() {
  try {
    const blob = await downloadKubeconfig()
    saveBlob(blob, 'kubeconfig')
    ElMessage.success('kubeconfig 已开始下载')
  } catch (e) {
    ElMessage.error('下载 kubeconfig 失败')
  }
}

function go(path: string, query?: Record<string, any>) {
  router.push({ path, query })
}

/** =======================
 * 一键巡检（Dialog + 进度模拟）
 * ======================= */
const inspectVisible = ref(false)
const inspectLoading = ref(false)
const inspectReport = ref<InspectReport | null>(null)

/** 进度模拟：后端一次性返回 items，这里做逐项“播放” */
const inspectShownItems = ref<InspectItem[]>([])
const inspectedCount = ref(0)
const totalCount = computed(() => inspectReport.value?.items?.length || 0)
const inspectProgress = computed(() => {
  const total = totalCount.value || 0
  if (total <= 0) return inspectLoading.value ? 5 : 0
  return Math.min(100, Math.round((inspectedCount.value / total) * 100))
})
const inspectProgressText = computed(() => {
  if (!inspectLoading.value) return '就绪'
  return `进度 ${inspectProgress.value}%`
})

let _timer: number | null = null
function _clearTimer() {
  if (_timer) {
    window.clearInterval(_timer)
    _timer = null
  }
}

/** 打开巡检弹窗并开始巡检 */
async function openInspection() {
  inspectVisible.value = true
  await startInspection()
}

async function startInspection() {
  _clearTimer()
  inspectLoading.value = true
  inspectReport.value = null
  inspectShownItems.value = []
  inspectedCount.value = 0

  try {
    // 你也可以传 include，先全量即可
    const resp = await runInspection({
      total_timeout_seconds: 25,
      per_check_timeout_seconds: 5,
      max_workers: 6,
      // include: 'prom,nodes,system,pods,events,storage,dns',
    })

    inspectReport.value = resp

    // 开始“逐项展示”
    const items = resp.items || []
    const total = items.length || 1
    let idx = 0

    // 根据总项数调整播放速度（保证 1.5~4s 内播完）
    const interval = Math.max(120, Math.min(320, Math.floor(2400 / total)))

    _timer = window.setInterval(() => {
      if (!inspectReport.value) return

      const it = items[idx]
      if (!it) {
        _clearTimer()
        inspectedCount.value = items.length
        inspectLoading.value = false
        ElMessage.success('巡检完成')
        return
      }

      inspectShownItems.value.push(it)
      idx += 1
      inspectedCount.value = idx

      if (idx >= items.length) {
        _clearTimer()
        inspectLoading.value = false
        ElMessage.success('巡检完成')
      }
    }, interval)
  } catch (e: any) {
    inspectLoading.value = false
    ElMessage.error('巡检失败：后端接口异常或网络问题')
  }
}

/** 下载 HTML 报告：直接打开后端生成的 reportUrl */
function downloadInspectionReport() {
  const url = inspectReport.value?.reportUrl
  if (!url) return
  // 直接打开（浏览器可另存为 / 或触发下载取决于响应头）
  window.open(url, '_blank')
}

/** 下载 JSON */
function downloadInspectionJson() {
  const url = inspectReport.value?.jsonUrl
  if (!url) return
  window.open(url, '_blank')
}

/** evidence 弹窗 */
const evidenceVisible = ref(false)
const evidenceText = ref('')

function openEvidence(it: InspectItem) {
  evidenceText.value = JSON.stringify(it.evidence || {}, null, 2)
  evidenceVisible.value = true
}

// 关闭弹窗时停止计时器
watch(inspectVisible, (v) => {
  if (!v) _clearTimer()
})

/** 工具卡片跳转 */
function goTool(key: string) {
  if (key === 'kubectl') return go('/tools/kubectl')
  if (key === 'kubeconfig') return handleDownloadKubeconfig()
  if (key === 'inspect') return openInspection()
  if (key === 'alert') return go('/metrics', { tab: 'alerts' })
}

const toolEntries = [
  { key: 'kubectl', title: 'kubectl 终端', desc: '通过命令行快速执行集群操作', icon: Monitor },
  { key: 'kubeconfig', title: 'kubeconfig 下载', desc: '获取当前集群的访问凭证文件', icon: Document },
  { key: 'inspect', title: '一键巡检', desc: '巡检集群健康并生成 HTML 报告', icon: WarningFilled },
  { key: 'alert', title: '告警规则配置', desc: '集中管理并优化告警阈值与收敛策略', icon: Clock },
]

onMounted(load)
</script>


<style scoped>
/* 你原来的样式几乎不动，仅补了状态颜色/点击手势 */
.overview-root { width: 100%; }
.overview-layout { display: grid; grid-template-columns: minmax(0, 3fr) minmax(320px, 1fr); gap: 16px; }
.overview-main { display: flex; flex-direction: column; gap: 16px; }
.section-card { border-radius: 10px; border: 1px solid #e5e7eb; }
.section-header { margin-bottom: 10px; }
.section-title { font-size: 15px; font-weight: 600; color: #111827; }
.section-subtitle { font-size: 12px; color: #9ca3af; }

.overview-card { background: #ffffff; }
.overview-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 10px; }
.stat-card { display: flex; padding: 10px 12px; border-radius: 10px; background: #f9fafb; border: 1px solid #e5e7eb; cursor: default; transition: box-shadow 0.15s ease, transform 0.1s ease, border-color 0.15s ease; }
.stat-card:hover { box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06); transform: translateY(-1px); border-color: rgba(59, 130, 246, 0.3); }
.stat-icon-wrapper { width: 32px; height: 32px; border-radius: 999px; background: rgba(59, 130, 246, 0.08); display: flex; align-items: center; justify-content: center; margin-right: 10px; }
.stat-icon { font-size: 18px; color: var(--brand-color, #3b82f6); }
.stat-content { display: flex; flex-direction: column; gap: 2px; }
.stat-value { font-size: 18px; font-weight: 600; color: #111827; }
.stat-unit { margin-left: 2px; font-size: 12px; color: #6b7280; }
.stat-label { font-size: 12px; color: #6b7280; }
.stat-desc { font-size: 11px; color: #9ca3af; }

.capacity-card { background: #ffffff; }
.capacity-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
.capacity-item { padding: 6px 0; }
.capacity-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.capacity-label { font-size: 13px; color: #4b5563; }
.capacity-value { font-size: 14px; font-weight: 600; color: #111827; }
.capacity-unit { margin-left: 2px; font-size: 12px; color: #6b7280; }
.capacity-bar { position: relative; width: 100%; height: 6px; border-radius: 999px; background: #e5e7eb; overflow: hidden; }
.capacity-bar-inner { height: 100%; border-radius: 999px; transition: width 0.25s ease; }
.capacity-ok { background: #22c55e; }
.capacity-warn { background: #f97316; }
.capacity-danger { background: #ef4444; }
.capacity-desc { margin-top: 4px; font-size: 11px; color: #9ca3af; }

.bottom-grid { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(0, 1.6fr); gap: 16px; }
.ops-card { background: #ffffff; }
.ops-list { list-style: none; padding: 0; margin: 4px 0 0; }
.ops-item { display: flex; align-items: center; padding: 6px 2px; gap: 8px; }
.ops-dot { width: 8px; height: 8px; border-radius: 999px; }
.level-ok { background: #22c55e; }
.level-warn { background: #f97316; }
.level-info { background: #3b82f6; }
.ops-item-main { flex: 1; min-width: 0; }
.ops-item-title { font-size: 13px; color: #111827; }
.ops-item-desc { font-size: 12px; color: #6b7280; }
.ops-item-extra { font-size: 12px; color: #3b82f6; white-space: nowrap; }

.tools-card { background: #ffffff; }
.tools-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 10px; margin-top: 6px; }
.tool-card { border-radius: 10px; cursor: pointer; }
.tool-card-body { display: flex; justify-content: space-between; align-items: flex-start; min-height: 80px; padding: 10px 12px; }
.tool-main { display: flex; align-items: center; gap: 10px; }
.tool-icon { font-size: 22px; color: var(--brand-color, #3b82f6); }
.tool-content { display: flex; flex-direction: column; gap: 2px; }
.tool-title { font-size: 14px; font-weight: 600; color: #111827; }
.tool-desc { font-size: 12px; color: #6b7280; }
.tool-link { font-size: 12px; margin-left: 4px; }

.overview-side { display: flex; flex-direction: column; gap: 16px; }
.cluster-card { background: #ffffff; border-radius: 10px; border: 1px solid #e5e7eb; }
.cluster-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.cluster-name { display: flex; align-items: center; gap: 6px; }
.cluster-badge { font-size: 11px; padding: 2px 6px; border-radius: 999px; background: rgba(59, 130, 246, 0.08); color: #1d4ed8; }
.cluster-title { font-size: 15px; font-weight: 600; }
.cluster-status { font-size: 12px; }
.cluster-status.cluster-running { color: #059669; }
.cluster-status.cluster-warning { color: #d97706; }
.cluster-status.cluster-down { color: #dc2626; }
.status-dot { width: 7px; height: 7px; border-radius: 999px; display: inline-block; margin-right: 4px; background: #22c55e; }
.dot-running { background: #22c55e; }
.dot-warning { background: #f97316; }
.dot-down { background: #ef4444; }

.cluster-desc { font-size: 12px; color: #6b7280; margin-bottom: 10px; }
.cluster-section-title { font-size: 13px; font-weight: 600; margin: 10px 0 6px; }
.cluster-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 4px; }
.metric-item { padding: 8px 10px; border-radius: 8px; background: #f9fafb; border: 1px solid #e5e7eb; cursor: pointer; }
.metric-item:hover { border-color: rgba(59,130,246,0.35); }
.metric-label { font-size: 12px; color: #6b7280; }
.metric-value { font-size: 16px; font-weight: 600; color: #111827; }

.health-list { list-style: none; padding: 0; margin: 4px 0 0; }
.health-item { display: flex; align-items: center; font-size: 12px; color: #4b5563; margin-bottom: 6px; }
.indicator { width: 8px; height: 8px; border-radius: 999px; margin-right: 6px; }
.indicator.ok { background: #22c55e; }
.indicator.warn { background: #f97316; }
.indicator.error { background: #ef4444; }

.mt-16 { margin-top: 16px; }

@media (max-width: 1200px) {
  .overview-layout { grid-template-columns: minmax(0, 1fr); }
  .overview-side { order: -1; }
}
</style>
