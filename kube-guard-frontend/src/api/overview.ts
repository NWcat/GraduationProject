// src/api/overview.ts
import { get } from './http'

export type OverviewStatItem = {
  key: string
  label: string
  value: number
  unit?: string
  desc?: string
}

export type CapacityItem = {
  key: 'cpu' | 'memory' | 'storage' | 'network'
  label: string
  value: number // 0-100
  unit: '%'
  desc?: string
}

export type OpsItem = {
  title: string
  desc?: string
  extra?: string
  level: 'ok' | 'warn' | 'info'
}

export type ClusterBasic = {
  name: string
  status: 'running' | 'warning' | 'down'
  clusterType?: string
  k8sVersion?: string
  platformVersion?: string
  location?: string
}

export type ClusterResourceSummary = {
  nodes: number
  namespaces: number
  pods: number
  alertRules?: number
}

export type ClusterHealthItem = {
  level: 'ok' | 'warn' | 'error'
  text: string
}

export type OverviewResponse = {
  overviewStats: OverviewStatItem[]
  capacityStats: CapacityItem[]
  opsSummary: OpsItem[]
  cluster: {
    basic: ClusterBasic
    resources: ClusterResourceSummary
    health: ClusterHealthItem[]
  }
}

/**
 * ✅ 建议后端提供一个聚合接口：
 * GET /api/overview
 *
 * 后端可以内部去 Prometheus / Alertmanager / K8s API 聚合出：
 * - 概览数字（nodes/pods/workloads）
 * - CPU/内存/存储/网络 使用率（Prometheus）
 * - 最近告警摘要（Alertmanager）
 * - 集群健康点检（K8s API）
 */
export function fetchOverview() {
  return get<OverviewResponse>('/api/overview')
}
