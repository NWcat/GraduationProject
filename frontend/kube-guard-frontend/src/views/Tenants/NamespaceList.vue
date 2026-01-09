<template>
  <div class="tenant-page">
    <!-- 顶部：标题 + 操作 -->
    <div class="page-head">
      <div>
        <div class="page-title">租户与命名空间</div>
        <div class="page-subtitle">
          租户（平台实体）= 用户/角色 + 资源域绑定（Namespace）+ 配额/标签等策略（占位）
        </div>
      </div>

      <div class="head-actions">
        <el-button :loading="loading" @click="refresh">
          <el-icon class="mr6"><Refresh /></el-icon>
          刷新
        </el-button>

        <el-button type="primary" @click="openCreate">
          <el-icon class="mr6"><Plus /></el-icon>
          创建租户
        </el-button>
      </div>
    </div>

    <!-- 筛选 -->
    <el-card shadow="never" class="card">
      <div class="filters">
        <el-input
          v-model="filters.keyword"
          placeholder="搜索：租户名 / 管理员账号 / Namespace"
          clearable
          class="w320"
          @keyup.enter="applyFilters"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>

        <el-select v-model="filters.status" placeholder="状态" clearable class="w160">
          <el-option label="正常" value="active" />
          <el-option label="禁用" value="disabled" />
          <el-option label="异常" value="warning" />
        </el-select>

        <el-button type="primary" @click="applyFilters">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <!-- 表格 -->
      <el-table
        :data="pagedRows"
        stripe
        class="table"
        height="560"
        v-loading="loading"
      >
        <el-table-column prop="name" label="租户" min-width="220" fixed="left">
          <template #default="{ row }">
            <div class="name-cell">
              <span class="name">{{ row.name }}</span>
              <StatusPill class="ml8" :status="row.status" />
            </div>
            <div class="sub muted">
              ID: <span class="mono">{{ row.id }}</span>
              · 创建于 {{ row.createdAt }}
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="adminUser" label="租户管理员账号" min-width="200">
          <template #default="{ row }">
            <div class="mono">{{ row.adminUser }}</div>
            <div class="sub muted">角色：Tenant Admin</div>
          </template>
        </el-table-column>

        <el-table-column label="绑定的 Namespace" min-width="220">
          <template #default="{ row }">
            <div class="ns-badges">
              <el-tag
                v-for="ns in row.namespaces"
                :key="ns"
                size="small"
                effect="plain"
                class="tag"
              >
                {{ ns }}
              </el-tag>
              <span v-if="row.namespaces.length === 0" class="muted">未绑定</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="配额（占位）" width="180">
          <template #default="{ row }">
            <div class="muted">
              CPU {{ row.quota.cpu }} / MEM {{ row.quota.memory }}
            </div>
            <div class="sub muted">后端接 ResourceQuota</div>
          </template>
        </el-table-column>

        <el-table-column label="标签" min-width="220">
          <template #default="{ row }">
            <div class="ns-badges">
              <el-tag
                v-for="(v, k) in row.labels"
                :key="k"
                size="small"
                type="info"
                effect="plain"
                class="tag"
              >
                {{ k }}={{ v }}
              </el-tag>
              <span v-if="Object.keys(row.labels).length === 0" class="muted">无</span>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="340" fixed="right">
          <template #default="{ row }">
            <div class="ops">
              <el-button size="small" @click="goDetail(row)">管理</el-button>

              <el-button size="small" @click="openBindNs(row)">绑定 Namespace</el-button>

              <el-button size="small" @click="openEditLabels(row)">编辑标签</el-button>

              <el-dropdown @command="(cmd:string)=>handleMore(cmd,row)">
                <el-button size="small">
                  更多 <el-icon class="ml6"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="resetPwd">重置管理员密码</el-dropdown-item>
                    <el-dropdown-item command="toggle">
                      {{ row.status === 'disabled' ? '启用租户' : '禁用租户' }}
                    </el-dropdown-item>
                    <el-dropdown-item command="delete" divided>删除租户</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
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

    <!-- 创建租户 -->
    <el-dialog v-model="create.open" title="创建租户" width="760px">
      <div class="dlg-grid">
        <el-form label-width="140px" class="form">
          <el-form-item label="租户名称">
            <el-input v-model="create.form.tenantName" placeholder="例如：acme / dev-team" />
          </el-form-item>

          <el-form-item label="绑定 Namespace（可选）">
            <el-select v-model="create.form.bindNamespace" placeholder="选择或输入" filterable allow-create clearable>
              <el-option v-for="ns in allNamespaceOptions" :key="ns" :label="ns" :value="ns" />
            </el-select>
            <div class="hint">
              建议命名：<span class="mono">ns-租户标识</span>（后端可自动创建 Namespace）
            </div>
          </el-form-item>

          <el-divider />

          <el-form-item label="创建租户管理员账号">
            <el-switch v-model="create.form.createAdminUser" />
            <div class="hint ml10">开启后会创建平台用户，并自动绑定 RBAC（占位）</div>
          </el-form-item>

          <template v-if="create.form.createAdminUser">
            <el-form-item label="管理员用户名">
              <el-input v-model="create.form.adminUsername" placeholder="例如：acme-admin" />
            </el-form-item>

            <el-form-item label="临时密码策略">
              <el-radio-group v-model="create.form.pwdMode">
                <el-radio label="auto">自动生成</el-radio>
                <el-radio label="manual">手动输入</el-radio>
              </el-radio-group>
            </el-form-item>

            <el-form-item v-if="create.form.pwdMode === 'manual'" label="临时密码">
              <el-input v-model="create.form.tempPassword" show-password placeholder="输入一次性临时密码" />
            </el-form-item>

            <el-form-item label="首登强制改密">
              <el-switch v-model="create.form.mustChangePassword" />
            </el-form-item>
          </template>

          <el-divider />

          <el-form-item label="配额（占位）">
            <div class="quota-row">
              <el-input v-model="create.form.quotaCpu" placeholder="CPU 例如 8" class="w160" />
              <el-input v-model="create.form.quotaMem" placeholder="内存 例如 16Gi" class="w160" />
              <span class="hint">后端对接 ResourceQuota / LimitRange</span>
            </div>
          </el-form-item>
        </el-form>

        <div class="side-preview">
          <div class="preview-title">将创建</div>
          <ul class="preview-list">
            <li>Tenant：<span class="mono">{{ create.form.tenantName || '-' }}</span></li>
            <li>
              Namespace：
              <span class="mono">{{ create.form.bindNamespace || '（不绑定）' }}</span>
            </li>
            <li>
              管理员账号：
              <span class="mono">
                {{ create.form.createAdminUser ? (create.form.adminUsername || '-') : '（不创建）' }}
              </span>
            </li>
            <li>配额：CPU <span class="mono">{{ create.form.quotaCpu || '-' }}</span> / MEM <span class="mono">{{ create.form.quotaMem || '-' }}</span></li>
            <li>RBAC：<span class="muted">占位（后端绑定 RoleBinding）</span></li>
          </ul>

          <div class="preview-note">
            安全策略：临时密码只展示一次；后续只能“重置密码”，不能“查询密码”。
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="create.open=false">取消</el-button>
        <el-button type="primary" :loading="create.submitting" @click="submitCreate">
          创建
        </el-button>
      </template>
    </el-dialog>

    <!-- 创建成功：一次性临时密码展示 -->
    <el-dialog v-model="pwdOnce.open" title="租户管理员临时密码（仅显示一次）" width="620px">
      <el-alert
        title="请立即复制保存。关闭后无法再次查看，只能重置。"
        type="warning"
        show-icon
        :closable="false"
        class="mb12"
      />
      <div class="pwd-box">
        <div class="pwd-label">用户名</div>
        <el-input v-model="pwdOnce.username" readonly class="mono" />
        <div class="pwd-label mt10">临时密码</div>
        <el-input v-model="pwdOnce.password" readonly class="mono" />
      </div>
      <template #footer>
        <el-button @click="pwdOnce.open=false">关闭</el-button>
        <el-button type="primary" @click="copyOncePassword">复制</el-button>
      </template>
    </el-dialog>

    <!-- 绑定 Namespace -->
    <el-dialog v-model="bindNs.open" title="绑定 Namespace（占位）" width="560px">
      <div class="muted mb8">
        租户：<span class="mono">{{ bindNs.row?.name }}</span>
      </div>
      <el-select v-model="bindNs.namespace" multiple filterable allow-create clearable placeholder="选择或输入 Namespace" class="w420">
        <el-option v-for="ns in allNamespaceOptions" :key="ns" :label="ns" :value="ns" />
      </el-select>
      <div class="hint mt10">
        后端建议：若 Namespace 不存在可自动创建，并绑定配额/RBAC。
      </div>
      <template #footer>
        <el-button @click="bindNs.open=false">取消</el-button>
        <el-button type="primary" @click="submitBindNs">确定</el-button>
      </template>
    </el-dialog>

    <!-- 编辑标签 -->
    <el-dialog v-model="labelsDlg.open" title="编辑标签（假数据）" width="720px">
      <div class="muted mb10">
        租户：<span class="mono">{{ labelsDlg.row?.name }}</span>
      </div>

      <el-table :data="labelsDlg.kvList" stripe height="320">
        <el-table-column prop="k" label="Key" width="240">
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
        <!-- 预留后端接口 -->
        <!-- PUT /api/tenants/{tenantId}/labels  body: { labels: {k:v} } -->
      </div>

      <template #footer>
        <el-button @click="labelsDlg.open=false">取消</el-button>
        <el-button type="primary" @click="submitLabels">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, reactive, ref, watch } from 'vue'
