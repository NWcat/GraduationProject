// src/api/tools.ts
import { http, get, post } from './http'

/** =======================
 *  巡检（One-click Inspection）
 *  ======================= */

export type InspectLevel = 'ok' | 'warn' | 'error' | 'skip'

export type InspectItem = {
  key: string
  title: string
  level: InspectLevel
  detail?: string
  suggestion?: string | null
  evidence?: Record<string, any>
  durationMs?: number
}

export type InspectSummary = {
  total: number
  ok: number
  warn: number
  error: number
  skip: number
}

export type InspectReport = {
  runId: string
  updatedAt: string
  durationMs: number
  summary: InspectSummary
  items: InspectItem[]
  meta?: Record<string, any>
  reportUrl?: string          // GET /api/tools/inspect/report/{runId}.html
  jsonUrl?: string            // GET /api/tools/inspect/report/{runId}.json
}

export function runInspection(params?: {
  include?: string            // 逗号分隔：prom,nodes,system,pods,events,storage,dns
  per_check_timeout_seconds?: number
  total_timeout_seconds?: number
  max_workers?: number
}) {
  return post<InspectReport>('/api/tools/inspect/run', undefined, { params })
}

/** 可选：直接取一次巡检（GET） */
export function fetchInspection(params?: {
  format?: 'json' | 'html'
  include?: string
  save?: boolean
}) {
  return get<any>('/api/tools/inspect', { params })
}

/** =======================
 *  kubeconfig 下载（Blob）
 *  ======================= */
export async function downloadKubeconfig(): Promise<Blob> {
  const resp = await http.get('/api/tools/kubeconfig', {
    responseType: 'blob',
  })
  return resp.data as Blob
}

/** =======================
 *  kubectl 终端（exec）
 *  ======================= */
export type KubectlExecReq = {
  command: string
  namespace?: string
  timeout_seconds?: number
  output?: 'text' | 'json' | 'yaml'
}

export type KubectlExecResp = {
  ok: boolean
  stdout: string
  stderr: string
  exit_code: number
}

export function kubectlExec(data: KubectlExecReq) {
  return post<KubectlExecResp>('/api/tools/k8s/kubectl/exec', data)
}
