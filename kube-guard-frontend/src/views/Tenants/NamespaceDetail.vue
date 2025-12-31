<template>
  <div class="detail-page">
    <!-- 顶部 -->
    <div class="page-head">
      <div class="left">
        <el-button text @click="back">
          <el-icon class="mr6"><ArrowLeft /></el-icon>
          返回
        </el-button>

        <div>
          <div class="title-row">
            <div class="page-title">{{ tenantName }}</div>
            <StatusPill :status="tenantStatus" class="ml10" />
          </div>
          <div class="page-subtitle">
            TenantID：<span class="mono">{{ tenantId }}</span>
            · 管理员：<span class="mono">{{ adminUser }}</span>
            · 创建时间：{{ createdAt }}
          </div>
        </div>
      </div>

      <div class="actions">
        <el-button @click="openEditLabels" :disabled="!tenant">
          <el-icon class="mr6"><Edit /></el-icon>
          编辑标签
        </el-button>

        <el-button @click="openBindNs" :disabled="!tenant">
          <el-icon class="mr6"><Link /></el-icon>
          绑定 Namespace
        </el-button>

        <el-button @click="openQuota" :disabled="!tenant">
          <el-icon class="mr6"><Setting /></el-icon>
          配额（占位）
        </el-button>

        <el-dropdown @command="(cmd:string)=>handleMore(cmd)" :disabled="!tenant">
          <el-button>
            更多 <el-icon class="ml6"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="resetPwd">重置租户管理员密码</el-dropdown-item>
              <el-dropdown-item command="toggle">
                {{ tenantStatus === 'disabled' ? '启用租户' : '禁用租户' }}
              </el-dropdown-item>
              <el-dropdown-item command="delete" divided>删除租户</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- tenant 不存在 -->
    <el-empty
      v-if="!tenant"
      description="租户不存在（请从列表页进入，或检查 query.id）"
      class="empty"
    />

    <!-- 主体 -->
    <div v-else class="grid">
      <!-- 左：概览 + namespace + quota -->
      <el-card shadow="never" class="card">
        <div class="section-title">租户概览</div>

        <div class="kv">
          <div class="k">状态</div>
          <div class="v"><StatusPill :status="tenantStatus" /></div>

          <div class="k">租户管理员</div>
          <div class="v mono">{{ adminUser }}</div>

          <div class="k">绑定 Namespace</div>
          <div class="v">
            <div class="tags">
              <el-tag
                v-for="ns in namespaces"
                :key="ns"
                size="small"
                effect="plain"
                class="tag"
              >
                {{ ns }}
              </el-tag>
              <span v-if="namespaces.length===0" class="muted">未绑定</span>
            </div>
          </div>

          <div class="k">配额（占位）</div>
          <div class="v">
            <div class="muted">
              CPU {{ quotaCpu }} / MEM {{ quotaMem }}
            </div>
            <div class="sub muted">后端对接：ResourceQuota / LimitRange</div>
          </div>

          <div class="k">标签</div>
          <div class="v">
            <div class="tags">
              <el-tag
                v-for="(v,k) in labels"
                :key="k"
                size="small"
                type="info"
                effect="plain"
                class="tag"
              >
                {{ k }}={{ v }}
              </el-tag>
              <span v-if="Object.keys(labels).length===0" class="muted">无</span>
            </div>
          </div>
        </div>

        <el-divider />

        <div class="section-title">Namespace 管理（占位）</div>
        <div class="ns-block">
          <div class="muted">
            这里模拟 KubeSphere：租户可以绑定多个 Namespace，并在后端下发 RBAC、配额等策略。
          </div>

          <div class="ns-actions">
            <el-button size="small" @click="openBindNs">
              <el-icon class="mr6"><Plus /></el-icon>绑定
            </el-button>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="namespaces.length===0"
              @click="openUnbindNs"
            >
              解绑（占位）
            </el-button>
          </div>

          <div class="hint mt10">
            <!-- 预留后端接口 -->
            <!-- POST /api/tenants/{id}/namespaces body:{namespace} -->
            <!-- DELETE /api/tenants/{id}/namespaces/{namespace} -->
            <!-- 可选：创建 ns + 绑定 ResourceQuota + RoleBinding -->
          </div>
        </div>
      </el-card>

      <!-- 右：成员与 RBAC -->
      <el-card shadow="never" class="card">
        <div class="section-title">成员与访问控制（RBAC 占位）</div>
        <div class="muted mb10">
          租户成员用于登录你的运维平台；后端再映射到 K8s RBAC（Role/RoleBinding/ClusterRoleBinding）。
        </div>

        <div class="toolbar">
          <el-input v-model="memberKeyword" placeholder="搜索成员：用户名/邮箱" clearable class="w260" />
          <div class="spacer"></div>
          <el-button type="primary" plain @click="openInvite">
            <el-icon class="mr6"><Plus /></el-icon>
            新增成员
          </el-button>
        </div>

        <el-table :data="filteredMembers" stripe height="360">
          <el-table-column prop="username" label="用户名" min-width="180">
            <template #default="{ row }">
              <div class="mono">{{ row.username }}</div>
              <div class="sub muted">邮箱：{{ row.email || '-' }}</div>
            </template>
          </el-table-column>

          <el-table-column prop="role" label="角色" width="160">
            <template #default="{ row }">
              <el-tag size="small" effect="plain">{{ roleLabel(row.role) }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column prop="status" label="状态" width="140">
            <template #default="{ row }">
              <UserStatus :status="row.status" />
            </template>
          </el-table-column>

          <el-table-column label="操作" width="360" fixed="right">
            <template #default="{ row }">
              <div class="ops">
                <el-button size="small" @click="openChangeRole(row)">
                  改角色
                </el-button>

                <el-button size="small" @click="resetUserPwd(row)">
                  重置密码
                </el-button>

                <el-button
                  size="small"
                  type="danger"
                  plain
                  @click="toggleUser(row)"
                >
                  {{ row.status === 'disabled' ? '启用' : '禁用' }}
                </el-button>

                <el-button
                  size="small"
                  type="danger"
                  plain
                  @click="removeUser(row)"
                >
                  删除
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div class="hint mt10">
          <!-- 预留后端接口 -->
          <!-- GET /api/tenants/{id} -->
          <!-- GET /api/tenants/{id}/members -->
          <!-- POST /api/tenants/{id}/members body:{username,email,role,initialPasswordMode} -> oneTimePassword? -->
          <!-- PUT /api/tenants/{id}/members/{username}/role body:{role} -->
          <!-- POST /api/users/reset-password body:{username} -> oneTimePassword -->
          <!-- POST /api/users/toggle body:{username} -->
          <!-- DELETE /api/tenants/{id}/members/{username} -->
          <!-- K8s落地：Role/RoleBinding 绑定 ns 资源权限 -->
        </div>
      </el-card>
    </div>

    <!-- 一次性密码弹窗（管理员/成员共用） -->
    <el-dialog v-model="pwdOnce.open" title="一次性临时密码（仅显示一次）" width="620px">
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
        租户：<span class="mono">{{ tenantName }}</span>
      </div>
      <el-select
        v-model="bindNs.namespace"
        filterable
        allow-create
        clearable
        placeholder="选择或输入 Namespace"
        class="w420"
      >
        <el-option v-for="ns in allNamespaceOptions" :key="ns" :label="ns" :value="ns" />
      </el-select>
      <div class="hint mt10">
        建议：后端可自动创建 Namespace，并应用配额与 RoleBinding。
      </div>
      <template #footer>
        <el-button @click="bindNs.open=false">取消</el-button>
        <el-button type="primary" @click="submitBindNs">确定</el-button>
      </template>
    </el-dialog>

    <!-- 解绑 Namespace（占位） -->
    <el-dialog v-model="unbindNs.open" title="解绑 Namespace（占位）" width="560px">
      <div class="muted mb8">
        租户：<span class="mono">{{ tenantName }}</span>
      </div>
      <el-select v-model="unbindNs.namespace" placeholder="选择要解绑的 Namespace" clearable class="w420">
        <el-option v-for="ns in namespaces" :key="ns" :label="ns" :value="ns" />
      </el-select>
      <div class="hint mt10">
        注意：解绑不等于删除 Namespace（是否删除由后端策略决定）。
      </div>
      <template #footer>
        <el-button @click="unbindNs.open=false">取消</el-button>
        <el-button type="danger" @click="submitUnbindNs">解绑</el-button>
      </template>
    </el-dialog>

    <!-- 编辑标签 -->
    <el-dialog v-model="labelsDlg.open" title="编辑标签（假数据）" width="720px">
      <div class="muted mb10">
        租户：<span class="mono">{{ tenantName }}</span>
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
        <!-- PUT /api/tenants/{id}/labels body:{labels:{k:v}} -->
      </div>

      <template #footer>
        <el-button @click="labelsDlg.open=false">取消</el-button>
        <el-button type="primary" @click="submitLabels">保存</el-button>
      </template>
    </el-dialog>

    <!-- 配额（占位） -->
    <el-dialog v-model="quotaDlg.open" title="配额设置（占位）" width="640px">
      <div class="muted mb10">
        租户：<span class="mono">{{ tenantName }}</span>
        · 目标：绑定 Namespace 后对其下发 ResourceQuota/LimitRange
      </div>

      <el-form label-width="140px">
        <el-form-item label="CPU 配额">
          <el-input v-model="quotaDlg.cpu" placeholder="例如 8" class="w260" />
        </el-form-item>
        <el-form-item label="内存配额">
          <el-input v-model="quotaDlg.mem" placeholder="例如 16Gi" class="w260" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input
            type="textarea"
            :rows="3"
            v-model="quotaDlg.note"
            placeholder="占位：后端对接 ResourceQuota/LimitRange，并关联 tenant->namespaces"
          />
        </el-form-item>
      </el-form>

      <div class="hint mt10">
        <!-- 预留后端接口 -->
        <!-- PUT /api/tenants/{id}/quota body:{cpu,memory} -->
        <!-- 可选：按 namespace 维度设置配额 -->
      </div>

      <template #footer>
        <el-button @click="quotaDlg.open=false">取消</el-button>
        <el-button type="primary" @click="submitQuota">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增成员 -->
    <el-dialog v-model="invite.open" title="新增成员（假数据）" width="680px">
      <el-form label-width="120px">
        <el-form-item label="用户名">
          <el-input v-model="invite.form.username" placeholder="例如 alice" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="invite.form.email" placeholder="alice@example.com" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="invite.form.role" placeholder="选择角色" class="w260">
            <el-option label="只读（viewer）" value="viewer" />
            <el-option label="编辑（editor）" value="editor" />
            <el-option label="管理员（admin）" value="admin" />
          </el-select>
        </el-form-item>

        <el-divider />

        <el-form-item label="初始密码">
          <el-radio-group v-model="invite.form.pwdMode">
            <el-radio label="auto">自动生成（一次性展示）</el-radio>
            <el-radio label="manual">手动输入（一次性展示）</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="invite.form.pwdMode==='manual'" label="临时密码">
          <el-input v-model="invite.form.tempPassword" show-password placeholder="输入一次性临时密码" />
        </el-form-item>

        <el-form-item label="首登强制改密">
          <el-switch v-model="invite.form.mustChange" />
        </el-form-item>
      </el-form>

      <div class="hint mt10">
        <!-- 预留后端接口 -->
        <!-- POST /api/tenants/{id}/members body:{username,email,role,pwdMode,tempPassword?,mustChange} -> oneTimePassword -->
      </div>

      <template #footer>
        <el-button @click="invite.open=false">取消</el-button>
        <el-button type="primary" @click="submitInvite">确定</el-button>
      </template>
    </el-dialog>

    <!-- 改角色 -->
    <el-dialog v-model="roleDlg.open" title="修改成员角色（假数据）" width="560px">
      <div class="muted mb10">
        成员：<span class="mono">{{ roleDlg.row?.username || '-' }}</span>
      </div>
      <el-select v-model="roleDlg.role" class="w260">
        <el-option label="只读（viewer）" value="viewer" />
        <el-option label="编辑（editor）" value="editor" />
        <el-option label="管理员（admin）" value="admin" />
      </el-select>

      <div class="hint mt10">
        <!-- 预留后端接口 -->
        <!-- PUT /api/tenants/{id}/members/{username}/role body:{role} -->
      </div>

      <template #footer>
        <el-button @click="roleDlg.open=false">取消</el-button>
        <el-button type="primary" @click="submitRole">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, reactive, ref, onMounted } from 'vue'
