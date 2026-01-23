<!-- view/ai/AiSuggestions.vue -->
<template>
  <div class="page">
    <div class="page-head">
      <div>
        <div class="page-title">智能建议</div>
        <div class="page-subtitle">规则引擎输出建议；支持一键执行（通过 /api/ai/execute）</div>
      </div>

      <div class="head-actions">
        <el-button :loading="loading" @click="run">
          <el-icon class="mr6"><MagicStick /></el-icon>
          生成建议
        </el-button>
        <el-button plain @click="reset">重置</el-button>
      </div>
    </div>

    <el-card shadow="never" class="card">
      <div class="filters">
        <el-select v-model="form.target" class="w200">
          <el-option label="节点 CPU" value="node_cpu" />
          <el-option label="节点内存" value="node_mem" />
          <el-option label="Pod CPU" value="pod_cpu" />
        </el-select>

        <template v-if="form.target !== 'pod_cpu'">
          <el-input v-model="form.node" class="w260" placeholder="节点名，如 k3s-master" clearable />
          <el-input-number v-model="form.threshold" :min="1" :max="100" controls-position="right" />
          <span class="hint">阈值(%)</span>
          <el-input-number v-model="form.sustain_minutes" :min="1" :max="120" controls-position="right" />
          <span class="hint">持续(min)</span>
          <el-input-number v-model="form.horizon_minutes" :min="15" :max="1440" controls-position="right" />
          <span class="hint">预测窗口(min)</span>
          <el-input-number v-model="form.step" :min="5" :max="3600" controls-position="right" />
          <span class="hint">步长(s)</span>
          <el-switch v-model="form.use_llm" active-text="LLM总结" />
        </template>

        <template v-else>
          <el-input v-model="form.namespace" class="w200" placeholder="namespace，如 default" clearable />
          <el-input v-model="form.pod" class="w320" placeholder="pod 名，如 nginx-xxx" clearable />

          <!-- ✅ 新增：扩容策略（线性/阶梯） -->
          <el-select v-model="form.scale_policy" class="w200">
            <el-option label="阶梯扩容（stair）" value="stair" />
            <el-option label="线性扩容（linear）" value="linear" />
          </el-select>
          <span class="hint">扩容策略</span>

          <!-- ✅ 新增：safe_low / safe_high（只对 linear 有意义，也允许显示给用户） -->
          <el-input-number
            v-model="form.safe_low"
            :min="0.1"
            :max="1.2"
            :step="0.05"
            controls-position="right"
            class="w200"
          />
          <span class="hint">safe_low</span>

          <el-input-number
            v-model="form.safe_high"
            :min="0.1"
            :max="1.2"
            :step="0.05"
            controls-position="right"
            class="w200"
          />
          <span class="hint">safe_high</span>

          <el-input-number v-model="form.sustain_minutes" :min="1" :max="120" controls-position="right" />
          <span class="hint">持续(min)</span>
          <el-input-number v-model="form.horizon_minutes" :min="15" :max="1440" controls-position="right" />
          <span class="hint">预测窗口(min)</span>
          <el-input-number v-model="form.step" :min="5" :max="3600" controls-position="right" />
          <span class="hint">步长(s)</span>
          <el-switch v-model="form.use_llm" active-text="LLM总结" />
        </template>
      </div>

      <el-divider />

      <div v-if="resp" class="result">
        <div class="topline">
          <div class="obj">
            <div class="k">对象</div>
            <div class="v">{{ resp.key }}</div>
          </div>
          <div class="risk">
            <div class="k">类型</div>
            <el-tag size="large" :type="targetTagType(resp.target)">
              {{ targetLabel(resp.target) }}
            </el-tag>
          </div>

          <div class="risk">
            <div class="k">总体等级</div>
            <el-tag size="large" :type="overallTagType(overallSeverity)">
              {{ overallSeverity.toUpperCase() }}
            </el-tag>
          </div>
        </div>

        <el-alert
          class="mt12"
          :type="overallAlertType(overallSeverity)"
          show-icon
          :closable="false"
          title="规则引擎结论"
          :description="ruleConclusionText"
        />

        <div v-if="resp?.suggestion_id && !resp.llm_summary" class="mt12">
          <el-button size="small" :loading="summaryLoading" @click="fetchSummary">获取总结</el-button>
        </div>

        <el-alert
          v-if="resp.llm_summary"
          class="mt12"
          type="info"
          show-icon
          :closable="false"
          title="LLM 总结"
          :description="resp.llm_summary"
        />

        <el-table
          v-if="resp.suggestions.length"
          class="mt12"
          :data="visibleSuggestions"
          :row-key="(row) => normalizeSuggestionKey(resp, resp.suggestions.indexOf(row), row)"
          :row-class-name="suggestionRowClass"
          size="small"
          border
        >
          <el-table-column label="Severity" width="120">
            <template #default="{ row }">
              <el-tag :type="severityTagType(row.severity)">{{ row.severity }}</el-tag>
            </template>
          </el-table-column>

          <el-table-column prop="title" label="Title" min-width="220" />

          <el-table-column label="Action" width="200">
            <template #default="{ row }">
              <code class="code">{{ row.action.kind }}</code>
              <div class="mini">
                <span v-if="!isExecutableKind(row.action.kind)">（不可执行）</span>
                <span v-else>（可执行）</span>
              </div>
            </template>
          </el-table-column>

          <el-table-column label="Params" min-width="220">
            <template #default="{ row }">
              <pre class="json">{{ pretty(row.action.params) }}</pre>
            </template>
          </el-table-column>

          <el-table-column label="Rationale" min-width="260">
            <template #default="{ row }">
              <div class="rationale">{{ row.rationale }}</div>
            </template>
          </el-table-column>

          <el-table-column label="Evidence" min-width="260">
            <template #default="{ row }">
              <pre class="json">{{ pretty(row.evidence) }}</pre>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="320" fixed="right">
            <template #default="{ row, $index }">
              <el-button size="small" @click="copySuggestion(row)">复制</el-button>

              <el-button
                size="small"
                type="primary"
                :loading="applyLoading"
                :disabled="!isExecutableKind(row.action.kind)"
                @click="openExecuteDialog(row, resolveRowIndex(row))"
              >
                一键执行
              </el-button>

              <el-button size="small" type="success" plain @click="explain(row)">
                解释
              </el-button>
              <el-button size="small" type="info" plain @click="onIgnore(row)">
                忽略 / 已读
              </el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-else description="暂无建议（可能数据不足或风险较低）" />
      </div>

      <el-empty v-else description="填写参数后点击“生成建议”" />

      <el-divider />

      <div class="history-head">
        <div class="history-title">历史记录</div>
        <div class="history-actions">
          <el-button size="small" plain :disabled="!history.length" @click="clearAllHistory">
            清空全部
          </el-button>
        </div>
      </div>

      <el-empty v-if="!history.length" description="暂无历史记录" />

      <el-collapse v-else v-model="openedHistory" class="mt12">
        <el-collapse-item v-for="h in history" :key="h.id" :name="h.id">
          <template #title>
            <div class="history-row">
              <div class="h-left">
                <strong class="h-time">{{ formatTs(h.ts) }}</strong>
                <el-tag size="small" :type="targetTagType(h.resp.target)">
                  {{ targetLabel(h.resp.target) }}
                </el-tag>
                <span class="h-key">{{ h.resp.key }}</span>
              </div>

              <div class="h-right">
                <el-tag size="small" :type="overallTagType(calcOverall(h.resp))">
                  {{ calcOverall(h.resp).toUpperCase() }}
                </el-tag>

                <el-button size="small" type="danger" plain @click.stop="removeOneHistory(h.id)">
                  删除
                </el-button>
              </div>
            </div>
          </template>

          <el-alert
            :type="overallAlertType(calcOverall(h.resp))"
            show-icon
            :closable="false"
            title="规则引擎结论"
            :description="buildRuleText(h.resp)"
          />

          <el-alert
            v-if="h.resp.llm_summary"
            class="mt12"
            type="info"
            show-icon
            :closable="false"
            title="LLM 总结"
            :description="h.resp.llm_summary"
          />

          <el-table
            v-if="h.resp.suggestions.length"
            class="mt12"
            :data="h.resp.suggestions"
            :row-key="(row) => normalizeSuggestionKey(h.resp, h.resp.suggestions.indexOf(row), row)"
            size="small"
            border
          >
            <el-table-column label="Severity" width="120">
              <template #default="{ row }">
                <el-tag :type="severityTagType(row.severity)">{{ row.severity }}</el-tag>
              </template>
            </el-table-column>

            <el-table-column prop="title" label="Title" min-width="220" />

            <el-table-column label="Action" width="200">
              <template #default="{ row }">
                <code class="code">{{ row.action.kind }}</code>
              </template>
            </el-table-column>

            <el-table-column label="Params" min-width="220">
              <template #default="{ row }">
                <pre class="json">{{ pretty(row.action.params) }}</pre>
              </template>
            </el-table-column>

            <el-table-column label="Rationale" min-width="260">
              <template #default="{ row }">
                <div class="rationale">{{ row.rationale }}</div>
              </template>
            </el-table-column>

            <el-table-column label="Evidence" min-width="260">
              <template #default="{ row }">
                <pre class="json">{{ pretty(row.evidence) }}</pre>
              </template>
            </el-table-column>
          </el-table>

          <el-empty v-else description="暂无建议（可能数据不足或风险较低）" />
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <!-- ✅ 执行弹窗：对齐 /api/ai/execute -->
    <!-- ✅ 执行弹窗：更像运维台 -->
    <el-dialog
      v-model="execOpen"
      width="900px"
      top="6vh"
      :close-on-click-modal="false"
      class="exec-dialog"
    >
      <template #header>
        <div class="exec-header">
          <div class="exec-title">
            一键执行建议
            <el-tag class="ml8" effect="plain" size="small">{{ execKind }}</el-tag>
            <el-tag class="ml6" type="info" effect="plain" size="small">index {{ execIndex }}</el-tag>
          </div>
          <div class="exec-sub">对齐接口：/api/ai/execute（会重新生成建议后按 index 执行）</div>
        </div>
      </template>

      <!-- 执行摘要（关键！） -->
      <el-card shadow="never" class="exec-card">
        <div class="exec-summary">
          <div class="sum-left">
            <div class="sum-label">执行对象</div>
            <div class="sum-value">{{ execSummary.obj }}</div>
          </div>

          <div class="sum-mid">
            <div class="sum-label">执行动作</div>
            <div class="sum-value">{{ execSummary.actionText }}</div>
          </div>

          <div class="sum-right">
            <div class="sum-label">模式</div>
            <el-tag :type="execDryRun ? 'warning' : 'danger'" effect="dark">
              {{ dryRunText }}
            </el-tag>
          </div>
        </div>

        <!-- 可选：展示证据（有就显示，没有就不占位） -->
        <div v-if="execSummary.evidence" class="mt10 evidence">
          <div class="evi-title">关键证据</div>
          <pre class="evi-pre">{{ JSON.stringify(execSummary.evidence, null, 2) }}</pre>
        </div>
      </el-card>

      <div class="mt12" />

      <!-- 基本设置 -->
      <el-form label-width="140px">
        <el-form-item label="执行模式">
          <el-segmented
            v-model="execDryRun"
            :options="[
              { label: '安全执行（Dry-Run）', value: true },
              { label: '真实执行', value: false },
            ]"
          />
          <div class="hint2 ml10">
            {{ execDryRun ? '只记录审计，不改集群' : '会修改集群资源，请确认' }}
          </div>
        </el-form-item>

        <!-- 把 exec_namespace 放小一点 -->
        <el-form-item label="命名空间">
          <el-input v-model="execNamespace" placeholder="default" class="w260" />
        </el-form-item>

        <el-form-item v-if="needExecName(execKind)" label="Deployment">
          <el-input v-model="execName" placeholder="例如 nginx-quickstart" />
        </el-form-item>

        <el-form-item v-if="needExecPod(execKind)" label="Pod">
          <el-input v-model="execPod" placeholder="例如 nginx-xxx-xxxxx" />
        </el-form-item>

        <!-- 资源调整：做成卡片 -->
        <el-form-item v-if="execKind === 'tune_requests_limits'" label="资源覆盖（可选）">
          <el-card shadow="never" class="param-card">
            <div class="param-grid">
              <div class="param-item">
                <div class="param-label">CPU request</div>
                <el-input-number v-model="tuneCpuReqM" :min="1" controls-position="right" class="w220" />
                <el-tag size="small" effect="plain">m</el-tag>
              </div>

              <div class="param-item">
                <div class="param-label">CPU limit</div>
                <el-input-number v-model="tuneCpuLimM" :min="1" controls-position="right" class="w220" />
                <el-tag size="small" effect="plain">m</el-tag>
              </div>

              <div class="param-item">
                <div class="param-label">Mem request</div>
                <el-input-number v-model="tuneMemReqMb" :min="1" controls-position="right" class="w220" />
                <el-tag size="small" effect="plain">Mi</el-tag>
              </div>

              <div class="param-item">
                <div class="param-label">Mem limit</div>
                <el-input-number v-model="tuneMemLimMb" :min="1" controls-position="right" class="w220" />
                <el-tag size="small" effect="plain">Mi</el-tag>
              </div>
            </div>

            <div class="param-tip">
              留空则使用建议 action.params；填写则覆盖发送到 /api/ai/execute（exec_* 覆盖字段）
            </div>
          </el-card>
        </el-form-item>

        <!-- 扩容：同样卡片化 -->
        <el-form-item v-if="execKind === 'scale_deployment'" label="扩容覆盖（可选）">
          <el-card shadow="never" class="param-card">
            <div class="param-grid">
              <div class="param-item">
                <div class="param-label">最终副本数</div>
                <el-input-number v-model="execReplicas" :min="0" controls-position="right" class="w220" />
              </div>
              <div class="param-item">
                <div class="param-label">增加副本数</div>
                <el-input-number v-model="execReplicasDelta" :min="0" controls-position="right" class="w220" />
              </div>
            </div>
            <div class="param-tip">
              填最终副本数优先于 +N；留空则使用建议 action.params
            </div>
          </el-card>
        </el-form-item>

        <!-- 高级参数折叠：把“这接口会重新生成建议”的那些参数收起来 -->
        <el-form-item label="高级（重建建议参数）">
          <el-collapse>
            <el-collapse-item title="展开查看 /api/ai/execute 必须一致的参数">
              <div class="hint3">
                这里用于保证执行时重建建议与页面一致（target / horizon / step / threshold / sustain / policy...）
              </div>
              <!-- 你可以在这里展示只读的当前 form 值 -->
              <div class="kv">
                <div><b>target</b>：{{ resp?.target }}</div>
                <div><b>horizon</b>：{{ form.horizon_minutes }} min</div>
                <div><b>step</b>：{{ form.step }} s</div>
                <div><b>threshold</b>：{{ form.threshold }}</div>
                <div><b>sustain</b>：{{ form.sustain_minutes }} min</div>
                <div v-if="resp?.target==='pod_cpu'"><b>policy</b>：{{ (form as any).scale_policy }} | safe_low {{ (form as any).safe_low }} | safe_high {{ (form as any).safe_high }}</div>
              </div>
            </el-collapse-item>
          </el-collapse>
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="execOpen = false">取消</el-button>
        <el-button
          type="primary"
          :loading="applyLoading"
          @click="doExecute"
        >
          {{ execDryRun ? '审计执行（Dry-Run）' : '确认执行（会改集群）' }}
        </el-button>
      </template>
    </el-dialog>


    <!-- 解释弹窗 -->
    <el-dialog v-model="explainOpen" title="大模型解释" width="760px">
      <el-input v-model="explainText" type="textarea" :rows="12" readonly placeholder="这里显示解释" />
      <template #footer>
        <el-button @click="explainOpen = false">关闭</el-button>
        <el-button type="primary" @click="copyText(explainText)">复制</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import {
  suggestions as aiSuggestions,
  execute as aiExecute,
  suggestionSummary as aiSummary,
  feedback as aiFeedback,
  markSuggestionState,
  fetchSuggestionStates,
  normalizeSuggestionKey,
  explainAiHttpError,
  type SuggestionState
} from '@/api/ai_unified'
import { assistantChat } from '@/api/ai_unified'
import { useAssistantStore } from '@/stores/assistant'
import { storeToRefs } from 'pinia'
import { useAiSuggestionsStore } from '@/stores/aiSuggestions'

