<!-- src/views/Nodes/NodeList.vue -->
<template>
  <div class="node-page">
    <!-- 顶部概览 -->
    <el-card shadow="never" class="section-card summary-card-wrap">
      <div class="section-header">
        <div class="section-title">节点列表</div>
        <div class="section-subtitle">查看集群节点状态、资源容量与运行情况</div>
      </div>

      <div class="summary-grid">
        <div class="summary-card">
          <div class="summary-label">总节点</div>
          <div class="summary-value">{{ summary.total }}</div>
        </div>

        <div class="summary-card">
          <div class="summary-label">Ready</div>
          <div class="summary-value ok">{{ summary.ready }}</div>
        </div>

        <div class="summary-card">
          <div class="summary-label">NotReady</div>
          <div class="summary-value danger">{{ summary.notReady }}</div>
        </div>

        <div class="summary-card">
          <div class="summary-label">可调度</div>
          <div class="summary-value">{{ summary.schedulable }}</div>
        </div>

        <div class="summary-card">
          <div class="summary-label">已下线</div>
          <div class="summary-value warn">{{ summary.disabled }}</div>
        </div>

        <div class="summary-card">
          <div class="summary-label">控制平面</div>
          <div class="summary-value">{{ summary.controlPlane }}</div>
        </div>

        <div class="summary-card">
          <div class="summary-label">Worker</div>
          <div class="summary-value">{{ summary.worker }}</div>
        </div>
      </div>
    </el-card>

    <!-- 查询栏 + 表格 -->
    <el-card shadow="never" class="section-card table-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <el-input
            v-model="filters.keyword"
            class="toolbar-item"
            placeholder="搜索节点名称 / IP / 角色"
            clearable
            @keyup.enter="applyFilters"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <el-select v-model="filters.status" class="toolbar-item" placeholder="状态" clearable @change="applyFilters">
            <el-option label="Ready" value="Ready" />
            <el-option label="NotReady" value="NotReady" />
          </el-select>

          <el-select v-model="filters.role" class="toolbar-item" placeholder="角色" clearable @change="applyFilters">
            <el-option label="control-plane" value="control-plane" />
            <el-option label="worker" value="worker" />
          </el-select>
        </div>

        <div class="toolbar-right">
          <el-button @click="resetFilters" plain size="small">重置</el-button>

          <el-button type="primary" @click="refresh" size="small">
            <el-icon class="mr-6"><Refresh /></el-icon>
            刷新
          </el-button>

          <el-button type="success" @click="openJoinDialog" size="small">添加节点</el-button>

          <el-button type="warning" plain @click="openOfflineDialog()" size="small">下线</el-button>

          <el-dropdown trigger="click">
            <el-button plain size="small">
              更多
              <el-icon class="ml-6"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="goClusters">纳管集群</el-dropdown-item>
                <el-dropdown-item divided @click="openRemoveDialog()">
                  <span class="danger-text">完全移除</span>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <div class="table-wrap">
        <el-table
          v-loading="loading"
          :data="pagedRows"
          size="default"
          class="node-table"
          :header-cell-style="{ background: '#f9fafb', color: '#374151' }"
          :table-layout="'fixed'"
        >
          <el-table-column type="index" width="60" label="#" />

          <!-- ✅ 节点名称列：可拖拽调宽 -->
          <el-table-column prop="name" :width="colW.name" :min-width="190">
            <template #header>
              <div class="th-resize">
                <span>节点名称</span>
                <span class="resize-handle" @mousedown.stop.prevent="startResize($event, 'name')"></span>
              </div>
            </template>

            <template #default="{ row }">
              <div class="node-name">
                <span class="node-dot" :class="row.status === 'Ready' ? 'dot-ok' : 'dot-bad'"></span>
                <span class="node-name-text">{{ row.name }}</span>

                <el-tag v-if="row.role === 'control-plane'" size="small" class="tag-muted">control-plane</el-tag>
                <el-tag v-else size="small" class="tag-muted">worker</el-tag>

                <el-tag v-if="row.unschedulable" size="small" type="warning" effect="light" class="tag-offline">
                  下线
                </el-tag>
              </div>
            </template>
          </el-table-column>

          <el-table-column prop="ip" label="IP" width="150" />

          <el-table-column prop="status" label="状态" width="130">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'Ready' ? 'success' : 'danger'" effect="light">
                {{ row.status }}
              </el-tag>
              <span v-if="row.unschedulable" class="status-sub">SchedulingDisabled</span>
            </template>
          </el-table-column>

          <el-table-column prop="kubeletVersion" label="Kubelet" min-width="150" />
          <el-table-column prop="osImage" label="OS" min-width="210" show-overflow-tooltip />

          <el-table-column label="CPU" width="150">
            <template #default="{ row }">
              <div class="metric">
                <div class="metric-top">
                  <span class="metric-strong">{{ row.cpuUsed }}</span>
                  <span class="metric-muted">/ {{ row.cpuTotal }}</span>
                </div>
                <div class="metric-sub">核</div>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="内存" width="170">
            <template #default="{ row }">
              <div class="metric">
                <div class="metric-top">
                  <span class="metric-strong">{{ row.memUsed }}</span>
                  <span class="metric-muted">/ {{ row.memTotal }}</span>
                </div>
                <div class="metric-sub">GB</div>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="Pod" width="140">
            <template #default="{ row }">
              <div class="metric">
                <div class="metric-top">
                  <span class="metric-strong">{{ row.podUsed }}</span>
                  <span class="metric-muted">/ {{ row.podCapacity }}</span>
                </div>
                <div class="metric-sub">个</div>
              </div>
            </template>
          </el-table-column>

          <el-table-column
            label="操作"
            :width="isNarrow ? 160 : 220"
            :fixed="isNarrow ? false : 'right'"
            class-name="op-col"
          >
            <template #default="{ row }">
              <div class="row-actions">
                <el-button size="small" type="primary" plain @click="openDetail(row)">详情</el-button>

                <el-button
                  size="small"
                  v-if="row.unschedulable"
                  type="success"
                  plain
                  @click="doUncordon(row.name)"
                >
                  上线
                </el-button>
                <el-button size="small" v-else type="warning" plain @click="openOfflineDialog(row.name)">下线</el-button>

                <el-dropdown trigger="click">
                  <el-button size="small" plain class="more-btn"> ⋯ </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item @click="copyText(row.ip)">复制IP</el-dropdown-item>
                      <el-dropdown-item divided @click="openRemoveDialog(row.name)">
                        <span class="danger-text">完全移除</span>
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div class="pager">
        <div class="pager-left">
          <span class="pager-hint">共 {{ filteredRows.length }} 条</span>
        </div>
        <el-pagination
          background
          layout="prev, pager, next, sizes"
          :page-size="page.size"
          :page-sizes="[5, 10, 20, 50]"
          :total="filteredRows.length"
          :current-page="page.current"
          @current-change="(p:number)=>page.current=p"
          @size-change="(s:number)=>{page.size=s; page.current=1}"
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detail.visible" size="420px" title="节点详情" destroy-on-close>
      <template v-if="detail.node">
        <div class="drawer-block">
          <div class="drawer-title">基础信息</div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="名称">{{ detail.node.name }}</el-descriptions-item>
            <el-descriptions-item label="IP">{{ detail.node.ip }}</el-descriptions-item>
            <el-descriptions-item label="角色">{{ detail.node.role }}</el-descriptions-item>
            <el-descriptions-item label="状态">{{ detail.node.status }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <div class="drawer-block">
          <div class="drawer-title">系统信息</div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="Kubelet">{{ detail.node.kubeletVersion }}</el-descriptions-item>
            <el-descriptions-item label="OS">{{ detail.node.osImage }}</el-descriptions-item>
            <el-descriptions-item label="Kernel">{{ detail.node.kernelVersion }}</el-descriptions-item>
            <el-descriptions-item label="Container Runtime">{{ detail.node.containerRuntime }}</el-descriptions-item>
          </el-descriptions>
        </div>

        <div class="drawer-block">
          <div class="drawer-title">容量与分配</div>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="CPU(核)">{{ detail.node.cpuUsed }} / {{ detail.node.cpuTotal }}</el-descriptions-item>
            <el-descriptions-item label="内存(GB)">{{ detail.node.memUsed }} / {{ detail.node.memTotal }}</el-descriptions-item>
            <el-descriptions-item label="Pod">{{ detail.node.podUsed }} / {{ detail.node.podCapacity }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </template>

      <template #footer>
        <el-button @click="detail.visible=false">关闭</el-button>
        <el-button type="primary" @click="detail.visible=false">确定</el-button>
      </template>
    </el-drawer>

    <!-- 添加节点弹窗：join 命令 -->
    <el-dialog v-model="join.visible" title="添加节点（自建/普通服务器）" width="640px" destroy-on-close>
      <div class="form-grid">
        <div class="form-item">
          <div class="form-label">K3S_URL（server）</div>
          <el-input v-model="join.server" placeholder="例如：https://<master-ip>:6443" />
          <div class="form-hint">如果是 k3s，通常是 API Server 地址（6443）。</div>
        </div>

        <div class="form-item">
          <div class="form-label">K3S_TOKEN（token）</div>
          <el-input v-model="join.token" placeholder="k3s token" show-password />
          <div class="form-hint">可以从 master 的 /var/lib/rancher/k3s/server/node-token 获取。</div>
        </div>

        <div class="form-item">
          <div class="form-label">Node IP（可选）</div>
          <el-input v-model="join.node_ip" placeholder="例如：192.168.100.11" clearable />
          <div class="form-hint">不填则由 k3s 自动选择节点 IP</div>
        </div>

        <div class="form-item">
          <div class="form-label">K3S 版本（可选）</div>
          <el-input v-model="join.k3s_version" placeholder="例如：v1.33.3+k3s1（建议与 master 一致）" clearable />
          <div class="form-hint">不填 = 默认安装“最新版本”，容易导致新节点版本比集群高。</div>
        </div>

        <div class="form-item">
          <div class="form-label">Flannel 网卡（可选）</div>
          <el-input v-model="join.flannel_iface" placeholder="例如：eth0 / ens192" clearable />
          <div class="form-hint">多网卡环境建议指定 flannel-iface</div>
        </div>

        <div class="form-item">
          <div class="form-label">生成的 Join 命令</div>
          <el-input v-model="join.command" type="textarea" :rows="3" placeholder="点击“生成命令”" readonly />
        </div>
      </div>

      <template #footer>
        <el-button @click="join.visible = false">关闭</el-button>
        <el-button :loading="join.loading" @click="genJoinCmd">生成命令</el-button>
        <el-button type="primary" :disabled="!join.command" @click="copyText(join.command)">复制命令</el-button>
      </template>
    </el-dialog>

    <!-- 下线节点弹窗 -->
    <el-dialog v-model="off.visible" title="下线节点（cordon → 可选 drain）" width="640px" destroy-on-close>
      <div class="form-grid">
        <div class="form-item">
          <div class="form-label">选择节点</div>
          <el-select v-model="off.node" filterable placeholder="请选择要下线的节点" class="w100">
            <el-option v-for="n in rows" :key="n.name" :label="`${n.name} (${n.role})`" :value="n.name" />
          </el-select>
          <div class="form-hint">下线 = 禁止调度新 Pod（可选驱逐已有 Pod）。不会删除节点对象，后续可一键上线（uncordon）。</div>
        </div>

        <div class="form-item">
          <div class="form-label">参数</div>
          <div class="row">
            <el-switch v-model="off.drain" />
            <span class="unit">drain</span>

            <el-input-number v-model="off.grace" :min="0" :max="600" :disabled="!off.drain" />
            <span class="unit">grace_seconds</span>

            <el-input-number v-model="off.timeout" :min="30" :max="1800" :disabled="!off.drain" />
            <span class="unit">timeout_seconds</span>

            <el-switch v-model="off.force" :disabled="!off.drain" />
            <span class="unit">force</span>
          </div>
          <div class="form-hint">
            drain=true：尝试驱逐 Pod；grace_seconds：每个 Pod 优雅退出时间；timeout_seconds：等待驱逐的总时长；force：允许动
            kube-system（慎用）。
          </div>
        </div>

        <div class="form-item">
          <div class="form-label">结果</div>
          <el-input v-model="off.resultText" type="textarea" :rows="6" readonly placeholder="执行后显示结果" />
        </div>
      </div>

      <template #footer>
        <el-button @click="off.visible=false">关闭</el-button>
        <el-button type="warning" :loading="off.loading" :disabled="!off.node" @click="doOfflineNode">确认下线</el-button>
      </template>
    </el-dialog>

    <!-- 移除节点弹窗 -->
    <el-dialog v-model="rm.visible" title="完全移除节点（cordon → drain → delete）" width="640px" destroy-on-close>
      <div class="form-grid">
        <div class="form-item">
          <div class="form-label">选择节点</div>
          <el-select v-model="rm.node" filterable placeholder="请选择要移除的节点" class="w100">
            <el-option v-for="n in rows" :key="n.name" :label="`${n.name} (${n.role})`" :value="n.name" />
          </el-select>
          <div class="form-hint danger">
            注意：这是“从集群删除 Node 对象”。如果该节点机器上的 k3s-agent 仍在运行且能连上 server，节点可能会再次注册回来。
            退役节点需在该机器上停止/卸载 k3s-agent。卸载脚本/usr/local/bin/k3s-agent-uninstall.sh
          </div>
        </div>

        <div class="form-item">
          <div class="form-label">参数</div>
          <div class="row">
            <el-input-number v-model="rm.grace" :min="0" :max="600" />
            <span class="unit">grace_seconds</span>

            <el-input-number v-model="rm.timeout" :min="30" :max="1800" />
            <span class="unit">timeout_seconds</span>

            <el-switch v-model="rm.force" />
            <span class="unit">force</span>
          </div>
          <div class="form-hint">grace_seconds：优雅退出等待；timeout_seconds：drain 最多等待；force=true 更强硬（慎用）。</div>
        </div>

        <div class="form-item">
          <div class="form-label">结果</div>
          <el-input v-model="rm.resultText" type="textarea" :rows="6" readonly placeholder="执行后显示结果" />
        </div>
      </div>

      <template #footer>
        <el-button @click="rm.visible = false">关闭</el-button>
        <el-button type="danger" :loading="rm.loading" :disabled="!rm.node" @click="doRemoveNode">确认移除</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchNodes, fetchJoinInfo, removeNode, offlineNode, uncordonNode, type NodeRow } from '@/api/nodes'
import { Search, Refresh, ArrowDown } from '@element-plus/icons-vue'

const router = useRouter()
const loading = ref(false)

/** ✅ 小屏判定：小屏不 fixed 右侧操作列，避免挤爆 */
const isNarrow = ref(false)
function updateNarrow() {
  isNarrow.value = window.innerWidth < 1200
}

/** ✅ 列宽（可拖拽） */
const colW = reactive({
  name: 300, // 节点名称列默认宽度
})

const resizing = reactive({
  active: false,
  key: '' as keyof typeof colW | '',
  startX: 0,
  startW: 0,
})

function startResize(e: MouseEvent, key: keyof typeof colW) {
  resizing.active = true
  resizing.key = key
  resizing.startX = e.clientX
  resizing.startW = colW[key]

  document.addEventListener('mousemove', onResizeMove)
  document.addEventListener('mouseup', stopResize)
}

function onResizeMove(e: MouseEvent) {
  if (!resizing.active || !resizing.key) return
  const dx = e.clientX - resizing.startX
  const next = resizing.startW + dx
  const min = 190
  const max = 900
  colW[resizing.key] = Math.max(min, Math.min(max, next))
}

function stopResize() {
  if (!resizing.active) return
  resizing.active = false
  resizing.key = ''
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', stopResize)
}

onBeforeUnmount(() => {
  document.removeEventListener('mousemove', onResizeMove)
  document.removeEventListener('mouseup', stopResize)
})

// filters / page
const filters = reactive({
  keyword: '',
  status: '' as '' | 'Ready' | 'NotReady',
  role: '' as '' | 'control-plane' | 'worker',
})

const page = reactive({
  current: 1,
  size: 10,
})

// ✅ 初始化为空
const rows = ref<(NodeRow & { unschedulable?: boolean })[]>([])

async function load() {
  loading.value = true
  try {
    const data = await fetchNodes()
    rows.value = (data as any) || []
  } catch (e: any) {
    ElMessage.error('获取节点数据失败：' + (e?.message ?? 'unknown'))
  } finally {
    loading.value = false
  }
}

// ✅ 纳管集群：跳转到 /clusters（按你路由实际路径调整）
function goClusters() {
  router.push('/clusters')
}

// -----------------------------
// 计算：过滤 / 分页 / 汇总
// -----------------------------
const filteredRows = computed(() => {
  const kw = filters.keyword.trim().toLowerCase()
  return rows.value.filter((r) => {
    const hitKw =
      !kw ||
      r.name.toLowerCase().includes(kw) ||
      r.ip.toLowerCase().includes(kw) ||
      r.role.toLowerCase().includes(kw)

    const hitStatus = !filters.status || r.status === filters.status
    const hitRole = !filters.role || r.role === filters.role
    return hitKw && hitStatus && hitRole
  })
})

const pagedRows = computed(() => {
  const start = (page.current - 1) * page.size
  return filteredRows.value.slice(start, start + page.size)
})

const summary = computed(() => {
  const all = rows.value
  const total = all.length
  const ready = all.filter((n) => n.status === 'Ready').length
  const notReady = all.filter((n) => n.status === 'NotReady').length
  const schedulable = all.filter((n) => !n.unschedulable).length
  const disabled = all.filter((n) => !!n.unschedulable).length
  const controlPlane = all.filter((n) => n.role === 'control-plane').length
  const worker = all.filter((n) => n.role === 'worker').length
  return { total, ready, notReady, schedulable, disabled, controlPlane, worker }
})

function applyFilters() {
  page.current = 1
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  filters.role = ''
  page.current = 1
}

async function refresh() {
  page.current = 1
  await load()
  ElMessage.success('已刷新')
}

// -----------------------------
// 详情抽屉
// -----------------------------
const detail = reactive<{
  visible: boolean
  node: NodeRow | null
}>({
  visible: false,
  node: null,
})

function openDetail(row: NodeRow) {
  detail.node = row
  detail.visible = true
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制：' + text)
  } catch {
    ElMessage.warning('复制失败，请手动复制：' + text)
  }
}

