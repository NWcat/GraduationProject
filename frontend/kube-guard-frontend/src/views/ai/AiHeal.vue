<!-- src/views/ai/AiHeal.vue -->
<template>
  <div class="page">
    <div class="page-head">
      <div>
        <div class="page-title">Pod 自愈</div>
        <div class="page-subtitle">
          CrashLoopBackOff / NotReady 自动处理（由后端 HEAL_* 控制）｜后台线程状态实时展示
        </div>
      </div>

      <div class="head-actions">
        <el-input v-model="ns" class="w200" placeholder="namespace 可选" clearable />

        <el-button :loading="runningOnce" type="primary" @click="runOnce">手动跑一次</el-button>
        <el-button :loading="loadingStatus || loadingList || loadingDeployments" plain @click="refreshAll">刷新</el-button>

        <!-- ✅ 新增：Decay 配置按钮（弹窗） -->
        <el-button plain @click="openDecayDialog">Decay 配置</el-button>
      </div>
    </div>

    <el-card shadow="never" class="card">
      <!-- ✅ 状态栏：对齐 /api/ops/heal/status -->
      <div class="status">
        <div class="status-left">
          <el-tag size="large" :type="statusTagType">
            {{ statusText }}
          </el-tag>

          <div class="kv"><span class="k">enabled</span><span class="v">{{ status?.enabled ? '1' : '0' }}</span></div>
          <div class="kv"><span class="k">execute</span><span class="v">{{ status?.execute ? '1' : '0' }}</span></div>
          <div class="kv"><span class="k">interval</span><span class="v">{{ status?.interval_sec ?? '-' }}s</span></div>
          <div class="kv"><span class="k">last_run</span><span class="v">{{ fmtTsSec(status?.last_run_ts) }}</span></div>
          <div class="kv"><span class="k">max_per_cycle</span><span class="v">{{ status?.max_per_cycle ?? '-' }}</span></div>
          <div class="kv"><span class="k">cooldown</span><span class="v">{{ status?.cooldown_sec ?? '-' }}s</span></div>

          <!-- ✅ 新增：显示 decay 当前生效 -->
          <div class="kv">
            <span class="k">decay</span>
            <span class="v">{{ decayCfgText }}</span>
          </div>
        </div>

        <div class="status-right">
          <el-switch v-model="autoRefresh" active-text="自动刷新" />
          <span class="hint">每 {{ intervalSec }} 秒刷新（状态 + 事件 + 审计 + Deployments）</span>
        </div>
      </div>

      <el-alert
        v-if="status?.last_error"
        class="mt12"
        type="error"
        show-icon
        :closable="false"
        title="后台自愈线程报错"
        :description="status.last_error"
      />

      <el-alert
        v-else-if="status && !status.running"
        class="mt12"
        type="warning"
        show-icon
        :closable="false"
        title="提示"
        description="检测到后台自愈线程未运行：如果你使用了 uvicorn --reload 或多进程 workers，线程可能只在某个进程里跑，导致你这边看到 running=false。建议开发期用单进程运行。"
      />

      <el-divider />

      <el-tabs v-model="tab">
        <!-- ✅ 新增 Tab：Deployment 状态 -->
        <el-tab-pane label="Deployment 状态" name="deployments">
          <div class="toolbar">
            <el-input
              v-model="deployKeyword"
              class="w260"
              placeholder="过滤：deployment_name / uid / last_pod / reason"
              clearable
            />
            <el-select v-model="deployStatusFilter" class="w160" clearable placeholder="状态筛选">
              <el-option label="normal" value="normal" />
              <el-option label="pending" value="pending" />
              <el-option label="circuit_open" value="circuit_open" />
            </el-select>
            <el-button :loading="loadingDeployments" @click="refreshDeployments">刷新 Deployments</el-button>
          </div>

          <el-table :data="filteredDeployments" size="small" border :loading="loadingDeployments">
            <el-table-column prop="namespace" label="Namespace" width="140" />
            <el-table-column prop="deployment_name" label="Deployment" min-width="180" />
            <el-table-column prop="deployment_uid" label="UID" min-width="260" />

            <el-table-column label="状态" width="140">
              <template #default="{ row }">
                <el-tag size="small" :type="statusType(row.status)">
                  {{ row.status }}
                </el-tag>
              </template>
            </el-table-column>

            <el-table-column prop="fail_count" label="fail_count" width="110" />
            <el-table-column label="pending_until" width="180">
              <template #default="{ row }">
                <span v-if="row.pending_until_ts && row.status === 'pending'">{{ fmtTsSec(row.pending_until_ts) }}</span>
                <span v-else>-</span>
              </template>
            </el-table-column>

            <el-table-column prop="last_reason" label="last_reason" width="160" />
            <el-table-column prop="last_action" label="last_action" width="150" />
            <el-table-column prop="last_result" label="last_result" width="140" />
            <el-table-column prop="last_pod" label="last_pod" min-width="220" />
            <el-table-column label="last_ts" width="180">
              <template #default="{ row }">{{ fmtTsSec(row.last_ts) }}</template>
            </el-table-column>

            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <!-- ✅ 复位按钮：把 circuit_open / pending / fail_count 清掉 -->
                <el-button
                  size="small"
                  type="warning"
                  plain
                  :loading="resettingKey === `${row.namespace}/${row.deployment_uid}`"
                  @click="resetDeployment(row)"
                >
                  复位
                </el-button>

                <el-button size="small" plain @click="openDetail(row)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-alert
            v-if="deployments.length === 0 && !loadingDeployments"
            class="mt12"
            type="info"
            show-icon
            :closable="false"
            title="暂无数据"
            description="还没有产生 heal_events 记录时，这里会是空的。你可以先触发一次异常或手动跑一次扫描。"
          />
        </el-tab-pane>

        <!-- 原有 Tab：heal_events -->
        <el-tab-pane label="自愈事件 heal_events" name="events">
          <el-table :data="events" size="small" border :loading="loadingList">
            <el-table-column label="时间" width="180">
              <template #default="{ row }">{{ fmtTsSec(row.ts) }}</template>
            </el-table-column>
            <el-table-column prop="namespace" label="Namespace" width="160" />
            <el-table-column prop="pod" label="Pod" min-width="220" />
            <el-table-column prop="reason" label="Reason" width="160" />
            <el-table-column prop="action" label="Action" width="140" />
            <el-table-column prop="result" label="Result" width="140" />
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :loading="deletingId === `ev:${row.id}`"
                  @click="deleteEvent(row.id)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 原有 Tab：ops_actions -->
        <el-tab-pane label="动作审计 ops_actions" name="actions">
          <el-table :data="actions" size="small" border :loading="loadingList">
            <el-table-column label="时间" width="180">
              <template #default="{ row }">{{ fmtTsSec(row.ts) }}</template>
            </el-table-column>
            <el-table-column prop="action" label="Action" width="170" />
            <el-table-column prop="dry_run" label="DryRun" width="90">
              <template #default="{ row }">{{ row.dry_run ? '1' : '0' }}</template>
            </el-table-column>
            <el-table-column prop="result" label="Result" width="120" />
            <el-table-column prop="detail" label="Detail" min-width="260" />
            <el-table-column label="Target/Params" min-width="260">
              <template #default="{ row }">
                <pre class="json">{{ row.target }}\n{{ row.params }}</pre>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button
                  size="small"
                  type="danger"
                  plain
                  :loading="deletingId === `ac:${row.id}`"
                  @click="deleteAction(row.id)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <!-- 原有 Tab：summary -->
        <el-tab-pane label="扫描摘要 last_summary" name="summary">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="running">{{ status?.running ? 'true' : 'false' }}</el-descriptions-item>
            <el-descriptions-item label="enabled">{{ status?.enabled ? 'true' : 'false' }}</el-descriptions-item>
            <el-descriptions-item label="execute">{{ status?.execute ? 'true' : 'false' }}</el-descriptions-item>
            <el-descriptions-item label="interval_sec">{{ status?.interval_sec ?? '-' }}</el-descriptions-item>

            <el-descriptions-item label="last_run_ts">{{ fmtTsSec(status?.last_run_ts) }}</el-descriptions-item>
            <el-descriptions-item label="last_error">{{ status?.last_error ?? '-' }}</el-descriptions-item>

            <el-descriptions-item label="allow_ns">{{ status?.allow_ns || '(empty = all)' }}</el-descriptions-item>
            <el-descriptions-item label="deny_ns">{{ status?.deny_ns || '(empty)' }}</el-descriptions-item>

            <el-descriptions-item label="only_reasons">{{ status?.only_reasons || '(empty = all)' }}</el-descriptions-item>
            <el-descriptions-item label="cooldown_sec">{{ status?.cooldown_sec ?? '-' }}</el-descriptions-item>

            <el-descriptions-item label="max_per_cycle">{{ status?.max_per_cycle ?? '-' }}</el-descriptions-item>
            <el-descriptions-item label="last_summary">
              <pre class="json">{{ pretty(status?.last_summary) }}</pre>
            </el-descriptions-item>
          </el-descriptions>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <!-- ✅ Decay 配置弹窗 -->
    <el-dialog v-model="decayDialogVisible" title="Decay 配置" width="460px">
      <div class="dlg-row">
        <div class="dlg-label">启用衰减</div>
        <el-switch v-model="decayForm.enabled" />
      </div>
      <div class="dlg-row">
        <div class="dlg-label">衰减步长 step</div>
        <el-input-number v-model="decayForm.step" :min="1" :max="10" />
      </div>
      <el-alert
        class="mt12"
        type="info"
        show-icon
        :closable="false"
        title="说明"
        description="衰减：当某 deployment 连续恢复成功时，把 fail_count 按 step 递减，避免偶发抖动造成永久熔断。"
      />
      <template #footer>
        <el-button @click="decayDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingDecay" @click="saveDecay">保存</el-button>
      </template>
    </el-dialog>

    <!-- ✅ Deployment 详情弹窗（可选但很实用） -->
    <el-dialog v-model="detailDialogVisible" title="Deployment 详情" width="680px">
      <pre class="json">{{ pretty(detailItem) }}</pre>

      <el-divider />

      <div class="dlg-row">
        <div class="dlg-label">restore_replicas（可选）</div>
        <el-input-number v-model="restoreReplicas" :min="0" :max="100" />
        <span class="hint">留空/不填：按后端默认逻辑</span>
      </div>

      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
        <el-button
          type="warning"
          plain
          :loading="detailItem ? resettingKey === `${detailItem.namespace}/${detailItem.deployment_uid}` : false"
          @click="detailItem && resetDeployment(detailItem)"
        >
          复位这个 Deployment
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  fetchHealEvents,
  fetchOpsActions,
  runHealOnce,
  fetchHealStatus,
  deleteHealEvent,
  deleteOpsAction,
  type HealStatusResp,
  fetchHealDeployments,
  type HealDeploymentItem,
  fetchHealDecayConfig,
  setHealDecayConfig,
  healReset
} from '@/api/ops'