type Target = 'node_cpu' | 'node_mem' | 'pod_cpu'
type Severity = 'info' | 'warning' | 'critical'
type ScalePolicy = 'stair' | 'linear'

type ActionKind =
  | 'scale_deployment'
  | 'restart_deployment'
  | 'restart_pod'
  | 'delete_pod'
  | 'no_action'
  | 'scale_hpa'
  | 'add_node'
  | 'cordon_node'
  | 'investigate_logs'
  | 'tune_requests_limits'
  | 'enable_rate_limit'

interface ActionHint {
  kind: ActionKind
  params: Record<string, unknown>
}
interface SuggestionItem {
  severity: Severity
  title: string
  evidence: Record<string, unknown>
  rationale: string
  action: ActionHint
}
interface SuggestionsResp {
  target: Target
  key: string
  suggestions: SuggestionItem[]
  suggestion_id?: string | null
  llm_summary?: string | null
  meta?: Record<string, unknown> | null
}

interface FetchSuggestionsParams {
  target: Target
  node?: string
  namespace?: string
  pod?: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
  threshold?: number
  sustain_minutes?: number
  use_llm?: boolean

  // ✅ 新增：Pod CPU 扩容策略参数（后端 Query）
  scale_policy?: ScalePolicy
  safe_low?: number
  safe_high?: number
}