// -----------------------------
// 添加节点（join 命令）
// -----------------------------
const join = reactive({
  visible: false,
  loading: false,
  server: '',
  token: '',
  node_ip: '',
  flannel_iface: '',
  k3s_version: '',
  command: '',
})

function openJoinDialog() {
  join.visible = true
  join.loading = false
  join.command = ''
}

async function genJoinCmd() {
  join.loading = true
  try {
    const server = join.server.trim()
    const token = join.token.trim()
    const node_ip = join.node_ip.trim()
    const flannel_iface = join.flannel_iface.trim()
    const k3s_version = join.k3s_version.trim()

    const resp = await fetchJoinInfo({
      server,
      token,
      node_ip: node_ip || undefined,
      flannel_iface: flannel_iface || undefined,
      k3s_version: k3s_version || undefined,
    })

    if (resp.ok) {
      join.command = resp.command
      ElMessage.success('已生成命令')
    } else {
      join.command = resp.command_template
      ElMessage.warning(resp.hint || '请补全 server / token')
    }
  } catch (e: any) {
    ElMessage.error('生成失败：' + (e?.message ?? 'unknown'))
  } finally {
    join.loading = false
  }
}

// -----------------------------
// 移除节点
// -----------------------------
const rm = reactive({
  visible: false,
  loading: false,
  node: '' as string,
  grace: 30,
  timeout: 180,
  force: false,
  resultText: '',
})

