<!-- src/views/Nodes/ClusterManage.vue -->
<template>
  <div class="page">
    <!-- 顶部：当前激活集群 -->
    <el-card shadow="never" class="card">
      <div class="head">
        <div>
          <div class="title">纳管集群</div>
          <div class="sub">单活多集群：同一时间只激活一个集群，平台所有监控/节点/工作负载操作都指向它</div>
        </div>
        <div class="actions">
          <el-button :loading="loading" @click="refresh" type="primary" plain>
            <el-icon class="mr6"><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>

      <div class="active-box">
        <div class="active-label">当前激活</div>
        <template v-if="active.active">
          <div class="active-main">
            <div class="active-name">
              <el-tag type="success" effect="light" class="mr6">ACTIVE</el-tag>
              {{ active.active.name }}
            </div>
            <div class="active-meta">
              <span class="pill">type: {{ active.active.type }}</span>
              <span class="pill">provider: {{ active.active.provider || '-' }}</span>
              <span class="pill">id: {{ active.active.id }}</span>
            </div>
          </div>
        </template>
        <template v-else>
          <div class="active-empty">
            还没有激活的集群。你可以先“验证 kubeconfig”，再“保存”，然后点“设为当前”。
          </div>
        </template>
      </div>
    </el-card>

    <div class="grid">
      <!-- 左：集群列表 -->
      <el-card shadow="never" class="card">
        <div class="sec-title">已纳管集群</div>

        <el-table
          v-loading="loading"
          :data="clusters"
          size="default"
          class="table"
          :header-cell-style="{ background: '#f9fafb', color: '#374151' }"
        >
          <el-table-column type="index" width="60" label="#" />
          <el-table-column label="名称" min-width="180">
            <template #default="{ row }">
              <div class="name">
                <el-tag v-if="row.is_active === 1" type="success" size="small" effect="light" class="mr6">
                  ACTIVE
                </el-tag>
                <span class="name-text">{{ row.name }}</span>
              </div>
              <div class="muted">id: {{ row.id }}</div>
            </template>
          </el-table-column>

          <el-table-column label="类型" width="120">
            <template #default="{ row }">
              <el-tag size="small" effect="light">{{ row.type }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column label="厂商" width="140">
            <template #default="{ row }">
              <span>{{ row.provider || '-' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button
                type="primary"
                text
                :disabled="row.is_active === 1"
                @click="doActivate(row.id)"
              >
                设为当前
              </el-button>
              <el-button text @click="fillFromRow(row)">复制到表单</el-button>
              <el-button
                type="danger"
                text
                :disabled="row.is_active === 1"
                @click="doDelete(row.id)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="hint danger">
          注意：这里的“删除/设为当前”只影响你的平台指向哪个集群，不会删除云服务器资源。
        </div>
      </el-card>

      <!-- 右：新增纳管 -->
      <el-card shadow="never" class="card">
        <div class="sec-title">新增纳管集群</div>

        <div class="form">
          <div class="form-item">
            <div class="label">名称</div>
            <el-input v-model="form.name" placeholder="例如：腾讯云 TKE-Prod / 本地 k3s-lab" />
          </div>

          <div class="form-item">
            <div class="label">类型</div>
            <el-radio-group v-model="form.type">
              <el-radio-button label="managed">managed（云托管）</el-radio-button>
              <el-radio-button label="self-hosted">self-hosted（自建）</el-radio-button>
            </el-radio-group>
          </div>

          <div class="form-item">
            <div class="label">provider（可选）</div>
            <el-select v-model="form.provider" placeholder="可选" clearable filterable>
              <el-option label="aliyun" value="aliyun" />
              <el-option label="tencent" value="tencent" />
              <el-option label="huawei" value="huawei" />
              <el-option label="custom" value="custom" />
            </el-select>
            <div class="muted">只是用于展示/筛选，不影响 kubeconfig 实际连接。</div>
          </div>

          <div class="form-item">
            <div class="label">kubeconfig</div>
            <el-input
              v-model="form.kubeconfig"
              type="textarea"
              :rows="12"
              placeholder="把 kubeconfig 全文粘贴进来（包含 clusters/users/contexts）"
            />
            <div class="muted">
              云托管 ACK/TKE/CCE 通常在控制台可下载 kubeconfig；自建集群也可以用 kubeconfig 来纳管。
            </div>
          </div>

          <div class="form-item">
            <div class="label">验证结果</div>
            <el-input v-model="verifyText" type="textarea" :rows="5" readonly placeholder="点击“验证”后显示" />
          </div>
        </div>

        <div class="footer">
          <el-button @click="resetForm" plain>重置</el-button>
          <el-button :loading="verifyLoading" @click="doVerify">验证</el-button>
          <el-button type="primary" :loading="saveLoading" :disabled="!canSave" @click="doSave">
            保存
          </el-button>
        </div>

        <div class="hint">
          推荐流程：1）粘贴 kubeconfig → 2）点“验证”确认能连 → 3）点“保存” → 4）在左侧列表点“设为当前”
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import {
  fetchClusters,
  fetchActiveCluster,
  verifyCluster,
  addCluster,
  activateCluster,
  deleteCluster,
  type ClusterRow,
} from '@/api/clusters'

const loading = ref(false)

const clusters = ref<ClusterRow[]>([])
const active = reactive<{ active: ClusterRow | null }>({ active: null })

const form = reactive({
  name: '',
  type: 'managed' as 'managed' | 'self-hosted',
  provider: '' as '' | 'aliyun' | 'tencent' | 'huawei' | 'custom',
  kubeconfig: '',
})

const verifyLoading = ref(false)
const saveLoading = ref(false)
const verifyOk = ref(false)
const verifyText = ref('')

const canSave = computed(() => {
  return form.name.trim().length > 0 && form.kubeconfig.trim().length > 0
})

async function refresh() {
  loading.value = true
  try {
    const [list, act] = await Promise.all([fetchClusters(), fetchActiveCluster()])
    clusters.value = list || []
    active.active = act?.active || null
  } catch (e: any) {
    ElMessage.error('刷新失败：' + (e?.message ?? 'unknown'))
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.name = ''
  form.type = 'managed'
  form.provider = ''
  form.kubeconfig = ''
  verifyText.value = ''
  verifyOk.value = false
}

function fillFromRow(row: ClusterRow) {
  // 这里只能复制展示字段，kubeconfig 不从 list 接口返回（更安全）
  form.name = row.name
  form.type = row.type
  form.provider = (row.provider as any) || ''
  ElMessage.success('已复制名称/类型/厂商到表单（kubeconfig 请重新粘贴）')
}

async function doVerify() {
  verifyLoading.value = true
  verifyOk.value = false
  verifyText.value = ''
  try {
    const resp = await verifyCluster({ kubeconfig: form.kubeconfig })
    verifyText.value = JSON.stringify(resp, null, 2)
    if (resp?.ok) {
      verifyOk.value = true
      ElMessage.success('验证通过')
    } else {
      ElMessage.warning('验证未通过')
    }
  } catch (e: any) {
    verifyText.value = String(e?.message ?? e)
    ElMessage.error('验证失败：' + (e?.message ?? 'unknown'))
  } finally {
    verifyLoading.value = false
  }
}

async function doSave() {
  if (!canSave.value) return
  saveLoading.value = true
  try {
    const resp = await addCluster({
      name: form.name.trim(),
      type: form.type,
      provider: form.provider || '',
      kubeconfig: form.kubeconfig,
    })
    ElMessage.success(`已保存（id=${resp?.id ?? '-'}）`)
    await refresh()
  } catch (e: any) {
    ElMessage.error('保存失败：' + (e?.message ?? 'unknown'))
  } finally {
    saveLoading.value = false
  }
}

async function doActivate(id: number) {
  try {
    await ElMessageBox.confirm(
      '设为当前后，平台所有页面会切换到该集群的数据（节点/工作负载/告警等）。继续？',
      '确认切换',
      { type: 'warning' }
    )
  } catch {
    return
  }

  loading.value = true
  try {
    await activateCluster(id)
    ElMessage.success('已切换为当前集群')
    await refresh()
  } catch (e: any) {
    ElMessage.error('切换失败：' + (e?.message ?? 'unknown'))
  } finally {
    loading.value = false
  }
}

async function doDelete(id: number) {
  try {
    await ElMessageBox.confirm('确认删除该纳管记录？（不会删除云资源）', '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
    })
  } catch {
    return
  }

  loading.value = true
  try {
    await deleteCluster(id)
    ElMessage.success('已删除')
    await refresh()
  } catch (e: any) {
    ElMessage.error('删除失败：' + (e?.message ?? 'unknown'))
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card {
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  background: #fff;
}

.head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
.title {
  font-size: 15px;
  font-weight: 700;
  color: #111827;
}
.sub {
  margin-top: 4px;
  font-size: 12px;
  color: #6b7280;
}
.actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.mr6 {
  margin-right: 6px;
}

.active-box {
  margin-top: 12px;
  padding: 12px;
  border-radius: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
}
.active-label {
  font-size: 12px;
  color: #6b7280;
}
.active-main {
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.active-name {
  font-size: 14px;
  font-weight: 700;
  color: #111827;
}
.active-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.pill {
  font-size: 12px;
  color: #374151;
  border: 1px solid #e5e7eb;
  background: #fff;
  padding: 2px 8px;
  border-radius: 999px;
}
.active-empty {
  margin-top: 8px;
  font-size: 12px;
  color: #6b7280;
}

.grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
@media (max-width: 1100px) {
  .grid {
    grid-template-columns: 1fr;
  }
}

.sec-title {
  font-size: 13px;
  font-weight: 700;
  color: #111827;
  margin-bottom: 10px;
}

.table {
  border-radius: 10px;
  overflow: hidden;
}

.name {
  display: flex;
  align-items: center;
  gap: 6px;
}
.name-text {
  font-weight: 700;
  color: #111827;
}
.muted {
  font-size: 12px;
  color: #6b7280;
  margin-top: 2px;
}

.form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.label {
  font-size: 12px;
  font-weight: 700;
  color: #374151;
}

.footer {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.hint {
  margin-top: 10px;
  font-size: 12px;
  color: #6b7280;
}
.hint.danger {
  color: #dc2626;
}
</style>
