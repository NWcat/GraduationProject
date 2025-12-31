<!-- src/views/Nodes/NodeList.vue -->
<template>
  <div class="node-page">
    <!-- 顶部概览 -->
    <el-card shadow="never" class="section-card">
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
          <div class="summary-label">控制平面</div>
          <div class="summary-value">{{ summary.controlPlane }}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">Worker</div>
          <div class="summary-value">{{ summary.worker }}</div>
        </div>
      </div>
    </el-card>

    <!-- 查询栏 -->
    <el-card shadow="never" class="section-card">
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

          <el-select
            v-model="filters.status"
            class="toolbar-item"
            placeholder="状态"
            clearable
            @change="applyFilters"
          >
            <el-option label="Ready" value="Ready" />
            <el-option label="NotReady" value="NotReady" />
          </el-select>

          <el-select
            v-model="filters.role"
            class="toolbar-item"
            placeholder="角色"
            clearable
            @change="applyFilters"
          >
            <el-option label="control-plane" value="control-plane" />
            <el-option label="worker" value="worker" />
          </el-select>
        </div>

        <div class="toolbar-right">
          <el-button @click="resetFilters" plain>
            重置
          </el-button>
          <el-button type="primary" @click="refresh">
            <el-icon class="mr-6"><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <!-- 表格 -->
      <el-table
        v-loading="loading"
        :data="pagedRows"
        size="default"
        class="node-table"
        :header-cell-style="{ background: '#f9fafb', color: '#374151' }"
      >
        <el-table-column type="index" width="60" label="#" />

        <el-table-column prop="name" label="节点名称" min-width="180">
          <template #default="{ row }">
            <div class="node-name">
              <span class="node-dot" :class="row.status === 'Ready' ? 'dot-ok' : 'dot-bad'"></span>
              <span class="node-name-text">{{ row.name }}</span>
              <el-tag v-if="row.role === 'control-plane'" size="small" class="tag-muted">
                control-plane
              </el-tag>
              <el-tag v-else size="small" class="tag-muted">
                worker
              </el-tag>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="ip" label="IP" width="150" />

        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.status === 'Ready' ? 'success' : 'danger'"
              effect="light"
            >
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="kubeletVersion" label="Kubelet" min-width="140" />
        <el-table-column prop="osImage" label="OS" min-width="180" show-overflow-tooltip />

        <el-table-column label="CPU(核)" width="120">
          <template #default="{ row }">
            <div class="metric">
              <span class="metric-strong">{{ row.cpuUsed }}</span>
              <span class="metric-muted">/ {{ row.cpuTotal }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="内存(GB)" width="140">
          <template #default="{ row }">
            <div class="metric">
              <span class="metric-strong">{{ row.memUsed }}</span>
              <span class="metric-muted">/ {{ row.memTotal }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="Pod" width="120">
          <template #default="{ row }">
            <div class="metric">
              <span class="metric-strong">{{ row.podUsed }}</span>
              <span class="metric-muted">/ {{ row.podCapacity }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" text @click="openDetail(row)">详情</el-button>
            <el-button text @click="copyText(row.ip)">复制IP</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
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
    <el-drawer
      v-model="detail.visible"
      size="420px"
      title="节点详情"
      destroy-on-close
    >
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, Refresh } from '@element-plus/icons-vue'
import { fetchNodes, type NodeRow } from '@/api/nodes'

const loading = ref(false)

const filters = reactive({
  keyword: '',
  status: '' as '' | 'Ready' | 'NotReady',
  role: '' as '' | 'control-plane' | 'worker',
})

const page = reactive({
  current: 1,
  size: 10,
})

// ✅ 去掉假数据：初始化为空
const rows = ref<NodeRow[]>([])

async function load() {
  loading.value = true
  try {
    const data = await fetchNodes()
    rows.value = data || []
  } catch (e: any) {
    ElMessage.error('获取节点数据失败：' + (e?.message ?? 'unknown'))
  } finally {
    loading.value = false
  }
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
  const controlPlane = all.filter((n) => n.role === 'control-plane').length
  const worker = all.filter((n) => n.role === 'worker').length
  return { total, ready, notReady, controlPlane, worker }
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

onMounted(load)
</script>

<style scoped>
.node-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 通用卡片 */
.section-card {
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  background: #ffffff;
}

/* 标题区 */
.section-header {
  margin-bottom: 10px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}
.section-subtitle {
  font-size: 12px;
  color: #9ca3af;
}

/* 顶部概览卡片 */
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}
.summary-card {
  padding: 10px 12px;
  border-radius: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
}
.summary-label {
  font-size: 12px;
  color: #6b7280;
}
.summary-value {
  margin-top: 4px;
  font-size: 20px;
  font-weight: 700;
  color: #111827;
}
.summary-value.ok {
  color: #059669;
}
.summary-value.danger {
  color: #dc2626;
}

/* 工具栏 */
.toolbar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.toolbar-item {
  width: 260px;
}
@media (max-width: 900px) {
  .toolbar-item {
    width: 100%;
  }
  .toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .toolbar-right {
    justify-content: flex-end;
  }
}

/* 表格 */
.node-table {
  border-radius: 10px;
  overflow: hidden;
}

.node-name {
  display: flex;
  align-items: center;
  gap: 8px;
}
.node-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  display: inline-block;
}
.dot-ok {
  background: #22c55e;
}
.dot-bad {
  background: #ef4444;
}
.node-name-text {
  font-weight: 600;
  color: #111827;
}
.tag-muted {
  margin-left: 6px;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  color: #4b5563;
}

.metric {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.metric-strong {
  font-weight: 700;
  color: #111827;
}
.metric-muted {
  font-size: 12px;
  color: #9ca3af;
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
  color: #6b7280;
}

/* 抽屉 */
.drawer-block {
  margin-bottom: 16px;
}
.drawer-title {
  font-size: 13px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 8px;
}

.mr-6 {
  margin-right: 6px;
}
</style>