function openRemoveDialog(nodeName?: string) {
  rm.visible = true
  rm.loading = false
  rm.node = nodeName || ''
  rm.resultText = ''
}

async function doRemoveNode() {
  if (!rm.node) return

  rm.loading = true
  rm.resultText = ''
  try {
    const resp = await removeNode(rm.node, {
      grace_seconds: rm.grace,
      timeout_seconds: rm.timeout,
      force: rm.force,
    })
    rm.resultText = JSON.stringify(resp, null, 2)
    ElMessage.success('已提交移除节点')
    await load()
  } catch (e: any) {
    rm.resultText = String(e?.message ?? e)
    ElMessage.error('移除失败：' + (e?.message ?? 'unknown'))
  } finally {
    rm.loading = false
  }
}

// -----------------------------
// 下线 / 上线
// -----------------------------
const off = reactive({
  visible: false,
  loading: false,
  node: '' as string,
  drain: true,
  grace: 30,
  timeout: 180,
  force: false,
  resultText: '',
})

function openOfflineDialog(nodeName?: string) {
  off.visible = true
  off.loading = false
  off.node = nodeName || ''
  off.resultText = ''
}

async function doOfflineNode() {
  if (!off.node) return
  off.loading = true
  off.resultText = ''
  try {
    const resp = await offlineNode(off.node, {
      drain: off.drain,
      grace_seconds: off.grace,
      timeout_seconds: off.timeout,
      force: off.force,
    })
    off.resultText = JSON.stringify(resp, null, 2)
    ElMessage.success('已下线节点')
    await load()
  } catch (e: any) {
    off.resultText = String(e?.message ?? e)
    ElMessage.error('下线失败：' + (e?.message ?? 'unknown'))
  } finally {
    off.loading = false
  }
}

