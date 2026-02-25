<template>
  <div class="page">
    <div class="page-head">
      <div>
        <div class="page-title">Events</div>
        <div class="page-subtitle">K8s 事件列表（分页/筛选）</div>
      </div>
      <div class="actions">
        <el-button :loading="loading" @click="refresh">刷新</el-button>
      </div>
    </div>

    <el-card shadow="never" class="card">
      <div class="filters">
        <el-input v-model="filters.namespace" class="w220" placeholder="namespace（可选）" clearable />
        <el-button type="primary" :loading="loading" @click="refresh">查询</el-button>
      </div>

      <el-table :data="rows" stripe v-loading="loading" height="560">
        <el-table-column prop="last_timestamp" label="Time" width="180" />
        <el-table-column prop="type" label="Type" width="120" />
        <el-table-column prop="reason" label="Reason" width="160" />
        <el-table-column prop="message" label="Message" min-width="320" />
        <el-table-column label="Object" width="220">
          <template #default="{ row }">
            <div class="obj">
              <div class="obj-main">{{ row.kind }} {{ row.namespace }}/{{ row.name }}</div>
              <el-button size="small" @click="jumpTo(row)">跳转</el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-button :disabled="!nextToken" @click="loadMore">加载更多</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchEvents, type K8sEventItem } from '@/api/events'
import { onMounted, onUnmounted, watch } from 'vue'

const router = useRouter()
const loading = ref(false)
const rows = ref<K8sEventItem[]>([])
const nextToken = ref('')

const filters = reactive({
  namespace: ''
})



async function refresh() {
  rows.value = []
  nextToken.value = ''
  await loadMore()
}

async function loadMore() {
  loading.value = true
  try {
    const { data } = await fetchEvents({
      namespace: filters.namespace || undefined,
      limit: 100,
      continue: nextToken.value || undefined
    })
    rows.value = rows.value.concat(data.items || [])
    nextToken.value = data.continue || ''
  } finally {
    loading.value = false
  }
}

function jumpTo(row: K8sEventItem) {
  const kind = (row.kind || '').toLowerCase()
  router.push({
    path: '/workloads',
    query: { kind: kind || 'pod', namespace: row.namespace, keyword: row.name }
  })
}

const autoRefresh = ref(true)
let timer: any = null

function startPoll() {
  stopPoll()
  timer = setInterval(() => {
    if (!autoRefresh.value) return
    refresh() // 你的刷新函数
  }, 60000)
}

function stopPoll() {
  if (timer) clearInterval(timer)
  timer = null
}

onMounted(() => startPoll())
onUnmounted(() => stopPoll())

watch(autoRefresh, (v) => {
  if (v) startPoll()
  else stopPoll()
})

// 可选：切后台就暂停，切回来再拉一次
document.addEventListener('visibilitychange', () => {
  if (document.hidden) stopPoll()
  else {
    startPoll()
    refresh()
  }
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
.card {
  border-radius: 12px;
}
.filters {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.w220 {
  width: 220px;
}
.obj {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.obj-main {
  font-size: 12px;
}
.pager {
  margin-top: 10px;
  display: flex;
  justify-content: center;
}
</style>
