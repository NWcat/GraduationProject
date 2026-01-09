// src/stores/aiSuggestions.ts
import { defineStore } from 'pinia'

export type Target = 'node_cpu' | 'node_mem' | 'pod_cpu'
export type Severity = 'info' | 'warning' | 'critical'
export type ScalePolicy = 'stair' | 'linear'

/** ✅ 与后端 /api/ai/suggestions & /execute 对齐（展示层超集） */
export type ActionKind =
  | 'scale_hpa'
  | 'scale_deployment'
  | 'restart_deployment'
  | 'add_node'
  | 'cordon_node'
  | 'restart_pod'
  | 'delete_pod'
  | 'investigate_logs'
  | 'tune_requests_limits'
  | 'enable_rate_limit'
  | 'no_action'

export interface ActionHint {
  kind: ActionKind
  params: Record<string, unknown>
}

export interface SuggestionItem {
  severity: Severity
  title: string
  evidence: Record<string, unknown>
  rationale: string
  action: ActionHint
}

export interface SuggestionsResp {
  target: Target
  key: string
  suggestions: SuggestionItem[]
  llm_summary?: string | null
  meta?: Record<string, unknown> | null
}

export interface SuggestionsForm {
  target: Target
  node: string
  namespace: string
  pod: string
  threshold: number
  sustain_minutes: number
  horizon_minutes: number
  step: number
  use_llm: boolean

  /** ✅ Pod CPU 扩容策略参数（后端 Query: scale_policy/safe_low/safe_high） */
  scale_policy: ScalePolicy
  safe_low: number
  safe_high: number
}

export interface SuggestionHistoryItem {
  id: string
  ts: number
  form: SuggestionsForm
  resp: SuggestionsResp
}

const LS_KEY = 'kube-guard-ai-suggestions-v1'

/* ---------------- utils ---------------- */

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null
}
function isString(v: unknown): v is string {
  return typeof v === 'string'
}
function isNumber(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}
function isBoolean(v: unknown): v is boolean {
  return typeof v === 'boolean'
}
function isTarget(v: unknown): v is Target {
  return v === 'node_cpu' || v === 'node_mem' || v === 'pod_cpu'
}
function isSeverity(v: unknown): v is Severity {
  return v === 'info' || v === 'warning' || v === 'critical'
}
function isScalePolicy(v: unknown): v is ScalePolicy {
  return v === 'stair' || v === 'linear'
}
function isActionKind(v: unknown): v is ActionKind {
  return [
    'scale_hpa',
    'scale_deployment',
    'restart_deployment',
    'add_node',
    'cordon_node',
    'restart_pod',
    'delete_pod',
    'investigate_logs',
    'tune_requests_limits',
    'enable_rate_limit',
    'no_action'
  ].includes(v as string)
}