import type { PropType } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowDown, Plus, Edit, Link, Setting } from '@element-plus/icons-vue'
import { fetchNamespaceOptions } from '@/api/namespaces'

type TenantStatus = 'active' | 'disabled' | 'warning'
type MemberRole = 'viewer' | 'editor' | 'admin'
type MemberStatus = 'active' | 'disabled'

type Tenant = {
  id: string
  name: string
  status: TenantStatus
  adminUser: string
  namespaces: string[]
  labels: Record<string, string>
  quota: { cpu: string; memory: string }
  createdAt: string
}

type Member = {
  username: string
  email?: string
  role: MemberRole
  status: MemberStatus
}

const route = useRoute()
const router = useRouter()

/** namespace 候选（假） */
const allNamespaceOptions = ref<string[]>([])
async function loadNsOptions() {
  const resp = await fetchNamespaceOptions()
  allNamespaceOptions.value = resp.items || []
}
onMounted(() => {
  loadNsOptions()
})

/** 假租户详情数据（后续用 route.query.id 去后端拉） */
const tenants = ref<Tenant[]>([
  {
    id: 't-1001',
    name: 'acme',
    status: 'active',
    adminUser: 'acme-admin',
    namespaces: ['ns-acme'],
    labels: { env: 'prod', owner: 'acme' },
    quota: { cpu: '16', memory: '32Gi' },
    createdAt: '2025-12-12',
  },
  {
    id: 't-1002',
    name: 'dev-team',
    status: 'warning',
    adminUser: 'dev-admin',
    namespaces: ['ns-dev-team', 'dev'],
    labels: { env: 'dev' },
    quota: { cpu: '8', memory: '16Gi' },
    createdAt: '2025-12-10',
  },
])

