<template>
  <div class="ns-page">
    <!-- 顶部 -->
    <div class="page-head">
      <div>
        <div class="page-title">Namespaces</div>
        <div class="page-subtitle">
          真实集群 Namespace 列表（k3s/k8s），支持创建 / 标签编辑 / 安全删除（系统 ns 禁删）
        </div>
      </div>

      <div class="head-actions">
        <el-button :loading="loading" @click="refresh">
          <el-icon class="mr6"><Refresh /></el-icon>刷新
        </el-button>

        <el-button type="primary" @click="openCreate">
          <el-icon class="mr6"><Plus /></el-icon>创建 Namespace
        </el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="card">
      <div class="filters">
        <el-input
          v-model="filters.keyword"
          placeholder="搜索：Namespace / 标签 key=value"
          clearable
          class="w320"
          @keyup.enter="applyFilters"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>

        <el-select v-model="filters.system" placeholder="类型" clearable class="w160">
          <el-option label="系统" value="system" />
          <el-option label="普通" value="normal" />
        </el-select>

        <el-select v-model="filters.managed" placeholder="平台接管" clearable class="w160">
          <el-option label="已接管" value="managed" />
          <el-option label="未接管" value="unmanaged" />
        </el-select>

        <el-button type="primary" @click="applyFilters">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <!-- 表格 -->
      <el-table :data="pagedRows" stripe height="560" v-loading="loading" class="table">
        <el-table-column prop="name" label="Namespace" min-width="240" fixed="left">
          <template #default="{ row }">
            <div class="name-cell">
              <span class="name mono">{{ row.name }}</span>
              <el-tag v-if="row.system" size="small" type="warning" effect="plain" class="tag">system</el-tag>
              <el-tag v-if="row.managed" size="small" type="success" effect="plain" class="tag">managed</el-tag>
            </div>
            <div class="sub muted">
              Phase：{{ row.phase || '-' }} · 创建于 {{ row.createdAt || '-' }}
            </div>
            <div v-if="row.managedByTenantId" class="sub muted">
              TenantID：<span class="mono">{{ row.managedByTenantId }}</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="Labels" min-width="360">
          <template #default="{ row }">
            <div class="labels">
              <el-tag
                v-for="(v,k) in row.labels"
                :key="k"
                size="small"
                type="info"
                effect="plain"
                class="tag"
              >
                {{ k }}={{ v }}
              </el-tag>
              <span v-if="Object.keys(row.labels||{}).length===0" class="muted">无</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <div class="ops">
              <el-button size="small" @click="openEditLabels(row)">编辑标签</el-button>

              <el-button
                size="small"
                type="danger"
                plain
                :disabled="row.system"
                @click="doDelete(row)"
              >
                删除
              </el-button>

              <el-dropdown @command="(cmd:string)=>handleMore(cmd,row)">
                <el-button size="small">
                  更多 <el-icon class="ml6"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="markManaged">
                      {{ row.managed ? '标记为未接管（占位）' : '标记为平台接管（占位）' }}
                    </el-dropdown-item>
                    <el-dropdown-item command="copyName">复制名称</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
            <div v-if="row.system" class="hint mt6">系统 Namespace 禁删（后端会拦截）</div>
          </template>
        </el-table-column>
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

    <!-- 创建 -->
    <el-dialog v-model="create.open" title="创建 Namespace" width="680px">
      <el-form label-width="140px">
        <el-form-item label="Namespace 名称">
          <el-input v-model="create.form.name" placeholder="例如 ns-acme / dev" />
        </el-form-item>

        <el-form-item label="初始标签（可选）">
          <el-input
            v-model="create.form.labelsText"
            type="textarea"
            :rows="4"
            placeholder="每行一个 key=value，例如：&#10;env=dev&#10;owner=acme"
          />
          <div class="hint mt6">后端幂等：已存在则直接返回（不会报错）。</div>
        </el-form-item>

        <el-form-item label="平台接管">
          <el-switch v-model="create.form.managed" />
          <div class="hint ml10">写入 sqlite registry（用于审计/保护/归属）</div>
        </el-form-item>

        <el-form-item label="归属 TenantID（可选）">
          <el-input v-model="create.form.managedByTenantId" placeholder="例如 t-1001（可空）" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="create.open=false">取消</el-button>
        <el-button type="primary" :loading="create.submitting" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑标签 -->
    <el-dialog v-model="labelsDlg.open" title="编辑 Namespace Labels" width="760px">
      <div class="muted mb10">
        Namespace：<span class="mono">{{ labelsDlg.name }}</span>
      </div>

      <el-table :data="labelsDlg.kvList" stripe height="320">
        <el-table-column prop="k" label="Key" width="260">
          <template #default="{ row }">
            <el-input v-model="row.k" placeholder="例如 env" />
          </template>
        </el-table-column>
        <el-table-column prop="v" label="Value">
          <template #default="{ row }">
            <el-input v-model="row.v" placeholder="例如 prod" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ $index }">
            <el-button size="small" type="danger" plain @click="labelsDlg.kvList.splice($index,1)">
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="mt10">
        <el-button @click="labelsDlg.kvList.push({k:'',v:''})">
          <el-icon class="mr6"><Plus /></el-icon>新增一行
        </el-button>
      </div>

      <div class="hint mt10">
        注意：这里是 merge patch —— 会合并 labels；想“清空”可把某些 key 设为空字符串（按你后端策略决定）。
      </div>

      <template #footer>
        <el-button @click="labelsDlg.open=false">取消</el-button>
        <el-button type="primary" :loading="labelsDlg.submitting" @click="submitLabels">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Search, ArrowDown } from '@element-plus/icons-vue'