type Tab = 'deployments' | 'events' | 'actions' | 'summary'

const tab = ref<Tab>('deployments')
const ns = ref('')

const events = ref<any[]>([])
const actions = ref<any[]>([])
const status = ref<HealStatusResp | null>(null)

const runningOnce = ref(false)
const loadingList = ref(false)
const loadingStatus = ref(false)

const deletingId = ref<string>('') // ev:ID or ac:ID

const autoRefresh = ref(true)
const intervalSec = 5
let timer: any = null

// ------------------- Deployments -------------------
const deployments = ref<HealDeploymentItem[]>([])
const loadingDeployments = ref(false)

const deployKeyword = ref('')
const deployStatusFilter = ref<string | null>(null)

const filteredDeployments = computed(() => {
  const kw = deployKeyword.value.trim().toLowerCase()
  const st = deployStatusFilter.value

  return deployments.value.filter((d) => {
    if (st && d.status !== st) return false
    if (!kw) return true

    const hit =
      (d.deployment_name || '').toLowerCase().includes(kw) ||
      (d.deployment_uid || '').toLowerCase().includes(kw) ||
      (d.last_pod || '').toLowerCase().includes(kw) ||
      (d.last_reason || '').toLowerCase().includes(kw) ||
      (d.last_action || '').toLowerCase().includes(kw)

    return hit
  })
})