/** 取 id（兜底） */
const tenantId = computed(() => String(route.query.id || ''))

/** 当前租户（可能为空） */
const tenant = computed<Tenant | null>(() => tenants.value.find((t) => t.id === tenantId.value) ?? null)

/** 全部展示字段用 computed 兜底，避免 TS “可能为 undefined” */
const tenantName = computed(() => tenant.value?.name ?? '未知租户')
const tenantStatus = computed<TenantStatus>(() => tenant.value?.status ?? 'warning')
const adminUser = computed(() => tenant.value?.adminUser ?? '-')
const namespaces = computed(() => tenant.value?.namespaces ?? [])
const labels = computed<Record<string, string>>(() => tenant.value?.labels ?? {})
const quotaCpu = computed(() => tenant.value?.quota?.cpu ?? '-')
const quotaMem = computed(() => tenant.value?.quota?.memory ?? '-')
const createdAt = computed(() => tenant.value?.createdAt ?? '-')

/** 返回 */
function back() {
  router.back()
}

/** role 显示 */
function roleLabel(role: MemberRole) {
  if (role === 'admin') return '管理员'
  if (role === 'editor') return '编辑'
  return '只读'
}

/** 成员（假数据） */
const members = ref<Member[]>([
  { username: 'acme-admin', email: 'admin@acme.com', role: 'admin', status: 'active' },
  { username: 'alice', email: 'alice@acme.com', role: 'editor', status: 'active' },
  { username: 'bob', email: 'bob@acme.com', role: 'viewer', status: 'disabled' },
])