import type { NamespaceItem } from '@/api/namespaces'
import { fetchNamespaces, createNamespace, patchNamespaceLabels, deleteNamespace } from '@/api/namespaces'

const loading = ref(false)
const rows = ref<NamespaceItem[]>([])

const filters = reactive({
  keyword: '',
  system: '' as '' | 'system' | 'normal',
  managed: '' as '' | 'managed' | 'unmanaged',
})

const pagination = reactive({ page: 1, pageSize: 20 })

const filteredRows = computed(() => {
  const kw = filters.keyword.trim().toLowerCase()
  return rows.value
    .filter((r) => {
      if (filters.system === 'system') return !!r.system
      if (filters.system === 'normal') return !r.system
      return true
    })
    .filter((r) => {
      if (filters.managed === 'managed') return !!r.managed
      if (filters.managed === 'unmanaged') return !r.managed
      return true
    })
    .filter((r) => {
      if (!kw) return true
      const hay = [
        r.name,
        Object.entries(r.labels || {})
          .map(([k, v]) => `${k}=${v}`)
          .join(' '),
      ]
        .join(' ')
        .toLowerCase()
      return hay.includes(kw)
    })
})

const pagedRows = computed(() => {
  const start = (pagination.page - 1) * pagination.pageSize
  return filteredRows.value.slice(start, start + pagination.pageSize)
})

watch(
  () => [filters.keyword, filters.system, filters.managed],
  () => (pagination.page = 1)
)

function applyFilters() {
  pagination.page = 1
  refresh()
}

function resetFilters() {
  filters.keyword = ''
  filters.system = ''
  filters.managed = ''
  pagination.page = 1
  refresh()
}

async function refresh() {
  loading.value = true
  try {
    const resp = await fetchNamespaces({ keyword: filters.keyword.trim() || undefined })
    rows.value = resp.items || []
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '刷新失败')
  } finally {
    loading.value = false
  }
}

onMounted(() => refresh())

/** 创建 */
const create = reactive({
  open: false,
  submitting: false,
  form: {
    name: '',
    labelsText: '',
    managed: true,
    managedByTenantId: '',
  },
})

function openCreate() {
  create.open = true
  create.form.name = ''
  create.form.labelsText = ''
  create.form.managed = true
  create.form.managedByTenantId = ''
}

function parseLabels(text: string): Record<string, string> {
  const out: Record<string, string> = {}
  const lines = (text || '').split('\n').map(s => s.trim()).filter(Boolean)
  for (const line of lines) {
    const idx = line.indexOf('=')
    if (idx <= 0) continue
    const k = line.slice(0, idx).trim()
    const v = line.slice(idx + 1).trim()
    if (k) out[k] = v
  }
  return out
}

