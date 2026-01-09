// src/api/clusters.ts
import { get, post, del } from './http'

export type ClusterRow = {
  id: number
  name: string
  type: 'self-hosted' | 'managed'
  provider: string
  is_active: number // 0/1
  created_ts: number
  updated_ts: number
}

export type ActiveClusterResp = {
  ok: boolean
  active: ClusterRow | null
}

export type VerifyClusterReq = {
  kubeconfig: string
}

export type VerifyClusterResp = {
  ok: boolean
  test?: {
    ok: string
    server: string
    nodes: string
  }
}

export type AddClusterReq = {
  name: string
  type: 'self-hosted' | 'managed'
  provider: string
  kubeconfig: string
}

export type AddClusterResp = {
  ok: boolean
  id?: number
  test?: any
}

export function fetchClusters() {
  return get<ClusterRow[]>('/api/clusters')
}

export function fetchActiveCluster() {
  return get<ActiveClusterResp>('/api/clusters/active')
}

export function verifyCluster(req: VerifyClusterReq) {
  return post<VerifyClusterResp>('/api/clusters/verify', req)
}

export function addCluster(req: AddClusterReq) {
  return post<AddClusterResp>('/api/clusters', req)
}

export function activateCluster(clusterId: number) {
  return post<{ ok: boolean; active_cluster_id: number; kubeconfig_path?: string }>(
    `/api/clusters/${clusterId}/activate`,
    {}
  )
}

export function deleteCluster(clusterId: number) {
  return del<{ ok: boolean }>(`/api/clusters/${clusterId}`)
}