function statusType(s: string): 'success' | 'warning' | 'danger' | 'info' {
  if (s === 'normal') return 'success'
  if (s === 'pending') return 'warning'
  if (s === 'circuit_open') return 'danger'
  return 'info'
}

// ------------------- Decay dialog -------------------
const decayDialogVisible = ref(false)
const savingDecay = ref(false)
const decayCfg = ref<{ enabled: boolean; step: number } | null>(null)
const decayForm = ref<{ enabled: boolean; step: number }>({ enabled: false, step: 1 })

const decayCfgText = computed(() => {
  if (!decayCfg.value) return '-'
  return `${decayCfg.value.enabled ? 'on' : 'off'} / step=${decayCfg.value.step}`
})

function openDecayDialog() {
  decayForm.value = {
    enabled: decayCfg.value?.enabled ?? false,
    step: decayCfg.value?.step ?? 1
  }
  decayDialogVisible.value = true
}

async function refreshDecay() {
  try {
    const { data } = await fetchHealDecayConfig()
    decayCfg.value = data
  } catch (e: any) {
    // 不阻塞页面
    decayCfg.value = null
  }
}

async function saveDecay() {
  savingDecay.value = true
  try {
    const { data } = await setHealDecayConfig({
      enabled: !!decayForm.value.enabled,
      step: Number(decayForm.value.step || 1)
    })
    decayCfg.value = data
    ElMessage.success('Decay 配置已保存')
    decayDialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    savingDecay.value = false
  }
}