async function submitCreate() {
  const name = create.form.name.trim()
  if (!name) return ElMessage.warning('请输入 Namespace 名称')

  create.submitting = true
  try {
    const labels = parseLabels(create.form.labelsText)
    const resp = await createNamespace({
      name,
      labels,
      managed: create.form.managed,
      managedByTenantId: create.form.managedByTenantId.trim() || undefined,
    })
    ElMessage.success('已创建（或已存在）')
    create.open = false

    // 更新列表：简单起见直接刷新（确保 phase/createdAt 最新）
    await refresh()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '创建失败')
  } finally {
    create.submitting = false
  }
}

/** 编辑 labels */
const labelsDlg = reactive<{
  open: boolean
  submitting: boolean
  name: string
  kvList: Array<{ k: string; v: string }>
}>({
  open: false,
  submitting: false,
  name: '',
  kvList: [],
})

function openEditLabels(row: NamespaceItem) {
  labelsDlg.open = true
  labelsDlg.submitting = false
  labelsDlg.name = row.name
  labelsDlg.kvList = Object.entries(row.labels || {}).map(([k, v]) => ({ k, v }))
  if (labelsDlg.kvList.length === 0) labelsDlg.kvList = [{ k: '', v: '' }]
}

async function submitLabels() {
  const name = labelsDlg.name
  const obj: Record<string, string> = {}
  for (const kv of labelsDlg.kvList) {
    const k = kv.k.trim()
    const v = kv.v.trim()
    if (!k) continue
    obj[k] = v
  }

  labelsDlg.submitting = true
  try {
    await patchNamespaceLabels(name, obj)
    ElMessage.success('已保存 labels')
    labelsDlg.open = false
    await refresh()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  } finally {
    labelsDlg.submitting = false
  }
}

/** 删除 */
async function doDelete(row: NamespaceItem) {
  await ElMessageBox.confirm(
    `确定删除 Namespace ${row.name} 吗？\n系统 Namespace 禁删；已绑定租户的 Namespace（若后端开启 block_if_bound）也会被拦截。`,
    '确认删除',
    { type: 'warning' }
  )

  try {
    await deleteNamespace(row.name, true)
    ElMessage.success('已提交删除（或已不存在）')
    await refresh()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
  }
}

async function handleMore(cmd: string, row: NamespaceItem) {
  if (cmd === 'copyName') {
    try {
      await navigator.clipboard.writeText(row.name)
      ElMessage.success('已复制')
    } catch {
      ElMessage.warning('复制失败（浏览器权限限制）')
    }
    return
  }

  if (cmd === 'markManaged') {
    // 这里留给你后续扩展：单独做 registry 标记接口（不改 k8s）
    ElMessage.info('占位：后续可加 /api/namespaces/{name}/registry 接口')
  }
}
</script>

<style scoped>
.ns-page { display: flex; flex-direction: column; gap: 14px; }

.page-head {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
}
.page-title { font-size: 16px; font-weight: 800; color: #111827; }
.page-subtitle { font-size: 12px; color: #6b7280; margin-top: 2px; }
.head-actions { display: flex; gap: 10px; align-items: center; }

.card { border-radius: 12px; border: 1px solid #e5e7eb; }

.filters {
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-bottom: 10px;
}
.w320 { width: 320px; }
.w160 { width: 160px; }

.table { border-radius: 10px; overflow: hidden; }
.pager { display: flex; justify-content: flex-end; padding-top: 12px; }

.name-cell { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.name { font-weight: 800; color: #111827; }
.labels { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { border-radius: 999px; }
.ops { display: flex; gap: 8px; flex-wrap: wrap; }
.hint { color: #6b7280; font-size: 12px; }
.muted { color: #6b7280; font-size: 12px; }
.sub { margin-top: 2px; }
.mt6 { margin-top: 6px; }
.mr6 { margin-right: 6px; }
.ml6 { margin-left: 6px; }
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

@media (max-width: 1024px) {
  .w320, .w160 { width: 100%; }
}
</style>
