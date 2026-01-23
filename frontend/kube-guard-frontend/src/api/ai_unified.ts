// src/api/ai_unified.ts
import { http } from '@/api/http'

export type Target = 'node_cpu' | 'node_mem' | 'pod_cpu'
export type Severity = 'info' | 'warning' | 'critical'
export type ScalePolicy = 'stair' | 'linear'
export type FeedbackOutcome = 'success' | 'fail' | 'ignored'
export type SuggestionState = 'read' | 'ignored'

export interface TsPoint {
  ts: number
  value: number
}

export interface BandPoint {
  ts: number
  yhat: number
  yhat_lower: number
  yhat_upper: number
}

export interface ErrorMetrics {
  note?: string
  mae?: number
  rmse?: number
  mape?: number
}

export interface CpuForecastResp {
  node: string
  history_minutes: number
  horizon_minutes: number
  step: number
  history: TsPoint[]
  forecast: BandPoint[]
  metrics: ErrorMetrics
  meta?: Record<string, any>
}

export interface MemForecastResp {
  node: string
  history_minutes: number
  horizon_minutes: number
  step: number
  history: TsPoint[]
  forecast: BandPoint[]
  metrics: ErrorMetrics
  meta?: Record<string, any>
}

export interface PodCpuForecastResp {
  namespace: string
  pod: string
  history_minutes: number
  horizon_minutes: number
  step: number
  history: TsPoint[]
  forecast: BandPoint[]
  metrics: ErrorMetrics
  meta?: {
    unit?: string
    limit_mcpu?: number | null
    [k: string]: any
  }
}

export type ForecastResp = CpuForecastResp | MemForecastResp | PodCpuForecastResp

export type ActionKind =
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
  suggestion_id?: string | null
  llm_summary?: string | null
  meta?: Record<string, unknown> | null
}

export function normalizeSuggestionKey(
  resp: SuggestionsResp | null | undefined,
  index: number,
  item?: SuggestionItem | null
): string {
  const target = resp?.target ?? 'unknown'
  const key = resp?.key ?? 'unknown'
  const suggestionId = typeof resp?.suggestion_id === 'string' ? resp.suggestion_id : 'none'
  const actionKind = item?.action?.kind ?? 'no_action'
  const title = typeof item?.title === 'string' && item.title ? item.title.slice(0, 40) : 'untitled'
  const idx = Number.isFinite(index) ? index : -1
  return `${target}|${key}|${suggestionId}|${idx}|${actionKind}|${title}`
}

export interface FeedbackPayload {
  target: Target
  key: string
  action_kind: string
  outcome: FeedbackOutcome
  detail?: string
  suggestion_id?: string | null
}

export interface FeedbackResp {
  ok: boolean
  feedback_id?: number
  evolved?: boolean
  evolution?: Record<string, unknown> | null
}

export interface SuggestionStateResp {
  ok: boolean
}

export interface SuggestionStatesResp {
  states: Record<string, SuggestionState>
}

export interface ApplyActionResp {
  ok: boolean
  action: string
  dry_run: boolean
  detail: string
  data: Record<string, any>
}

export type AiTaskStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED'

export interface AiTaskResp<T = unknown> {
  task_id: string
  status: AiTaskStatus
  result?: T
  error?: { detail?: string }
}

type AiErrorKind = 'param' | 'expired' | 'system'

export function classifyAiError(err: any): { kind: AiErrorKind; message: string; status?: number } {
  if (err && err.__ai_kind) {
    return { kind: err.__ai_kind as AiErrorKind, message: String(err.message || ''), status: err.status }
  }
  const status = err?.response?.status ?? err?.status_code ?? err?.status
  const detail = err?.response?.data?.detail
  const message = typeof detail === 'string' ? detail : String(err?.message || '')
  const requestId =
    err?.config?.headers?.['X-Request-Id'] || err?.response?.headers?.['x-request-id']
  const suffix = requestId ? ` (request_id=${requestId})` : ''
  if (status === 400) return { kind: 'param', message: `${message || 'invalid parameters'}${suffix}`, status }
  if (status === 409) {
    return { kind: 'expired', message: `${message || 'suggestion expired, please re-generate'}${suffix}`, status }
  }
  return { kind: 'system', message: `${message || 'system error'}${suffix}`, status }
}