const memberKeyword = ref('')
const filteredMembers = computed(() => {
  const kw = memberKeyword.value.trim().toLowerCase()
  if (!kw) return members.value
  return members.value.filter((m) => `${m.username} ${m.email ?? ''}`.toLowerCase().includes(kw))
})

/** 一次性密码弹窗 */
const pwdOnce = reactive({
  open: false,
  username: '',
  password: '',
})

function genPassword(len = 12) {
  const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%&*'
  let out = ''
  for (let i = 0; i < len; i++) out += chars[Math.floor(Math.random() * chars.length)]
  return out
}

async function copyOncePassword() {
  try {
    await navigator.clipboard.writeText(`username: ${pwdOnce.username}\npassword: ${pwdOnce.password}`)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('复制失败（浏览器权限限制）')
  }
}

/** 更多操作（租户） */
async function handleMore(cmd: string) {
  if (!tenant.value) return

  if (cmd === 'resetPwd') {
    await ElMessageBox.confirm(
      `确定重置租户管理员（${tenant.value.adminUser}）密码吗？\n将生成一次性临时密码（仅显示一次）。`,
      '重置密码',
      { type: 'warning' }
    )
    // === 预留后端接口 ===
    // POST /api/users/reset-password  body:{username: tenant.value.adminUser}
    // resp: { oneTimePassword: { username, password } }

    pwdOnce.username = tenant.value.adminUser
    pwdOnce.password = genPassword(14)
    pwdOnce.open = true
    ElMessage.success('已重置（假数据）')
    return
  }

  if (cmd === 'toggle') {
    // === 预留后端接口 ===
    // POST /api/tenants/{id}/toggle
    tenant.value.status = tenant.value.status === 'disabled' ? 'active' : 'disabled'
    ElMessage.success('已更新状态（假数据）')
    return
  }

  if (cmd === 'delete') {
    await ElMessageBox.confirm(
      `确定删除租户 ${tenant.value.name} 吗？\n（是否删除/保留 Namespace 由后端策略决定）`,
      '确认删除',
      { type: 'warning' }
    )
    // === 预留后端接口 ===
    // DELETE /api/tenants/{id}
    tenants.value = tenants.value.filter((x) => x.id !== tenant.value!.id)
    ElMessage.success('已删除（假数据）')
    router.back()
  }
}