const tuneCpuReqM = ref<number | null>(null)
const tuneCpuLimM = ref<number | null>(null)
const tuneMemReqMb = ref<number | null>(null)
const tuneMemLimMb = ref<number | null>(null)

const assistantStore = useAssistantStore()

const loading = ref(false)
const summaryLoading = ref(false)
const applyLoading = ref(false)

const sugStore = useAiSuggestionsStore()
const { form, resp, history } = storeToRefs(sugStore)
const rowStates = ref<Record<string, SuggestionState>>({})

const visibleSuggestions = computed(() => {
  const r = resp.value
  if (!r) return []
  return r.suggestions.filter((item, index) => {
    const rowKey = normalizeSuggestionKey(r, index, item)
    return rowStates.value[rowKey] !== 'ignored'
  })
})

/** ✅ 历史折叠默认打开最新一条 */
const openedHistory = ref<string[]>([])

watch(
  () => history.value.map((h) => h.id),
  (ids) => {
    const firstId = ids[0]
    if (typeof firstId === 'string' && firstId && openedHistory.value.length === 0) {
      openedHistory.value = [firstId]
    }
  },
  { immediate: true }
)

/** 当切到 Pod CPU 时，确保策略参数存在且合法（兼容旧 localStorage） */
watch(
  () => form.value.target,
  (t) => {
    if (t === 'pod_cpu') {
      // 限制scale_policy只能是stair或linear
      if (!['stair', 'linear'].includes(form.value.scale_policy)) {
        form.value.scale_policy = 'stair';
      }

      // 处理safe_low的数值合法性
      const low = Number(form.value.safe_low);
      if (!Number.isFinite(low)) {
        form.value.safe_low = 0.6;
      }

      // 处理safe_high的数值合法性
      const high = Number(form.value.safe_high);
      if (!Number.isFinite(high)) {
        form.value.safe_high = 0.7;
      }

      // 确保safe_low < safe_high
      if (form.value.safe_low >= form.value.safe_high) {
        form.value.safe_low = 0.6;
        form.value.safe_high = 0.7;
      }
    }
  },
  { immediate: true }
);