export function explainAiHttpError(err: any): string {
  if (err?.__ai_handled) return ''
  const status = err?.response?.status ?? err?.status_code ?? err?.status
  const detail = err?.response?.data?.detail
  const message = typeof detail === 'string' ? detail : String(err?.message || '')
  const requestId =
    err?.config?.headers?.['X-Request-Id'] || err?.response?.headers?.['x-request-id']
  const suffix = requestId ? ` (request_id=${requestId})` : ''
  if (status === 400) return `${message || '参数错误'}${suffix}`
  if (status === 401) return `未登录或登录已过期${suffix}`
  if (status === 403) return `权限不足${suffix}`
  if (status === 409) return `${message || '建议已过期，请重新生成'}${suffix}`
  if (message) return `${message}${suffix}`
  return `请求失败${suffix}`
}

function paramError(message: string) {
  return { __ai_kind: 'param', message }
}

function normalizeHistoryHorizon<T extends Record<string, any>>(params: T): T {
  const merged = {
    ...params,
    history_minutes: params.history_minutes ?? params.minutes ?? 240,
    horizon_minutes: params.horizon_minutes ?? params.horizon ?? 120,
    step: params.step ?? 60
  }
  if (typeof merged.horizon_minutes === 'number' && merged.horizon_minutes < 15) {
    throw paramError('horizon_minutes must be >= 15')
  }
  return merged
}

function assertTarget(target: string) {
  const ok = target === 'node_cpu' || target === 'node_mem' || target === 'pod_cpu'
  if (!ok) throw paramError('invalid target')
}

export async function forecast(params: {
  target: Target
  node?: string
  namespace?: string
  pod?: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
  cache_ttl?: number
  promql?: string
  async_mode?: boolean
  minutes?: number
  horizon?: number
}) {
  if (!params?.target) throw paramError('target required')
  assertTarget(params.target)
  if (params.target === 'node_cpu' || params.target === 'node_mem') {
    if (!params.node) throw paramError('node required')
  }
  if (params.target === 'pod_cpu') {
    if (!params.namespace || !params.pod) throw paramError('namespace/pod required')
  }
  const merged = normalizeHistoryHorizon(params)
  const resp = await http.get<ForecastResp | AiTaskResp<ForecastResp>>('/api/ai/forecast', {
    params: merged
  })
  const data: any = resp?.data
  if (data && typeof data.task_id === 'string' && data.task_id) {
    const result = await pollTask<ForecastResp>(data.task_id)
    return { ...resp, data: result } as typeof resp
  }
  return resp
}

export async function suggestions(params: {
  target: Target
  node?: string
  namespace?: string
  pod?: string
  threshold?: number
  sustain_minutes?: number
  step?: number
  history_minutes?: number
  horizon_minutes?: number
  use_llm?: boolean
  async_mode?: boolean
  scale_policy?: ScalePolicy
  safe_low?: number
  safe_high?: number
  minutes?: number
  horizon?: number
}) {
  if (!params?.target) throw paramError('target required')
  assertTarget(params.target)
  if (params.target === 'node_cpu' || params.target === 'node_mem') {
    if (!params.node) throw paramError('node required')
  }
  if (params.target === 'pod_cpu') {
    if (!params.namespace || !params.pod) throw paramError('namespace/pod required')
  }
  const merged = {
    ...normalizeHistoryHorizon(params),
    threshold: params.threshold ?? 85,
    sustain_minutes: params.sustain_minutes ?? 15,
    use_llm: params.use_llm ?? false
  }
  const resp = await http.get<SuggestionsResp | AiTaskResp<SuggestionsResp>>('/api/ai/suggestions', {
    params: merged
  })
  const data: any = resp?.data
  if (data && typeof data.task_id === 'string' && data.task_id) {
    const result = await pollTask<SuggestionsResp>(data.task_id)
    return { ...resp, data: result } as typeof resp
  }
  return resp
}

