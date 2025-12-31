// src/api/nodes.ts
import { get } from './http'

export type NodeRow = {
  name: string
  ip: string
  role: 'control-plane' | 'worker'
  status: 'Ready' | 'NotReady'
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
