<template>
  <div class="page">
    <div class="page-head">
      <div>
        <div class="page-title">任务中心</div>
        <div class="page-subtitle">统一追踪长耗时任务状态</div>
      </div>
      <div class="actions">
        <el-button type="danger" plain @click="handleBatchDelete" :disabled="selectedTaskIds.length === 0">删除选中</el-button>
        <el-button type="danger" @click="handleDeleteAll">清空所有</el-button>
        <el-button :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </div>

    <el-card shadow="never" class="card">
      <div class="filters">
        <el-select v-model="filters.status" clearable class="w160" placeholder="状态">
          <el-option label="PENDING" value="PENDING" />
          <el-option label="RUNNING" value="RUNNING" />
          <el-option label="SUCCESS" value="SUCCESS" />
          <el-option label="FAILED" value="FAILED" />
          <el-option label="RESTRICTED" value="RESTRICTED" />
          <el-option label="UNKNOWN" value="UNKNOWN" />
        </el-select>
        <el-input v-model="filters.type" clearable class="w220" placeholder="类型（如 ai_forecast）" />
        <el-button type="primary" :loading="loading" @click="refresh">查询</el-button>
      </div>

      <el-table :data="rows" stripe v-loading="loading" height="560" @selection-change="handleSelectionChange">
        <el-table-column type="selection" width="55" />
        <el-table-column prop="task_id" label="Task ID" min-width="220" />
        <el-table-column prop="type" label="Type" width="160" />
        <el-table-column prop="status" label="Status" width="120" />
        <el-table-column label="Progress" width="120">
          <template #default="{ row }">
            <span>{{ formatPct(row.progress) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Updated" width="180">
          <template #default="{ row }">
            <span>{{ formatTs(row.updated_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Error" min-width="220">
          <template #default="{ row }">
            <span class="mono">{{ row.error || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <div class="actions-group">
              <el-button size="small" @click="openDetail(row)">详情</el-button>
              <el-button
                v-if="row.status === 'RUNNING'"
                size="small"
                type="warning"
                @click="handlePause(row)"
              >
                暂停
              </el-button>
              <el-button
                v-if="row.status === 'PAUSED'"
                size="small"
                type="success"
                @click="handleResume(row)"
              >
                恢复
              </el-button>
              <el-button
                v-if="['PENDING', 'RUNNING'].includes(row.status)"
                size="small"
                type="danger"
                @click="handleCancel(row)"
              >
                取消
              </el-button>
              <el-button
                size="small"
                type="info"
                @click="handleDelete(row)"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="detailOpen" width="720px">
      <template #header>
        <div class="dialog-title">任务详情</div>
      </template>
      <div v-if="detail">
        <div class="detail-row"><b>Task ID:</b> {{ detail.task_id }}</div>
        <div class="detail-row"><b>Type:</b> {{ detail.type }}</div>
        <div class="detail-row"><b>Status:</b> {{ detail.status }}</div>
        <div class="detail-row"><b>Updated:</b> {{ formatTs(detail.updated_at) }}</div>
        <div class="detail-row"><b>Error:</b> {{ detail.error || '-' }}</div>
        <div class="detail-row">
          <b>Result:</b>
          <pre class="json">{{ pretty(detail.result) }}</pre>
        </div>
      </div>
      <el-empty v-else description="暂无详情" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchTasks, fetchTaskDetail, type TaskItem } from '@/api/tasks'
import {
  cancelTask,
  pauseTask,
  resumeTask,
  deleteTask,
  deleteTasksBatch,
  deleteAllTasks,
} from '@/api/tasks_advanced'

const loading = ref(false)
const rows = ref<TaskItem[]>([])
const detailOpen = ref(false)
const detail = ref<(TaskItem & { result?: any }) | null>(null)
const selectedTaskIds = ref<string[]>([])
let timer: number | null = null

const filters = reactive({
  status: '',
  type: ''
})

function handleSelectionChange(selectedItems: TaskItem[]) {
  selectedTaskIds.value = selectedItems.map(item => item.task_id)
}

function formatTs(ts: number) {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleString()
}

function formatPct(v: number) {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '-'
  return `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%`
}

function pretty(v: any) {
  try {
    return JSON.stringify(v ?? {}, null, 2)
  } catch {
    return String(v)
  }
}

async function refresh() {
  loading.value = true
  try {
    const { data } = await fetchTasks({
      status: filters.status || undefined,
      type: filters.type || undefined,
      limit: 50,
      offset: 0
    })
    rows.value = data.items || []
  } finally {
    loading.value = false
  }
}

async function openDetail(row: TaskItem) {
  const { data } = await fetchTaskDetail(row.task_id)
  detail.value = data.task
  detailOpen.value = true
}

async function handleCancel(row: TaskItem) {
  try {
    await ElMessageBox.confirm(
      `确认取消任务 ${row.task_id} 吗？`,
      '确认取消',
      {
        confirmButtonText: '确认',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    await cancelTask(row.task_id)
    ElMessage.success('任务已取消')
    await refresh()
  } catch (err: any) {
    if (err.response?.data?.detail) {
      ElMessage.error(err.response.data.detail)
    } else if (err !== 'cancel') {
      ElMessage.error('取消任务失败')
    }
  }
}

async function handlePause(row: TaskItem) {
  try {
    await pauseTask(row.task_id)
    ElMessage.success('任务已暂停')
    await refresh()
  } catch (err: any) {
    if (err.response?.data?.detail) {
      ElMessage.error(err.response.data.detail)
    } else {
      ElMessage.error('暂停任务失败')
    }
  }
}

async function handleResume(row: TaskItem) {
  try {
    await resumeTask(row.task_id)
    ElMessage.success('任务已恢复')
    await refresh()
  } catch (err: any) {
    if (err.response?.data?.detail) {
      ElMessage.error(err.response.data.detail)
    } else {
      ElMessage.error('恢复任务失败')
    }
  }
}

async function handleDelete(row: TaskItem) {
  try {
    await ElMessageBox.confirm(
      `确认删除任务 ${row.task_id} 吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'danger'
      }
    )
    await deleteTask(row.task_id, false)
    ElMessage.success('任务已删除')
    await refresh()
  } catch (err: any) {
    if (err.response?.data?.detail) {
      ElMessage.error(err.response.data.detail)
    } else if (err !== 'cancel') {
      ElMessage.error('删除任务失败')
    }
  }
}

async function handleBatchDelete() {
  if (selectedTaskIds.value.length === 0) {
    ElMessage.warning('请至少选择一个任务')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${selectedTaskIds.value.length} 个任务吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
        type: 'danger'
      }
    )
    await deleteTasksBatch(selectedTaskIds.value)
    ElMessage.success(`成功删除 ${selectedTaskIds.value.length} 个任务`)
    await refresh()
  } catch (err: any) {
    if (err.response?.data?.detail) {
      ElMessage.error(err.response.data.detail)
    } else if (err !== 'cancel') {
      ElMessage.error('批量删除任务失败')
    }
  }
}

async function handleDeleteAll() {
  try {
    await ElMessageBox.confirm(
      '确认清空所有任务记录吗？此操作不可恢复。',
      '确认清空',
      {
        confirmButtonText: '确认清空',
        cancelButtonText: '取消',
        type: 'danger'
      }
    )
    const { data } = await deleteAllTasks()
    ElMessage.success(`成功清空 ${data.data.deleted_count} 条任务记录`)
    await refresh()
  } catch (err: any) {
    if (err.response?.data?.detail) {
      ElMessage.error(err.response.data.detail)
    } else if (err !== 'cancel') {
      ElMessage.error('清空任务失败')
    }
  }
}


onMounted(() => {
  refresh()
  timer = window.setInterval(refresh, 5000)
})

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}
.page-title {
  font-size: 18px;
  font-weight: 800;
}
.page-subtitle {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}
.actions {
  display: flex;
  gap: 8px;
}
.actions-group {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.actions-group :deep(.el-button) {
  margin: 2px;
}
.card {
  border-radius: 12px;
}
.filters {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.w160 {
  width: 160px;
}
.w220 {
  width: 220px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 12px;
}
.dialog-title {
  font-weight: 700;
}
.detail-row {
  margin-bottom: 8px;
  font-size: 13px;
}
.json {
  background: #0b1220;
  color: #e5e7eb;
  padding: 8px;
  border-radius: 8px;
  font-size: 12px;
  max-height: 260px;
  overflow: auto;
}
</style>