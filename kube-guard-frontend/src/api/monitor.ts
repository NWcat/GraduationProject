import { http } from '@/api/http'

export type MonitorOverviewResp = {
  status: 'success' | 'error'
  data: {
    time: { range: string; minutes: number; now: string }
    health: {
      promOk: boolean
      nodesTotal: number
      nodesReady: number
      alertFiring: number
      alertPending: number
    }
    resource: {
      cpuUsedPct: number
      memUsedPct: number
      fsUsedPct: number
    }
    trends: {
      cpuUsedPct: Array<[number, number]>
      memUsedPct: Array<[number, number]>
      fsUsedPct: Array<[number, number]>
    }
    top: {
      podCpu: Array<{ rank: number; metric: Record<string, string>; value: number; valueText: string }>
      podMem: Array<{ rank: number; metric: Record<string, string>; value: number; valueText: string }>
      podNet: Array<{ rank: number; metric: Record<string, string>; value: number; valueText: string }>
    }
  }
}

export async function fetchMonitorOverview(params?: { range?: string }): Promise<MonitorOverviewResp> {
  const res = await http.get<MonitorOverviewResp>('/api/monitor/overview', { params })
  return res.data // ✅ 只返回业务体
}