async function doUncordon(nodeName: string) {
  try {
    await uncordonNode(nodeName)
    ElMessage.success('已上线节点')
    await load()
  } catch (e: any) {
    ElMessage.error('上线失败：' + (e?.message ?? 'unknown'))
  }
}

onMounted(() => {
  updateNarrow()
  window.addEventListener('resize', updateNarrow)
  load()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateNarrow)
})
</script>

<style scoped>
.node-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-card {
  border-radius: 14px;
  border: 1px solid #eef2f7;
  background: #ffffff;
}

.summary-card-wrap :deep(.el-card__body),
.table-card :deep(.el-card__body) {
  padding: 18px;
}

.section-header {
  margin-bottom: 12px;
}
.section-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}
.section-subtitle {
  margin-top: 2px;
  font-size: 12px;
  color: #94a3b8;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
.summary-card {
  padding: 12px 14px;
  border-radius: 14px;
  background: #f8fafc;
  border: 1px solid #eef2f7;
}
.summary-label {
  font-size: 12px;
  color: #64748b;
}
.summary-value {
  margin-top: 6px;
  font-size: 22px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: 0.2px;
}
.summary-value.ok {
  color: #059669;
}
.summary-value.danger {
  color: #dc2626;
}
.summary-value.warn {
  color: #d97706;
}

/* 工具栏 */
.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  align-items: flex-start;
}
.toolbar-left {
  flex: 1;
  min-width: 520px;
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.toolbar-item {
  width: 240px;
}

@media (max-width: 1200px) {
  .toolbar-item {
    width: 200px;
  }
}
@media (max-width: 900px) {
  .toolbar-left {
    min-width: unset;
  }
  .toolbar-item {
    width: 100%;
  }
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .toolbar-right {
    justify-content: flex-start;
  }
}

/* 表格外层 */
.table-wrap {
  border: 1px solid #eef2f7;
  border-radius: 14px;
  overflow: hidden;
}

.node-table {
  width: 100%;
}

:deep(.el-table__fixed-right) {
  box-shadow: -8px 0 18px rgba(15, 23, 42, 0.06);
}
:deep(.el-table__fixed) {
  box-shadow: 8px 0 18px rgba(15, 23, 42, 0.04);
}

/* ✅ 表头可拖拽手柄 */
.th-resize {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
}
.resize-handle {
  width: 10px;
  height: 18px;
  cursor: col-resize;
  flex: 0 0 auto;
  position: relative;
  opacity: 0.6;
}
.resize-handle::after {
  content: '';
  position: absolute;
  left: 4px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: #cbd5e1;
  border-radius: 2px;
}
.resize-handle:hover {
  opacity: 1;
}

.node-name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.node-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  display: inline-block;
  flex: 0 0 auto;
}
.dot-ok {
  background: #22c55e;
}
.dot-bad {
  background: #ef4444;
}

