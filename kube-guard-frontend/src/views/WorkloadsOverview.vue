<!-- src/views/Workloads/WorkloadsOverview.vue -->
<template>
  <div class="workloads-page">
    <!-- 顶部：标题 + 说明 -->
    <div class="page-head">
      <div>
        <div class="page-title">工作负载概览</div>
        <div class="page-subtitle">统一管理无状态 / 有状态 / Pod，支持常用运维操作</div>
      </div>

      <div class="head-actions">
        <el-button :loading="loading" @click="handleRefresh">
          <el-icon class="mr6"><Refresh /></el-icon>
          刷新
        </el-button>

        <el-button type="primary" plain @click="handleCreateHint">
          <el-icon class="mr6"><Plus /></el-icon>
          新建
        </el-button>
      </div>
    </div>

    <!-- Tabs + 筛选条 -->
    <el-card shadow="never" class="card">
      <div class="tabs-row">
        <el-tabs v-model="activeKind" class="tabs" @tab-change="handleTabChange">
          <el-tab-pane label="无状态负载（Deployment）" name="deployment" />
          <el-tab-pane label="有状态负载（StatefulSet）" name="statefulset" />
          <el-tab-pane label="Pod 管理" name="pod" />
        </el-tabs>

        <div class="filters">
          <el-select v-model="filters.namespace" placeholder="命名空间" clearable class="w160">
            <el-option v-for="ns in namespaceOptions" :key="ns" :label="ns" :value="ns" />
          </el-select>

          <el-select v-model="filters.status" placeholder="状态" clearable class="w140">
            <el-option label="运行中" value="running" />
            <el-option label="异常" value="warning" />
            <el-option label="失败" value="failed" />
            <el-option label="未知" value="unknown" />
          </el-select>

          <el-input
            v-model="filters.keyword"
            placeholder="搜索名称 / 节点 / 镜像..."
            clearable
            class="w260"
            @keyup.enter="applyFilters"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>

          <el-button type="primary" @click="applyFilters">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </div>
      </div>

      <!-- 工具条：不同类型显示不同操作 -->
      <div class="toolbar">
        <div class="toolbar-left">
          <el-tag type="info" effect="plain">
            当前：{{ kindLabel }}
          </el-tag>
          <span class="muted">共 {{ filteredRows.length }} 条</span>
        </div>

        <div class="toolbar-right">
          <!-- Deployment/StatefulSet 的批量操作 -->
          <template v-if="activeKind !== 'pod'">
            <el-button :disabled="selected.length === 0" @click="handleBatchRestart">
              <el-icon class="mr6"><RefreshRight /></el-icon>
              批量重启
            </el-button>
            <el-button :disabled="selected.length === 0" @click="handleBatchScale">
              <el-icon class="mr6"><Aim /></el-icon>
              批量扩缩容
            </el-button>
          </template>

          <!-- Pod 的批量操作 -->
          <template v-else>
            <el-button
              :disabled="selected.length === 0"
              type="danger"
              plain
              @click="handleBatchDeletePods"
            >
              <el-icon class="mr6"><Delete /></el-icon>
              批量删除
            </el-button>
          </template>
        </div>
      </div>

      <!-- 表格 -->
      <el-table
        :data="pagedRows"
        class="table"
        height="520"
        stripe
        @selection-change="handleSelectionChange"
        v-loading="loading"
      >
        <el-table-column type="selection" width="44" />

        <el-table-column prop="name" label="名称" min-width="220" fixed="left">
          <template #default="{ row }">
            <div class="name-cell">
              <span class="name">{{ row.name }}</span>
              <el-tag v-if="row.kindTag" size="small" effect="plain" class="ml8">
                {{ row.kindTag }}
              </el-tag>
            </div>
            <div class="sub muted">ns: {{ row.namespace }} · {{ row.age }}</div>
          </template>
        </el-table-column>

        <el-table-column prop="namespace" label="命名空间" width="140" />

        <!-- Deployment / StatefulSet -->
        <template v-if="activeKind !== 'pod'">
          <el-table-column label="副本" width="120">
            <template #default="{ row }">
              <span class="mono">{{ row.readyReplicas }}/{{ row.replicas }}</span>
            </template>
          </el-table-column>

          <el-table-column prop="strategy" label="策略" width="140">
            <template #default="{ row }">
              <el-tag size="small" type="info" effect="plain">{{ row.strategy }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column prop="image" label="镜像" min-width="220" show-overflow-tooltip />

          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <StatusPill :status="row.status" />
            </template>
          </el-table-column>

          <el-table-column label="操作" width="360" fixed="right">
            <template #default="{ row }">
              <div class="ops">
                <el-button size="small" @click="openDetail(row)">详情</el-button>
                <el-button size="small" @click="openScaleDialog(row)">扩缩容</el-button>
                <el-button size="small" @click="confirmRestart(row)">重启</el-button>
                <el-button size="small" @click="openYaml(row)">YAML</el-button>
                <el-button size="small" type="danger" plain @click="confirmDeleteWorkload(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </template>

        <!-- Pod -->
        <template v-else>
          <el-table-column prop="node" label="节点" width="160" show-overflow-tooltip />
          <el-table-column prop="podIP" label="Pod IP" width="140" />
          <el-table-column label="重启次数" width="110">
            <template #default="{ row }">
              <span class="mono">{{ row.restarts }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="image" label="镜像" min-width="220" show-overflow-tooltip />
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <StatusPill :status="row.status" />
            </template>
          </el-table-column>

          <el-table-column label="操作" width="360" fixed="right">
            <template #default="{ row }">
              <div class="ops">
                <el-button size="small" @click="openDetail(row)">详情</el-button>
                <el-button size="small" @click="openLogs(row)">日志</el-button>
                <el-button size="small" @click="openYaml(row)">YAML</el-button>
                <el-button size="small" type="danger" plain @click="confirmDeletePod(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </template>
      </el-table>

      <!-- 分页 -->
      <div class="pager">
        <el-pagination
          layout="total, sizes, prev, pager, next"
          :total="filteredRows.length"
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.pageSize"
          :page-sizes="[10, 20, 50, 100]"
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detail.open" :title="detailTitle" size="520px">
      <div class="drawer-body">
        <div class="kv">
          <div class="k">名称</div><div class="v">{{ detail.row?.name }}</div>
          <div class="k">类型</div><div class="v">{{ kindLabel }}</div>
          <div class="k">命名空间</div><div class="v">{{ detail.row?.namespace }}</div>
          <div class="k">状态</div>
          <div class="v"><StatusPill :status="detail.row?.status || 'unknown'" /></div>
          <div class="k">镜像</div><div class="v mono">{{ detail.row?.image || '-' }}</div>
        </div>

        <el-divider />

        <template v-if="activeKind !== 'pod'">
          <div class="kv">
            <div class="k">副本</div><div class="v mono">{{ detail.row?.readyReplicas }}/{{ detail.row?.replicas }}</div>
            <div class="k">策略</div><div class="v">{{ detail.row?.strategy }}</div>
            <div class="k">更新时间</div><div class="v">{{ detail.row?.updatedAt || '-' }}</div>
          </div>
        </template>

        <template v-else>
          <div class="kv">
            <div class="k">节点</div><div class="v">{{ detail.row?.node }}</div>
            <div class="k">Pod IP</div><div class="v mono">{{ detail.row?.podIP }}</div>
            <div class="k">重启次数</div><div class="v mono">{{ detail.row?.restarts }}</div>
            <div class="k">创建时间</div><div class="v">{{ detail.row?.createdAt || '-' }}</div>
          </div>
        </template>

        <el-divider />

        <div class="hint">
          这里可以继续加：容器列表、事件 Events、资源用量、YAML 预览等（后端接 Kubernetes API / Prometheus）。
        </div>
      </div>
    </el-drawer>

    <!-- YAML 弹窗 -->
    <el-dialog v-model="yaml.open" :title="yamlTitle" width="820px">
      <el-input type="textarea" :rows="18" v-model="yaml.content" readonly class="mono" />
      <template #footer>
        <el-button @click="yaml.open = false">关闭</el-button>
        <el-button type="primary" @click="copyYaml">复制</el-button>
      </template>
    </el-dialog>

    <!-- 扩缩容弹窗 -->
    <el-dialog v-model="scale.open" title="扩缩容" width="460px">
      <div class="scale-box">
        <div class="muted mb8">
          {{ scale.row?.name }}（ns: {{ scale.row?.namespace }}）
        </div>
        <el-input-number v-model="scale.replicas" :min="0" :max="200" />
      </div>
      <template #footer>
        <el-button @click="scale.open = false">取消</el-button>
        <el-button type="primary" @click="submitScale">确定</el-button>
      </template>
    </el-dialog>

    <!-- ✅ 新建（YAML apply） -->
<el-dialog v-model="create.open" title="新建 / 应用 YAML" width="860px">
  <div style="display:flex; gap:12px; margin-bottom:10px; flex-wrap:wrap;">
    <el-select v-model="create.kind" style="width:160px">
      <el-option label="Deployment" value="deployment" />
      <el-option label="StatefulSet" value="statefulset" />
      <el-option label="Pod" value="pod" />
    </el-select>

    <el-select v-model="create.namespace" filterable allow-create default-first-option style="width:220px" placeholder="namespace">
      <el-option v-for="ns in namespaceOptions" :key="ns" :label="ns" :value="ns" />
    </el-select>

    <el-input v-model="create.name" style="width:220px" placeholder="name" />
    <el-input v-model="create.image" style="width:260px" placeholder="image，例如 nginx:1.25" />
    <el-input-number v-if="create.kind !== 'pod'" v-model="create.replicas" :min="0" :max="200" />
  </div>

  <el-input type="textarea" :rows="18" v-model="create.yaml" class="mono" />

  <template #footer>
    <el-button @click="create.open = false">取消</el-button>
    <el-button type="primary" :loading="create.applying" @click="submitCreate">应用到集群</el-button>
  </template>
</el-dialog>

<!-- ✅ Pod 日志（可选） -->
<el-dialog v-model="logs.open" :title="logs.title" width="900px">
  <el-input type="textarea" :rows="20" v-model="logs.content" readonly class="mono" />
  <template #footer>
    <el-button @click="logs.open = false">关闭</el-button>
  </template>
</el-dialog>

  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch, defineComponent, h, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search, Plus, RefreshRight, Aim, Delete } from '@element-plus/icons-vue'
import {
  fetchNamespaces,
  fetchWorkloads,
  fetchWorkloadYaml,
  scaleWorkload,
  restartWorkload,
  deletePod,
  applyManifest,
  fetchPodLogs,
  deleteWorkload,
} from '@/api/workloads'
import type { WorkloadRow, Kind, RowStatus } from '@/api/workloads'

const loading = ref(false)
const activeKind = ref<Kind>('deployment')

const filters = reactive({
  namespace: '' as string,
  status: '' as '' | RowStatus,
  keyword: '' as string,
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
})

const selected = ref<WorkloadRow[]>([])
const namespaceOptions = ref<string[]>([])
const rows = ref<WorkloadRow[]>([])

const kindLabel = computed(() => {
  if (activeKind.value === 'deployment') return '无状态负载（Deployment）'
  if (activeKind.value === 'statefulset') return '有状态负载（StatefulSet）'
  return 'Pod 管理'
})

const filteredRows = computed(() => {
  const kw = filters.keyword.trim().toLowerCase()
  return rows.value
    .filter((r) => r.kind === activeKind.value)
    .filter((r) => (filters.namespace ? r.namespace === filters.namespace : true))
    .filter((r) => (filters.status ? r.status === filters.status : true))
    .filter((r) => {
      if (!kw) return true
      const hay = [r.name, r.namespace, r.image ?? '', r.node ?? '', r.podIP ?? ''].join(' ').toLowerCase()
      return hay.includes(kw)
    })
})

const pagedRows = computed(() => {
  const start = (pagination.page - 1) * pagination.pageSize
  const end = start + pagination.pageSize
  return filteredRows.value.slice(start, end)
})

watch(
  () => [activeKind.value, filters.namespace, filters.status, filters.keyword],
  () => {
    pagination.page = 1
    selected.value = []
  }
)

function handleSelectionChange(list: WorkloadRow[]) {
  selected.value = list
}
function applyFilters() {
  pagination.page = 1
}
function resetFilters() {
  filters.namespace = ''
  filters.status = ''
  filters.keyword = ''
  pagination.page = 1
}

function handleTabChange() {
  loadData()
}

async function handleRefresh() {
  await loadData()
}

/** ✅ 初始化：namespaces + 默认列表 */
onMounted(async () => {
  try {
    namespaceOptions.value = await fetchNamespaces()
  } catch (e: any) {
    ElMessage.error('命名空间加载失败：' + (e?.message ?? 'unknown'))
  }
  await loadData()
})

async function loadData() {
  loading.value = true
  try {
    const resp = await fetchWorkloads({
      kind: activeKind.value,
      namespace: filters.namespace || undefined,
      status: (filters.status || undefined) as any,
      keyword: filters.keyword || undefined,
    })
    rows.value = resp.items || []
  } catch (e: any) {
    ElMessage.error('刷新失败：' + (e?.message ?? 'unknown'))
  } finally {
    loading.value = false
  }
}

/** 详情抽屉 */
const detail = reactive<{ open: boolean; row: WorkloadRow | null }>({ open: false, row: null })
const detailTitle = computed(() => detail.row?.name ?? '详情')
function openDetail(row: WorkloadRow) {
  detail.row = row
  detail.open = true
}

/** YAML 弹窗：改成真实接口 */
const yaml = reactive<{ open: boolean; content: string; row: WorkloadRow | null }>({ open: false, content: '', row: null })
const yamlTitle = computed(() => `YAML · ${yaml.row?.name ?? ''}`)
async function openYaml(row: WorkloadRow) {
  yaml.row = row
  yaml.open = true
  yaml.content = '加载中...'
  try {
    const resp = await fetchWorkloadYaml({ kind: row.kind, namespace: row.namespace, name: row.name })
    yaml.content = resp.yaml
  } catch (e: any) {
    yaml.content = ''
    ElMessage.error('获取 YAML 失败：' + (e?.message ?? 'unknown'))
  }
}
async function copyYaml() {
  try {
    await navigator.clipboard.writeText(yaml.content)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败（浏览器权限限制）')
  }
}

/** 扩缩容：真实接口 */
const scale = reactive<{ open: boolean; row: WorkloadRow | null; replicas: number }>({ open: false, row: null, replicas: 1 })
function openScaleDialog(row: WorkloadRow) {
  scale.row = row
  scale.replicas = row.replicas ?? 1
  scale.open = true
}
async function submitScale() {
  if (!scale.row) return
  const row = scale.row
  try {
    await scaleWorkload({
      kind: row.kind as any,
      namespace: row.namespace,
      name: row.name,
      replicas: scale.replicas,
    })
    ElMessage.success(`已提交扩缩容：${scale.replicas}`)
    scale.open = false
    await loadData()
  } catch (e: any) {
    ElMessage.error('扩缩容失败：' + (e?.message ?? 'unknown'))
  }
}

/** 重启：真实接口 */
async function confirmRestart(row: WorkloadRow) {
  await ElMessageBox.confirm(
    `确定要重启 ${row.name} 吗？\n（将触发滚动更新）`,
    '确认重启',
    { type: 'warning' }
  )
  try {
    await restartWorkload({ kind: row.kind as any, namespace: row.namespace, name: row.name })
    ElMessage.success('已触发重启')
    await loadData()
  } catch (e: any) {
    ElMessage.error('重启失败：' + (e?.message ?? 'unknown'))
  }
}

/** Pod：删除（真实） */
async function confirmDeletePod(row: WorkloadRow) {
  await ElMessageBox.confirm(
    `确定删除 Pod ${row.name} 吗？\n（若由控制器管理，会自动重建）`,
    '确认删除',
    { type: 'warning' }
  )
  try {
    await deletePod({ namespace: row.namespace, name: row.name })
    ElMessage.success('已删除')
    await loadData()
  } catch (e: any) {
    ElMessage.error('删除失败：' + (e?.message ?? 'unknown'))
  }
}

/** Pod：日志（可选补齐） */
const logs = reactive<{ open: boolean; title: string; content: string; row: WorkloadRow | null }>({
  open: false, title: '日志', content: '', row: null
})
async function openLogs(row: WorkloadRow) {
  logs.row = row
  logs.open = true
  logs.title = `日志 · ${row.name}`
  logs.content = '加载中...'
  try {
    const resp = await fetchPodLogs({ namespace: row.namespace, name: row.name, tailLines: 200 })
    logs.content = resp.logs
  } catch (e: any) {
    logs.content = ''
    ElMessage.error('获取日志失败：' + (e?.message ?? 'unknown'))
  }
}

/** ✅ 新建：YAML apply */
const create = reactive<{
  open: boolean
  kind: Kind
  namespace: string
  name: string
  image: string
  replicas: number
  yaml: string
  applying: boolean
}>({
  open: false,
  kind: 'deployment',
  namespace: 'default',
  name: 'demo-app',
  image: 'nginx:1.25',
  replicas: 1,
  yaml: '',
  applying: false,
})

function buildYamlTemplate(): string {
  const ns = create.namespace || 'default'
  const name = create.name || 'demo-app'
  const image = create.image || 'nginx:1.25'
  const replicas = Math.max(0, create.replicas || 1)

  if (create.kind === 'deployment') {
    return `apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${name}
  namespace: ${ns}
spec:
  replicas: ${replicas}
  selector:
    matchLabels:
      app: ${name}
  template:
    metadata:
      labels:
        app: ${name}
    spec:
      containers:
        - name: app
          image: ${image}
          ports:
            - containerPort: 80
`
  }

  if (create.kind === 'statefulset') {
    return `apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: ${name}
  namespace: ${ns}
spec:
  serviceName: ${name}
  replicas: ${replicas}
  selector:
    matchLabels:
      app: ${name}
  template:
    metadata:
      labels:
        app: ${name}
    spec:
      containers:
        - name: app
          image: ${image}
          ports:
            - containerPort: 80
`
  }

  // pod
  return `apiVersion: v1
kind: Pod
metadata:
  name: ${name}
  namespace: ${ns}
spec:
  containers:
    - name: app
      image: ${image}
      ports:
        - containerPort: 80
`
}

function handleCreateHint() {
  // ✅ 由占位改为真正新建入口
  create.open = true
  create.yaml = buildYamlTemplate()
}

watch(() => [create.kind, create.namespace, create.name, create.image, create.replicas], () => {
  if (!create.open) return
  create.yaml = buildYamlTemplate()
})

async function submitCreate() {
  if (!create.yaml.trim()) {
    ElMessage.warning('YAML 不能为空')
    return
  }
  create.applying = true
  try {
    const resp = await applyManifest({ yaml: create.yaml })
    if (resp.ok) {
      ElMessage.success('已应用到集群')
      create.open = false
      await loadData()
    } else {
      ElMessage.error('应用失败：' + (resp.stderr || resp.stdout || 'unknown'))
    }
  } catch (e: any) {
    ElMessage.error('应用失败：' + (e?.message ?? 'unknown'))
  } finally {
    create.applying = false
  }
}

/** 删除工作负载 */
async function confirmDeleteWorkload(row: WorkloadRow
) {
  if (row.kind === 'pod') return

  // StatefulSet 可选：是否连 PVC 一起删（危险）
  let deletePVC = false
  if (row.kind === 'statefulset'
) {
    try
 {
      await ElMessageBox.confirm
(
        `即将删除 StatefulSet：${row.name}
\n默认仅删除工作负载本体，不会删除 PVC。\n\n你要连同 PVC 一起清理吗？（危险操作）`,
        '删除确认'
,
        {
          type: 'warning'
,
          confirmButtonText: '连 PVC 一起删'
,
          cancelButtonText: '只删工作负载'
,
          distinguishCancelAndClose: true
,
        }
      )
      deletePVC = 
true
    } 
catch
 {
      deletePVC = 
false
    }
  } 
else
 {
    await ElMessageBox.confirm
(
      `确定彻底删除 Deployment：${row.name}
 吗？\n（会删除该工作负载并级联删除其 Pod/RS）`,
      '删除确认'
,
      { 
type: 'warning'
 }
    )
  }

  try
 {
    const resp = await deleteWorkload
({
      kind: row.kind as any
,
      namespace: row.namespace
,
      name: row.name
,
      deletePVC,
    })
    if (resp.ok
) {
      ElMessage.success('已删除工作负载'
)
      await loadData
()
    } 
else
 {
      ElMessage.error('删除失败：' + (resp.message || 'unknown'
))
    }
  } 
catch (e: any
) {
    ElMessage.error('删除失败：' + (e?.message ?? 'unknown'
))
  }
}


/** 批量：重启/扩缩容/删除 pods（你可按需继续接真实接口） */
async function handleBatchRestart() {
  if (selected.value.length === 0) return
  await ElMessageBox.confirm(`确定批量重启 ${selected.value.length} 个资源吗？`, '批量重启', { type: 'warning' })
  // 简化：循环调用（毕设够用）
  for (const r of selected.value) {
    if (r.kind === 'deployment' || r.kind === 'statefulset') {
      await restartWorkload({ kind: r.kind, namespace: r.namespace, name: r.name })
    }
  }
  ElMessage.success('已批量触发重启')
  await loadData()
}
async function handleBatchScale() {
  ElMessage.info('批量扩缩容：建议做一个弹窗输入 replicas（你需要我也可以补）')
}
async function handleBatchDeletePods() {
  if (selected.value.length === 0) return
  await ElMessageBox.confirm(`确定批量删除 ${selected.value.length} 个 Pod 吗？`, '批量删除', { type: 'warning' })
  for (const r of selected.value) {
    if (r.kind === 'pod') await deletePod({ namespace: r.namespace, name: r.name })
  }
  selected.value = []
  ElMessage.success('已批量删除')
  await loadData()
}

/** 内联状态组件保持不变 */
const StatusPill = defineComponent({
  name: 'StatusPill',
  props: { status: { type: String as () => RowStatus, required: true } },
  setup(props) {
    const text = computed(() => {
      if (props.status === 'running') return '运行中'
      if (props.status === 'warning') return '异常'
      if (props.status === 'failed') return '失败'
      return '未知'
    })
    return () =>
      h('span', { class: ['pill', `pill-${props.status}`] }, [
        h('span', { class: 'dot' }),
        text.value,
      ])
  },
})
</script>

<style scoped>
.workloads-page {
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
  font-weight: 700;
  color: #111827;
}
.page-subtitle {
  font-size: 12px;
  color: #6b7280;
  margin-top: 2px;
}
.head-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

/* 卡片 */
.card {
  border-radius: 12px;
  border: 1px solid #e5e7eb;
}

/* Tabs 行 */
.tabs-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
}
.tabs :deep(.el-tabs__header) {
  margin: 0;
}
.filters {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.w160 {
  width: 160px;
}
.w140 {
  width: 140px;
}
.w260 {
  width: 260px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 10px 0 12px;
  gap: 10px;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.table {
  border-radius: 10px;
  overflow: hidden;
}

.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

/* 小样式 */
.muted {
  color: #6b7280;
  font-size: 12px;
}
.mr6 {
  margin-right: 6px;
}
.ml8 {
  margin-left: 8px;
}
.mb8 {
  margin-bottom: 8px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

/* 名称单元格 */
.name-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.name {
  font-weight: 600;
  color: #111827;
}
.sub {
  margin-top: 2px;
}

/* 操作按钮 */
.ops {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* 抽屉 */
.drawer-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.kv {
  display: grid;
  grid-template-columns: 110px 1fr;
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
  word-break: break-word;
}
.hint {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.6;
}

/* 扩缩容 */
.scale-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* 状态 pill */
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

.pill-running {
  color: #059669;
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.25);
}
.pill-warning {
  color: #d97706;
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.25);
}
.pill-failed {
  color: #dc2626;
  background: rgba(239, 68, 68, 0.1);
  border-color: rgba(239, 68, 68, 0.25);
}
.pill-unknown {
  color: #64748b;
  background: rgba(100, 116, 139, 0.1);
  border-color: rgba(100, 116, 139, 0.25);
}

@media (max-width: 1024px) {
  .w160,
  .w140,
  .w260 {
    width: 100%;
  }
  .head-actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