/** =========================
 * Executable helper (对齐后端 _map_action_hint_to_ops_req)
 * ========================= */
function isExecutableKind(kind: string): boolean {
  return ['scale_deployment', 'restart_deployment', 'restart_pod', 'delete_pod', 'tune_requests_limits'].includes(kind)
}
function needExecName(kind: string): boolean {
  return ['scale_deployment', 'restart_deployment', 'tune_requests_limits'].includes(kind)
}
function needExecPod(kind: string): boolean {
  return ['restart_pod', 'delete_pod'].includes(kind)
}
function parseNsPod(key: string): { ns: string; pod: string } {
  const [ns = '', pod = ''] = String(key || '').split('/')
  return { ns, pod }
}
function parseNsName(s: unknown): { ns: string; name: string } {
  const raw = String(s ?? '')
  const [ns = '', name = ''] = raw.split('/')
  return { ns, name }
}

function getWorkloadKind(evidence: Record<string, unknown>): string {
  return typeof (evidence as any).workload_kind === 'string' ? String((evidence as any).workload_kind) : ''
}

function getControllerKind(evidence: Record<string, unknown>): string {
  return typeof (evidence as any).controller_kind === 'string' ? String((evidence as any).controller_kind) : ''
}

function isBarePod(evidence: Record<string, unknown>): boolean {
  const wk = getWorkloadKind(evidence).trim()
  const ck = getControllerKind(evidence).trim()
  const wkUnknown = wk === '' || wk === 'Unknown' || wk === 'None'
  const ckUnknown = ck === '' || ck === 'Unknown' || ck === 'None'
  return wkUnknown && ckUnknown
}

function isControllerExecutable(evidence: Record<string, unknown>): boolean {
  const wk = getWorkloadKind(evidence).trim()
  return wk === 'Deployment' || isBarePod(evidence)
}

function getRowKeyFromResp(r: SuggestionsResp, row: SuggestionItem): string {
  const index = r.suggestions.indexOf(row)
  if (index < 0) return ''
  return normalizeSuggestionKey(r, index, row)
}

function resolveRowIndex(row: SuggestionItem): number {
  const r = resp.value
  if (!r) return -1
  return r.suggestions.indexOf(row)
}

function suggestionRowClass({ row }: { row: SuggestionItem }): string {
  const r = resp.value
  if (!r) return ''
  const rowKey = getRowKeyFromResp(r, row)
  if (!rowKey) return ''
  return rowStates.value[rowKey] === 'read' ? 'row-read' : ''
}

async function syncSuggestionStates(r: SuggestionsResp): Promise<void> {
  const rowKeys = r.suggestions.map((item, index) => normalizeSuggestionKey(r, index, item))
  rowStates.value = {}
  if (!rowKeys.length) return
  try {
    const { data } = await fetchSuggestionStates(rowKeys)
    rowStates.value = data?.states ? { ...data.states } : {}
  } catch (e: unknown) {
    const message = explainAiHttpError(e)
    if (message) ElMessage.error(message)
  }
}

function pickDeploymentFromEvidence(evidence: Record<string, unknown>): { ns: string; name: string } {
  // 1) 优先 evidence.deployment = "ns/name"
  const dep = (evidence as any).deployment
  if (typeof dep === 'string' && dep.includes('/')) {
    return parseNsName(dep)
  }

  // 2) 兜底：namespace + deployment_name（未来你可能这样传）
  const ns = typeof (evidence as any).namespace === 'string' ? (evidence as any).namespace : ''
  const name = typeof (evidence as any).deployment_name === 'string' ? (evidence as any).deployment_name : ''
  return { ns, name }
}


