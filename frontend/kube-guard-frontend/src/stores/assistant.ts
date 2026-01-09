import { defineStore } from 'pinia'

export type ChatRole = 'user' | 'assistant' | 'system'

export interface ChatMsg {
  id: string
  role: ChatRole
  content: string
  ts: number
}

/** ===== 新版 AI Suggestion 类型（必须与 aiSuggestions.ts 一致） ===== */
export type Target = 'node_cpu' | 'node_mem' | 'pod_cpu'
export type Severity = 'info' | 'warning' | 'critical'

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

export interface AiSuggestionItem {
  severity: Severity
  title: string
  evidence: Record<string, unknown>
  rationale: string
  action: ActionHint
}

export interface AiSuggestionsResp {
  target: Target
  key: string
  suggestions: AiSuggestionItem[]
  llm_summary?: string | null
  meta?: Record<string, unknown> | null
}

/* ===== Assistant UI 兼容结构 ===== */

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH'

export interface AssistantSuggestionItem {
  action: string
  target: Record<string, unknown>
  params: Record<string, unknown>
  message?: string
}

export interface AssistantLastSuggestions {
  node: string
  risk_level: RiskLevel
  reasons: string[]
  items: AssistantSuggestionItem[]
  raw?: AiSuggestionsResp
}

/* ===== converters ===== */

function sevWeight(s: Severity): number {
  if (s === 'critical') return 3
  if (s === 'warning') return 2
  return 1
}

function toRiskLevel(r: AiSuggestionsResp): RiskLevel {
  if (r.suggestions.some((s) => s.severity === 'critical')) return 'HIGH'
  if (r.suggestions.some((s) => s.severity === 'warning')) return 'MEDIUM'
  return 'LOW'
}

function toReasons(r: AiSuggestionsResp): string[] {
  if (!r.suggestions.length) return ['暂无原因（风险较低或数据不足）']
  return [...r.suggestions]
    .sort((a, b) => sevWeight(b.severity) - sevWeight(a.severity))
    .slice(0, 3)
    .map((s) => `${s.title}：${s.rationale}`)
}

function toItems(r: AiSuggestionsResp): AssistantSuggestionItem[] {
  return r.suggestions.map((s) => ({
    action: s.action.kind,
    target: { target: r.target, key: r.key },
    params: s.action.params,
    message: s.title
  }))
}

function convert(r: AiSuggestionsResp): AssistantLastSuggestions {
  return {
    node: r.key,
    risk_level: toRiskLevel(r),
    reasons: toReasons(r),
    items: toItems(r),
    raw: r
  }
}

/* ===== store ===== */

export const useAssistantStore = defineStore('assistant', {
  state: () => ({
    open: false,
    messages: [] as ChatMsg[],
    lastSuggestions: null as AssistantLastSuggestions | null
  }),

  actions: {
    toggle(v?: boolean) {
      this.open = typeof v === 'boolean' ? v : !this.open
    },

    clearChat() {
      this.messages = []
    },

    push(role: ChatRole, content: string) {
      this.messages.push({
        id: `${Date.now()}_${Math.random().toString(16).slice(2)}`,
        role,
        content,
        ts: Date.now()
      })
    },

    setLastSuggestions(ai: AiSuggestionsResp | null) {
      this.lastSuggestions = ai ? convert(ai) : null
    }
  }
})
