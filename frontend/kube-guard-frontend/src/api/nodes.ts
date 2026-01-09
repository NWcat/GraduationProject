// src/api/nodes.ts
import { get, post } from './http'

export type NodeRow = {
  name: string
  ip: string
  role: 'control-plane' | 'worker'
  status: 'Ready' | 'NotReady'
  unschedulable?: boolean
  kubeletVersion: string
  osImage: string
  kernelVersion: string
  containerRuntime: string
  cpuTotal: number
  cpuUsed: number
  memTotal: number
  memUsed: number
  podCapacity: number
  podUsed: number
}

export function fetchNodes() {
  return get<NodeRow[]>('/api/nodes')
}

export type JoinInfoResp =
  | {
      type: 'k3s'
      ok: true
      command: string
      params?: {
        node_ip?: string | null
        flannel_iface?: string | null
        k3s_version?: string | null
      }
    }
  | {
      type: 'k3s'
      ok: false
      hint: string
      command_template: string
    }

export interface FetchJoinInfoParams {
  server?: string
  token?: string
  node_ip?: string
  flannel_iface?: string
  k3s_version?: string
}

export function fetchJoinInfo(params: FetchJoinInfoParams) {
  const sp = new URLSearchParams()

  if (params.server) sp.set('server', params.server)
  if (params.token) sp.set('token', params.token)
  if (params.node_ip) sp.set('node_ip', params.node_ip)
  if (params.flannel_iface) sp.set('flannel_iface', params.flannel_iface)
  if (params.k3s_version) sp.set('k3s_version', params.k3s_version)

  const qs = sp.toString()
  return get<JoinInfoResp>(`/api/nodes/join-info${qs ? `?${qs}` : ''}`)
}


export type RemoveNodeResp = {
  ok: boolean
  steps?: any[]
  hint?: string
  node_side_hint?: string[]
  detail?: any
}


export function removeNode(
  nodeName: string,
  params?: { grace_seconds?: number; timeout_seconds?: number; force?: boolean }
) {
  const sp = new URLSearchParams()
  if (params?.grace_seconds != null) sp.set('grace_seconds', String(params.grace_seconds))
  if (params?.timeout_seconds != null) sp.set('timeout_seconds', String(params.timeout_seconds))
  if (params?.force != null) sp.set('force', params.force ? 'true' : 'false')
  const qs = sp.toString()
  return post<RemoveNodeResp>(`/api/nodes/${encodeURIComponent(nodeName)}/remove${qs ? `?${qs}` : ''}`, {})
}

export type OfflineNodeResp = {
  ok: boolean
  steps?: any[]
  hint?: string
}

export function offlineNode(
  nodeName: string,
  params?: { drain?: boolean; grace_seconds?: number; timeout_seconds?: number; force?: boolean }
) {
  const sp = new URLSearchParams()
  if (params?.drain != null) sp.set('drain', params.drain ? 'true' : 'false')
  if (params?.grace_seconds != null) sp.set('grace_seconds', String(params.grace_seconds))
  if (params?.timeout_seconds != null) sp.set('timeout_seconds', String(params.timeout_seconds))
  if (params?.force != null) sp.set('force', params.force ? 'true' : 'false')
  const qs = sp.toString()
  return post<OfflineNodeResp>(`/api/nodes/${encodeURIComponent(nodeName)}/offline${qs ? `?${qs}` : ''}`, {})
}

export type UncordonResp = { ok: boolean; node?: string; action?: string; detail?: any }

export function uncordonNode(nodeName: string) {
  return post<UncordonResp>(`/api/nodes/${encodeURIComponent(nodeName)}/uncordon`, {})
}