function safeJsonParse(raw: string): unknown | null {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function toPlainJson<T>(v: T): T {
  return JSON.parse(JSON.stringify(v)) as T
}

function uuid(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`
}

/* ---------------- defaults ---------------- */

const defaultForm: SuggestionsForm = {
  target: 'node_cpu',
  node: 'k3s-master',
  namespace: 'default',
  pod: '',
  threshold: 85,
  sustain_minutes: 15,
  horizon_minutes: 120,
  step: 60,
  use_llm: true,

  // ✅ 新增默认：阶梯策略
  scale_policy: 'stair',
  safe_low: 0.6,
  safe_high: 0.7
}

function numOr(v: unknown, fb: number): number {
  return isNumber(v) ? v : fb
}
function strOr(v: unknown, fb: string): string {
  return isString(v) ? v : fb
}
function boolOr(v: unknown, fb: boolean): boolean {
  return isBoolean(v) ? v : fb
}
function recordOr(v: unknown): Record<string, unknown> {
  return isObject(v) ? v : {}
}

/* ---------------- coercers ---------------- */

function coerceForm(v: unknown): SuggestionsForm {
  if (!isObject(v)) return { ...defaultForm }

  // 纠正 safe_low/safe_high 的边界与关系（避免老缓存/手滑导致后端参数异常）
  let safeLow = numOr((v as any).safe_low, defaultForm.safe_low)
  let safeHigh = numOr((v as any).safe_high, defaultForm.safe_high)

  if (!Number.isFinite(safeLow)) safeLow = defaultForm.safe_low
  if (!Number.isFinite(safeHigh)) safeHigh = defaultForm.safe_high

  // 合理区间（与后端 Query 约束一致，给更宽松的容错）
  safeLow = Math.max(0.1, Math.min(1.2, safeLow))
  safeHigh = Math.max(0.1, Math.min(1.2, safeHigh))
  if (safeLow >= safeHigh) {
    // 保底：拉开一点
    safeLow = Math.min(safeLow, 0.6)
    safeHigh = Math.max(safeHigh, 0.7)
    if (safeLow >= safeHigh) {
      safeLow = 0.6
      safeHigh = 0.7
    }
  }

  return {
    target: isTarget((v as any).target) ? ((v as any).target as Target) : defaultForm.target,
    node: strOr((v as any).node, defaultForm.node),
    namespace: strOr((v as any).namespace, defaultForm.namespace),
    pod: strOr((v as any).pod, defaultForm.pod),
    threshold: numOr((v as any).threshold, defaultForm.threshold),
    sustain_minutes: numOr((v as any).sustain_minutes, defaultForm.sustain_minutes),
    horizon_minutes: numOr((v as any).horizon_minutes, defaultForm.horizon_minutes),
    step: numOr((v as any).step, defaultForm.step),
    use_llm: boolOr((v as any).use_llm, defaultForm.use_llm),

    // ✅ 新增字段（兼容旧缓存缺失）
    scale_policy: isScalePolicy((v as any).scale_policy)
      ? ((v as any).scale_policy as ScalePolicy)
      : defaultForm.scale_policy,
    safe_low: safeLow,
    safe_high: safeHigh
  }
}

function coerceActionHint(v: unknown): ActionHint {
  if (!isObject(v)) return { kind: 'no_action', params: {} }
  return {
    kind: isActionKind((v as any).kind) ? ((v as any).kind as ActionKind) : 'no_action',
    params: recordOr((v as any).params)
  }
}

function coerceSuggestionItem(v: unknown): SuggestionItem | null {
  if (!isObject(v)) return null
  const title = isString((v as any).title) ? ((v as any).title as string) : ''
  if (!title) return null

  return {
    severity: isSeverity((v as any).severity) ? ((v as any).severity as Severity) : 'info',
    title,
    rationale: isString((v as any).rationale) ? ((v as any).rationale as string) : '',
    evidence: recordOr((v as any).evidence),
    action: coerceActionHint((v as any).action)
  }
}

function coerceResp(v: unknown): SuggestionsResp | null {
  if (!isObject(v)) return null
  if (!isTarget((v as any).target) || !isString((v as any).key) || !Array.isArray((v as any).suggestions)) return null

  return {
    target: (v as any).target as Target,
    key: (v as any).key as string,
    suggestions: ((v as any).suggestions as unknown[])
      .map(coerceSuggestionItem)
      .filter((x): x is SuggestionItem => x !== null),
    llm_summary:
      (v as any).llm_summary === null || isString((v as any).llm_summary)
        ? (((v as any).llm_summary as unknown) as string | null)
        : null,
    meta: (v as any).meta === null || isObject((v as any).meta) ? (((v as any).meta as unknown) as Record<string, unknown> | null) : null
  }
}

function coerceHistory(v: unknown): SuggestionHistoryItem[] {
  if (!Array.isArray(v)) return []
  return (v as unknown[])
    .map((x) => {
      if (!isObject(x)) return null
      const resp = coerceResp((x as any).resp)
      if (!resp || !isString((x as any).id) || !isNumber((x as any).ts)) return null
      return {
        id: (x as any).id as string,
        ts: (x as any).ts as number,
        form: coerceForm((x as any).form),
        resp
      }
    })
    .filter((x): x is SuggestionHistoryItem => x !== null)
}

/* ---------------- persistence ---------------- */

function loadState() {
  const raw = localStorage.getItem(LS_KEY)
  if (!raw) return null
  const parsed = safeJsonParse(raw)
  if (!isObject(parsed)) return null

  const form = coerceForm((parsed as any).form)
  const resp = (parsed as any).resp === null ? null : coerceResp((parsed as any).resp)
  const history = coerceHistory((parsed as any).history)

  return { form, resp, history }
}

function persist(state: { form: SuggestionsForm; resp: SuggestionsResp | null; history: SuggestionHistoryItem[] }) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(toPlainJson(state)))
  } catch {}
}

/* ---------------- store ---------------- */

export const useAiSuggestionsStore = defineStore('aiSuggestions', {
  state: () => {
    const saved = loadState()
    return {
      form: saved?.form ?? { ...defaultForm },
      resp: saved?.resp ?? null,
      history: saved?.history ?? ([] as SuggestionHistoryItem[])
    }
  },

  actions: {
    setResp(resp: SuggestionsResp) {
      this.resp = resp
      persist(this.$state)
    },

    pushHistory(resp: SuggestionsResp) {
      this.history.unshift({
        id: uuid(),
        ts: Date.now(),
        form: toPlainJson(this.form),
        resp: toPlainJson(resp)
      })
      if (this.history.length > 50) this.history.length = 50
      this.resp = resp
      persist(this.$state)
    },

    removeHistory(id: string) {
      this.history = this.history.filter((x) => x.id !== id)
      if (!this.history.length) this.resp = null
      persist(this.$state)
    },

    clearHistory() {
      this.history = []
      this.resp = null
      persist(this.$state)
    },

    reset() {
      this.resp = null
      // 只清 pod，其他保留（按你原逻辑）
      this.form.pod = ''
      persist(this.$state)
    }
  }
})
