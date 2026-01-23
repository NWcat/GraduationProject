// src/api/ai.ts
import {
  forecast as unifiedForecast,
  suggestions as unifiedSuggestions,
  execute as unifiedExecute,
  suggestionSummary as unifiedSuggestionSummary,
  assistantChat as unifiedAssistantChat,
  feedback as unifiedFeedback,
  classifyAiError
} from '@/api/ai_unified'
import type { Target, ScalePolicy } from '@/api/ai_unified'

export type {
  Target,
  Severity,
  ScalePolicy,
  ForecastResp,
  ActionKind,
  ActionHint,
  SuggestionItem,
  SuggestionsResp,
  FeedbackPayload,
  FeedbackResp,
  ApplyActionResp,
  TsPoint,
  BandPoint,
  ErrorMetrics,
  CpuForecastResp,
  MemForecastResp,
  PodCpuForecastResp
} from '@/api/ai_unified'

export { classifyAiError }

export function fetchCpuForecast(params: {
  node: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
}) {
  return unifiedForecast({ target: 'node_cpu', ...params }) as any
}

export function fetchMemForecast(params: {
  node: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
}) {
  return unifiedForecast({ target: 'node_mem', ...params }) as any
}

export function fetchPodCpuForecast(params: {
  namespace: string
  pod: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
}) {
  return unifiedForecast({ target: 'pod_cpu', ...params }) as any
}

export function fetchUnifiedForecast(params: {
  target: Target
  node?: string
  namespace?: string
  pod?: string
  history_minutes?: number
  horizon_minutes?: number
  step?: number
  cache_ttl?: number
  promql?: string
  minutes?: number
  horizon?: number
}) {
  return unifiedForecast(params as any) as any
}

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
  scale_policy?: ScalePolicy
  safe_low?: number
  safe_high?: number
  minutes?: number
  horizon?: number
}) {
  return unifiedSuggestions(params as any) as any
}

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
  scale_policy?: ScalePolicy
  safe_low?: number
  safe_high?: number
  suggestion_index: number
  dry_run: boolean
  exec_namespace?: string
  exec_name?: string
  exec_pod?: string
}) {
  return unifiedExecute(params as any) as any
}

export const assistantChat = unifiedAssistantChat
export const feedback = unifiedFeedback

export function fetchSuggestionSummary(params: { suggestion_id: string }) {
  return unifiedSuggestionSummary(params) as any
}
