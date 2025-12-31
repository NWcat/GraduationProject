// src/api/workloads.ts
import axios from 'axios'

export type Kind = 'deployment' | 'statefulset' | 'pod'
export type RowStatus = 'running' | 'warning' | 'failed' | 'unknown'

export type WorkloadRow = {
  kind: Kind
  kindTag?: string
  name: string
  namespace: string
  status: RowStatus
  image?: string
  age?: string

  replicas?: number
  readyReplicas?: number
  strategy?: string
  updatedAt?: string

  node?: string
  podIP?: string
  restarts?: number
  createdAt?: string
}

export type WorkloadsListResp = {
  items: WorkloadRow[]
}

const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000',
  timeout: 15000,
})

export async function fetchNamespaces(): Promise<string[]> {
  const { data } = await http.get('/api/workloads/namespaces')
  return data
}

export async function fetchWorkloads(params: {
  kind: Kind
  namespace?: string
  status?: RowStatus
  keyword?: string
}): Promise<WorkloadsListResp> {
  const { data } = await http.get('/api/workloads', { params })
  return data
}

export async function fetchWorkloadYaml(params: {
  kind: Kind
  namespace: string
  name: string
}): Promise<{ yaml: string }> {
  const { data } = await http.get('/api/workloads/yaml', { params })
  return data
}

export async function scaleWorkload(payload: {
  kind: 'deployment' | 'statefulset'
  namespace: string
  name: string
  replicas: number
}): Promise<{ ok: boolean }> {
  const { data } = await http.post('/api/workloads/scale', payload)
  return data
}

export async function restartWorkload(payload: {
  kind: 'deployment' | 'statefulset'
  namespace: string
  name: string
}): Promise<{ ok: boolean }> {
  const { data } = await http.post('/api/workloads/restart', payload)
  return data
}

export async function deletePod(payload: {
  namespace: string
  name: string
}): Promise<{ ok: boolean }> {
  const { data } = await http.post('/api/workloads/pod/delete', payload)
  return data
}

/** ✅ 新建/应用：kubectl apply -f - */
export async function applyManifest(payload: { yaml: string }): Promise<{ ok: boolean; stdout: string; stderr: string }> {
  const { data } = await http.post('/api/workloads/apply', payload)
  return data
}

/** （可选）Pod 日志 */
export async function fetchPodLogs(params: {
  namespace: string
  name: string
  container?: string
  tailLines?: number
}): Promise<{ logs: string }> {
  const { data } = await http.get('/api/workloads/pod/logs', { params })
  return data
}

export async function deleteWorkload(payload: {
  kind: 'deployment' | 'statefulset'
  namespace: string
  name: string
  deletePVC?: boolean
}): Promise<{ ok: boolean; message?: string }> {
  const { data } = await http.post('/api/workloads/delete', payload)
  return data
}
