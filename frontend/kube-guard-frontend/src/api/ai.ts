// src/api/ai.ts
import { http } from '@/api/http'

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

export function fetchCpuForecast(params: {
  node: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
}) {
  return http.get<CpuForecastResp>('/api/ai/cpu/forecast', { params })
}

export function fetchMemForecast(params: {
  node: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
}) {
  return http.get<MemForecastResp>('/api/ai/mem/forecast', { params })
}

export function fetchPodCpuForecast(params: {
  namespace: string
  pod: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
}) {
  return http.get<PodCpuForecastResp>('/api/ai/pod/cpu/forecast', { params })
}

// ====== 智能建议 / 动作执行 / 助手聊天（新版）======

export type Target = 'node_cpu' | 'node_mem' | 'pod_cpu'
export type Severity = 'info' | 'warning' | 'critical'
export type ScalePolicy = 'stair' | 'linear'

/**
 * ✅ 前端 ActionKind 建议“超集”，但“可执行”只支持：
 * - scale_deployment / restart_deployment / restart_pod / delete_pod
 * 其余 kind 仅展示，不走 execute
 */
export type ActionKind =
  | 'scale_deployment'
  | 'restart_deployment'
  | 'restart_pod'
  | 'delete_pod'
  | 'no_action'
  // 其他保留展示
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
  llm_summary?: string | null
  meta?: Record<string, unknown> | null
}

/**
 * ✅ 智能建议（新增：scale_policy / safe_low / safe_high）
 * - 仅对 pod_cpu 的扩容建议有意义；其他 target 传了也不会影响（后端会忽略/不使用）
 */
export function fetchSuggestions(params: {
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

  // ✅ 新增：扩容策略（pod_cpu）
  scale_policy?: ScalePolicy
  safe_low?: number
  safe_high?: number

  // compat
  minutes?: number
  horizon?: number
}) {
  const merged = {
    ...params,
    history_minutes: params.history_minutes ?? params.minutes,
    horizon_minutes: params.horizon_minutes ?? params.horizon
  }
  return http.get<SuggestionsResp>('/api/ai/suggestions', { params: merged })
}

/** 你原来的 /api/ops/actions/apply 仍然可保留给“手动动作测试” */
export interface ApplyActionResp {
  ok: boolean
  action: string
  dry_run: boolean
  detail: string
  data: Record<string, any>
}

export function applyOpsAction(payload: {
  action: string
  target: Record<string, unknown>
  params: Record<string, unknown>
  dry_run?: boolean
}) {
  return http.post<ApplyActionResp>('/api/ops/actions/apply', payload)
}

/**
 * ✅ 一键执行建议（新增：scale_policy / safe_low / safe_high）
 * 后端 /api/ai/execute 会重新生成一次建议，所以这里的参数必须与生成建议时一致。
 */
export function executeSuggestion(params: {
  target: Target
  node?: string
  namespace?: string
  pod?: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
  threshold?: number
  sustain_minutes?: number

  // ✅ 新增：扩容策略（pod_cpu）
  scale_policy?: ScalePolicy
  safe_low?: number
  safe_high?: number

  suggestion_index: number
  dry_run: boolean
  exec_namespace?: string
  exec_name?: string
  exec_pod?: string
}) {
  return http.post<ApplyActionResp>('/api/ai/execute', null, { params })
}

// ✅ 助手聊天
export function assistantChat(payload: {
  message: string
  page?: string
  context?: Record<string, unknown>
  use_llm?: boolean
}) {
  return http.post<{ reply: string }>('/api/ai/assistant/chat', payload)
}