/** =========================
 * Computeds（当前 resp）
 * ========================= */
const overallSeverity = computed<Severity>(() => {
  const list = resp.value?.suggestions ?? []
  if (list.some((s) => s.severity === 'critical')) return 'critical'
  if (list.some((s) => s.severity === 'warning')) return 'warning'
  return 'info'
})

const ruleConclusionText = computed<string>(() => {
  return buildRuleText(resp.value ?? null)
})

function buildRuleText(r: SuggestionsResp | null): string {
  const list = r?.suggestions ?? []
  if (!list.length) return '暂无原因（可能数据不足或风险较低）'
  const picked = [...list].sort((a, b) => sevWeight(b.severity) - sevWeight(a.severity)).slice(0, 2)
  return picked.map((s) => `${s.title}：${s.rationale}`).join('；')
}
function sevWeight(s: Severity): number {
  if (s === 'critical') return 3
  if (s === 'warning') return 2
  return 1
}
function calcOverall(r: SuggestionsResp): Severity {
  const list = r.suggestions ?? []
  if (list.some((s) => s.severity === 'critical')) return 'critical'
  if (list.some((s) => s.severity === 'warning')) return 'warning'
  return 'info'
}

/** =========================
 * UI Helpers
 * ========================= */
function targetLabel(t: Target): string {
  if (t === 'node_cpu') return '节点 CPU'
  if (t === 'node_mem') return '节点内存'
  return 'Pod CPU'
}
function targetTagType(t: Target): 'success' | 'warning' | 'info' {
  if (t === 'node_cpu') return 'success'
  if (t === 'node_mem') return 'warning'
  return 'info'
}
function severityTagType(level: Severity): 'success' | 'warning' | 'danger' | 'info' {
  if (level === 'critical') return 'danger'
  if (level === 'warning') return 'warning'
  return 'success'
}
function overallTagType(level: Severity): 'success' | 'warning' | 'danger' | 'info' {
  return severityTagType(level)
}
function overallAlertType(level: Severity): 'success' | 'warning' | 'error' | 'info' {
  if (level === 'critical') return 'error'
  if (level === 'warning') return 'warning'
  return 'success'
}
function pretty(v: unknown): string {
  try {
    return JSON.stringify(v ?? {}, null, 2)
  } catch {
    return String(v)
  }
}
function formatTs(ts: number): string {
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return String(ts)
  }
}
function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}
/** =========================
 * Actions
 * ========================= */
function reset(): void {
  sugStore.reset()
  rowStates.value = {}
  ElMessage.success('已重置')
}

async function run(): Promise<void> {
  loading.value = true
  try {
    const params: FetchSuggestionsParams = {
      target: form.value.target,
      use_llm: form.value.use_llm,
      sustain_minutes: form.value.sustain_minutes,
      step: form.value.step,
      horizon_minutes: form.value.horizon_minutes,
      history_minutes: 240
    }

    if (form.value.target === 'pod_cpu') {
      params.namespace = form.value.namespace
      params.pod = form.value.pod

      // ✅ 把策略参数带上（后端会用于 rules.linear）
      params.scale_policy = (form.value as any).scale_policy as ScalePolicy
      params.safe_low = Number((form.value as any).safe_low)
      params.safe_high = Number((form.value as any).safe_high)
    } else {
      params.node = form.value.node
      params.threshold = form.value.threshold
    }

    const { data } = await aiSuggestions(params as any)
    const normalized = normalizeSuggestionsResp(data)

    sugStore.pushHistory(normalized)
    openedHistory.value = history.value[0]?.id ? [history.value[0].id] : []

    assistantStore.setLastSuggestions(normalized as any)
    await syncSuggestionStates(normalized)
    ElMessage.success('已生成建议')
  } catch (e: unknown) {
    const message = explainAiHttpError(e)
    if (message) ElMessage.error(message)
  } finally {
    loading.value = false
  }
}

async function fetchSummary(): Promise<void> {
  if (!resp.value?.suggestion_id) {
    ElMessage.warning('请先生成建议')
    return
  }
  summaryLoading.value = true
  try {
    const { data } = await aiSummary({ suggestion_id: resp.value.suggestion_id })
    if (resp.value) resp.value.llm_summary = data.llm_summary
  } catch (e: unknown) {
    const message = explainAiHttpError(e)
    if (message) ElMessage.error(message)
  } finally {
    summaryLoading.value = false
  }
}

async function removeOneHistory(id: string): Promise<void> {
  try {
    await ElMessageBox.confirm('确定删除这条历史记录吗？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消'
    })
    sugStore.removeHistory(id)
    ElMessage.success('已删除')
  } catch {}
}

async function clearAllHistory(): Promise<void> {
  try {
    await ElMessageBox.confirm('确定清空全部历史记录吗？此操作不可恢复。', '清空确认', {
      type: 'warning',
      confirmButtonText: '清空',
      cancelButtonText: '取消'
    })
    sugStore.clearHistory()
    openedHistory.value = []
    ElMessage.success('已清空')
  } catch {}
}

/** =========================
 * Normalize (unknown -> typed)
 * ========================= */
function normalizeSuggestionsResp(input: unknown): SuggestionsResp {
  if (!isObject(input)) {
    return { target: 'node_cpu', key: '-', suggestions: [], suggestion_id: null, llm_summary: null, meta: null }
  }

  const target = (typeof (input as any).target === 'string' ? (input as any).target : 'node_cpu') as Target
  const key = typeof (input as any).key === 'string' ? (input as any).key : '-'
  const suggestion_id =
    typeof (input as any).suggestion_id === 'string' ? (input as any).suggestion_id : null
  const llm_summary = typeof (input as any).llm_summary === 'string' ? (input as any).llm_summary : null
  const meta = isObject((input as any).meta) ? ((input as any).meta as Record<string, unknown>) : null

  const suggestionsRaw = Array.isArray((input as any).suggestions) ? ((input as any).suggestions as unknown[]) : []
  const suggestions: SuggestionItem[] = suggestionsRaw
    .map((x: unknown) => toSuggestionItem(x))
    .filter((x: SuggestionItem | null): x is SuggestionItem => x !== null)

  return { target, key, suggestions, suggestion_id, llm_summary, meta }
}