/* ✅ 修复：不要 max-width 卡死，列变宽就能显示更多 */
.node-name-text {
  font-weight: 700;
  color: #0f172a;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag-muted {
  margin-left: 2px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #475569;
}
.tag-offline {
  margin-left: 2px;
}

.status-sub {
  margin-left: 8px;
  font-size: 12px;
  color: #94a3b8;
}

/* 指标 */
.metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.metric-top {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.metric-strong {
  font-weight: 800;
  color: #0f172a;
}
.metric-muted {
  font-size: 12px;
  color: #94a3b8;
}
.metric-sub {
  font-size: 12px;
  color: #94a3b8;
}

/* 操作区 */
.row-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}
.more-btn {
  padding: 0 10px;
}

.danger-text {
  color: #dc2626;
}

/* 分页 */
.pager {
  margin-top: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.pager-hint {
  font-size: 12px;
  color: #64748b;
}

.mr-6 {
  margin-right: 6px;
}
.ml-6 {
  margin-left: 6px;
}

/* dialogs */
.form-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-label {
  font-size: 12px;
  color: #334155;
  font-weight: 700;
}
.form-hint {
  font-size: 12px;
  color: #64748b;
}
.form-hint.danger {
  color: #dc2626;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.unit {
  font-size: 12px;
  color: #64748b;
}
.w100 {
  width: 100%;
}
</style>
