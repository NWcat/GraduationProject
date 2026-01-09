// src/api/ops.ts
import { http } from '@/api/http'

export interface HealEvent {
  id: number
  ts: number
  namespace: string
  pod: string
  reason: string
  action: string
  result: string
}

export interface OpsAction {
  id: number
  ts: number
  action: string
  target: string
  params: string
  dry_run: number
  result: string
  detail: string
}

export interface HealStatusResp {
  running: boolean
  interval_sec: number
  last_run_ts: number | null
  last_summary: any | null
  last_error: string | null
  enabled: boolean
  execute: boolean
  max_per_cycle: number
  cooldown_sec: number
  allow_ns: string
  deny_ns: string
  only_reasons: string
}

export function runHealOnce(params?: { namespace?: string }) {
  return http.post('/api/ops/heal/run', null, { params })
}

export function fetchHealEvents(params?: { limit?: number; offset?: number }) {
  return http.get<{ items: HealEvent[] }>('/api/ops/heal/events', { params })
}

export function deleteHealEvent(id: number) {
  return http.delete<{ ok: boolean }>('/api/ops/heal/events/' + id)
}

export function fetchOpsActions(params?: { limit?: number; offset?: number }) {
  return http.get<{ items: OpsAction[] }>('/api/ops/actions', { params })
}

export function deleteOpsAction(id: number) {
  return http.delete<{ ok: boolean }>('/api/ops/actions/' + id)
}

export function fetchHealStatus() {
  return http.get<HealStatusResp>('/api/ops/heal/status')
}

// ===================== ✅ 阶段 3.3：Deployment 视图 =====================

export type HealDeploymentStatus = 'normal' | 'pending' | 'circuit_open'

export interface HealDeploymentItem {
  namespace: string
  deployment_uid: string
  deployment_name: string
  status: HealDeploymentStatus
  fail_count: number
  is_failing: number
  pending_until_ts: number
  last_action: string
  last_reason: string
  last_pod: string
  last_ts: number
  last_result: string
}

export function fetchHealDeployments(params?: { limit?: number; offset?: number; namespace?: string }) {
  return http.get<{ items: HealDeploymentItem[] }>('/api/ops/heal/deployments', { params })
}

export function fetchHealDeploymentDetail(namespace: string, deployment_uid: string) {
  return http.get<{ ok: boolean; item?: HealDeploymentItem; reason?: string }>(
    `/api/ops/heal/deployments/${namespace}/${deployment_uid}`
  )
}

// ===================== ✅ 复位（reset） =====================

export interface HealResetReq {
  namespace?: string | null
  deployment_uid?: string | null
  deployment_name?: string | null
  restore_replicas?: number | null
}

export interface HealResetResp {
  ok: boolean
  reason?: string | null
}

export function healReset(payload: HealResetReq) {
  return http.post<HealResetResp>('/api/ops/heal/reset', payload)
}

// ===================== ✅ Decay 配置（按钮用） =====================

export interface HealDecayCfgResp {
  enabled: boolean
  step: number
}

export function fetchHealDecayConfig() {
  return http.get<HealDecayCfgResp>('/api/ops/heal/decay')
}

export function setHealDecayConfig(payload: HealDecayCfgResp) {
  return http.put<HealDecayCfgResp>('/api/ops/heal/decay', payload)
}