function toSuggestionItem(x: unknown): SuggestionItem | null {
  if (!isObject(x)) return null

  const severity = (typeof (x as any).severity === 'string' ? (x as any).severity : 'info') as Severity
  const title = typeof (x as any).title === 'string' ? (x as any).title : '(no title)'
  const rationale = typeof (x as any).rationale === 'string' ? (x as any).rationale : ''
  const evidence = isObject((x as any).evidence) ? ((x as any).evidence as Record<string, unknown>) : {}

  const actionObj = isObject((x as any).action) ? (x as any).action : {}
  const kind = (typeof (actionObj as any).kind === 'string' ? (actionObj as any).kind : 'no_action') as ActionKind
  const params = isObject((actionObj as any).params) ? ((actionObj as any).params as Record<string, unknown>) : {}

  const sevOk: Severity = severity === 'critical' || severity === 'warning' || severity === 'info' ? severity : 'info'

  return {
    severity: sevOk,
    title,
    evidence,
    rationale,
    action: { kind, params }
  }
}

async function copySuggestion(row: SuggestionItem): Promise<void> {
  await navigator.clipboard.writeText(JSON.stringify(row, null, 2))
  ElMessage.success('已复制')
}

async function copyText(t: string): Promise<void> {
  if (!t) return
  await navigator.clipboard.writeText(t)
  ElMessage.success('已复制')
}

/** =========================
 * ✅ Execute dialog（核心）
 * ========================= */
const execOpen = ref(false)
const execDryRun = ref(true)
const execIndex = ref(0)
const execKind = ref<ActionKind>('no_action')

const execNamespace = ref('default')
const execName = ref('')
const execPod = ref('')

// scale extra params（可选）
const execReplicas = ref<number | null>(null)
const execReplicasDelta = ref<number | null>(1)


const execSummary = computed(() => {
  const r = resp.value
  const kind = execKind.value

  const ns = execNamespace.value || 'default'
  const nameOrPod =
    kind === 'tune_requests_limits' || kind === 'scale_deployment' || kind === 'restart_deployment'
      ? execName.value
      : execPod.value

  const obj =
    needExecName(kind) ? `${ns}/${nameOrPod || '-' } (Deployment)` :
    needExecPod(kind) ? `${ns}/${nameOrPod || '-' } (Pod)` :
    `${ns}/${nameOrPod || '-'}`

  // 🌟 关键修复：显式声明 actionText 为 string 类型，而非默认的 ActionKind
  let actionText: string = kind; // 初始值用 kind 标识，后续替换为中文描述
  if (kind === 'scale_deployment') {
    const delta = execReplicasDelta.value
    const final = execReplicas.value
    actionText = final != null ? `扩容到 ${final} 副本` : `扩容 +${delta ?? 0} 副本`
  }
  if (kind === 'tune_requests_limits') {
    const parts: string[] = []
    if (tuneCpuReqM.value != null) parts.push(`CPU request ${tuneCpuReqM.value}m`)
    if (tuneCpuLimM.value != null) parts.push(`CPU limit ${tuneCpuLimM.value}m`)
    if (tuneMemReqMb.value != null) parts.push(`Mem request ${tuneMemReqMb.value}Mi`)
    if (tuneMemLimMb.value != null) parts.push(`Mem limit ${tuneMemLimMb.value}Mi`)
    actionText = parts.length ? `调整资源：${parts.join('，')}` : '调整资源（未填写覆盖值）'
  }

  // 证据（如果你 resp.suggestions 里能取到当前行 item，就更完整；先兜底）
  const evidence = (() => {
    const item = r?.suggestions?.[execIndex.value] // 你如果没有，就删掉这段
    return item?.evidence || null
  })()

  return { obj, actionText, evidence }
})

const dryRunText = computed(() => (execDryRun.value ? '安全执行（Dry-Run）' : '真实执行'))


function openExecuteDialog(row: SuggestionItem, index: number) {
  const kind = row.action.kind
  if (!isExecutableKind(kind)) {
    ElMessage.warning(`该建议不可执行：${kind}`)
    return
  }
  if (!isControllerExecutable(row.evidence || {})) {
    ElMessage.warning('不支持该控制器一键执行')
    return
  }
  if (index < 0) {
    ElMessage.warning('建议索引无效')
    return
  }

  execIndex.value = index
  execKind.value = kind as ActionKind
  execDryRun.value = true

  // reset（先清空，再回填）
  execNamespace.value = 'default'
  execName.value = ''
  execPod.value = ''
  execReplicas.value = null
  execReplicasDelta.value = 1
  tuneCpuReqM.value = null
  tuneCpuLimM.value = null
  tuneMemReqMb.value = null
  tuneMemLimMb.value = null

  const r = resp.value

  // ✅ pod_cpu 页面下，先回填 namespace（对 deployment 动作也有用）
  if (r?.target === 'pod_cpu') {
    const { ns, pod } = parseNsPod(r.key)
    execNamespace.value = form.value.namespace || ns || 'default'
    // 只有 pod 动作才需要 pod
    if (needExecPod(kind)) execPod.value = form.value.pod || pod || ''
  }

  // ✅ 再从 evidence 里自动填 exec_name（deployment）
  if (needExecName(kind)) {
    const picked = pickDeploymentFromEvidence(row.evidence || {})
    if (picked.ns) execNamespace.value = picked.ns
    if (picked.name) execName.value = picked.name
  }

  // ✅ 如果后端 hint.params 里本来就带了建议值，把它带到输入框里（方便你编辑）
  const p: any = row.action.params || {}

  if (kind === 'scale_deployment') {
    if (p.replicas != null) execReplicas.value = Number(p.replicas)
    if (p.replicas_delta != null) execReplicasDelta.value = Number(p.replicas_delta)
  }

  if (kind === 'tune_requests_limits') {
    if (p.cpu_request_m != null) tuneCpuReqM.value = Number(p.cpu_request_m)
    if (p.cpu_limit_m != null) tuneCpuLimM.value = Number(p.cpu_limit_m)
    if (p.mem_request_mb != null) tuneMemReqMb.value = Number(p.mem_request_mb)
    if (p.mem_limit_mb != null) tuneMemLimMb.value = Number(p.mem_limit_mb)
  }

  execOpen.value = true
}




