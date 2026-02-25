<!-- src/views/Settings/OpsSettings.vue -->
<template>
  <div class="page">
    <div class="page-head">
      <div>
        <div class="page-title">系统设置</div>
        <div class="page-subtitle">环境配置（DB 覆盖 .env / settings）。Secret 配置不会回显明文。</div>
      </div>

      <div class="actions">
        <el-button :loading="loading" @click="load">刷新</el-button>
        <el-button type="primary" :loading="saving" @click="saveAll">保存更改</el-button>
      </div>
    </div>

    <el-card shadow="never" class="card">
      <div class="toolbar">
        <el-input v-model="kw" placeholder="搜索 key / 描述" clearable class="w320" />
        <el-switch v-model="onlyChanged" inline-prompt active-text="只看改动" inactive-text="全部" />
      </div>

      <el-table :data="filtered" size="small" border>
        <el-table-column prop="k" label="Key" min-width="240" />
        <el-table-column prop="desc" label="说明" min-width="320" />
        <el-table-column prop="type" label="类型" width="90" />

        <el-table-column label="来源" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.source === 'db' ? 'warning' : 'info'">
              {{ row.source }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="当前值" min-width="360">
          <template #default="{ row }">
            <!-- secret：不回显，输入新值才会改 -->
            <template v-if="row.secret">
              <div class="secret-row">
                <el-tag size="small" :type="row.has_value ? 'success' : 'info'">
                  {{ row.has_value ? '已设置' : '未设置' }}
                </el-tag>

                <el-input
                  v-model="draft[row.k]"
                  type="password"
                  show-password
                  clearable
                  placeholder="输入新值以更新；留空=不改；清空覆盖=点恢复默认"
                  class="w240"
                />
              </div>
            </template>

            <!-- bool：统一用 switch（关键：toBool + 回写 boolean） -->
            <template v-else-if="row.type === 'bool'">
              <el-tooltip
                v-if="row.k === PROMQL_FREE_KEY"
                content="开启后允许任意 PromQL（仍受时间范围/step/points 限制）；关闭则启用白名单校验"
                placement="top"
              >
                <el-switch
                  :model-value="toBool(draft[row.k])"
                  :disabled="loading || saving"
                  inline-prompt
                  active-text="开启"
                  inactive-text="关闭"
                  @update:model-value="(v:boolean) => (draft[row.k] = v)"
                />
              </el-tooltip>

              <el-switch
                v-else
                :model-value="toBool(draft[row.k])"
                :disabled="loading || saving"
                @update:model-value="(v:boolean) => (draft[row.k] = v)"
              />
            </template>

            <!-- choices：下拉 -->
            <template v-else-if="row.choices && row.choices.length">
              <el-select v-model="draft[row.k]" class="w240" filterable>
                <el-option v-for="c in row.choices" :key="c" :label="c" :value="c" />
              </el-select>
            </template>

            <!-- int/float/str：input -->
            <template v-else>
              <el-input v-model="draft[row.k]" clearable class="w240" />
            </template>

            <div class="hint">
              <span class="muted">default:</span>
              <code>{{ row.default ?? '' }}</code>
              <span v-if="row.example" class="muted ml8">example:</span>
              <code v-if="row.example">{{ row.example }}</code>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-tag v-if="isChanged(row)" size="small" type="success">已修改</el-tag>
            <el-tag v-else size="small" type="info">未修改</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="resetOne(row)">恢复默认</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="foot muted">提示：secret 不会回显明文；要更新请在“当前值”输入新 secret 后保存。</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchOpsConfig, saveOpsConfig, deleteOpsConfigKey, type ConfigItem } from '@/api/opsConfig'

const loading = ref(false)
const saving = ref(false)

const kw = ref('')
const onlyChanged = ref(false)

const items = ref<ConfigItem[]>([])
const draft = reactive<Record<string, any>>({})
const baseline = reactive<Record<string, any>>({})

const PROMQL_FREE_KEY = 'PROMQL_FREE_ENABLED'

function toBool(v: any): boolean {
  if (typeof v === 'boolean') return v
  if (typeof v === 'number') return v !== 0
  if (typeof v === 'string') {
    const s = v.trim().toLowerCase()
    if (s === '1' || s === 'true' || s === 'yes' || s === 'y' || s === 'on') return true
    if (s === '0' || s === 'false' || s === 'no' || s === 'n' || s === 'off' || s === '') return false
  }
  return false
}

function normalizeRowValue(row: ConfigItem) {
  if (row.secret) return row.value || ''
  if (row.type === 'bool') return toBool(row.value)
  return row.value
}

async function load() {
  loading.value = true
  try {
    const resp = await fetchOpsConfig()
    const list: ConfigItem[] = resp?.data?.items || []
    items.value = list

    for (const row of list) {
      const v = normalizeRowValue(row)
      baseline[row.k] = v
      draft[row.k] = row.secret ? '' : v
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function isChanged(row: ConfigItem) {
  if (row.secret) {
    return !!(draft[row.k] && String(draft[row.k]).trim())
  }
  if (row.type === 'bool') {
    return toBool(draft[row.k]) !== toBool(baseline[row.k])
  }
  return draft[row.k] !== baseline[row.k]
}

const filtered = computed(() => {
  const s = kw.value.trim().toLowerCase()
  let arr = items.value
  if (s) {
    arr = arr.filter((x) => x.k.toLowerCase().includes(s) || (x.desc || '').toLowerCase().includes(s))
  }
  if (onlyChanged.value) {
    arr = arr.filter((x) => isChanged(x))
  }
  return arr
})

async function saveAll() {
  const payload: Record<string, any> = {}

  for (const row of items.value) {
    if (!isChanged(row)) continue

    if (row.secret) {
      payload[row.k] = String(draft[row.k]).trim()
      continue
    }

    if (row.type === 'bool') {
      payload[row.k] = toBool(draft[row.k]) // ✅ 强制提交 boolean
      continue
    }

    payload[row.k] = draft[row.k]
  }

  if (Object.keys(payload).length === 0) {
    ElMessage.info('没有可保存的更改')
    return
  }

  saving.value = true
  try {
    const resp = await saveOpsConfig(payload)
    const ok = resp?.data?.ok
    if (!ok) {
      ElMessage.error('保存失败：' + JSON.stringify(resp?.data))
      return
    }
    ElMessage.success('保存成功')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function resetOne(row: ConfigItem) {
  const confirm = await ElMessageBox.confirm(`确定将 ${row.k} 恢复默认吗？（会删除 DB 覆盖）`, '恢复默认', {
    type: 'warning',
  }).catch(() => false)

  if (!confirm) return

  try {
    await deleteOpsConfigKey(row.k)
    ElMessage.success('已恢复默认')
    await load()
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

load()
</script>

<style scoped>
.page { padding: 6px 0; }
.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.page-title { font-size: 18px; font-weight: 800; }
.page-subtitle { font-size: 12px; color: #64748b; margin-top: 6px; }
.actions { display: flex; gap: 8px; }
.card { border-radius: 14px; }
.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}
.w320 { width: 320px; }
.w240 { width: 240px; }
.secret-row { display: flex; gap: 10px; align-items: center; }
.hint { margin-top: 6px; font-size: 12px; color: #64748b; }
.muted { color: #64748b; }
.ml8 { margin-left: 8px; }
.foot { margin-top: 10px; font-size: 12px; }
code { background: rgba(15,23,42,0.06); padding: 2px 6px; border-radius: 6px; }
</style>