// ------------------- Reset -------------------
const resettingKey = ref<string>('') // `${ns}/${uid}`
const restoreReplicas = ref<number>(0)

async function resetDeployment(row: HealDeploymentItem) {
  const key = `${row.namespace}/${row.deployment_uid}`

  try {
    await ElMessageBox.confirm(
      `确定复位这个 Deployment 吗？\n${row.deployment_name}\n(uid=${row.deployment_uid})`,
      '复位确认',
      { type: 'warning', confirmButtonText: '复位', cancelButtonText: '取消' }
    )

    resettingKey.value = key

    const payload = {
      namespace: row.namespace,
      deployment_uid: row.deployment_uid,
      deployment_name: row.deployment_name,
      restore_replicas: restoreReplicas.value > 0 ? restoreReplicas.value : null
    }

    const { data } = await healReset(payload)
    if (!data.ok) throw new Error(data.reason || 'reset failed')

    ElMessage.success('已复位')
    await refreshDeployments()
    await refreshLists()
  } catch (e: any) {
    if (e === 'cancel' || e?.message === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '复位失败')
  } finally {
    resettingKey.value = ''
  }
}

// ------------------- Detail dialog -------------------
const detailDialogVisible = ref(false)
const detailItem = ref<HealDeploymentItem | null>(null)

async function openDetail(row: HealDeploymentItem) {
  detailItem.value = row
  restoreReplicas.value = 0
  detailDialogVisible.value = true
}

// ------------------- base helpers -------------------
function fmtTsSec(ts: number | null | undefined) {
  if (!ts) return '-'
  try {
    return new Date(ts * 1000).toLocaleString()
  } catch {
    return String(ts)
  }
}

function pretty(v: unknown): string {
  try {
    return JSON.stringify(v ?? {}, null, 2)
  } catch {
    return String(v)
  }
}