/** 绑定/解绑 Namespace */
const bindNs = reactive({ open: false, namespace: '' })
function openBindNs() {
  bindNs.namespace = ''
  bindNs.open = true
}
function submitBindNs() {
  if (!tenant.value) return
  const ns = bindNs.namespace.trim()
  if (!ns) return ElMessage.warning('请输入或选择 Namespace')

  // === 预留后端接口 ===
  // POST /api/tenants/{id}/namespaces body:{namespace: ns}

  if (!tenant.value.namespaces.includes(ns)) tenant.value.namespaces.push(ns)
  bindNs.open = false
  ElMessage.success('已绑定（假数据）')
}

const unbindNs = reactive({ open: false, namespace: '' })
function openUnbindNs() {
  unbindNs.namespace = ''
  unbindNs.open = true
}
async function submitUnbindNs() {
  if (!tenant.value) return
  const ns = unbindNs.namespace.trim()
  if (!ns) return ElMessage.warning('请选择要解绑的 Namespace')

  await ElMessageBox.confirm(
    `确定解绑 Namespace ${ns} 吗？\n（是否删除 Namespace 由后端策略决定）`,
    '确认解绑',
    { type: 'warning' }
  )

  // === 预留后端接口 ===
  // DELETE /api/tenants/{id}/namespaces/{namespace}

  tenant.value.namespaces = tenant.value.namespaces.filter((x) => x !== ns)
  unbindNs.open = false
  ElMessage.success('已解绑（假数据）')
}

/** 标签编辑 */
const labelsDlg = reactive<{ open: boolean; kvList: Array<{ k: string; v: string }> }>({
  open: false,
  kvList: [],
})