export function execute(params: {
  target: Target
  node?: string
  namespace?: string
  pod?: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
  threshold?: number
  sustain_minutes?: number
  scale_policy?: ScalePolicy
  safe_low?: number
  safe_high?: number
  suggestion_id?: string | null
  suggestion_index: number
  expected_kind?: string
  dry_run: boolean
  exec_namespace?: string
  exec_name?: string
  exec_pod?: string
  replicas?: number
  replicas_delta?: number
  cpu_request_m?: number
  cpu_limit_m?: number
  mem_request_mb?: number
  mem_limit_mb?: number
}) {
  if (!params?.target) throw paramError('target required')
  assertTarget(params.target)
  if (params.target === 'node_cpu' || params.target === 'node_mem') {
    if (!params.node) throw paramError('node required')
  }
  if (params.target === 'pod_cpu') {
    if (!params.namespace || !params.pod) throw paramError('namespace/pod required')
  }
  const merged = {
    ...normalizeHistoryHorizon(params),
    threshold: params.threshold ?? 85,
    sustain_minutes: params.sustain_minutes ?? 15,
    suggestion_id: params.suggestion_id ?? undefined
  }
  return http.post<ApplyActionResp>('/api/ai/execute', null, { params: merged })
}

export function suggestionSummary(params: { suggestion_id: string }) {
  if (!params?.suggestion_id) throw paramError('suggestion_id required')
  return http.get<{ suggestion_id: string; llm_summary: string | null }>(
    '/api/ai/suggestions/summary',
    { params }
  )
}

export function getTask(task_id: string) {
  if (!task_id) throw paramError('task_id required')
  return http.get<AiTaskResp>(`/api/ai/tasks/${task_id}`)
}

export function assistantChat(payload: {
  message: string
  page?: string
  context?: Record<string, unknown>
  use_llm?: boolean
}) {
  if (!payload?.message) throw paramError('message required')
  return http.post<{ reply: string }>('/api/ai/assistant/chat', payload, { timeout: 60000 })
}

export function feedback(payload: FeedbackPayload) {
  if (!payload?.target) throw paramError('target required')
  if (!payload?.key) throw paramError('key required')
  const merged = {
    ...payload,
    action_kind: payload.action_kind || 'no_action',
    outcome: payload.outcome || 'ignored'
  }
  return http.post<FeedbackResp>('/api/ai/feedback', merged)
}

export function markSuggestionState(row_key: string, status: SuggestionState) {
  if (!row_key) throw paramError('row_key required')
  if (!status) throw paramError('status required')
  return http.post<SuggestionStateResp>('/api/ai/suggestions/state', { row_key, status })
}

export function fetchSuggestionStates(row_keys: string[]) {
  if (!Array.isArray(row_keys) || row_keys.length === 0) throw paramError('row_keys required')
  return http.post<SuggestionStatesResp>('/api/ai/suggestions/states', { row_keys })
}

export async function pollTask<T = unknown>(
  task_id: string,
  options?: { interval_ms?: number; timeout_ms?: number }
): Promise<T> {
  if (!task_id) throw paramError('task_id required')
  const interval = Math.max(200, Number(options?.interval_ms ?? 800))
  const timeout = Math.max(1000, Number(options?.timeout_ms ?? 60000))
  const start = Date.now()

  function extractErrorMessage(payload: any): string {
    if (!payload) return 'task failed'
    if (typeof payload === 'string') return payload
    if (typeof payload.detail === 'string') return payload.detail
    if (typeof payload.message === 'string') return payload.message
    if (typeof payload.error === 'string') return payload.error
    if (typeof payload.error?.detail === 'string') return payload.error.detail
    if (typeof payload.error?.message === 'string') return payload.error.message
    return 'task failed'
  }

  function isParamLikeMessage(message: string): boolean {
    const text = String(message || '').toLowerCase()
    if (!text) return false
    return (
      text.includes('invalid parameter') ||
      text.includes('invalid parameters') ||
      text.includes('required') ||
      text.includes('must be >=') ||
      text.includes('must be >') ||
      text.includes('must be <=') ||
      text.includes('must be <') ||
      text.includes('unsupported target')
    )
  }

  while (true) {
    const { data } = await getTask(task_id)
    const status = data?.status
    if (status === 'DONE') {
      return data.result as T
    }
    if (status === 'FAILED') {
      const detail = extractErrorMessage(data?.error)
      const message = String(detail || '')
      const kind: AiErrorKind = isParamLikeMessage(message) ? 'param' : 'system'
      throw { __ai_kind: kind, message }
    }
    if (Date.now() - start > timeout) {
      throw { __ai_kind: 'system', message: 'task timeout' }
    }
    await new Promise((resolve) => setTimeout(resolve, interval))
  }
}