const statusText = computed(() => {
  if (!status.value) return '状态未知'
  if (status.value.last_error) return '线程异常'
  return status.value.running ? '线程运行中' : '线程未运行'
})

const statusTagType = computed<'success' | 'warning' | 'danger' | 'info'>(() => {
  if (!status.value) return 'info'
  if (status.value.last_error) return 'danger'
  return status.value.running ? 'success' : 'warning'
})

async function refreshLists() {
  loadingList.value = true
  try {
    const ev = await fetchHealEvents({ limit: 50, offset: 0 })
    events.value = ev.data.items ?? []

    const ac = await fetchOpsActions({ limit: 50, offset: 0 })
    actions.value = ac.data.items ?? []
  } finally {
    loadingList.value = false
  }
}

async function refreshStatus() {
  loadingStatus.value = true
  try {
    const { data } = await fetchHealStatus()
    status.value = data
  } finally {
    loadingStatus.value = false
  }
}

async function refreshDeployments() {
  loadingDeployments.value = true
  try {
    const { data } = await fetchHealDeployments({
      limit: 200,
      offset: 0,
      namespace: ns.value ? ns.value : undefined
    })
    deployments.value = data.items ?? []
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '拉取 deployments 失败')
  } finally {
    loadingDeployments.value = false
  }
}

async function refreshAll() {
  try {
    await Promise.all([refreshStatus(), refreshLists(), refreshDeployments(), refreshDecay()])
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '刷新失败')
  }
}

async function runOnce() {
  runningOnce.value = true
  try {
    await runHealOnce(ns.value ? { namespace: ns.value } : undefined)
    ElMessage.success('已触发一次自愈扫描')
    await refreshAll()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '运行失败')
  } finally {
    runningOnce.value = false
  }
}

async function deleteEvent(id: number) {
  try {
    await ElMessageBox.confirm(`确定删除这条自愈事件吗？(id=${id})`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    deletingId.value = `ev:${id}`
    await deleteHealEvent(id)
    ElMessage.success('已删除')
    await refreshLists()
  } catch (e: any) {
    if (e === 'cancel' || e?.message === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  } finally {
    deletingId.value = ''
  }
}

async function deleteAction(id: number) {
  try {
    await ElMessageBox.confirm(`确定删除这条动作审计吗？(id=${id})`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    deletingId.value = `ac:${id}`
    await deleteOpsAction(id)
    ElMessage.success('已删除')
    await refreshLists()
  } catch (e: any) {
    if (e === 'cancel' || e?.message === 'cancel') return
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  } finally {
    deletingId.value = ''
  }
}

onMounted(async () => {
  await refreshAll()
  timer = setInterval(() => {
    if (autoRefresh.value) refreshAll()
  }, intervalSec * 1000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.page {
  padding: 16px;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}
.page-title {
  font-size: 20px;
  font-weight: 800;
}
.page-subtitle {
  color: #8a8f98;
  margin-top: 4px;
  font-size: 13px;
}
.head-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}
.card {
  border-radius: 12px;
}

.status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.status-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.status-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.kv {
  display: flex;
  gap: 6px;
  align-items: baseline;
  padding: 6px 10px;
  border: 1px solid #eef1f5;
  border-radius: 10px;
  background: #fff;
}
.kv .k {
  color: #8a8f98;
  font-size: 12px;
}
.kv .v {
  font-weight: 700;
  font-size: 12px;
}

.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.hint {
  color: #8a8f98;
  font-size: 12px;
}
.w200 {
  width: 200px;
}
.w260 {
  width: 260px;
}
.w160 {
  width: 160px;
}
.json {
  background: #0b1220;
  color: #d7e0ef;
  padding: 8px;
  border-radius: 8px;
  font-size: 12px;
  overflow: auto;
  max-height: 360px;
  white-space: pre-wrap;
}
.mt12 {
  margin-top: 12px;
}

.dlg-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 10px 0;
}
.dlg-label {
  width: 130px;
  color: #606266;
  font-size: 13px;
}
</style>