function openEditLabels() {
  if (!tenant.value) return
  labelsDlg.kvList = Object.entries(tenant.value.labels).map(([k, v]) => ({ k, v }))
  if (labelsDlg.kvList.length === 0) labelsDlg.kvList = [{ k: '', v: '' }]
  labelsDlg.open = true
}

function submitLabels() {
  if (!tenant.value) return
  const obj: Record<string, string> = {}
  for (const kv of labelsDlg.kvList) {
    const k = kv.k.trim()
    const v = kv.v.trim()
    if (!k) continue
    obj[k] = v
  }

  // === 预留后端接口 ===
  // PUT /api/tenants/{id}/labels body:{labels: obj}

  tenant.value.labels = obj
  labelsDlg.open = false
  ElMessage.success('已保存标签（假数据）')
}

/** 配额（占位） */
const quotaDlg = reactive({
  open: false,
  cpu: '',
  mem: '',
  note: '',
})

function openQuota() {
  quotaDlg.open = true
  quotaDlg.cpu = quotaCpu.value
  quotaDlg.mem = quotaMem.value
  quotaDlg.note = '占位：后端对接 ResourceQuota/LimitRange，并按 tenant->namespace 下发'
}

function submitQuota() {
  if (!tenant.value) return
  const cpu = quotaDlg.cpu.trim()
  const mem = quotaDlg.mem.trim()
  if (!cpu || !mem) return ElMessage.warning('请填写 CPU 与内存配额')

  // === 预留后端接口 ===
  // PUT /api/tenants/{id}/quota body:{cpu, memory}
  // 然后对 namespaces 下发 ResourceQuota/LimitRange

  tenant.value.quota = { cpu, memory: mem }
  quotaDlg.open = false
  ElMessage.success('已保存配额（假数据）')
}

/** 新增成员 */
const invite = reactive({
  open: false,
  form: {
    username: '',
    email: '',
    role: 'viewer' as MemberRole,
    pwdMode: 'auto' as 'auto' | 'manual',
    tempPassword: '',
    mustChange: true,
  },
})

function openInvite() {
  invite.open = true
  invite.form.username = ''
  invite.form.email = ''
  invite.form.role = 'viewer'
  invite.form.pwdMode = 'auto'
  invite.form.tempPassword = ''
  invite.form.mustChange = true
}

async function submitInvite() {
  if (!tenant.value) return
  const u = invite.form.username.trim()
  if (!u) return ElMessage.warning('请输入用户名')
  if (members.value.some((m) => m.username === u)) return ElMessage.warning('该用户名已存在')

  if (invite.form.pwdMode === 'manual' && !invite.form.tempPassword.trim()) {
    return ElMessage.warning('请输入临时密码')
  }

  // === 预留后端接口 ===
  // POST /api/tenants/{id}/members body:{username,email,role,pwdMode,tempPassword?,mustChange}
  // resp: { oneTimePassword: { username, password } }

  members.value.unshift({
    username: u,
    email: invite.form.email.trim() || undefined,
    role: invite.form.role,
    status: 'active',
  })
  invite.open = false
  ElMessage.success('已新增成员（假数据）')

  // 一次性密码展示（模拟后端返回）
  pwdOnce.username = u
  pwdOnce.password = invite.form.pwdMode === 'manual' ? invite.form.tempPassword.trim() : genPassword(14)
  pwdOnce.open = true
}

/** 改角色 */
const roleDlg = reactive<{ open: boolean; row: Member | null; role: MemberRole }>({
  open: false,
  row: null,
  role: 'viewer',
})

function openChangeRole(row: Member) {
  roleDlg.row = row
  roleDlg.role = row.role
  roleDlg.open = true
}

function submitRole() {
  if (!roleDlg.row) return
  // === 预留后端接口 ===
  // PUT /api/tenants/{id}/members/{username}/role body:{role}

  roleDlg.row.role = roleDlg.role
  roleDlg.open = false
  ElMessage.success('已更新角色（假数据）')
}