import type { PropType } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { Refresh, Plus, Search, ArrowDown } from '@element-plus/icons-vue'
import { fetchNamespaceOptions } from '@/api/namespaces'

import type { TenantRow, TenantStatus } from '@/api/tenants'
import {
  fetchTenants,
  createTenant,
  deleteTenant,
  toggleTenant,
  bindTenantNamespace,
  updateTenantLabels,
} from '@/api/tenants'
import { resetPassword } from '@/api/users'
import { tr } from 'element-plus/es/locales.mjs'

const router = useRouter()
const loading = ref(false)

const filters = reactive({
  keyword: '',
  status: '' as '' | TenantStatus,
})

const pagination = reactive({
  page: 1,
  pageSize: 20,
})

/** Namespace 候选：建议后端提供 /api/namespaces/options；这里先保留本地候选 */
const allNamespaceOptions = ref<string[]>([
  'default',
  'kube-system',
  'monitoring',
  'logging',
])

/** ✅ 真数据：从后端拉 */
const rows = ref<TenantRow[]>([])

const filteredRows = computed(() => {
  // 这里前端继续做一次过滤兜底；实际也可让后端过滤
  const kw = filters.keyword.trim().toLowerCase()
  return rows.value
    .filter((r) => (filters.status ? r.status === filters.status : true))
    .filter((r) => {
      if (!kw) return true
      const hay = [
        r.name,
        r.adminUser,
        r.id,
        (r.namespaces || []).join(' '),
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
  () => [filters.keyword, filters.status],
  () => {
    pagination.page = 1
  }
)

function applyFilters() {
  pagination.page = 1
  // 也可以选择：每次查询都从后端拉（更准确/省前端算力）
  refresh()
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  pagination.page = 1
  refresh()
}

/** ✅ 刷新：真接口 */
async function refresh() {
  loading.value = true
  try {
    const resp = await fetchTenants({
      keyword: filters.keyword.trim() || undefined,
      status: (filters.status as any) || undefined,
    })
    rows.value = resp.items || []
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '刷新失败')
  } finally {
    loading.value = false
  }
}

async function loadNamespaceOptions() {
  try {
    const resp = await fetchNamespaceOptions()
    allNamespaceOptions.value = resp.items || []
  } catch (e:any) {
    // options 拉失败不阻塞主流程
  }
}

onMounted(() => {
  refresh()
  loadNamespaceOptions()
})


/** 进入详情 */
function goDetail(row: TenantRow) {
  router.push({ path: '/tenants', query: { id: row.id } })
}

/** 创建租户 */
const create = reactive({
  open: false,
  submitting: false,
  form: {
    tenantName: '',
    bindNamespace: '',
    createAdminUser: true,
    adminUsername: '',
    pwdMode: 'auto' as 'auto' | 'manual',
    tempPassword: '',
    mustChangePassword: true,
    quotaCpu: '8',
    quotaMem: '16Gi',
  },
})

function openCreate() {
  create.open = true
  create.form.tenantName = ''
  create.form.bindNamespace = ''
  create.form.createAdminUser = true
  create.form.adminUsername = ''
  create.form.pwdMode = 'auto'
  create.form.tempPassword = ''
  create.form.mustChangePassword = true
  create.form.quotaCpu = '8'
  create.form.quotaMem = '16Gi'
}

/** 一次性密码弹窗 */
const pwdOnce = reactive({
  open: false,
  username: '',
  password: '',
})

async function submitCreate() {
  const tenantName = create.form.tenantName.trim()
  if (!tenantName) return ElMessage.warning('请输入租户名称')

  if (create.form.createAdminUser) {
    const u = create.form.adminUsername.trim()
    if (!u) return ElMessage.warning('请输入管理员用户名')
    if (create.form.pwdMode === 'manual' && !create.form.tempPassword.trim()) {
      return ElMessage.warning('请输入临时密码')
    }
  }

  create.submitting = true
  try {
    const resp = await createTenant({
      name: tenantName,
      bindNamespace: create.form.bindNamespace.trim() || undefined,
      autoCreateNamespace: true,
      createAdminUser: create.form.createAdminUser,
      adminUsername: create.form.createAdminUser ? create.form.adminUsername.trim() : undefined,
      pwdMode: create.form.createAdminUser ? create.form.pwdMode : undefined,
      tempPassword:
        create.form.createAdminUser && create.form.pwdMode === 'manual'
          ? create.form.tempPassword.trim()
          : undefined,
      mustChangePassword: create.form.createAdminUser ? create.form.mustChangePassword : undefined,
      quotaCpu: create.form.quotaCpu.trim() || '8',
      quotaMem: create.form.quotaMem.trim() || '16Gi',
    })

    // 更新表格
    rows.value = [resp.tenant, ...rows.value]
    create.open = false
    ElMessage.success('租户已创建')

    // 展示一次性密码（后端返回）
    if (resp.oneTimePassword) {
      pwdOnce.username = resp.oneTimePassword.username
      pwdOnce.password = resp.oneTimePassword.password
      pwdOnce.open = true
    }

    // 如果你想把新 namespace 自动加入候选（可选）
    const ns = resp.tenant.namespaces?.[0]
    if (ns && !allNamespaceOptions.value.includes(ns)) {
      allNamespaceOptions.value.push(ns)
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '创建失败')
  } finally {
    create.submitting = false
  }
}

async function copyOncePassword() {
  try {
    await navigator.clipboard.writeText(`username: ${pwdOnce.username}\npassword: ${pwdOnce.password}`)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败（浏览器权限限制）')
  }
}

/** 绑定 Namespace */
const bindNs = reactive<{ open: boolean; row: TenantRow | null; namespace: string[] }>({
  open: false,
  row: null,
  namespace: [],
})

function openBindNs(row: TenantRow) {
  bindNs.row = row
  bindNs.namespace = [...(row.namespaces || [])]   // 默认带上已有绑定
  bindNs.open = true
}


async function submitBindNs() {
  if (!bindNs.row) return
  const arr = (bindNs.namespace || []).map(s => s.trim()).filter(Boolean)
  if (arr.length === 0) return ElMessage.warning('请选择或输入 Namespace')

  try {
    // 逐个绑定（幂等：后端若已存在应返回成功）
    let latest: string[] = bindNs.row.namespaces || []
    for (const ns of arr) {
      const resp = await bindTenantNamespace({ id: bindNs.row.id, namespace: ns, autoCreate: true })
      latest = resp.namespaces
      if (!allNamespaceOptions.value.includes(ns)) allNamespaceOptions.value.push(ns)
    }
    bindNs.row.namespaces = latest
    bindNs.open = false
    ElMessage.success('已绑定 Namespace')
  } catch (e:any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '绑定失败')
  }
}

/** 编辑标签 */
const labelsDlg = reactive<{
  open: boolean
  row: TenantRow | null
  kvList: Array<{ k: string; v: string }>
}>({
  open: false,
  row: null,
  kvList: [],
})

function openEditLabels(row: TenantRow) {
  labelsDlg.row = row
  labelsDlg.kvList = Object.entries(row.labels || {}).map(([k, v]) => ({ k, v }))
  if (labelsDlg.kvList.length === 0) labelsDlg.kvList = [{ k: '', v: '' }]
  labelsDlg.open = true
}

async function submitLabels() {
  if (!labelsDlg.row) return

  const obj: Record<string, string> = {}
  for (const kv of labelsDlg.kvList) {
    const k = kv.k.trim()
    const v = kv.v.trim()
    if (!k) continue
    obj[k] = v
  }

  try {
    const resp = await updateTenantLabels({ id: labelsDlg.row.id, labels: obj })
    labelsDlg.row.labels = resp.labels
    labelsDlg.open = false
    ElMessage.success('已保存标签')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '保存失败')
  }
}

/** 更多操作 */
async function handleMore(cmd: string, row: TenantRow) {
  if (cmd === 'delete') {
    await ElMessageBox.confirm(
      `确定删除租户 ${row.name} 吗？\n（默认不删除 Namespace；如需联动删除，请后端开启 deleteNamespaces=true）`,
      '确认删除',
      { type: 'warning' }
    )

    try {
      await deleteTenant({ id: row.id, deleteNamespaces: true })
      rows.value = rows.value.filter((x) => x.id !== row.id)
      ElMessage.success('已删除')
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '删除失败')
    }
    return
  }

  if (cmd === 'toggle') {
    try {
      const resp = await toggleTenant(row.id)
      row.status = resp.status
      ElMessage.success('已更新状态')
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '更新失败')
    }
    return
  }

  if (cmd === 'resetPwd') {
    await ElMessageBox.confirm(
      `确定要重置管理员账号（${row.adminUser}）的密码吗？\n重置后会生成一次性临时密码（仅显示一次）。`,
      '重置密码',
      { type: 'warning' }
    )

    try {
      const resp = await resetPassword({ username: row.adminUser })
      pwdOnce.username = resp.oneTimePassword.username
      pwdOnce.password = resp.oneTimePassword.password
      pwdOnce.open = true
      ElMessage.success('已重置密码')
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || e?.message || '重置失败')
    }
  }
}

