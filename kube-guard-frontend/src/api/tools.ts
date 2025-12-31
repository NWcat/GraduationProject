// src/api/tools.ts
import { http, get, post } from './http'

/** =======================
 *  诊断
 *  ======================= */
export type DiagnosticItem = {
  key: string
  title: string
  level: 'ok' | 'warn' | 'error'
  detail?: string
}

export type DiagnosticResponse = {
  updatedAt: string
  items: DiagnosticItem[]
}

// 诊断：JSON
export function fetchDiagnostics() {
  return get<DiagnosticResponse>('/api/tools/diagnostics')
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
 *  kubectl 终端（最小可用：exec）
 *  ======================= */
export type KubectlExecReq = {
  command: string               // 例如：get pods -A（不写 kubectl 前缀）
  namespace?: string            // 可选
  timeout_seconds?: number      // 1~30
  output?: 'text' | 'json' | 'yaml'
}

export type KubectlExecResp = {
  ok: boolean
  stdout: string
  stderr: string
  exit_code: number
}

export function kubectlExec(data: KubectlExecReq) {
  return post<KubectlExecResp>('/api/tools/kubectl/exec', data)
}