/** 成员：重置密码 */
async function resetUserPwd(row: Member) {
  await ElMessageBox.confirm(
    `确定重置 ${row.username} 的密码吗？\n将生成一次性临时密码（仅显示一次）。`,
    '重置密码',
    { type: 'warning' }
  )

  // === 预留后端接口 ===
  // POST /api/users/reset-password body:{username: row.username}
  // resp: { oneTimePassword: { username, password } }

  pwdOnce.username = row.username
  pwdOnce.password = genPassword(14)
  pwdOnce.open = true
  ElMessage.success('已重置（假数据）')
}

/** 成员：启用/禁用 */
function toggleUser(row: Member) {
  // === 预留后端接口 ===
  // POST /api/users/toggle body:{username}
  row.status = row.status === 'disabled' ? 'active' : 'disabled'
  ElMessage.success('已更新（假数据）')
}

/** 成员：删除 */
async function removeUser(row: Member) {
  await ElMessageBox.confirm(
    `确定删除成员 ${row.username} 吗？`,
    '删除成员',
    { type: 'warning' }
  )

  // === 预留后端接口 ===
  // DELETE /api/tenants/{id}/members/{username}

  members.value = members.value.filter((m) => m.username !== row.username)
  ElMessage.success('已删除（假数据）')
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
      h('span', { class: cls.value }, [
        h('span', { class: 'dot' }),
        h('span', { class: 'txt' }, text.value),
      ])
  },
})

/**
 * ✅ UserStatus（不用 JSX，用 h()）
 */
const UserStatus = defineComponent({
  name: 'UserStatus',
  props: {
    status: { type: String as PropType<MemberStatus>, required: true },
  },
  setup(props) {
    const text = computed(() => (props.status === 'active' ? '正常' : '禁用'))
    const cls = computed(() => `pill pill-${props.status === 'active' ? 'active' : 'disabled'}`)
    return () =>
      h('span', { class: cls.value }, [
        h('span', { class: 'dot' }),
        h('span', { class: 'txt' }, text.value),
      ])
  },
})


</script>

<style scoped>
.detail-page {
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
.left {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.page-title {
  font-size: 16px;
  font-weight: 800;
  color: #111827;
}
.page-subtitle {
  margin-top: 2px;
  font-size: 12px;
  color: #6b7280;
}
.actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.empty {
  padding: 40px 0;
}

/* 主体布局 */
.grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  gap: 14px;
}
.card {
  border-radius: 12px;
  border: 1px solid #e5e7eb;
}

/* section */
.section-title {
  font-weight: 800;
  margin-bottom: 10px;
  color: #111827;
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
  word-break: break-word;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  border-radius: 999px;
}
.sub {
  margin-top: 2px;
}

.ns-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ns-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

/* 右侧工具条 */
.toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 10px;
}
.spacer {
  flex: 1;
}
.w260 {
  width: 260px;
}

/* ops */
.ops {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* 密码弹窗 */
.pwd-box .pwd-label {
  font-size: 12px;
  color: #6b7280;
  margin: 6px 0;
}

.muted {
  color: #6b7280;
  font-size: 12px;
}
.hint {
  color: #6b7280;
  font-size: 12px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
}

.mt10 {
  margin-top: 10px;
}
.mb10 {
  margin-bottom: 10px;
}
.mb12 {
  margin-bottom: 12px;
}
.mr6 {
  margin-right: 6px;
}
.ml6 {
  margin-left: 6px;
}
.ml10 {
  margin-left: 10px;
}
.w420 {
  width: 420px;
}

/* pill */
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
  background: rgba(100, 116, 139, 0.1);
  border-color: rgba(100, 116, 139, 0.25);
}
.pill-warning {
  color: #d97706;
  background: rgba(245, 158, 11, 0.1);
  border-color: rgba(245, 158, 11, 0.25);
}

@media (max-width: 1024px) {
  .grid {
    grid-template-columns: 1fr;
  }
  .w420,
  .w260 {
    width: 100%;
  }
}
</style>