async function doExecute(): Promise<void> {
  const r = resp.value
  if (!r) return

  const kind = execKind.value
  if (!isExecutableKind(kind)) {
    ElMessage.warning(`不可执行：${kind}`)
    return
  }

  // 前端先校验必填字段，避免后端 500
  if (needExecName(kind) && !execName.value) {
    ElMessage.warning('请填写 exec_name（Deployment 名称）')
    return
  }
  if (needExecPod(kind) && !execPod.value) {
    ElMessage.warning('请填写 exec_pod（Pod 名称）')
    return
  }

  // 基础参数：用于后端重新 build_suggestions（必须与当前表单一致）
  const params: any = {
    target: r.target,
    suggestion_index: execIndex.value,
    expected_kind: execKind.value,
    dry_run: execDryRun.value,
    history_minutes: 240,
    horizon_minutes: form.value.horizon_minutes,
    step: form.value.step,
    sustain_minutes: form.value.sustain_minutes,
    threshold: form.value.threshold,
    suggestion_id: r.suggestion_id || undefined,
  }

  if (r.target === 'pod_cpu') {
    params.namespace = form.value.namespace
    params.pod = form.value.pod
    params.scale_policy = (form.value as any).scale_policy
    params.safe_low = Number((form.value as any).safe_low)
    params.safe_high = Number((form.value as any).safe_high)
  } else {
    params.node = form.value.node
  }

  // 执行动作用对象（exec_*）
  params.exec_namespace = execNamespace.value || 'default'
  if (needExecName(kind)) params.exec_name = execName.value
  if (needExecPod(kind)) params.exec_pod = execPod.value

  // ✅ 把“弹窗编辑参数”用 action.params 的同名字段发给后端（便于后端覆盖 hint.params）
  if (kind === 'scale_deployment') {
    // 用 replicas / replicas_delta（不要用 exec_replicas）
    if (execReplicas.value != null) params.replicas = Number(execReplicas.value)
    if (execReplicasDelta.value != null) params.replicas_delta = Number(execReplicasDelta.value)
  }

  if (kind === 'tune_requests_limits') {
    // 用 cpu_request_m / cpu_limit_m / mem_request_mb / mem_limit_mb（不要用 exec_cpu_request_m）
    if (tuneCpuReqM.value != null) params.cpu_request_m = Number(tuneCpuReqM.value)
    if (tuneCpuLimM.value != null) params.cpu_limit_m = Number(tuneCpuLimM.value)
    if (tuneMemReqMb.value != null) params.mem_request_mb = Number(tuneMemReqMb.value)
    if (tuneMemLimMb.value != null) params.mem_limit_mb = Number(tuneMemLimMb.value)
  }

  applyLoading.value = true
  try {
    const { data } = await aiExecute(params)
    ElMessage.success(data.detail || '已执行')
    execOpen.value = false
    await postFeedback('success')
  } catch (e: unknown) {
    const message = explainAiHttpError(e) || '执行失败'
    if (message) ElMessage.error(message)
    await postFeedback('fail', message)
  } finally {
    applyLoading.value = false
  }
}

async function onIgnore(row: SuggestionItem): Promise<void> {
  const r = resp.value
  if (!r) return
  const rowKey = getRowKeyFromResp(r, row)
  if (!rowKey) return
  let status: SuggestionState | null = null
  try {
    await ElMessageBox.confirm('选择处理方式', '标记建议', {
      type: 'warning',
      confirmButtonText: '忽略',
      cancelButtonText: '已读',
      distinguishCancelAndClose: true
    })
    status = 'ignored'
  } catch (action) {
    if (action === 'cancel') {
      status = 'read'
    } else {
      return
    }
  }
  if (!status) return
  try {
    await markSuggestionState(rowKey, status)
    rowStates.value[rowKey] = status
    if (status === 'ignored') {
      ElMessage.success('已忽略该建议')
    } else {
      ElMessage.success('已标记为已读')
    }
  } catch (e) {
    const message = explainAiHttpError(e)
    if (message) ElMessage.error(message)
  }
}

async function postFeedback(outcome: 'success' | 'fail' | 'ignored', detail?: string): Promise<void> {
  const r = resp.value
  if (!r) return
  try {
    await aiFeedback({
      target: r.target,
      key: r.key,
      action_kind: execKind.value,
      outcome,
      detail,
      suggestion_id: r.suggestion_id ?? undefined
    })
  } catch (e) {
    console.warn('feedback failed', e)
  }
}


/** =========================
 * Explain (LLM)
 * ========================= */
const explainOpen = ref(false)
const explainText = ref('')

function buildAssistantContextFromResp(r: SuggestionsResp): Record<string, unknown> {
  if (r.target === 'pod_cpu') {
    const { ns, pod } = parseNsPod(r.key)
    return { target: r.target, key: r.key, namespace: ns, pod }
  }
  return { target: r.target, key: r.key, node: r.key }
}