/**
 * ✅ StatusPill（不用 JSX，用 h()）
 */
const StatusPill = defineComponent({
  name: 'StatusPill',
  props: {
    status: { type: String as PropType<TenantStatus>, required: true },
  },
  setup(props) {
    const text = computed(() => {
      if (props.status === 'active') return '正常'
      if (props.status === 'disabled') return '禁用'
      return '异常'
    })
    const cls = computed(() => `pill pill-${props.status}`)
    return () =>
      h('span', { class: cls.value }, [h('span', { class: 'dot' }), h('span', { class: 'txt' }, text.value)])
  },
})
</script>

<style scoped>
.tenant-page {
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

.card {
  border-radius: 12px;
  border: 1px solid #e5e7eb;
}
.filters {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.w320 { width: 320px; }
.w160 { width: 160px; }

.table {
  border-radius: 10px;
  overflow: hidden;
}
.pager {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

/* 单元格 */
.name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}
.name {
  font-weight: 700;
  color: #111827;
}
.sub {
  margin-top: 2px;
}
.ns-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag { border-radius: 999px; }
.ops {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* 创建弹窗布局 */
.dlg-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(0, 0.7fr);
  gap: 14px;
}
.form :deep(.el-form-item) { margin-bottom: 12px; }
.side-preview {
  border: 1px dashed #e5e7eb;
  border-radius: 12px;
  padding: 12px;
  background: #fafafa;
}
.preview-title {
  font-weight: 700;
  margin-bottom: 8px;
}
.preview-list {
  margin: 0;
  padding-left: 18px;
  color: #374151;
  font-size: 13px;
}
.preview-note {
  margin-top: 10px;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.6;
}

.quota-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.w160 { width: 160px; }

/* 一次性密码弹窗 */
.pwd-box .pwd-label {
  font-size: 12px;
  color: #6b7280;
  margin: 6px 0;
}
.mt10 { margin-top: 10px; }
.mb12 { margin-bottom: 12px; }
.mr6 { margin-right: 6px; }
.ml6 { margin-left: 6px; }
.ml8 { margin-left: 8px; }
.ml10 { margin-left: 10px; }

.muted { color: #6b7280; font-size: 12px; }
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
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
.pill-active {
  color: #059669;
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.25);
}
.pill-disabled {
  color: #64748b;
  background: rgba(100, 116, 139, 0.10);
  border-color: rgba(100, 116, 139, 0.25);
}
.pill-warning {
  color: #d97706;
  background: rgba(245, 158, 11, 0.10);
  border-color: rgba(245, 158, 11, 0.25);
}

@media (max-width: 1024px) {
  .dlg-grid { grid-template-columns: 1fr; }
  .w320, .w160 { width: 100%; }
}
</style>