async function explain(row: SuggestionItem): Promise<void> {
  explainOpen.value = true
  explainText.value = '生成中...'

  try {
    const r = resp.value
    const ctxObj = r ? buildAssistantContextFromResp(r) : {}

    const contextJson = r
      ? JSON.stringify(
          {
            ...ctxObj,
            overall: overallSeverity.value,
            meta: r.meta ?? {},
            suggestion: row
          },
          null,
          2
        )
      : 'no context'

    const prompt =
      `请用简洁中文解释这条智能建议，说明：\n` +
      `1) 为什么会触发；2) 证据是什么；3) 我该怎么验证（给3步）；4) 如果要执行动作，风险点与回滚建议。\n\n` +
      `上下文(JSON)：\n${contextJson}\n`

    const { data } = await assistantChat({
      message: prompt,
      page: '/ai/suggestions',
      context: {
        ...ctxObj,
        threshold: form.value.threshold,
        sustain_minutes: form.value.sustain_minutes,
        horizon_minutes: form.value.horizon_minutes,
        step: form.value.step,

        // ✅ Pod CPU 时把策略参数也给助手看（方便解释）
        scale_policy: (form.value as any).scale_policy,
        safe_low: (form.value as any).safe_low,
        safe_high: (form.value as any).safe_high
      }
    })

    explainText.value = typeof (data as any)?.reply === 'string' ? (data as any).reply : '（大模型未返回内容）'
  } catch (e: unknown) {
    const message = explainAiHttpError(e) || '解释失败（请先接通 deepseek 代理接口）'
    explainText.value = message
  }
}
</script>

<style scoped>
/* ===================== 页面基础（保留你的） ===================== */
.page {
  padding: 16px;
}

.page-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}

.page-title {
  font-size: 20px;
  font-weight: 800;
}

.page-subtitle {
  color: #8a8f98;
  margin-top: 4px;
  font-size: 13px;
}

.head-actions {
  display: flex;
  gap: 10px;
}

.card {
  border-radius: 12px;
}

.filters {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.hint {
  color: #8a8f98;
  font-size: 12px;
  margin-left: -6px;
  margin-right: 8px;
}

.result .topline {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
}

.obj,
.risk {
  display: flex;
  gap: 8px;
  align-items: center;
}

.k {
  color: #8a8f98;
  font-size: 12px;
}

.v {
  font-weight: 700;
}

.code {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 6px;
  font-size: 12px;
}

.mini {
  font-size: 12px;
  color: #8a8f98;
}

.json {
  background: #0b1220;
  color: #d7e0ef;
  padding: 8px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.35;
  overflow: auto;
  max-height: 160px;
}

.rationale {
  font-size: 13px;
  line-height: 1.55;
}

.mt12 {
  margin-top: 12px;
}

.mt10 {
  margin-top: 10px;
}

.mr6 {
  margin-right: 6px;
}

.ml6 {
  margin-left: 6px;
}

.ml8 {
  margin-left: 8px;
}

.w200 {
  width: 200px;
}

.w220 {
  width: 200px;
}

.w240 {
  width: 240px;
}

.w260 {
  width: 260px;
}

.w320 {
  width: 320px;
}

.history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.history-title {
  font-weight: 800;
}

.history-actions {
  display: flex;
  gap: 8px;
}

.history-row {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.h-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.h-time {
  font-weight: 700;
}

.h-key {
  color: #2b2f36;
  max-width: 520px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.h-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ===================== ✅ 执行弹窗（新增：符合我那套） ===================== */

/* 给 el-dialog 加 class="exec-dialog" */
.exec-dialog :deep(.el-dialog) {
  border-radius: 14px;
  overflow: hidden;
}

.exec-dialog :deep(.el-dialog__header) {
  padding: 16px 18px 10px 18px;
  margin-right: 0;
}

.exec-dialog :deep(.el-dialog__body) {
  padding: 14px 18px 18px 18px;
}

.exec-dialog :deep(.el-dialog__footer) {
  padding: 12px 18px 16px 18px;
}

/* header 区 */
.exec-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.exec-title {
  font-size: 16px;
  font-weight: 800;
  display: flex;
  align-items: center;
  gap: 8px;
}

.exec-sub {
  font-size: 12px;
  color: #8a8f98;
}

/* 摘要卡片 */
.exec-card {
  border-radius: 12px;
  border: 1px solid #ebeef5;
}

.exec-summary {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.sum-left,
.sum-mid {
  flex: 1;
  min-width: 0;
}

.sum-right {
  width: 220px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.sum-label {
  font-size: 12px;
  color: #8a8f98;
}

.sum-value {
  font-size: 14px;
  font-weight: 700;
  margin-top: 3px;
  color: #2b2f36;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 证据展示（pre） */
.evidence {
  margin-top: 10px;
}

.evi-title {
  font-size: 12px;
  color: #8a8f98;
  margin-bottom: 6px;
}

.evi-pre {
  background: #0b1220;
  color: #cbd5e1;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 1.4;
  overflow: auto;
  max-height: 180px;
}

/* 参数卡片（资源/扩容） */
.param-card {
  width: 100%;
  border-radius: 12px;
  border: 1px solid #ebeef5;
  background: #fbfcfe;
  padding: 12px;
}

.param-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.param-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.param-label {
  width: 92px;
  font-size: 12px;
  color: #6b7280;
  flex-shrink: 0;
}

.param-tip {
  margin-top: 10px;
  font-size: 12px;
  color: #8a8f98;
  line-height: 1.45;
}

.hint2 {
  font-size: 12px;
  color: #8a8f98;
}

.hint3 {
  font-size: 12px;
  color: #8a8f98;
  margin-bottom: 8px;
  line-height: 1.45;
}

.kv {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: #374151;
}

.kv b {
  color: #111827;
}

/* 建议已读状态 */
.row-read td {
  color: #9ca3af;
}

.row-read .el-tag {
  opacity: 0.6;
}

/* 小分割与间距 */
.divider-soft {
  height: 1px;
  background: #ebeef5;
  margin: 12px 0;
}

/* 响应式：窄屏弹窗单列 */
@media (max-width: 920px) {
  .exec-summary {
    flex-direction: column;
  }
  .sum-right {
    width: 100%;
    align-items: flex-start;
  }
  .param-grid {
    grid-template-columns: 1fr;
  }
}
</style>
